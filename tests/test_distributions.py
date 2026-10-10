"""Blink distributions from known synthetic sequences (no camera, no files unless noted)."""

import json
import tempfile
import unittest
from pathlib import Path

from ocusense.config import MIN_VALID_SECONDS_FOR_RATE
from ocusense.core.distributions import (
    CLOSURE_BINS, INSTANT_BINS, INSTANT_BINS_PER_SECOND, INTERVAL_BINS, RATE_BINS_PER_SECOND, OPENNESS_BINS, DistributionBuilder, histogram, quartiles,
)
from ocusense.core.measurements import MeasurementTracker
from ocusense.core.models import FrameObservation
from ocusense.core.replay import RecordedCalibration, Row, replay
from ocusense.core.session import SessionRecorder

FPS = 30
CAL = RecordedCalibration(left_open_ear=0.30, left_closed_ear=0.10, right_open_ear=0.40, right_closed_ear=0.20,
                          close_below=0.35, reopen_above=0.65, calibrated_at="2026-10-10T15:52:16",
                          measurement_version="ear-personal-v2")


def ear(openness: float, eye: str, cal=CAL) -> float:
    open_ear = cal.left_open_ear if eye == "left" else cal.right_open_ear
    closed_ear = cal.left_closed_ear if eye == "left" else cal.right_closed_ear
    return closed_ear + openness * (open_ear - closed_ear)


def rows_from(values, start=1_000_000.0, step=1 / FPS, cal=CAL):
    """values: openness per frame (None = unreliable frame). Returns Rows at a fixed frame rate."""
    rows = []
    for i, v in enumerate(values):
        t = start + i * step
        if v is None:
            rows.append(Row(t, None, None, False))
        else:
            rows.append(Row(t, ear(v, "left", cal), ear(v, "right", cal), True))
    return rows


def blinks(seconds: float, blink_at: list[float], closed_frames: int = 6):
    """Openness 0.9 with a blink (0.05) of `closed_frames` frames starting at each time in blink_at."""
    values = [0.9] * int(seconds * FPS)
    for t in blink_at:
        i = int(round(t * FPS))
        for k in range(closed_frames):
            values[i + k] = 0.05
    return values


class NormalisationTest(unittest.TestCase):
    def test_each_eye_uses_its_own_references_and_percent_bins(self):
        result = replay(rows_from([0.5] * 60), CAL)
        self.assertAlmostEqual(result.timeline.left[10], 0.5, places=6)  # (0.2 − 0.1) / (0.3 − 0.1)
        self.assertAlmostEqual(result.timeline.right[10], 0.5, places=6)  # (0.3 − 0.2) / (0.4 − 0.2)
        shares = result.distributions.openness.shares("left")
        self.assertAlmostEqual(shares[OPENNESS_BINS.index(50)], 100.0)  # all time in the 50–55 % bin


