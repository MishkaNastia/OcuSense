/**
 * Synthetic sample session — NOT a real person's data.
 *
 * Generates simulated eye-aspect-ratio values (with blinks, noise and the
 * occasional tracking loss) and runs them through the same measurement engine
 * the camera demo uses, so the sample numbers follow the real rules.
 */

import { EyeReference, PersonalCalibration } from "@/lib/measurement/calibration";
import type { EyeMeasurement } from "@/lib/measurement/eyeMetrics";
import { EyeMonitorCore, LiveSession } from "@/lib/measurement/monitor";

export const SAMPLE_FPS = 30;
/** The simulated person's calibration (fixed, so results are reproducible). */
export const SAMPLE_CALIBRATION = new PersonalCalibration(new EyeReference(0.3, 0.1), new EyeReference(0.26, 0.09));

/** Small seeded random generator so the sample looks the same every time. */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type SampleScenario = "steady" | "longer-closures";

/** Simulated eyes: produces one EyeMeasurement (or null = face not found) per frame. */
export class SyntheticEyes {
  private random: () => number;
  private nextBlink: number;
  private blinkEnd = -1;
  private lostUntil = -1;
  scenario: SampleScenario = "steady";

  constructor(seed = 7, private t = 0) {
    this.random = seededRandom(seed);
    this.nextBlink = t + 1.5;
  }

  frame(t: number): EyeMeasurement | null {
    if (t < this.lostUntil) return null;
    if (this.random() < 0.0015) {
      this.lostUntil = t + 0.6 + this.random() * 1.2; // simulated tracking loss (looked away)
      return null;
    }
    if (t >= this.nextBlink && this.blinkEnd < this.nextBlink) {
      const longer = this.scenario === "longer-closures";
      this.blinkEnd = t + (longer ? 0.32 + this.random() * 0.3 : 0.14 + this.random() * 0.1);
    }
    const closed = t < this.blinkEnd;
    if (!closed && t >= this.blinkEnd && this.blinkEnd >= this.nextBlink) {
      this.nextBlink = t + 2.2 + this.random() * 3.2;
    }
    const noise = () => (this.random() - 0.5) * 0.012;
    const left = closed ? 0.095 + noise() : 0.297 + noise();
    const right = closed ? 0.088 + noise() : 0.258 + noise();
    return { ears: { left, right }, reliable: true, reason: "" };
  }
}

/** A complete simulated monitoring session (already calibrated). */
export class SampleSession {
  readonly monitor = new EyeMonitorCore();
  readonly eyes: SyntheticEyes;
  session: LiveSession;
  t: number;
  latestOpenness: [number, number] | null = null;

  constructor(seed = 7, start = 0) {
    this.monitor.calibration = SAMPLE_CALIBRATION;
    this.eyes = new SyntheticEyes(seed, start);
    this.t = start;
    this.session = new LiveSession(start);
  }

  /** Advance simulated time by `seconds`, processing every frame in between. */
  advance(seconds: number): void {
    const frames = Math.round(seconds * SAMPLE_FPS);
    for (let i = 0; i < frames; i++) {
      this.t += 1 / SAMPLE_FPS;
      const result = this.monitor.process(this.eyes.frame(this.t), this.t);
      this.session.add(result.observation, result.openness ? result.openness[2] : null);
      const o = result.observation;
      this.latestOpenness = o.valid ? [o.leftRaw!, o.rightRaw!] : null;
    }
  }

  setScenario(scenario: SampleScenario): void {
    this.eyes.scenario = scenario;
  }

  pause(): void {
    this.session.pause(this.t);
    this.monitor.interrupt();
  }

  resume(): void {
    this.session.resume(this.t);
  }
}
