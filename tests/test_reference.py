"""The saved reference file: creation rules, saving, loading and where it lives."""

import math
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from ocusense import reference as reference_file
from ocusense.core.baseline_drift import LiveDrift, fit_lognormal


def pairs(n, start=1.0):
    onsets, t = [], start
    for i in range(n + 1):
        onsets.append(t)
        t += 2.0 + i % 4
    return list(zip(onsets, onsets[1:]))


class ReferenceFileTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "sub" / "reference.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_too_few_intervals_make_no_reference(self):
        self.assertIsNone(reference_file.from_pairs(pairs(49), datetime(2026, 10, 10), "test", None))
        self.assertIsNotNone(reference_file.from_pairs(pairs(50), datetime(2026, 10, 10), "test", None))

    def test_fit_is_the_mle(self):
        ref = reference_file.from_pairs(pairs(80), datetime(2026, 10, 10, 21, 26), "test", None)
        mu, sigma, n = fit_lognormal(ref.intervals)
        self.assertEqual((ref.mu, ref.sigma, ref.n), (mu, sigma, n))
        self.assertAlmostEqual(ref.median, math.exp(mu))
        self.assertEqual(ref.label(), "10 Oct 2026, 21:26")

    def test_save_and_load_round_trip(self):
        calibration = {"close_below": 0.35, "reopen_above": 0.65, "calibrated_at": "2026-10-10T21:26:24"}
        ref = reference_file.from_pairs(pairs(60), datetime(2026, 10, 10, 21, 26, 24), "ear_x.csv", calibration)
        reference_file.save(ref, self.path)
        self.assertEqual(reference_file.load(self.path), ref)
        self.assertFalse(self.path.with_suffix(".json.tmp").exists())

    def test_missing_and_unreadable_files(self):
        self.assertIsNone(reference_file.load(self.path))
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{}")
        with self.assertRaises(reference_file.ReferenceFileError):
            reference_file.load(self.path)

    def test_discard(self):
        reference_file.save(reference_file.from_pairs(pairs(60), datetime(2026, 10, 10), "test", None), self.path)
        reference_file.discard(self.path)
        self.assertFalse(self.path.exists())
        reference_file.discard(self.path)  # nothing to remove: no error

    def test_default_path(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(reference_file.default_path(),
                             Path.home() / "Library" / "Application Support" / "OcuSense" / "reference.json")
        with mock.patch.dict(os.environ, {"OCUSENSE_RECORDINGS_DIR": "/tmp/x"}, clear=True):
            self.assertEqual(reference_file.default_path(), Path("/tmp/x/reference.json"))  # tests stay inside
        with mock.patch.dict(os.environ, {"OCUSENSE_REFERENCE_FILE": "/tmp/r.json"}, clear=True):
            self.assertEqual(reference_file.default_path(), Path("/tmp/r.json"))


class FixedReferenceTest(unittest.TestCase):
    def test_windows_from_the_start_and_none_overlap(self):
        ref = [b - a for a, b in pairs(150)]
        live = LiveDrift(100.0, reference=ref)
        self.assertTrue(live.fixed)
        session = pairs(200, start=101.0)
        self.assertEqual(live.update(session, 100.0 + 304), [])
        first = live.update(session, 100.0 + 305)
        self.assertEqual([w.start for w in first], [100.0])
        self.assertFalse(first[0].overlaps_baseline)
        self.assertFalse(first[0].different)  # the same pattern as the reference
        self.assertIsNone(live.baseline_pairs)  # nothing of this session becomes a reference


if __name__ == "__main__":
    unittest.main()
