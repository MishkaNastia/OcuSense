"""The OcuSense main window: sidebar navigation and the session life cycle.

It connects the pieces and holds no layouts of its own pages:
  Sidebar                                        — navigation and the monitoring status
  StudyPage / CalibrationView                    — Study
  CurrentSessionPage / AllTimePage / PatternsPage — Statistics
  SettingsPage / AccountPage                     — at the bottom of the sidebar
  CameraWorker (monitoring/camera_worker.py)     — frames in, structured results out
  SessionRecorder + SessionStore                 — numbers kept for Statistics
  EarRecording (recording.py)                    — raw EAR of every frame, saved as CSV files

Navigation only swaps the visible page: it never starts, stops or restarts the
camera worker, so monitoring carries on while you look at other pages.

States:
  ready        nothing running, camera off
  calibrating  camera on, guided calibration (no blinks counted)
  monitoring   camera on, counting blinks, session timer running
  paused       camera OFF, calibration and counts kept
  error        camera could not be used
"""

import time
from dataclasses import asdict

from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from ocusense.config import CLOSE_BELOW, MIN_SESSION_SECONDS, MODEL_PATH, REOPEN_ABOVE
from ocusense.core.calibration import GuidedCalibration
from ocusense.core.session import SessionRecorder
from ocusense.demo_data import demo_sessions
from ocusense.monitoring.camera_worker import CameraWorker, MonitorUpdate, open_camera
from ocusense.monitoring.pipeline import CALIBRATION_DONE, CALIBRATION_FAILED, CLOSED_STEP_FINISHED, EyeMonitor
from ocusense.recording import EarRecording
from ocusense.storage import SessionStore

from .account_page import AccountPage
from .all_time_page import AllTimePage
from .calibration_view import CalibrationView
from .current_session_page import CurrentSessionPage
from .patterns_page import PatternsPage
from .settings_page import SettingsPage
from .sidebar import STATISTICS_PAGES, Sidebar
from .study_page import StudyPage
from .widgets.common import vline

CAMERA_HELP = ("Could not open the camera. On a Mac: System Settings › Privacy & Security › Camera, "
               "allow this app (or Terminal / VS Code when running from there), then reopen it.")

BUTTONS_FOR_STATE = {
    "ready": {"start"},  # + "recalibrate" once calibrated
    "error": {"start"},
    "monitoring": {"pause", "stop", "recalibrate"},
    "paused": {"resume", "stop"},
    "calibrating": set(),
}


