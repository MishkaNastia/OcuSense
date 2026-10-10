"""Statistics › Current session and Settings: the comparison with the saved reference (no camera, offscreen)."""

import os

os.environ["OCUSENSE_NO_NOTIFICATIONS"] = "1"  # never show a real notification from the tests
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from tests.test_main_window import FakeThread, update  # noqa: E402  (offscreen Qt, temporary recordings folder)

from ocusense import reference as reference_file  # noqa: E402
from ocusense.core.session import SessionRecorder  # noqa: E402
from ocusense.monitoring.pipeline import MODEL_PATH  # noqa: E402
from tests.helpers import Observer  # noqa: E402


def onsets(seconds, factor=1.0):
    """Blink onsets with intervals cycling 2, 3, 4, 5 s (times `factor`)."""
    result, t, i = [], 1.0, 0
    while t < seconds:
        result.append(t)
        t += (2.0 + i % 4) * factor
        i += 1
    return result


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class LiveDriftUiTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "reference.json"
        os.environ["OCUSENSE_REFERENCE_FILE"] = str(self.path)  # each test has its own reference file

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        os.environ.pop("OCUSENSE_REFERENCE_FILE", None)
        self.folder.cleanup()

    def open_window(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.notifications = []
        self.window.notify = lambda message, title: self.notifications.append((title, message))
        return self.window

    def feed(self, seconds, factor=1.0):
        """A session that started `seconds` ago, blinking with intervals cycling 2, 3, 4, 5 s (times `factor`)."""
        w = self.window
        w.monitor.calibration = object()
        w.start()
        t0 = time.monotonic() - seconds
        w.recorder = SessionRecorder(t0)
        times, k = onsets(seconds, factor), 0
        observe = Observer()
        for frame in range(int(seconds * 30)):
            rel = frame / 30
            while k + 1 < len(times) and times[k + 1] <= rel + 1e-9:
                k += 1
            value = 0.05 if 0 <= rel - times[k] < 0.2 - 1e-9 else 0.9
            obs = observe(t0 + rel, value)
            w._on_update(update(now=t0 + rel, openness=(value, value, value), blinked=obs.blink_completed,
                                observation=obs))
        w._ticks = 3
        w._tick()  # the 4th tick: the comparison is updated once per second

    def save_reference(self):
        times = onsets(600)
        new = reference_file.from_pairs(list(zip(times, times[1:])), datetime(2026, 10, 10, 21, 26, 24),
                                        "test", None)
        reference_file.save(new, self.path)
        return new

    def test_collecting_without_a_reference(self):
        self.open_window()
        self.feed(120)
        self.window.show_page("current")
        page = self.window.current_page
        self.assertIn("No reference yet", page.drift_baseline.text())
        self.assertIn("Collecting: 2 min of 10 min", page.drift_baseline.text())
        self.assertIn("10 minutes into the session", page.drift_latest.text())
        self.assertFalse(self.path.exists())

    def test_first_ten_minutes_become_the_reference(self):
        w = self.open_window()
        self.feed(700)
        self.assertTrue(self.path.exists())
        saved = reference_file.load(self.path)
        self.assertGreaterEqual(saved.n, reference_file.MIN_REFERENCE_INTERVALS)
        self.assertTrue(all(0 <= a < b < 600 for a, b in saved.pairs))  # seconds since the session started
        w.show_page("current")
        page = w.current_page
        self.assertIn("saved as your reference", page.drift_baseline.text())
        self.assertIn("similar to the first 10 minutes", page.drift_latest.text())
        self.assertIn("14 windows so far: 14 tested, 0 below p = 0.01, 0 confirmed", page.drift_counts.text())  # ends 300 … 690 s
        w.show_page("settings")
        self.assertIn(f"{saved.n} intervals", w.settings_page.reference_detail.text())
        w.recalibrate()  # a new session, but the reference is kept
        self.assertIsNone(w._drift)
        self.assertTrue(self.path.exists())

    def test_saved_reference_is_used_from_the_start(self):
        saved = self.save_reference()
        w = self.open_window()
        self.feed(400)
        w.show_page("current")
        page = w.current_page
        self.assertIn(f"Reference: session of 10 Oct 2026, 21:26 · {saved.n} intervals", page.drift_baseline.text())
        self.assertIn("similar to the reference", page.drift_latest.text())
        self.assertNotIn("overlaps", page.drift_latest.text())
        self.assertIn("4 windows so far", page.drift_counts.text())  # ends at 300, 330, 360, 390 s
        self.assertEqual(reference_file.load(self.path), saved)  # unchanged

    def test_three_windows_in_a_row_confirm_a_difference(self):
        self.save_reference()
        w = self.open_window()
        self.feed(400, factor=2.5)  # blinking much less often than in the reference
        w.show_page("current")
        page = w.current_page
        self.assertIn("different from the reference: 4 windows in a row below p = 0.01", page.drift_latest.text())
        self.assertIn("4 below p = 0.01, 2 confirmed (3 in a row)", page.drift_counts.text())

    def test_slower_blinking_gives_one_break_reminder(self):
        self.save_reference()
        w = self.open_window()
        self.feed(400, factor=2.5)  # blinking much less often than in the reference
        self.assertEqual(len(self.notifications), 1)
        title, message = self.notifications[0]
        self.assertEqual(title, "Time for a break")
        self.assertIn("drier than the Sahara desert", message)
        self.assertFalse(w.study.reminder.isHidden())
        self.assertIn("take a break", w.study.reminder_label.text())
        w.study.reminder_dismiss.click()
        self.assertTrue(w.study.reminder.isHidden())

    def test_faster_blinking_gives_no_reminder(self):
        self.save_reference()
        self.open_window()
        self.feed(400, factor=0.4)
        self.window.show_page("current")
        self.assertIn("different from the reference", self.window.current_page.drift_latest.text())  # confirmed…
        self.assertEqual(self.notifications, [])  # …but faster, so no reminder
        self.assertTrue(self.window.study.reminder.isHidden())

    def test_reminders_can_be_switched_off(self):
        self.save_reference()
        w = self.open_window()
        w.settings_page.reminders.setChecked(False)
        self.feed(400, factor=2.5)
        self.assertEqual(self.notifications, [])
        self.assertTrue(w.study.reminder.isHidden())

    def test_new_reference_asks_first(self):
        self.save_reference()
        w = self.open_window()
        w._confirm = lambda box: None  # Cancel
        w.make_new_reference()
        self.assertTrue(self.path.exists())
        w._confirm = lambda box: next(b for b in box.buttons() if b.text() == "Discard Reference")
        w.make_new_reference()
        self.assertFalse(self.path.exists())
        self.assertIsNone(w.reference)
        w.show_page("settings")
        self.assertIn("No reference yet", w.settings_page.reference_detail.text())
        self.assertFalse(w.settings_page.reference_button.isEnabled())

    def test_unreadable_reference_is_never_overwritten(self):
        self.path.write_text("not json")
        w = self.open_window()
        self.feed(700)
        self.assertEqual(self.path.read_text(), "not json")
        w.show_page("settings")
        self.assertIn("can’t be read", w.settings_page.reference_detail.text())
        self.assertTrue(w.settings_page.reference_button.isEnabled())  # discarding it is allowed


if __name__ == "__main__":
    unittest.main()
