"use client";

import { useState } from "react";

import { LogoMark } from "@/components/Logo";
import { Star } from "@/components/art/Art";

import styles from "./Alerts.module.css";

export type AlertKind = "close" | "slower" | "focus";

/** The same reminders the desktop app shows (ocusense/ui/main_window.py). */
export const ALERTS: Record<AlertKind, { title: string; body: () => string; actions: string[] }> = {
  close: {
    title: "Trying to lick the screen?",
    body: () => "Go easy on your eyes and move back a little.",
    actions: ["Got it", "Reminder settings"],
  },
  slower: {
    title: "Time for a break",
    body: () => "Hey, you should take a break, else your eyes will become drier than the Sahara desert.",
    actions: ["Got it"],
  },
  focus: {
    title: "Focus round done, nice work!",
    body: () => "Short break time. Look out of a window: your eyes have been staring at pixels for a while.",
    actions: ["Got it"],
  },
};

function AlertMark({ kind }: { kind: AlertKind }) {
  return (
    <svg width="56" height="56" viewBox="0 0 60 60" aria-hidden="true" focusable="false" className={styles.mark}>
      {kind === "slower" && (<>
        <path d="M8 40 A 22 22 0 0 1 52 40 Z" fill="var(--golden)" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" />
        <path d="M3 42 C 18 36, 40 47, 57 39" fill="none" stroke="var(--ink)" strokeWidth="2.8" strokeLinecap="round" />
      </>)}
      {kind === "close" && (<>
        <path d="M4 32 C 14 16, 42 14, 54 30 C 42 44, 16 46, 4 32 Z" fill="var(--cobalt)" />
        <circle cx="29" cy="31" r="7" fill="var(--ink)" />
        <circle cx="31.5" cy="28.5" r="2" fill="var(--paper)" />
        <Star x={50} y={9} r={5} width={2} />
      </>)}
      {kind === "focus" && (<>
        <circle cx="30" cy="34" r="19" fill="var(--vermilion)" stroke="var(--ink)" strokeWidth="2" />
        <path d="M30 15 C 26 8, 20 8, 17 11 M30 15 C 34 8, 40 8, 43 11" fill="none" stroke="var(--green, #2e7a4d)" strokeWidth="3" strokeLinecap="round" />
        <path d="M30 24 V 34 L 37 38" fill="none" stroke="var(--paper)" strokeWidth="2.6" strokeLinecap="round" />
      </>)}
    </svg>
  );
}

/** An in-app prompt: gentle, dismissible, announced politely, never steals focus. */
export function AlertBanner({ kind, onAction }: { kind: AlertKind; onAction: (action: string) => void }) {
  const a = ALERTS[kind];
  return (
    <div className={styles.banner} role="status" aria-label={a.title}>
      <AlertMark kind={kind} />
      <div className={styles.text}>
        <strong className={styles.title}>{a.title}</strong>
        <span className="muted">{a.body()}</span>
      </div>
      <div className={styles.actions}>
        {a.actions.map((action, i) => (
          <button key={action} type="button" className={`btn btn-small ${i === 0 ? "btn-primary" : "btn-secondary"}`}
            onClick={() => onAction(action)}>{action}</button>
        ))}
      </div>
    </div>
  );
}

/** A picture of how macOS shows the reminder when OcuSense is in the background (not a real notification). */
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
        <span className="tag">Visual preview only</span> How the desktop app shows this reminder as a macOS notification when you’re in another app.
        macOS draws it in its own style; nothing is sent to your system and no permission is requested.
      </figcaption>
    </figure>
  );
}

/** Home-page gallery: click to see each prompt; actions only explain what would happen. */
export function AlertGallery() {
  const [kind, setKind] = useState<AlertKind | null>("close");
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
    case "Got it": return "close the reminder";
    case "Reminder settings": return "open Settings, where you choose how often it may remind you, or switch it off";
    default: return "close the reminder";
  }
}