class EventTimingTest(unittest.TestCase):
    def test_closure_duration_and_onset_to_onset_intervals(self):
        d = replay(rows_from(blinks(10, [2.0, 5.0, 7.5], closed_frames=6)), CAL).distributions
        self.assertEqual(d.blinks, 3)
        self.assertEqual(len(d.events), 3)
        for ms in d.closure_ms():
            self.assertAlmostEqual(ms, 6 * 1000 / FPS, delta=0.5)  # closing frame → first reopened frame
        self.assertEqual([round(x, 3) for x in d.interval_seconds()], [3.0, 2.5])
        self.assertEqual(d.interrupted, 0)

    def test_frequency_per_blink_is_sixty_over_each_interval(self):
        d = replay(rows_from(blinks(12, [1.0, 4.0, 5.0, 5.5])), CAL).distributions  # intervals 3, 1 and 0.5 s
        self.assertEqual([round(v, 3) for v in d.frequency_per_blink()], [20.0, 60.0, 120.0])
        counts = histogram(d.frequency_per_blink(), INSTANT_BINS)
        self.assertEqual(sum(counts), 3)  # every value counted
        self.assertEqual(counts[-1], 2)  # 60 and 120 per minute: the "60 or more" bar
        self.assertEqual(counts[INSTANT_BINS.index(20)], 1)

    def test_per_second_bins_put_edge_values_in_the_right_bin(self):
        self.assertEqual(INSTANT_BINS_PER_SECOND.index(0.15), 3)  # 0.15–0.20, despite 0.15 / 0.05 = 2.999…
        self.assertEqual(INSTANT_BINS_PER_SECOND.index(1 / 3), 6)  # 20 per minute → 0.30–0.35
        self.assertEqual(INSTANT_BINS_PER_SECOND.index(1.0), INSTANT_BINS_PER_SECOND.size - 1)  # "1 per second or more"
        self.assertEqual(RATE_BINS_PER_SECOND.edges[-1], 0.7)

    def test_frequency_per_blink_never_spans_a_gap(self):
        before = rows_from(blinks(5, [1.0, 3.0]))
        after = rows_from(blinks(5, [1.0]), start=before[-1].t + 2.0)
        self.assertEqual([round(v, 3) for v in replay(before + after, CAL).distributions.frequency_per_blink()], [30.0])

    def test_prolonged_closure_stays_visible(self):
        d = replay(rows_from(blinks(10, [2.0], closed_frames=45)), CAL).distributions  # 1.5 s
        self.assertAlmostEqual(d.closure_ms()[0], 1500, delta=1)
        counts = histogram(d.closure_ms(), CLOSURE_BINS)
        self.assertEqual(counts[-1], 1)  # the "1000 ms or more" bar

    def test_histogram_counts_every_event(self):
        d = replay(rows_from(blinks(60, [1 + i * 2.3 for i in range(25)], closed_frames=4)), CAL).distributions
        self.assertEqual(sum(histogram(d.closure_ms(), CLOSURE_BINS)), len(d.events))
        self.assertEqual(sum(histogram(d.interval_seconds(), INTERVAL_BINS)), len(d.intervals))


class GapTest(unittest.TestCase):
    def test_gaps_are_excluded_and_never_bridged(self):
        before = rows_from(blinks(5, [2.0]))
        after = rows_from(blinks(5, [1.0]), start=before[-1].t + 2.0)  # 2 s without frames
        d = replay(before + after, CAL).distributions
        self.assertEqual(d.segments, 2)
        self.assertEqual(len(d.events), 2)
        self.assertEqual(d.intervals, [])  # the two blinks are in different segments
        self.assertAlmostEqual(d.valid_seconds, (len(before) - 1 + len(after) - 1) / FPS, places=6)

    def test_blink_cut_by_lost_tracking_is_interrupted_not_timed(self):
        values = [0.9] * 60 + [0.05] * 5 + [None] * 10 + [0.9] * 60
        d = replay(rows_from(values), CAL).distributions
        self.assertEqual(len(d.events), 0)
        self.assertEqual(d.interrupted, 1)
        self.assertEqual(d.blinks, 0)  # the detector restarts after lost tracking, as it does live

    def test_unreliable_frames_are_unobserved(self):
        values = [0.9] * 30 + [None] * 30 + [0.9] * 30
        d = replay(rows_from(values), CAL).distributions
        self.assertAlmostEqual(d.valid_seconds, 2 * 29 / FPS, places=6)


