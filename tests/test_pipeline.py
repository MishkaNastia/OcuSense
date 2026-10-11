"""Checks for the per-frame monitor (uses the real MediaPipe model). Run with:  python -m unittest"""

import unittest
from types import SimpleNamespace

import numpy as np

from ocusense.core.calibration import GuidedCalibration
from ocusense.core.models import PostureBaseline
from ocusense.core.posture import PostureCalibration, PostureMonitor
from ocusense.monitoring.pipeline import (
    CALIBRATION_DONE, MODEL_PATH, POSTURE_CALIBRATION_FAILED, SCREEN_TILTED, EyeMonitor,
)


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
        self.monitor.posture_enabled = True
        self.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        result = self.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
        self.assertIsNone(result.posture)
        self.assertFalse(result.posture_status.tracked)  # like lost tracking

    def test_posture_calibration_is_separate_from_the_eye_calibration(self):
        calibration = object()
        self.monitor.calibration = calibration
        self.monitor.posture_enabled = True
        self.monitor.start_posture_calibration(now=1.0)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)
        self.assertIs(self.monitor.calibration, calibration)  # eye calibration untouched
        self.assertEqual(self.monitor.calibrator.status, GuidedCalibration.IDLE)
        frame = np.zeros((480, 640, 3), np.uint8)
        self.monitor.process(frame, now=2.0)
        result = self.monitor.process(frame, now=62.0)  # 1 min without a face
        self.assertIn(POSTURE_CALIBRATION_FAILED, result.events)
        self.assertIn("seen clearly", self.monitor.posture_calibration_error)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)  # no baseline: retried
        self.assertIsNone(self.monitor.posture_monitor)

    def test_eye_calibration_leaves_the_posture_baseline_to_the_session(self):
        class Calibrator:  # finishes on the next frame, like the real one at the end of its last step
            status, step, result = GuidedCalibration.RUNNING, SimpleNamespace(name="blinks"), None

            def update(self, now, ears, scale):
                self.status, self.step = GuidedCalibration.DONE, None
                eye = SimpleNamespace(open_ear=0.3, closed_ear=0.1)
                self.result = SimpleNamespace(left=eye, right=eye, face_scale=0.2)

        self.monitor.calibrator = Calibrator()
        self.monitor.posture_enabled = True
        result = self.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
        self.assertIn(CALIBRATION_DONE, result.events)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.IDLE)  # the session start asks

    def test_posture_is_off_by_default(self):
        result = self.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0, lid_angle=118.0)
        self.assertFalse(self.monitor.posture_enabled)
        self.assertIsNone(result.posture)
        self.assertIsNone(result.posture_status)
        self.assertIsNone(self.monitor.tilt.reference)

    def test_switching_posture_on_and_off(self):
        self.monitor.set_posture_enabled(True, now=1.0)  # eyes not calibrated: waits for the eye calibration
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.IDLE)
        self.monitor.set_posture_enabled(False, now=2.0)
        self.monitor.calibration = object()
        self.monitor.set_posture_enabled(True, now=3.0)  # calibrated: the 2-min baseline starts now
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)
        self.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        self.monitor.set_posture_enabled(False, now=4.0)  # off: everything forgotten
        self.assertIsNone(self.monitor.posture_monitor)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.IDLE)

    def test_settled_screen_tilt_waits_for_recalibrate_now(self):
        self.monitor.posture_enabled = True
        self.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3, lid_angle=118.0))
        frame = np.zeros((480, 640, 3), np.uint8)
        events = []
        for i, lid in enumerate([118, 118, 121, 125, 125, 125, 125, 125, 125, 125]):  # tilted, then left at 125°
            events += self.monitor.process(frame, now=1.0 + i * 0.5, lid_angle=float(lid)).events
        self.assertEqual(events.count(SCREEN_TILTED), 1)
        self.assertTrue(self.monitor.posture_needs_recalibration)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.IDLE)  # nothing starts by itself
        result = self.monitor.process(frame, now=7.0, lid_angle=135.0)
        self.assertIsNone(result.posture_status)  # not judged until recalibrated
        for i in range(8):  # tilted again before recalibrating: no second message
            events = self.monitor.process(frame, now=7.5 + i * 0.5, lid_angle=135.0).events
            self.assertNotIn(SCREEN_TILTED, events)
        self.monitor.start_posture_calibration(now=12.0)  # "Recalibrate now"
        self.assertFalse(self.monitor.posture_needs_recalibration)

    def test_tilt_during_a_recalibration_just_restarts_it(self):
        self.monitor.posture_enabled = True
        self.monitor.start_posture_calibration(now=0.5)
        frame = np.zeros((480, 640, 3), np.uint8)
        events = []
        for i, lid in enumerate([118, 118, 125, 125, 125, 125, 125, 125, 125]):
            events += self.monitor.process(frame, now=1.0 + i * 0.5, lid_angle=float(lid)).events
        self.assertNotIn(SCREEN_TILTED, events)
        self.assertEqual(self.monitor.posture_calibrator.status, PostureCalibration.RUNNING)
        self.assertGreater(self.monitor.posture_calibrator._started, 0.5)  # started again
        self.assertFalse(self.monitor.posture_needs_recalibration)

    def test_pause_forgets_posture_timers(self):
        monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        monitor._since["slumped"] = 0.0
        self.monitor.posture_monitor = monitor
        self.monitor.interrupt()
        self.assertEqual(monitor._since, {})


if __name__ == "__main__":
    unittest.main()
