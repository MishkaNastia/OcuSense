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
          <h1>Understandable measurements, calibrated to you.</h1>
          <p className="lead">
            OcuSense turns six points around each eye into a few clearly defined numbers. Here is exactly what they
            mean — and what they don’t.
          </p>
        </div>
        <StepMark step="calibrate" size={220} />
      </header>

      <section className="section-rule prose" aria-labelledby="pipeline">
        <h2 id="pipeline">From camera picture to numbers</h2>
        <ol>
          <li><b>Find the face.</b> Google’s MediaPipe Face Landmarker places 478 points on the face, on your device.</li>
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
            the two eyes are averaged only when both are measured. Relative to your calibration — not a fatigue score
            and not a literal anatomical percentage.
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
            left out of every calculation — never counted as zero or as “closed”.
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
          precise as the frame rate (about ±33 ms at 30 frames per second). These limits are engineering choices
          for a prototype, not clinical standards.
        </p>
      </section>

      <section className="section-rule two-col" aria-labelledby="calibration">
        <div className="prose">
          <h2 id="calibration">Calibration is not learning</h2>
          <p>
            <b>Calibration</b> takes about 30 seconds: eyes comfortably open, gently closed, then a few natural blinks.
            It produces two reference values per eye and is rejected if they are too similar, unstable, or if blinks
            can’t be detected. It is measurement setup — nothing is “learned” about you.
          </p>
        </div>
        <div className="prose">
          <h2>Personal patterns are experimental</h2>
          <p>
            <b>Patterns</b> come from comparing your measurements over time with your own check-ins (“how sleepy?”,
            “how comfortable are your eyes?”). OcuSense reports what you said and what was measured. It does not decide
            that you are tired, and it doesn’t claim a break <i>caused</i> a change. Pattern prompts are labelled experimental.
          </p>
        </div>
      </section>

      <section className="section-rule prose" aria-labelledby="where">
        <h2 id="where">Where it runs</h2>
        <p>
          In the <Link href="/download">Mac app</Link>, everything runs on your Mac. In the <Link href="/demo/camera">camera demo</Link>,
          the same rules run in your browser: the TypeScript code is a port of the app’s Python code and is tested against
          its results. Read more on the <Link href="/privacy">privacy page</Link>.
        </p>
      </section>
    </div>
  );
}
