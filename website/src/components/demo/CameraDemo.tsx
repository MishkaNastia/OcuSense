"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { MeasurementPanel } from "@/components/measure/MeasurementPanel";
import { OpennessGraph } from "@/components/measure/OpennessGraph";
import { CALIBRATION_STEP_TEXT, CameraTracker, cameraSupport, SERVER_SUPPORT, type CameraState } from "@/lib/camera/cameraTracker";

import styles from "./Demo.module.css";

function Status({ state }: { state: CameraState }) {
  let text = "Camera off";
  let shape = <rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="var(--ink)" strokeWidth="1.6" />;
  if (state.phase === "starting") text = "Starting the camera…";
  if (state.phase === "calibrating" || state.phase === "monitoring") {
    if (!state.face.found || !state.face.reliable) {
      text = state.face.found ? `Tracking paused: ${state.face.reason}` : "Tracking paused: face not found";
      shape = <path d="M6 1 L11.5 11 H0.5 Z" fill="var(--golden)" stroke="var(--ink)" strokeWidth="1.4" strokeLinejoin="round" />;
    } else {
      text = state.phase === "calibrating" ? "Calibrating · face tracked" : "Monitoring · face tracked";
      shape = <circle cx="6" cy="6" r="5" fill="var(--cobalt)" />;
    }
  }
  if (state.phase === "paused") {
    text = state.pausedBecause === "hidden" ? "Paused because the tab was hidden" : "Paused";
    shape = <circle cx="6" cy="6" r="4.5" fill="none" stroke="var(--ink)" strokeWidth="1.6" />;
  }
  return (
    <p className={styles.status} role="status">
      <svg className={styles.glyph} viewBox="0 0 12 12" aria-hidden="true">{shape}</svg>
      {text}
    </p>
  );
}

const noSubscription = () => () => {};

