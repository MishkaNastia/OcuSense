import { CLOSE_BELOW, GRAPH_SECONDS, MAX_FRAME_GAP, REOPEN_ABOVE } from "@/lib/measurement/config";
import type { GraphSample } from "@/lib/measurement/monitor";

import styles from "./OpennessGraph.module.css";

const W = 600;
const H = 200;

/**
 * Live graph of both-eyes personal eye openness (0–100 %) over the last seconds.
 * Exact data only: straight lines between real samples, gaps where measurement was
 * missing, a dot at the lowest point of each counted blink.
 */
export function OpennessGraph({ samples, now, dimmed = false, message, label }: {
  samples: readonly GraphSample[];
  now: number;
  dimmed?: boolean;
  message?: string;
  label: string;
}) {
  const x = (t: number) => W * (1 - (now - t) / GRAPH_SECONDS);
  const y = (v: number) => H - v * H;
  let path = "";
  let penDown = false;
  let lastT: number | null = null;
  let dip: { x: number; y: number; v: number } | null = null;
  const blinks: { x: number; y: number }[] = [];
  for (const s of samples) {
    if (s.openness === null || (lastT !== null && s.t - lastT > MAX_FRAME_GAP)) penDown = false;
    if (s.openness !== null) {
      const px = x(s.t);
      const py = y(s.openness);
      path += `${penDown ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)} `;
      penDown = true;
      if (!dip || s.openness < dip.v) dip = { x: px, y: py, v: s.openness };
    } else {
      dip = null;
    }
    if (s.blinked && dip) {
      blinks.push(dip);
      dip = null;
    }
    lastT = s.t;
  }
  return (
    <figure className={styles.figure} aria-label={label}>
      <div className={styles.row}>
        <div className={styles.yAxis} aria-hidden="true"><span>100%</span><span>0%</span></div>
        <div className={styles.plot}>
          <svg viewBox={`0 0 ${W} ${H}`} className={styles.svg} role="img" aria-label={label}>
            <line x1="0" x2={W} y1={y(REOPEN_ABOVE)} y2={y(REOPEN_ABOVE)} className={styles.threshold} />
            <line x1="0" x2={W} y1={y(CLOSE_BELOW)} y2={y(CLOSE_BELOW)} className={styles.threshold} />
            <g opacity={dimmed ? 0.35 : 1}>
              <path d={path} className={styles.line} />
              {blinks.map((b, i) => <circle key={i} cx={b.x} cy={b.y} r={6} className={styles.blink} />)}
            </g>
          </svg>
          {message ? <p className={styles.message}>{message}</p> : null}
        </div>
        <div className={styles.thresholdLabels} aria-hidden="true">
          <span style={{ top: `${(1 - REOPEN_ABOVE) * 100}%` }}>reopens · {Math.round(REOPEN_ABOVE * 100)}%</span>
          <span style={{ top: `${(1 - CLOSE_BELOW) * 100}%` }}>closes · {Math.round(CLOSE_BELOW * 100)}%</span>
        </div>
      </div>
      <div className={styles.xAxis} aria-hidden="true"><span>−{GRAPH_SECONDS} s</span><span>−{GRAPH_SECONDS / 2} s</span><span>now</span></div>
      <figcaption className={styles.legend}>
        <span><i className={styles.keyLine} />Both eyes</span>
        <span><i className={styles.keyDash} />Detector thresholds</span>
        <span><i className={styles.keyDot} />Blink counted</span>
      </figcaption>
    </figure>
  );
}
