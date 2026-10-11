-- OcuSense accounts: public profiles (usernames), game scores, friends and the leaderboards.
--
-- Run once in the Supabase project the website uses: Dashboard › SQL Editor › paste › Run.
-- Safe to run again. See docs/accounts.md.
--
-- What is stored: a username per account and game scores. Never eye measurements,
-- recordings or calibration — those stay on the person's Mac.

-- ---------------------------------------------------------------- profiles
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username text,  -- null until chosen (e.g. accounts made on the website)
  created_at timestamptz not null default now(),
  constraint username_format check (username is null or username ~ '^[A-Za-z0-9_]{3,20}$')
);
create unique index if not exists profiles_username_unique on public.profiles (lower(username));

alter table public.profiles enable row level security;
drop policy if exists "Profiles are readable by everyone" on public.profiles;
create policy "Profiles are readable by everyone" on public.profiles for select using (true);
-- No insert/update policies: profiles are written only by the trigger below, from the
-- username the app sends at sign-up or on the Account page (auth user metadata).

create or replace function public.sync_profile() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  wanted text := nullif(new.raw_user_meta_data ->> 'username', '');
begin
  if wanted is not null and wanted !~ '^[A-Za-z0-9_]{3,20}$' then
    wanted := null;
  end if;
  if wanted is not null and exists (
    select 1 from public.profiles p where lower(p.username) = lower(wanted) and p.id <> new.id
  ) then
    wanted := null;  -- taken meanwhile: keep the old name; the app checks availability first
  end if;
  insert into public.profiles (id, username) values (new.id, wanted)
  on conflict (id) do update set username = coalesce(excluded.username, public.profiles.username);
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.sync_profile();
drop trigger if exists on_auth_user_updated on auth.users;
create trigger on_auth_user_updated after update of raw_user_meta_data on auth.users
  for each row execute function public.sync_profile();

-- Profiles for accounts that already existed before this script.
insert into public.profiles (id) select id from auth.users on conflict (id) do nothing;

