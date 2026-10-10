"""Checks for the measurement foundation (core/measurements.py). Run with:  python -m unittest

Timestamps are exact and known, so the expected rates, durations and
percentages can be worked out by hand. The real blink detector decides when
eyes close and reopen (see tests/helpers.py).
"""

import hashlib
import json
import random
import unittest

from ocusense.core.blink_counter import BlinkCounter
from ocusense.core.calibration import CalibrationError, EyeReference, PersonalCalibration, build_eye_reference
from ocusense.core.measurements import (
    MeasurementTracker, RollingWindow, combined_openness_percent, openness_percent,
)
from ocusense.core.session import SessionRecorder
from tests.helpers import CLOSED, FPS, OPEN, Observer, blinking, frames


def run(values, start=0.0, seconds=60.0, window=None, observe=None):
    """Feed frames through tracker + rolling window; returns (window, observer)."""
    observe = observe or Observer()
    tracker = MeasurementTracker()
    window = window or RollingWindow(start)
    window._tracker = tracker
    for t, value in frames(start, seconds, values):
        window.add(tracker.add(observe(t, value)))
    return window, observe


class OpennessTest(unittest.TestCase):
    def test_each_eye_uses_its_own_calibration_range(self):
        left = EyeReference(open_ear=0.30, closed_ear=0.10)
        right = EyeReference(open_ear=0.24, closed_ear=0.08)  # a naturally narrower eye
        self.assertAlmostEqual(left.raw_openness(0.20), 0.5)
        self.assertAlmostEqual(right.raw_openness(0.16), 0.5)
        cal = PersonalCalibration(left, right)
        l_raw, r_raw = cal.raw_openness({"left": 0.20, "right": 0.16})
        self.assertAlmostEqual(combined_openness_percent(l_raw, r_raw), 50.0)

    def test_display_is_clamped_but_raw_value_kept(self):
        ref = EyeReference(open_ear=0.30, closed_ear=0.10)
        self.assertAlmostEqual(ref.raw_openness(0.36), 1.3)  # wider than calibrated: kept internally
        self.assertEqual(openness_percent(ref.raw_openness(0.36)), 100.0)
        self.assertAlmostEqual(ref.raw_openness(0.06), -0.2)
        self.assertEqual(openness_percent(ref.raw_openness(0.06)), 0.0)

    def test_combined_uses_mean_of_separately_clamped_eyes(self):
        self.assertAlmostEqual(combined_openness_percent(1.4, 0.6), (100 + 60) / 2)

    def test_unavailable_is_none_not_zero(self):
        self.assertIsNone(openness_percent(None))
        self.assertIsNone(combined_openness_percent(0.8, None))
        self.assertIsNone(combined_openness_percent(None, None))

    def test_invalid_references_are_rejected(self):
        with self.assertRaises(ValueError):
            EyeReference(open_ear=0.10, closed_ear=0.30)  # closed wider than open
        with self.assertRaises(ValueError):
            EyeReference(open_ear=0.20, closed_ear=0.20)  # no separation
        with self.assertRaises(CalibrationError):
            build_eye_reference("left", [0.30] * 20, [0.28] * 20)  # insufficiently separated

    def test_detector_input_is_unchanged(self):
        ref = EyeReference(open_ear=0.30, closed_ear=0.10)
        self.assertEqual(ref.openness(0.36), 1.0)  # the detector still gets the 0..1 clipped value
        self.assertEqual(ref.openness(0.06), 0.0)


class KnownSequenceTest(unittest.TestCase):
    def test_rate_duration_and_closed_percent(self):
        # 60 s at 30 fps; a 0.2 s closure every 4 s starting at 1 s → 15 blinks.
        window, _ = run(blinking(every=4.0, closed_for=0.2))
        snap = window.snapshot(now=60.0 - 1 / FPS)
        self.assertEqual(snap.blinks, 15)
        self.assertAlmostEqual(snap.valid_seconds, 60.0 - 1 / FPS, places=6)
        self.assertAlmostEqual(snap.blink_rate, 15 / (60.0 - 1 / FPS) * 60, places=6)
        self.assertAlmostEqual(snap.median_closure, 0.2, places=6)  # 6 closed frames → reopen 0.2 s later
        self.assertAlmostEqual(snap.closed_seconds, 15 * 0.2, places=6)
        self.assertAlmostEqual(snap.closed_percent, 15 * 0.2 / (60.0 - 1 / FPS) * 100, places=6)
        self.assertAlmostEqual(snap.coverage, 1.0, places=3)
        self.assertAlmostEqual(snap.processing_rate, FPS, places=3)

    def test_durations_use_timestamps_not_frame_counts(self):
        # Same closure (2 frames) at 10 fps lasts 0.2 s, not "2 frames".
        observe, tracker = Observer(), MeasurementTracker()
        steps = [tracker.add(observe(t, v)) for t, v in [(0.0, OPEN), (0.1, OPEN), (0.2, CLOSED), (0.3, CLOSED), (0.4, OPEN)]]
        self.assertAlmostEqual(steps[-1].closure, 0.2)


