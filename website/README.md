# OcuSense website

The public website for OcuSense: what it is, how it works, two browser demos, the
download status of the Mac app, and optional accounts. It lives in its own folder and
does not change the desktop app (`../ocusense`).

Built with Next.js 16, React 19 and TypeScript. The camera demo uses MediaPipe Face
Landmarker in the browser, with the measurement rules of the Python app ported to
TypeScript and tested against it.

## Start and stop it locally

You need Node.js 20 or newer (`node -v`).

```bash
cd ~/Projects/OcuSense/website
npm install          # first time only (or after pulling new dependencies)
npm run dev          # development mode, reloads when you edit files
```

Open **http://localhost:3000**. Stop it with **Ctrl+C** in the same terminal.

For the jury, use the faster production build:

```bash
npm run build
npm run start        # then open http://localhost:3000, stop with Ctrl+C
```

`npm run dev` and `npm run build` first copy the MediaPipe program files and the face
model into `public/` (from `node_modules` and `../models/face_landmarker.task`). These
copies are ignored by Git.

## Demonstrating it to the jury (about 5 minutes)

Use Chrome, Edge or Safari on a laptop with a camera, in good front lighting.

1. **Home** (`/`): read the hero line, scroll through the sample preview, the five steps,
   and the gentle prompts.
2. **Demo → Sample session** (`/demo/sample`): press *Play simulation*, then *Skip ahead
   1 minute* so blink rate, closure time and closed time appear. Trigger *Scheduled
   break* → *Take a break* → choose Walking, rate before, *Start break*, *Finish break*,
   rate after, *Save feedback*. Show the factual before/after comparison and the
   history. Press *Reset demo* at the end.
3. **Demo → Camera** (`/demo/camera`): press *Start camera*, allow access, follow the 3
   calibration steps (open → gently closed → natural blinks). Then show the live
   openness graph and measurements; blink rate shows "Collecting data" for the first
   30 seconds. Switch tabs and come back to show that it pauses and turns the camera off.
   Press *Stop camera*.
4. **How it works**, **Privacy** and **Download** for the honest status of each part.

Backup plan: if the camera or lighting is a problem, use the sample session — it needs
no camera and shows every feature.

## What is live, simulated or waiting for configuration

| Feature | Status |
| --- | --- |
| All information pages | Live |
| Sample session and the app's reminders | Simulated (made up data, kept in memory only, gone on reload) |
| Camera demo (calibration, openness, blinks, rolling measurements) | Live in the browser. Checked with Chromium's fake camera only, **not yet with a real face/webcam** |
| Leaderboard (`/leaderboard`) | Live once Supabase is connected: top 20 per game, refreshed every minute |
| Account email links (`/update-password`, `/email-confirmed`) | Live once Supabase is connected. There's no login on the website: accounts are made and used in the app |
| Mac download | "Coming soon" until you add a public download link |
| Windows | Being prepared, not tested on a Windows PC yet |
| Linux | Planned |

No analytics or advertising trackers are used. The face model and program files are
served by this website itself; camera images never leave the browser.

## Connecting accounts (Supabase, optional)

The website has no login of its own. It needs the Supabase project for two things: the
public leaderboard, and the pages that password reset and confirmation emails open. The
easiest way is `packaging/connect_supabase.py` from the repository root (see
`docs/accounts.md`), which also creates `.env.local`. By hand:

1. Create a free project at https://supabase.com.
2. In the dashboard open **Project Settings → API** and copy the *Project URL* and the
   *publishable* key (or the legacy *anon* key). **Never use the secret / service_role key.**
3. Copy the example file and fill in the two values:
   ```bash
   cp .env.example .env.local
   ```
4. In **Authentication → URL Configuration** set *Site URL* to `http://localhost:3000`
   and add `http://localhost:3000/auth/callback` to *Redirect URLs* (later also your
   public address, e.g. `https://your-site.example/auth/callback`, and set
   `NEXT_PUBLIC_SITE_URL` to it).
5. Restart (`Ctrl+C`, then `npm run dev`, or `npm run build && npm run start`).
6. Test: in the app, use *Log in › Forgot password?* and open the email's link; it should
   land on *Choose a new password*. Open `/leaderboard` after playing a game while logged in.
   Supabase's built-in email sender is rate-limited; for real use add your own SMTP
   provider in the Supabase dashboard.

`.env.local` is ignored by Git — never commit it.

## Connecting the real Mac download

Edit **`src/content/release.ts`** only:

1. Build the app (`./packaging/build_mac.sh` in the project root) and zip or package it.
2. Upload it somewhere **public over https**, for example as an asset of a GitHub
   Release. Never link to a file on your own computer.
3. In the `macOS` entry set `status: "available"`, `version`, `url`, `fileName`,
   `sizeLabel` and, optionally, `sha256` (`shasum -a 256 OcuSense.zip`).
4. Keep the `verified` list truthful (signing, notarisation, which Macs you tested).

## Tests

```bash
npm run lint        # ESLint
npm run typecheck   # TypeScript
npm test            # Vitest: measurement parity with Python, demos, auth validation
npm run build       # production build
npm run vectors     # regenerate the Python→TS parity vectors (needs ../.venv)
```

Still to check by hand: the camera demo with a real face on Chrome, Safari and Firefox;
calibration in dim light and with glasses; the full Supabase email flow once
configured; a screen reader pass (VoiceOver) on the demos.

## Where to edit things

| What | File |
| --- | --- |
| Site name, tagline, navigation, GitHub link, contact email | `src/content/site.ts` |
| Team text and members (About us) | `src/content/team.ts` |
| Download status and links | `src/content/release.ts` |
| Colours, fonts sizes, spacing | `src/app/globals.css` (the `:root` tokens at the top) |
| Home page text | `src/app/page.tsx` |
| Prompt wording | `src/components/alerts/Alerts.tsx` |
| Break activities and sample history | `src/lib/demo/sampleHistory.ts` |

Measurement constants (thresholds, window lengths) live in
`src/lib/measurement/config.ts` and must stay in sync with `ocusense/` in the app.

## Credits

MediaPipe Tasks Vision and the Face Landmarker model (Apache 2.0, Google); fonts
Bricolage Grotesque (OFL) and Atkinson Hyperlegible Next/Mono (OFL); Next.js (MIT);
Supabase client libraries (MIT). See `/credits` on the site.

OcuSense is not a medical device. It does not diagnose tiredness, dry eye or any other
condition, and its suggestions are not clinically validated.
