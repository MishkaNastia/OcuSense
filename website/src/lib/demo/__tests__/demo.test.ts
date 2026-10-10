import { describe, expect, it } from "vitest";

import { EyeMonitorCore, LiveSession } from "@/lib/measurement/monitor";

import { SAMPLE_BREAKS, STILL_LEARNING_BELOW, summarise } from "../sampleHistory";
import { SampleSession, SyntheticEyes } from "../sampleSession";

describe("synthetic sample session", () => {
  it("is deterministic and produces plausible measurements through the real engine", () => {
    const a = new SampleSession(7);
    const b = new SampleSession(7);
    a.advance(90);
    b.advance(90);
    const sa = a.session.snapshot(a.t);
    expect(sa).toEqual(b.session.snapshot(b.t));
    expect(sa.enoughData).toBe(true);
    expect(sa.blinkRate!).toBeGreaterThan(8);
    expect(sa.blinkRate!).toBeLessThan(30);
    expect(sa.medianClosure!).toBeGreaterThan(0.1);
    expect(sa.medianClosure!).toBeLessThan(0.3);
    expect(sa.coverage!).toBeGreaterThan(0.8); // occasional simulated tracking loss is excluded
  });

  it("the 'longer closures' scenario raises the median closure duration", () => {
    const s = new SampleSession(7);
    s.advance(70);
    const before = s.session.snapshot(s.t).medianClosure!;
    s.setScenario("longer-closures");
    s.advance(70);
    expect(s.session.snapshot(s.t).medianClosure!).toBeGreaterThan(before + 0.1);
  });
});

describe("full browser pipeline (calibration → monitoring)", () => {
  it("calibrates on synthetic eyes, then counts blinks; pausing forgets a half-finished blink", () => {
    const monitor = new EyeMonitorCore();
    const eyes = new SyntheticEyes(3);
    // Calibration needs eyes open, gently closed, then natural blinks: script those phases.
    monitor.startCalibration(0);
    let t = 0;
    while (monitor.calibrator.status === "running" && t < 60) {
      t += 1 / 30;
      const step = monitor.calibrator.step!;
      const closed = step.name === "closed" && monitor.calibrator.measuring(t);
      const blinking = step.name === "blinks" && monitor.calibrator.measuring(t) && t % 1 < 0.15; // a blink every second, as instructed
      const shut = closed || blinking;
      const m = { ears: shut ? { left: 0.1, right: 0.09 } : { left: 0.3, right: 0.26 }, reliable: true, reason: "" };
      monitor.process(m, t);
    }
    expect(monitor.calibrator.status).toBe("done");
    const session = new LiveSession(t);
    for (let i = 0; i < 60 * 30; i++) {
      t += 1 / 30;
      const r = monitor.process(eyes.frame(t), t);
      session.add(r.observation, r.openness ? r.openness[2] : null);
    }
    expect(session.blinks).toBeGreaterThan(5);
    monitor.counter.state = "closed";
    monitor.interrupt();
    expect(monitor.counter.state).toBe("unknown");
  });
});

describe("sample break history", () => {
  it("summarises self-reports and keeps 'still learning' below the threshold", () => {
    const walking = summarise(SAMPLE_BREAKS, "sleepy").find((s) => s.activity === "walking")!;
    expect(walking.logged).toBe(5);
    expect(walking.complete).toBe(5);
    expect(walking.improved).toBe(3); // 4→3, 4→2, 4→2 (3→3 and 3→4 are not improvements)
    expect(walking.stillLearning).toBe(false); // 5 complete breaks reach STILL_LEARNING_BELOW
    expect(STILL_LEARNING_BELOW).toBe(5);
    const rest = summarise(SAMPLE_BREAKS, "comfort").find((s) => s.activity === "rest")!;
    expect(rest.complete).toBe(1); // one rest break skipped the after check-in
  });
});
