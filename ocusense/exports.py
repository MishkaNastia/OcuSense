"""Export derived blink-distribution results (never the recordings themselves).

Everything goes into a NEW folder inside the folder the person chooses:
  blink_events.csv       one row per completed closure event
  windows.csv            one row per 60 s window, with eligibility
  summary.csv            counts, medians and quartiles
  analysis_settings.json definitions, bins, thresholds, calibration, sources, exclusions
  histogram.png          the chart on screen (written by the interface)
No camera images, no face landmarks, no per-frame data.
"""

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ocusense.config import MAX_FRAME_GAP, MIN_VALID_SECONDS_FOR_RATE
from ocusense.core.distributions import BINNINGS, WINDOW_SECONDS, Distributions, quartiles

DEFINITIONS = {
    "closure_duration": "Detector closing → reopening thresholds (bilateral, mean of clipped per-eye openness); "
                        "not the full blink movement. Interrupted events are excluded and counted.",
    "time_between_blinks": "Onset-to-onset time of consecutive completed events within one valid segment.",
    "frequency_per_blink": "60 / time between blinks, for every interval above (blinks per minute, one value "
                           "per pair of consecutive blinks). Per second = 1 / time between blinks.",
    "blink_rate": f"Completed blinks / valid minutes in non-overlapping {WINDOW_SECONDS:.0f} s windows; eligible "
                  f"with at least {MIN_VALID_SECONDS_FOR_RATE:.0f} s of valid observation. Per second = per minute / 60.",
    "personal_openness": "Share of valid observed time per bin, weighted by the time to the next valid frame; "
                         "unclipped (below 0 % and above 100 % kept).",
    "valid_observation": f"Reliable frames with both eyes measured; gaps longer than {MAX_FRAME_GAP} s are unobserved.",
}


def _stats_rows(name: str, unit: str, values: list[float]) -> list[list]:
    q = quartiles(values)
    return [[f"{name} count", len(values), ""],
            [f"{name} median", round(q[1], 3) if q else "", unit],
            [f"{name} Q1", round(q[0], 3) if q else "", unit],
            [f"{name} Q3", round(q[2], 3) if q else "", unit]]


def export_analysis(folder: Path, title: str, d: Distributions, context: dict) -> Path:
    """Write the derived files into a new subfolder of `folder` and return it.

    context: source description, calibration identifiers, exclusions (JSON-serialisable).
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = Path(folder) / f"OcuSense analysis {stamp}"
    target.mkdir(parents=True, exist_ok=False)

    with (target / "blink_events.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["event", "onset_s", "end_s", "closure_ms", "segment"])
        for i, e in enumerate(d.events, 1):
            writer.writerow([i, f"{e.onset - d.start:.3f}", f"{e.end - d.start:.3f}", f"{e.duration * 1000:.0f}", e.segment])

    with (target / "windows.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["window", "start_s", "end_s", "valid_s", "blinks", "eligible", "rate_per_min", "rate_per_s",
                         "status"])
        for i, w in enumerate(d.windows, 1):
            status = ("in progress" if not w.complete else "eligible" if w.eligible
                      else f"excluded: under {MIN_VALID_SECONDS_FOR_RATE:.0f} s valid")
            writer.writerow([i, f"{w.start - d.start:.1f}", f"{w.end - d.start:.1f}", f"{w.valid_seconds:.2f}",
                             w.blinks, int(w.eligible), f"{w.rate:.2f}" if w.rate is not None else "",
                             f"{w.rate / 60:.4f}" if w.rate is not None else "", status])

    rows = [["valid observation", round(d.valid_seconds, 2), "s"], ["valid segments", d.segments, ""],
            ["blinks counted", d.blinks, ""], ["completed closure events", len(d.events), ""],
            ["interrupted events (excluded)", d.interrupted, ""],
            ["eligible windows", len(d.eligible_rates()), ""], ["excluded windows", d.excluded_windows(), ""]]
    rows += _stats_rows("closure duration", "ms", d.closure_ms())
    rows += _stats_rows("time between blinks", "s", d.interval_seconds())
    rows += _stats_rows("frequency per blink", "blinks/min", d.frequency_per_blink())
    rows += _stats_rows("frequency per blink", "blinks/s", [v / 60 for v in d.frequency_per_blink()])
    rows += _stats_rows("blink rate (eligible windows)", "blinks/min", d.eligible_rates())
    rows += _stats_rows("blink rate (eligible windows)", "blinks/s", [v / 60 for v in d.eligible_rates()])
    if d.openness.total:
        for eye in ("left", "right", "both"):
            shares = d.openness.shares(eye)
            rows.append([f"openness {eye}: time below 0 %", round(shares[0], 2), "% of valid time"])
            rows.append([f"openness {eye}: time at or above 100 %", round(shares[-1], 2), "% of valid time"])
    with (target / "summary.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["measure", "value", "unit"])
        writer.writerows(rows)

    settings = {
        "title": title,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "definitions": DEFINITIONS,
        "bins": {key: {**asdict(b), "edges": b.edges} for key, b in BINNINGS.items()},
        "max_frame_gap_s": MAX_FRAME_GAP,
        "window_s": WINDOW_SECONDS,
        "min_valid_s_per_window": MIN_VALID_SECONDS_FOR_RATE,
        **context,
    }
    (target / "analysis_settings.json").write_text(json.dumps(settings, indent=2, default=str) + "\n")
    return target
