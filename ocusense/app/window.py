"""The OcuSense main window: study screen and calibration screen.

States:
  ready        nothing running, camera off
  calibrating  camera on, guided calibration (no blinks counted)
  monitoring   camera on, counting blinks, session timer running
  paused       camera OFF, calibration and counts kept
  error        camera could not be used
"""

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QFont, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ocusense.core.calibration import STEPS, GuidedCalibration
from ocusense.core.session import SessionRecorder, SessionStore
from ocusense.core.monitor import (
    CALIBRATION_DONE, CALIBRATION_FAILED, CLOSED_STEP_FINISHED, MODEL_PATH, EyeMonitor,
)

from . import theme
from .artwork import Composition, LogoMark
from .demo import demo_sessions
from .graph import OpennessGraph
from .stats_page import StatsPage
from .worker import MonitorThread, open_camera

PREVIEW_INSET = QSize(4, 4)  # keep the preview image inside its 2 px border

CAMERA_HELP = ("Could not open the camera. On a Mac: System Settings › Privacy & Security › Camera, "
               "allow this app (or Terminal / VS Code when running from there), then reopen it.")

STEP_TEXT = [
    ("Eyes comfortably open", "Look at the screen with your eyes comfortably open."),
    ("Gently close your eyes", "When the countdown ends, close your eyes gently and slowly count to 5. "
                               "A sound tells you when to open them."),
    ("A few natural blinks", "Blink naturally, about 5 times."),
]


def _label(text="", role=None, font=None, wrap=False):
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    if font:
        label.setFont(font)
    label.setWordWrap(wrap)
    return label


def _button(text, kind):
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _rule(thickness=2, role="rule"):
    line = QFrame()
    line.setProperty("role", role)
    line.setFixedHeight(thickness)
    return line


