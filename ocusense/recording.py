"""Saves the raw Eye Aspect Ratio (EAR) of every processed frame to CSV files.

One row per frame while the camera is on (calibration included):

    unix_time,left_ear,right_ear,reliable
    1791632325.713,0.2871,0.2903,1
    1791632325.746,,,0          <- no face found: empty EAR, the gap stays visible

unix_time  wall-clock seconds (millisecond precision), so durations and frame
           gaps can be computed exactly
left_ear   raw EAR of each eye (not calibrated, not clipped); empty if not measured
reliable   1 if the frame passed the tracking-quality checks, 0 if not (head
           turned, face too small or too far away) — filter on it in analysis

Rows are kept in memory and written as a new file every RECORDING_CHUNK_SECONDS,
and whenever monitoring pauses, stops or the app quits. Numbers only: no images,
no face landmarks.
"""

import csv
import os
import time
from datetime import datetime
from pathlib import Path

from ocusense.config import RECORDING_CHUNK_SECONDS

HEADER = ("unix_time", "left_ear", "right_ear", "reliable")


def default_directory() -> Path:
    """The standard place for an app's own files on a Mac (OCUSENSE_RECORDINGS_DIR overrides it, e.g. in tests)."""
    override = os.environ.get("OCUSENSE_RECORDINGS_DIR")
    return Path(override) if override else Path.home() / "Library" / "Application Support" / "OcuSense" / "recordings"


def _ear(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


class EarRecording:
    def __init__(self, directory: Path | None = None, chunk_seconds: float = RECORDING_CHUNK_SECONDS):
        self.directory = directory or default_directory()
        self.chunk_seconds = chunk_seconds
        self.enabled = True
        self.rows: list[tuple] = []
        self._chunk_started: float | None = None  # time.monotonic() of the first row in the buffer
        self.files_written = 0
        self.last_file: Path | None = None
        self.last_error = ""

    def add(self, monotonic_t: float, left_ear: float | None, right_ear: float | None, reliable: bool) -> None:
        """Buffer one frame. monotonic_t is the frame's time.monotonic(); it is converted to wall-clock time."""
        if not self.enabled:
            return
        if self._chunk_started is None:
            self._chunk_started = monotonic_t
        unix_time = time.time() - (time.monotonic() - monotonic_t)
        self.rows.append((f"{unix_time:.3f}", _ear(left_ear), _ear(right_ear), "1" if reliable else "0"))

    def due(self, now: float) -> bool:
        """True when the buffered rows span a full chunk and should be written."""
        return self._chunk_started is not None and now - self._chunk_started >= self.chunk_seconds

    def flush(self) -> Path | None:
        """Write the buffered rows to a new CSV file. Returns its path, or None if nothing was written."""
        if not self.rows:
            return None
        first = datetime.fromtimestamp(float(self.rows[0][0]))
        stem = f"ear_{first:%Y-%m-%d_%H-%M-%S}"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            for attempt in range(100):
                path = self.directory / (f"{stem}.csv" if attempt == 0 else f"{stem}_{attempt}.csv")
                try:
                    with path.open("x", newline="") as file:  # "x": never overwrite an existing recording
                        writer = csv.writer(file)
                        writer.writerow(HEADER)
                        writer.writerows(self.rows)
                    return self._written(path)
                except FileExistsError:
                    continue
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
