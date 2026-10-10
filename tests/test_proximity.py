"""The distance reminder: face size, the calibration reference and the reminder rules."""

import unittest

from ocusense.core.calibration import GuidedCalibration
from ocusense.core.eye_metrics import measure_eyes
from ocusense.core.proximity import ProximityMonitor
from ocusense.core.replay import RecordedCalibration
from tests.test_calibration import FPS, five_blinks
from tests.test_eye_metrics import fake_landmarks


def frames(monitor, start, seconds, closeness, fps=30):
    """Feed a steady closeness; returns the times at which a reminder fired."""
    fired = []
    for i in range(int(seconds * fps)):
        t = start + i / fps
        if monitor.update(t, closeness):
            fired.append(t)
    return fired


class FaceScaleTest(unittest.TestCase):
    def test_eye_centre_distance_relative_to_frame_width(self):
        eyes = {"left": (0.40, 0.5, 0.08, 0.03), "right": (0.60, 0.5, 0.08, 0.03)}
        m = measure_eyes(fake_landmarks(eyes), 640, 480)
        self.assertAlmostEqual(m.face_scale, 0.20, places=6)  # centres 0.2 of the width apart
        closer = {"left": (0.35, 0.5, 0.12, 0.045), "right": (0.65, 0.5, 0.12, 0.045)}
        self.assertAlmostEqual(measure_eyes(fake_landmarks(closer), 640, 480).face_scale / m.face_scale, 1.5)

    def test_same_scale_at_any_camera_resolution(self):
        eyes = {"left": (0.40, 0.5, 0.08, 0.03), "right": (0.60, 0.5, 0.08, 0.03)}
        self.assertAlmostEqual(measure_eyes(fake_landmarks(eyes), 1280, 720).face_scale, 0.20, places=6)


class CalibrationReferenceTest(unittest.TestCase):
    def test_reference_is_the_median_scale_of_the_open_step(self):
        cal = GuidedCalibration()
        cal.start(0.0)
        now = 0.0
        while cal.status == GuidedCalibration.RUNNING and now < 120:
            step = cal.step
            t = now - cal._step_start - step.get_ready_seconds
            ear = 0.30 if step.name == "open" or t < 0 else 0.10 if step.name == "closed" else five_blinks(t)
            scale = 0.2 if step.name == "open" else 0.5  # only the open step may count
            cal.update(now, {"left": ear, "right": ear}, scale)
            now += 1 / FPS
        self.assertEqual(cal.status, GuidedCalibration.DONE, cal.error)
        self.assertAlmostEqual(cal.result.face_scale, 0.2)

    def test_old_recordings_without_reference_still_load(self):
        values = {"left_open_ear": 0.3, "left_closed_ear": 0.1, "right_open_ear": 0.3, "right_closed_ear": 0.1,
                  "close_below": 0.35, "reopen_above": 0.65, "calibrated_at": "2026-10-10T15:52:16",
                  "measurement_version": "ear-personal-v2"}
        self.assertIsNone(RecordedCalibration.from_json(values).reference_face_scale)
        self.assertEqual(RecordedCalibration.from_json({**values, "reference_face_scale": 0.21}).reference_face_scale,
                         0.21)


class ProximityRulesTest(unittest.TestCase):
    def test_reminds_after_three_seconds_close(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 300.0)
        self.assertEqual(frames(m, 0, 2.9, 1.8), [])  # a quick lean forward doesn't count
        fired = frames(m, 2.9, 2.0, 1.8)
        self.assertEqual(len(fired), 1)
        self.assertAlmostEqual(fired[0], 3.0, delta=1 / 30)
        self.assertTrue(m.too_close)

    def test_repeats_every_interval_while_still_close(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 5.0)  # "remind again after 5 s"
        fired = frames(m, 0, 20, 1.8)
        self.assertEqual([round(t) for t in fired], [3, 8, 13, 18])

    def test_never_more_often_than_the_interval(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 300.0)
        self.assertEqual(len(frames(m, 0, 60, 1.8)), 1)  # staying close for a minute: one reminder
        frames(m, 60, 5, 1.0)  # moved back
        self.assertFalse(m.too_close)
        self.assertEqual(frames(m, 65, 10, 1.8), [])  # close again within 5 minutes: quiet
        frames(m, 75, 5, 1.0)
        self.assertEqual(len(frames(m, 310, 10, 1.8)), 1)  # 5 minutes after the first: reminds again

    def test_two_levels_stop_flicker(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 300.0)
        frames(m, 0, 4, 1.8)
        frames(m, 4, 5, 1.45)  # between the levels: still counted as too close
        self.assertTrue(m.too_close)
        frames(m, 9, 1, 1.2)
        self.assertFalse(m.too_close)

    def test_unreliable_frames_restart_the_count(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 300.0)
        frames(m, 0, 2.5, 1.8)
        self.assertFalse(m.update(2.5, None))
        self.assertEqual(frames(m, 2.6, 2.5, 1.8), [])  # needs 3 s again after the interruption

    def test_reset_keeps_the_cooldown(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 300.0)
        frames(m, 0, 4, 1.8)
        m.reset()
        self.assertFalse(m.too_close)
        self.assertEqual(frames(m, 10, 10, 1.8), [])

    def test_interval_can_change_while_running(self):
        m = ProximityMonitor(1.6, 1.3, 3.0, 600.0)
        frames(m, 0, 4, 1.8)
        m.cooldown_seconds = 5.0  # changed in Settings
        self.assertEqual(len(frames(m, 4, 5, 1.8)), 1)

    def test_levels_must_be_ordered(self):
        with self.assertRaises(ValueError):
            ProximityMonitor(1.3, 1.6)


if __name__ == "__main__":
    unittest.main()
