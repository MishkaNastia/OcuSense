/**
 * Measurement foundation — port of ocusense/core/measurements.py.
 *
 * Definitions (times in seconds from a monotonic clock, e.g. performance.now()/1000):
 * - Valid observation interval: time between two consecutive VALID frames at most
 *   MAX_FRAME_GAP apart. Invalid frames, longer gaps and pauses are missing time.
 * - Detector closed time: a valid interval counts as closed when the blink detector
 *   was in its bilateral CLOSED state at the interval's start frame.
 * - Closure event: from the detector's OPEN → CLOSED frame to its CLOSED → OPEN
 *   frame (the frame that counts the blink). Discarded if tracking was lost, a
 *   frame gap occurred, or monitoring paused while it was in progress.
 */

import {
  MAX_FRAME_GAP, MIN_VALID_SECONDS_FOR_RATE, PROCESSING_RATE_WINDOW, ROLLING_WINDOW_SECONDS,
} from "./config";
import { median } from "./stats";

/** One processed frame, already calibrated (input to the measurements). */
export interface FrameObservation {
  t: number;
  valid: boolean;
  leftRaw: number | null; // unclamped personal openness fractions
  rightRaw: number | null;
  leftEar: number | null;
  rightEar: number | null;
  detectorClosed: boolean;
  closingStarted: boolean;
  blinkCompleted: boolean;
}

export function invalidObservation(t: number, leftEar: number | null = null, rightEar: number | null = null): FrameObservation {
  return { t, valid: false, leftRaw: null, rightRaw: null, leftEar, rightEar, detectorClosed: false, closingStarted: false, blinkCompleted: false };
}

/** The "last 60 seconds" numbers. null = not available (show "—" or "Collecting data"). */
export interface RollingSnapshot {
  windowSeconds: number;
  runningSeconds: number;
  validSeconds: number;
  coverage: number | null;
  enoughData: boolean;
  blinks: number;
  blinkRate: number | null; // blinks per minute of valid observation
  closureCount: number;
  medianClosure: number | null; // seconds
  closedSeconds: number;
  closedPercent: number | null;
  processingRate: number | null; // frames per second
}

// ------------------------------------------------------------ display values
/** Displayed personal eye openness for one eye: 0–100 %, or null when unavailable. */
export function opennessPercent(raw: number | null): number | null {
  if (raw === null || Number.isNaN(raw)) return null;
  return Math.min(100, Math.max(0, raw * 100));
}

/** Mean of the two separately normalised, clamped eyes; null unless both are valid. */
export function combinedOpennessPercent(leftRaw: number | null, rightRaw: number | null): number | null {
  const l = opennessPercent(leftRaw);
  const r = opennessPercent(rightRaw);
  return l === null || r === null ? null : (l + r) / 2;
}

// ------------------------------------------------------------- tracker
export interface Step {
  t: number;
  interval: [number, number, boolean] | null; // start, end, closed
  closure: number | null;
  blink: boolean;
}

export class MeasurementTracker {
  private last: FrameObservation | null = null;
  private closureStart: number | null = null;

  interrupt(): void {
    this.last = null;
    this.closureStart = null;
  }

  add(obs: FrameObservation): Step {
    if (!obs.valid) {
      this.interrupt();
      return { t: obs.t, interval: null, closure: null, blink: false };
    }
    let interval: Step["interval"] = null;
    if (this.last !== null) {
      const dt = obs.t - this.last.t;
      if (dt > 0 && dt <= MAX_FRAME_GAP) interval = [this.last.t, obs.t, this.last.detectorClosed];
      else this.closureStart = null; // can't time an event across an unobserved gap
    }
    if (obs.closingStarted) this.closureStart = obs.t;
    let closure: number | null = null;
    if (obs.blinkCompleted) {
      if (this.closureStart !== null) closure = obs.t - this.closureStart;
      this.closureStart = null;
    }
    this.last = obs;
    return { t: obs.t, interval, closure, blink: obs.blinkCompleted };
  }
}

// ------------------------------------------------------------- rolling window
function overlap(start: number, end: number, low: number, high: number): number {
  return Math.max(0, Math.min(end, high) - Math.max(start, low));
}

/** The last ROLLING_WINDOW_SECONDS of measurements, with bounded memory. */
export class RollingWindow {
  private intervals: [number, number, boolean][] = [];
  private blinks: number[] = [];
  private closures: [number, number][] = [];
  private frames: number[] = [];
  private running: [number, number | null][];

  constructor(now: number, readonly seconds = ROLLING_WINDOW_SECONDS, readonly minValidSeconds = MIN_VALID_SECONDS_FOR_RATE) {
    this.running = [[now, null]];
  }

  add(step: Step): void {
    this.frames.push(step.t);
    if (step.interval) this.intervals.push(step.interval);
    if (step.blink) this.blinks.push(step.t);
    if (step.closure !== null) this.closures.push([step.t, step.closure]);
    this.prune(step.t);
  }

  pause(t: number): void {
    const last = this.running[this.running.length - 1];
    if (last && last[1] === null) last[1] = t;
  }

  resume(t: number): void {
    const last = this.running[this.running.length - 1];
    if (!last || last[1] !== null) this.running.push([t, null]);
  }

  /** Number of stored items — used by tests to check memory stays bounded. */
  get size(): { intervals: number; frames: number } {
    return { intervals: this.intervals.length, frames: this.frames.length };
  }

  private prune(now: number): void {
    const low = now - this.seconds;
    // Arrays are time-ordered; drop from the front (amortised by slicing in batches).
    const drop = <T,>(list: T[], old: (item: T) => boolean): T[] => {
      let i = 0;
      while (i < list.length && old(list[i])) i++;
      return i ? list.slice(i) : list;
    };
    this.intervals = drop(this.intervals, (it) => it[1] <= low);
    this.blinks = drop(this.blinks, (t) => t < low);
    this.closures = drop(this.closures, (c) => c[0] < low);
    this.frames = drop(this.frames, (t) => t < now - Math.max(PROCESSING_RATE_WINDOW, 1));
    while (this.running.length > 1 && this.running[0][1] !== null && this.running[0][1] <= low) this.running.shift();
  }

  snapshot(now: number): RollingSnapshot {
    const low = now - this.seconds;
    let valid = 0;
    let closed = 0;
    for (const [start, end, isClosed] of this.intervals) {
      const part = overlap(start, end, low, now); // intervals crossing the edge count partly
      valid += part;
      if (isClosed) closed += part;
    }
    const running = this.running.reduce((sum, [s, e]) => sum + overlap(s, e ?? now, low, now), 0);
    const blinks = this.blinks.filter((t) => t >= low && t <= now).length;
    const durations = this.closures.filter(([t]) => t >= low && t <= now).map(([, d]) => d);
    const enough = valid >= this.minValidSeconds;
    const recent = this.frames.filter((t) => t > now - PROCESSING_RATE_WINDOW);
    let rate: number | null = null;
    if (recent.length >= 2 && recent[recent.length - 1] > recent[0]) rate = (recent.length - 1) / (recent[recent.length - 1] - recent[0]);
    return {
      windowSeconds: this.seconds,
      runningSeconds: running,
      validSeconds: valid,
      coverage: running > 0 ? valid / running : null,
      enoughData: enough,
      blinks,
      blinkRate: enough ? (blinks / valid) * 60 : null,
      closureCount: durations.length,
      medianClosure: durations.length ? median(durations) : null,
      closedSeconds: closed,
      closedPercent: enough ? (closed / valid) * 100 : null,
      processingRate: rate,
    };
  }
}