class MainWindow(QMainWindow):
    def __init__(self, demo_history: bool = False):
        super().__init__()
        self.setWindowTitle("OcuSense")
        self.resize(1280, 900)
        self.setMinimumSize(1080, 640)  # pages scroll when the window is shorter than their content

        self.monitor = EyeMonitor(MODEL_PATH)  # may raise; ui/app.py shows the error
        self.camera = None
        self.thread: CameraWorker | None = None
        self.state = "ready"
        self.elapsed = 0.0  # seconds of monitoring in this session (excluding pauses)
        self.running_since: float | None = None
        self.last_update: MonitorUpdate | None = None
        self.view = "study"  # the sidebar page shown: study, current, all_time, patterns, settings or account
        self.demo_history = demo_history
        self.store = SessionStore(demo_sessions() if demo_history else None)  # in memory for now
        self.recorder: SessionRecorder | None = None
        self.ear_log = EarRecording()  # raw EAR per frame, written every 10 minutes
        self._ticks = 0

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.show_page)
        self.sidebar.set_account_label(AccountPage.sidebar_label())
        self.status = self.sidebar.status
        outer.addWidget(self.sidebar)
        divider = vline()
        divider.setProperty("role", "rule")
        divider.setFixedWidth(2)
        outer.addWidget(divider)

        self.study = StudyPage()
        self.calibration = CalibrationView()
        self.current_page = CurrentSessionPage()
        self.stats_page = AllTimePage()
        self.patterns_page = PatternsPage()
        self.settings_page = SettingsPage()
        self.account_page = AccountPage()
        self.page_for = {"study": self.study, "current": self.current_page, "all_time": self.stats_page,
                         "patterns": self.patterns_page, "settings": self.settings_page, "account": self.account_page}
        self.pages = QStackedWidget()
        for page in (self.study, self.calibration, self.current_page, self.stats_page, self.patterns_page,
                     self.settings_page, self.account_page):
            self.pages.addWidget(page)
        outer.addWidget(self.pages, 1)

        self.study.start_button.clicked.connect(self.start)
        self.study.pause_button.clicked.connect(self.pause)
        self.study.resume_button.clicked.connect(self.resume)
        self.study.stop_button.clicked.connect(self.stop)
        self.study.recalibrate_button.clicked.connect(self.recalibrate)
        self.calibration.try_again_button.clicked.connect(self.retry_calibration)
        self.calibration.cancel_button.clicked.connect(self.cancel_calibration)
        self.stats_page.go_to_study.connect(self.show_study)
        self.current_page.go_to_study.connect(self.show_study)
        self.settings_page.recalibrate_requested.connect(self._recalibrate_from_settings)
        self.settings_page.clear_history_requested.connect(self.clear_history)
        self.settings_page.record.toggled.connect(self._set_recording)
        self.settings_page.details.toggled.connect(self.study.details_button.setChecked)
        self.study.details_button.toggled.connect(self.settings_page.details.setChecked)

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(250)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop)  # ⌘. on macOS
        self._set_state("ready")

    # ------------------------------------------------------------- camera life
    def _start_camera(self) -> bool:
        if self.thread is not None:
            return True
        self.camera = open_camera()
        if self.camera is None:
            self._set_state("error", CAMERA_HELP)
            return False
        self.thread = CameraWorker(self.monitor, self.camera)
        self.thread.updated.connect(self._on_update)  # queued: runs on the interface thread
        self.thread.failed.connect(self._on_failed)
        self.thread.start()
        return True

    def _stop_camera(self) -> None:
        """Stop the worker first, then release the camera (the camera light turns off)."""
        if self.thread is not None:
            self.thread.requestInterruption()
            self.thread.wait(3000)
            self.thread = None
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.study.clear_preview()
        self.calibration.clear_preview()

    # ---------------------------------------------------------------- actions
    def start(self) -> None:
        if not self._start_camera():
            return
        self._finish_session()
        self.monitor.reset_session()
        self.elapsed = 0.0
        if self.monitor.calibration is None:
            self._begin_calibration()
        else:
            self._enter_monitoring()

    def pause(self) -> None:
        if self.recorder:
            self.recorder.pause(time.monotonic())
        self._stop_clock()
        self._stop_camera()
        self.monitor.interrupt()  # after the worker stopped: no blink may span the pause
        self._save_recording()
        self._set_state("paused")

    def resume(self) -> None:
        if self._start_camera():
            self._enter_monitoring()

    def stop(self) -> None:
        if self.state == "calibrating":
            self.cancel_calibration()
            return
        self._stop_clock()
        self._stop_camera()
        self._save_recording()
        saved = self._finish_session()
        self.monitor.reset_session()
        self.elapsed = 0.0
        self._set_state("ready", "Session ended — see it under Statistics." if saved else "")

    def recalibrate(self) -> None:
        self._stop_clock()
        self._finish_session()  # a new calibration starts a new session
        if self._start_camera():
            self._begin_calibration()

    def retry_calibration(self) -> None:
        if self._start_camera():
            self._begin_calibration()

    def cancel_calibration(self) -> None:
        self._stop_camera()
        self._save_recording()
        self._set_state("ready", "Calibration cancelled. Press Start to calibrate again.")

    def _begin_calibration(self) -> None:
        self.thread.request_calibration()
        self._set_state("calibrating")

    def _enter_monitoring(self) -> None:
        now = time.monotonic()
        self.running_since = now
        if self.recorder is None:
            self.recorder = SessionRecorder(now, calibration=self.monitor.calibration_info)
            self.study.clear_measurements()
        else:
            self.recorder.resume(now)
        self._set_state("monitoring")

    def _finish_session(self) -> bool:
        """End the recorded session; keep it for Statistics if it was long enough."""
        if self.recorder is None:
            return False
        summary = self.recorder.finish(time.monotonic())
        self.recorder = None
        if summary.study_seconds >= MIN_SESSION_SECONDS:
            self.store.add(summary)
            return True
        return False

    def _stop_clock(self) -> None:
        if self.running_since is not None:
            self.elapsed += time.monotonic() - self.running_since
            self.running_since = None

    # ---------------------------------------------------------------- updates
    def _on_failed(self, message: str) -> None:
        if self.recorder:
            self.recorder.pause(time.monotonic())
        self._stop_clock()
        self._stop_camera()
        self._save_recording()
        self._set_state("error", message)

    def _on_update(self, update: MonitorUpdate) -> None:
        if self.thread is None or (update.source is not None and update.source is not self.thread):
            return  # a late frame from a camera run that has already been stopped
        self.last_update = update
        obs = update.observation
        if obs is not None:
            self.ear_log.add(update.now, obs.left_ear, obs.right_ear, update.reliable,
                             obs.left_raw, obs.right_raw, update.calibration_info)
        pixmap = QPixmap.fromImage(update.preview)
        if self.state == "calibrating":
            self.calibration.set_preview(pixmap)
            self._on_calibration_update(update)
            return
        self.study.set_preview(pixmap)
        if self.state != "monitoring":
            return
        if self.recorder:
            self.recorder.add_observation(update.observation)
        self.study.set_live_openness(update.observation)
        self.study.set_blinks(update.blinks)
        if not update.face_found:
            self.status.set("warning", "Face not tracked")
            self.study.graph_caption.setText("Measurement paused — face the camera")
        elif not update.reliable:
            self.status.set("warning", "Measurement paused")
            self.study.graph_caption.setText(f"Paused — {update.reason}")
        else:
            self.status.set("monitoring", "Monitoring")
            self.study.graph_caption.setText("Last 10 seconds · relative to your own calibration")
        self.study.graph.set_data(update.samples, update.now)
        if self.view == "current":  # only paint the second graph while it is visible
            self.current_page.set_graph(update.samples, update.now, caption=self.study.graph_caption.text())

    def _on_calibration_update(self, update: MonitorUpdate) -> None:
        if CLOSED_STEP_FINISHED in update.events:
            QApplication.beep()  # "you can open your eyes"
        if CALIBRATION_DONE in update.events:
            self.monitor.reset_session()
            self.study.graph.clear()
            self.elapsed = 0.0
            self._enter_monitoring()
            self.study.message_label.setText("Calibration complete.")
        elif CALIBRATION_FAILED in update.events:
            self.calibration.show_failure(update.cal_error)
        elif update.cal_status == GuidedCalibration.RUNNING and update.cal_step is not None:
            self.calibration.show_progress(update.cal_step, update.cal_seconds_left, update.cal_measuring,
                                           update.face_found, update.reliable, update.reason)

    def _tick(self) -> None:
        if self.ear_log.due(time.monotonic()):
            self._save_recording()
        running = time.monotonic() - self.running_since if self.running_since is not None else 0.0
        self.study.set_time(self.elapsed + running)
        self._ticks += 1
        if self.state == "monitoring" and self.recorder and self._ticks % 2 == 0:
            self._refresh_measurements()  # twice per second
        if self.view in STATISTICS_PAGES and self.state == "monitoring" and self._ticks % 8 == 0:
            self._refresh_stats()  # every 2 seconds while a session is running

    def _refresh_measurements(self) -> None:
        snapshot = self.recorder.live(time.monotonic())
        self.study.set_rolling(snapshot)
        if self.study.details_button.isChecked():
            self.study.set_details(self.recorder.latest, snapshot, self.recorder.calibration)

    # ------------------------------------------------------------- navigation
    def show_page(self, key: str) -> None:
        """Show a sidebar page. Never touches the camera or the session."""
        if self.state == "calibrating" and key != "study":
            return  # calibration needs the person's attention; other pages open again afterwards
        self.view = key
        if key in STATISTICS_PAGES:
            self._refresh_stats()
        elif key == "settings":
            self._refresh_settings()
        self._show_page()

    def show_study(self) -> None:
        self.show_page("study")

    def show_stats(self) -> None:
        self.show_page("all_time")

    def _refresh_stats(self) -> None:
        current = self.recorder.summary(time.monotonic()) if self.recorder else None
        if current is not None and current.study_seconds < 1:
            current = None
        sessions = self.store.all()
        if self.view == "current":
            self.current_page.show_session(current, paused=self.state == "paused")
            if self.recorder is not None:
                self._show_live_distributions()
            if current is not None and self.last_update is not None and self.state != "monitoring":
                self.current_page.set_graph(self.last_update.samples, self.last_update.now, dimmed=True,
                                            caption="Paused — the camera is off")
        elif self.view == "all_time":
            self.stats_page.refresh(sessions, current, self.demo_history)
        elif self.view == "patterns":
            self.patterns_page.refresh(sessions)

    def _show_live_distributions(self) -> None:
        """Every 2 s while Current session is shown (never per frame); bins stay fixed."""
        recorder = self.recorder
        info = recorder.calibration
        thresholds = (info.close_below, info.reopen_above) if info else (CLOSE_BELOW, REOPEN_ABOVE)
        context = {"source": {"type": "live session", "started": recorder.started_at.isoformat(timespec="seconds")},
                   "calibration": asdict(info) if info else None,
                   "thresholds": {"close_below": thresholds[0], "reopen_above": thresholds[1]}}
        self.current_page.show_distributions(recorder.distributions.snapshot(time.monotonic()), thresholds, context)

    def _refresh_settings(self) -> None:
        calibration = self.monitor.calibration_info if self.monitor.calibration else None
        if calibration is not None:
            text = f"Calibrated at {calibration.calibrated_at:%H:%M}. Recalibrate if lighting, glasses or your position change."
        elif self.monitor.calibration:
            text = "Calibrated. Recalibrate if lighting, glasses or your position change."
        else:
            text = "Not calibrated yet — your first session starts with a 30-second calibration."
        can = bool(self.monitor.calibration) and self.state in ("ready", "monitoring")
        if not can and self.monitor.calibration and self.state == "paused":
            text += " Resume or stop the session to recalibrate."
        completed = sum(1 for s in self.store.all() if not s.in_progress)
        self.settings_page.show_state(text, can, completed)
        self.settings_page.show_recording(self.ear_log)

    def _save_recording(self) -> None:
        """Write buffered EAR rows to a CSV file; a failure is reported, and the rows are kept for the next try."""
        self.ear_log.flush()
        if self.ear_log.last_error:
            self.study.message_label.setText(self.ear_log.last_error)
        if self.view == "settings":
            self._refresh_settings()

    def _set_recording(self, on: bool) -> None:
        if not on:
            self._save_recording()  # keep what was recorded so far
        self.ear_log.enabled = on
        self._refresh_settings()

    def _recalibrate_from_settings(self) -> None:
        self.recalibrate()  # switches to the Study page, where calibration is shown

    def clear_history(self) -> None:
        box = QMessageBox(QMessageBox.Icon.Warning, "Clear session history?",
                          "This removes all completed sessions from Statistics and can’t be undone. "
                          "A session that is running now is not affected.", parent=self)
        clear = box.addButton("Clear History", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Cancel))
        if self._confirm(box) is clear:
            self.store.clear()
            self._refresh_settings()

    def _confirm(self, box: QMessageBox):
        """Show a confirmation and return the clicked button (replaced in tests)."""
        box.exec()
        return box.clickedButton()

    def _show_page(self) -> None:
        if self.state == "calibrating":
            self.view = "study"
            page = self.calibration
        else:
            page = self.page_for.get(self.view, self.study)
        self.pages.setCurrentWidget(page)
        self.sidebar.set_current(self.view)
        self.sidebar.set_only_enabled({"study"} if self.state == "calibrating" else None)

    # ------------------------------------------------------------------ state
    def _set_state(self, state: str, message: str = "") -> None:
        self.state = state
        names = set(BUTTONS_FOR_STATE[state])
        if state == "ready" and self.monitor.calibration:
            names.add("recalibrate")
        self.study.show_buttons(names, "Try again" if state == "error" else "Start")
        self._show_page()
        if self.view in STATISTICS_PAGES:
            self._refresh_stats()
        elif self.view == "settings":
            self._refresh_settings()
        self.study.message_label.setText(message)

        if state == "ready":
            self.status.set("ready", "Ready")
            self.study.graph_caption.setText("")
            first = not self.monitor.calibration
            self.study.graph.clear("Press Start. Your first session begins with a 30-second calibration." if first
                                   else "Press Start to begin a new session.")
            self.study.set_blinks(0)
            self.study.clear_measurements()
            self.study.start_button.setFocus()
        elif state == "error":
            self.status.set("warning", "Camera unavailable")
            self.study.graph.clear("")
        elif state == "paused":
            self.status.set("paused", "Paused")
            self.study.graph_caption.setText("Paused — the camera is off")
            self.study.set_live_openness(None)
            if self.last_update:
                self.study.graph.set_data(self.last_update.samples, self.last_update.now, dimmed=True)
        elif state == "calibrating":
            self.status.set("calibrating", "Calibrating")
            self.calibration.reset()
        elif state == "monitoring":
            self.status.set("monitoring", "Monitoring")
            self.study.pause_button.setFocus()
        self._tick()

    def closeEvent(self, event) -> None:
        self._finish_session()
        self._stop_camera()
        self.ear_log.flush()  # the last minutes of EAR data
        self.monitor.close()
        super().closeEvent(event)
