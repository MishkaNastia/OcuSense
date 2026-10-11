import type { Metadata } from "next";
import Link from "next/link";

import { StepMark } from "@/components/art/Art";
import { CLOSE_BELOW, MAX_FRAME_GAP, MIN_VALID_SECONDS_FOR_RATE, REOPEN_ABOVE, ROLLING_WINDOW_SECONDS } from "@/lib/measurement/config";

export const metadata: Metadata = { title: "How it works" };

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function HowItWorksPage() {
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">How it works</p>
          <h1>How OcuSense knows you blinked</h1>
          <p className="lead">
            Six points around each eye become a handful of clearly defined numbers. Here’s what each one means, and
            what it can’t tell you.
          </p>
        </div>
        <StepMark step="calibrate" size={220} />
      </header>

      <section className="section-rule prose" aria-labelledby="pipeline">
        <h2 id="pipeline">From camera picture to numbers</h2>
        <ol>
          <li><b>Find the face.</b> A face tracking model places 478 points on the face, right on your device.</li>
          <li><b>Measure each eye.</b> Six eyelid points give the Eye Aspect Ratio (EAR): eye height divided by eye width, measured in pixels.</li>
          <li><b>Check the picture is usable.</b> Measurement pauses if the face is missing, too small, or turned too far.</li>
          <li><b>Make it personal.</b> Each eye’s EAR is compared with your own calibrated open and closed values.</li>
          <li><b>Count and time blinks.</b> A simple, fixed rule decides when both eyes have closed and opened again.</li>
        </ol>
      </section>

      <section className="section-rule" aria-labelledby="definitions">
        <h2 id="definitions">Exact definitions</h2>
        <dl className="def">
          <dt>Personal eye openness</dt>
          <dd>
            For each eye: 100 × (EAR − closed reference) ÷ (open reference − closed reference). Shown from 0 to 100 %;
            the two eyes are averaged only when both are measured. It’s relative to your calibration, so it isn’t a
            tiredness score or a ruler for your eyelids.
          </dd>
          <dt>Blink (both eyes)</dt>
          <dd>
            Both-eyes openness falls below {pct(CLOSE_BELOW)}, then rises above {pct(REOPEN_ABOVE)}. That counts once,
            however long the eyes stayed closed. A one-eyed wink keeps the average near 50 % and isn’t counted. Losing
            tracking or pausing forgets a half-finished blink.
          </dd>
          <dt>Valid observation</dt>
          <dd>
            Time between two usable frames at most {MAX_FRAME_GAP} s apart. Lost tracking, longer gaps and pauses are
            left out of every calculation. They never count as zero or as “closed”.
          </dd>
          <dt>Blink rate</dt>
          <dd>Completed blinks ÷ valid seconds × 60, over the last {ROLLING_WINDOW_SECONDS} seconds.</dd>
          <dt>Median closure duration</dt>
          <dd>The median time from closing to reopening for completed blinks. It is the threshold-defined closed interval, not the whole blink movement.</dd>
          <dt>Time classified as closed</dt>
          <dd>Valid time spent in the closed state ÷ valid time × 100, including long closures. Not PERCLOS: calibrated thresholds don’t measure anatomical closure.</dd>
        </dl>
        <p className="muted">
          Blink rate and closed time are shown after {MIN_VALID_SECONDS_FOR_RATE} seconds of valid observation;
          before that you see “Collecting data”. Durations are timed between camera frames, so they are only as
          precise as the frame rate (about ±33 ms at 30 frames per second). These limits are our own choices for a
          student project, not clinical standards.
        </p>
      </section>

      <section className="section-rule two-col" aria-labelledby="calibration">
        <div className="prose">
          <h2 id="calibration">Calibrate once</h2>
          <p>
            <b>Calibration</b> takes under half a minute: eyes comfortably open, gently closed, then a few natural
            blinks. It produces two reference values per eye and is rejected if they are too similar, unstable, or if
            blinks can’t be detected. The app saves it, so next time you press Start and go. New glasses or a new lamp?
            Recalibrate.
          </p>
        </div>
        <div className="prose">
          <h2>Reminders that know your normal</h2>
          <p>
            The first 10 minutes of one session become your <b>reference</b> for how often you blink. Later, if the
            gaps between your blinks stay longer than in your reference for several minutes in a row, the app suggests a
            break. It compares you with you, never with other people, and it doesn’t decide that you are tired.
          </p>
        </div>
      </section>

      <section className="section-rule" aria-labelledby="app">
        <h2 id="app">What else is in the app</h2>
        <dl className="def">
          <dt>Reminders</dt>
          <dd>
            Too close to the screen (“Trying to lick the screen?”), blinking slower than your reference, an optional
            eye rest every 20 minutes, an optional lighting check for dark rooms, and optional posture monitoring that
            speaks up after 15 seconds of slumping or leaning in. They show in the window and as notifications when
            OcuSense is in the background.
          </dd>
          <dt>Pomodoro and Time log</dt>
          <dd>
            Focus rounds and breaks that start and pause eye monitoring for you, with a notification when each one ends.
            The Time log keeps track of which subject you worked on and for how long.
          </dd>
          <dt>Games</dt>
          <dd>
            Blink Code (Morse code with your blinks), EyeGame (an endless runner you play by blinking) and OcuSense
            Garden (water crops with a gentle eye exercise, harvest them for coins). Game blinks never count in your
            study statistics.
          </dd>
          <dt>Gallery and leaderboards</dt>
          <dd>
            Spend garden coins on paintings by famous artists and hang two in the sidebar. With an account you can put
            your game scores on leaderboards and compare them with friends.
          </dd>
          <dt>Themes</dt>
          <dd>Miró (warm paper, calm colours) or Keith Haring (bold colours, thick lines, dancing figures). Switch any time.</dd>
        </dl>
      </section>

      <section className="section-rule prose" aria-labelledby="where">
        <h2 id="where">Where it runs</h2>
        <p>
          In the <Link href="/download">desktop app</Link>, everything runs on your computer. In the <Link href="/demo/camera">camera demo</Link>,
          the same rules run in your browser: the TypeScript code is a port of the app’s Python code and is tested against
          its results. Read more on the <Link href="/privacy">privacy page</Link>.
        </p>
      </section>
    </div>
  );
}
