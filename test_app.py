"""Checks for the PySide6 window, without a camera. Run with:  python -m unittest

The window is driven with fake camera updates, in Qt's invisible "offscreen" mode.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.core.monitor import CALIBRATION_DONE, CALIBRATION_FAILED, MODEL_PATH  # noqa: E402
from ocusense.app.worker import MonitorUpdate  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeThread:
    """Stands in for MonitorThread: no camera, no background thread."""

    def __init__(self):
        self.calibration_requests = 0
        self.stopped = False

    def request_calibration(self):
        self.calibration_requests += 1

    def requestInterruption(self):
        self.stopped = True

    def wait(self, ms):
        return True


def update(**changes):
    preview = QImage(480, 360, QImage.Format.Format_RGB888)
    preview.fill(QColor("#888888"))
    values = dict(now=100.0, face_found=True, reliable=True, reason="", openness=(0.9, 0.9, 0.9),
                  blinked=False, events=[], blinks=0, calibrated=True, cal_status="running",
                  cal_step=0, cal_measuring=False, cal_seconds_left=2.4, cal_error="",
                  samples=[], preview=preview)
    values.update(changes)
    return MonitorUpdate(**values)


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class WindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.app.window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = self._fake_start

    def tearDown(self):
        self.window.close()

    def _fake_start(self):
        self.window.thread = self.thread
        return True

    def visible_buttons(self):
        w = self.window
        names = {"Start": w.start_button, "Pause": w.pause_button, "Resume": w.resume_button,
                 "Stop": w.stop_button, "Recalibrate": w.recalibrate_button}
        return sorted(name for name, button in names.items() if not button.isHidden())

    def test_starts_ready(self):
        self.assertEqual(self.window.state, "ready")
        self.assertEqual(self.visible_buttons(), ["Start"])

    def test_first_start_calibrates_then_monitors(self):
        w = self.window
        w.start()
        self.assertEqual(w.state, "calibrating")
        self.assertEqual(self.thread.calibration_requests, 1)
        w._on_update(update(cal_step=1, cal_seconds_left=3.2))
        self.assertIn("STEP 2 OF 3", w.cal_eyebrow.text())
        self.assertEqual(w.cal_count.text(), "4")
        w.monitor.calibration = object()
        w._on_update(update(events=[CALIBRATION_DONE]))
        self.assertEqual(w.state, "monitoring")
        self.assertEqual(self.visible_buttons(), ["Pause", "Recalibrate", "Stop"])

    def test_failed_calibration_offers_try_again(self):
        w = self.window
        w.start()
        w._on_update(update(events=[CALIBRATION_FAILED], cal_status="failed", cal_error="Too similar."))
        self.assertEqual(w.state, "calibrating")
        self.assertIn("Too similar.", w.cal_error.text())
        self.assertFalse(w.try_again_button.isHidden())

    def test_monitoring_updates_count_and_status(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        samples = [(99.0 + i * 0.1, (0.9, 0.9, 0.9 if i % 5 else 0.1), i % 5 == 1) for i in range(10)]
        w._on_update(update(blinks=3, samples=samples))
        self.assertEqual(w.blink_label.text(), "3 blinks this session")
        self.assertEqual(w.status.text.text(), "Monitoring")
        w._on_update(update(face_found=False, openness=None))
        self.assertEqual(w.status.text.text(), "Face not tracked")
        self.assertFalse(w.graph.grab().isNull())  # the graph paints without errors

    def test_pause_turns_camera_off_and_resume_keeps_calibration(self):
        w = self.window
        calibration = object()
        w.monitor.calibration = calibration
        w.start()
        w.pause()
        self.assertTrue(self.thread.stopped)
        self.assertIsNone(w.thread)
        self.assertEqual(self.visible_buttons(), ["Resume", "Stop"])
        w.resume()
        self.assertEqual(w.state, "monitoring")
        self.assertIs(w.monitor.calibration, calibration)

    def test_stop_resets_session_but_keeps_calibration(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w.monitor.counter.count = 5
        w.stop()
        self.assertEqual(w.state, "ready")
        self.assertEqual(w.monitor.counter.count, 0)
        self.assertEqual(w.timer_label.text(), "00:00:00")
        self.assertEqual(self.visible_buttons(), ["Recalibrate", "Start"])

    def test_late_update_after_stop_is_ignored(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w.stop()
        w._on_update(update(blinks=9))
        self.assertEqual(w.blink_label.text(), "0 blinks this session")

    def test_frame_from_an_old_camera_run_is_ignored(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w._on_update(update(blinks=9, source=FakeThread()))  # not the current run
        self.assertEqual(w.blink_label.text(), "0 blinks this session")
        w._on_update(update(blinks=4, source=self.thread))
        self.assertEqual(w.blink_label.text(), "4 blinks this session")


if __name__ == "__main__":
    unittest.main()
