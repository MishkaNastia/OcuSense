"use client";

import { useCallback, useEffect, useState } from "react";

import { AlertBanner, MacNotificationPreview, type AlertKind } from "@/components/alerts/Alerts";
import { BreakFlow } from "@/components/breaks/BreakFlow";
import { RatingScale } from "@/components/breaks/RatingScale";
import { MeasurementPanel } from "@/components/measure/MeasurementPanel";
import { OpennessGraph } from "@/components/measure/OpennessGraph";
import { PatternsView } from "@/components/patterns/PatternsView";
import { COMFORT_LABELS, SAMPLE_BREAKS, SLEEPY_LABELS, type Activity, type BreakRecord } from "@/lib/demo/sampleHistory";
import { SampleSession, type SampleScenario } from "@/lib/demo/sampleSession";
import { clock } from "@/lib/measurement/format";

import styles from "./Demo.module.css";

const STEP_SECONDS = 0.1; // simulated time added per tick while playing

function freshSession(): SampleSession {
  const s = new SampleSession(7);
  s.advance(12); // start with a few seconds on the graph
  return s;
}

interface CheckIn { id: number; sleepy: number | null; comfort: number | null }

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
  const [checkInOpen, setCheckInOpen] = useState(false);
  const [pending, setPending] = useState<{ sleepy: number | null; comfort: number | null }>({ sleepy: null, comfort: null });
  const [checkIns, setCheckIns] = useState<CheckIn[]>([]);
  const [breaks, setBreaks] = useState<BreakRecord[]>(SAMPLE_BREAKS);
  const [startAt, setStartAt] = useState<{ stage: "select" | "during" | "after"; activity?: Activity; key: number }>();
  const [lastActivity, setLastActivity] = useState("a walking break");
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
    setPlaying(false); setScenario("steady"); setAlert(null); setOutcome(""); setCheckInOpen(false);
    setPending({ sleepy: null, comfort: null }); setCheckIns([]); setBreaks(SAMPLE_BREAKS); setStartAt(undefined);
    rerender();
  };
  const goToBreak = (stage: "select" | "after", activity?: Activity) => {
    setStartAt({ stage, activity, key: Date.now() });
    document.getElementById("breaks")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const onAlertAction = (action: string) => {
    setAlert(null);
    setCheckInOpen(false);
    switch (action) {
      case "Take a break": setOutcome(""); goToBreak("select"); break;
      case "Add feedback": setOutcome(""); goToBreak("after", "walking"); break;
      case "Check in": setOutcome(""); setCheckInOpen(true); break;
      case "Snooze 5 min": setOutcome("Snoozed for 5 minutes. (In this demo it won’t come back on its own — use the buttons above.)"); break;
      case "Remind me later": setOutcome("We’d ask once more a little later. (Demo: nothing is scheduled.)"); break;
      default: setOutcome("Dismissed. Nothing was recorded.");
    }
  };
  const onStageChange = useCallback((stage: string, label: string) => {
    if (stage === "during" && label) setLastActivity(label.toLowerCase().startsWith("a ") ? label : `a ${label.toLowerCase()} break`);
  }, []);

  return (
    <div className={styles.demo}>
      <div className={styles.toolbar} role="group" aria-label="Simulation controls">
        <button type="button" className="btn btn-primary btn-small" onClick={togglePlay} aria-pressed={playing}>
          {playing ? "Pause simulation" : "Play simulation"}
        </button>
        <button type="button" className="btn btn-secondary btn-small" onClick={fastForward}>Skip ahead 1 minute</button>
        <label className={styles.select}>
          Simulated pattern
          <select value={scenario} onChange={(e) => setScenario(e.target.value as SampleScenario)}>
            <option value="steady">Steady blinking</option>
            <option value="longer-closures">Longer eye closures</option>
          </select>
        </label>
        <button type="button" className="btn btn-quiet btn-small" onClick={reset}>Reset demo</button>
      </div>
      <p className="muted">
        <span className="tag">Synthetic data</span> A simulated person, not you. Everything you enter here stays in this tab’s memory
        and is cleared by Reset demo or reloading.
      </p>

      <section className={styles.studyCard} aria-labelledby="sim-title">
        <div className={styles.sessionRow}>
          <div>
            <p className="eyebrow" id="sim-title">Simulated study session</p>
            <p className={`mono ${styles.timer}`}>{clock(s.t)}</p>
            <p>{s.session.blinks} blinks counted · {playing ? "playing" : "paused"}</p>
          </div>
          <div className={styles.triggers} role="group" aria-label="Show a prompt now">
            <span className="muted">Show a prompt now:</span>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("scheduled"); setOutcome(""); }}>Scheduled break</button>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("pattern"); setOutcome(""); }}>Pattern change (experimental)</button>
            <button type="button" className="btn btn-secondary btn-small" onClick={() => { setAlert("feedback"); setOutcome(""); }}>After a break</button>
          </div>
        </div>
        {alert ? <AlertBanner kind={alert} activity={lastActivity} onAction={onAlertAction} /> : null}
        {outcome ? <p className="muted" role="status">{outcome}</p> : null}
        {checkInOpen ? (
          <div className={styles.checkIn}>
            <p className="eyebrow">Self-reported check-in</p>
            <div className={styles.scales}>
              <RatingScale question="How sleepy do you feel?" labels={SLEEPY_LABELS} value={pending.sleepy} onChange={(v) => setPending((p) => ({ ...p, sleepy: v }))} />
              <RatingScale question="How comfortable do your eyes feel?" labels={COMFORT_LABELS} value={pending.comfort} onChange={(v) => setPending((p) => ({ ...p, comfort: v }))} />
            </div>
            <div className={styles.row}>
              <button type="button" className="btn btn-primary btn-small" disabled={pending.sleepy === null && pending.comfort === null}
                onClick={() => { setCheckIns((c) => [...c, { id: Date.now(), ...pending }]); setPending({ sleepy: null, comfort: null }); setCheckInOpen(false); setOutcome("Check-in saved in this demo. It is your own rating, not a measurement."); }}>
                Save check-in
              </button>
              <button type="button" className="btn btn-quiet btn-small" onClick={() => setCheckInOpen(false)}>Cancel</button>
            </div>
          </div>
        ) : null}
        {checkIns.length ? (
          <p className="muted">Your check-ins in this demo: {checkIns.map((c) => `sleepiness ${c.sleepy ?? "—"}, eye comfort ${c.comfort ?? "—"}`).join(" · ")}</p>
        ) : null}
        <OpennessGraph samples={s.session.graphSamples()} now={s.t} label="Simulated personal eye openness over the last 10 seconds" />
        <MeasurementPanel snapshot={snapshot} opennessRaw={s.latestOpenness} source="sample" />
        {scenario === "longer-closures" ? (
          <p className="notice">
            <b>Simulated change:</b> the sample person’s closures are now longer. Watch the median closure duration
            rise over the next minute. In a future version, a sustained change like this could trigger the
            experimental “A quick check-in?” prompt — it would ask, never diagnose.
          </p>
        ) : null}
        {alert ? <MacNotificationPreview kind={alert} /> : null}
      </section>

      <section id="breaks" className={styles.section} aria-labelledby="breaks-title">
        <div>
          <p className="eyebrow">Break feedback</p>
          <h2 id="breaks-title">Take a break, then tell us how it went</h2>
          <p className="muted">Everything in this section is self-reported. It is kept separate from measured eye activity.</p>
        </div>
        <BreakFlow key={startAt?.key ?? "start"} startAt={startAt} onStageChange={onStageChange} onSave={(record) => setBreaks((b) => [...b, record])} />
      </section>

      <section id="patterns" className={styles.section} aria-labelledby="patterns-title">
        <div>
          <p className="eyebrow">Personal patterns</p>
          <h2 id="patterns-title">A sample week, plus anything you add</h2>
          <p className="muted">A synthetic history so you can explore. Breaks you log above appear here, marked “added by you”.</p>
        </div>
        <PatternsView breaks={breaks} />
      </section>
    </div>
  );
}
