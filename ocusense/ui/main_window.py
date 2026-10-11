"""The OcuSense main window: sidebar navigation and the session life cycle.

It connects the pieces and holds no layouts of its own pages:
  Sidebar                                        — navigation and the monitoring status
  StudyPage / CalibrationView                    — Study
  CurrentSessionPage / AllTimePage / PatternsPage — Statistics
  SettingsPage / AccountPage                     — at the bottom of the sidebar
  TimeLogPage                                    — Time log (subjects, projects and when you work on them)
  CameraWorker (monitoring/camera_worker.py)     — frames in, structured results out
  SessionRecorder + SessionStore                 — numbers kept for Statistics
  EarRecording (recording.py)                    — raw EAR of every frame, saved as CSV files
  CalibrationStore (calibration_store.py)        — the personal calibration, saved once and reused
  ProximityMonitor + AlertBanner                 — the distance reminder (banner + macOS notification)

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
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ocusense.calibration_store import CalibrationStore
from ocusense.preferences import Preferences
from ocusense.config import CLOSE_BELOW, MIN_SESSION_SECONDS, MODEL_PATH, REOPEN_ABOVE
from ocusense.core.baseline_drift import BreakReminder, LiveDrift
from ocusense.core.posture import PostureCalibration
from ocusense.core.calibration import GuidedCalibration
from ocusense.core.eye_rest import EyeRestTimer
from ocusense.core.lighting import LightingMonitor
from ocusense.core.proximity import ProximityMonitor
from ocusense.core.session import SessionRecorder
from ocusense.demo_data import demo_sessions
from ocusense.monitoring.camera_worker import CameraWorker, MonitorUpdate, open_camera
from ocusense import notifications
from ocusense import reference as reference_file
from ocusense.monitoring.pipeline import (
    CALIBRATION_DONE, CALIBRATION_FAILED, CLOSED_STEP_FINISHED, SCREEN_TILTED, EyeMonitor,
)
from ocusense.recording import EarRecording
from ocusense.storage import SessionStore
from ocusense.system import COMPUTER, camera_help, camera_permission, relaunch, request_camera_permission

from .account_page import AccountPage
from .account_service import AccountService
from .all_time_page import AllTimePage
from .calibration_view import CalibrationView
from .current_session_page import CurrentSessionPage
from .settings_page import SettingsPage
from .sidebar import STATISTICS_PAGES, Sidebar
from .eye_rest_card import BODY as EYE_REST_BODY, TITLE as EYE_REST_TITLE, EyeRestCard
from .games_page import GamesPage
from .library_page import LibraryPage, PaintingWall
from .lighting_card import BODY as LIGHTING_BODY, TITLE as LIGHTING_TITLE, LightingCard
from .menu_bar import MenuBarIcon
from .pomodoro_page import PomodoroPage
from .session_summary import SessionExtras, SessionSummaryCard
from .study_page import StudyPage
from .time_log_page import TimeLogPage
from .widgets.alert_banner import AlertBanner, TooCloseMark
from .widgets.common import vline

TILT_MESSAGE = "Screen tilted! Relearning how you sit, give me 2 minutes"
BREAK_MESSAGE = "Hey, you should take a break, else your eyes will become drier than the Sahara desert."
POMODORO_MESSAGES = {  # next phase → (title, message)
    "short_break": ("Focus round done, nice work!", "Short break time. Look out of a window: your eyes have been "
                    "staring at pixels for a while."),
    "long_break": ("That’s a full set of focus rounds!", "Long break time. Stand up, stretch, find a snack. "
                   "The screen will still be here, we promise."),
    "focus": ("Break’s over", "Back to it! The next focus round is ready when you are."),
}
DISTANCE_TITLE = "Trying to lick the screen?"
DISTANCE_BODY = "Go easy on your eyes and move back a little."

CAMERA_HELP = camera_help()  # in this system's words (ocusense/system.py)

BUTTONS_FOR_STATE = {
    "ready": {"start"},  # + "recalibrate" once calibrated
    "error": {"start"},
    "monitoring": {"pause", "stop", "recalibrate"},
    "paused": {"resume", "stop"},
    "calibrating": set(),
    "playing": set(),  # a game uses the camera; the study session (if any) waits, paused
}


class MainWindow(QMainWindow):
    permission_answered = Signal(bool)  # macOS camera question answered (from Apple's thread)

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
        self.view = "study"  # the sidebar page shown: study, current, all_time, settings, account, …
        self.demo_history = demo_history
        self.store = SessionStore(demo_sessions() if demo_history else None)  # in memory for now
        self.recorder: SessionRecorder | None = None
        self._drift: tuple[SessionRecorder, LiveDrift] | None = None  # comparison with the reference
        self._reminder: BreakReminder | None = None  # break reminders for that session
        self.notify = notifications.post  # replaced in tests
        self._after_permission = None  # set while macOS asks for camera access
        self._next_after_permission = None
        self.permission_answered.connect(self._on_permission)
        self.reference_path = reference_file.default_path()
        self.reference: reference_file.Reference | None = None  # the saved reference for blink timing
        self.reference_error = ""
        self._reference_checked: SessionRecorder | None = None  # the session whose first 10 min were considered
        try:
            self.reference = reference_file.load(self.reference_path)
        except reference_file.ReferenceFileError as error:
            self.reference_error = str(error)  # never overwritten automatically
        self.ear_log = EarRecording()  # raw EAR per frame, written every 10 minutes
        self.calibration_store = CalibrationStore()  # calibrate once, reuse on every launch
        self.preferences = Preferences.load()  # remembered Settings choices
        self.proximity = ProximityMonitor(cooldown_seconds=self.preferences.distance_reminder_interval)
        self.distance_reminder = self.preferences.distance_reminder  # Settings › Reminders
        self.eye_rest = EyeRestTimer()  # 20-20-20 (off unless switched on in Settings)
        self._eye_rest_waiting = False  # due while another reminder was on screen
        self.lighting = LightingMonitor()  # off unless switched on in Settings
        self._lighting_waiting = False
        self.session_extras = SessionExtras()  # reminders and focus rounds in the running session
        self.summary_card: SessionSummaryCard | None = None
        self.monitor.posture_enabled = self.preferences.posture_monitoring  # Settings › Monitoring (camera not running yet)
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
        self.settings_page = SettingsPage()
        self.account_service = AccountService()
        self.account_page = AccountPage(self.account_service)
        self.account_service.changed.connect(
            lambda account: self.sidebar.set_account_label(AccountPage.sidebar_label(account)))
        self.sidebar.set_account_label(AccountPage.sidebar_label(self.account_service.account))
        self.account_service.restore()  # renews a saved sign-in in the background
        self.pomodoro_page = PomodoroPage(self.preferences)
        self.pomodoro_page.checks["animations"].toggled.connect(lambda _on: self._apply_painter_animations())
        self._apply_painter_animations()
        self.games_page = GamesPage(self)
        self.library_page = LibraryPage(self.games_page.blink_garden.store)
        self.time_log_page = TimeLogPage(preferences=self.preferences)
        self.time_log_page.status_text.connect(self.sidebar.set_time_log_status)
        self.time_log_page.running_changed.connect(self._time_log_running)
        self.page_for = {"study": self.study, "current": self.current_page, "all_time": self.stats_page,
                         "settings": self.settings_page, "account": self.account_page,
                         "pomodoro": self.pomodoro_page, "games": self.games_page,
                         "time_log": self.time_log_page, "library": self.library_page}
        self.pages = QStackedWidget()
        for page in (self.study, self.calibration, self.current_page, self.stats_page,
                     self.settings_page, self.account_page, self.pomodoro_page, self.games_page,
                     self.time_log_page, self.library_page):
            self.pages.addWidget(page)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.distance_banner = AlertBanner(DISTANCE_TITLE, DISTANCE_BODY, ("Got it", "Reminder settings"),
                                           TooCloseMark())
        self.distance_banner.action.connect(self._banner_action)
        self.distance_banner.setVisible(False)
        holder = QWidget()  # gives the card some room from the window edges
        holder_row = QVBoxLayout(holder)
        holder_row.setContentsMargins(40, 16, 40, 0)
        holder_row.addWidget(self.distance_banner)
        self.banner_holder = holder
        holder.setVisible(False)
        column.addWidget(holder)
        self.eye_rest_card = EyeRestCard()  # the 20-20-20 reminder, below the distance reminder
        self.eye_rest_card.finished.connect(lambda _how: self.eye_rest.rested())
        column.addWidget(self.eye_rest_card)
        self.lighting_card = LightingCard()  # the lighting check, below the other reminders
        self.lighting_card.finished.connect(self._lighting_card_closed)
        column.addWidget(self.lighting_card)
        from .blink_garden_page import GardenReminderCard
        self.garden_reminder = GardenReminderCard(self, self.games_page.blink_garden)
        column.addWidget(self.garden_reminder)
        self.painting_wall = PaintingWall(self.games_page.blink_garden.store)
        self.library_page.changed.connect(self.painting_wall.refresh)
        self.sidebar.paintings_layout.addWidget(self.painting_wall)
        column.addWidget(self.pages, 1)
        outer.addWidget(content, 1)

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
        self.current_page.calibrate_posture.connect(self.calibrate_posture)
        self.settings_page.posture.setChecked(self.preferences.posture_monitoring)
        self.current_page.set_posture_enabled(self.preferences.posture_monitoring)
        self.settings_page.posture.toggled.connect(self._set_posture_monitoring)
        self.settings_page.clear_history_requested.connect(self.clear_history)
        self.settings_page.new_reference_requested.connect(self.make_new_reference)
        self.settings_page.theme_chosen.connect(self._set_theme)
        self.settings_page.restart_requested.connect(self.restart)
        self.settings_page.record.toggled.connect(self._set_recording)
        self.settings_page.distance.setChecked(self.distance_reminder)
        self.settings_page.set_distance_interval(self.preferences.distance_reminder_interval)
        self.settings_page.distance.toggled.connect(self._set_distance_reminder)
        self.settings_page.distance_interval_changed.connect(self._set_distance_interval)
        self.pomodoro_page.status_text.connect(self.sidebar.set_pomodoro_status)
        self.pomodoro_page.phase_ended.connect(self._pomodoro_phase_ended)
        self.pomodoro_page.state_changed.connect(self._pomodoro_state_changed)
        self.settings_page.show_eye_rest(self.preferences.eye_rest)
        self.settings_page.eye_rest_changed.connect(self._set_eye_rest)
        self.settings_page.show_lighting(self.preferences.lighting_check)
        self.settings_page.lighting_changed.connect(self._set_lighting)
        self.settings_page.details.toggled.connect(self.study.details_button.setChecked)
        self.study.details_button.toggled.connect(self.settings_page.details.setChecked)

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(250)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop)  # ⌘. on macOS
        self._set_state("ready")
        self._load_saved_calibration(announce=True)
        self.menu_bar = MenuBarIcon(self)  # the eye in the macOS menu bar

    # ------------------------------------------------------------- camera life
    def _camera_then(self, then) -> bool:
        """_start_camera, remembering what to do once macOS's camera question is answered with Allow,
        so the very first Start doesn't need a second click."""
        self._next_after_permission = then
        try:
            return self._start_camera()
        finally:
            self._next_after_permission = None

    def _start_camera(self) -> bool:
        if self.thread is not None:
            return True
        then = self._next_after_permission
        permission = camera_permission()
        if permission == "undetermined":
            already_asking = self._after_permission is not None
            self._after_permission = then or (lambda: None)
            self.study.message_label.setText("Click Allow in the macOS camera question. OcuSense carries on by itself "
                                             "right after.")
            if not already_asking and not request_camera_permission(self.permission_answered.emit):
                self._after_permission = None
                self._set_state("error", CAMERA_HELP)
            return False
        if permission == "denied":
            self._set_state("error", CAMERA_HELP)
            return False
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
    def _on_permission(self, granted: bool) -> None:
        then, self._after_permission = self._after_permission, None
        if granted and then is not None:
            then()  # carry on exactly where you were: start, resume or calibrate
        elif not granted:
            self._set_state("error", CAMERA_HELP)

    def start(self) -> None:
        if not self._camera_then(self.start):
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
        self._clear_distance_reminder()
        self._set_state("paused")

    def resume(self) -> None:
        if self._camera_then(self.resume):
            self._enter_monitoring()

    def stop(self) -> None:
        if self.state == "calibrating":
            self.cancel_calibration()
            return
        self._stop_clock()
        self._stop_camera()
        self._save_recording()
        self._clear_distance_reminder()
        saved = self._finish_session()
        self.monitor.reset_session()
        self.elapsed = 0.0
        self._set_state("ready", "Session saved. Have a peek under Statistics whenever you like." if saved else "")
        if saved:
            self._show_session_summary()

    def _show_session_summary(self) -> None:
        """The recap card after Stop (doesn't block the window)."""
        if self.summary_card is not None:
            self.summary_card.close()
        self.summary_card = SessionSummaryCard(self.last_summary, self.session_extras, self)
        self.summary_card.see_statistics.connect(lambda: self.show_page("all_time"))
        self.summary_card.open()

    def recalibrate(self) -> None:
        self._stop_clock()
        self._finish_session()  # a new calibration starts a new session
        if self._camera_then(self.retry_calibration):
            self._begin_calibration()

    def retry_calibration(self) -> None:
        if self._camera_then(self.retry_calibration):
            self._begin_calibration()

    def cancel_calibration(self) -> None:
        self._stop_camera()
        self._save_recording()
        if self._load_saved_calibration():  # a cancelled recalibration keeps the saved calibration
            self._set_state("ready", "No worries, recalibration cancelled. Your saved calibration is still on duty.")
        else:
            self._set_state("ready", "Calibration cancelled. Press Start whenever you want to try again.")

    def _load_saved_calibration(self, announce: bool = False) -> bool:
        """Use the calibration saved on this computer, if there is a valid one. Only while the camera is off."""
        saved = self.calibration_store.load()
        if saved is None:
            if announce and self.calibration_store.last_error:
                self.study.message_label.setText(self.calibration_store.last_error + " Press Start to calibrate again.")
            return False
        self.monitor.use_calibration(saved.calibration, saved.calibrated_at)
        if announce:
            self._set_state("ready", f"Welcome back! Using your calibration from {saved.calibrated_at.day} "
                                     f"{saved.calibrated_at:%b %Y}. New lamp, glasses or chair? Recalibrate.")
        return True

    def _begin_calibration(self) -> None:
        self._clear_distance_reminder()  # a new calibration sets a new reference distance
        self.thread.request_calibration()
        self._set_state("calibrating")

    def _enter_monitoring(self) -> None:
        now = time.monotonic()
        self.running_since = now
        if self.recorder is None:
            self.recorder = SessionRecorder(now, calibration=self.monitor.calibration_info)
            self.session_extras = SessionExtras()
            self.study.clear_measurements()
        else:
            self.recorder.resume(now)
        self._set_state("monitoring")
        m = self.monitor
        if (m.posture_enabled and m.calibration is not None and m.posture_monitor is None
                and m.posture_calibrator.status != PostureCalibration.RUNNING and self.thread is not None):
            self.thread.request_posture_calibration()  # ticked while the camera was off, or after a pause

    def _finish_session(self) -> bool:
        """End the recorded session; keep it for Statistics if it was long enough."""
        if self.recorder is None:
            return False
        summary = self.recorder.finish(time.monotonic())
        self.recorder = None
        self._drift = None
        if summary.study_seconds >= MIN_SESSION_SECONDS:
            self.store.add(summary)
            self.last_summary = summary
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
        self._clear_distance_reminder()
        self._set_state("error", message)

    def _on_update(self, update: MonitorUpdate) -> None:
        if self.thread is None or (update.source is not None and update.source is not self.thread):
            return  # a late frame from a camera run that has already been stopped
        self.last_update = update
        if self.state == "playing":
            self.games_page.feed(update)  # game blinks never reach the session, the recording or reminders
            return
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
        if SCREEN_TILTED in update.events:
            self.notify(TILT_MESSAGE, "OcuSense")  # the posture baseline is recorded again (2 min)
            self.study.message_label.setText(f"{TILT_MESSAGE} ({datetime.now():%H:%M}).")
        self._check_distance(update.now, update.closeness)
        self._check_lighting(update.now, update.brightness)
        self.study.set_live_openness(update.observation)
        self.study.set_blinks(update.blinks)
        if not update.face_found:
            self.status.set("warning", "Face not tracked")
            self.study.graph_caption.setText("Measurement paused. Come back, the camera misses you")
        elif not update.reliable:
            self.status.set("warning", "Measurement paused")
            self.study.graph_caption.setText(f"Paused: {update.reason}")
        else:
            self.status.set("monitoring", "Monitoring")
            self.study.graph_caption.setText("Last 10 seconds · relative to your own calibration")
        self.study.graph.set_data(update.samples, update.now)
        if self.view == "current":  # only paint the second graph while it is visible
            self.current_page.set_graph(update.samples, update.now, caption=self.study.graph_caption.text())
            self.current_page.show_posture(update)

    def _set_posture_monitoring(self, on: bool) -> None:
        """The Settings tick. With the camera on, it is switched on the camera thread before the next frame."""
        self.preferences.posture_monitoring = on
        self.preferences.save()
        self.current_page.set_posture_enabled(on)
        if self.thread is not None:
            self.thread.request_posture_enabled(on)
        elif on:
            self.monitor.posture_enabled = True  # the baseline starts when monitoring does
        else:
            self.monitor.set_posture_enabled(False, time.monotonic())

    def calibrate_posture(self) -> None:
        """A new 2-minute posture baseline, recorded on the camera thread while monitoring; the eye calibration is kept."""
        if not self.settings_page.posture.isChecked():
            self.current_page.posture_detail.setText(self.current_page.posture_off_text)
            return
        if self.state != "monitoring" or self.thread is None:
            self.current_page.posture_detail.setText("Start a session first: posture can only be learned while "
                                                     "the camera is watching.")
            return
        self.thread.request_posture_calibration()

    def _on_calibration_update(self, update: MonitorUpdate) -> None:
        if CLOSED_STEP_FINISHED in update.events:
            QApplication.beep()  # "you can open your eyes"
        if CALIBRATION_DONE in update.events:
            saved = self.monitor.calibration_info is not None and self.calibration_store.save(
                self.monitor.calibration, self.monitor.calibration_info)
            self.monitor.reset_session()
            self.study.graph.clear()
            self.elapsed = 0.0
            self._enter_monitoring()
            self.study.message_label.setText(
                "Has anyone told you you have pretty eyes? We’re calibrated, and next time you can start right away."
                if saved
                else self.calibration_store.last_error or "Calibration complete.")
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
        self._check_eye_rest(time.monotonic())
        self.garden_reminder.tick(time.monotonic())
        if self._ticks % 4 == 0 and getattr(self, "menu_bar", None) is not None:
            self.menu_bar.refresh()  # once a second
        if self.state == "monitoring" and self.recorder and self._ticks % 2 == 0:
            self._refresh_measurements()  # twice per second
        if self.state == "monitoring" and self.recorder and self._ticks % 4 == 0:
            drift = self._drift_for(self.recorder)
            new = drift.update(self.recorder.distributions.intervals, time.monotonic())
            self._save_reference_if_new()
            for result in new if drift.baseline_fit is not None else ():  # no usable baseline: nothing to compare
                if self._reminder.update(result, drift.baseline_fit.mu) and self.settings_page.reminders.isChecked():
                    self._remind()
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
                self.current_page.show_drift(self._drift_for(self.recorder), self.recorder.distributions.intervals,
                                             time.monotonic(), self.reference, self.reference_error)
            if current is not None and self.last_update is not None and self.state != "monitoring":
                self.current_page.set_graph(self.last_update.samples, self.last_update.now, dimmed=True,
                                            caption="Paused. The camera is off")
        elif self.view == "all_time":
            self.stats_page.refresh(sessions, current, self.demo_history)

    def _drift_for(self, recorder: SessionRecorder) -> LiveDrift:
        """The comparison for this session: with the saved reference, or (without one) its own first 10 minutes."""
        if self._drift is None or self._drift[0] is not recorder:
            saved = self.reference.intervals if self.reference else None
            self._drift = (recorder, LiveDrift(recorder.distributions.start, reference=saved))
            self._reminder = BreakReminder()
            self.study.hide_reminder()
        return self._drift[1]

    # ------------------------------------------------------- 20-20-20 eye rest
    def _check_eye_rest(self, now: float) -> None:
        if not self.preferences.eye_rest:
            return
        if self.eye_rest.update(now, self.state == "monitoring"):
            self._eye_rest_waiting = True
        if self._eye_rest_waiting and self.banner_holder.isHidden() and self.eye_rest_card.isHidden():
            self._eye_rest_waiting = False  # never on top of the distance reminder
            self.session_extras.eye_rests += 1
            self.eye_rest_card.show_card()
            if self.in_background():
                self.notify(EYE_REST_BODY, EYE_REST_TITLE)

    def _set_theme(self, name: str) -> None:
        self.preferences.theme = name
        self.preferences.save()

    def restart(self) -> None:
        """Open a fresh OcuSense (for a new theme) and close this one; the session is saved on close."""
        if relaunch():
            self.close()
            QApplication.instance().quit()

    def in_background(self) -> bool:
        """True when you're not looking at OcuSense (another app in front, or the window hidden)."""
        app = QApplication.instance()
        return app.applicationState() != Qt.ApplicationState.ApplicationActive or not self.isActiveWindow()

    def _set_eye_rest(self, on: bool) -> None:
        self.preferences.eye_rest = on
        self.preferences.save()
        self.eye_rest.rested()  # switching on starts a fresh 20 minutes
        if not on:
            self._eye_rest_waiting = False
            self.eye_rest_card.setVisible(False)

    def _apply_painter_animations(self) -> None:
        """The sidebar painter follows the Animations switch and macOS Reduce motion, like the Pomodoro dial."""
        self.sidebar.painter.set_animations(self.preferences.animations and not self.pomodoro_page.reduce_motion)

    def _pomodoro_state_changed(self, phase: str, state: str) -> None:
        """Focus round running → monitor; break or Pomodoro paused → pause monitoring (camera off, eyes rest)."""
        if not self.preferences.pomodoro_monitoring or self.state in ("calibrating", "playing"):
            return
        if phase == "focus" and state == "running":
            if self.state in ("ready", "error"):
                self.start()  # the very first time this calibrates first
            elif self.state == "paused":
                self.resume()
        elif state == "running" or state == "paused":  # a break running, or the Pomodoro paused
            if self.state == "monitoring":
                self.pause()
                self.study.message_label.setText("Paused for your break. The camera is off, so go look at "
                                                 "something that isn’t a screen." if phase != "focus"
                                                 else "Paused along with the Pomodoro.")

    def _time_log_running(self, running: bool) -> None:
        """A time-log timer started → eye monitoring starts (or resumes); stopped → the session ends."""
        if not self.preferences.time_log_monitoring or self.state in ("calibrating", "playing"):
            return
        if running:
            if self.state in ("ready", "error"):
                self.start()  # the very first time this calibrates first
            elif self.state == "paused":
                self.resume()
        elif self.state in ("monitoring", "paused"):
            self.stop()  # saved under Statistics, with the summary card

    def _pomodoro_phase_ended(self, ended) -> None:
        """A Pomodoro phase finished: a notification (whether or not OcuSense is in view) and an optional sound."""
        prefs = self.preferences
        if ended.phase == "focus" and ended.completed and self.recorder is not None:
            self.session_extras.focus_rounds += 1
        if prefs.pomodoro_sound:
            QApplication.beep()
        if not prefs.pomodoro_notify:
            return
        title, message = POMODORO_MESSAGES[ended.next_phase]
        if not ended.started_automatically:
            message += " Press Start in OcuSense when you’re ready."
        self.notify(message, title)

    def _remind(self) -> None:
        """Blinking less often than in the reference, confirmed: suggest a break (notification + Study page)."""
        self.session_extras.break_reminders += 1
        self.notify(BREAK_MESSAGE, "Time for a break")
        self.study.show_reminder(f"{BREAK_MESSAGE} ({datetime.now():%H:%M})")

    def _save_reference_if_new(self) -> None:
        """Without a reference, a session's first 10 minutes become it once complete (if usable). Tried once per session."""
        recorder, drift = self._drift
        if (self.reference is not None or self.reference_error or drift.fixed or drift.baseline_pairs is None
                or self._reference_checked is recorder):
            return
        self._reference_checked = recorder
        pairs = [(a - drift.start, b - drift.start) for a, b in drift.baseline_pairs]
        info = recorder.calibration
        calibration = {k: (v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else v)
                       for k, v in asdict(info).items()} if info else None
        new = reference_file.from_pairs(pairs, recorder.started_at, "live session", calibration)
        if new is None:
            return  # too few intervals: the next session tries again
        try:
            reference_file.save(new, self.reference_path)
        except OSError as error:
            self.reference_error = f"Couldn’t save the reference: {error.strerror or error}"
            return
        self.reference = new

    def make_new_reference(self) -> None:
        box = QMessageBox(QMessageBox.Icon.Warning, "Make a new reference?",
                          "This discards the saved reference. The first 10 minutes of your next session become "
                          "the new one. A session that is running now keeps its current comparison.", parent=self)
        discard = box.addButton("Discard Reference", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Cancel))
        if self._confirm(box) is not discard:
            return
        try:
            reference_file.discard(self.reference_path)
        except OSError as error:
            self.reference_error = f"Couldn’t remove the reference: {error.strerror or error}"
        else:
            self.reference = None
            self.reference_error = ""
            if self.recorder is not None:
                self._reference_checked = self.recorder  # the running session doesn't become the new reference
        self._refresh_settings()

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
            text = (f"Calibrated on {calibration.calibrated_at.day} {calibration.calibrated_at:%b %Y at %H:%M}. Saved on this {COMPUTER} and reused "
                    "every time you open OcuSense. Recalibrate if lighting, glasses or your position change.")
        elif self.monitor.calibration:
            text = "Calibrated. Recalibrate if lighting, glasses or your position change."
        else:
            text = "Not calibrated yet. Your first session starts with a short calibration (about 25 s), and OcuSense remembers it."
        can = bool(self.monitor.calibration) and self.state in ("ready", "monitoring")
        if not can and self.monitor.calibration and self.state == "paused":
            text += " Resume or stop the session to recalibrate."
        completed = sum(1 for s in self.store.all() if not s.in_progress)
        self.settings_page.show_state(text, can, completed)
        self.settings_page.show_recording(self.ear_log)
        self.settings_page.show_reference(self.reference, self.reference_error, self.reference_path)
        has_reference = bool(getattr(self.monitor.calibration, "face_scale", None))
        self.settings_page.show_distance(self.distance_reminder, has_reference or not self.monitor.calibration)

    # ------------------------------------------------------- distance reminder
    def _check_distance(self, now: float, closeness: float | None) -> None:
        if not self.distance_reminder:
            return
        if self.proximity.update(now, closeness):
            self.session_extras.distance_reminders += 1
            self.banner_holder.setVisible(True)
            self.distance_banner.setVisible(True)
            if self.in_background():
                self.notify(DISTANCE_BODY, DISTANCE_TITLE)  # OcuSense is in the background (notifications.post)
        elif not self.proximity.too_close and not self.banner_holder.isHidden():
            self.banner_holder.setVisible(False)  # moved back: the reminder goes away by itself

    def _clear_distance_reminder(self) -> None:
        self.proximity.reset()
        self.banner_holder.setVisible(False)
        self.lighting.reset()  # pause/stop/recalibrate: the dark stretch starts over
        self._lighting_waiting = False

    # ------------------------------------------------------- lighting check
    def _check_lighting(self, now: float, brightness: float | None) -> None:
        if not self.preferences.lighting_check:
            return
        if self.lighting.update(now, brightness):
            self._lighting_waiting = True
        elif not self.lighting.dark and not self.lighting_card.isHidden():
            self.lighting_card.setVisible(False)  # the room is lit again
        if (self._lighting_waiting and self.banner_holder.isHidden() and self.eye_rest_card.isHidden()
                and self.lighting_card.isHidden()):
            self._lighting_waiting = False  # never on top of another reminder
            self.session_extras.lighting_reminders += 1
            self.lighting_card.setVisible(True)
            if self.in_background():
                self.notify(LIGHTING_BODY, LIGHTING_TITLE)

    def _lighting_card_closed(self, how: str) -> None:
        if how == "turn off":
            self.settings_page.lighting.setChecked(False)  # saves the choice through _set_lighting

    def _set_lighting(self, on: bool) -> None:
        self.preferences.lighting_check = on
        self.preferences.save()
        self.lighting.reset()
        if not on:
            self._lighting_waiting = False
            self.lighting_card.setVisible(False)

    def _banner_action(self, name: str) -> None:
        self.banner_holder.setVisible(False)
        if name == "Reminder settings":
            self.show_page("settings")

    def _set_distance_interval(self, seconds: float) -> None:
        self.proximity.cooldown_seconds = seconds
        self.preferences.distance_reminder_interval = seconds
        self.preferences.save()

    def _set_distance_reminder(self, on: bool) -> None:
        self.distance_reminder = on
        self.preferences.distance_reminder = on
        self.preferences.save()
        if not on:
            self._clear_distance_reminder()
        self._refresh_settings()

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
            self.study.graph.clear("Press Start. First time? A quick calibration comes first." if first
                                   else "Press Start when you’re ready to study.")
            self.study.set_blinks(0)
            self.study.clear_measurements()
            self.study.start_button.setFocus()
        elif state == "error":
            self.status.set("warning", "Camera unavailable")
            self.study.graph.clear("")
        elif state == "paused":
            self.status.set("paused", "Paused")
            self.study.graph_caption.setText("Paused. The camera is off and resting too")
            self.study.set_live_openness(None)
            if self.last_update:
                self.study.graph.set_data(self.last_update.samples, self.last_update.now, dimmed=True)
        elif state == "calibrating":
            self.status.set("calibrating", "Calibrating")
            self.calibration.reset()
        elif state == "monitoring":
            self.status.set("monitoring", "Monitoring")
            self.study.pause_button.setFocus()
        elif state == "playing":
            self.status.set("monitoring", "Playing Blink Code")
            self.study.graph.clear("A game is using the camera. Your study session waits until you go back.")
        self._tick()

    # ------------------------------------------------------------------ games
    def start_game_camera(self) -> str:
        """Let a game use the camera. Returns "" on success, otherwise why not (shown by the game)."""
        if self.state == "calibrating":
            return "Finish the calibration first."
        if not self.monitor.calibration:
            return "Calibrate once on the Study page first. The game needs to know what your open and closed eyes look like."
        if self.state == "playing":
            return ""
        if self.state == "monitoring":
            self.pause()  # the study session waits, paused; nothing from the game is recorded in it
        if not self._start_camera():
            if self._after_permission is not None:
                return "Click Allow in the macOS camera question, then press the camera button again."
            return "The camera couldn’t be opened."
        self.monitor.interrupt()
        self._set_state("playing", "A game is borrowing the camera. Your study session is paused and waiting.")
        return ""

    def stop_game_camera(self) -> None:
        if self.state != "playing":
            return
        self._stop_camera()
        self.monitor.interrupt()
        self._set_state("paused" if self.recorder is not None else "ready",
                        "Welcome back from the game! Press Resume to continue your session." if self.recorder else "")

    def title_bar_blended(self, height: int) -> None:
        """The title bar became transparent (ui/window_chrome.py): keep the logo clear of the window buttons."""
        layout = self.sidebar.layout()
        m = layout.contentsMargins()
        layout.setContentsMargins(m.left(), m.top() + height, m.right(), m.bottom())

    def closeEvent(self, event) -> None:
        self._finish_session()
        self._stop_camera()
        self.ear_log.flush()  # the last minutes of EAR data
        self.monitor.close()
        super().closeEvent(event)
