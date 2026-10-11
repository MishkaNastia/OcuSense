"""Games: the top-right field with the Pomodoro break left, or "Get back to work my little genius"."""

import unittest

from tests.test_main_window import MODEL_PATH, FakeThread  # offscreen Qt; files go to a temporary folder

from ocusense.core.pomodoro import FOCUS, PAUSED, SHORT_BREAK, PomodoroSettings, PomodoroTimer


def timer_in_break(now: float) -> PomodoroTimer:
    """A timer whose 25-minute focus round ended at `now`, with the 5-minute break started automatically."""
    timer = PomodoroTimer(PomodoroSettings(auto_start_breaks=True))
    timer.start(now - 25 * 60)
    timer.tick(now)
    return timer


class BreakRemainingTest(unittest.TestCase):
    def test_no_break_while_focusing(self):
        timer = PomodoroTimer()
        self.assertIsNone(timer.break_remaining(0.0))  # ready to focus
        timer.start(0.0)
        self.assertIsNone(timer.break_remaining(60.0))  # focusing

    def test_running_and_paused_break(self):
        timer = timer_in_break(1500.0)
        self.assertEqual(timer.phase, SHORT_BREAK)
        self.assertAlmostEqual(timer.break_remaining(1560.0), 240.0)  # 1 of 5 minutes gone
        timer.pause(1560.0)
        self.assertEqual(timer.state, PAUSED)
        self.assertAlmostEqual(timer.break_remaining(1700.0), 240.0)  # paused: the clock stops

    def test_a_break_that_hasnt_started_isnt_on(self):
        timer = PomodoroTimer(PomodoroSettings(auto_start_breaks=False))
        timer.start(0.0)
        timer.tick(25 * 60.0)
        self.assertEqual(timer.phase, SHORT_BREAK)
        self.assertIsNone(timer.break_remaining(25 * 60.0 + 10))
        timer.skip(25 * 60.0 + 10)
        self.assertEqual(timer.phase, FOCUS)
        self.assertIsNone(timer.break_remaining(25 * 60.0 + 20))


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class BreakFieldTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.window.resize(1200, 900)
        self.window.show()
        self.window.show_page("games")
        self.page = self.window.games_page
        self.field = self.page.break_field

    def tearDown(self):
        self.window.close()

    def test_only_while_a_game_is_open(self):
        self.page.update_break_field()
        self.assertTrue(self.field.isHidden())  # the game list
        self.page.open_eye_runner()
        self.assertFalse(self.field.isHidden())
        self.page.show_hub()
        self.assertTrue(self.field.isHidden())

    def test_no_break_means_back_to_work(self):
        self.page.open_blink_code()
        self.assertEqual(self.field.text(), "Get back to work my little genius")

    def test_break_time_left_top_right(self):
        import time
        self.window.pomodoro_page.timer = timer_in_break(time.monotonic() - 60)  # a break that started 1 min ago
        self.page.open_blink_garden()
        self.assertEqual(self.field.text(), "Break: 04:00 left")
        right = self.field.x() + self.field.width()
        self.assertGreater(right, self.page.viewport().width() - 60)  # in the top-right corner
        self.assertLess(self.field.y(), 60)
        self.window.pomodoro_page.timer.pause(time.monotonic())
        self.page.update_break_field()
        self.assertTrue(self.field.text().startswith("Break paused: 04:0"))


if __name__ == "__main__":
    unittest.main()
