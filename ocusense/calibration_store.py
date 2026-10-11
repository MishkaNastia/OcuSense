"""The saved personal calibration: made once, reused every time OcuSense opens.

One person per Mac user account: the file lives in that account's Application
Support folder. It holds only numbers — the open and closed EAR of each eye, the
reference face size (distance reminder), when it was made and the measurement
version — never images.

    <OcuSense data folder>/calibration.json   (see ocusense/system.py)

A file that can't be read, doesn't pass the calibration's own checks, or was made
with a different measurement version is ignored (load() returns None), so the app
simply calibrates again. Recalibrating replaces the file only when it succeeds.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ocusense.config import MEASUREMENT_VERSION
from ocusense.core.calibration import EyeReference, PersonalCalibration
from ocusense.core.models import CalibrationInfo
from ocusense.system import user_data_dir


def default_path() -> Path:
    """OCUSENSE_CALIBRATION_FILE overrides it (e.g. in tests)."""
    override = os.environ.get("OCUSENSE_CALIBRATION_FILE")
    return Path(override) if override else user_data_dir() / "calibration.json"


@dataclass(frozen=True)
class SavedCalibration:
    calibration: PersonalCalibration
    calibrated_at: datetime
    measurement_version: str


class CalibrationStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.last_error = ""

    def save(self, calibration: PersonalCalibration, info: CalibrationInfo) -> bool:
        record = {
            "calibrated_at": info.calibrated_at.isoformat(timespec="seconds"),
            "measurement_version": info.measurement_version,
            "left_open_ear": calibration.left.open_ear, "left_closed_ear": calibration.left.closed_ear,
            "right_open_ear": calibration.right.open_ear, "right_closed_ear": calibration.right.closed_ear,
            "reference_face_scale": calibration.face_scale,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2) + "\n")
            temporary.replace(self.path)  # all or nothing: a crash never leaves half a file
        except OSError as error:
            self.last_error = f"Couldn’t save your calibration: {error.strerror or error}"
            return False
        self.last_error = ""
        return True

    def load(self) -> SavedCalibration | None:
        if not self.path.exists():
            return None
        try:
            record = json.loads(self.path.read_text())
            if record.get("measurement_version") != MEASUREMENT_VERSION:
                self.last_error = "Your saved calibration was made with an older version of OcuSense."
                return None
            calibration = PersonalCalibration(
                EyeReference(float(record["left_open_ear"]), float(record["left_closed_ear"])),
                EyeReference(float(record["right_open_ear"]), float(record["right_closed_ear"])),
                face_scale=record.get("reference_face_scale"),
            )
            return SavedCalibration(calibration, datetime.fromisoformat(record["calibrated_at"]),
                                    record["measurement_version"])
        except (OSError, ValueError, KeyError, TypeError) as error:  # damaged or invalid: calibrate again
            self.last_error = f"Your saved calibration couldn’t be used ({type(error).__name__})."
            return None
