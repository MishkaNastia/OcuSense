"""The 20-20-20 eye rest: counts screen time while monitoring, pauses count as rest, the card counts down."""

import os
import unittest

from ocusense.core.eye_rest import EyeRestTimer


def run(timer, start, seconds, monitoring, step=0.25):
    due, t = 0, start
    while t < start + seconds:
        t += step
        due += timer.update(t, monitoring)
    return due, t


class EyeRestTimerTest(unittest.TestCase):
    def test_due_after_the_interval_of_monitoring(self):
        timer = EyeRestTimer(20)
        due, t = run(timer, 0, 20 * 60 - 1, True)
        self.assertEqual(due, 0)
        due, t = run(timer, t, 2, True)
        self.assertEqual(due, 1)
        self.assertLess(timer.screen_seconds, 2)  # counting started over (the rest of the loop adds a little)

    def test_a_pause_of_20_s_is_a_rest(self):
        timer = EyeRestTimer(20)
        _, t = run(timer, 0, 15 * 60, True)
        _, t = run(timer, t, 25, False)  # e.g. a Pomodoro break
        due, t = run(timer, t, 10 * 60, True)
        self.assertEqual(due, 0)  # the earlier 15 min no longer count

    def test_a_short_pause_does_not_reset(self):
        timer = EyeRestTimer(20)
        _, t = run(timer, 0, 15 * 60, True)
        _, t = run(timer, t, 5, False)
        due, _ = run(timer, t, 5 * 60 + 1, True)
        self.assertEqual(due, 1)

    def test_a_stalled_clock_never_adds_minutes(self):
        timer = EyeRestTimer(20)
        timer.update(0, True)
        self.assertFalse(timer.update(30 * 60, True))  # e.g. the Mac slept
        self.assertLessEqual(timer.screen_seconds, 5)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread, update  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class EyeRestWindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        for key in ("OCUSENSE_PREFERENCES_FILE",):
            path = os.environ.get(key)
            if path and os.path.exists(path):
                os.remove(path)
        self.window = MainWindow()
        self.sent = []
        self.window.notify = lambda message, title: self.sent.append((title, message))
        self.window._start_camera = lambda: (setattr(self.window, "thread", FakeThread()), True)[1]
        self.window.monitor.calibration = object()
        self.window.settings_page.eye_rest.setChecked(True)  # off by default
        self.window.start()

    def tearDown(self):
        self.window.close()
        path = os.environ.get("OCUSENSE_PREFERENCES_FILE")
        if path and os.path.exists(path):
            os.remove(path)

    def test_card_with_countdown_and_notification(self):
        w = self.window
        w.eye_rest.screen_seconds = w.eye_rest.interval  # 20 minutes of screen time
        w._check_eye_rest(1000.0)
        w._check_eye_rest(1000.25)
        card = w.eye_rest_card
        self.assertFalse(card.isHidden())
        self.assertEqual(self.sent[0][0], "Time for a 20-second eye rest")  # the window isn't active in tests
        card.banner.buttons["Start 20 s"].click()
        self.assertIn("20", card.banner.title.text())
        for _ in range(20):
            card._count()
        self.assertIn("Nice", card.banner.title.text())
        card._close("done")
        self.assertTrue(card.isHidden())
        self.assertEqual(w.state, "monitoring")  # the reminder never interrupts monitoring

    def test_waits_while_the_distance_reminder_is_shown(self):
        w = self.window
        w.banner_holder.setVisible(True)
        w.eye_rest.screen_seconds = w.eye_rest.interval
        w._check_eye_rest(1000.0)
        w._check_eye_rest(1000.25)
        self.assertTrue(w.eye_rest_card.isHidden())  # no stacking
        w.banner_holder.setVisible(False)
        w._check_eye_rest(1000.5)
        self.assertFalse(w.eye_rest_card.isHidden())

    def test_off_by_default_and_the_switch_is_remembered(self):
        from ocusense.preferences import Preferences
        self.assertFalse(Preferences().eye_rest)
        w = self.window
        self.assertEqual(w.eye_rest.interval, 20 * 60)  # fixed: the "20" of 20-20-20
        w.settings_page.eye_rest.setChecked(False)
        w.eye_rest.screen_seconds = 10 ** 6
        w._check_eye_rest(1000.0)
        self.assertTrue(w.eye_rest_card.isHidden())  # off: nothing appears
        from ocusense.ui.main_window import MainWindow
        again = MainWindow()
        self.addCleanup(again.close)
        self.assertFalse(again.settings_page.eye_rest.isChecked())
        again.settings_page.eye_rest.setChecked(True)
        third = MainWindow()
        self.addCleanup(third.close)
        self.assertTrue(third.settings_page.eye_rest.isChecked())


if __name__ == "__main__":
    unittest.main()
