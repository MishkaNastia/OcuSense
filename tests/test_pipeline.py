"""Checks for the per-frame monitor (uses the real MediaPipe model). Run with:  python -m unittest"""

import unittest
from types import SimpleNamespace

import numpy as np

from ocusense.core.calibration import GuidedCalibration
from ocusense.core.models import PostureBaseline
from ocusense.core.posture import PostureCalibration, PostureMonitor
from ocusense.monitoring.pipeline import CALIBRATION_DONE, MODEL_PATH, SCREEN_TILTED, EyeMonitor


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class EyeMonitorTest(unittest.TestCase):
    def setUp(self):
        self.monitor = EyeMonitor()

    def tearDown(self):
        self.monitor.close()

    def test_no_face_means_paused(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        frame[:, :10] = 255  # white stripe on the left
        result = self.monitor.process(frame, now=1.0)
        self.assertIsNone(result.landmarks)
        self.assertIsNone(result.openness)
        self.assertFalse(result.blinked)
        self.assertEqual(result.frame[0, -1].tolist(), [255, 255, 255])  # mirrored

    def test_reset_session_keeps_calibration(self):
        calibration = object()
        self.monitor.calibration = calibration
        self.monitor.counter.count = 7
        self.monitor.history.add(0.0, (1.0, 1.0, 1.0))
        self.monitor.reset_session()
        self.assertEqual(self.monitor.counter.count, 0)
        self.assertEqual(self.monitor.eye_counters["left"].count, 0)
        self.assertEqual(len(self.monitor.history.samples), 0)
        self.assertIs(self.monitor.calibration, calibration)

    def test_start_calibration_forgets_old_state(self):
        self.monitor.history.add(0.0, (1.0, 1.0, 1.0))
        self.monitor.start_calibration(now=1.0)
        self.assertIsNone(self.monitor.calibration)
        self.assertEqual(len(self.monitor.history.samples), 0)
        self.assertEqual(self.monitor.calibrator.status, GuidedCalibration.RUNNING)


    def test_no_face_means_no_posture(self):
        self.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        result = self.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
        self.assertIsNone(result.posture)
        self.assertFalse(result.posture_status.tracked)  # like lost tracking

    def test_posture_calibration_is_separate_from_the_eye_calibration(self):
        calibration = object()
        self.monitor.calibration = calibration
        self.monitor.start_posture_calibration(now=1.0)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)
        self.assertIs(self.monitor.calibration, calibration)  # eye calibration untouched
        self.assertEqual(self.monitor.calibrator.status, GuidedCalibration.IDLE)
        frame = np.zeros((480, 640, 3), np.uint8)
        self.monitor.process(frame, now=2.0)
        self.monitor.process(frame, now=122.0)  # 2 min without a face
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.FAILED)
        self.assertIsNone(self.monitor.posture_monitor)

    def test_eye_calibration_starts_the_posture_baseline(self):
        class Calibrator:  # finishes on the next frame, like the real one at the end of its last step
            status, step, result = GuidedCalibration.RUNNING, SimpleNamespace(name="blinks"), None

            def update(self, now, ears, scale):
                self.status, self.step = GuidedCalibration.DONE, None
                eye = SimpleNamespace(open_ear=0.3, closed_ear=0.1)
                self.result = SimpleNamespace(left=eye, right=eye, face_scale=0.2)

        self.monitor.calibrator = Calibrator()
        result = self.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
        self.assertIn(CALIBRATION_DONE, result.events)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)

    def test_settled_screen_tilt_records_a_new_baseline(self):
        self.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3, lid_angle=118.0))
        frame = np.zeros((480, 640, 3), np.uint8)
        events = []
        for i, lid in enumerate([118, 118, 121, 125, 125, 125, 125, 125, 125, 125]):  # tilted, then left at 125°
            events += self.monitor.process(frame, now=1.0 + i * 0.5, lid_angle=float(lid)).events
        self.assertEqual(events.count(SCREEN_TILTED), 1)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)
        self.assertEqual(self.monitor.tilt.reference, 125.0)

    def test_pause_forgets_posture_timers(self):
        monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        monitor._since["slumped"] = 0.0
        self.monitor.posture_monitor = monitor
        self.monitor.interrupt()
        self.assertEqual(monitor._since, {})


if __name__ == "__main__":
    unittest.main()
