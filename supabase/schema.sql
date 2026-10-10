-- OcuSense accounts: public profiles (usernames) and game scores for the leaderboards.
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
  game text not null check (game in ('blink_code_challenge')),  -- add new games here
  score integer not null check (score between 0 and 100000),
  details jsonb not null default '{}'::jsonb check (pg_column_size(details) < 2000),  -- e.g. words, best combo
  created_at timestamptz not null default now()
);
create index if not exists game_scores_by_game on public.game_scores (game, score desc);

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
