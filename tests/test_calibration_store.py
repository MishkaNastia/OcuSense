"""The saved calibration: written once, reused on every launch, never trusted when broken."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ocusense.calibration_store import CalibrationStore
from ocusense.config import MEASUREMENT_VERSION
from ocusense.core.calibration import EyeReference, PersonalCalibration
from ocusense.core.models import CalibrationInfo

CAL = PersonalCalibration(EyeReference(0.31, 0.05), EyeReference(0.33, 0.03), face_scale=0.21)
INFO = CalibrationInfo(datetime(2026, 10, 10, 15, 52, 16), 0.31, 0.05, 0.33, 0.03, 0.35, 0.65,
                       MEASUREMENT_VERSION, 0.21)


class CalibrationStoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "OcuSense" / "calibration.json"
        self.store = CalibrationStore(self.path)

    def tearDown(self):
        self.folder.cleanup()

    def test_round_trip(self):
        self.assertTrue(self.store.save(CAL, INFO))
        saved = CalibrationStore(self.path).load()
        self.assertEqual(saved.calibration, CAL)
        self.assertEqual(saved.calibrated_at, datetime(2026, 10, 10, 15, 52, 16))
        self.assertEqual(saved.measurement_version, MEASUREMENT_VERSION)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["calibration.json"])  # no temp file left

    def test_numbers_only(self):
        self.store.save(CAL, INFO)
        record = json.loads(self.path.read_text())
        self.assertEqual(set(record), {"calibrated_at", "measurement_version", "left_open_ear", "left_closed_ear",
                                       "right_open_ear", "right_closed_ear", "reference_face_scale"})

    def test_no_file_means_calibrate(self):
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.last_error, "")

    def test_damaged_file_is_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertIsNone(self.store.load())
        self.assertIn("couldn’t be used", self.store.last_error)

    def test_invalid_references_are_ignored(self):
        self.store.save(CAL, INFO)
        record = json.loads(self.path.read_text())
        record["left_closed_ear"] = 0.5  # closed above open: not a usable calibration
        self.path.write_text(json.dumps(record))
        self.assertIsNone(self.store.load())

    def test_other_measurement_version_is_ignored(self):
        self.store.save(CAL, INFO)
        record = json.loads(self.path.read_text())
        record["measurement_version"] = "ear-personal-v1"
        self.path.write_text(json.dumps(record))
        self.assertIsNone(self.store.load())
        self.assertIn("older version", self.store.last_error)

    def test_failed_save_reports_and_keeps_the_old_file(self):
        self.store.save(CAL, INFO)
        blocked = CalibrationStore(Path(self.folder.name) / "file" / "calibration.json")
        (Path(self.folder.name) / "file").write_text("a file where the folder should be")
        self.assertFalse(blocked.save(CAL, INFO))
        self.assertIn("Couldn’t save", blocked.last_error)
        self.assertIsNotNone(self.store.load())


if __name__ == "__main__":
    unittest.main()
