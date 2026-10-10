"""The OcuSense main window: header, navigation, and the session life cycle.

It connects the pieces and holds no layouts of its own pages:
  StudyPage / CalibrationView / StatisticsPage  — what is shown
  CameraWorker (monitoring/camera_worker.py)    — frames in, structured results out
  SessionRecorder + SessionStore                — numbers kept for Statistics

States:
  ready        nothing running, camera off
  calibrating  camera on, guided calibration (no blinks counted)
  monitoring   camera on, counting blinks, session timer running
  paused       camera OFF, calibration and counts kept
  error        camera could not be used
"""

import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ocusense.config import MIN_SESSION_SECONDS, MODEL_PATH
from ocusense.core.calibration import GuidedCalibration
from ocusense.core.session import SessionRecorder
from ocusense.demo_data import demo_sessions
from ocusense.monitoring.camera_worker import CameraWorker, MonitorUpdate, open_camera
from ocusense.monitoring.pipeline import CALIBRATION_DONE, CALIBRATION_FAILED, CLOSED_STEP_FINISHED, EyeMonitor
from ocusense.storage import SessionStore

from . import theme
from .calibration_view import CalibrationView
from .statistics_page import StatisticsPage
from .study_page import StudyPage
from .widgets.artwork import LogoMark
from .widgets.common import button, label, rule
from .widgets.status_indicator import StatusIndicator

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
        self.resize(1120, 900)
        self.setMinimumSize(920, 820)

        self.monitor = EyeMonitor(MODEL_PATH)  # may raise; ui/app.py shows the error
        self.camera = None
        self.thread: CameraWorker | None = None
        self.state = "ready"
        self.elapsed = 0.0  # seconds of monitoring in this session (excluding pauses)
        self.running_since: float | None = None
        self.last_update: MonitorUpdate | None = None
        self.view = "study"  # which tab is shown: "study" or "stats"
        self.demo_history = demo_history
        self.store = SessionStore(demo_sessions() if demo_history else None)  # in memory for now
        self.recorder: SessionRecorder | None = None
        self._ticks = 0

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        outer.addWidget(rule())

        self.study = StudyPage()
        self.calibration = CalibrationView()
        self.stats_page = StatisticsPage()
        self.pages = QStackedWidget()
        for page in (self.study, self.calibration, self.stats_page):
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

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(250)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop)  # ⌘. on macOS
        self._set_state("ready")

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(40, 16, 40, 16)
        layout.addWidget(LogoMark(38))
        layout.addSpacing(8)
        wordmark = label("OcuSense", font=theme.ui_font(25, QFont.Weight.Bold))
        wordmark.setStyleSheet("letter-spacing: -0.5px;")
        layout.addWidget(wordmark)
        layout.addSpacing(36)
        self.nav_study = button("Study", "nav")
        self.nav_stats = button("Statistics", "nav")
        for widget, handler in ((self.nav_study, self.show_study), (self.nav_stats, self.show_stats)):
            widget.setCheckable(True)
            widget.clicked.connect(handler)
            layout.addWidget(widget)
        layout.addStretch(1)
        self.status = StatusIndicator()
        layout.addWidget(self.status)
        return header

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
        self._set_state("error", message)

    def _on_update(self, update: MonitorUpdate) -> None:
        if self.thread is None or (update.source is not None and update.source is not self.thread):
            return  # a late frame from a camera run that has already been stopped
        self.last_update = update
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
        running = time.monotonic() - self.running_since if self.running_since is not None else 0.0
        self.study.set_time(self.elapsed + running)
        self._ticks += 1
        if self.state == "monitoring" and self.recorder and self._ticks % 2 == 0:
            self._refresh_measurements()  # twice per second
        if self.view == "stats" and self.state == "monitoring" and self._ticks % 8 == 0:
            self._refresh_stats()  # every 2 seconds while a session is running

    def _refresh_measurements(self) -> None:
        snapshot = self.recorder.live(time.monotonic())
        self.study.set_rolling(snapshot)
        if self.study.details_button.isChecked():
            self.study.set_details(self.recorder.latest, snapshot, self.recorder.calibration)

    # ------------------------------------------------------------- navigation
    def show_study(self) -> None:
        self.view = "study"
        self._show_page()

    def show_stats(self) -> None:
        if self.state == "calibrating":
            return
        self.view = "stats"
        self._refresh_stats()
        self._show_page()

    def _refresh_stats(self) -> None:
        current = self.recorder.summary(time.monotonic()) if self.recorder else None
        if current is not None and current.study_seconds < 1:
            current = None
        self.stats_page.refresh(self.store.all(), current, self.demo_history)

    def _show_page(self) -> None:
        if self.state == "calibrating":
            page = self.calibration
        else:
            page = self.stats_page if self.view == "stats" else self.study
        self.pages.setCurrentWidget(page)
        self.nav_study.setChecked(page is not self.stats_page)
        self.nav_stats.setChecked(page is self.stats_page)
        self.nav_stats.setEnabled(self.state != "calibrating")

    # ------------------------------------------------------------------ state
    def _set_state(self, state: str, message: str = "") -> None:
        self.state = state
        names = set(BUTTONS_FOR_STATE[state])
        if state == "ready" and self.monitor.calibration:
            names.add("recalibrate")
        self.study.show_buttons(names, "Try again" if state == "error" else "Start")
        if state == "calibrating":
            self.view = "study"
        self._show_page()
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
        self.monitor.close()
        super().closeEvent(event)
