"use client";

import { useEffect, useState } from "react";

import { StepMark } from "@/components/art/Art";
import {
  ACTIVITIES, COMFORT_LABELS, HELPFUL_LABELS, SLEEPY_LABELS, type Activity, type BreakRecord, type Helpful,
} from "@/lib/demo/sampleHistory";
import { clock } from "@/lib/measurement/format";

import { RatingScale } from "./RatingScale";
import styles from "./Breaks.module.css";

type Stage = "select" | "during" | "after" | "saved";

interface Draft {
  activity: Activity | null;
  other: string;
  minutes: number;
  sleepyBefore: number | null;
  comfortBefore: number | null;
  sleepyAfter: number | null;
  comfortAfter: number | null;
  helpful: Helpful | null;
  note: string;
  napLater: boolean;
}

const EMPTY: Draft = {
  activity: null, other: "", minutes: 10, sleepyBefore: null, comfortBefore: null,
  sleepyAfter: null, comfortAfter: null, helpful: null, note: "", napLater: false,
};

const durationsFor = (a: Activity | null) => (a === "nap" ? [20, 30, 45] : [5, 10, 15, 20]);

function compare(before: number | null, after: number | null, name: string, lower: string, higher: string): string {
  if (before === null && after === null) return `${name}: not answered.`;
  if (before === null || after === null) return `${name}: not compared, one answer was skipped.`;
  if (before === after) return `${name}: ${before} before, ${after} after, no change reported.`;
  return `${name}: ${before} before, ${after} after, so you reported ${after < before ? lower : higher}.`;
}

/**
 * Break selection, a simple timer, and before/after self-reports.
 * Everything here is SELF-REPORTED and kept in memory by the parent page.
 */
