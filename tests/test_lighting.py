"""The lighting check: a sustained dark room suggests a lamp; never stacked, off by default."""

import os
import unittest

import numpy as np

from ocusense.core.lighting import LightingMonitor


def feed(monitor, start, seconds, brightness, fps=30):
    fired, t = [], start
    for i in range(int(seconds * fps)):
        t = start + i / fps
        if monitor.update(t, brightness):
            fired.append(t)
    return fired, t


class LightingRulesTest(unittest.TestCase):
    def test_reminds_after_a_minute_of_darkness(self):
        m = LightingMonitor()
        self.assertEqual(feed(m, 0, 59, 30)[0], [])
        fired, _ = feed(m, 59, 5, 30)
        self.assertEqual(len(fired), 1)
        self.assertTrue(m.dark)

    def test_light_clears_and_cooldown_limits(self):
        m = LightingMonitor()
        feed(m, 0, 61, 30)
        feed(m, 61, 2, 120)  # lamp on
        self.assertFalse(m.dark)
        self.assertEqual(feed(m, 63, 120, 30)[0], [])  # dark again within 30 minutes: quiet
        self.assertEqual(len(feed(m, 30 * 60 + 10, 61, 30)[0]), 1)

    def test_in_between_neither_counts_nor_clears(self):
        m = LightingMonitor()
        feed(m, 0, 61, 30)
        feed(m, 61, 5, 65)  # between the two levels
        self.assertTrue(m.dark)

    def test_brightness_from_a_frame(self):
        from ocusense.monitoring.camera_worker import picture_brightness
        self.assertAlmostEqual(picture_brightness(np.full((480, 640, 3), 200, np.uint8)), 200, delta=1)
        self.assertAlmostEqual(picture_brightness(np.zeros((480, 640, 3), np.uint8)), 0, delta=1)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread, update  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class LightingWindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        path = os.environ.get("OCUSENSE_PREFERENCES_FILE")
        if path and os.path.exists(path):
            os.remove(path)
        self.window = MainWindow()
        self.sent = []
        self.window.notify = lambda message, title: self.sent.append((title, message))
        self.window._start_camera = lambda: (setattr(self.window, "thread", FakeThread()), True)[1]
        self.window.monitor.calibration = object()
        self.window.start()

    def tearDown(self):
        self.window.close()
        path = os.environ.get("OCUSENSE_PREFERENCES_FILE")
        if path and os.path.exists(path):
            os.remove(path)

    def frames(self, start, seconds, brightness):
        for i in range(int(seconds * 10)):
            self.window._on_update(update(now=start + i / 10, brightness=brightness))
        return start + seconds

    def test_off_by_default(self):
        self.assertFalse(self.window.settings_page.lighting.isChecked())
        self.frames(1000, 65, 20)
        self.assertTrue(self.window.lighting_card.isHidden())

    def test_card_notification_and_clearing(self):
        w = self.window
        w.settings_page.lighting.setChecked(True)
        t = self.frames(1000, 65, 20)
        self.assertFalse(w.lighting_card.isHidden())
        self.assertEqual(self.sent[0][0], "Your room looks quite dark")
        self.assertEqual(w.session_extras.lighting_reminders, 1)
        self.frames(t, 1, 150)  # a lamp goes on
        self.assertTrue(w.lighting_card.isHidden())
        self.assertEqual(w.state, "monitoring")

    def test_never_on_top_of_another_reminder_and_turn_off(self):
        w = self.window
        w.settings_page.lighting.setChecked(True)
        w.banner_holder.setVisible(True)  # the distance reminder is showing…
        w.proximity.too_close = True  # …because the person really is too close
        t = self.frames(1000, 65, 20)
        self.assertTrue(w.lighting_card.isHidden())
        w.proximity.too_close = False
        w.banner_holder.setVisible(False)
        self.frames(t, 0.2, 20)
        self.assertFalse(w.lighting_card.isHidden())
        w.lighting_card.banner.buttons["Turn off"].click()
        self.assertFalse(w.settings_page.lighting.isChecked())
        self.assertFalse(w.preferences.lighting_check)


if __name__ == "__main__":
    unittest.main()
