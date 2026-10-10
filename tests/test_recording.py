"""The raw EAR recording: one CSV row per frame, a new file per chunk, nothing lost or overwritten."""

import csv
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from ocusense.core.models import CalibrationInfo
from ocusense.recording import HEADER, EarRecording


def calibration(open_ear=0.30):
    return CalibrationInfo(calibrated_at=datetime(2026, 10, 10, 14, 3, 12), left_open_ear=open_ear,
                           left_closed_ear=0.10, right_open_ear=0.31, right_closed_ear=0.11,
                           close_below=0.35, reopen_above=0.65, measurement_version="ear-personal-v2")


def read(path: Path) -> list[list[str]]:
    with path.open(newline="") as file:
        return list(csv.reader(file))


class EarRecordingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.log = EarRecording(Path(self.folder.name) / "recordings", chunk_seconds=600)

    def tearDown(self):
        self.folder.cleanup()

    def test_writes_one_row_per_frame_with_wall_clock_time(self):
        now = time.monotonic()
        self.log.add(now - 1 / 30, 0.28714, 0.29031, True)
        self.log.add(now, None, None, False)  # no face: empty EAR, gap stays visible
        path = self.log.flush()
        rows = read(path)
        self.assertEqual(tuple(rows[0]), HEADER)
        self.assertEqual(rows[1][1:], ["0.2871", "0.2903", "1", "", ""])  # not calibrated: no openness
        self.assertEqual(rows[2][1:], ["", "", "0", "", ""])
        self.assertAlmostEqual(float(rows[1][0]), time.time() - 1 / 30, delta=0.5)
        self.assertAlmostEqual(float(rows[2][0]) - float(rows[1][0]), 1 / 30, delta=0.002)

    def test_due_after_a_full_chunk(self):
        t0 = time.monotonic()
        self.assertFalse(self.log.due(t0))  # nothing buffered
        self.log.add(t0, 0.3, 0.3, True)
        self.assertFalse(self.log.due(t0 + 599))
        self.assertTrue(self.log.due(t0 + 600))
        self.log.flush()
        self.assertFalse(self.log.due(t0 + 1200))  # a new chunk starts with the next frame

    def test_each_flush_makes_a_new_file_and_never_overwrites(self):
        t = time.monotonic()
        self.log.add(t, 0.3, 0.3, True)
        first = self.log.flush()
        self.log.add(t, 0.2, 0.2, True)  # same start second: must not replace the first file
        second = self.log.flush()
        self.assertNotEqual(first, second)
        self.assertEqual(read(first)[1][1], "0.3000")
        self.assertEqual(read(second)[1][1], "0.2000")
        self.assertIsNone(self.log.flush())  # nothing buffered: no empty file

    def test_failed_write_keeps_rows_for_the_next_try(self):
        blocker = Path(self.folder.name) / "recordings"
        blocker.write_text("not a folder")  # the folder can't be created
        self.log.add(time.monotonic(), 0.3, 0.3, True)
        self.assertIsNone(self.log.flush())
        self.assertIn("Couldn’t save", self.log.last_error)
        self.assertEqual(len(self.log.rows), 1)
        blocker.unlink()
        self.assertIsNotNone(self.log.flush())
        self.assertEqual(self.log.last_error, "")

    def test_disabled_records_nothing(self):
        self.log.enabled = False
        self.log.add(time.monotonic(), 0.3, 0.3, True)
        self.assertEqual(self.log.rows, [])

    def test_openness_columns_and_calibration_file(self):
        info = calibration()
        self.log.add(time.monotonic(), 0.29, 0.30, True, 0.95, 0.9512, calibration=info)
        path = self.log.flush()
        self.assertEqual(read(path)[1][1:], ["0.2900", "0.3000", "1", "0.9500", "0.9512"])
        record = json.loads(path.with_suffix("").with_suffix(".calibration.json").read_text())
        self.assertEqual(record["calibration"]["left_open_ear"], 0.30)
        self.assertEqual(record["calibration"]["right_closed_ear"], 0.11)
        self.assertEqual(record["calibration"]["calibrated_at"], "2026-10-10T14:03:12")
        self.assertIn("openness_formula", record)

    def test_without_calibration_the_file_says_so(self):
        self.log.add(time.monotonic(), 0.29, 0.30, True)
        path = self.log.flush()
        record = json.loads((path.parent / (path.stem + ".calibration.json")).read_text())
        self.assertIsNone(record["calibration"])

    def test_a_new_calibration_starts_a_new_file(self):
        t = time.monotonic()
        self.log.add(t, 0.2, 0.2, True)  # calibrating: no calibration yet
        self.log.add(t + 0.03, 0.2, 0.2, True)
        self.log.add(t + 0.06, 0.3, 0.3, True, 0.9, 0.9, calibration=calibration())  # calibration done
        self.assertEqual(self.log.files_written, 1)  # the calibration frames were written on their own
        self.log.add(t + 0.09, 0.3, 0.3, True, 0.9, 0.9, calibration=calibration())  # equal: same file
        self.log.add(t + 0.12, 0.3, 0.3, True, 0.8, 0.8, calibration=calibration(0.32))  # recalibrated
        self.assertEqual(self.log.files_written, 2)
        self.log.flush()
        files = sorted(Path(self.folder.name, "recordings").glob("*.csv"))
        self.assertEqual([len(read(f)) - 1 for f in files], [2, 2, 1])


if __name__ == "__main__":
    unittest.main()
