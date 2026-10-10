/**
 * Browser camera + MediaPipe + the shared measurement engine, outside React.
 *
 * Privacy: frames are drawn to an in-memory canvas, analysed, and discarded.
 * Nothing is uploaded or recorded. The camera is requested only from start(),
 * which the page calls after an explicit button press, and is released on
 * stop(), when the tab is hidden, and on dispose().
 *
 * Performance: one frame is processed at a time (requestVideoFrameCallback /
 * requestAnimationFrame), so work never piles up; the UI is notified at most
 * ~10 times per second.
 */

import type { FaceLandmarker } from "@mediapipe/tasks-vision";

import { STEPS, type CalibrationStatus } from "@/lib/measurement/calibration";
import { measureEyes, type EyeMeasurement } from "@/lib/measurement/eyeMetrics";
import type { FrameObservation, RollingSnapshot } from "@/lib/measurement/measurements";
import { EyeMonitorCore, LiveSession, type GraphSample } from "@/lib/measurement/monitor";

export const WASM_PATH = "/vendor/mediapipe/wasm";
export const MODEL_PATH = "/models/face_landmarker.task";

export type Phase = "idle" | "starting" | "calibrating" | "monitoring" | "paused" | "stopped" | "error";
export type ErrorKind = "unsupported" | "denied" | "no-camera" | "busy" | "model" | "other";

export interface CameraState {
  phase: Phase;
  error: { kind: ErrorKind; message: string } | null;
  pausedBecause: "hidden" | "user" | null;
  calibrated: boolean;
  calibration: { status: CalibrationStatus; step: number | null; secondsLeft: number; measuring: boolean; error: string };
  face: { found: boolean; reliable: boolean; reason: string };
  latest: FrameObservation | null;
  snapshot: RollingSnapshot | null;
  graph: readonly GraphSample[];
  now: number;
  blinks: number;
}

const INITIAL: CameraState = {
  phase: "idle", error: null, pausedBecause: null, calibrated: false,
  calibration: { status: "idle", step: null, secondsLeft: 0, measuring: false, error: "" },
  face: { found: false, reliable: false, reason: "" },
  latest: null, snapshot: null, graph: [], now: 0, blinks: 0,
};

const seconds = () => performance.now() / 1000; // monotonic clock

export type Support = { ok: true } | { ok: false; reason: string };
let cachedSupport: Support | null = null;
export const SERVER_SUPPORT: Support = { ok: true }; // assumed during prerendering; checked again in the browser

/** Same object on every call (React's useSyncExternalStore requires a stable snapshot). */
export function cameraSupport(): Support {
  if (typeof window === "undefined") return SERVER_SUPPORT;
  cachedSupport ??= detectSupport();
  return cachedSupport;
}

function detectSupport(): Support {
  if (!window.isSecureContext) return { ok: false, reason: "The camera only works on a secure (https) page or on localhost." };
  if (!navigator.mediaDevices?.getUserMedia) return { ok: false, reason: "This browser doesn’t allow web pages to use a camera." };
  if (typeof WebAssembly === "undefined") return { ok: false, reason: "This browser doesn’t support WebAssembly, which the face model needs." };
  return { ok: true };
}

export class CameraTracker {
  private state: CameraState = INITIAL;
  private listeners = new Set<() => void>();
  private video: HTMLVideoElement | null = null;
  private stream: MediaStream | null = null;
  private landmarker: FaceLandmarker | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private monitor = new EyeMonitorCore();
  private session: LiveSession | null = null;
  private running = false;
  private lastTimestamp = -1;
  private lastEmit = 0;
  private frameHandle: number | null = null;
  private keepSessionOnStart = false;
  soundCue = false;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  getState = () => this.state;

  setSoundCue(on: boolean): void {
    this.soundCue = on;
  }

  attach(video: HTMLVideoElement | null): void {
    this.video = video;
  }

