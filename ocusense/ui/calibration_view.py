"""The guided calibration screen. It shows progress; the calibration rules live in core/calibration.py."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ocusense.core.calibration import STEPS

from . import theme
from .study_page import scaled_preview
from .widgets.common import button, label

# What to tell the person in each calibration step (same order as core.calibration.STEPS).
STEP_TEXT = [
    ("Eyes comfortably open", "Look at the screen with your eyes comfortably open."),
    ("Gently close your eyes", "When the countdown ends, close your eyes gently and slowly count to 5. "
                               "A sound tells you when to open them."),
    ("A few natural blinks", "Blink naturally, about 5 times."),
]
assert len(STEP_TEXT) == len(STEPS)


PREVIEW_MAX_WIDTH = 480
PREVIEW_MIN_WIDTH = 280
TEXT_MIN_WIDTH = 360


class CalibrationView(QScrollArea):
    """Scrolls on short windows; the camera preview shrinks so the instructions keep their width."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Root")
        self.setWidget(content)
        layout = QHBoxLayout(content)
        layout.setContentsMargins(56, 40, 56, 40)
        layout.setSpacing(48)

        left = QVBoxLayout()
        left.setSpacing(12)
        self.eyebrow = label("CALIBRATION", "eyebrow", theme.ui_font(13, QFont.Weight.Bold))
        self.title = label("", font=theme.ui_font(34, QFont.Weight.Bold), wrap=True)
        self.detail = label("", "secondary", theme.ui_font(17), wrap=True)
        self.countdown = label("", font=theme.number_font(64))
        self.countdown.setStyleSheet(f"color: {theme.COBALT};")
        self.phase = label("", font=theme.ui_font(15, QFont.Weight.Bold))
        for widget in (self.eyebrow, self.title, self.detail):
            left.addWidget(widget)
        left.addSpacing(10)
        left.addWidget(self.countdown)
        left.addWidget(self.phase)
        left.addSpacing(10)
        self.steps = [label(title, font=theme.ui_font(16)) for title, _ in STEP_TEXT]
        for step in self.steps:
            left.addWidget(step)
        left.addSpacing(10)
        self.face = label("", "secondary", theme.ui_font(14), wrap=True)
        self.error = label("", font=theme.ui_font(16, QFont.Weight.Bold), wrap=True)
        left.addWidget(self.face)
        left.addWidget(self.error)
        left.addStretch(1)
        actions = QHBoxLayout()
        self.try_again_button = button("Try again", "primary")
        self.cancel_button = button("Cancel", "secondary")
        actions.addWidget(self.try_again_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        left.addLayout(actions)
        left.addWidget(label("Measured against your own eyes, not a fixed average. Nothing is recorded.",
                             "secondary", theme.ui_font(13), wrap=True))
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMinimumWidth(TEXT_MIN_WIDTH)
        layout.addWidget(left_widget, 1)

        self.preview = QLabel()
        self.preview.setFixedSize(PREVIEW_MAX_WIDTH, PREVIEW_MAX_WIDTH * 3 // 4)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"border: 2px solid {theme.INK}; border-radius: 12px; background: {theme.PAPER_DEEP};")
        self.preview.setAccessibleName("Camera preview")
        layout.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

    def reset(self) -> None:
        """Shown while the camera starts, before the first step."""
        self.eyebrow.setText("CALIBRATION")
        self.title.setText("Starting the camera…")
        self.detail.setText("Sit comfortably, facing the screen, with light on your face.")
        for widget in (self.countdown, self.phase, self.face, self.error):
            widget.setText("")
        self.try_again_button.setVisible(False)
        self.cancel_button.setFocus()

    def show_progress(self, step: int, seconds_left: float, measuring: bool, face_found: bool,
                      reliable: bool, reason: str) -> None:
        self.try_again_button.setVisible(False)
        title, detail = STEP_TEXT[step]
        self.eyebrow.setText(f"CALIBRATION · STEP {step + 1} OF {len(STEPS)}")
        self.title.setText(title)
        self.detail.setText(detail)
        self.countdown.setText(str(max(0, math.ceil(seconds_left))))
        self.phase.setText("Measuring now" if measuring else "Get ready")
        for i, widget in enumerate(self.steps):
            prefix = "Done · " if i < step else ("Now · " if i == step else "Next · ")
            widget.setText(prefix + STEP_TEXT[i][0])
            widget.setFont(theme.ui_font(16, QFont.Weight.Bold if i == step else QFont.Weight.Normal))
        if not face_found:
            self.face.setText("Face not found — move into the camera’s view.")
        elif not reliable:
            self.face.setText(f"Hold on — {reason}.")
        else:
            self.face.setText("Face tracked.")

    def show_failure(self, reason: str) -> None:
        self.error.setText("Calibration didn’t work: " + reason)
        self.countdown.setText("")
        self.phase.setText("")
        self.try_again_button.setVisible(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        margins = 56 * 2 + 48  # page margins and the gap between text and preview
        width = max(PREVIEW_MIN_WIDTH, min(PREVIEW_MAX_WIDTH, self.viewport().width() - margins - TEXT_MIN_WIDTH))
        self.preview.setFixedSize(width, width * 3 // 4)

    def set_preview(self, pixmap: QPixmap) -> None:
        self.preview.setPixmap(scaled_preview(pixmap, self.preview))

    def clear_preview(self) -> None:
        self.preview.clear()
