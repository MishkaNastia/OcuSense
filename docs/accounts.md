# Accounts and leaderboards

OcuSense accounts are optional. One account works on both the website and the Mac
app, and it is what the game leaderboards build on. An account stores only an
email address, a username and (later) game scores. Eye measurements, recordings
and calibration never leave the Mac.

## How it works

- **Sign-in service:** the website's Supabase project (Supabase Auth). The app uses
  the same public values as the website: the project URL and the **publishable**
  (anon) key. The secret / service-role key is never needed, and the app refuses one.
- **Mac app:**
  - `ocusense/accounts.py` makes the Supabase calls (sign up, log in, renew, reset
    password, change username, log out).
  - `ocusense/ui/account_service.py` runs them in the background.
  - `ocusense/ui/account_page.py` is the Account page (sidebar › Log in).
- **What the Mac remembers:**
  - `~/Library/Application Support/OcuSense/account.json`: user id, email and
    username. Nothing secret.
  - The sign-in (refresh) token, in the macOS Keychain under
    `app.ocusense.OcuSense`. Passwords are never stored.
- **Usernames:** 3–20 letters, numbers or underscores, unique ignoring case. They
  are chosen at sign-up in the app, or later on the Account page. Accounts made on
  the website start without one.
- **Email confirmation:** when it's on in Supabase, a new account works after the
  link in the email is opened. The link goes to the website (`/auth/callback`); then
  you log in in the app.

## Setting it up (once, for everyone who gets the app)

The website (`website/`) and the app use **one** Supabase project, so one account works in both.

1. **Create the project.** Sign in at https://supabase.com and create a free project.
2. **Set up the database.** Supabase › SQL Editor › paste `supabase/schema.sql` › Run. It creates:
   - `profiles`: public usernames, filled in automatically from sign-ups.
   - `username_available()`: lets the form say "taken" before sign-up.
   - `game_scores`, `friendships` and the leaderboard and friend functions (see below).

   Running it again is safe, and it is needed again after this file changes.
3. **Choose how new accounts start.** While the website runs only on your own computer,
   confirmation emails would link to `localhost`, which other people can't open. So switch
   **Authentication › Sign In / Providers › Email › Confirm email** off: accounts then work
   straight away. Once the website is public, switch it back on and set the **Site URL**
   (Authentication › URL Configuration) to the website's address, with
   `https://…/auth/callback` in the Redirect URLs.
4. **Connect the app and the website, and rebuild.** Copy the *Project URL* and the
   **publishable** key from Project Settings › API Keys, then run:

   ```bash
   .venv/bin/python packaging/connect_supabase.py https://YOUR-PROJECT.supabase.co sb_publishable_… --build
   ```

   The script:
   - refuses a secret key
   - asks the project whether sign-in and the database are ready, and says exactly what's missing
   - saves `ocusense/supabase.json`, which is bundled into the app, so everyone who gets this
     `OcuSense.app` can log in
   - creates `website/.env.local` if it doesn't exist
   - rebuilds the app

   `ocusense/supabase.json` is committed to the repository, so every copy and every GitHub build
   has login without extra setup; `website/.env.local` stays git-ignored. The publishable key is
   designed to be public: what users can do is limited by the database rules in `schema.sql`.
   Never commit the secret key.

Other ways to point a copy of the app at a project:

- `~/Library/Application Support/OcuSense/supabase.json`: just your Mac, no rebuild needed.
- `OCUSENSE_SUPABASE_URL` and `OCUSENSE_SUPABASE_KEY`: while developing.

Without any of these, the Account page says "Accounts aren't set up in this copy of OcuSense",
and everything else works as before.

## Leaderboards and friends

**In the app**

- **Games › Leaderboards** has one game at a time (Blink Code challenge, EyeGame) and three tabs:
  - **On this Mac:** your top 10 per game. Kept in
    `~/Library/Application Support/OcuSense/scores.json`, with or without an account. A high score
    from before this existed shows as "earlier".
  - **Friends:** you and your accepted friends, best score each. Needs a sign-in.
  - **Everyone:** every player with a username, best score each. Readable while signed out too.

  Ties share a place. If you're below the top 50, your own row is added at the end, highlighted.
- **Every finished game counts:** each 90-second Blink Code challenge and each EyeGame run (score
  above 0) goes into the list on this Mac.
- **Uploads:** a game played while signed in is also uploaded to `game_scores`, straight away. If
  OcuSense is offline, or the server refuses, it waits in `scores.json` and goes up the next time
  you're signed in and online. Games played while signed out stay on this Mac, so a score can't be
  claimed for an account afterwards.
- **Account › Friends:**
  - Add a player by their exact username (not case-sensitive).
  - They accept or decline. If you both ask each other, it becomes a friendship straight away.
  - Either of you can remove the friendship, and you can cancel a request you sent.
  - You need a username yourself first.
- **The code:**
  - `ocusense/scores.py`: the list on this Mac and the upload queue.
  - `ocusense/leaderboards.py`: the Supabase calls.
  - `ocusense/ui/leaderboard_view.py`: the Games section and `ScoreKeeper`.
  - `ocusense/ui/friends_panel.py`: the Account section.
  - `tests/test_leaderboards.py`: tests with the network faked.

**On the server** (`supabase/schema.sql`; run it again after updating, which is safe):

| | What it does |
| --- | --- |
| `game_scores` | `game` is `blink_code_challenge` or `eye_runner` (constraint `game_scores_game_check`; add new games there and in `ocusense/scores.py`) |
| `friendships` | one row per pair: `pending`, then `accepted`. Players can read only their own rows and can't write any directly. |
| `request_friend(name)` | ask by username; accepts if they already asked you; at most 50 open requests |
| `respond_friend(other, accept)` | accept or decline a request you received |
| `remove_friend(other)` | unfriend, or withdraw your request |
| `my_friends()` | your friends and open requests |
| `game_leaderboard(game_name, scope, max_rows)` | best score per player for `everyone` or `friends`, ranked, with `is_me` |

The SQL was checked against PostgreSQL 16 with a small stand-in for Supabase's `auth` schema
(`auth.users`, `auth.uid()`, the `anon` and `authenticated` roles). The checks covered:

- upgrading from the previous version of the script, and running it twice
- ranking and ties, and your own row outside the top
- the whole request, accept, decline and remove cycle
- what's refused: posting a score for someone else, changing a score, writing friendships
  directly, reading other people's friendships, and signed-out friend requests

**Limits (fine for a class project):**

- Scores are sent by the app, so a determined person could post a fake one. A Supabase Edge
  Function could check scores (for example, against the game length) before saving them.
- Usernames on the leaderboards are public: anyone can see them.
- The website doesn't show leaderboards yet. It can call `game_leaderboard` the same way.