class DataQualityTest(unittest.TestCase):
    def test_tracking_gap_excluded_from_denominators(self):
        # 20 s valid, 10 s face lost, 30 s valid — 50 s observed out of 60 s monitored.
        window, _ = run(lambda rel: None if 20 <= rel < 30 else OPEN)
        snap = window.snapshot(now=60.0)
        self.assertAlmostEqual(snap.valid_seconds, 50.0 - 2 / FPS, places=3)
        self.assertAlmostEqual(snap.running_seconds, 60.0, places=6)
        self.assertAlmostEqual(snap.coverage, (50.0 - 2 / FPS) / 60.0, places=3)
        self.assertEqual(snap.closed_seconds, 0.0)  # missing time is never "closed"

    def test_long_frame_gap_is_not_observed_time(self):
        observe, tracker, window = Observer(), MeasurementTracker(), RollingWindow(0.0)
        for t in (0.0, 0.1, 0.2, 1.5, 1.6):  # 1.3 s jump between frames: longer than MAX_FRAME_GAP
            window.add(tracker.add(observe(t, OPEN)))
        self.assertAlmostEqual(window.snapshot(1.6).valid_seconds, 0.3)

    def test_pause_creates_a_gap_and_keeps_history(self):
        recorder = SessionRecorder(0.0)
        observe = Observer()
        for t, v in frames(0.0, 40.0, blinking()):
            recorder.add_observation(observe(t, v))
        before = recorder.live(40.0)
        recorder.pause(40.0)
        recorder.resume(55.0)  # 15 s paused
        for t, v in frames(55.0, 5.0, lambda rel: OPEN):
            recorder.add_observation(observe(t, v))
        after = recorder.live(60.0)
        self.assertEqual(after.blinks, before.blinks)  # history kept
        self.assertAlmostEqual(after.running_seconds, 45.0, places=6)  # pause not in the denominator
        self.assertLess(after.valid_seconds, 45.0)
        self.assertAlmostEqual(recorder.summary(60.0).study_seconds, 45.0, places=6)

    def test_new_session_resets_rolling_measurements(self):
        first = SessionRecorder(0.0)
        observe = Observer()
        for t, v in frames(0.0, 40.0, blinking()):
            first.add_observation(observe(t, v))
        second = SessionRecorder(40.0)  # what Start or Recalibrate creates
        snap = second.live(41.0)
        self.assertEqual((snap.blinks, snap.valid_seconds), (0, 0.0))


class ClosureEventTest(unittest.TestCase):
    def test_incomplete_closure_interrupted_by_tracking_loss(self):
        # Eyes close at 10 s, face is lost at 10.5 s, back (open) at 12 s.
        def values(rel):
            if 10 <= rel < 10.5:
                return CLOSED
            return None if 10.5 <= rel < 12 else OPEN
        window, observe = run(values, seconds=40.0)
        snap = window.snapshot(40.0)
        self.assertEqual(snap.blinks, 0)  # the detector forgot the half-finished blink
        self.assertEqual(snap.closure_count, 0)  # and no duration is reported
        self.assertIsNone(snap.median_closure)
        self.assertAlmostEqual(snap.closed_seconds, 0.5 - 1 / FPS, places=6)  # closed time up to the last valid frame

    def test_prolonged_closure_counts_as_closed_time_and_one_blink(self):
        # Eyes closed from 10 s to 15 s.
        window, _ = run(lambda rel: CLOSED if 10 <= rel < 15 else OPEN, seconds=40.0)
        snap = window.snapshot(40.0)
        self.assertEqual(snap.blinks, 1)  # not repeated while eyes stay closed
        self.assertAlmostEqual(snap.closed_seconds, 5.0, places=6)
        self.assertAlmostEqual(snap.median_closure, 5.0, places=6)

    def test_ongoing_closure_counts_up_to_latest_frame(self):
        window, _ = run(lambda rel: CLOSED if rel >= 35 else OPEN, seconds=40.0)
        snap = window.snapshot(40.0 - 1 / FPS)
        self.assertEqual(snap.blinks, 0)  # never reopened
        self.assertAlmostEqual(snap.closed_seconds, 5.0 - 1 / FPS, places=6)

    def test_pause_discards_an_unfinished_closure(self):
        recorder, observe = SessionRecorder(0.0), Observer()
        for t, v in frames(0.0, 10.0, lambda rel: CLOSED if rel >= 9 else OPEN):
            recorder.add_observation(observe(t, v))
        recorder.pause(10.0)
        observe.detector.update(None)  # what EyeMonitor.interrupt() does on pause
        recorder.resume(20.0)
        for t, v in frames(20.0, 5.0, lambda rel: OPEN):
            recorder.add_observation(observe(t, v))
        snap = recorder.live(25.0)
        self.assertEqual(snap.blinks, 0)
        self.assertEqual(snap.closure_count, 0)