  private set(patch: Partial<CameraState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l());
  }

  async start(): Promise<void> {
    const support = cameraSupport();
    if (!support.ok) return this.set({ phase: "error", error: { kind: "unsupported", message: support.reason } });
    if (!this.video) return;
    this.set({ phase: "starting", error: null, pausedBecause: null });
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false,
      });
    } catch (error) {
      return this.fail(error);
    }
    if (this.state.phase !== "starting") return this.releaseCamera(); // stopped or hidden while asking for permission
    try {
      if (!this.landmarker) this.landmarker = await this.loadModel();
    } catch {
      this.releaseCamera();
      return this.set({ phase: "error", error: { kind: "model", message: "The face model couldn’t be loaded. Check your connection and reload the page." } });
    }
    if (this.state.phase !== "starting") return this.releaseCamera();
    this.video.srcObject = this.stream;
    this.video.muted = true;
    this.video.playsInline = true;
    try { await this.video.play(); } catch { /* autoplay of a muted inline video is allowed after the click */ }
    if (this.monitor.calibration && this.keepSessionOnStart && this.session) {
      this.session.resume(seconds()); // continue the same session after a pause: history is kept
      this.set({ phase: "monitoring" });
    } else if (this.monitor.calibration) {
      this.beginMonitoring();
    } else {
      this.beginCalibration();
    }
    this.keepSessionOnStart = false;
    this.running = true;
    this.schedule();
  }

  private async loadModel(): Promise<FaceLandmarker> {
    const vision = await import("@mediapipe/tasks-vision");
    const fileset = await vision.FilesetResolver.forVisionTasks(WASM_PATH);
    const create = (delegate: "GPU" | "CPU") => vision.FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_PATH, delegate }, runningMode: "VIDEO", numFaces: 1,
    });
    try { return await create("GPU"); } catch { return await create("CPU"); }
  }

  private fail(error: unknown): void {
    const name = error instanceof DOMException ? error.name : "";
    const map: Record<string, [ErrorKind, string]> = {
      NotAllowedError: ["denied", "Camera access was blocked. You can allow it in your browser’s site settings and try again — or explore the sample session instead."],
      SecurityError: ["denied", "The browser blocked camera access on this page."],
      NotFoundError: ["no-camera", "No camera was found on this device."],
      OverconstrainedError: ["no-camera", "No suitable camera was found on this device."],
      NotReadableError: ["busy", "The camera is in use by another app (for example a video call). Close it and try again."],
    };
    const [kind, message] = map[name] ?? ["other", "The camera couldn’t be started."];
    this.releaseCamera();
    this.set({ phase: "error", error: { kind, message } });
  }

  private beginCalibration(): void {
    this.monitor.startCalibration(seconds());
    this.set({ phase: "calibrating", calibrated: false });
  }

  private beginMonitoring(): void {
    const now = seconds();
    this.session = new LiveSession(now);
    this.monitor.resetSession();
    this.set({ phase: "monitoring", calibrated: true, blinks: 0, snapshot: null, graph: [], latest: null });
  }

  recalibrate(): void {
    if (!this.running) return;
    this.session = null;
    this.beginCalibration();
  }

  /** Pause: stop processing and release the camera (its light turns off); the calibration is kept. */
  pause(reason: "hidden" | "user"): void {
    if (!this.running && this.state.phase !== "starting") return;
    const t = seconds();
    this.session?.pause(t);
    this.monitor.interrupt();
    if (this.state.phase === "calibrating") this.monitor.calibration = null; // an interrupted calibration starts over
    this.running = false;
    this.cancelFrame();
    this.releaseCamera();
    this.set({ phase: "paused", pausedBecause: reason });
  }

  async resume(): Promise<void> {
    if (this.state.phase !== "paused") return;
    this.keepSessionOnStart = true;
    await this.start();
  }

  stop(): void {
    this.running = false;
    this.cancelFrame();
    this.releaseCamera();
    this.session = null;
    this.set({ phase: "stopped", pausedBecause: null });
  }

  dispose(): void {
    this.stop();
    this.landmarker?.close();
    this.landmarker = null;
    this.listeners.clear();
  }

  private releaseCamera(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    if (this.video) this.video.srcObject = null;
  }

  private cancelFrame(): void {
    if (this.frameHandle === null || !this.video) return;
    const v = this.video as HTMLVideoElement & { cancelVideoFrameCallback?: (h: number) => void };
    if (v.cancelVideoFrameCallback) v.cancelVideoFrameCallback(this.frameHandle);
    cancelAnimationFrame(this.frameHandle);
    this.frameHandle = null;
  }

  private schedule(): void {
    if (!this.running || !this.video) return;
    const v = this.video as HTMLVideoElement & { requestVideoFrameCallback?: (cb: () => void) => number };
    this.frameHandle = v.requestVideoFrameCallback
      ? v.requestVideoFrameCallback(() => this.tick())
      : requestAnimationFrame(() => this.tick());
  }

  /** Process exactly one frame, then schedule the next — work never accumulates. */
  private tick(): void {
    if (!this.running || !this.video || !this.landmarker) return;
    const video = this.video;
    if (video.readyState >= 2 && video.videoWidth > 0) {
      const now = seconds();
      const measurement = this.detect(video, now);
      const result = this.monitor.process(measurement, now);
      if (this.state.phase === "calibrating") this.onCalibrationFrame(result.events);
      else if (this.session) this.session.add(result.observation, result.openness ? result.openness[2] : null);
      const face = { found: measurement !== null, reliable: !!measurement?.reliable, reason: measurement?.reason ?? "" };
      if (now - this.lastEmit > 0.1 || result.events.length) {
        this.lastEmit = now;
        const cal = this.monitor.calibrator;
        this.set({
          face, now, latest: result.observation,
          blinks: this.session?.blinks ?? 0,
          graph: this.session ? [...this.session.graphSamples()] : [],
          snapshot: this.session ? this.session.snapshot(now) : null,
          calibration: { status: cal.status, step: cal.stepNumber, secondsLeft: cal.secondsLeft(now), measuring: cal.measuring(now), error: cal.error },
        });
      }
    }
    this.schedule();
  }

  private detect(video: HTMLVideoElement, now: number): EyeMeasurement | null {
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!this.canvas) this.canvas = document.createElement("canvas");
    const canvas = this.canvas;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) return null;
    // Mirror the frame before detection, exactly like the desktop app (eye names depend on it).
    ctx.setTransform(-1, 0, 0, 1, w, 0);
    ctx.drawImage(video, 0, 0, w, h);
    const timestamp = Math.max(this.lastTimestamp + 1, Math.round(now * 1000));
    this.lastTimestamp = timestamp;
    const result = this.landmarker!.detectForVideo(canvas, timestamp);
    const landmarks = result.faceLandmarks?.[0];
    return landmarks ? measureEyes(landmarks, w, h) : null;
  }

  private onCalibrationFrame(events: string[]): void {
    if (events.includes("closed_step_finished") && this.soundCue) playCue();
    if (events.includes("calibration_done")) this.beginMonitoring();
  }
}

/** A short, quiet tone — only if the person switched the sound cue on. */
function playCue(): void {
  try {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 660;
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.36);
    osc.onended = () => ctx.close();
  } catch { /* no audio available: the on-screen cue still shows */ }
}

export const CALIBRATION_STEP_TEXT = STEPS.map((s, i) => ({
  ...s,
  title: ["Eyes comfortably open", "Gently close your eyes", "A few natural blinks"][i],
  detail: [
    "Look at the screen with your eyes comfortably open.",
    "When the countdown ends, close your eyes gently and slowly count to 5, then open them.",
    "Blink naturally, about 5 times.",
  ][i],
}));
