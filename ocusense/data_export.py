"""Copy the EAR recordings from a time range into a folder, and fit their blink intervals.

    .venv/bin/python -m ocusense.data_export --since 2026-10-10 --until 2026-10-11 --out data/awake
    .venv/bin/python -m ocusense.data_export --since "2026-10-10 00:00" --until "2026-10-11 12:00" --out data/awake

Times are local; --until is exclusive. Reads the app's recordings folder (or --recordings)
and never changes it. Into --out it writes:

    recordings/ear_….csv               every frame in the range (a file crossing an edge is cut there)
    recordings/ear_….calibration.json  the calibration each file was measured with, unchanged
    check_ins.csv                      the check-ins prompted in the range, if there are any
    intervals.csv                      every time between blinks: recording, onset_a, onset_b (unix s), seconds,
                                       counted (0 = the same moment is already covered by another recording)
    fit.json                           log-normal fits of those intervals: all together and per recording

The intervals come from the app's own replay (core/replay.py, the live detector's rules: onset to
onset, never across a gap, pause or recalibration). The fit is core/baseline_drift.fit_lognormal:
maximum likelihood on ln(interval), mu = mean, sigma with ddof = 0; median interval = e^mu.
A modelling choice, not a statement that the intervals ARE log-normal.

Two copies of OcuSense open at once record the same blinks twice (each with its own
calibration, in separate files). The combined fit counts every moment once: recordings are
taken in order of their start, and an interval inside the time span of an earlier recording is
kept in intervals.csv with counted = 0 but left out of the "all" fit. Per-recording fits use
all of that recording's intervals.
"""

import argparse
import csv
import json
import math
import shutil
from datetime import datetime
from pathlib import Path

from ocusense.core.baseline_drift import fit_lognormal
from ocusense.recording import default_directory
from ocusense.recording_files import calibration_path, import_recordings


def parse_time(text: str) -> float:
    """'2026-10-10' or '2026-10-10 14:30' (local time) → unix seconds."""
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).timestamp()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Use a date like 2026-10-10 or 2026-10-10 14:30, not {text!r}")


def copy_range(source: Path, target: Path, since: float, until: float) -> list[dict]:
    """Copy the frames with since <= unix_time < until; returns one summary per file written."""
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for csv_path in sorted(source.glob("ear_*.csv")):
        with csv_path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            rows = [r for r in reader if _in_range(r.get("unix_time"), since, until)]
        if not rows:
            continue
        with (target / csv_path.name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        calibration = calibration_path(csv_path)
        if calibration.exists():
            shutil.copy2(calibration, target / calibration.name)
        times = [float(r["unix_time"]) for r in rows]
        written.append({"file": csv_path.name, "frames": len(rows), "first": min(times), "last": max(times),
                        "cut": len(rows) < _count_rows(csv_path), "calibration": calibration.exists()})
    return written


def _in_range(value, since: float, until: float) -> bool:
    try:
        return since <= float(value) < until
    except (TypeError, ValueError):
        return False


def _count_rows(path: Path) -> int:
    with path.open(newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def copy_check_ins(source: Path, target: Path, since: float, until: float) -> int:
    path = source / "check_ins" / "labels.csv"
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = [r for r in reader if _in_range(r.get("prompted_unix_time"), since, until)]
        fields = reader.fieldnames or []
    if rows:
        with (target / "check_ins.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return len(rows)


def _fit_dict(intervals) -> dict:
    fit = fit_lognormal(intervals)
    if fit is None:
        return {"n": len(intervals), "fit": None}
    mu, sigma, n = fit
    return {"n": n, "mu_log_seconds": mu, "sigma_log_seconds": sigma, "median_seconds": math.exp(mu),
            "mean_seconds": math.exp(mu + sigma * sigma / 2),
            "blinks_per_minute_at_median": 60 / math.exp(mu)}


def fit_folder(folder: Path) -> dict:
    """Replay the copied recordings with their own calibrations, write intervals.csv, return the fits."""
    result = import_recordings(sorted((folder / "recordings").glob("ear_*.csv")))
    everything, per_recording, covered, duplicates = [], [], [], 0
    with (folder / "intervals.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["recording", "onset_a_unix", "onset_b_unix", "interval_seconds", "counted"])
        for recording in sorted(result.recordings, key=lambda r: r.files[0].first):
            replayed = recording.replay_result
            name = recording.files[0].csv_path.name
            intervals = []
            for a, b in replayed.distributions.intervals:
                a, b = a + replayed.start_unix, b + replayed.start_unix
                counted = not any(lo <= a <= hi or lo <= b <= hi for lo, hi in covered)
                writer.writerow([name, f"{a:.3f}", f"{b:.3f}", f"{b - a:.3f}", int(counted)])
                intervals.append(b - a)
                if counted:
                    everything.append(b - a)
                else:
                    duplicates += 1
            covered.append((recording.files[0].first, recording.files[-1].last))
            per_recording.append({"recording": name, "files": [f.csv_path.name for f in recording.files],
                                  "started": recording.started.isoformat(timespec="seconds"),
                                  "minutes": round(recording.seconds / 60, 1),
                                  "valid_frames": replayed.valid_frames, "frames": replayed.frames,
                                  "blinks": replayed.distributions.blinks, **_fit_dict(intervals)})
    return {"all": _fit_dict(everything), "duplicate_intervals_left_out": duplicates, "recordings": per_recording,
            "not_analysed": [{"file": name, "reason": reason} for name, reason in result.excluded]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", type=parse_time, required=True, help="local start, e.g. 2026-10-10")
    parser.add_argument("--until", type=parse_time, required=True, help="local end (exclusive), e.g. 2026-10-11")
    parser.add_argument("--out", type=Path, required=True, help="folder to write, e.g. data/awake")
    parser.add_argument("--recordings", type=Path, default=None, help="where the app saved them (default: its folder)")
    args = parser.parse_args(argv)
    if args.until <= args.since:
        parser.error("--until must be after --since")
    source = args.recordings or default_directory()
    if args.out.resolve() == source.resolve() or source.resolve() in args.out.resolve().parents:
        parser.error("--out must be outside the recordings folder")

    files = copy_range(source, args.out / "recordings", args.since, args.until)
    check_ins = copy_check_ins(source, args.out, args.since, args.until)
    fits = fit_folder(args.out)
    summary = {"since": datetime.fromtimestamp(args.since).isoformat(timespec="minutes"),
               "until": datetime.fromtimestamp(args.until).isoformat(timespec="minutes"),
               "source": str(source), "files": files, "check_ins": check_ins, **fits}
    (args.out / "fit.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"{len(files)} recording files ({sum(f['frames'] for f in files)} frames) and {check_ins} check-ins "
          f"from {summary['since']} to {summary['until']} → {args.out}")
    if fits["duplicate_intervals_left_out"]:
        print(f"  {fits['duplicate_intervals_left_out']} intervals were recorded twice (two copies of OcuSense open at "
              "once): counted once in the fit")
    for item in fits["not_analysed"]:
        print(f"  not analysed: {item['file']} — {item['reason']}")
    a = fits["all"]
    if a.get("fit", True) is None:
        print(f"Too few blink intervals to fit ({a['n']}).")
    else:
        print(f"Log-normal fit of {a['n']} blink intervals: mu = {a['mu_log_seconds']:.3f}, "
              f"sigma = {a['sigma_log_seconds']:.3f} (ln seconds) · median {a['median_seconds']:.2f} s · "
              f"mean {a['mean_seconds']:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