-- Lets the sign-up form say "That username is taken" before creating the account.
create or replace function public.username_available(name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select name ~ '^[A-Za-z0-9_]{3,20}$'
     and not exists (
       select 1 from public.profiles p
       where lower(p.username) = lower(name) and p.id is distinct from auth.uid()
     );
$$;
grant execute on function public.username_available(text) to anon, authenticated;

-- ---------------------------------------------------------------- game scores
create table if not exists public.game_scores (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  game text not null,  -- which games: the game_scores_game_check constraint below
  score integer not null check (score between 0 and 100000),
  details jsonb not null default '{}'::jsonb check (pg_column_size(details) < 2000),  -- e.g. words, best combo
  created_at timestamptz not null default now()
);
create index if not exists game_scores_by_game on public.game_scores (game, score desc);
-- The games with leaderboards (ids as in ocusense/scores.py). Add new games here; re-running replaces it.
alter table public.game_scores drop constraint if exists game_scores_game_check;
alter table public.game_scores add constraint game_scores_game_check
  check (game in ('blink_code_challenge', 'eye_runner'));

alter table public.game_scores enable row level security;
drop policy if exists "Scores are readable by everyone" on public.game_scores;
create policy "Scores are readable by everyone" on public.game_scores for select using (true);
drop policy if exists "Players add their own scores" on public.game_scores;
create policy "Players add their own scores" on public.game_scores for insert to authenticated
  with check (user_id = (select auth.uid()));
-- No update or delete policies: a submitted score can't be changed.

-- Each player's best score per game, for players who chose a username.
create or replace view public.leaderboard with (security_invoker = true) as
select distinct on (s.user_id, s.game)
  s.game, p.username, s.score, s.created_at
from public.game_scores s
join public.profiles p on p.id = s.user_id
where p.username is not null
order by s.user_id, s.game, s.score desc, s.created_at;

-- ---------------------------------------------------------------- friends
-- One row per pair of players: a request (pending) that becomes a friendship (accepted).
-- Rows are written only through the functions below, never directly by the app.
create table if not exists public.friendships (
  requester uuid not null references public.profiles (id) on delete cascade,
  addressee uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'pending' check (status in ('pending', 'accepted')),
  created_at timestamptz not null default now(),
  primary key (requester, addressee),
  constraint not_yourself check (requester <> addressee)
);
-- At most one row per pair, whoever asked first.
create unique index if not exists friendships_one_per_pair
  on public.friendships (least(requester, addressee), greatest(requester, addressee));
create index if not exists friendships_by_addressee on public.friendships (addressee);

alter table public.friendships enable row level security;
drop policy if exists "Players see their own friendships" on public.friendships;
create policy "Players see their own friendships" on public.friendships for select to authenticated
  using ((select auth.uid()) in (requester, addressee));
-- No insert/update/delete policies: request_friend, respond_friend and remove_friend do the writing.

-- Ask someone (by username) to be friends. If they already asked you, this accepts.
-- Returns: requested, accepted, already_friends, already_requested, not_found, self or too_many.
create or replace function public.request_friend(name text) returns text
language plpgsql security definer set search_path = '' as $$
declare
  me uuid := auth.uid();
  other uuid;
  existing public.friendships%rowtype;
begin
  if me is null then
    raise exception 'Log in first' using errcode = '28000';
  end if;
  select p.id into other from public.profiles p where lower(p.username) = lower(name);
  if other is null then
    return 'not_found';
  end if;
  if other = me then
    return 'self';
  end if;
  select * into existing from public.friendships f
   where (f.requester = me and f.addressee = other) or (f.requester = other and f.addressee = me);
  if found then
    if existing.status = 'accepted' then
      return 'already_friends';
    elsif existing.requester = me then
      return 'already_requested';
    end if;
    update public.friendships set status = 'accepted' where requester = other and addressee = me;
    return 'accepted';
  end if;
  if (select count(*) from public.friendships f where f.requester = me and f.status = 'pending') >= 50 then
    return 'too_many';  -- a simple brake on request spam
  end if;
  insert into public.friendships (requester, addressee) values (me, other);
  return 'requested';
end $$;

-- Accept or decline a request someone sent you. Returns accepted, declined or not_found.
create or replace function public.respond_friend(other uuid, accept boolean) returns text
language plpgsql security definer set search_path = '' as $$
declare
  me uuid := auth.uid();
begin
  if me is null then
    raise exception 'Log in first' using errcode = '28000';
  end if;
  if accept then
    update public.friendships set status = 'accepted'
     where requester = other and addressee = me and status = 'pending';
  else
    delete from public.friendships where requester = other and addressee = me and status = 'pending';
  end if;
  if not found then
    return 'not_found';
  end if;
  return case when accept then 'accepted' else 'declined' end;
end $$;

-- Unfriend, or withdraw a request you sent. Either side can do it.
create or replace function public.remove_friend(other uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then
    raise exception 'Log in first' using errcode = '28000';
  end if;
  delete from public.friendships
   where (requester = auth.uid() and addressee = other) or (requester = other and addressee = auth.uid());
end $$;

-- Your friends and open requests: status friend, incoming (they asked you) or outgoing (you asked them).
create or replace function public.my_friends()
returns table (user_id uuid, username text, status text, since timestamptz)
language sql stable security invoker set search_path = '' as $$
  select case when f.requester = (select auth.uid()) then f.addressee else f.requester end,
         p.username,
         case when f.status = 'accepted' then 'friend'
              when f.addressee = (select auth.uid()) then 'incoming'
              else 'outgoing' end,
         f.created_at
  from public.friendships f
  join public.profiles p
    on p.id = case when f.requester = (select auth.uid()) then f.addressee else f.requester end
  where (select auth.uid()) in (f.requester, f.addressee)
  order by 3, lower(p.username);
$$;

grant execute on function public.request_friend(text) to authenticated;
grant execute on function public.respond_friend(uuid, boolean) to authenticated;
grant execute on function public.remove_friend(uuid) to authenticated;
grant execute on function public.my_friends() to authenticated;
revoke execute on function public.request_friend(text) from anon, public;
revoke execute on function public.respond_friend(uuid, boolean) from anon, public;
revoke execute on function public.remove_friend(uuid) from anon, public;
revoke execute on function public.my_friends() from anon, public;

-- ---------------------------------------------------------------- ranked leaderboards
-- Each player's best score in one game, ranked (ties share a place). scope 'everyone' or 'friends'
-- (you and your accepted friends). Returns the top max_rows plus your own row if you are further down.
create or replace function public.game_leaderboard(game_name text, scope text default 'everyone',
                                                   max_rows integer default 50)
returns table (place bigint, username text, score integer, created_at timestamptz, is_me boolean)
language sql stable security invoker set search_path = '' as $$
  with circle as (
    select (select auth.uid()) as id
    union
    select case when f.requester = (select auth.uid()) then f.addressee else f.requester end
    from public.friendships f
    where f.status = 'accepted' and (select auth.uid()) in (f.requester, f.addressee)
  ), best as (
    select distinct on (s.user_id) s.user_id, s.score, s.created_at
    from public.game_scores s
    join public.profiles p on p.id = s.user_id and p.username is not null
    where s.game = game_name
      and (scope = 'everyone' or s.user_id in (select c.id from circle c))
    order by s.user_id, s.score desc, s.created_at
  ), ranked as (
    select rank() over (order by b.score desc) as place, b.user_id, b.score, b.created_at
    from best b
  )
  select r.place, p.username, r.score, r.created_at, r.user_id is not distinct from (select auth.uid())
  from ranked r
  join public.profiles p on p.id = r.user_id
  where r.place <= least(greatest(max_rows, 1), 200) or r.user_id = (select auth.uid())
  order by r.place, r.created_at;
$$;
grant execute on function public.game_leaderboard(text, text, integer) to anon, authenticated;
