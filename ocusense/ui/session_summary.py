"""The end-of-session summary card, shown after Stop. Display only.

A short recap in the OcuSense (Miró) style: study time, blinks, the measurements
over the whole session, tracking coverage, Pomodoro rounds and the reminders that
came up. Descriptive numbers only — no score, no verdict. Opens without blocking the
window (QDialog.open()).
"""

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.core.models import SessionSummary
from ocusense.core.stats import format_duration, format_metric

from . import theme
from .widgets.artwork import Composition
from .widgets.common import label, rule


@dataclass
class SessionExtras:
    """What happened during a session besides the measurements (counted by the window)."""
    distance_reminders: int = 0
    eye_rests: int = 0
    break_reminders: int = 0
    focus_rounds: int = 0
    notes: list = field(default_factory=list)


def _button(text: str, kind: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


def _cell(title: str, value: str, note: str = "") -> QWidget:
    cell = QWidget()
    layout = QVBoxLayout(cell)
    layout.setContentsMargins(0, 6, 18, 6)
    layout.setSpacing(2)
    layout.addWidget(label(title, "secondary", theme.ui_font(13)))
    value_label = label(value, font=theme.number_font(26))
    value_label.setAccessibleName(title)
    layout.addWidget(value_label)
    if note:
        layout.addWidget(label(note, "secondary", theme.ui_font(12), wrap=True))
    return cell


class SessionSummaryCard(QDialog):
    see_statistics = Signal()

    def __init__(self, summary: SessionSummary, extras: SessionExtras, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session complete")
        self.setObjectName("Root")
        self.setStyleSheet(f"QDialog#Root {{ background: {theme.PAPER}; border: 2px solid {theme.INK}; }}")
        self.setMinimumWidth(680)
        self.values: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.setSpacing(12)
        top = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("SESSION COMPLETE", "eyebrow", theme.ui_font(13, QFont.Weight.Bold)))
        when = f"{summary.started_at:%H:%M}–{summary.ended_at:%H:%M}"
        text.addWidget(label(format_duration(summary.study_seconds) + " of study",
                             font=theme.ui_font(32, QFont.Weight.Bold)))
        text.addWidget(label(f"Today, {when}. Pauses not counted.", "secondary", theme.ui_font(14)))
        text.addStretch(1)
        top.addLayout(text, 1)
        top.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)  # drawn at its own fixed size
        layout.addLayout(top)
        layout.addWidget(rule())

        coverage = f"{summary.coverage * 100:.0f}%" if summary.coverage is not None else "—"
        rows = [
            ("blinks", "Blinks counted", str(summary.blinks), ""),
            ("rate", "Blink rate", format_metric("rate", summary.metric("rate")), "per minute of tracked time"),
            ("closure", "Median closure", format_metric("closure", summary.metric("closure")), ""),
            ("closed", "Time classified as closed", format_metric("closed", summary.metric("closed")), ""),
            ("coverage", "Tracking coverage", coverage, "share of study time with both eyes measured"),
            ("focus", "Pomodoro focus rounds", str(extras.focus_rounds), "completed during this session"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        for i, (key, title, value, note) in enumerate(rows):
            self.values[key] = value
            grid.addWidget(_cell(title, value, note), i // 3, i % 3)
        layout.addLayout(grid)
        layout.addWidget(rule(1, "hairline"))

        reminders = []
        for count, one, many in ((extras.distance_reminders, "distance reminder", "distance reminders"),
                                 (extras.eye_rests, "eye-rest reminder", "eye-rest reminders"),
                                 (extras.break_reminders, "break reminder", "break reminders")):
            if count:
                reminders.append(f"{count} {one if count == 1 else many}")
        self.values["reminders"] = ", ".join(reminders) if reminders else "No reminders this session."
        layout.addWidget(label("Reminders: " + self.values["reminders"] if reminders else self.values["reminders"],
                               font=theme.ui_font(15), wrap=True))
        layout.addWidget(label("These describe what the camera measured — not a tiredness or health score.",
                               "secondary", theme.ui_font(12), wrap=True))

        actions = QHBoxLayout()
        actions.addStretch(1)
        close = _button("Close", "quiet")
        close.clicked.connect(self.accept)
        stats = _button("See statistics", "primary")
        stats.clicked.connect(lambda: (self.see_statistics.emit(), self.accept()))
        actions.addWidget(close)
        actions.addWidget(stats)
        layout.addLayout(actions)
        stats.setFocus()
