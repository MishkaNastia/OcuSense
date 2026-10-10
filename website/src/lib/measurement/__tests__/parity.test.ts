/**
 * Parity with the desktop app: the same inputs must give the same results as
 * the Python implementation. Vectors come from scripts/python_vectors.py.
 */
import { describe, expect, it } from "vitest";

import { BlinkCounter } from "../blinkCounter";
import { buildEyeReference, CalibrationError, GuidedCalibration, robustReference, type Ears } from "../calibration";
import { eyeAspectRatio, measureEyes, type Landmark, type Point } from "../eyeMetrics";
import { combinedOpennessPercent, MeasurementTracker, RollingWindow, type FrameObservation } from "../measurements";
import vectors from "./python-vectors.json";

const close = (actual: number | null, expected: number | null, digits = 7) => {
  if (expected === null) expect(actual).toBeNull();
  else expect(actual).toBeCloseTo(expected, digits);
};

describe("parity with the Python desktop implementation", () => {
  it("EAR", () => {
    for (const c of vectors.ear) close(eyeAspectRatio(c.points as unknown as Point[]), c.ear);
  });

  it("measure_eyes in pixel coordinates, including reliability", () => {
    for (const c of vectors.measure_eyes) {
      const landmarks: Landmark[] = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }));
      for (const [i, [x, y]] of Object.entries(c.landmarks)) landmarks[Number(i)] = { x, y };
      const m = measureEyes(landmarks, c.width, c.height);
      expect(m.reliable).toBe(c.reliable);
      expect(m.reason).toBe(c.reason);
      for (const eye of ["left", "right"] as const) {
        const expected = (c.ears as Record<string, number | undefined>)[eye];
        if (expected !== undefined) close(m.ears[eye] ?? null, expected);
      }
    }
  });

  it("robust references (median and MAD spread)", () => {
    for (const c of vectors.robust_reference) {
      const [m, spread] = robustReference(c.samples);
      close(m, c.median);
      close(spread, c.spread);
    }
  });

  it("eye references accept and reject the same calibrations with the same messages", () => {
    for (const c of vectors.eye_reference) {
      if (c.ok) {
        const ref = buildEyeReference("left", c.open, c.closed);
        close(ref.openEar, c.openEar!);
        close(ref.closedEar, c.closedEar!);
        for (const [ear, raw] of c.raw!) close(ref.rawOpenness(ear), raw);
      } else {
        expect(() => buildEyeReference("left", c.open, c.closed)).toThrow(CalibrationError);
        expect(() => buildEyeReference("left", c.open, c.closed)).toThrow(c.error!);
      }
    }
  });

  it("blink detector makes identical decisions", () => {
    const counter = new BlinkCounter();
    vectors.detector.input.forEach((value, i) => {
      const blinked = counter.update(value);
      expect([blinked, counter.state]).toEqual(vectors.detector.decisions[i]);
    });
    expect(counter.count).toBe(vectors.detector.count);
  });

  it("guided calibration reaches the same outcome", () => {
    for (const c of vectors.calibration) {
      const cal = new GuidedCalibration();
      cal.start(0);
      for (const [now, ears] of c.frames as [number, Ears | null][]) cal.update(now, ears);
      expect(cal.status).toBe(c.result.status);
      expect(cal.error).toBe(c.result.error);
      if (c.result.left) {
        close(cal.result!.left.openEar, c.result.left[0]);
        close(cal.result!.left.closedEar, c.result.left[1]);
        close(cal.result!.right.openEar, c.result.right![0]);
        close(cal.result!.right.closedEar, c.result.right![1]);
      }
    }
  });

  it("rolling measurements: rate, closure, closed time, coverage, gaps", () => {
    const tracker = new MeasurementTracker();
    const window = new RollingWindow(0);
    const snapshots = [...vectors.measurements.snapshots];
    for (const [t, valid, leftRaw, rightRaw, detectorClosed, closingStarted, blinkCompleted] of vectors.measurements.observations) {
      const obs: FrameObservation = {
        t: t as number, valid: valid as boolean, leftRaw: leftRaw as number | null, rightRaw: rightRaw as number | null,
        leftEar: null, rightEar: null, detectorClosed: detectorClosed as boolean,
        closingStarted: closingStarted as boolean, blinkCompleted: blinkCompleted as boolean,
      };
      window.add(tracker.add(obs));
      if (snapshots.length && snapshots[0].after_t === t) {
        const expected = snapshots.shift()!;
        const s = window.snapshot(t as number);
        close(s.validSeconds, expected.valid_seconds, 6);
        close(s.runningSeconds, expected.running_seconds, 6);
        close(s.coverage, expected.coverage, 6);
        expect(s.enoughData).toBe(expected.enough_data);
        expect(s.blinks).toBe(expected.blinks);
        close(s.blinkRate, expected.blink_rate, 6);
        expect(s.closureCount).toBe(expected.closure_count);
        close(s.medianClosure, expected.median_closure, 6);
        close(s.closedSeconds, expected.closed_seconds, 6);
        close(s.closedPercent, expected.closed_percent, 6);
        close(s.processingRate, expected.processing_rate, 6);
      }
    }
    expect(snapshots).toHaveLength(0); // every checkpoint was compared
  });

  it("combined openness display", () => {
    for (const [a, b, expected] of vectors.combined_percent) close(combinedOpennessPercent(a, b), expected);
  });
});
