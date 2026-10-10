"""Reading saved EAR recordings (ear_*.csv + ear_*.calibration.json) for analysis. Read-only.

A *recording* here is one or more files that belong together: consecutive files
are joined only when (1) both carry exactly the same calibration and thresholds
and (2) the next file starts within MAX_FRAME_GAP of the previous one's last
frame — i.e. the app rotated to a new file while the camera kept running.
Anything else (a pause, a stop, a recalibration, another day) stays separate.
Files don't name their session, so nothing is joined on file names alone.

Files whose calibration is null (the calibration frames themselves) are not
analysed: without a calibration there is no personal openness and no blink
detection. They are listed as excluded, with that reason.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ocusense.config import MAX_FRAME_GAP
from ocusense.core.replay import RecordedCalibration, Replay, Row, replay

REQUIRED_COLUMNS = ("unix_time", "left_ear", "right_ear", "reliable")


class RecordingError(Exception):
    """A file can't be used; the message says why."""


def _float(text: str) -> float | None:
    return float(text) if text not in ("", None) else None


def calibration_path(csv_path: Path) -> Path:
    return csv_path.with_name(csv_path.stem + ".calibration.json")


@dataclass
class RecordingFile:
    csv_path: Path
    calibration: RecordedCalibration | None
    rows: list  # [Row]

    @property
    def first(self) -> float:
        return self.rows[0].t

    @property
    def last(self) -> float:
        return self.rows[-1].t


def read_file(csv_path: Path) -> RecordingFile:
    """Read one CSV and its calibration file. Raises RecordingError when they can't be used."""
    csv_path = Path(csv_path)
    json_path = calibration_path(csv_path)
    if not json_path.exists():
        raise RecordingError(f"{csv_path.name}: no matching {json_path.name}, so its calibration is unknown.")
    try:
        record = json.loads(json_path.read_text())
    except (OSError, ValueError) as error:
        raise RecordingError(f"{json_path.name} can’t be read: {error}") from error
    values = record.get("calibration")
    try:
        calibration = RecordedCalibration.from_json(values) if values is not None else None
    except (KeyError, TypeError) as error:
        raise RecordingError(f"{json_path.name} is missing calibration field {error}.") from error

    rows = []
    try:
        with csv_path.open(newline="") as file:
            reader = csv.DictReader(file)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise RecordingError(f"{csv_path.name} has no column {', '.join(missing)}.")
            for line in reader:
                rows.append(Row(
                    t=float(line["unix_time"]), left_ear=_float(line["left_ear"]), right_ear=_float(line["right_ear"]),
                    reliable=line["reliable"] == "1",
                    left_openness=_float(line.get("left_openness", "")),
                    right_openness=_float(line.get("right_openness", "")),
                ))
    except (OSError, ValueError) as error:
        raise RecordingError(f"{csv_path.name} can’t be read: {error}") from error
    if not rows:
        raise RecordingError(f"{csv_path.name} contains no frames.")
    return RecordingFile(csv_path, calibration, rows)


@dataclass
class Recording:
    files: list  # [RecordingFile], in time order, one calibration
    replay_result: Replay | None = None

    @property
    def calibration(self) -> RecordedCalibration:
        return self.files[0].calibration

    @property
    def rows(self) -> list:
        return [row for f in self.files for row in f.rows]

    @property
    def started(self) -> datetime:
        return datetime.fromtimestamp(self.files[0].first)

    @property
    def seconds(self) -> float:
        return self.files[-1].last - self.files[0].first

    def label(self) -> str:
        minutes, seconds = divmod(round(self.seconds), 60)
        length = f"{minutes} min {seconds} s" if minutes else f"{seconds} s"
        parts = f" · {len(self.files)} files" if len(self.files) > 1 else ""
        return f"{self.started:%a %d %b %Y, %H:%M:%S} · {length}{parts}"


@dataclass
class ImportResult:
    recordings: list = field(default_factory=list)  # [Recording], analysed
    excluded: list = field(default_factory=list)  # [(file name, reason)]


def group(files: list[RecordingFile]) -> list[Recording]:
    """Join files only when calibration matches and timestamps continue without a gap."""
    recordings: list[Recording] = []
    for f in sorted(files, key=lambda f: f.first):
        last = recordings[-1] if recordings else None
        if (last is not None and last.calibration == f.calibration
                and 0 <= f.first - last.files[-1].last <= MAX_FRAME_GAP):
            last.files.append(f)
        else:
            recordings.append(Recording([f]))
    return recordings


def import_recordings(paths: list[Path]) -> ImportResult:
    """Read, check, group and analyse the chosen CSV files. Slow for long recordings: run off the UI thread."""
    result = ImportResult()
    usable = []
    for path in sorted(set(Path(p) for p in paths)):
        try:
            f = read_file(path)
        except RecordingError as error:
            result.excluded.append((Path(path).name, str(error)))
            continue
        if f.calibration is None:
            result.excluded.append((f.csv_path.name, "Calibration frames only (calibration: null): without a "
                                                     "calibration there is no personal openness or blink detection."))
            continue
        usable.append(f)
    for recording in group(usable):
        recording.replay_result = replay(recording.rows, recording.calibration)
        result.recordings.append(recording)
    return result
