"use client";

import { useState } from "react";

import { LogoMark } from "@/components/Logo";
import { Star } from "@/components/art/Art";

import styles from "./Alerts.module.css";

export type AlertKind = "scheduled" | "pattern" | "feedback";

export const ALERTS: Record<AlertKind, { title: string; body: (activity?: string) => string; actions: [string, string, string]; experimental?: boolean }> = {
  scheduled: {
    title: "Ready for a little pause?",
    body: () => "You’ve reached your planned study interval. Take a moment away from the screen.",
    actions: ["Take a break", "Snooze 5 min", "Dismiss"],
  },
  pattern: {
    title: "A quick check-in?",
    body: () => "Your recent eye closures have been longer than earlier in this session. How are you feeling?",
    actions: ["Check in", "Take a break", "Dismiss"],
    experimental: true,
  },
  feedback: {
    title: "Did that help?",
    body: (activity = "a walking break") => `You just finished ${activity}. Do you feel more alert or more comfortable?`,
    actions: ["Add feedback", "Remind me later", "Skip"],
  },
};

function AlertMark({ kind }: { kind: AlertKind }) {
  return (
    <svg width="56" height="56" viewBox="0 0 60 60" aria-hidden="true" focusable="false" className={styles.mark}>
      {kind === "scheduled" && (<>
        <path d="M8 40 A 22 22 0 0 1 52 40 Z" fill="var(--golden)" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" />
        <path d="M3 42 C 18 36, 40 47, 57 39" fill="none" stroke="var(--ink)" strokeWidth="2.8" strokeLinecap="round" />
      </>)}
      {kind === "pattern" && (<>
        <path d="M4 32 C 14 16, 42 14, 54 30 C 42 44, 16 46, 4 32 Z" fill="var(--cobalt)" />
        <circle cx="29" cy="31" r="7" fill="var(--ink)" />
        <circle cx="31.5" cy="28.5" r="2" fill="var(--paper)" />
        <Star x={50} y={9} r={5} width={2} />
      </>)}
      {kind === "feedback" && (<>
        <g transform="rotate(-18 18 38)"><ellipse cx="18" cy="40" rx="6.5" ry="11" fill="var(--ink)" /><circle cx="12.5" cy="25" r="2.2" fill="var(--ink)" /><circle cx="17" cy="23.5" r="2.2" fill="var(--ink)" /><circle cx="21.5" cy="24.5" r="2" fill="var(--ink)" /><circle cx="24.5" cy="27.5" r="1.7" fill="var(--ink)" /></g>
        <g transform="rotate(14 40 22)"><ellipse cx="40" cy="24" rx="6.5" ry="11" fill="var(--ink)" /><circle cx="34.5" cy="9" r="2.2" fill="var(--ink)" /><circle cx="39" cy="7.5" r="2.2" fill="var(--ink)" /><circle cx="43.5" cy="8.5" r="2" fill="var(--ink)" /><circle cx="46.5" cy="11.5" r="1.7" fill="var(--ink)" /></g>
        <circle cx="51" cy="48" r="4.5" fill="var(--vermilion)" />
      </>)}
    </svg>
  );
}

/** An in-app prompt: gentle, dismissible, announced politely, never steals focus. */
export function AlertBanner({ kind, activity, onAction }: { kind: AlertKind; activity?: string; onAction: (action: string) => void }) {
  const a = ALERTS[kind];
  return (
    <div className={styles.banner} role="status" aria-label={a.title}>
      <AlertMark kind={kind} />
      <div className={styles.text}>
        {a.experimental ? <span className="tag">Experimental · example of pattern-based feedback</span> : null}
        <strong className={styles.title}>{a.title}</strong>
        <span className="muted">{a.body(activity)}</span>
      </div>
      <div className={styles.actions}>
        <button type="button" className="btn btn-primary btn-small" onClick={() => onAction(a.actions[0])}>{a.actions[0]}</button>
        <button type="button" className="btn btn-secondary btn-small" onClick={() => onAction(a.actions[1])}>{a.actions[1]}</button>
        <button type="button" className="btn btn-quiet btn-small" onClick={() => onAction(a.actions[2])}>{a.actions[2]}</button>
      </div>
    </div>
  );
}

/** A picture of how macOS would show the prompt in the background — not a real notification. */
export function MacNotificationPreview({ kind }: { kind: AlertKind }) {
  const a = ALERTS[kind];
  return (
    <figure className={styles.macFigure}>
      <div className={styles.desktop} aria-hidden="true">
        <div className={styles.notification}>
          <span className={styles.appIcon}><LogoMark size={26} /></span>
          <div className={styles.notifText}>
            <div className={styles.notifTop}><b>{a.title}</b><span>now</span></div>
            <span>{a.body()}</span>
          </div>
          <span className={styles.options}>Options ⌄</span>
        </div>
      </div>
      <figcaption className="muted">
        <span className="tag">Visual preview only</span> How the desktop app’s reminder could look as a macOS notification.
        macOS draws it in its own style; nothing is sent to your system and no permission is requested.
      </figcaption>
    </figure>
  );
}

/** Home-page gallery: click to see each prompt; actions only explain what would happen. */
export function AlertGallery() {
  const [kind, setKind] = useState<AlertKind | null>("scheduled");
  const [outcome, setOutcome] = useState("");
  const show = (k: AlertKind) => { setKind(k); setOutcome(""); };
  return (
    <div className={styles.gallery}>
      <div className={styles.triggers} role="group" aria-label="Show an example prompt">
        {(Object.keys(ALERTS) as AlertKind[]).map((k) => (
          <button key={k} type="button" aria-pressed={kind === k} className={`btn btn-small ${kind === k ? "btn-primary" : "btn-secondary"}`} onClick={() => show(k)}>
            {ALERTS[k].title}
          </button>
        ))}
      </div>
      {kind ? (
        <>
          <AlertBanner kind={kind} onAction={(action) => { setOutcome(`Example only: “${action}” would ${describe(action)}.`); }} />
          <p className="muted" role="status">{outcome}</p>
          <MacNotificationPreview kind={kind} />
        </>
      ) : null}
    </div>
  );
}

function describe(action: string): string {
  switch (action) {
    case "Take a break": return "open the break picker";
    case "Snooze 5 min": return "hide this reminder for five minutes";
    case "Check in": return "ask two separate questions: sleepiness and eye comfort";
    case "Add feedback": return "ask the same two questions as before the break";
    case "Remind me later": return "ask once more a little later";
    default: return "close the prompt without recording anything";
  }
}
