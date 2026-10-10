"""Checks for the PySide6 window, without a camera. Run with:  python -m unittest

The window is driven with fake camera updates, in Qt's invisible "offscreen" mode.
"""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["OCUSENSE_NO_NOTIFICATIONS"] = "1"  # never show a real notification from the tests
import tempfile  # noqa: E402

RECORDINGS = tempfile.mkdtemp(prefix="ocusense-test-recordings-")
os.environ["OCUSENSE_RECORDINGS_DIR"] = RECORDINGS  # never write into the real Library folder
PREFERENCES_FILE = os.path.join(RECORDINGS, "preferences.json")
os.environ["OCUSENSE_PREFERENCES_FILE"] = PREFERENCES_FILE  # never change the person's real Settings choices
CALIBRATION_FILE = os.path.join(RECORDINGS, "calibration.json")
os.environ["OCUSENSE_CALIBRATION_FILE"] = CALIBRATION_FILE  # never read or replace the person's real calibration
os.environ["OCUSENSE_ACCOUNT_FILE"] = os.path.join(RECORDINGS, "account.json")  # never the real sign-in or Keychain
os.environ["OCUSENSE_NO_ACCOUNTS"] = "1"  # never reach a real Supabase project

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.monitoring.pipeline import CALIBRATION_DONE, CALIBRATION_FAILED, MODEL_PATH  # noqa: E402
from ocusense.monitoring.camera_worker import MonitorUpdate  # noqa: E402
from ocusense.core.models import FrameObservation  # noqa: E402
from ocusense.core.session import SessionRecorder  # noqa: E402
from tests.helpers import Observer  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeThread:
    """Stands in for CameraWorker: no camera, no background thread."""

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
    if "observation" not in changes:  # what the pipeline would send for this frame
        o = values["openness"]
        values["observation"] = FrameObservation(
            t=values["now"], valid=o is not None,
            left_raw=o[0] if o else None, right_raw=o[1] if o else None, blink_completed=values["blinked"])
    return MonitorUpdate(**values)


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class WindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
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
        names = {"Start": w.study.start_button, "Pause": w.study.pause_button, "Resume": w.study.resume_button,
                 "Stop": w.study.stop_button, "Recalibrate": w.study.recalibrate_button}
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
        self.assertIn("STEP 2 OF 3", w.calibration.eyebrow.text())
        self.assertEqual(w.calibration.countdown.text(), "4")
        w.monitor.calibration = object()
        w._on_update(update(events=[CALIBRATION_DONE]))
        self.assertEqual(w.state, "monitoring")
        self.assertEqual(self.visible_buttons(), ["Pause", "Recalibrate", "Stop"])

    def test_failed_calibration_offers_try_again(self):
        w = self.window
        w.start()
        w._on_update(update(events=[CALIBRATION_FAILED], cal_status="failed", cal_error="Too similar."))
        self.assertEqual(w.state, "calibrating")
        self.assertIn("Too similar.", w.calibration.error.text())
        self.assertFalse(w.calibration.try_again_button.isHidden())

    def test_monitoring_updates_count_and_status(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        samples = [(99.0 + i * 0.1, (0.9, 0.9, 0.9 if i % 5 else 0.1), i % 5 == 1) for i in range(10)]
        w._on_update(update(blinks=3, samples=samples))
        self.assertEqual(w.study.blink_label.text(), "3 blinks this session")
        self.assertEqual(w.status.text.text(), "Monitoring")
        w._on_update(update(face_found=False, openness=None))
        self.assertEqual(w.status.text.text(), "Face not tracked")
        self.assertFalse(w.study.graph.grab().isNull())  # the graph paints without errors

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
        self.assertEqual(w.study.timer_label.text(), "00:00:00")
        self.assertEqual(self.visible_buttons(), ["Recalibrate", "Start"])

    def test_late_update_after_stop_is_ignored(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w.stop()
        w._on_update(update(blinks=9))
        self.assertEqual(w.study.blink_label.text(), "0 blinks this session")

    def _run_session(self, seconds, blink_every=4):
        """Feed `seconds` of fake frames at 30 fps while monitoring."""
        w = self.window
        t0 = time.monotonic() - seconds  # frames end "now", on the same clock the app uses
        w.recorder = SessionRecorder(t0)
        observe = Observer()  # the real detector decides closing and reopening
        for i in range(int(seconds * 30)):
            t = t0 + i / 30
            value = 0.05 if blink_every and 1.0 <= t % blink_every < 1.2 else 0.9
            obs = observe(t, value)
            w._on_update(update(now=t, openness=(value, value, value), blinked=obs.blink_completed, observation=obs))

    def test_live_openness_shows_dash_not_zero_when_face_lost(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w._on_update(update(openness=(0.8, 0.6, 0.7)))
        self.assertEqual(w.study.openness_value.text(), "70%")
        w._on_update(update(face_found=False, openness=None))
        self.assertEqual(w.study.openness_value.text(), "—")

    def test_last_60_seconds_collects_data_then_shows_values(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self._run_session(10)
        w._refresh_measurements()
        self.assertEqual(w.study.stat_values["rate"].text(), "Collecting data")
        self.assertEqual(w.study.stat_values["closed"].text(), "Collecting data")
        self._run_session(40)
        w._refresh_measurements()
        self.assertTrue(w.study.stat_values["rate"].text().endswith("blinks/min"))
        self.assertTrue(w.study.stat_values["closure"].text().endswith("ms"))
        self.assertTrue(w.study.stat_values["closed"].text().endswith("%"))

    def test_pause_tells_the_detector_tracking_stopped(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w.monitor.counter.state = w.monitor.counter.CLOSED  # paused mid-blink
        w.pause()
        self.assertEqual(w.monitor.counter.state, w.monitor.counter.UNKNOWN)  # can't complete across the pause

    def test_stopped_session_appears_in_statistics(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self._run_session(30)
        w.stop()
        sessions = w.store.all()
        self.assertEqual(len(sessions), 1)
        self.assertGreater(sessions[0].blinks, 0)
        w.show_stats()
        self.assertIs(w.pages.currentWidget(), w.stats_page)
        self.assertEqual(w.stats_page.summary_values["sessions"].text(), "1")
        self.assertTrue(w.sidebar.items["all_time"].selected)
        self.assertTrue(w.sidebar.items["statistics"].ancestor)

    def test_very_short_session_is_not_kept(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w.stop()
        self.assertEqual(w.store.all(), [])

    def test_paused_session_shows_as_in_progress(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self._run_session(15)
        w.pause()
        w.show_stats()
        self.assertEqual(w.store.all(), [])  # not finished yet
        self.assertEqual(w.stats_page.summary_values["sessions"].text(), "0")  # completed only
        self.assertTrue(w.stats_page.body.isVisible() or not w.isVisible())

    def test_other_pages_unavailable_during_calibration(self):
        w = self.window
        w.start()
        for key in ("statistics", "current", "all_time", "patterns", "settings", "account"):
            self.assertFalse(w.sidebar.items[key].isEnabled(), key)
        self.assertTrue(w.sidebar.items["study"].isEnabled())
        w.show_stats()
        w.show_page("settings")
        self.assertIs(w.pages.currentWidget(), w.calibration)

    def test_statistics_page_draws_every_view(self):
        from ocusense.demo_data import demo_sessions
        page = self.window.stats_page
        page.resize(1100, 900)
        for period in ("today", "week", "month"):
            for metric in ("rate", "closure", "closed"):
                page.period, page.metric_key = period, metric
                page.refresh(demo_sessions(), None, demo=True)
                self.assertFalse(page.widget().grab().isNull())
                self.assertFalse(page.chart.grab().isNull())

    def test_new_user_sees_empty_statistics(self):
        w = self.window
        w.show_stats()
        self.assertTrue(w.stats_page.body.isHidden())
        self.assertFalse(w.stats_page.empty.isHidden())

    def test_frame_from_an_old_camera_run_is_ignored(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        w._on_update(update(blinks=9, source=FakeThread()))  # not the current run
        self.assertEqual(w.study.blink_label.text(), "0 blinks this session")
        w._on_update(update(blinks=4, source=self.thread))
        self.assertEqual(w.study.blink_label.text(), "4 blinks this session")




@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class SidebarNavigationTest(unittest.TestCase):
    """The sidebar pages: switching never touches monitoring; pages show only real data."""

    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = self._fake_start

    def tearDown(self):
        self.window.close()

    def _fake_start(self):
        self.window.thread = self.thread
        return True

    def _monitor(self, seconds=20):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        t0 = time.monotonic() - seconds
        w.recorder = SessionRecorder(t0)
        observe = Observer()
        for i in range(int(seconds * 30)):
            t = t0 + i / 30
            value = 0.05 if 1.0 <= t % 4 < 1.2 else 0.9
            obs = observe(t, value)
            w._on_update(update(now=t, openness=(value, value, value), blinked=obs.blink_completed, observation=obs))

    def test_switching_pages_keeps_monitoring_running(self):
        w = self.window
        self._monitor()
        recorder = w.recorder
        for key in ("current", "all_time", "patterns", "settings", "account", "study", "current"):
            w.show_page(key)
            self.assertIs(w.pages.currentWidget(), w.page_for[key])
            self.assertEqual(w.state, "monitoring")
            self.assertIs(w.thread, self.thread)  # same camera worker: none stopped or added
            self.assertFalse(self.thread.stopped)
            self.assertIs(w.recorder, recorder)
            self.assertTrue(w.sidebar.items[key].selected)

    def test_statistics_expands_to_its_three_pages(self):
        bar = self.window.sidebar
        self.assertTrue(bar.items["current"].isHidden())
        bar.items["statistics"].click()
        self.assertFalse(bar.items["current"].isHidden())
        self.assertIs(self.window.pages.currentWidget(), self.window.current_page)
        bar.items["statistics"].click()  # collapse; the group stays highlighted
        self.assertTrue(bar.items["patterns"].isHidden())
        self.assertTrue(bar.items["statistics"].ancestor)

    def test_sidebar_keyboard_navigation(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w = self.window
        w.show()
        w.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(w))  # keyboard focus needs an active window
        bar = w.sidebar
        bar.items["study"].setFocus()
        QTest.keyClick(bar.items["study"], Qt.Key.Key_Down)
        self.assertTrue(bar.items["pomodoro"].hasFocus())
        QTest.keyClick(bar.items["pomodoro"], Qt.Key.Key_Down)
        self.assertTrue(bar.items["games"].hasFocus())
        QTest.keyClick(bar.items["games"], Qt.Key.Key_Down)
        self.assertTrue(bar.items["statistics"].hasFocus())
        QTest.keyClick(bar.items["statistics"], Qt.Key.Key_Right)
        self.assertFalse(bar.items["current"].isHidden())
        QTest.keyClick(bar.items["statistics"], Qt.Key.Key_Down)
        QTest.keyClick(bar.items["current"], Qt.Key.Key_Down)
        QTest.keyClick(bar.items["all_time"], Qt.Key.Key_Return)
        self.assertIs(w.pages.currentWidget(), w.stats_page)

    def test_current_session_empty_then_live(self):
        w = self.window
        w.show_page("current")
        self.assertFalse(w.current_page.empty.isHidden())
        self.assertTrue(w.current_page.content.isHidden())
        self._monitor(40)
        w.show_page("current")
        self.assertTrue(w.current_page.empty.isHidden())
        self.assertIn("blinks/min", w.current_page.metric_values["rate"].text())
        self.assertNotEqual(w.current_page.time_values["blinks"].text(), "0")
        w.pause()
        self.assertEqual(w.current_page.tag.text(), "Paused")
        w.stop()
        self.assertFalse(w.current_page.empty.isHidden())

    def test_all_time_totals_and_memory_note(self):
        w = self.window
        self._monitor(30)
        w.stop()
        w.show_page("all_time")
        page = w.stats_page
        self.assertEqual(page.summary_values["sessions"].text(), "1")
        self.assertEqual(page.summary_values["breaks"].text(), "—")  # breaks aren't recorded yet
        self.assertIn("memory only", page.memory_note.text())

    def test_patterns_page_never_invents_findings(self):
        from ocusense.ui.patterns_page import PLACEHOLDER
        w = self.window
        self._monitor(30)
        w.stop()
        w.show_page("patterns")
        self.assertEqual(w.patterns_page.observations.text(), PLACEHOLDER)
        self.assertIn("1 session", w.patterns_page.observations_detail.text())

    def test_settings_controls_are_connected(self):
        w = self.window
        w.show_page("settings")
        page = w.settings_page
        self.assertFalse(page.recalibrate_button.isEnabled())  # not calibrated yet
        self.assertFalse(page.clear_button.isEnabled())  # nothing to clear
        page.details.setChecked(True)
        self.assertTrue(w.study.details_button.isChecked())

    def test_clear_history_asks_first(self):
        w = self.window
        self._monitor(30)
        w.stop()
        w._confirm = lambda box: None  # Cancel
        w.clear_history()
        self.assertEqual(len(w.store.all()), 1)
        w._confirm = lambda box: next(b for b in box.buttons() if b.text() == "Clear History")
        w.clear_history()
        self.assertEqual(w.store.all(), [])

    def test_recalibrate_from_settings_opens_calibration(self):
        w = self.window
        self._monitor()
        w.stop()
        w.show_page("settings")
        self.assertTrue(w.settings_page.recalibrate_button.isEnabled())
        w.settings_page.recalibrate_button.click()
        self.assertEqual(w.state, "calibrating")
        self.assertIs(w.pages.currentWidget(), w.calibration)

    def test_account_says_when_it_is_not_set_up(self):
        w = self.window
        w.show_page("account")
        self.assertEqual(w.sidebar.items["account"].text(), "Log in")
        self.assertFalse(w.account_page.unconfigured.isHidden())
        self.assertTrue(w.account_page.signed_out.isHidden())
        self.assertEqual(w.account_page.tag.text(), "Not set up")


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class EarRecordingWindowTest(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from ocusense.ui.main_window import MainWindow
        self.folder = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.window.ear_log.directory = Path(self.folder.name)
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]

    def tearDown(self):
        self.window.close()
        self.folder.cleanup()

    def frames(self, n):
        for i in range(n):
            obs = FrameObservation(t=time.monotonic(), valid=True, left_ear=0.28, right_ear=0.3)
            self.window._on_update(update(now=obs.t, observation=obs))

    def files(self):
        return sorted(p for p in __import__("pathlib").Path(self.folder.name).glob("ear_*.csv"))

    def test_records_calibration_and_monitoring_frames_and_saves_on_pause(self):
        w = self.window
        w.start()  # first start calibrates: those frames are recorded too
        self.frames(5)
        w.monitor.calibration = object()
        w._on_update(update(events=[CALIBRATION_DONE]))
        self.frames(5)
        self.assertEqual(self.files(), [])  # not yet: written every 10 minutes or on pause/stop/quit
        w.pause()
        files = self.files()
        self.assertEqual(len(files), 1)
        rows = files[0].read_text().splitlines()
        self.assertEqual(rows[0], "unix_time,left_ear,right_ear,reliable,left_openness,right_openness")
        self.assertEqual(len(rows), 1 + 11)  # 5 + the calibration-done frame + 5
        self.assertTrue(rows[1].endswith(",0.2800,0.3000,1,,"))

    def test_calibrated_frames_carry_openness_and_their_calibration(self):
        import json
        from datetime import datetime
        from ocusense.core.models import CalibrationInfo
        w = self.window
        info = CalibrationInfo(datetime(2026, 10, 10, 9, 0), 0.30, 0.10, 0.31, 0.11, 0.35, 0.65, "ear-personal-v2")
        w.monitor.calibration = object()
        w.start()
        obs = FrameObservation(t=time.monotonic(), valid=True, left_ear=0.29, right_ear=0.30,
                               left_raw=0.95, right_raw=0.95)
        w._on_update(update(now=obs.t, observation=obs, calibration_info=info))
        w.stop()
        csv_file = self.files()[0]
        self.assertTrue(csv_file.read_text().splitlines()[1].endswith(",0.2900,0.3000,1,0.9500,0.9500"))
        record = json.loads(csv_file.with_name(csv_file.stem + ".calibration.json").read_text())
        self.assertEqual(record["calibration"]["left_open_ear"], 0.30)

    def test_saves_every_chunk_and_on_quit(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self.frames(3)
        w.ear_log._chunk_started -= 601  # pretend 10 minutes passed
        w._tick()
        self.assertEqual(len(self.files()), 1)
        self.frames(2)
        w.close()  # quitting writes the rest
        self.assertEqual(len(self.files()), 2)

    def test_recording_can_be_switched_off_in_settings(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self.frames(3)
        w.settings_page.record.setChecked(False)  # saves what was recorded so far
        self.assertEqual(len(self.files()), 1)
        self.frames(3)
        w.stop()
        self.assertEqual(len(self.files()), 1)
        w.show_page("settings")
        self.assertIn("Recording is off", w.settings_page.recording_detail.text())


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class DistributionsUiTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.folder = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.window.close()
        self.folder.cleanup()

    def test_live_distributions_while_monitoring(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        t0 = time.monotonic() - 200
        w.recorder = SessionRecorder(t0)
        observe = Observer()
        for i in range(200 * 30):
            t = t0 + i / 30
            value = 0.05 if 1.0 <= t % 4 < 1.2 else 0.9
            obs = observe(t, value)
            w._on_update(update(now=t, openness=(value, value, value), blinked=obs.blink_completed, observation=obs))
        w.show_page("current")
        panel = w.current_page.distributions
        self.assertIn("completed events", panel.summary.text())
        self.assertEqual(panel.metric, "closure")  # the default
        for metric in ("closure", "interval", "rate", "instant", "openness"):
            panel._set_metric(metric)
            self.assertFalse(panel.chart.grab().isNull())
            if metric == "rate":
                self.assertIn("eligible windows", panel.note.text())
                self.assertIn("windows ·", panel.summary.text())  # 3 complete minutes → a histogram
            if metric == "instant":
                self.assertIn("values · median 15.0 blinks/min", panel.summary.text())  # a blink every 4 s
                self.assertFalse(panel.unit_switch.isHidden())
                panel._set_unit("second")
                self.assertIn("median 0.250 blinks/s", panel.summary.text())  # 15 per minute ÷ 60
                self.assertEqual(panel.chart.binning.unit, "blinks/s")
                panel._set_metric("rate")
                self.assertIn("blinks/s", panel.summary.text())  # the unit choice applies to both measures
                panel._set_unit("minute")
                panel._set_metric("instant")
        panel._set_eye("both")
        self.assertIn("Both eyes", panel.summary.text())
        self.assertEqual(w.state, "monitoring")  # looking at Statistics never touched monitoring
        self.assertFalse(self.thread.stopped)

    def test_current_session_without_session_shows_empty_state(self):
        w = self.window
        w.show_page("current")
        self.assertFalse(w.current_page.empty.isHidden())

    def test_import_inspect_and_export_a_recording(self):
        import json
        from pathlib import Path
        folder = Path(self.folder.name)
        lines = ["unix_time,left_ear,right_ear,reliable,left_openness,right_openness"]
        for i in range(90 * 30):
            t = 1_000_000 + i / 30
            v = 0.05 if 1.0 <= (i / 30) % 3 < 1.2 else 0.9
            e = 0.1 + v * 0.2
            lines.append(f"{t:.3f},{e:.4f},{e:.4f},1,{v:.4f},{v:.4f}")
        (folder / "ear_x.csv").write_text("\n".join(lines) + "\n")
        calibration = {"calibrated_at": "2026-10-10T15:52:16", "left_open_ear": 0.3, "left_closed_ear": 0.1,
                       "right_open_ear": 0.3, "right_closed_ear": 0.1, "close_below": 0.35, "reopen_above": 0.65,
                       "measurement_version": "ear-personal-v2"}
        (folder / "ear_x.calibration.json").write_text(json.dumps({"calibration": calibration}))
        section = self.window.stats_page.recordings
        self.assertIn("No recording imported", section.panel.chart.message)
        section.import_files([folder / "ear_x.csv"])
        section.worker.wait(10000)  # the analysis runs on a background thread
        for _ in range(20):
            app.processEvents()  # deliver its result to the interface thread
        self.assertEqual(section.choice.count(), 1)
        self.assertIn("completed events", section.panel.summary.text())
        self.assertIn("closes below 35%", section.calibration_label.text())
        section.inspect_button.setChecked(True)
        self.assertFalse(section.inspect.isHidden())
        self.assertFalse(section.timeline.grab().isNull())
        target = section.panel.export_to(folder / "out")
        self.assertTrue((target / "histogram.png").exists())
        summary = (target / "summary.csv").read_text()
        self.assertIn("frequency per blink median", summary)
        self.assertIn("blinks/s", summary)
        self.assertTrue((target / "blink_events.csv").exists())


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class DistanceReminderTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.sent = []  # (title, message) of every Mac notification
        self.window.notify = lambda message, title: self.sent.append((title, message))
        self.window.monitor.calibration = object()
        self.window.start()

    def tearDown(self):
        self.window.close()

    def feed(self, seconds, closeness, start=None):
        t0 = time.monotonic() if start is None else start
        for i in range(int(seconds * 30)):
            self.window._on_update(update(now=t0 + i / 30, closeness=closeness))
        return t0 + seconds

    def test_banner_and_notification_after_three_seconds_close(self):
        from ocusense.ui.main_window import DISTANCE_BODY, DISTANCE_TITLE
        w = self.window
        t = self.feed(2, 1.8)
        self.assertTrue(w.banner_holder.isHidden())
        self.feed(2, 1.8, start=t)
        self.assertFalse(w.banner_holder.isHidden())
        self.assertEqual(w.distance_banner.title.text(), "Trying to lick the screen?")
        self.assertEqual(w.distance_banner.body.text(), "Go easy on your eyes and move back a little.")
        self.assertEqual(self.sent, [(DISTANCE_TITLE, DISTANCE_BODY)])  # the window isn't active in tests
        self.assertEqual(w.state, "monitoring")  # the reminder never interrupts monitoring

    def test_banner_goes_away_when_moving_back(self):
        w = self.window
        t = self.feed(4, 1.8)
        self.feed(1, 1.1, start=t)
        self.assertTrue(w.banner_holder.isHidden())

    def test_got_it_and_reminder_settings(self):
        w = self.window
        self.feed(4, 1.8)
        w.distance_banner.buttons["Reminder settings"].click()
        self.assertTrue(w.banner_holder.isHidden())
        self.assertIs(w.pages.currentWidget(), w.settings_page)
        self.assertIn("Recalibrate", w.settings_page.distance_detail.text())  # this calibration has no reference

    def test_switched_off_in_settings(self):
        w = self.window
        w.settings_page.distance.setChecked(False)
        self.feed(5, 1.8)
        self.assertTrue(w.banner_holder.isHidden())
        self.assertEqual(self.sent, [])

    def test_pause_clears_the_reminder(self):
        w = self.window
        self.feed(4, 1.8)
        w.pause()
        self.assertTrue(w.banner_holder.isHidden())
        self.assertFalse(w.proximity.too_close)


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class ReminderIntervalTest(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(PREFERENCES_FILE):
            os.remove(PREFERENCES_FILE)

    def open_window(self):
        from ocusense.ui.main_window import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        return window

    def test_choices_from_5_seconds_to_10_minutes(self):
        combo = self.open_window().settings_page.interval
        texts = [combo.itemText(i) for i in range(combo.count())]
        self.assertEqual(texts[0], "5 s")
        self.assertEqual(texts[-1], "10 min")
        self.assertEqual(combo.currentText(), "5 min")  # the default

    def test_choice_applies_and_is_remembered(self):
        w = self.open_window()
        combo = w.settings_page.interval
        combo.setCurrentIndex(combo.findText("30 s"))
        self.assertEqual(w.proximity.cooldown_seconds, 30)
        self.assertIn("again every 30 s", w.settings_page.distance_explain.text())
        w.settings_page.distance.setChecked(False)
        self.assertFalse(combo.isEnabled())
        again = self.open_window()  # next launch
        self.assertEqual(again.settings_page.interval.currentText(), "30 s")
        self.assertEqual(again.proximity.cooldown_seconds, 30)
        self.assertFalse(again.settings_page.distance.isChecked())
        self.assertFalse(again.distance_reminder)
        self.assertFalse(again.settings_page.interval.isEnabled())


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class SavedCalibrationTest(unittest.TestCase):
    """Calibrate once: the calibration is saved and reused on the next launch."""

    def setUp(self):
        from ocusense.calibration_store import CalibrationStore
        from tests.test_calibration_store import CAL, INFO
        self.cal, self.info = CAL, INFO
        self.store = CalibrationStore()  # the temporary file set at the top of this module
        self.thread = FakeThread()

    def tearDown(self):
        if os.path.exists(CALIBRATION_FILE):
            os.remove(CALIBRATION_FILE)

    def open_window(self):
        from ocusense.ui.main_window import MainWindow
        window = MainWindow()
        window._start_camera = lambda: (setattr(window, "thread", self.thread), True)[1]
        self.addCleanup(window.close)
        return window

    def test_first_calibration_is_saved(self):
        w = self.open_window()
        w.start()
        self.assertEqual(w.state, "calibrating")  # nothing saved yet: calibrate
        w.monitor.calibration, w.monitor.calibration_info = self.cal, self.info  # what the worker produces
        w._on_update(update(events=[CALIBRATION_DONE]))
        self.assertEqual(self.store.load().calibration, self.cal)
        self.assertIn("saved", w.study.message_label.text())

    def test_next_launch_starts_monitoring_right_away(self):
        self.store.save(self.cal, self.info)
        w = self.open_window()
        self.assertEqual(w.monitor.calibration, self.cal)
        self.assertIn("saved calibration from 10 Oct 2026", w.study.message_label.text())
        self.assertFalse(w.study.recalibrate_button.isHidden())  # recalibration is always possible
        w.start()
        self.assertEqual(w.state, "monitoring")
        self.assertEqual(self.thread.calibration_requests, 0)  # no calibration this session
        self.assertEqual(w.monitor.calibration_info.reference_face_scale, 0.21)  # distance reminder works too

    def test_cancelled_recalibration_keeps_the_saved_one(self):
        self.store.save(self.cal, self.info)
        w = self.open_window()
        w.recalibrate()
        self.assertEqual(w.state, "calibrating")
        w.monitor.calibration = None  # the worker forgets the old one when calibration starts
        w.cancel_calibration()
        self.assertEqual(w.monitor.calibration, self.cal)
        self.assertIn("saved calibration is still in use", w.study.message_label.text())

    def test_failed_recalibration_does_not_replace_the_file(self):
        self.store.save(self.cal, self.info)
        before = open(CALIBRATION_FILE).read()
        w = self.open_window()
        w.recalibrate()
        w._on_update(update(events=[CALIBRATION_FAILED], cal_status="failed", cal_error="Too similar."))
        self.assertEqual(open(CALIBRATION_FILE).read(), before)

    def test_settings_show_the_saved_date(self):
        self.store.save(self.cal, self.info)
        w = self.open_window()
        w.show_page("settings")
        self.assertIn("Calibrated on 10 Oct 2026 at 15:52", w.settings_page.calibration_row_detail.text())


if __name__ == "__main__":
    unittest.main()
