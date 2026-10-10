"""Show what's in the saved EAR recordings: per file, then per joined recording. Read-only.

Usage (from the repo root):
    .venv/bin/python analysis/check_recordings.py [folder]

The folder defaults to ~/Library/Application Support/OcuSense/recordings/.
Files are read with ocusense.recording_files.read_file and joined with group(),
exactly as Statistics › All time › Import recording… does.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run from anywhere

from ocusense.recording import default_directory  # noqa: E402
from ocusense.recording_files import RecordingError, group, read_file  # noqa: E402

BASELINE_SECONDS = 600.0
COLUMNS = ("left_ear", "right_ear", "left_openness", "right_openness")


def duration(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes} min {seconds:02d} s"


def header(path: Path) -> list[str]:
    with path.open(newline="") as file:
        return next(csv.reader(file), [])


def main(folder: Path) -> None:
    paths = sorted(folder.glob("ear_*.csv"))
    print(f"Folder: {folder}")
    print(f"{len(paths)} CSV file(s)\n")
    if not paths:
        return

    files, calibrated = [], []
    print(f"{'file':<32} {'rows':>7} {'duration':>12} {'reliable':>9}  "
          f"{'L_ear R_ear L_open R_open':<26} calibration")
    for path in paths:
        try:
            f = read_file(path)
        except RecordingError as error:
            print(f"{path.name:<32} EXCLUDED: {error}")
            continue
        files.append(f)
        columns = header(path)
        present = "  ".join(f"{'yes' if c in columns else 'NO':>5}" for c in COLUMNS)
        reliable = sum(r.reliable for r in f.rows) / len(f.rows) * 100
        if f.calibration is None:
            kind = "calibration-only (null)"
        else:
            kind = f"yes ({f.calibration.calibrated_at})"
            calibrated.append(f)
        print(f"{path.name:<32} {len(f.rows):>7} {duration(f.last - f.first):>12} {reliable:>8.1f}%  "
              f"{present:<26} {kind}")

    # Like import_recordings: calibration-only files can't be replayed, so they aren't grouped.
    recordings = group(calibrated)
    print(f"\n{len(recordings)} joined recording(s) (calibrated files only; "
          f"{len(files) - len(calibrated)} calibration-only file(s) left out)\n")
    print(f"{'#':>2}  {'start':<20} {'duration':>12} {'files':>5}  ≥ 10 min")
    first_baseline = None
    for i, r in enumerate(recordings, 1):
        long_enough = r.seconds >= BASELINE_SECONDS
        if long_enough and first_baseline is None:
            first_baseline = i
        print(f"{i:>2}  {r.started:%Y-%m-%d %H:%M:%S}  {duration(r.seconds):>12} {len(r.files):>5}  "
              f"{'yes' if long_enough else 'no'}")
    print()
    if first_baseline is None:
        print("No joined recording is at least 10 minutes long: no baseline available.")
    else:
        r = recordings[first_baseline - 1]
        print(f"Baseline candidate (earliest ≥ 10 min): #{first_baseline}, started {r.started:%Y-%m-%d %H:%M:%S}, "
              f"files {', '.join(f.csv_path.name for f in r.files)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else default_directory())