export function CameraDemo() {
  const [tracker] = useState(() => new CameraTracker());
  const state = useSyncExternalStore(tracker.subscribe, tracker.getState, tracker.getState);
  const [sound, setSound] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const support = useSyncExternalStore(noSubscription, cameraSupport, () => SERVER_SUPPORT);

  const videoRef = useCallback((node: HTMLVideoElement | null) => tracker.attach(node), [tracker]);

  // Release the camera when leaving the page, and pause while the tab is hidden.
  useEffect(() => {
    const onVisibility = () => { if (document.hidden) tracker.pause("hidden"); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      tracker.dispose();
    };
  }, [tracker]);

  useEffect(() => { tracker.setSoundCue(sound); }, [tracker, sound]);

  const active = state.phase === "calibrating" || state.phase === "monitoring" || state.phase === "starting";
  const step = state.calibration.step !== null ? CALIBRATION_STEP_TEXT[state.calibration.step] : null;
  const latest = state.latest;

  return (
    <div className={styles.demo}>
      {!support.ok ? (
        <div className="notice notice-attention" role="alert">
          <b>The camera demo can’t run here.</b> {support.reason} <Link href="/demo/sample">Explore the sample session instead.</Link>
        </div>
      ) : null}

      <div className={styles.toolbar}>
        {state.phase === "paused" ? (
          <button type="button" className="btn btn-primary" onClick={() => tracker.resume()}>Resume camera</button>
        ) : !active ? (
          <button type="button" className="btn btn-primary" disabled={!support.ok} onClick={() => tracker.start()}>
            {state.calibrated ? "Start camera again" : "Start camera"}
          </button>
        ) : null}
        {active ? <button type="button" className="btn btn-secondary" onClick={() => tracker.pause("user")}>Pause</button> : null}
        {active || state.phase === "paused" ? <button type="button" className="btn btn-quiet" onClick={() => tracker.stop()}>Stop camera</button> : null}
        {state.phase === "monitoring" ? <button type="button" className="btn btn-quiet" onClick={() => tracker.recalibrate()}>Recalibrate</button> : null}
        <label className={styles.select}>
          <input type="checkbox" checked={sound} onChange={(e) => setSound(e.target.checked)} /> Soft sound when you can open your eyes
        </label>
      </div>

      {state.phase === "error" && state.error ? (
        <div className="notice notice-attention" role="alert">
          <b>{state.error.message}</b>{" "}
          <Link href="/demo/sample">Explore the sample session</Link>. It needs no camera.
        </div>
      ) : null}
      {state.phase === "paused" && state.pausedBecause === "hidden" ? (
        <p className="notice" role="status">
          Browsers slow down or stop background tabs, so the demo paused and turned the camera off when you switched away.
          Your calibration and measurements are kept. Press Resume camera to continue.
        </p>
      ) : null}

      <div className={styles.cameraLayout}>
        <div className={styles.video}>
          <video ref={videoRef} className={styles.mirror} muted playsInline aria-label="Your camera preview (mirrored, stays in this browser)" />
          {state.phase === "idle" || state.phase === "stopped" || state.phase === "error" ? (
            <p className={styles.videoNote}>Your camera preview appears here after you press Start camera. Nothing is recorded or uploaded.</p>
          ) : null}
        </div>

        <aside className={styles.calibration} aria-live="polite">
          <Status state={state} />
          {state.phase === "calibrating" && step ? (
            <>
              <p className="eyebrow">Calibration · step {state.calibration.step! + 1} of 3</p>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
              <p className={`mono ${styles.countdown}`} aria-label="Seconds left in this step">{Math.max(0, Math.ceil(state.calibration.secondsLeft))}</p>
              <p><b>{state.calibration.measuring ? "Measuring now" : "Get ready"}</b></p>
              <ol className={styles.steps}>
                {CALIBRATION_STEP_TEXT.map((s, i) => (
                  <li key={s.name} aria-current={i === state.calibration.step ? "step" : undefined}>
                    {i < state.calibration.step! ? "Done · " : i === state.calibration.step ? "Now · " : "Next · "}{s.title}
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          {state.phase === "calibrating" && state.calibration.status === "failed" ? (
            <div className="notice notice-attention" role="alert">
              <p><b>Calibration didn’t work:</b> {state.calibration.error}</p>
              <button type="button" className="btn btn-primary btn-small" onClick={() => tracker.recalibrate()}>Try again</button>
            </div>
          ) : null}
          {state.phase === "starting" ? <p>Loading the face model and starting your camera…</p> : null}
          {state.phase === "monitoring" ? (
            <>
              <p className="eyebrow">Live session</p>
              <p className="mono" style={{ fontSize: "2rem", lineHeight: 1 }}>{state.blinks} blinks</p>
              <p className="muted">Counted once per close-and-reopen of both eyes. Winks and tracking gaps don’t count.</p>
            </>
          ) : null}
          {state.phase === "idle" ? (
            <p className="muted">
              You’ll calibrate first (under half a minute): eyes open, gently closed, then a few natural blinks. Sit facing the
              screen with light on your face.
            </p>
          ) : null}
        </aside>
      </div>

      {state.phase === "monitoring" || (state.phase === "paused" && state.calibrated) ? (
        <section className={styles.studyCard} aria-label="Your measurements">
          <OpennessGraph samples={state.graph} now={state.now} dimmed={state.phase === "paused"}
            message={state.graph.length ? undefined : "Waiting for the first measurements…"}
            label="Your personal eye openness over the last 10 seconds" />
          <MeasurementPanel snapshot={state.snapshot} opennessRaw={latest?.valid ? [latest.leftRaw!, latest.rightRaw!] : null} source="camera" />
          <p className="muted">
            The reminders (too close, blinking slower, Pomodoro) live in the desktop app; you can preview them in the{" "}
            <Link href="/demo/sample">sample session</Link>. Nothing here diagnoses tiredness or any condition.
          </p>
          <button type="button" className="btn btn-quiet btn-small" aria-expanded={showDetails} onClick={() => setShowDetails((v) => !v)} style={{ alignSelf: "flex-start" }}>
            {showDetails ? "Hide details" : "Show details"}
          </button>
          {showDetails ? (
            <div className={styles.details}>
              <span>EAR left {latest?.leftEar?.toFixed(3) ?? "none"} · right {latest?.rightEar?.toFixed(3) ?? "none"}</span>
              <span>Unclamped openness left {latest?.leftRaw != null ? `${Math.round(latest.leftRaw * 100)}%` : "none"} · right {latest?.rightRaw != null ? `${Math.round(latest.rightRaw * 100)}%` : "none"}</span>
              <span>Processing rate {state.snapshot?.processingRate ? `${state.snapshot.processingRate.toFixed(1)} frames/s` : "none"} · coverage {state.snapshot?.coverage != null ? `${Math.round(state.snapshot.coverage * 100)}%` : "none"}</span>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
