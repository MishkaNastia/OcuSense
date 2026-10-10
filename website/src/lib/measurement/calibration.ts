/**
 * Personal calibration — port of ocusense/core/calibration.py.
 *
 * Each eye gets its own references: the median EAR while comfortably open
 * and while gently closed. A calibration is rejected if the references are
 * too similar, unstable, based on too few frames, or if natural blinks can't
 * be detected with them.
 */

import { BlinkCounter } from "./blinkCounter";
import { MAX_SPREAD_FRACTION, MIN_CALIBRATION_BLINKS, MIN_RELATIVE_SEPARATION, MIN_SAMPLES } from "./config";
import type { EyeName } from "./eyeMetrics";
import { median } from "./stats";

export type Ears = Record<EyeName, number>;

export class CalibrationError extends Error {}

/** Median and robust spread (1.4826 × median absolute deviation). */
export function robustReference(samples: readonly number[]): [number, number] {
  const m = median(samples);
  const mad = median(samples.map((s) => Math.abs(s - m)));
  return [m, 1.4826 * mad];
}

/** One eye's validated references. */
export class EyeReference {
  constructor(readonly openEar: number, readonly closedEar: number) {
    if (!(openEar > closedEar && closedEar >= 0)) {
      throw new Error(`invalid eye reference: open ${openEar}, closed ${closedEar}`);
    }
  }

  /** Unclamped: 0 = calibrated closed, 1 = calibrated open (can be outside 0..1). */
  rawOpenness(ear: number): number {
    return (ear - this.closedEar) / (this.openEar - this.closedEar);
  }

  /** Clipped to 0..1 — the value the blink detector uses. */
  openness(ear: number): number {
    return Math.min(1, Math.max(0, this.rawOpenness(ear)));
  }
}

export function buildEyeReference(eyeName: string, openSamples: readonly number[], closedSamples: readonly number[]): EyeReference {
  if (openSamples.length < MIN_SAMPLES || closedSamples.length < MIN_SAMPLES) {
    throw new CalibrationError(`Not enough clear frames of your ${eyeName} eye. Face the camera in good light and keep still.`);
  }
  const [openEar, openSpread] = robustReference(openSamples);
  const [closedEar, closedSpread] = robustReference(closedSamples);
  const gap = openEar - closedEar;
  if (openEar <= 0 || gap < MIN_RELATIVE_SEPARATION * openEar) {
    throw new CalibrationError(
      `Open and closed ${eyeName} eye looked too similar. Keep eyes comfortably open, then fully (but gently) closed.`,
    );
  }
  if (Math.max(openSpread, closedSpread) > MAX_SPREAD_FRACTION * gap) {
    const capital = eyeName[0].toUpperCase() + eyeName.slice(1);
    throw new CalibrationError(`${capital} eye measurements were unstable. Keep your head still and avoid blinking during the open step.`);
  }
  return new EyeReference(openEar, closedEar);
}

/** Both eyes by averaging; a one-eyed wink stays near 0.5 and is not a blink. */
export function combine(left: number, right: number): number {
  return (left + right) / 2;
}

export class PersonalCalibration {
  constructor(readonly left: EyeReference, readonly right: EyeReference) {}

  /** (left, right, combined) clipped personal openness. */
  openness(ears: Ears): [number, number, number] {
    const l = this.left.openness(ears.left);
    const r = this.right.openness(ears.right);
    return [l, r, combine(l, r)];
  }

  rawOpenness(ears: Ears): [number, number] {
    return [this.left.rawOpenness(ears.left), this.right.rawOpenness(ears.right)];
  }
}

export function countBlinks(values: readonly (number | null)[]): number {
  const counter = new BlinkCounter();
  for (const v of values) counter.update(v);
  return counter.count;
}

export interface CalibrationStep {
  name: "open" | "closed" | "blinks";
  instruction: string;
  getReadySeconds: number;
  measureSeconds: number;
  useFrom: number;
  useUntil: number;
}

export const STEPS: readonly CalibrationStep[] = [
  { name: "open", instruction: "Keep your eyes comfortably open and look at the screen", getReadySeconds: 3, measureSeconds: 3, useFrom: 0.5, useUntil: 3 },
  { name: "closed", instruction: "When the countdown ends, gently close your eyes and slowly count to 5", getReadySeconds: 4, measureSeconds: 4.5, useFrom: 1, useUntil: 3.5 },
  { name: "blinks", instruction: "Blink naturally about 5 times", getReadySeconds: 3, measureSeconds: 6, useFrom: 0, useUntil: 6 },
];

export type CalibrationStatus = "idle" | "running" | "done" | "failed";

/** Walks through the calibration steps using the clock (seconds). */
export class GuidedCalibration {
  status: CalibrationStatus = "idle";
  result: PersonalCalibration | null = null;
  error = "";
  private samples = { open: { left: [] as number[], right: [] as number[] }, closed: { left: [] as number[], right: [] as number[] } };
  private blinkOpenness: (number | null)[] = [];
  private candidate: PersonalCalibration | null = null;
  private stepIndex = 0;
  private stepStart = 0;

  start(now: number): void {
    this.status = "running";
    this.result = null;
    this.error = "";
    this.samples = { open: { left: [], right: [] }, closed: { left: [], right: [] } };
    this.blinkOpenness = [];
    this.candidate = null;
    this.stepIndex = 0;
    this.stepStart = now;
  }

  get step(): CalibrationStep | null {
    return this.status === "running" ? STEPS[this.stepIndex] : null;
  }

  get stepNumber(): number | null {
    return this.status === "running" ? this.stepIndex : null;
  }

  measuring(now: number): boolean {
    const step = this.step;
    return step !== null && now - this.stepStart >= step.getReadySeconds;
  }

  secondsLeft(now: number): number {
    const step = this.step;
    if (!step) return 0;
    const elapsed = now - this.stepStart;
    if (elapsed < step.getReadySeconds) return step.getReadySeconds - elapsed;
    return step.getReadySeconds + step.measureSeconds - elapsed;
  }

  update(now: number, ears: Ears | null): void {
    const step = this.step;
    if (!step) return;
    const t = now - this.stepStart - step.getReadySeconds;
    if (t >= 0 && t < step.measureSeconds && t >= step.useFrom && t <= step.useUntil) {
      if (step.name === "blinks") {
        this.blinkOpenness.push(ears === null ? null : this.candidate!.openness(ears)[2]);
      } else if (ears !== null) {
        this.samples[step.name].left.push(ears.left);
        this.samples[step.name].right.push(ears.right);
      }
    }
    if (t >= step.measureSeconds) this.finishStep(step, now);
  }

  private finishStep(step: CalibrationStep, now: number): void {
    try {
      if (step.name === "closed") {
        this.candidate = new PersonalCalibration(
          buildEyeReference("left", this.samples.open.left, this.samples.closed.left),
          buildEyeReference("right", this.samples.open.right, this.samples.closed.right),
        );
      } else if (step.name === "blinks") {
        const found = countBlinks(this.blinkOpenness);
        if (found < MIN_CALIBRATION_BLINKS) {
          throw new CalibrationError(
            `Only ${found} blink(s) detected (need ${MIN_CALIBRATION_BLINKS}). During the closed step, close your eyes gently - don't squeeze.`,
          );
        }
        this.result = this.candidate;
        this.status = "done";
        return;
      }
    } catch (problem) {
      if (!(problem instanceof CalibrationError)) throw problem;
      this.error = problem.message;
      this.status = "failed";
      return;
    }
    this.stepIndex += 1;
    this.stepStart = now;
  }
}
