"""ocusense/data_export.py: copies only the frames in the time range, and counts a moment recorded twice once."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ocusense.data_export import copy_check_ins, copy_range, fit_folder, parse_time

CALIBRATION = {"left_open_ear": 0.30, "left_closed_ear": 0.10, "right_open_ear": 0.30, "right_closed_ear": 0.10,
               "close_below": 0.35, "reopen_above": 0.65, "calibrated_at": "2026-10-10T18:00:00",
               "measurement_version": "ear-personal-v2"}


def write_recording(folder: Path, name: str, start: float, seconds: float, blink_every: float = 3.0) -> None:
    """30 frames/s; eyes closed for 0.2 s every blink_every seconds (EAR 0.30 open, 0.10 closed)."""
    with (folder / f"{name}.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["unix_time", "left_ear", "right_ear", "reliable"])
        for i in range(int(seconds * 30)):
            t = i / 30
            closed = (t % blink_every) > blink_every - 0.2
            ear = 0.10 if closed else 0.30
            writer.writerow([f"{start + t:.3f}", ear, ear, 1])
    (folder / f"{name}.calibration.json").write_text(json.dumps({"calibration": CALIBRATION}))


class DataExportTest(unittest.TestCase):
    def test_range_cut_check_ins_and_duplicates(self):
        source, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        start = parse_time("2026-10-10 22:00")
        write_recording(source, "ear_a", start, 120)
        write_recording(source, "ear_b", start + 60, 120)  # a second copy of the app, overlapping by 60 s
        write_recording(source, "ear_c", start - 3600, 30)  # before the range
        (source / "check_ins").mkdir()
        (source / "check_ins" / "labels.csv").write_text(
            "session_started,prompted_unix_time,sleepiness\ns,%f,3\ns,%f,4\n" % (start + 30, start - 7200))
        until = start + 150  # cuts ear_b
        files = copy_range(source, out / "recordings", start, until)
        self.assertEqual([f["file"] for f in files], ["ear_a.csv", "ear_b.csv"])
        self.assertEqual([f["cut"] for f in files], [False, True])
        self.assertTrue((out / "recordings" / "ear_b.calibration.json").exists())
        with (out / "recordings" / "ear_b.csv").open() as stream:
            times = [float(r["unix_time"]) for r in csv.DictReader(stream)]
        self.assertLess(max(times), until)
        self.assertEqual(copy_check_ins(source, out, start, until), 1)

        fits = fit_folder(out)
        self.assertGreater(fits["duplicate_intervals_left_out"], 0)
        counted = [r for r in csv.DictReader((out / "intervals.csv").open()) if r["counted"] == "1"]
        self.assertTrue(all(r["recording"] == "ear_a.csv" or float(r["onset_a_unix"]) > start + 120
                            for r in counted))
        self.assertAlmostEqual(fits["all"]["median_seconds"], 3.0, delta=0.1)
        self.assertEqual(fits["all"]["n"], len(counted))


if __name__ == "__main__":
    unittest.main()
