import { combinedOpennessPercent, type RollingSnapshot } from "@/lib/measurement/measurements";
import * as fmt from "@/lib/measurement/format";
import { MIN_VALID_SECONDS_FOR_RATE } from "@/lib/measurement/config";

import styles from "./MeasurementPanel.module.css";

/**
 * Live personal eye openness + the "last 60 seconds" measurements.
 * `source` makes it impossible to mistake simulated numbers for real ones.
 */
export function MeasurementPanel({ snapshot, opennessRaw, source }: {
  snapshot: RollingSnapshot | null;
  opennessRaw: [number, number] | null;
  source: "sample" | "camera";
}) {
  const openness = opennessRaw ? combinedOpennessPercent(opennessRaw[0], opennessRaw[1]) : null;
  const enough = snapshot?.enoughData ?? false;
  const coverage = snapshot?.coverage ?? null;
  return (
    <section className={styles.panel} aria-label={source === "sample" ? "Simulated measurements" : "Measurements from your camera"}>
      <div className={styles.live}>
        <div className={styles.liveHead}>
          <h3>Personal eye openness</h3>
          <span className={source === "sample" ? "tag" : "tag tag-solid"}>{source === "sample" ? "Simulated" : "Live · your camera"}</span>
        </div>
        <p className={`${styles.big} mono`} aria-live="off">{fmt.percent(openness)}</p>
        <p className={styles.explain}>Relative to {source === "sample" ? "the simulated person’s" : "your"} calibrated open and closed positions. Not a fatigue score and not an anatomical percentage.</p>
      </div>
      <div className={styles.window}>
        <div className={styles.windowHead}>
          <h3>Last 60 seconds</h3>
          <span className="muted">
            {snapshot ? <>Valid observation {fmt.duration(snapshot.validSeconds)} of {fmt.duration(snapshot.runningSeconds)} · coverage {fmt.percent(coverage === null ? null : coverage * 100)}</> : "Not started"}
          </span>
        </div>
        <dl className={styles.stats}>
          <div>
            <dt>Blink rate</dt>
            <dd className="mono">{fmt.blinkRate(snapshot?.blinkRate ?? null, enough)}</dd>
            <p>Completed blinks per minute of valid observation.</p>
          </div>
          <div>
            <dt>Median closure duration</dt>
            <dd className="mono">{fmt.closureMs(snapshot?.medianClosure ?? null)}</dd>
            <p>Time from closing to reopening, measured at the two thresholds (not the whole blink movement).</p>
          </div>
          <div>
            <dt>Time classified as closed</dt>
            <dd className="mono">{fmt.closedPercent(snapshot?.closedPercent ?? null, enough)}</dd>
            <p>Share of valid observation in the detector’s closed state.</p>
          </div>
        </dl>
        <p className={styles.note}>
          Blink rate and closed time appear after {MIN_VALID_SECONDS_FOR_RATE} s of valid observation (an engineering choice).
          {snapshot?.processingRate ? ` Durations are timed between frames (${Math.round(snapshot.processingRate)} per second), so they are accurate to about ±${Math.round(1000 / snapshot.processingRate)} ms.` : ""}
        </p>
      </div>
    </section>
  );
}
