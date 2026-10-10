/**
 * One measuring step per frame — port of the counting part of
 * ocusense/monitoring/pipeline.py (EyeMonitor.process), without MediaPipe.
 *
 * Input: the eye measurement of one frame (EARs + reliability) or null when no
 * face was found. The same class drives the camera demo (real landmarks) and
 * the sample demo (synthetic EARs), so both use identical rules.
 */

import { BlinkCounter } from "./blinkCounter";
import { GuidedCalibration, PersonalCalibration, type Ears } from "./calibration";
import { GRAPH_SECONDS } from "./config";
import type { EyeMeasurement } from "./eyeMetrics";
import { MeasurementTracker, RollingWindow, invalidObservation, type FrameObservation, type RollingSnapshot } from "./measurements";

export type MonitorEvent = "closed_step_finished" | "calibration_done" | "calibration_failed";

export interface FrameResult {
  openness: [number, number, number] | null; // clipped, used by the detector
  blinked: boolean;
  events: MonitorEvent[];
  observation: FrameObservation;
}

export interface GraphSample {
  t: number;
  openness: number | null; // both eyes, clipped 0..1
  blinked: boolean;
}

export class EyeMonitorCore {
  counter = new BlinkCounter();
  calibrator = new GuidedCalibration();
  calibration: PersonalCalibration | null = null;

  resetSession(): void {
    this.counter = new BlinkCounter();
  }

  startCalibration(now: number): void {
    this.calibration = null;
    this.calibrator.start(now);
  }

  /** Monitoring paused: like lost tracking, so no blink can span the pause. */
  interrupt(): void {
    this.counter.update(null);
  }

  process(measurement: EyeMeasurement | null, now: number): FrameResult {
    const reliableEars: Ears | null =
      measurement && measurement.reliable && measurement.ears.left !== undefined && measurement.ears.right !== undefined
        ? { left: measurement.ears.left, right: measurement.ears.right }
        : null;
    const events: MonitorEvent[] = [];
    const calibrator = this.calibrator;
    const wasCalibrating = calibrator.status === "running";
    if (wasCalibrating) {
      const stepBefore = calibrator.step!.name;
      calibrator.update(now, reliableEars);
      if ((calibrator.step === null || calibrator.step.name !== stepBefore) && stepBefore === "closed") {
        events.push("closed_step_finished");
      }
      if (calibrator.status === "done") {
        this.calibration = calibrator.result;
        events.push("calibration_done");
      } else if (calibrator.status === "failed") {
        events.push("calibration_failed");
      }
    }
    let openness: FrameResult["openness"] = null;
    let raw: [number, number] | null = null;
    if (!wasCalibrating && this.calibration && reliableEars) {
      openness = this.calibration.openness(reliableEars);
      raw = this.calibration.rawOpenness(reliableEars);
    }
    const before = this.counter.state;
    const blinked = this.counter.update(openness ? openness[2] : null);
    const after = this.counter.state;
    const leftEar = measurement?.ears.left ?? null;
    const rightEar = measurement?.ears.right ?? null;
    const observation: FrameObservation = openness
      ? {
          t: now, valid: true, leftRaw: raw![0], rightRaw: raw![1], leftEar, rightEar,
          detectorClosed: after === "closed",
          closingStarted: before === "open" && after === "closed",
          blinkCompleted: blinked,
        }
      : invalidObservation(now, leftEar, rightEar);
    return { openness, blinked, events, observation };
  }
}

/** The rolling window plus graph history for one monitoring session. */
export class LiveSession {
  private tracker = new MeasurementTracker();
  readonly window: RollingWindow;
  private graph: GraphSample[] = [];
  running = true;
  blinks = 0;
  latest: FrameObservation | null = null;

  constructor(now: number) {
    this.window = new RollingWindow(now);
  }

  add(obs: FrameObservation, combinedOpenness: number | null): void {
    if (!this.running) return;
    this.latest = obs;
    const step = this.tracker.add(obs);
    this.window.add(step);
    if (step.blink) this.blinks += 1;
    this.graph.push({ t: obs.t, openness: combinedOpenness, blinked: obs.blinkCompleted });
    while (this.graph.length && this.graph[0].t < obs.t - GRAPH_SECONDS) this.graph.shift();
  }

  pause(t: number): void {
    if (!this.running) return;
    this.running = false;
    this.tracker.interrupt();
    this.window.pause(t);
  }

  resume(t: number): void {
    if (this.running) return;
    this.running = true;
    this.window.resume(t);
  }

  snapshot(now: number): RollingSnapshot {
    return this.window.snapshot(now);
  }

  graphSamples(): readonly GraphSample[] {
    return this.graph;
  }
}
