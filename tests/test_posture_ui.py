"""Statistics › Current session: the posture indicator and the Calibrate posture button (no camera, offscreen)."""

import os
import unittest

from tests.test_main_window import FakeThread, update  # sets offscreen Qt and a temporary recordings folder

from ocusense.core.models import PostureStatus
from ocusense.core.posture import HEAD_DROPPED, SLUMPED, PostureCalibration
from ocusense.monitoring.pipeline import MODEL_PATH

os.environ["OCUSENSE_NO_NOTIFICATIONS"] = "1"


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class PostureUiTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.page = self.window.current_page

    def tearDown(self):
        self.window.close()

    def monitoring(self):
        self.window.monitor.calibration = object()
        self.window.start()
        self.window.show_page("current")

    def send(self, **changes):
        self.window._on_update(update(**changes))

    def test_button_needs_a_running_session(self):
        self.page.posture_button.click()
        self.assertEqual(self.thread.posture_calibration_requests, 0)
        self.assertIn("Start a session first", self.page.posture_detail.text())

    def test_button_asks_the_camera_thread(self):
        self.monitoring()
        self.page.posture_button.click()
        self.assertEqual(self.thread.posture_calibration_requests, 1)
        self.assertEqual(self.thread.calibration_requests, 0)  # the eye calibration isn't touched
        self.assertEqual(self.window.state, "monitoring")

    def test_calibrating_then_good_then_poor(self):
        self.monitoring()
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=2.2)
        self.assertEqual(self.page.posture_indicator.text.text(), "Calibrating posture…")
        self.assertIn("2 s", self.page.posture_detail.text())

        good = PostureStatus(tracked=True, pitch_change=-2.0, roll_change=1.0, distance_cm=63.0,
                             baseline_distance_cm=65.0, centre_drop=0.01, size_ratio=1.02)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=good)
        self.assertEqual(self.page.posture_indicator.text.text(), "Good posture")
        self.assertIn("head 2° higher", self.page.posture_detail.text())
        self.assertIn("about 63 cm away (calibrated 65 cm)", self.page.posture_detail.text())

        brief = PostureStatus(tracked=True, outside=(HEAD_DROPPED,), longest_outside=4.0, pitch_change=20.0,
                              roll_change=0.0, centre_drop=0.0)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=brief)
        self.assertEqual(self.page.posture_indicator.text.text(), "Good · head dropped for 4 s")

        poor = PostureStatus(tracked=True, poor=True, problems=(HEAD_DROPPED, SLUMPED), outside=(HEAD_DROPPED, SLUMPED),
                             longest_outside=31.0, pitch_change=20.0, roll_change=0.0, centre_drop=0.1)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=poor)
        self.assertEqual(self.page.posture_indicator.text.text(), "Poor posture: head dropped, slumped")
        self.assertEqual(self.page.posture_indicator.glyph.kind, "warning")

    def test_failed_calibration_and_lost_face(self):
        self.monitoring()
        self.send(posture_cal_status=PostureCalibration.FAILED, posture_cal_error="Your face wasn't seen clearly.")
        self.assertEqual(self.page.posture_indicator.text.text(), "Posture calibration failed")
        self.assertIn("seen clearly", self.page.posture_detail.text())
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=PostureStatus(tracked=False),
                  face_found=False)
        self.assertEqual(self.page.posture_indicator.text.text(), "Face not tracked")


if __name__ == "__main__":
    unittest.main()
