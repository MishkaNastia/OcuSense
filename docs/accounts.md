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

## Setting it up (once per Supabase project)

1. **Use the same Supabase project as the website.** Its URL and publishable key are
   in Supabase › Project Settings › API, and in `website/.env.local` if the website
   is already set up.
2. **Run the database script:** Supabase › SQL Editor › paste
   `supabase/schema.sql` › Run. It creates:
   - `profiles`: public usernames, filled in automatically from sign-ups.
   - `username_available()`: lets the form say "taken" before sign-up.
   - `game_scores`: players can add their own scores but never edit them.
   - the `leaderboard` view: each player's best score per game.

   Running it again is safe.
3. **Tell the app where the project is.** Use one of these:
   - **Just your Mac:** create `~/Library/Application Support/OcuSense/supabase.json`.
   - **Bundled into the app for everyone:** put the same file at
     `ocusense/supabase.json` and rebuild (`./packaging/build_mac.sh`). It is
     git-ignored, like the website's `.env.local`.
   - **While developing:** set `OCUSENSE_SUPABASE_URL` and `OCUSENSE_SUPABASE_KEY`.

   The file looks like this:

   ```json
   { "url": "https://YOUR-PROJECT.supabase.co", "publishable_key": "sb_publishable_…" }
   ```
4. **Set the redirect URLs.** In Supabase › Authentication › URL Configuration,
   make sure the website's address is the Site URL, so confirmation and
   password-reset links open the website.

Without step 3, the Account page says "Accounts aren't set up in this copy of
OcuSense", and everything else works as before.

## Next: the leaderboards

The tables are ready. What's left is in the app:

- **Submit a score** after a Blink Code challenge, when signed in:
  `POST /rest/v1/game_scores` with `{"game": "blink_code_challenge", "score": 420,
  "details": {"words": 5, "best_combo": 9}}`. Send the `apikey` header and
  `Authorization: Bearer <access token>`, as `AccountService._access_token()`
  gives it.
- **Read the top 50:**
  `GET /rest/v1/leaderboard?game=eq.blink_code_challenge&order=score.desc&limit=50`.
- **Show it:** a Leaderboard view in the Games page, plus your rank on the
  Account page.

Scores are submitted by the app, so a determined person could send a fake score.
For a class project that's fine. Later, a Supabase Edge Function could check
scores (for example, against the game length) before saving them.