class WindowTest(unittest.TestCase):
    def test_non_overlapping_windows_with_coverage_rule(self):
        # 0–60 s fully tracked, 60–120 s tracked for only 20 s, 120–150 s fully tracked (a partial last window)
        values = blinks(60, [5, 15, 25, 35, 45]) + [0.9] * (20 * FPS) + [None] * (40 * FPS) + [0.9] * (30 * FPS)
        d = replay(rows_from(values), CAL).distributions
        self.assertEqual(len(d.windows), 3)
        first, second, third = d.windows
        self.assertTrue(first.eligible)
        self.assertAlmostEqual(first.rate, 5 / (first.valid_seconds / 60))
        self.assertFalse(second.eligible)  # 20 s < MIN_VALID_SECONDS_FOR_RATE
        self.assertLess(second.valid_seconds, MIN_VALID_SECONDS_FOR_RATE)
        self.assertFalse(third.eligible)  # just under 30 s of intervals in the last 30 s
        self.assertEqual(d.excluded_windows(), 2)
        self.assertEqual(d.eligible_rates(), [first.rate])

    def test_valid_time_is_split_at_window_edges(self):
        d = replay(rows_from([0.9] * (90 * FPS)), CAL).distributions
        self.assertAlmostEqual(sum(w.valid_seconds for w in d.windows), d.valid_seconds, places=6)
        self.assertAlmostEqual(d.windows[0].valid_seconds, 60.0, places=6)

    def test_live_window_in_progress_is_not_used(self):
        builder = DistributionBuilder(0.0)
        tracker = MeasurementTracker()
        for i in range(45 * FPS):
            obs = FrameObservation(t=i / FPS, valid=True, left_raw=0.9, right_raw=0.9)
            builder.add(obs, tracker.add(obs))
        d = builder.snapshot(now=45.0)
        self.assertFalse(d.windows[0].complete)
        self.assertEqual(d.eligible_rates(), [])
        self.assertEqual(d.excluded_windows(), 0)


class OpennessWeightingTest(unittest.TestCase):
    def test_time_weighted_not_frame_counted(self):
        slow = [Row(1000 + i * 0.1, ear(1.0, "left"), ear(1.0, "right"), True) for i in range(51)]  # 5 s
        fast = [Row(slow[-1].t + (i + 1) * 0.01, ear(0.5, "left"), ear(0.5, "right"), True) for i in range(100)]
        o = replay(slow + fast, CAL).distributions.openness
        shares = o.shares("left")
        high = shares[OPENNESS_BINS.index(100)]  # 100 % falls in the "100 % or more" bin
        middle = shares[OPENNESS_BINS.index(50)]
        self.assertAlmostEqual(high, 5.0 / 5.99 * 100, delta=0.5)  # 51 frames but 5 s
        self.assertAlmostEqual(middle, 0.99 / 5.99 * 100, delta=0.5)  # 100 frames but ~1 s

    def test_out_of_range_openness_is_kept(self):
        values = [1.2] * 31 + [-0.1] * 31 + [0.9] * 31
        o = replay(rows_from(values), CAL).distributions.openness
        shares = o.shares("left")
        self.assertGreater(shares[-1], 30)  # ≥ 100 %
        self.assertGreater(shares[0], 30)  # < 0 %
        self.assertAlmostEqual(sum(shares), 100.0, places=6)
        self.assertAlmostEqual(o.highest["left"], 120, places=6)
        self.assertAlmostEqual(o.lowest["left"], -10, places=6)


class SmallAndEmptyTest(unittest.TestCase):
    def test_no_valid_frames(self):
        d = replay(rows_from([None] * 50), CAL).distributions
        self.assertEqual((d.valid_seconds, d.blinks, d.events, d.intervals), (0.0, 0, [], []))
        self.assertEqual(d.openness.shares("left"), [0.0] * OPENNESS_BINS.size)

    def test_quartiles_of_tiny_samples(self):
        self.assertIsNone(quartiles([]))
        self.assertEqual(quartiles([250.0]), (250.0, 250.0, 250.0))

    def test_empty_builder_snapshot(self):
        d = DistributionBuilder(10.0).snapshot(now=10.0)
        self.assertEqual((d.blinks, d.valid_seconds, d.segments), (0, 0.0, 0))


class ThresholdsFromMetadataTest(unittest.TestCase):
    def test_recorded_thresholds_are_used(self):
        shallow = [0.9] * 30 + [0.3] * 6 + [0.9] * 30  # dips to 30 %
        strict = RecordedCalibration(**{**CAL.__dict__, "close_below": 0.2, "reopen_above": 0.8})
        self.assertEqual(replay(rows_from(shallow), CAL).distributions.blinks, 1)  # 30 % < 35 %
        self.assertEqual(replay(rows_from(shallow, cal=strict), strict).distributions.blinks, 0)  # 30 % > 20 %


