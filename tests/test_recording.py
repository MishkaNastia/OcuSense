"""The raw EAR recording: one CSV row per frame, a new file per chunk, nothing lost or overwritten."""

import csv
import tempfile
import time
import unittest
from pathlib import Path

from ocusense.recording import HEADER, EarRecording


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
        self.assertEqual(rows[1][1:], ["0.2871", "0.2903", "1"])
        self.assertEqual(rows[2][1:], ["", "", "0"])
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


if __name__ == "__main__":
    unittest.main()
