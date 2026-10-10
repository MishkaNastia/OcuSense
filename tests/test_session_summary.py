"""The end-of-session summary card."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.helpers import Observer  # noqa: E402
from tests.test_main_window import MODEL_PATH, FakeThread, update  # noqa: E402

from ocusense.core.session import SessionRecorder  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class SessionSummaryTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.window._start_camera = lambda: (setattr(self.window, "thread", FakeThread()), True)[1]
        self.window.monitor.calibration = object()

    def tearDown(self):
        if self.window.summary_card is not None:
            self.window.summary_card.done(0)
        self.window.close()

    def run_session(self, seconds):
        w = self.window
        w.start()
        t0 = time.monotonic() - seconds
        w.recorder = SessionRecorder(t0)
        observe = Observer()
        for i in range(int(seconds * 30)):
            t = t0 + i / 30
            v = 0.05 if 1.0 <= t % 4 < 1.2 else 0.9
            o = observe(t, v)
            w._on_update(update(now=t, openness=(v, v, v), blinked=o.blink_completed, observation=o))

    def test_card_after_stop_with_the_session_numbers(self):
        w = self.window
        self.run_session(60)
        w.session_extras.distance_reminders = 2
        w.session_extras.eye_rests = 1
        w.session_extras.focus_rounds = 1
        w.stop()
        card = w.summary_card
        self.assertIsNotNone(card)
        self.assertTrue(card.isVisible() or not w.isVisible())
        summary = w.store.all()[-1]
        self.assertEqual(card.values["blinks"], str(summary.blinks))
        self.assertTrue(card.values["rate"].endswith("blinks/min"))
        self.assertEqual(card.values["focus"], "1")
        self.assertEqual(card.values["reminders"], "2 distance reminders, 1 eye-rest reminder")
        self.assertEqual(w.state, "ready")

    def test_see_statistics_and_short_sessions(self):
        w = self.window
        w.start()
        w.stop()  # a few seconds: not kept, no card
        self.assertIsNone(w.summary_card)
        self.run_session(30)
        w.stop()
        w.summary_card.see_statistics.emit()
        self.assertIs(w.pages.currentWidget(), w.stats_page)

    def test_counts_start_fresh_each_session(self):
        w = self.window
        self.run_session(20)
        w.session_extras.eye_rests = 3
        w.stop()
        w.summary_card.done(0)
        w.start()  # a new session
        self.assertEqual(w.session_extras.eye_rests, 0)


if __name__ == "__main__":
    unittest.main()
