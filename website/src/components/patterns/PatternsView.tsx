"use client";

import { useState } from "react";

import {
  COMFORT_LABELS, HELPFUL_LABELS, SAMPLE_DAYS, SLEEPY_LABELS, STILL_LEARNING_BELOW, summarise, type BreakRecord,
} from "@/lib/demo/sampleHistory";

import styles from "./Patterns.module.css";

type Metric = "rate" | "closure" | "closed";
const METRICS: Record<Metric, { label: string; unit: string; max: number; value: (d: (typeof SAMPLE_DAYS)[number]) => number }> = {
  rate: { label: "Blink rate", unit: "blinks/min", max: 24, value: (d) => d.blinkRate },
  closure: { label: "Median closure", unit: "ms", max: 300, value: (d) => d.medianClosureMs },
  closed: { label: "Time closed", unit: "%", max: 6, value: (d) => d.closedPercent },
};

function Segmented<T extends string>({ label, options, value, onChange }: { label: string; options: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <div className={styles.segmented} role="group" aria-label={label}>
      {options.map(([id, text]) => (
        <button key={id} type="button" aria-pressed={value === id} onClick={() => onChange(id)}>{text}</button>
      ))}
    </div>
  );
}

export function PatternsView({ breaks }: { breaks: BreakRecord[] }) {
  const [metric, setMetric] = useState<Metric>("rate");
  const [felt, setFelt] = useState<"sleepy" | "comfort">("sleepy");
  const [helpView, setHelpView] = useState<"sleepy" | "comfort">("sleepy");
  const m = METRICS[metric];
  const studied = SAMPLE_DAYS.filter((d) => d.studyMinutes > 0);
  const totalMinutes = studied.reduce((s, d) => s + d.studyMinutes, 0);
  const rows = [...breaks].reverse().filter((b) => b[felt][0] !== null || b[felt][1] !== null).slice(0, 8);
  const labels = felt === "sleepy" ? SLEEPY_LABELS : COMFORT_LABELS;

  return (
    <div className={styles.patterns}>
      <section aria-labelledby="measured" className={styles.block}>
        <div className={styles.head}>
          <div>
            <h3 id="measured">Measured eye activity</h3>
            <p className="muted">Sample week · {Math.floor(totalMinutes / 60)} h {totalMinutes % 60} min of simulated study · camera-derived numbers</p>
          </div>
          <span className="tag">Simulated</span>
        </div>
        <Segmented label="Measure" value={metric} onChange={setMetric}
          options={[["rate", "Blink rate"], ["closure", "Median closure"], ["closed", "Time closed"]]} />
        <ul className={styles.days}>
          {SAMPLE_DAYS.map((d) => (
            <li key={d.day}>
              <span className={styles.day}>{d.day}</span>
              {d.studyMinutes ? (
                <>
                  <span className={styles.track} aria-hidden="true"><span style={{ width: `${Math.min(100, (m.value(d) / m.max) * 100)}%` }} /></span>
                  <span className="mono">{m.value(d).toFixed(metric === "closure" ? 0 : 1)} {m.unit}</span>
                  <span className="muted">{d.studyMinutes} min · {Math.round(d.trackedShare * 100)}% tracked</span>
                </>
              ) : <span className="muted">No study session, so left blank rather than zero</span>}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="felt" className={styles.block}>
        <div className={styles.head}>
          <div>
            <h3 id="felt">How you felt</h3>
            <p className="muted">Before (ring) and after (dot) a break, on a scale from 1 to 5.</p>
          </div>
          <span className="tag tag-solid">Self-reported</span>
        </div>
        <Segmented label="Rating" value={felt} onChange={setFelt} options={[["sleepy", "Sleepiness"], ["comfort", "Eye comfort"]]} />
        <div className={styles.scaleHead} aria-hidden="true"><span /><span>1 · {labels[0]}</span><span>5 · {labels[4]}</span></div>
        <ul className={styles.felt}>
          {rows.map((b) => {
            const [before, after] = b[felt];
            const pos = (v: number) => `${((v - 1) / 4) * 100}%`;
            return (
              <li key={b.id}>
                <span>{b.day} · {b.label} {b.sample ? null : <span className="tag">added by you</span>}</span>
                <span className={styles.dumbbell} aria-label={`Before ${before ?? "not answered"}, after ${after ?? "not answered"}`} role="img">
                  {before !== null && after !== null && before !== after ? (
                    <i className={styles.link} style={{ left: pos(Math.min(before, after)), width: `${(Math.abs(after - before) / 4) * 100}%` }} />
                  ) : null}
                  {before !== null ? <i className={styles.before} style={{ left: pos(before) }} /> : null}
                  {after !== null ? <i className={styles.after} style={{ left: pos(after) }} /> : null}
                </span>
                <span className="mono muted">{before ?? "none"} → {after ?? "none"}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="helpful" className={styles.block}>
        <div className={styles.head}>
          <div>
            <h3 id="helpful">What seems helpful</h3>
            <p className="muted">How often you reported an improvement after breaks with both check-ins. Shows what you said, not what caused it.</p>
          </div>
          <span className="tag tag-solid">Self-reported</span>
        </div>
        <Segmented label="Compare by" value={helpView} onChange={setHelpView} options={[["sleepy", "Sleepiness"], ["comfort", "Eye comfort"]]} />
        <ul className={styles.helpful}>
          {summarise(breaks, helpView).map((s) => {
            const word = helpView === "sleepy" ? "less sleepy" : "more comfortable eyes";
            const sentence = !s.complete
              ? "No break with both check-ins yet."
              : s.stillLearning
                ? `${s.improved} of ${s.complete} with ${word} so far. That’s too few to see a pattern.`
                : `You reported ${word} after ${s.improved} of ${s.complete} ${s.label.toLowerCase()} breaks.`;
            return (
              <li key={s.activity}>
                <div className={styles.helpHead}>
                  <b>{s.label}</b>
                  <span className="muted">logged {s.logged}× · {s.complete} with both check-ins</span>
                  {s.stillLearning ? <span className="tag">Still learning</span> : null}
                </div>
                <span className={`${styles.track} ${s.stillLearning ? styles.trackLearning : ""}`} aria-hidden="true">
                  <span style={{ width: `${s.complete ? (s.improved / s.complete) * 100 : 0}%` }} />
                </span>
                <p>{sentence}</p>
              </li>
            );
          })}
        </ul>
        <p className="muted">“Still learning” until an activity has {STILL_LEARNING_BELOW} breaks with both check-ins. Not a recommendation and not medical advice.</p>
      </section>

      <section aria-labelledby="history" className={styles.block}>
        <h3 id="history">Break history</h3>
        <ul className={styles.history}>
          {[...breaks].reverse().map((b) => (
            <li key={b.id}>
              <span><b>{b.day}</b> · {b.label} · {b.minutes} min {b.sample ? <span className="tag">sample</span> : <span className="tag tag-solid">added by you</span>}</span>
              <span className="muted">
                Sleepiness {b.sleepy[0] ?? "none"} → {b.sleepy[1] ?? "none"} · eye comfort {b.comfort[0] ?? "none"} → {b.comfort[1] ?? "none"}
                {b.helpful ? ` · ${HELPFUL_LABELS[b.helpful]}` : ""}{b.note ? ` · “${b.note}”` : ""}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
