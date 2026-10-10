"""Statistics › Current session: the running (or paused) session, from the live recorder.

Every number comes from SessionRecorder.summary() (the same data the All time page
uses once the session ends). Unavailable values are "—", never 0.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.core.models import SessionSummary
from ocusense.core.stats import METRICS, format_duration, format_metric

from . import theme
from .widgets.artwork import Composition
from .widgets.common import label, rule, vline
from .widgets.openness_graph import OpennessGraph
from .widgets.page import Page, paragraph

UNAVAILABLE = "—"


def value_row(cells) -> tuple[QWidget, dict]:
    """A row of (key, title, explanation) cells with large values; returns the row and the value labels."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    values = {}
    for i, (key, title, explain) in enumerate(cells):
        if i:
            layout.addWidget(vline())
        cell = QWidget()
        col = QVBoxLayout(cell)
        col.setContentsMargins(0 if i == 0 else 22, 14, 22, 14)
        col.setSpacing(4)
        col.addWidget(label(title, font=theme.ui_font(14, QFont.Weight.Bold)))
        value = label(UNAVAILABLE, font=theme.number_font(30))
        value.setAccessibleName(title)
        values[key] = value
        col.addWidget(value)
        if explain:
            col.addWidget(label(explain, "secondary", theme.ui_font(12), wrap=True))
        col.addStretch(1)
        layout.addWidget(cell, 1)
    return row, values


class CurrentSessionPage(Page):
    go_to_study = Signal()

    def __init__(self, parent=None):
        super().__init__("Statistics", "Current session",
                         "The session you are running now, measured relative to your own calibration.", parent)

        # Empty state: no session
        self.empty = QWidget()
        empty = QHBoxLayout(self.empty)
        empty.setContentsMargins(0, 8, 0, 8)
        empty.setSpacing(36)
        empty.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.addWidget(label("No session is running.", font=theme.ui_font(26, QFont.Weight.Bold), wrap=True))
        text.addWidget(paragraph("Start a session on the Study page. Its time, tracking coverage and "
                                 "measurements appear here while it runs.", 16, secondary=True))
        go = QPushButton("Go to Study")
        go.setProperty("kind", "primary")
        go.clicked.connect(self.go_to_study.emit)
        text.addWidget(go, 0, Qt.AlignmentFlag.AlignLeft)
        text.addStretch(1)
        empty.addLayout(text, 1)
        self.body.addWidget(self.empty)

        # Session content
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(rule())
        row, self.time_values = value_row((
            ("duration", "Study time", "running time, pauses excluded"),
            ("coverage", "Tracking coverage", "share of study time with both eyes measured"),
            ("blinks", "Blinks counted", "completed blinks this session"),
        ))
        body.addWidget(row)
        body.addWidget(rule(1, "hairline"))

        self.section("Eye measurements · whole session so far", body)
        row, self.metric_values = value_row(tuple(
            (key, METRICS[key]["name"], METRICS[key]["explain"]) for key in ("rate", "closure", "closed")))
        body.addWidget(row)
        body.addWidget(label("Averaged over all tracked time in this session. The Study page shows the last 60 seconds.",
                             "secondary", theme.ui_font(13), wrap=True))

        self.section("Personal eye openness", body)
        self.graph_caption = label("", "secondary", theme.ui_font(14))
        body.addWidget(self.graph_caption)
        self.graph = OpennessGraph()
        body.addWidget(self.graph)
        body.addWidget(label("Relative to your calibrated open and closed positions — not a fatigue score.",
                             "secondary", theme.ui_font(13), wrap=True))

        self.section("Breaks and check-ins", body)
        body.addWidget(paragraph("Breaks and check-ins aren’t recorded by the Mac app yet, so none are shown "
                                 "for this session.", secondary=True))
        self.body.addWidget(self.content)
        self.finish()
        self.show_session(None)

    def show_session(self, summary: SessionSummary | None, paused: bool = False) -> None:
        has = summary is not None
        self.empty.setVisible(not has)
        self.content.setVisible(has)
        self.set_tag(("Paused" if paused else "In progress") if has else "")
        if not has:
            self.graph.clear()
            return
        self.time_values["duration"].setText(format_duration(summary.study_seconds))
        coverage = summary.coverage
        self.time_values["coverage"].setText(UNAVAILABLE if coverage is None else f"{coverage * 100:.0f}%")
        self.time_values["blinks"].setText(str(summary.blinks))
        for key, value in self.metric_values.items():
            value.setText(format_metric(key, summary.metric(key)))

    def set_graph(self, samples, now, dimmed: bool = False, caption: str = "") -> None:
        self.graph.set_data(samples, now, dimmed=dimmed)
        self.graph_caption.setText(caption)
