"""Make the saved reference for blink timing from a recording's first 10 minutes. Recordings are only read.

Usage (from the repo root):
    .venv/bin/python analysis/set_reference.py                         # list the recordings
    .venv/bin/python analysis/set_reference.py "2026-10-10 21:26:24"    # by start time
    .venv/bin/python analysis/set_reference.py ear_2026-10-10_21-26-24.csv
    ... --replace     replace an existing reference
    ... --folder F    read recordings from F instead of the default folder

The reference is written where the app reads it (ocusense.reference.default_path()):
the same definition as when the app saves a session's first 10 minutes itself.
"""

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run from anywhere

from ocusense import reference as reference_file  # noqa: E402
from ocusense.core.baseline_drift import BASELINE_SECONDS  # noqa: E402
from ocusense.core.replay import replay  # noqa: E402
from ocusense.recording import default_directory  # noqa: E402
from ocusense.recording_files import RecordingError, group, read_file  # noqa: E402


def recordings(folder: Path):
    files = []
    for path in sorted(folder.glob("ear_*.csv")):
        try:
            f = read_file(path)
        except RecordingError:
            continue
        if f.calibration is not None:
            files.append(f)
    return group(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", help="start time (YYYY-MM-DD HH:MM:SS) or a CSV file name in it")
    parser.add_argument("--replace", action="store_true", help="replace an existing reference")
    parser.add_argument("--folder", type=Path, default=default_directory())
    args = parser.parse_args()

    found = recordings(args.folder)
    if not args.recording:
        for r in found:
            print(f"{r.started:%Y-%m-%d %H:%M:%S}  {r.label()}  (first file {r.files[0].csv_path.name})")
        return 0
    matches = [r for r in found if f"{r.started:%Y-%m-%d %H:%M:%S}" == args.recording
               or any(f.csv_path.name == args.recording for f in r.files)]
    if not matches:
        print(f"No calibrated recording matches {args.recording!r}. Run without arguments to list them.")
        return 1
    recording = matches[0]
    if recording.seconds < BASELINE_SECONDS:
        print(f"{recording.label()} is shorter than {BASELINE_SECONDS / 60:.0f} minutes.")
        return 1

    path = reference_file.default_path()
    try:
        existing = reference_file.load(path)
    except reference_file.ReferenceFileError as error:
        existing = error
    if existing is not None and not args.replace:
        print(f"A reference already exists ({path}). Use --replace to replace it.")
        return 1

    result = replay(recording.rows, recording.calibration)
    pairs = [(a, b) for a, b in result.distributions.intervals if a < BASELINE_SECONDS and b < BASELINE_SECONDS]
    new = reference_file.from_pairs(pairs, recording.started, ", ".join(f.csv_path.name for f in recording.files),
                                    asdict(recording.calibration))
    if new is None:
        print(f"Only {len(pairs)} intervals in the first 10 minutes; at least "
              f"{reference_file.MIN_REFERENCE_INTERVALS} are needed.")
        return 1
    reference_file.save(new, path)
    print(f"Saved {path}")
    print(f"Reference: {recording.label()}")
    print(f"n = {new.n}, mu = {new.mu:.4f}, sigma = {new.sigma:.4f} (MLE), median {new.median:.2f} s between blinks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