class StatusGlyph(QWidget):
    """Shape + colour, so status never relies on colour alone."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "ready"
        self.setFixedSize(14, 14)

    def set_kind(self, kind):
        self.kind = kind
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = QPen(theme.color(theme.INK), 1.6)
        if self.kind == "monitoring":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.COBALT)))
            p.drawEllipse(QPointF(7, 7), 5.5, 5.5)
        elif self.kind == "calibrating":
            p.setPen(QPen(theme.color(theme.COBALT), 1.8))
            p.drawEllipse(QPointF(7, 7), 5, 5)
            p.setBrush(QBrush(theme.color(theme.COBALT)))
            p.drawEllipse(QPointF(7, 7), 1.8, 1.8)
        elif self.kind == "paused":
            p.setPen(ink)
            p.drawEllipse(QPointF(7, 7), 5, 5)
        elif self.kind == "warning":
            path = QPainterPath(QPointF(7, 1.5))
            path.lineTo(13, 12.5)
            path.lineTo(1, 12.5)
            path.closeSubpath()
            p.setPen(ink)
            p.setBrush(QBrush(theme.color(theme.GOLDEN)))
            p.drawPath(path)
        else:  # ready
            p.setPen(ink)
            p.drawRect(QRectF(2, 2, 10, 10))


class Status(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.glyph = StatusGlyph()
        self.text = _label("Ready", font=theme.ui_font(15, QFont.Weight.Medium))
        layout.addWidget(self.glyph)
        layout.addWidget(self.text)

    def set(self, kind, text):
        self.glyph.set_kind(kind)
        self.text.setText(text)
        self.setAccessibleName("Status: " + text)


class MainWindow(QMainWindow):
    def __init__(self, demo_history=False):
        super().__init__()
        self.setWindowTitle("OcuSense")
        self.resize(1120, 900)
        self.setMinimumSize(920, 820)

        self.monitor = EyeMonitor(MODEL_PATH)
        self.camera = None
        self.thread = None
        self.state = "ready"
        self.elapsed = 0.0  # seconds of monitoring in this session (excluding pauses)
        self.running_since = None
        self.last_update = None
        self.view = "study"  # which tab is shown: "study" or "stats"
        self.demo_history = demo_history
        # Completed sessions: in memory only for now (forgotten when the app quits).
        self.store = SessionStore(demo_sessions() if demo_history else None)
        self.recorder = None  # the session being recorded
        self._ticks = 0

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        outer.addWidget(_rule())
        self.pages = QStackedWidget()
        self.study_page = self._build_study_page()
        self.calibration_page = self._build_calibration_page()
        self.pages.addWidget(self.study_page)
        self.pages.addWidget(self.calibration_page)
        self.stats_page = StatsPage()
        self.stats_page.go_to_study.connect(self.show_study)
        self.pages.addWidget(self.stats_page)
        outer.addWidget(self.pages, 1)

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._refresh_timer)
        self.clock.start(250)

        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop)  # ⌘. on macOS
        self._set_state("ready")

    # ------------------------------------------------------------------ layout
    def _build_header(self):
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(40, 16, 40, 16)
        layout.addWidget(LogoMark(38))
        layout.addSpacing(8)
        wordmark = _label("OcuSense", font=theme.ui_font(25, QFont.Weight.Bold))
        wordmark.setStyleSheet("letter-spacing: -0.5px;")
        layout.addWidget(wordmark)
        layout.addSpacing(36)
        self.nav_study = QPushButton("Study")
        self.nav_stats = QPushButton("Statistics")
        for button, handler in ((self.nav_study, self.show_study), (self.nav_stats, self.show_stats)):
            button.setProperty("kind", "nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(handler)
            layout.addWidget(button)
        layout.addStretch(1)
        self.status = Status()
        layout.addWidget(self.status)
        return header

    def _build_study_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 40, 56, 28)
        layout.setSpacing(28)

        top = QHBoxLayout()
        session = QVBoxLayout()
        session.setSpacing(8)
        session.addWidget(_label("STUDY SESSION", "eyebrow", theme.ui_font(13, QFont.Weight.Bold)))
        self.timer_label = _label("00:00:00", font=theme.number_font(76))
        self.timer_label.setContentsMargins(0, 10, 0, 4)  # room for the tall digits
        self.timer_label.setAccessibleName("Session time")
        session.addWidget(self.timer_label)
        self.blink_label = _label("0 blinks this session", font=theme.ui_font(18))
        session.addWidget(self.blink_label)
        session.addSpacing(14)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start_button = _button("Start", "primary")
        self.pause_button = _button("Pause", "secondary")
        self.resume_button = _button("Resume", "primary")
        self.stop_button = _button("Stop", "quiet")
        self.recalibrate_button = _button("Recalibrate", "quiet")
        self.stop_button.setToolTip("Stop and end this session (⌘.)")
        self.pause_button.setToolTip("Pause — the camera turns off until you resume")
        for button in (self.start_button, self.pause_button, self.resume_button, self.stop_button, self.recalibrate_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.pause)
        self.resume_button.clicked.connect(self.resume)
        self.stop_button.clicked.connect(self.stop)
        self.recalibrate_button.clicked.connect(self.recalibrate)
        session.addLayout(buttons)
        self.message_label = _label("", "secondary", theme.ui_font(14), wrap=True)
        session.addWidget(self.message_label)
        top.addLayout(session, 1)
        top.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        layout.addWidget(_rule())
        heading = QHBoxLayout()
        heading.addWidget(_label("Personal eye openness", font=theme.ui_font(24, QFont.Weight.DemiBold)))
        heading.addStretch(1)
        self.graph_caption = _label("", "secondary", theme.ui_font(14))
        heading.addWidget(self.graph_caption)
        layout.addLayout(heading)
        self.graph = OpennessGraph()
        layout.addWidget(self.graph)
        layout.addWidget(self._legend())
        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(14)
        self.small_preview = QLabel()
        self.small_preview.setFixedSize(128, 96)
        self.small_preview.setStyleSheet(f"border: 2px solid {theme.INK}; border-radius: 8px; background: {theme.PAPER_DEEP};")
        self.small_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.small_preview.setAccessibleName("Camera preview")
        footer.addWidget(self.small_preview)
        privacy = QVBoxLayout()
        privacy.addWidget(_label("Camera preview", font=theme.ui_font(14, QFont.Weight.Bold)))
        privacy.addWidget(_label("Processed on this Mac. Nothing is recorded or uploaded.", "secondary", theme.ui_font(13)))
        footer.addLayout(privacy)
        footer.addStretch(1)
        layout.addLayout(footer)
        return page

    def _legend(self):
        legend = QWidget()
        row = QHBoxLayout(legend)
        row.setContentsMargins(OpennessGraph.LEFT, 0, 0, 0)
        row.setSpacing(24)
        for kind, text in (("line", "Both eyes"), ("dash", "Thresholds"), ("dot", "Blink counted")):
            item = QHBoxLayout()
            item.setSpacing(8)
            swatch = QLabel()
            swatch.setPixmap(self._legend_swatch(kind))
            item.addWidget(swatch)
            item.addWidget(_label(text, font=theme.ui_font(14)))
            row.addLayout(item)
        row.addStretch(1)
        return legend

    @staticmethod
    def _legend_swatch(kind):
        pixmap = QPixmap(28, 14)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if kind == "line":
            p.setPen(QPen(theme.color(theme.COBALT), 2.5))
            p.drawLine(1, 7, 27, 7)
        elif kind == "dash":
            p.setPen(QPen(theme.color(theme.GRAPHITE), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(1, 7, 27, 7)
        else:
            p.setPen(QPen(theme.color(theme.INK), 1.2))
            p.setBrush(QBrush(theme.color(theme.VERMILION)))
            p.drawEllipse(QPointF(14, 7), 5, 5)
        p.end()
        return pixmap

    def _build_calibration_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(56, 40, 56, 40)
        layout.setSpacing(48)

        left = QVBoxLayout()
        left.setSpacing(12)
        self.cal_eyebrow = _label("CALIBRATION", "eyebrow", theme.ui_font(13, QFont.Weight.Bold))
        left.addWidget(self.cal_eyebrow)
        self.cal_title = _label("", font=theme.ui_font(34, QFont.Weight.Bold), wrap=True)
        left.addWidget(self.cal_title)
        self.cal_detail = _label("", "secondary", theme.ui_font(17), wrap=True)
        left.addWidget(self.cal_detail)
        left.addSpacing(10)
        self.cal_count = _label("", font=theme.number_font(64))
        self.cal_count.setStyleSheet(f"color: {theme.COBALT};")
        left.addWidget(self.cal_count)
        self.cal_phase = _label("", font=theme.ui_font(15, QFont.Weight.Bold))
        left.addWidget(self.cal_phase)
        left.addSpacing(10)
        self.cal_steps = []
        for title, _ in STEP_TEXT:
            step = _label(title, font=theme.ui_font(16))
            self.cal_steps.append(step)
            left.addWidget(step)
        left.addSpacing(10)
        self.cal_face = _label("", "secondary", theme.ui_font(14), wrap=True)
        left.addWidget(self.cal_face)
        self.cal_error = _label("", font=theme.ui_font(16, QFont.Weight.Bold), wrap=True)
        left.addWidget(self.cal_error)
        left.addStretch(1)
        actions = QHBoxLayout()
        self.try_again_button = _button("Try again", "primary")
        self.cancel_button = _button("Cancel", "secondary")
        self.try_again_button.clicked.connect(self.retry_calibration)
        self.cancel_button.clicked.connect(self.cancel_calibration)
        actions.addWidget(self.try_again_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        left.addLayout(actions)
        left.addWidget(_label("Measured against your own eyes, not a fixed average. Nothing is recorded.",
                              "secondary", theme.ui_font(13), wrap=True))
        layout.addLayout(left, 1)

        self.big_preview = QLabel()
        self.big_preview.setFixedSize(480, 360)
        self.big_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big_preview.setStyleSheet(f"border: 2px solid {theme.INK}; border-radius: 12px; background: {theme.PAPER_DEEP};")
        self.big_preview.setAccessibleName("Camera preview")
        layout.addWidget(self.big_preview, 0, Qt.AlignmentFlag.AlignTop)
        return page

    # ------------------------------------------------------------- camera life
    def _start_camera(self):
        if self.thread is not None:
            return True
        self.camera = open_camera()
        if self.camera is None:
            self._set_state("error", CAMERA_HELP)
            return False
        self.thread = MonitorThread(self.monitor, self.camera)
        self.thread.updated.connect(self._on_update)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()
        return True

    def _stop_camera(self):
        if self.thread is not None:
            self.thread.requestInterruption()
            self.thread.wait(3000)
            self.thread = None
        if self.camera is not None:
            self.camera.release()  # the camera light turns off
            self.camera = None
        self.small_preview.clear()
        self.big_preview.clear()

    # ---------------------------------------------------------------- actions
    def start(self):
        if not self._start_camera():
            return
        self._finish_session()
        self.monitor.reset_session()
        self.elapsed = 0.0
        if self.monitor.calibration is None:
            self._begin_calibration()
        else:
            self._enter_monitoring()

    def pause(self):
        if self.recorder:
            self.recorder.pause(time.monotonic())
        self._stop_clock()
        self._stop_camera()
        self._set_state("paused")

    def resume(self):
        if self._start_camera():
            self._enter_monitoring()

    def stop(self):
        if self.state == "calibrating":
            self.cancel_calibration()
            return
        self._stop_clock()
        self._stop_camera()
        saved = self._finish_session()
        self.monitor.reset_session()
        self.elapsed = 0.0
        self._set_state("ready", "Session ended — see it under Statistics." if saved else "")

    def recalibrate(self):
        self._stop_clock()
        self._finish_session()  # a new calibration starts a new session
        if self._start_camera():
            self._begin_calibration()

    def retry_calibration(self):
        if self._start_camera():
            self._begin_calibration()

    def cancel_calibration(self):
        self._stop_camera()
        self._set_state("ready", "Calibration cancelled. Press Start to calibrate again.")

    def _begin_calibration(self):
        self.thread.request_calibration()
        self.cal_error.setText("")
        self._set_state("calibrating")

    def _enter_monitoring(self):
        now = time.monotonic()
        self.running_since = now
        if self.recorder is None:
            self.recorder = SessionRecorder(now)
        else:
            self.recorder.resume(now)
        self._set_state("monitoring")

    def _finish_session(self):
        """End the recorded session; keep it for Statistics if it lasted at least 10 seconds."""
        if self.recorder is None:
            return False
        summary = self.recorder.finish(time.monotonic())
        self.recorder = None
        if summary.study_seconds >= 10:
            self.store.add(summary)
            return True
        return False

    def _stop_clock(self):
        if self.running_since is not None:
            self.elapsed += time.monotonic() - self.running_since
            self.running_since = None

    # ---------------------------------------------------------------- updates
    def _on_failed(self, message):
        if self.recorder:
            self.recorder.pause(time.monotonic())
        self._stop_clock()
        self._stop_camera()
        self._set_state("error", message)

    def _on_update(self, update):
        if self.thread is None or (update.source is not None and update.source is not self.thread):
            return  # a late frame from a camera run that has already been stopped
        self.last_update = update
        pixmap = QPixmap.fromImage(update.preview)
        if self.state == "calibrating":
            self._update_calibration(update, pixmap)
            return
        self.small_preview.setPixmap(pixmap.scaled(self.small_preview.size() - PREVIEW_INSET, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
        if self.state != "monitoring":
            return
        if self.recorder:
            self.recorder.add_frame(update.now, update.openness[2] if update.openness else None, update.blinked)
        self.blink_label.setText(f"{update.blinks} blink{'s' if update.blinks != 1 else ''} this session")
        if not update.face_found:
            self.status.set("warning", "Face not tracked")
            self.graph_caption.setText("Measurement paused — face the camera")
        elif not update.reliable:
            self.status.set("warning", "Measurement paused")
            self.graph_caption.setText(f"Paused — {update.reason}")
        else:
            self.status.set("monitoring", "Monitoring")
            self.graph_caption.setText("Last 10 seconds · relative to your own calibration")
        self.graph.set_data(update.samples, update.now)

    def _update_calibration(self, update, pixmap):
        self.big_preview.setPixmap(pixmap.scaled(self.big_preview.size() - PREVIEW_INSET, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
        if CLOSED_STEP_FINISHED in update.events:
            QApplication.beep()  # "you can open your eyes"
        if CALIBRATION_DONE in update.events:
            self.monitor.reset_session()
            self.graph.clear()
            self.elapsed = 0.0
            self._enter_monitoring()
            self.message_label.setText("Calibration complete.")
            return
        if CALIBRATION_FAILED in update.events:
            self.cal_error.setText("Calibration didn’t work: " + update.cal_error)
            self.cal_count.setText("")
            self.cal_phase.setText("")
            self.try_again_button.setVisible(True)
            return
        if update.cal_status != GuidedCalibration.RUNNING or update.cal_step is None:
            return
        self.try_again_button.setVisible(False)
        title, detail = STEP_TEXT[update.cal_step]
        self.cal_eyebrow.setText(f"CALIBRATION · STEP {update.cal_step + 1} OF {len(STEPS)}")
        self.cal_title.setText(title)
        self.cal_detail.setText(detail)
        self.cal_count.setText(str(max(0, math.ceil(update.cal_seconds_left))))
        self.cal_phase.setText("Measuring now" if update.cal_measuring else "Get ready")
        for i, label in enumerate(self.cal_steps):
            prefix = "Done · " if i < update.cal_step else ("Now · " if i == update.cal_step else "Next · ")
            label.setText(prefix + STEP_TEXT[i][0])
            label.setFont(theme.ui_font(16, QFont.Weight.Bold if i == update.cal_step else QFont.Weight.Normal))
        if not update.face_found:
            self.cal_face.setText("Face not found — move into the camera’s view.")
        elif not update.reliable:
            self.cal_face.setText(f"Hold on — {update.reason}.")
        else:
            self.cal_face.setText("Face tracked.")

    def _refresh_timer(self):
        total = self.elapsed + (time.monotonic() - self.running_since if self.running_since is not None else 0)
        seconds = int(total)
        self.timer_label.setText(f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}")
        self._ticks += 1
        if self.view == "stats" and self.state == "monitoring" and self._ticks % 8 == 0:
            self._refresh_stats()  # every 2 seconds while a session is running

    # ------------------------------------------------------------- navigation
    def show_study(self):
        self.view = "study"
        self._show_page()

    def show_stats(self):
        if self.state == "calibrating":
            return
        self.view = "stats"
        self._refresh_stats()
        self._show_page()

    def _refresh_stats(self):
        current = self.recorder.summary(time.monotonic()) if self.recorder else None
        if current is not None and current.study_seconds < 1:
            current = None
        self.stats_page.refresh(self.store.all(), current, self.demo_history)

    def _show_page(self):
        if self.state == "calibrating":
            page = self.calibration_page
        else:
            page = self.stats_page if self.view == "stats" else self.study_page
        self.pages.setCurrentWidget(page)
        self.nav_study.setChecked(page is not self.stats_page)
        self.nav_stats.setChecked(page is self.stats_page)
        self.nav_stats.setEnabled(self.state != "calibrating")

    # ------------------------------------------------------------------ state
    def _set_state(self, state, message=""):
        self.state = state
        show = {
            "ready": {self.start_button} | ({self.recalibrate_button} if self.monitor.calibration else set()),
            "error": {self.start_button},
            "monitoring": {self.pause_button, self.stop_button, self.recalibrate_button},
            "paused": {self.resume_button, self.stop_button},
            "calibrating": set(),
        }[state]
        for button in (self.start_button, self.pause_button, self.resume_button, self.stop_button, self.recalibrate_button):
            button.setVisible(button in show)
        self.start_button.setText("Try again" if state == "error" else "Start")
        if state == "calibrating":
            self.view = "study"
        self._show_page()
        self.message_label.setText(message)

        if state == "ready":
            self.status.set("ready", "Ready")
            self.graph_caption.setText("")
            first = not self.monitor.calibration
            self.graph.clear("Press Start. Your first session begins with a 30-second calibration." if first
                             else "Press Start to begin a new session.")
            self.blink_label.setText("0 blinks this session")
            self.start_button.setFocus()
        elif state == "error":
            self.status.set("warning", "Camera unavailable")
            self.graph.clear("")
        elif state == "paused":
            self.status.set("paused", "Paused")
            self.graph_caption.setText("Paused — the camera is off")
            if self.last_update:
                self.graph.set_data(self.last_update.samples, self.last_update.now, dimmed=True)
        elif state == "calibrating":
            self.status.set("calibrating", "Calibrating")
            self.cal_eyebrow.setText("CALIBRATION")
            self.cal_title.setText("Starting the camera…")
            self.cal_detail.setText("Sit comfortably, facing the screen, with light on your face.")
            self.cal_count.setText("")
            self.cal_phase.setText("")
            self.cal_face.setText("")
            self.try_again_button.setVisible(False)
            self.cancel_button.setFocus()
        elif state == "monitoring":
            self.status.set("monitoring", "Monitoring")
            self.pause_button.setFocus()
        self._refresh_timer()

    def closeEvent(self, event):
        self._finish_session()
        self._stop_camera()
        self.monitor.close()
        super().closeEvent(event)
