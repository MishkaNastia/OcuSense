"""Settings, grouped as Monitoring, Reminders, Appearance, and Data & privacy.

Only controls that work are shown as controls. Features the Mac app doesn't have
yet are described in words with a "Not available yet" tag — never as switches
that do nothing. The window connects the signals; this page holds no state.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.config import CAMERA_INDEX, RECORDING_CHUNK_SECONDS

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph, tag_label


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
    row.setMaximumWidth(860)
    return row


def _button(text: str, kind: str) -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("kind", kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return widget


class SettingsPage(Page):
    recalibrate_requested = Signal()
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Settings", "Settings", "Settings apply while OcuSense is open.", parent)

        # Monitoring
        self.section("Monitoring")
        self.recalibrate_button = _button("Recalibrate", "secondary")
        self.recalibrate_button.clicked.connect(self.recalibrate_requested.emit)
        self.calibration_row_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(setting_row("Calibration", "", self.recalibrate_button, extra=(self.calibration_row_detail,)))
        self.body.addWidget(setting_row("Calibration sound",
                                        "A short system sound tells you when to open your eyes after the “gently "
                                        "closed” step. It is always on, because your eyes are closed then."))
        self.details = QCheckBox("Show")
        self.details.setAccessibleName("Show measurement details on the Study page")
        self.body.addWidget(setting_row("Measurement details",
                                        "Raw values, data quality and the calibration in use, below the "
                                        "measurements on the Study page.", self.details))
        self.body.addWidget(setting_row("Camera", f"Built-in camera (camera {CAMERA_INDEX}). Images are analysed on "
                                                  "this Mac and never saved or uploaded."))

        # Reminders
        self.section("Reminders")
        self.body.addWidget(setting_row("Break reminders and check-ins",
                                        "Not in the Mac app yet. The planned gentle prompts can be tried in the "
                                        "sample session on the OcuSense website.", tag="Not available yet"))

        # Appearance
        self.section("Appearance")
        self.body.addWidget(setting_row("Theme", "OcuSense uses its light paper theme. A dark appearance isn’t "
                                                 "available yet.", tag="Not available yet"))
        self.body.addWidget(setting_row("Motion", "The Mac app uses no decorative animation."))

        # Data & privacy
        self.section("Data & privacy")
        self.body.addWidget(paragraph(
            "Camera images are analysed in memory on this Mac and thrown away immediately — they are never saved "
            "or uploaded. Statistics (session times, blink counts, closure durations) are <b>kept only until you "
            "quit OcuSense</b>. The raw EAR recording below is the only thing saved to disk.", rich=True))
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
            f"{RECORDING_CHUNK_SECONDS / 60:.0f} minutes and when you pause, stop or quit. Numbers only — no images.", controls, extra=(self.recording_detail,)))
        self.folder = None
        self.clear_button = _button("Clear session history…", "secondary")
        self.clear_button.clicked.connect(self.clear_history_requested.emit)
        self.history_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(setting_row("Session history", "", self.clear_button, extra=(self.history_detail,)))
        self.finish()

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