class WindowBoundaryTest(unittest.TestCase):
    def test_intervals_crossing_the_window_edge_count_partly(self):
        # 70 s of data; closure from 9 s to 11 s; at now=70 the window starts at 10 s.
        window, _ = run(lambda rel: CLOSED if 9 <= rel < 11 else OPEN, seconds=70.0)
        snap = window.snapshot(70.0)
        self.assertAlmostEqual(snap.closed_seconds, 1.0, places=6)  # only the part after 10 s
        self.assertEqual(snap.blinks, 1)  # completed at 11 s, inside the window
        self.assertAlmostEqual(snap.median_closure, 2.0, places=6)  # the whole completed event
        self.assertAlmostEqual(snap.valid_seconds, 60.0 - 1 / FPS, places=3)

    def test_old_events_leave_the_window(self):
        window, _ = run(lambda rel: CLOSED if 2 <= rel < 3 else OPEN, seconds=70.0)
        snap = window.snapshot(70.0)
        self.assertEqual((snap.blinks, snap.closure_count, snap.closed_seconds), (0, 0, 0.0))

    def test_memory_is_bounded(self):
        window, _ = run(blinking(), seconds=300.0)
        self.assertLess(len(window._intervals), 61 * FPS)
        self.assertLess(len(window._frames), 6 * FPS + 2)


class NotEnoughDataTest(unittest.TestCase):
    def test_collecting_data_before_30_valid_seconds(self):
        window, _ = run(blinking(), seconds=20.0)
        snap = window.snapshot(20.0)
        self.assertFalse(snap.enough_data)
        self.assertIsNone(snap.blink_rate)
        self.assertIsNone(snap.closed_percent)
        self.assertIsNotNone(snap.median_closure)  # completed events can already be shown

    def test_no_events_gives_zero_rate_and_no_median(self):
        window, _ = run(lambda rel: OPEN, seconds=45.0)
        snap = window.snapshot(45.0)
        self.assertTrue(snap.enough_data)
        self.assertEqual(snap.blink_rate, 0.0)  # enough observation, genuinely no blinks
        self.assertIsNone(snap.median_closure)  # "—"
        self.assertEqual(snap.closed_percent, 0.0)

    def test_empty_window(self):
        snap = RollingWindow(0.0).snapshot(5.0)
        self.assertEqual(snap.valid_seconds, 0.0)
        self.assertIsNone(snap.processing_rate)
        self.assertIsNone(snap.blink_rate)


class DetectorUnchangedTest(unittest.TestCase):
    def test_same_decisions_as_before_this_change(self):
        """Fingerprint of the detector's decisions on a long, noisy sequence (recorded before the change)."""
        rng = random.Random(42)
        cal = PersonalCalibration(EyeReference(0.30, 0.10), EyeReference(0.24, 0.08))
        counter, trace = BlinkCounter(), []
        for i in range(20000):
            t = i / 30
            if rng.random() < 0.01:
                ears = None
            else:
                closing = (t % 3.7) < 0.2 or (5000 < i < 5200)
                wink = (t % 11) < 0.3
                ears = {"left": (0.09 if closing else 0.31) + rng.gauss(0, 0.01),
                        "right": (0.07 if (closing or wink) else 0.25) + rng.gauss(0, 0.01)}
            o = None if ears is None else cal.openness(ears)
            b = counter.update(None if o is None else o[2])
            trace.append((round(o[2], 6) if o else None, b, counter.state))
        digest = hashlib.sha256(json.dumps(trace).encode()).hexdigest()[:16]
        self.assertEqual((digest, counter.count), ("bc42f2fc0c7c3574", 160))


if __name__ == "__main__":
    unittest.main()
