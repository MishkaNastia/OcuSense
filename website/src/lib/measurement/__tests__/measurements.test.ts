/** Behaviour tests for the browser measurement engine (mirrors tests/test_measurements.py). */
import { describe, expect, it } from "vitest";

import { BlinkCounter } from "../blinkCounter";
import { EyeReference, PersonalCalibration } from "../calibration";
import { LiveSession } from "../monitor";
import {
  combinedOpennessPercent, MeasurementTracker, opennessPercent, RollingWindow, type FrameObservation,
} from "../measurements";

const OPEN = 0.95;
const CLOSED = 0.05;
const FPS = 30;

class Observer {
  detector = new BlinkCounter();
  observe(t: number, openness: number | null): FrameObservation {
    const before = this.detector.state;
    const blinked = this.detector.update(openness);
    const after = this.detector.state;
    if (openness === null) {
      return { t, valid: false, leftRaw: null, rightRaw: null, leftEar: null, rightEar: null, detectorClosed: false, closingStarted: false, blinkCompleted: false };
    }
    return {
      t, valid: true, leftRaw: openness, rightRaw: openness, leftEar: null, rightEar: null,
      detectorClosed: after === "closed", closingStarted: before === "open" && after === "closed", blinkCompleted: blinked,
    };
  }
}

function run(valueAt: (rel: number) => number | null, seconds = 60) {
  const observer = new Observer();
  const tracker = new MeasurementTracker();
  const window = new RollingWindow(0);
  const n = Math.round(seconds * FPS);
  for (let i = 0; i < n; i++) window.add(tracker.add(observer.observe(i / FPS, valueAt(i / FPS))));
  return window;
}

const blinking = (every = 4, closedFor = 0.2) => (rel: number) => {
  const phase = (rel - 1 + 1e-9) % every;
  return rel >= 1 - 1e-9 && phase < closedFor - 1e-9 ? CLOSED : OPEN;
};

describe("personal eye openness", () => {
  it("normalises each eye with its own range and clamps only the display", () => {
    const cal = new PersonalCalibration(new EyeReference(0.3, 0.1), new EyeReference(0.24, 0.08));
    const [l, r] = cal.rawOpenness({ left: 0.2, right: 0.16 });
    expect(l).toBeCloseTo(0.5);
    expect(r).toBeCloseTo(0.5);
    expect(new EyeReference(0.3, 0.1).rawOpenness(0.36)).toBeCloseTo(1.3);
    expect(opennessPercent(1.3)).toBe(100);
    expect(opennessPercent(-0.2)).toBe(0);
  });

  it("shows nothing (not 0 %) when an eye is unavailable", () => {
    expect(combinedOpennessPercent(0.8, null)).toBeNull();
    expect(opennessPercent(null)).toBeNull();
  });

  it("rejects invalid references", () => {
    expect(() => new EyeReference(0.1, 0.3)).toThrow();
    expect(() => new EyeReference(0.2, 0.2)).toThrow();
  });
});

describe("blink detector", () => {
  it("counts open → closed → open once, ignores long closures and starting closed", () => {
    const c = new BlinkCounter();
    for (const v of [CLOSED, CLOSED, OPEN, CLOSED, ...Array(50).fill(CLOSED), OPEN]) c.update(v);
    expect(c.count).toBe(1);
  });

  it("forgets a half-finished blink when tracking is lost", () => {
    const c = new BlinkCounter();
    for (const v of [OPEN, CLOSED, null, OPEN]) c.update(v);
    expect(c.count).toBe(0);
  });
});

describe("rolling measurements", () => {
  it("known sequence: rate, median closure and closed time", () => {
    const s = run(blinking()).snapshot(60 - 1 / FPS);
    expect(s.blinks).toBe(15);
    expect(s.medianClosure).toBeCloseTo(0.2, 6);
    expect(s.closedSeconds).toBeCloseTo(3.0, 6);
    expect(s.blinkRate).toBeCloseTo((15 / (60 - 1 / FPS)) * 60, 6);
    expect(s.processingRate).toBeCloseTo(30, 3);
  });

  it("excludes tracking gaps from the denominators and never counts them as closed", () => {
    const s = run((rel) => (rel >= 20 && rel < 30 ? null : OPEN)).snapshot(60);
    expect(s.validSeconds).toBeCloseTo(50 - 2 / FPS, 3);
    expect(s.runningSeconds).toBeCloseTo(60, 6);
    expect(s.closedSeconds).toBe(0);
  });

  it("discards an incomplete closure interrupted by tracking loss", () => {
    const s = run((rel) => (rel >= 10 && rel < 10.5 ? CLOSED : rel >= 10.5 && rel < 12 ? null : OPEN), 40).snapshot(40);
    expect(s.blinks).toBe(0);
    expect(s.closureCount).toBe(0);
    expect(s.medianClosure).toBeNull();
    expect(s.closedSeconds).toBeCloseTo(0.5 - 1 / FPS, 6);
  });

  it("includes a prolonged closure once, with its full duration", () => {
    const s = run((rel) => (rel >= 10 && rel < 15 ? CLOSED : OPEN), 40).snapshot(40);
    expect(s.blinks).toBe(1);
    expect(s.closedSeconds).toBeCloseTo(5, 6);
    expect(s.medianClosure).toBeCloseTo(5, 6);
  });

  it("counts intervals crossing the window edge partly", () => {
    const s = run((rel) => (rel >= 9 && rel < 11 ? CLOSED : OPEN), 70).snapshot(70);
    expect(s.closedSeconds).toBeCloseTo(1, 6);
    expect(s.blinks).toBe(1);
  });

  it("says 'collecting data' before 30 valid seconds, and has no median without events", () => {
    const early = run(blinking(), 20).snapshot(20);
    expect(early.enoughData).toBe(false);
    expect(early.blinkRate).toBeNull();
    const quiet = run(() => OPEN, 45).snapshot(45);
    expect(quiet.blinkRate).toBe(0);
    expect(quiet.medianClosure).toBeNull();
  });

  it("keeps memory bounded over a long session", () => {
    const w = run(blinking(), 300);
    expect(w.size.intervals).toBeLessThan(61 * FPS);
    expect(w.size.frames).toBeLessThan(6 * FPS + 2);
  });

  it("pauses create a gap without deleting history", () => {
    const session = new LiveSession(0);
    const observer = new Observer();
    for (let i = 0; i < 40 * FPS; i++) {
      const t = i / FPS;
      session.add(observer.observe(t, blinking()(t)), blinking()(t));
    }
    const before = session.snapshot(40);
    session.pause(40);
    observer.detector.update(null);
    session.resume(55);
    for (let i = 0; i < 5 * FPS; i++) session.add(observer.observe(55 + i / FPS, OPEN), OPEN);
    const after = session.snapshot(60);
    expect(after.blinks).toBe(before.blinks);
    expect(after.runningSeconds).toBeCloseTo(45, 6);
  });
});
