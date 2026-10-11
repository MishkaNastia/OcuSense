"""Settings, grouped as Monitoring, Reminders, Appearance, and Data & privacy.

Only controls that work are shown as controls. Features the Mac app doesn't have
yet are described in words with a "Not available yet" tag — never as switches
that do nothing. The window connects the signals; this page holds no state.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.config import (
    CAMERA_INDEX, PROXIMITY_COOLDOWN_CHOICES, PROXIMITY_COOLDOWN_SECONDS, PROXIMITY_SUSTAIN_SECONDS,
    PROXIMITY_WARN_RATIO, RECORDING_CHUNK_SECONDS,
)
from ocusense.system import COMPUTER, NOTIFICATION_NAME, THIS_APP

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph, tag_label
from .widgets.segmented import Segmented


def setting_row(title: str, detail: str, control: QWidget | None = None, tag: str = "",
                extra: tuple = ()) -> QWidget:
    """Title and explanation (plus any `extra` labels) on the left, the control (or a tag) on the right."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 6, 0, 6)
    layout.setSpacing(24)
    text = QVBoxLayout()
    text.setSpacing(3)
    text.addWidget(label(title, font=theme.ui_font(16, QFont.Weight.DemiBold)))
    if detail:
        explanation = label(detail, "secondary", theme.ui_font(14), wrap=True)
        explanation.setMinimumWidth(320)  # wrapped labels need a width to compute their height
        text.addWidget(explanation)
    for widget in extra:
        widget.setMinimumWidth(320)
        text.addWidget(widget)
    layout.addLayout(text, 1)
    if control is not None:
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    if tag:
        layout.addWidget(tag_label(tag), 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def interval_text(seconds: float) -> str:
    """5 s, 30 s, 1 min, 10 min …"""
    return f"{seconds:g} s" if seconds < 60 else f"{seconds / 60:g} min"


def _button(text: str, kind: str) -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("kind", kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return widget


class SettingsPage(Page):
    recalibrate_requested = Signal()
    distance_interval_changed = Signal(float)  # seconds between distance reminders
    eye_rest_changed = Signal(bool)  # 20-20-20 eye rest switched on or off
    lighting_changed = Signal(bool)  # lighting check switched on or off
    clear_history_requested = Signal()
    new_reference_requested = Signal()
    theme_chosen = Signal(str)  # "miro" or "haring", applied at once

    def __init__(self, parent=None):
        super().__init__("Settings", "Settings", "Reminder choices are remembered; the other settings apply while "
                                                 "OcuSense is open.", parent)

        # Monitoring
        self.section("Monitoring")
        self.recalibrate_button = _button("Recalibrate", "secondary")
        self.recalibrate_button.clicked.connect(self.recalibrate_requested.emit)
        self.calibration_row_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(setting_row("Calibration", "", self.recalibrate_button, extra=(self.calibration_row_detail,)))
        self.posture = QCheckBox("On")
        self.posture.setAccessibleName("Posture monitoring")
        self.body.addWidget(setting_row(
            "Posture monitoring",
            "Watches your head angle, distance from the screen and slumping, compared with the first 2 minutes "
            "after each eye calibration (Statistics › Current session). Shown live only; nothing about your posture is saved. Remembered between launches.", self.posture))
        self.body.addWidget(setting_row("Calibration sound",
                                        "A short system sound tells you when to open your eyes after the “gently "
                                        "closed” step. It is always on, because your eyes are closed then."))
        self.details = QCheckBox("Show")
        self.details.setAccessibleName("Show measurement details on the Study page")
        self.body.addWidget(setting_row("Measurement details",
                                        "Raw values, data quality and the calibration in use, below the "
                                        "measurements on the Study page.", self.details))
        self.body.addWidget(setting_row("Camera", f"Your computer’s own camera (camera {CAMERA_INDEX}). Images are analysed on "
                                                  f"this {COMPUTER} and never saved or uploaded."))

        # Reminders
        self.section("Reminders")
        self.reminders = QCheckBox("On")
        self.reminders.setChecked(True)
        self.reminders.setAccessibleName("Break reminders")
        self.body.addWidget(setting_row(
            "Break reminders",
            f"A {NOTIFICATION_NAME} (and a note on the Study page) when you have been blinking less often than in your "
            "reference for several minutes: 3 windows of five minutes in a row below p = 0.01 with longer intervals. "
            "At most one per slow stretch and one every 20 minutes. Faster blinking never triggers one.",
            self.reminders))
        self.distance = QCheckBox("On")
        self.distance.setChecked(True)
        self.distance.setAccessibleName("Distance reminder")
        self.interval = QComboBox()
        self.interval.setAccessibleName("Remind again after")
        for seconds in PROXIMITY_COOLDOWN_CHOICES:
            self.interval.addItem(interval_text(seconds), float(seconds))
        self.interval.currentIndexChanged.connect(
            lambda i: (self._explain_distance(), self.distance_interval_changed.emit(self.interval.itemData(i))))
        self.distance.toggled.connect(self.interval.setEnabled)
        controls = QWidget()
        controls_row = QHBoxLayout(controls)
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(10)
        controls_row.addWidget(label("Remind again after", "secondary", theme.ui_font(14)))
        controls_row.addWidget(self.interval)
        controls_row.addSpacing(8)
        controls_row.addWidget(self.distance)
        self.distance_explain = label("", "secondary", theme.ui_font(14), wrap=True)
        self.distance_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(setting_row("Distance reminder", "", controls,
                                        extra=(self.distance_explain, self.distance_detail)))
        self.set_distance_interval(PROXIMITY_COOLDOWN_SECONDS)
        self.eye_rest = QCheckBox("On")
        self.eye_rest.setAccessibleName("Eye rest every 20 minutes")
        self.body.addWidget(setting_row(
            "Eye rest every 20 minutes",
            "Off unless you switch it on. Then, after 20 minutes of monitored screen time, a card asks you to look "
            "about 6 metres (20 feet) away for 20 seconds, with a countdown. A pause of 20 s or more (like a "
            "Pomodoro break) starts the count again.", self.eye_rest))
        self.eye_rest.toggled.connect(self.eye_rest_changed.emit)
        self.lighting = QCheckBox("On")
        self.lighting.setAccessibleName("Lighting check")
        self.body.addWidget(setting_row(
            "Lighting check",
            "Off unless you switch it on. Then, if your room stays dark for a minute while you study, a card "
            "suggests a lamp (a bright screen in a dark room is hard on the eyes; you’re not a bat). Uses only the picture’s "
            "average brightness (never saved); webcams adjust their exposure, so it is a rough guide.",
            self.lighting))
        self.lighting.toggled.connect(self.lighting_changed.emit)

        # Appearance
        self.section("Appearance")
        self.theme_switch = Segmented(tuple(theme.THEME_NAMES.items()), theme.ACTIVE, "Theme")
        self.theme_switch.changed.connect(self._theme_picked)
        theme_controls = QWidget()
        theme_row = QHBoxLayout(theme_controls)
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(12)
        theme_row.addWidget(self.theme_switch)
        theme_row.addStretch(1)
        self.body.addWidget(setting_row(
            "Theme", "Miró: warm paper and calm colours. Keith Haring: bold colours, thick black lines and a "
            "couple of dancers in the sidebar. Switches right away, and OcuSense remembers your pick.",
            theme_controls))
        self.body.addWidget(setting_row("Motion", "Animations follow the Animations switch on the Pomodoro page, "
                                                  "and turn off when your system asks for reduced motion."))

        # Data & privacy
        self.section("Data & privacy")
        self.body.addWidget(paragraph(
            f"Camera images are analysed in memory on this {COMPUTER} and thrown away immediately. They are never saved "
            "or uploaded. Statistics (session times, blink counts, closure durations) are <b>kept only until you "
            f"quit OcuSense</b>. Saved on this {COMPUTER}: your calibration (a few numbers, reused every time OcuSense "
            "opens), the raw EAR recording, your reference for blink timing (below) and your reminder choices.",
            rich=True))
        self.record = QCheckBox("Record")
        self.record.setChecked(True)
        self.record.setAccessibleName("Record the raw EAR of every frame")
        self.show_folder = _button("Show in Finder", "quiet")
        self.show_folder.clicked.connect(self._open_folder)
        controls = QWidget()
        controls_row = QHBoxLayout(controls)
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.addWidget(self.show_folder)
        controls_row.addWidget(self.record)
        self.recording_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.recording_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(setting_row(
            "Raw EAR recording",
            f"While the camera is on, the left and right Eye Aspect Ratio of every frame is saved with its time "
            "and your calibrated openness, as a CSV file (plus the calibration used) every "
            f"{RECORDING_CHUNK_SECONDS / 60:.0f} minutes and when you pause, stop or quit. Numbers only, no images.", controls, extra=(self.recording_detail,)))
        self.folder = None
        self.reference_button = _button("Make a new reference…", "secondary")
        self.reference_button.clicked.connect(self.new_reference_requested.emit)
        self.reference_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.reference_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(setting_row(
            "Reference for blink timing",
            "The time between your blinks in the first 10 minutes of one session. Every session is compared with "
            "it (Statistics › Current session). Saved as numbers only; kept when you recalibrate.",
            self.reference_button, extra=(self.reference_detail,)))
        self.clear_button = _button("Clear session history…", "secondary")
        self.clear_button.clicked.connect(self.clear_history_requested.emit)
        self.history_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(setting_row("Session history", "", self.clear_button, extra=(self.history_detail,)))
        self.finish()

    def show_lighting(self, on: bool) -> None:
        """Show the remembered choice without announcing it as a change."""
        self.lighting.blockSignals(True)
        self.lighting.setChecked(on)
        self.lighting.blockSignals(False)

    def show_eye_rest(self, on: bool) -> None:
        """Show the remembered choice without announcing it as a change."""
        self.eye_rest.blockSignals(True)
        self.eye_rest.setChecked(on)
        self.eye_rest.blockSignals(False)

    def set_distance_interval(self, seconds: float) -> None:
        """Show a chosen interval (from preferences) without announcing it as a change."""
        self.interval.blockSignals(True)
        self.interval.setCurrentIndex(max(0, self.interval.findData(float(seconds))))
        self.interval.blockSignals(False)
        self._explain_distance()

    def _explain_distance(self) -> None:
        every = interval_text(self.interval.currentData())
        self.distance_explain.setText(
            f"“Trying to lick the screen?” appears when your face looks {PROXIMITY_WARN_RATIO:g}× as big as during "
            f"calibration (roughly {100 / PROXIMITY_WARN_RATIO:.0f} % of the distance) for "
            f"{PROXIMITY_SUSTAIN_SECONDS:g} s; again every {every} while you stay that close, and never more often "
            f"than that. Shown in the window, and as a {NOTIFICATION_NAME} while OcuSense is in the background.")
        self.fit_height()

    def show_distance(self, enabled: bool, has_reference: bool) -> None:
        if not enabled:
            text = "Off."
        elif not has_reference:
            text = "Recalibrate to use it: the current calibration has no reference distance."
        else:
            text = "On."
        self.distance_detail.setText(text)
        self.fit_height()

    def show_recording(self, log) -> None:
        """log: the window's EarRecording."""
        self.folder = log.directory
        if log.last_error:
            status = log.last_error
        elif not log.enabled:
            status = "Recording is off."
        elif log.files_written:
            status = f"{log.files_written} file{'s' if log.files_written != 1 else ''} saved since OcuSense opened."
        else:
            status = "No file saved yet in this run."
        home = str(Path.home())
        folder = str(log.directory)
        shown = "~" + folder[len(home):] if folder.startswith(home) else folder
        self.recording_detail.setText(f"{status} Folder: {shown}")
        self.fit_height()

    def show_reference(self, reference, error: str, path: Path) -> None:
        """reference: the saved ocusense.reference.Reference, or None."""
        home = str(Path.home())
        shown = "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)
        if error:
            text = f"{error} Make a new reference to replace it. File: {shown}"
        elif reference is None:
            text = "No reference yet: the first 10 minutes of your next session become it."
        else:
            text = (f"Made from the session of {reference.label()}: {reference.n} intervals, median "
                    f"{reference.median:.1f} s between blinks. File: {shown}")
        self.reference_detail.setText(text)
        self.reference_button.setEnabled(reference is not None or bool(error))

    def _theme_picked(self, name: str) -> None:
        self.theme_chosen.emit(name)

    def _open_folder(self) -> None:
        if self.folder is not None:
            self.folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))

    def show_state(self, calibration_text: str, can_recalibrate: bool, completed_sessions: int) -> None:
        self.calibration_row_detail.setText(calibration_text)
        self.recalibrate_button.setEnabled(can_recalibrate)
        self.history_detail.setText(
            f"{completed_sessions} completed session{'s' if completed_sessions != 1 else ''} in memory. "
            "Clearing removes them from Statistics; a running session is not affected."
            if completed_sessions else "No completed sessions yet.")
        self.clear_button.setEnabled(completed_sessions > 0)
        self.fit_height()
