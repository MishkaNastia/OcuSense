"""Settings, grouped as Monitoring, Reminders, Appearance, and Data & privacy.

Only controls that work are shown as controls. Features the Mac app doesn't have
yet are described in words with a "Not available yet" tag — never as switches
that do nothing. The window connects the signals; this page holds no state.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.config import CAMERA_INDEX

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph, tag_label


def setting_row(title: str, detail: str, control: QWidget | None = None, tag: str = "") -> QWidget:
    """Title and explanation on the left, the control (or a tag) on the right."""
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
        calibration = setting_row("Calibration", "", self.recalibrate_button)
        calibration.layout().itemAt(0).layout().addWidget(self.calibration_row_detail)
        self.body.addWidget(calibration)
        self.body.addWidget(setting_row("Calibration sound",
                                        "A short system sound tells you when to open your eyes after the “gently "
                                        "closed” step. It is always on, because your eyes are closed then."))
        self.details = QCheckBox("Show")
        self.details.setAccessibleName("Show measurement details on the Study page")
        self.body.addWidget(setting_row("Measurement details",
                                        "Raw values, data quality and the calibration in use, below the "
                                        "measurements on the Study page.", self.details))
        self.body.addWidget(setting_row("Camera", f"Built-in camera (camera {CAMERA_INDEX}). Frames are analysed on "
                                                  "this Mac and never recorded or uploaded."))

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
            "Camera images are analysed in memory on this Mac and thrown away immediately. Session numbers "
            "(times, blink counts, closure durations) are <b>kept only until you quit OcuSense</b> — nothing is "
            "saved to disk and nothing is uploaded.", rich=True))
        self.clear_button = _button("Clear session history…", "secondary")
        self.clear_button.clicked.connect(self.clear_history_requested.emit)
        self.history_detail = label("", "secondary", theme.ui_font(14), wrap=True)
        history = setting_row("Session history", "", self.clear_button)
        history.layout().itemAt(0).layout().addWidget(self.history_detail)
        self.body.addWidget(history)
        self.finish()

    def show_state(self, calibration_text: str, can_recalibrate: bool, completed_sessions: int) -> None:
        self.calibration_row_detail.setText(calibration_text)
        self.recalibrate_button.setEnabled(can_recalibrate)
        self.history_detail.setText(
            f"{completed_sessions} completed session{'s' if completed_sessions != 1 else ''} in memory. "
            "Clearing removes them from Statistics; a running session is not affected."
            if completed_sessions else "No completed sessions yet.")
        self.clear_button.setEnabled(completed_sessions > 0)