export function BreakFlow({ onSave, startAt, onStageChange }: {
  onSave: (record: BreakRecord) => void;
  /** Jump straight to a stage (e.g. "after" from a "Did that help?" prompt). Change the component's `key` to apply a new one. */
  startAt?: { stage: Stage; activity?: Activity; key: number };
  onStageChange?: (stage: Stage, label: string) => void;
}) {
  const [stage, setStage] = useState<Stage>(startAt?.stage ?? "select");
  const [draft, setDraft] = useState<Draft>(startAt ? { ...EMPTY, activity: startAt.activity ?? "walking" } : EMPTY);
  const [left, setLeft] = useState(startAt?.stage === "during" ? 10 * 60 : 0);
  const [saved, setSaved] = useState<BreakRecord | null>(null);
  const update = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const label = draft.activity === "other" ? draft.other.trim() || "Other" : ACTIVITIES.find((a) => a.id === draft.activity)?.label ?? "";

  useEffect(() => onStageChange?.(stage, label), [stage, label, onStageChange]);

  // A plain countdown that only runs during a break (no sound when it ends).
  useEffect(() => {
    if (stage !== "during") return;
    const id = window.setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, [stage]);

  const finish = (skip: boolean) => {
    const record: BreakRecord = {
      id: `demo-${Date.now()}`, day: "Today", activity: draft.activity ?? "other", label,
      minutes: draft.minutes,
      sleepy: [draft.sleepyBefore, skip ? null : draft.sleepyAfter],
      comfort: [draft.comfortBefore, skip ? null : draft.comfortAfter],
      helpful: skip ? null : draft.helpful, note: skip ? undefined : draft.note.trim() || undefined, sample: false,
    };
    onSave(record);
    setSaved(record);
    setStage("saved");
  };

  if (stage === "during") {
    return (
      <div className={styles.flow} aria-live="polite">
        <div className={styles.duringHead}>
          <StepMark step="break" size={96} />
          <div>
            <p className="eyebrow">On a break</p>
            <h3 className={styles.flowTitle}>{label}</h3>
          </div>
        </div>
        <p className={`mono ${styles.countdown}`} role="timer" aria-label="Time left in your break">{clock(left).slice(3)}</p>
        <p className="muted">of {draft.minutes} min planned{left === 0 ? ". Your planned break time is over. Finish when you’re ready." : ""}</p>
        <p className="muted">In the app, camera measurement is paused during a break. No sound plays when the time is up.</p>
        <div className={styles.row}>
          <button type="button" className="btn btn-primary" onClick={() => setStage("after")}>Finish break</button>
          <button type="button" className="btn btn-secondary" onClick={() => { setLeft((s) => s + 300); update({ minutes: draft.minutes + 5 }); }}>Extend 5 min</button>
        </div>
      </div>
    );
  }

  if (stage === "after") {
    return (
      <div className={styles.flow}>
        <div>
          <p className="eyebrow">Self-reported check-in</p>
          <h3 className={styles.flowTitle}>Did that help?</h3>
          <p className="muted">{label} · {draft.minutes} min. Same two questions as before, all optional.</p>
        </div>
        <div className={styles.scales}>
          <RatingScale question="How sleepy do you feel?" labels={SLEEPY_LABELS} value={draft.sleepyAfter} onChange={(v) => update({ sleepyAfter: v })} />
          <RatingScale question="How comfortable do your eyes feel?" labels={COMFORT_LABELS} value={draft.comfortAfter} onChange={(v) => update({ comfortAfter: v })} />
        </div>
        <fieldset className={styles.choice}>
          <legend>Was this break helpful?</legend>
          <div className={styles.row}>
            {(Object.keys(HELPFUL_LABELS) as Helpful[]).map((h) => (
              <button key={h} type="button" className={styles.chip} aria-pressed={draft.helpful === h}
                onClick={() => update({ helpful: draft.helpful === h ? null : h })}>{HELPFUL_LABELS[h]}</button>
            ))}
          </div>
        </fieldset>
        <div className="field" style={{ maxWidth: 520 }}>
          <label htmlFor="break-note">Note (optional)</label>
          <textarea id="break-note" maxLength={140} value={draft.note} onChange={(e) => update({ note: e.target.value })} />
        </div>
        {draft.activity === "nap" ? (
          <label className={styles.check}>
            <input type="checkbox" checked={draft.napLater} onChange={(e) => update({ napLater: e.target.checked })} />
            Check in again later <span className="muted">(demo only, no reminder is actually scheduled)</span>
          </label>
        ) : null}
        <div className={styles.row}>
          <button type="button" className="btn btn-primary" onClick={() => finish(false)}>Save feedback</button>
          <button type="button" className="btn btn-quiet" onClick={() => finish(true)}>Skip</button>
        </div>
      </div>
    );
  }

  if (stage === "saved" && saved) {
    return (
      <div className={styles.flow} role="status">
        <p className="eyebrow">Saved in this demo only</p>
        <h3 className={styles.flowTitle}>Break recorded</h3>
        <ul className={styles.facts}>
          <li>{saved.label} · {saved.minutes} min</li>
          <li>{compare(saved.sleepy[0], saved.sleepy[1], "Sleepiness", "feeling less sleepy", "feeling sleepier")}</li>
          <li>{compare(saved.comfort[0], saved.comfort[1], "Eye comfort", "less comfortable eyes", "more comfortable eyes")}</li>
          {saved.helpful ? <li>Helpful: {HELPFUL_LABELS[saved.helpful]}</li> : null}
          {draft.napLater ? <li>Later check-in requested (demo only, nothing is scheduled)</li> : null}
        </ul>
        <p className="muted">These are your own ratings. A change after a break doesn’t show what caused it.</p>
        <div className={styles.row}>
          <button type="button" className="btn btn-secondary" onClick={() => { setDraft(EMPTY); setSaved(null); setStage("select"); }}>Log another break</button>
          <a className="btn btn-quiet" href="#patterns">See it in your patterns</a>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.flow}>
      <fieldset className={styles.choice}>
        <legend>What will you do?</legend>
        <div className={styles.activities}>
          {ACTIVITIES.map((a) => (
            <button key={a.id} type="button" className={styles.activity} aria-pressed={draft.activity === a.id}
              onClick={() => {
                const options = durationsFor(a.id);
                update({ activity: a.id, minutes: options.includes(draft.minutes) ? draft.minutes : options[a.id === "nap" ? 0 : 1] });
              }}>
              <b>{a.label}</b><span>{a.hint}</span>
            </button>
          ))}
        </div>
        {draft.activity === "other" ? (
          <div className="field" style={{ maxWidth: 360, marginTop: 12 }}>
            <label htmlFor="other-label">Label (optional)</label>
            <input id="other-label" maxLength={40} value={draft.other} onChange={(e) => update({ other: e.target.value })} placeholder="e.g. Making tea" />
          </div>
        ) : null}
      </fieldset>
      <fieldset className={styles.choice}>
        <legend>How long?</legend>
        <div className={styles.row}>
          {durationsFor(draft.activity).map((m) => (
            <button key={m} type="button" className={styles.chip} aria-pressed={draft.minutes === m} onClick={() => update({ minutes: m })}>{m} min</button>
          ))}
        </div>
      </fieldset>
      <div className={styles.scales}>
        <RatingScale question="How sleepy do you feel?" labels={SLEEPY_LABELS} value={draft.sleepyBefore} onChange={(v) => update({ sleepyBefore: v })} />
        <RatingScale question="How comfortable do your eyes feel?" labels={COMFORT_LABELS} value={draft.comfortBefore} onChange={(v) => update({ comfortBefore: v })} />
      </div>
      <div className={styles.row}>
        <button type="button" className="btn btn-primary" disabled={!draft.activity} onClick={() => { setLeft(draft.minutes * 60); setStage("during"); }}>Start break</button>
        <button type="button" className="btn btn-secondary" disabled={!draft.activity}
          onClick={() => { update({ sleepyBefore: null, comfortBefore: null }); setLeft(draft.minutes * 60); setStage("during"); }}>Skip questions and start</button>
        {!draft.activity ? <span className="muted">Choose an activity to start.</span> : null}
      </div>
    </div>
  );
}
