"""Statistics › Current session: the posture indicator and the Calibrate posture button (no camera, offscreen)."""

import os
import unittest

from tests.test_main_window import FakeThread, update  # sets offscreen Qt and a temporary recordings folder

from ocusense.core.models import PostureStatus
from ocusense.core.posture import HEAD_DROPPED, SLUMPED, PostureCalibration
from ocusense.monitoring.pipeline import MODEL_PATH, SCREEN_TILTED
from ocusense.ui.main_window import TILT_MESSAGE

os.environ["OCUSENSE_NO_NOTIFICATIONS"] = "1"


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class PostureUiTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.notifications = []
        self.window.notify = lambda message, title: self.notifications.append((title, message))
        self.page = self.window.current_page
        self.window.settings_page.posture.setChecked(True)  # off by default; these tests are about it being on

    def tearDown(self):
        self.window.settings_page.posture.setChecked(False)  # the test preferences file is shared: leave it off
        self.window.close()

    def monitoring(self):
        self.window.monitor.calibration = object()
        self.window.start()
        self.window.show_page("current")

    def send(self, **changes):
        changes.setdefault("posture_enabled", True)
        self.window._on_update(update(**changes))

    def test_off_until_ticked(self):
        self.window.settings_page.posture.setChecked(False)
        self.assertEqual(self.page.posture_indicator.text.text(), "Posture monitoring is off")
        self.assertFalse(self.page.posture_button.isEnabled())
        self.assertFalse(self.window.monitor.posture_enabled)
        self.window.settings_page.posture.setChecked(True)
        self.assertTrue(self.window.monitor.posture_enabled)  # camera off: applied directly
        self.assertTrue(self.page.posture_button.isEnabled())
        from ocusense.preferences import Preferences
        self.assertTrue(Preferences.load().posture_monitoring)  # remembered

    def test_tick_while_monitoring_goes_to_the_camera_thread(self):
        self.monitoring()
        self.window.settings_page.posture.setChecked(False)
        self.assertEqual(self.thread.posture_enabled_requests, [False])
        self.send(posture_enabled=False, posture_cal_status=PostureCalibration.RUNNING)  # frames while off
        self.assertEqual(self.page.posture_indicator.text.text(), "Posture monitoring is off")

    def test_every_session_starts_with_a_new_baseline(self):
        from ocusense.core.models import PostureBaseline
        from ocusense.core.posture import PostureMonitor
        self.monitoring()
        self.assertEqual(self.thread.posture_calibration_requests, 1)  # session 1 starts
        self.window.monitor.posture_monitor = PostureMonitor(PostureBaseline(0.0, 0.0, 60.0, 0.5, 0.3))
        self.window.pause()
        self.window.resume()
        self.assertEqual(self.thread.posture_calibration_requests, 1)  # resumed with a baseline: kept
        self.window.stop()
        self.window.start()
        self.assertEqual(self.thread.posture_calibration_requests, 2)  # session 2: a fresh minute, baseline or not

    def test_button_needs_a_running_session(self):
        self.page.posture_button.click()
        self.assertEqual(self.thread.posture_calibration_requests, 0)
        self.assertIn("Start a session first", self.page.posture_detail.text())

    def test_button_asks_the_camera_thread(self):
        self.monitoring()
        self.assertEqual(self.thread.posture_calibration_requests, 1)  # monitoring started without a baseline
        self.page.posture_button.click()
        self.assertEqual(self.thread.posture_calibration_requests, 2)
        self.assertEqual(self.thread.calibration_requests, 0)  # the eye calibration isn't touched
        self.assertEqual(self.window.state, "monitoring")

    def test_calibrating_then_good_then_poor(self):
        self.monitoring()
        self.assertEqual(self.page.posture_button.text(), "Recalibrate posture")
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=80.4)
        self.assertEqual(self.page.posture_indicator.text.text(), "Calibrating posture: 1:20 left")
        self.assertIn("sit up straight", self.page.posture_detail.text())

        good = PostureStatus(tracked=True, pitch_change=-2.0, roll_change=1.0, distance_cm=63.0,
                             baseline_distance_cm=65.0, centre_drop=0.01, size_ratio=1.02, lid_change=3.0)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=good)
        self.assertEqual(self.page.posture_indicator.text.text(), "Good posture")
        self.assertIn("head 2° higher", self.page.posture_detail.text())
        self.assertIn("about 63 cm away (calibrated 65 cm)", self.page.posture_detail.text())
        self.assertIn("screen tilted 3° back (corrected)", self.page.posture_detail.text())

        brief = PostureStatus(tracked=True, outside=(HEAD_DROPPED,), longest_outside=4.0, pitch_change=20.0,
                              roll_change=0.0, centre_drop=0.0)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=brief)
        self.assertEqual(self.page.posture_indicator.text.text(), "Good · head dropped for 4 s")

        poor = PostureStatus(tracked=True, poor=True, problems=(HEAD_DROPPED, SLUMPED), outside=(HEAD_DROPPED, SLUMPED),
                             longest_outside=31.0, pitch_change=20.0, roll_change=0.0, centre_drop=0.1)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=poor)
        self.assertEqual(self.page.posture_indicator.text.text(), "Poor posture: head dropped, slumped")
        self.assertEqual(self.page.posture_indicator.glyph.kind, "warning")

    def test_screen_tilt_asks_you_to_recalibrate(self):
        self.monitoring()
        requests = self.thread.posture_calibration_requests
        self.send(events=[SCREEN_TILTED], posture_cal_status=PostureCalibration.DONE, posture_needs_recalibration=True)
        message = TILT_MESSAGE
        self.assertEqual(self.notifications, [("OcuSense", message)])
        self.assertIn(message, self.window.study.message_label.text())
        self.assertFalse(self.window.tilt_holder.isHidden())  # the card with "Recalibrate now"
        self.assertEqual(self.page.posture_indicator.text.text(), "Screen angle changed. Recalibrate your posture")
        self.assertEqual(self.thread.posture_calibration_requests, requests)  # nothing recalibrates by itself
        self.send(posture_cal_status=PostureCalibration.DONE, posture_needs_recalibration=True)
        self.assertEqual(len(self.notifications), 1)  # once per tilt
        self.window.tilt_banner.buttons["Recalibrate now"].click()
        self.assertEqual(self.thread.posture_calibration_requests, requests + 1)
        self.assertTrue(self.window.tilt_holder.isHidden())

    def test_not_now_keeps_waiting(self):
        self.monitoring()
        requests = self.thread.posture_calibration_requests
        self.send(events=[SCREEN_TILTED], posture_cal_status=PostureCalibration.DONE, posture_needs_recalibration=True)
        self.window.tilt_banner.buttons["Not now"].click()
        self.assertTrue(self.window.tilt_holder.isHidden())
        self.assertEqual(self.thread.posture_calibration_requests, requests)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_needs_recalibration=True)
        self.assertTrue(self.window.tilt_holder.isHidden())  # not shown again until the next tilt
        self.assertEqual(self.page.posture_indicator.text.text(), "Screen angle changed. Recalibrate your posture")

    def test_poor_posture_sends_the_message_once(self):
        self.monitoring()
        poor = PostureStatus(tracked=True, poor=True, problems=(SLUMPED,), outside=(SLUMPED,), longest_outside=30.0,
                             pitch_change=5.0, roll_change=0.0, centre_drop=0.1)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=poor)
        self.send(posture_cal_status=PostureCalibration.DONE, posture_status=poor)
        self.assertFalse(self.window.posture_holder.isHidden())  # the card in the window
        self.assertEqual(self.window.posture_banner.title.text(),
                         "Stop slouching, hunchbacks are not particularly sexy you know")
        self.assertIn("Stop slouching", self.window.study.message_label.text())
        self.assertLessEqual(len(self.notifications), 1)  # a Mac notification only when OcuSense is in the background
        self.send(posture_cal_status=PostureCalibration.DONE,
                  posture_status=PostureStatus(tracked=True, pitch_change=0.0, centre_drop=0.0))
        self.assertTrue(self.window.posture_holder.isHidden())  # sat up: the card goes away

    def test_no_posture_message_when_off(self):
        self.monitoring()
        poor = PostureStatus(tracked=True, poor=True, problems=(SLUMPED,), pitch_change=0.0, centre_drop=0.1)
        self.send(posture_enabled=False, posture_status=poor)
        self.assertEqual(self.notifications, [])

    def test_calibration_card_with_countdown(self):
        from ocusense.monitoring.pipeline import POSTURE_CALIBRATION_DONE
        self.monitoring()
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=42)
        self.assertFalse(self.window.posture_cal_holder.isHidden())
        self.assertEqual(self.window.posture_cal_banner.title.text(), "Calibrating posture: please sit up straight")
        self.assertIn("0:42 left", self.window.posture_cal_banner.body.text())
        self.send(posture_cal_status=PostureCalibration.DONE, events=[POSTURE_CALIBRATION_DONE],
                  posture_status=PostureStatus(tracked=True, pitch_change=0.0, centre_drop=0.0))
        self.assertTrue(self.window.posture_cal_holder.isHidden())
        self.assertIn("Posture recorded. I'll tell you when you slouch", self.window.study.message_label.text())

    def test_got_it_hides_the_card_until_the_next_recording(self):
        self.monitoring()
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=50)
        self.window.posture_cal_banner.buttons["Got it"].click()
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=49)
        self.assertTrue(self.window.posture_cal_holder.isHidden())  # still recording, card stays away
        self.send(posture_cal_status=PostureCalibration.DONE)
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=60)  # a new recording
        self.assertFalse(self.window.posture_cal_holder.isHidden())

    def test_a_failed_baseline_says_it_tries_again(self):
        from ocusense.monitoring.pipeline import POSTURE_CALIBRATION_FAILED
        self.monitoring()
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=1)
        self.send(posture_cal_status=PostureCalibration.RUNNING, posture_cal_seconds_left=60,
                  events=[POSTURE_CALIBRATION_FAILED], posture_cal_error="Your face wasn't seen clearly enough.")
        self.assertIn("Couldn't record your posture: Your face wasn't seen clearly enough. Trying again.",
                      self.window.study.message_label.text())
        self.assertIn("The last try didn't work", self.page.posture_detail.text())

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
