"""Checks for the per-frame monitor (uses the real MediaPipe model). Run with:  python -m unittest"""

import unittest

import numpy as np

from ocusense.core.calibration import GuidedCalibration
from ocusense.monitoring.pipeline import MODEL_PATH, EyeMonitor


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


if __name__ == "__main__":
    unittest.main()
