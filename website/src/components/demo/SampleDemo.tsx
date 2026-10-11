"use client";

import { useEffect, useState } from "react";

import { AlertBanner, MacNotificationPreview, type AlertKind } from "@/components/alerts/Alerts";
import { MeasurementPanel } from "@/components/measure/MeasurementPanel";
import { OpennessGraph } from "@/components/measure/OpennessGraph";
import { SampleSession, type SampleScenario } from "@/lib/demo/sampleSession";
import { clock } from "@/lib/measurement/format";

import styles from "./Demo.module.css";

const STEP_SECONDS = 0.1; // simulated time added per tick while playing

function freshSession(): SampleSession {
  const s = new SampleSession(7);
  s.advance(12); // start with a few seconds on the graph
  return s;
}

/**
 * Sample session: everything here is SYNTHETIC and lives only in this component's
 * memory. Reset demo (or reloading the page) clears it.
 */
export function SampleDemo() {
  // The simulation object is mutated as time advances; `tick` triggers a re-render.
  const [sample, setSample] = useState<SampleSession>(freshSession);
  const [, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [scenario, setScenario] = useState<SampleScenario>("steady");
  const [alert, setAlert] = useState<AlertKind | null>(null);
  const [outcome, setOutcome] = useState("");
  const rerender = () => setTick((t) => t + 1);

  // Play the simulation only while the user asked for it and the tab is visible.
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      if (document.hidden) return;
      sample.advance(STEP_SECONDS);
      rerender();
    }, STEP_SECONDS * 1000);
    return () => window.clearInterval(id);
  }, [playing, sample]);

  useEffect(() => { sample.setScenario(scenario); }, [sample, scenario]);

  const s = sample;
  const snapshot = s.session.snapshot(s.t);

  // Simulated time only moves when playing or skipping, so "pause" needs no gap in the measurements.
  const fastForward = () => { s.advance(60); rerender(); };
  const togglePlay = () => setPlaying(!playing);
  const reset = () => {
    setSample(freshSession());
    setPlaying(false); setScenario("steady"); setAlert(null); setOutcome("");
    rerender();
  };
  const onAlertAction = (action: string) => {
    setAlert(null);
    switch (action) {
      case "Reminder settings": setOutcome("In the app this opens Settings, where you pick how often it may remind you, or switch it off."); break;
      default: setOutcome("Closed. Now go look at something far away for a moment.");
    }
  };

  return (
    <div className={styles.demo}>
      <div className={styles.toolbar} role="group" aria-label="Simulation controls">
        <button type="button" className="btn btn-primary btn-small" onClick={togglePlay} aria-pressed={playing}>
          {playing ? "Pause simulation" : "Play simulation"}
        </button>
        <button type="button" className="btn btn-secondary btn-small" onClick={fastForward}>Skip ahead 1 minute</button>
        <label className={styles.select}>
          Simulated blinking
          <select value={scenario} onChange={(e) => setScenario(e.target.value as SampleScenario)}>
            <option value="steady">Steady blinking</option>
            <option value="longer-closures">Longer eye closures</option>
          </select>
        </label>
        <button type="button" className="btn btn-quiet btn-small" onClick={reset}>Reset demo</button>
      </div>
      <p className="muted">
        <span className="tag">Made up data</span> A simulated person, not you. Nothing here is saved; Reset demo or
        reloading starts over.
      </p>

      <section className={styles.studyCard} aria-labelledby="sim-title">
        <div className={styles.sessionRow}>
          <div>
            <p className="eyebrow" id="sim-title">Simulated study session</p>
            <p className={`mono ${styles.timer}`}>{clock(s.t)}</p>
            <p>{s.session.blinks} blinks counted · {playing ? "playing" : "paused"}</p>
          </div>
          <div className={styles.triggers} role="group" aria-label="Show a reminder now">
            <span className="muted">Show a reminder from the app:</span>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("close"); setOutcome(""); }}>Too close</button>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("slower"); setOutcome(""); }}>Blinking slower</button>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("focus"); setOutcome(""); }}>Focus round done</button>
          </div>
        </div>
        {alert ? <AlertBanner kind={alert} onAction={onAlertAction} /> : null}
        {outcome ? <p className="muted" role="status">{outcome}</p> : null}
        <OpennessGraph samples={s.session.graphSamples()} now={s.t} label="Simulated personal eye openness over the last 10 seconds" />
        <MeasurementPanel snapshot={snapshot} opennessRaw={s.latestOpenness} source="sample" />
        {scenario === "longer-closures" ? (
          <p className="notice">
            <b>Simulated change:</b> the sample person’s blinks now last longer. Watch the median closure duration
            go up over the next minute (or press Skip ahead).
          </p>
        ) : null}
        {alert ? <MacNotificationPreview kind={alert} /> : null}
      </section>
    </div>
  );
}