class LiveRecorderTest(unittest.TestCase):
    def test_pause_breaks_intervals(self):
        recorder = SessionRecorder(0.0)
        from tests.helpers import Observer
        observe = Observer()
        t = 0.0
        for i in range(10 * FPS):
            t = i / FPS
            v = 0.05 if 2.0 <= t < 2.2 else 0.9
            recorder.add_observation(observe(t, v))
        recorder.pause(t)
        recorder.resume(t + 5)
        observe = Observer()
        for i in range(10 * FPS):
            t2 = t + 5 + i / FPS
            v = 0.05 if 3.0 <= i / FPS < 3.2 else 0.9
            recorder.add_observation(observe(t2, v))
        d = recorder.distributions.snapshot(now=t2)
        self.assertEqual(len(d.events), 2)
        self.assertEqual(d.intervals, [])  # never across the pause
        self.assertEqual(d.segments, 2)


class FilesTest(unittest.TestCase):
    """Reading, grouping and exporting with real files in a temporary folder."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def write(self, name, rows, calibration):
        path = self.dir / f"{name}.csv"
        lines = ["unix_time,left_ear,right_ear,reliable,left_openness,right_openness"]
        for r in rows:
            e = lambda v: "" if v is None else f"{v:.4f}"  # noqa: E731
            lines.append(f"{r.t:.3f},{e(r.left_ear)},{e(r.right_ear)},{1 if r.reliable else 0},,")
        path.write_text("\n".join(lines) + "\n")
        record = {"calibration": None if calibration is None else calibration.__dict__}
        (self.dir / f"{name}.calibration.json").write_text(json.dumps(record))
        return path

    def test_grouping_by_continuity_and_calibration(self):
        from ocusense.recording_files import import_recordings
        other = RecordedCalibration(**{**CAL.__dict__, "left_open_ear": 0.32, "calibrated_at": "2026-10-10T16:00:00"})
        a = rows_from(blinks(5, [1.0]), start=1000.0)
        b = rows_from(blinks(5, [1.0]), start=a[-1].t + 1 / FPS)  # continues a, same calibration → joined
        c = rows_from(blinks(5, [1.0]), start=b[-1].t + 1 / FPS, cal=other)  # continues, other calibration
        d = rows_from(blinks(5, [1.0]), start=c[-1].t + 60, cal=other)  # same calibration, after a pause
        paths = [self.write("ear_a", a, CAL), self.write("ear_b", b, CAL), self.write("ear_c", c, other),
                 self.write("ear_d", d, other), self.write("ear_cal", rows_from([0.9] * 30), None)]
        (self.dir / "ear_nojson.csv").write_text("unix_time,left_ear,right_ear,reliable\n1,0.3,0.3,1\n")
        before = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        result = import_recordings(paths + [self.dir / "ear_nojson.csv"])
        self.assertEqual([len(r.files) for r in result.recordings], [2, 1, 1])
        self.assertEqual(result.recordings[0].calibration, CAL)
        self.assertEqual(result.recordings[1].calibration, other)  # segments stay distinguishable
        self.assertNotEqual(result.recordings[0].calibration.label(), result.recordings[1].calibration.label())
        reasons = dict(result.excluded)
        self.assertIn("calibration: null", reasons["ear_cal.csv"])
        self.assertIn("no matching", reasons["ear_nojson.csv"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.dir.iterdir()})  # originals untouched
        joined = result.recordings[0].replay_result.distributions
        self.assertEqual(joined.segments, 1)  # rotated files continue one segment
        self.assertEqual(len(joined.intervals), 1)

    def test_export_writes_derived_files_only(self):
        from ocusense.exports import export_analysis
        d = replay(rows_from(blinks(70, [1 + i * 3 for i in range(20)])), CAL).distributions
        target = export_analysis(self.dir, "test", d, {"calibration": CAL.__dict__})
        names = sorted(p.name for p in target.iterdir())
        self.assertEqual(names, ["analysis_settings.json", "blink_events.csv", "summary.csv", "windows.csv"])
        events = (target / "blink_events.csv").read_text().splitlines()
        self.assertEqual(len(events) - 1, len(d.events))
        settings = json.loads((target / "analysis_settings.json").read_text())
        self.assertEqual(settings["bins"]["closure"]["width"], 50)
        self.assertEqual(settings["calibration"]["close_below"], 0.35)


if __name__ == "__main__":
    unittest.main()
