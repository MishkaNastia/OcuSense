"""Statistics › All time: every session kept in this run of the app, built from session summaries.

A personal record, not a medical dashboard: exact numbers with units,
gaps for untracked time (never zero), no scores. History lives in memory
only (see storage.py) and the page says so.
"""

from datetime import date

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ocusense.core.models import SessionSummary
from ocusense.core.stats import METRICS, combined_metric, format_duration, format_metric, period_stats

from . import theme
from .widgets.activity_chart import DAY_LABEL_WIDTH, ActivityChart, day_name
from .widgets.artwork import Composition
from .widgets.common import label as _label, rule as _rule, vline as _vline


class Segmented(QWidget):
    """A row of mutually exclusive choices, e.g. Today / This week / This month."""
    changed = Signal(str)

    def __init__(self, options, current, label, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)  # lets the style sheet draw the border
        self.setAccessibleName(label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for key, text in options:
            button = QPushButton(text)
            button.setProperty("kind", "segment")
            button.setCheckable(True)
            button.setChecked(key == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)

    def set_current(self, key):
        self.buttons[key].setChecked(True)


class SessionRow(QWidget):
    def __init__(self, key, title, subtitle, details, expanded, on_toggle, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.button = QPushButton(f"{title}     {subtitle}")
        self.button.setProperty("kind", "row")
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setAccessibleDescription("Show session details")
        self.details = _label(details, font=theme.ui_font(14), wrap=True)
        self.details.setContentsMargins(4, 4, 4, 14)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setVisible(expanded)
        self.button.toggled.connect(lambda on: (self.details.setVisible(on), on_toggle(key, on)))
        layout.addWidget(self.button)
        layout.addWidget(self.details)
        layout.addWidget(_rule(1, "hairline"))


class AllTimePage(QScrollArea):
    go_to_study = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.period, self.metric_key = "today", "rate"
        self.expanded = set()
        self.sessions, self.current, self.demo = [], None, False

        content = QWidget()
        content.setObjectName("Root")
        self.setWidget(content)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(48, 36, 48, 72)
        outer.setSpacing(28)

        # Title
        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(12)
        heading = QHBoxLayout()
        title_col.addWidget(_label("STATISTICS", "eyebrow", theme.ui_font(13, QFont.Weight.Bold)))
        heading.addWidget(_label("All time", font=theme.ui_font(40, QFont.Weight.Bold)))
        self.tag = _label("", font=theme.ui_font(12, QFont.Weight.Bold))
        self.tag.setStyleSheet(f"color: {theme.GRAPHITE}; border: 1px dashed {theme.GRAPHITE}; border-radius: 6px; padding: 2px 8px;")
        heading.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
        heading.addStretch(1)
        title_col.addLayout(heading)
        self.memory_note = _label("", "secondary", theme.ui_font(16), wrap=True)
        title_col.addWidget(self.memory_note)
        title_row.addLayout(title_col, 1)
        outer.addLayout(title_row)

        # New-user state
        self.empty = QWidget()
        empty_row = QHBoxLayout(self.empty)
        empty_row.setContentsMargins(0, 8, 0, 8)
        empty_row.setSpacing(40)
        empty_row.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        empty_text = QVBoxLayout()
        empty_text.addWidget(_label("No sessions yet.",
                                    font=theme.ui_font(28, QFont.Weight.Bold), wrap=True))
        self.empty_detail = _label("", "secondary", theme.ui_font(16), wrap=True)
        empty_text.addWidget(self.empty_detail)
        back = QPushButton("Go to Study")
        back.setProperty("kind", "primary")
        back.clicked.connect(self.go_to_study.emit)
        empty_text.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        empty_text.addStretch(1)
        empty_row.addLayout(empty_text, 1)
        outer.addWidget(self.empty)

        # Everything below is hidden in the new-user state
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        outer.addWidget(self.body)
        outer.addStretch(1)

        summary = QWidget()
        summary_row = QHBoxLayout(summary)
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(0)
        self.summary_values = {}
        for i, (key, text, note) in enumerate((("study", "Total study time", "includes a session in progress"),
                                               ("sessions", "Completed sessions", ""),
                                               ("breaks", "Recorded breaks", "not recorded by the Mac app yet"))):
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(0 if i == 0 else 24, 18, 24, 18)
            col.addWidget(_label(text, "secondary", theme.ui_font(14)))
            value = _label("—", font=theme.number_font(36))
            value.setAccessibleName(text)
            self.summary_values[key] = value
            col.addWidget(value)
            if note:
                col.addWidget(_label(note, "secondary", theme.ui_font(12)))
            if i:
                summary_row.addWidget(_vline())
            summary_row.addWidget(cell, 1)
        body.addWidget(_rule())
        body.addWidget(summary)
        body.addWidget(_rule(1, "hairline"))
        body.addSpacing(26)

        # Date filter: drives the chart and the session list below
        filter_row = QHBoxLayout()
        filter_row.addWidget(_label("By date", font=theme.ui_font(28, QFont.Weight.Bold)))
        filter_row.addSpacing(18)
        self.period_switch = Segmented([("today", "Today"), ("week", "This week"), ("month", "This month")],
                                       self.period, "Date filter")
        self.period_switch.changed.connect(self._set_period)
        filter_row.addWidget(self.period_switch)
        filter_row.addStretch(1)
        body.addLayout(filter_row)
        self.period_summary = _label("", "secondary", theme.ui_font(15), wrap=True)
        body.addWidget(self.period_summary)
        body.addSpacing(14)

        # Study and eye activity
        header = QHBoxLayout()
        header.addWidget(_label("Study and eye activity", font=theme.ui_font(28, QFont.Weight.Bold)))
        header.addStretch(1)
        self.metric_switch = Segmented([("rate", "Blink rate"), ("closure", "Median closure"), ("closed", "Time closed")],
                                       self.metric_key, "Metric")
        self.metric_switch.changed.connect(self._set_metric)
        header.addWidget(self.metric_switch)
        body.addLayout(header)
        body.addWidget(_rule())
        self.metric_title = _label("", font=theme.ui_font(17, QFont.Weight.Bold))
        self.metric_explain = _label("", "secondary", theme.ui_font(15), wrap=True)
        body.addWidget(self.metric_title)
        body.addWidget(self.metric_explain)
        self.chart = ActivityChart()
        body.addWidget(self.chart)
        body.addWidget(self._legend())
        self.details = _label("", font=theme.ui_font(15), wrap=True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(_rule(1, "hairline"))
        body.addWidget(self.details)
        body.addWidget(_label("Measured relative to your own calibration. These describe what the camera saw — "
                              "not a tiredness or health score.", "secondary", theme.ui_font(13), wrap=True))
        body.addSpacing(30)

        # Sessions in the selected period, each expandable to its summary
        body.addWidget(_label("Sessions", font=theme.ui_font(28, QFont.Weight.Bold)))
        body.addWidget(_rule())
        self.session_box = QVBoxLayout()
        self.session_box.setSpacing(0)
        body.addLayout(self.session_box)

    def _legend(self):
        legend = QWidget()
        row = QHBoxLayout(legend)
        row.setContentsMargins(DAY_LABEL_WIDTH + 14, 0, 0, 0)
        row.setSpacing(24)
        for kind, text in (("study", "Study (running)"), ("gap", "Not tracked"), ("line", "Selected measure")):
            swatch = _Swatch(kind)
            item = QHBoxLayout()
            item.setSpacing(8)
            item.addWidget(swatch)
            item.addWidget(_label(text, font=theme.ui_font(14)))
            row.addLayout(item)
        row.addStretch(1)
        return legend

    def _set_period(self, period):
        self.period = period
        self.render()

    def _set_metric(self, metric):
        self.metric_key = metric
        self.render()

    def _toggle(self, key, on):
        (self.expanded.add if on else self.expanded.discard)(key)

    def refresh(self, completed: list[SessionSummary], current: SessionSummary | None = None,
                demo: bool = False) -> None:
        self.sessions, self.current, self.demo = completed, current, demo
        self.render()

    def render(self):
        today = date.today()
        everything = self.sessions + ([self.current] if self.current else [])
        self.period_switch.set_current(self.period)
        self.metric_switch.set_current(self.metric_key)
        self.tag.setText("Demo data" if self.demo else "Kept until you quit")
        self.tag.setToolTip("" if self.demo else "Sessions are kept in memory only and forgotten when OcuSense quits.")
        self.memory_note.setText(
            "Clearly labelled demo sessions, plus any you record now. Statistics aren’t saved to disk." if self.demo else
            "Sessions from this run of OcuSense. They are kept in memory only — when you quit, they are gone, "
            "and earlier runs are not shown. (The raw EAR recording is saved separately; see Settings.)")
        has_any = bool(everything)
        self.empty.setVisible(not has_any)
        self.body.setVisible(has_any)
        self.empty_detail.setText("Press Start on the Study page. Sessions are kept only until you quit "
                                  "OcuSense — earlier runs are not shown here.")
        if not has_any:
            return

        total = sum(s.study_seconds for s in everything)
        self.summary_values["study"].setText(format_duration(total) if total else "—")
        self.summary_values["sessions"].setText(str(sum(1 for s in everything if not s.in_progress)))
        self.summary_values["breaks"].setText("—")

        stats = period_stats(everything, self.period, today)
        completed = [s for s in stats.sessions if not s.in_progress]
        coverage = f"{stats.coverage * 100:.0f}%" if stats.coverage is not None else "—"
        self.period_summary.setText(
            f"{format_duration(stats.study_seconds) if stats.study_seconds else 'No'} study · "
            f"{len(completed)} completed session{'s' if len(completed) != 1 else ''} · tracking coverage {coverage}")

        m = METRICS[self.metric_key]
        self.metric_title.setText(f"{m['name']}  ·  {m['unit']}")
        self.metric_explain.setText(m["explain"])
        self.chart.set_data(stats, self.metric_key, today, self.period)

        values = [s.metric(self.metric_key) for s in stats.sessions if s.metric(self.metric_key) is not None]
        not_tracked = stats.study_seconds - stats.tracked_seconds
        rng = (f"{format_metric(self.metric_key, min(values))} – {format_metric(self.metric_key, max(values))}"
               if values else "—")
        self.details.setText(
            f"<span style='color:{theme.GRAPHITE}'>Average</span>&nbsp; <b>{format_metric(self.metric_key, combined_metric(stats.sessions, self.metric_key))}</b>"
            f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:{theme.GRAPHITE}'>Range across sessions</span>&nbsp; <b>{rng}</b>"
            f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:{theme.GRAPHITE}'>Not tracked</span>&nbsp; <b>{format_duration(max(0, not_tracked)) if stats.study_seconds else '—'}</b>"
        )

        while self.session_box.count():
            item = self.session_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = sorted(stats.sessions, key=lambda s: s.started_at, reverse=True)
        if not rows:
            self.session_box.addWidget(_label("No sessions in this period.", "secondary", theme.ui_font(15)))
        for s in rows:
            key = s.started_at.isoformat()
            when = day_name(s.started_at.date(), today) + ", " + s.started_at.strftime("%H:%M") + "–" + (
                "now" if s.in_progress else s.ended_at.strftime("%H:%M"))
            subtitle = ("In progress · " if s.in_progress else "") + f"{format_duration(s.study_seconds)} study · {s.blinks} blinks"
            paused = (s.ended_at - s.started_at).total_seconds() - s.study_seconds
            coverage = f"{s.coverage * 100:.0f}%" if s.coverage is not None else "—"
            details = (
                f"<span style='color:{theme.GRAPHITE}'>Duration</span>&nbsp; {format_duration(s.study_seconds)} study"
                + (f", {format_duration(paused)} paused" if paused >= 60 else "") + "<br>"
                f"<span style='color:{theme.GRAPHITE}'>Measurement</span>&nbsp; "
                f"blink rate {format_metric('rate', s.metric('rate'))} · median closure {format_metric('closure', s.metric('closure'))} · "
                f"{format_metric('closed', s.metric('closed'), with_unit=False)} closed · {coverage} tracked<br>"
                f"<span style='color:{theme.GRAPHITE}'>Breaks and check-ins</span>&nbsp; not recorded yet"
            )
            self.session_box.addWidget(SessionRow(key, when, subtitle, details, key in self.expanded, self._toggle))


class _Swatch(QWidget):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.setFixedSize(24, 14)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.kind == "study":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.INK)))
            p.drawRoundedRect(QRectF(1, 2, 22, 10), 2, 2)
        elif self.kind == "gap":
            p.setPen(QPen(theme.color(theme.GRAPHITE), 1.25, Qt.PenStyle.DashLine))
            p.drawRoundedRect(QRectF(1, 2, 22, 10), 2, 2)
        else:
            p.setPen(QPen(theme.color(theme.COBALT), 2.5))
            p.drawLine(1, 7, 23, 7)
