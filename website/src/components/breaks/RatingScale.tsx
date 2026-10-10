"use client";

import styles from "./Breaks.module.css";

/** A labelled 1–5 self-report scale. Pressing the selected value again clears it (answers are optional). */
export function RatingScale({ question, labels, value, onChange }: {
  question: string;
  labels: string[];
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <fieldset className={styles.scale}>
      <legend>{question}</legend>
      <div className={styles.scaleButtons}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={styles.scaleButton}
            aria-pressed={value === n}
            aria-label={`${n}, ${labels[n - 1]}`}
            onClick={() => onChange(value === n ? null : n)}
          >
            {n}
          </button>
        ))}
      </div>
      <div className={styles.anchors} aria-hidden="true"><span>{labels[0]}</span><span>{labels[4]}</span></div>
      <p className={styles.selected}>{value ? `${value} · ${labels[value - 1]}` : "Not answered (optional)"}</p>
    </fieldset>
  );
}
