"""The Pomodoro timer, its remembered settings, and the page in the window."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from ocusense.core.pomodoro import (
    FOCUS, IDLE, LONG_BREAK, PAUSED, RUNNING, SHORT_BREAK, PomodoroSettings, PomodoroTimer,
)
from ocusense.preferences import Preferences


def run_through(timer, start, seconds, step=0.25):
    """Tick the timer every `step` seconds; returns the PhaseEnded events and the end time."""
    events, t = [], start
    while t < start + seconds:
        t += step
        ended = timer.tick(t)
        if ended:
            events.append(ended)
    return events, t


class TimerTest(unittest.TestCase):
    def test_cycle_with_long_break_after_n_rounds(self):
        timer = PomodoroTimer(PomodoroSettings(1, 1, 2, 2, auto_start_breaks=True, auto_start_focus=True))
        timer.start(0)
        events, _ = run_through(timer, 0, 60 * 1 + 60 + 60 + 120 + 1)
        self.assertEqual([(e.phase, e.next_phase) for e in events],
                         [(FOCUS, SHORT_BREAK), (SHORT_BREAK, FOCUS), (FOCUS, LONG_BREAK), (LONG_BREAK, FOCUS)])
        self.assertEqual(timer.completed_focus, 2)
        self.assertEqual(timer.round_in_cycle, 1)  # a new cycle after the long break

    def test_phase_ends_exactly_on_time(self):
        timer = PomodoroTimer(PomodoroSettings(1, 1, 1, 2, auto_start_breaks=True))
        timer.start(0)
        timer.tick(60.2)  # checked a little late
        self.assertEqual(timer.phase, SHORT_BREAK)
        self.assertAlmostEqual(timer.remaining(60.2), 60 - 0.2)  # the break started at 60.0, not 60.2

    def test_waits_for_start_without_auto_start(self):
        timer = PomodoroTimer(PomodoroSettings(1, 1, 1, 2, auto_start_breaks=False))
        timer.start(0)
        ended = timer.tick(60)
        self.assertFalse(ended.started_automatically)
        self.assertEqual((timer.phase, timer.state), (SHORT_BREAK, IDLE))
        self.assertEqual(timer.remaining(500), 60)  # nothing counts until Start

    def test_pause_and_resume(self):
        timer = PomodoroTimer(PomodoroSettings(25))
        timer.start(0)
        timer.pause(100)
        self.assertEqual(timer.state, PAUSED)
        self.assertEqual(timer.remaining(5000), 1400)  # time stands still while paused
        timer.resume(5000)
        self.assertEqual(timer.remaining(5100), 1300)
        self.assertAlmostEqual(timer.focus_time(5100), 200)

    def test_skip_does_not_count_as_completed(self):
        timer = PomodoroTimer(PomodoroSettings(25, 5, 15, 4))
        timer.start(0)
        ended = timer.skip(30)
        self.assertFalse(ended.completed)
        self.assertEqual(timer.completed_focus, 0)
        self.assertAlmostEqual(timer.focus_seconds, 30)  # the time spent still counts as focus time
        self.assertEqual(timer.phase, SHORT_BREAK)

    def test_reset_keeps_finished_rounds(self):
        timer = PomodoroTimer(PomodoroSettings(1, 1, 1, 4, auto_start_breaks=True))
        timer.start(0)
        run_through(timer, 0, 61)
        timer.reset()
        self.assertEqual((timer.phase, timer.state, timer.round_in_cycle), (FOCUS, IDLE, 1))
        self.assertEqual(timer.completed_focus, 1)

    def test_changing_lengths_mid_phase(self):
        timer = PomodoroTimer(PomodoroSettings(25))
        timer.start(0)
        timer.apply_settings(PomodoroSettings(30), 600)
        self.assertEqual(timer.remaining(600), 1200)  # 10 min spent of the new 30
        timer.apply_settings(PomodoroSettings(5), 700)  # shorter than already spent: ends at the next tick
        self.assertIsNotNone(timer.tick(701))

    def test_settings_are_kept_in_range(self):
        s = PomodoroSettings(0, 500, -3, 99).clamped()
        self.assertEqual((s.focus_minutes, s.short_break_minutes, s.long_break_minutes, s.rounds_before_long_break),
                         (1, 30, 1, 8))


class PreferencesTest(unittest.TestCase):
    def test_round_trip_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            prefs = Preferences()
            prefs.set_pomodoro(PomodoroSettings(50, 10, 30, 3, auto_start_breaks=False))
            prefs.animations = False
            prefs.save(path)
            loaded = Preferences.load(path)
            self.assertEqual(loaded.pomodoro(), PomodoroSettings(50, 10, 30, 3, auto_start_breaks=False))
            self.assertFalse(loaded.animations)
            path.write_text(json.dumps({"focus_minutes": 999, "short_break_minutes": "5", "animations": "no"}))
            loaded = Preferences.load(path)
            self.assertEqual((loaded.focus_minutes, loaded.short_break_minutes, loaded.animations), (25, 5, True))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread, app  # noqa: E402  (also points files at a temp folder)


def _settings_files():
    """The files the app uses right now (the test helpers may have been loaded twice under different names)."""
    return [os.environ[k] for k in ("OCUSENSE_PREFERENCES_FILE", "OCUSENSE_CALIBRATION_FILE") if k in os.environ]


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class PomodoroPageTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        for path in _settings_files():  # every test starts from the defaults
            if os.path.exists(path):
                os.remove(path)
        self.window = MainWindow()
        self.page = self.window.pomodoro_page
        self.clock = [1000.0]
        self.page.now = lambda: self.clock[0]  # a controllable clock
        self.sent = []
        self.window.notify = lambda message, title: self.sent.append((title, message))
        self.thread = FakeThread()  # Start also starts eye monitoring: never the real camera in tests
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]

    def tearDown(self):
        self.window.close()
        for path in _settings_files():
            if os.path.exists(path):
                os.remove(path)

    def advance(self, seconds):
        self.clock[0] += seconds
        self.page.tick()

    def test_in_the_sidebar_with_the_time_left(self):
        w = self.window
        w.sidebar.items["pomodoro"].click()
        self.assertIs(w.pages.currentWidget(), self.page)
        self.assertEqual(w.sidebar.items["pomodoro"].text(), "Pomodoro")
        self.page.main_button.click()  # Start
        self.advance(65)
        self.assertEqual(w.sidebar.items["pomodoro"].text(), "Pomodoro · 23:55")
        self.page.main_button.click()  # Pause
        self.assertEqual(w.sidebar.items["pomodoro"].text(), "Pomodoro · paused")
        self.assertFalse(self.page.dial.grab().isNull())

    def test_phase_end_notifies_when_not_in_view(self):
        self.page.spins["focus_minutes"].setValue(1)
        self.page.main_button.click()
        self.advance(61)
        self.assertEqual(self.page.timer.phase, SHORT_BREAK)
        self.assertEqual(self.sent[0][0], "Focus round done")  # the window isn't active in tests

    def test_settings_presets_and_animations_are_remembered(self):
        self.page.presets.buttons["deep"].click()
        self.assertEqual(self.page.spins["focus_minutes"].value(), 50)
        self.assertEqual(self.page.timer.settings.short_break_minutes, 10)
        self.page.spins["focus_minutes"].setValue(40)
        self.assertEqual(self.page.presets.current(), "custom")
        self.page.checks["animations"].setChecked(False)
        self.assertFalse(self.page.dial.animate)
        from ocusense.ui.main_window import MainWindow
        again = MainWindow()  # next launch
        self.addCleanup(again.close)
        self.assertEqual(again.pomodoro_page.spins["focus_minutes"].value(), 40)
        self.assertFalse(again.pomodoro_page.checks["animations"].isChecked())

    def test_runs_alongside_monitoring(self):
        w = self.window
        thread = FakeThread()
        w._start_camera = lambda: (setattr(w, "thread", thread), True)[1]
        w.monitor.calibration = object()
        w.start()
        w.show_page("pomodoro")
        self.page.main_button.click()
        self.advance(30)
        w.show_page("study")
        self.advance(30)
        self.assertEqual(w.state, "monitoring")
        self.assertEqual(self.page.timer.state, RUNNING)  # keeps running on other pages
        self.assertFalse(thread.stopped)

    def test_focus_runs_monitoring_and_breaks_pause_it(self):
        w = self.window
        thread = FakeThread()
        w._start_camera = lambda: (setattr(w, "thread", thread), True)[1]
        w.monitor.calibration = object()  # already calibrated
        self.page.spins["focus_minutes"].setValue(1)
        self.page.main_button.click()  # Start the focus round
        self.assertEqual(w.state, "monitoring")
        self.advance(61)  # → short break (auto-starts)
        self.assertEqual(w.state, "paused")
        self.assertIn("break", w.study.message_label.text())
        self.page._skip()  # → focus waits for Start (auto_start_focus is off)
        self.page.main_button.click()
        self.assertEqual(w.state, "monitoring")
        self.page.main_button.click()  # Pause the Pomodoro
        self.assertEqual(w.state, "paused")

    def test_link_can_be_switched_off(self):
        w = self.window
        w._start_camera = lambda: (setattr(w, "thread", FakeThread()), True)[1]
        w.monitor.calibration = object()
        self.page.checks["pomodoro_monitoring"].setChecked(False)
        self.page.main_button.click()
        self.assertEqual(w.state, "ready")


if __name__ == "__main__":
    unittest.main()
