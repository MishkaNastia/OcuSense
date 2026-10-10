"""Saves the raw Eye Aspect Ratio (EAR) of every processed frame to CSV files.

One row per frame while the camera is on (calibration included):

    unix_time,left_ear,right_ear,reliable,left_openness,right_openness
    1791632325.713,0.2871,0.2903,1,0.9512,0.9734
    1791632325.746,,,0,,           <- no face found: empty values, the gap stays visible

unix_time       wall-clock seconds (millisecond precision), so durations and frame
                gaps can be computed exactly
left_ear        raw EAR of each eye (not calibrated, not clipped); empty if not measured
reliable        1 if the frame passed the tracking-quality checks, 0 if not (head
                turned, face too small or too far away) — filter on it in analysis
left_openness   personal eye openness from the calibration in use:
                (EAR − closed EAR) / (open EAR − closed EAR), not clipped, so it can
                go slightly below 0 or above 1. Empty while not calibrated (for
                example during calibration) or when the frame isn't reliable.

Next to each CSV, a .calibration.json file records the calibration those openness
values used: the open and closed EAR of each eye, the blink thresholds and when the
calibration was made ("calibration": null if there was none). Every CSV belongs to
exactly one calibration: when it changes (a recalibration), a new file starts.

Rows are kept in memory and written as a new file every RECORDING_CHUNK_SECONDS,
whenever the calibration changes, and whenever monitoring pauses, stops or the app
quits. Numbers only: no images, no face landmarks.
"""

import csv
import json
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ocusense.config import RECORDING_CHUNK_SECONDS
from ocusense.core.models import CalibrationInfo

HEADER = ("unix_time", "left_ear", "right_ear", "reliable", "left_openness", "right_openness")


def default_directory() -> Path:
    """The standard place for an app's own files on a Mac (OCUSENSE_RECORDINGS_DIR overrides it, e.g. in tests)."""
    override = os.environ.get("OCUSENSE_RECORDINGS_DIR")
    return Path(override) if override else Path.home() / "Library" / "Application Support" / "OcuSense" / "recordings"


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


def calibration_record(info: CalibrationInfo | None) -> dict:
    """What goes into the .calibration.json file next to a recording."""
    if info is None:
        return {"calibration": None,
                "note": "No calibration was in use for these frames (for example while calibrating), "
                        "so the openness columns are empty."}
    values = asdict(info)
    values["calibrated_at"] = info.calibrated_at.isoformat(timespec="seconds")
    return {"calibration": values,
            "openness_formula": "(ear - closed_ear) / (open_ear - closed_ear), per eye, not clipped"}


class EarRecording:
    def __init__(self, directory: Path | None = None, chunk_seconds: float = RECORDING_CHUNK_SECONDS):
        self.directory = directory or default_directory()
        self.chunk_seconds = chunk_seconds
        self.enabled = True
        self.rows: list[tuple] = []
        self.calibration: CalibrationInfo | None = None  # the calibration of the buffered rows
        self._chunk_started: float | None = None  # time.monotonic() of the first row in the buffer
        self.files_written = 0
        self.last_file: Path | None = None
        self.last_error = ""

    def add(self, monotonic_t: float, left_ear: float | None, right_ear: float | None, reliable: bool,
            left_openness: float | None = None, right_openness: float | None = None,
            calibration: CalibrationInfo | None = None) -> None:
        """Buffer one frame. monotonic_t is the frame's time.monotonic(); it is converted to wall-clock time.

        calibration is the one that produced this frame's openness values; a different one starts a new file.
        """
        if not self.enabled:
            return
        if calibration != self.calibration:
            self.flush()  # one calibration per file
            self.calibration = calibration
        if self._chunk_started is None:
            self._chunk_started = monotonic_t
        unix_time = time.time() - (time.monotonic() - monotonic_t)
        self.rows.append((f"{unix_time:.3f}", _number(left_ear), _number(right_ear), "1" if reliable else "0",
                          _number(left_openness), _number(right_openness)))

    def due(self, now: float) -> bool:
        """True when the buffered rows span a full chunk and should be written."""
        return self._chunk_started is not None and now - self._chunk_started >= self.chunk_seconds

    def flush(self) -> Path | None:
        """Write the buffered rows to a new CSV file (plus its .calibration.json). Returns the CSV path."""
        if not self.rows:
            return None
        first = datetime.fromtimestamp(float(self.rows[0][0]))
        stem = f"ear_{first:%Y-%m-%d_%H-%M-%S}"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            for attempt in range(100):
                name = stem if attempt == 0 else f"{stem}_{attempt}"
                path = self.directory / f"{name}.csv"
                try:
                    with path.open("x", newline="") as file:  # "x": never overwrite an existing recording
                        writer = csv.writer(file)
                        writer.writerow(HEADER)
                        writer.writerows(self.rows)
                except FileExistsError:
                    continue
                written = self._written(path)  # the rows are safe now; never write them twice
                try:
                    sidecar = self.directory / f"{name}.calibration.json"
                    sidecar.write_text(json.dumps(calibration_record(self.calibration), indent=2) + "\n")
                except OSError as error:
                    self.last_error = f"Couldn’t save the calibration file for {path.name}: {error.strerror or error}"
                return written
            raise OSError("too many recordings with the same start time")
        except OSError as error:
            self.last_error = f"Couldn’t save the EAR recording: {error.strerror or error}"
            return None  # rows stay buffered and are tried again at the next save

    def _written(self, path: Path) -> Path:
        self.rows = []
        self._chunk_started = None
        self.files_written += 1
        self.last_file = path
        self.last_error = ""
        return path
