import type { Metadata } from "next";
import Link from "next/link";

import { HeroArt, StepMark } from "@/components/art/Art";

import styles from "./choose.module.css";

export const metadata: Metadata = { title: "Demo" };

export default function DemoPage() {
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Interactive demo · no account needed</p>
          <h1>Try OcuSense in your browser.</h1>
          <p className="lead">Two ways in. The sample session never asks for your camera.</p>
        </div>
        <HeroArt />
      </header>
      <div className={styles.options}>
        <section aria-labelledby="opt-a" className={styles.option}>
          <StepMark step="notice" size={88} />
          <p className="eyebrow">Option A</p>
          <h2 id="opt-a">Explore a sample session</h2>
          <ul>
            <li>Works without camera permission.</li>
            <li>Clearly labelled synthetic data, measured with the real rules.</li>
            <li>Make the app’s reminders pop up whenever you like, and watch the numbers change.</li>
          </ul>
          <Link href="/demo/sample" className="btn btn-primary">Explore the sample</Link>
        </section>
        <section aria-labelledby="opt-b" className={styles.option}>
          <StepMark step="calibrate" size={88} />
          <p className="eyebrow">Option B</p>
          <h2 id="opt-b">Try with my camera</h2>
          <ul>
            <li>The camera starts only when you press Start.</li>
            <li>Frames are processed in this browser tab and never uploaded or recorded.</li>
            <li>A quick calibration, then live eye openness, blinks and measurements.</li>
          </ul>
          <Link href="/demo/camera" className="btn btn-secondary">Use my camera</Link>
        </section>
      </div>
      <p className="muted">
        Short on time? The sample session has a “Skip ahead 1 minute” button, so you can see every measurement
        straight away. The games, garden and gallery live in the desktop app. OcuSense is not a medical device.
      </p>
    </div>
  );
}
