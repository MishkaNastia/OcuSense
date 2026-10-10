"""The menu-bar menu: status text and actions that call the window's own controls."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class MenuBarTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.window.monitor.calibration = object()
        self.menu = self.window.menu_bar

    def tearDown(self):
        if self.window.summary_card is not None:
            self.window.summary_card.done(0)
        self.window.close()

    def test_icon_is_a_template_image(self):
        from ocusense.ui.menu_bar import template_icon
        self.assertTrue(template_icon().isMask())

    def test_monitoring_controls_follow_the_state(self):
        w, m = self.window, self.menu
        m.refresh()
        self.assertEqual((m.status.text(), m.monitor_action.text()), ("Ready", "Start monitoring"))
        self.assertFalse(m.stop_action.isEnabled())
        m.monitor_action.trigger()
        self.assertEqual(w.state, "monitoring")
        m.refresh()
        self.assertTrue(m.status.text().startswith("Monitoring · 00:00:0"))
        self.assertEqual(m.monitor_action.text(), "Pause monitoring")
        m.monitor_action.trigger()
        self.assertEqual(w.state, "paused")
        m.refresh()
        self.assertEqual(m.monitor_action.text(), "Resume monitoring")
        m.stop_action.trigger()
        self.assertEqual(w.state, "ready")

    def test_pomodoro_from_the_menu(self):
        m = self.menu
        m.refresh()
        self.assertFalse(m.pomodoro_status.isVisible())
        m.pomodoro_action.trigger()  # start a focus round
        m.refresh()
        self.assertTrue(m.pomodoro_status.text().startswith("Pomodoro · Focus 2"))
        self.assertEqual(m.pomodoro_action.text(), "Pause Pomodoro")


if __name__ == "__main__":
    unittest.main()
