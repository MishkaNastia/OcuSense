"""The Statistics page ("Your patterns"), built from session summaries.

A personal record, not a medical dashboard: exact numbers with units,
gaps for untracked time (never zero), no scores.
"""

from datetime import date, datetime, time as dtime

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ocusense.core.stats import (
    METRICS, combined_metric, format_duration, format_metric, hour_range, minute_series, period_stats,
)

from . import theme
from .artwork import Composition

DAY_LABEL_WIDTH = 104
VALUE_WIDTH = 132


def _label(text="", role=None, font=None, wrap=False):
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    if font:
        label.setFont(font)
    label.setWordWrap(wrap)
    return label


def _rule(thickness=2, role="rule"):
    line = QFrame()
    line.setProperty("role", role)
    line.setFixedHeight(thickness)
    return line


def day_name(day, today):
    return "Today" if day == today else day.strftime("%a %-d %b")


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


class ActivityChart(QWidget):
    """Timeline rows (one per day) plus, for Today, a per-minute line on the same time axis."""

    ROW = 34
    AXIS = 24
    LINE_CHART = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self.days, self.today, self.stats, self.metric_key, self.sessions = [], date.today(), None, "rate", []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Timeline of study sessions")

    def set_data(self, stats, metric, today, period):
        self.stats, self.metric_key, self.today, self.period = stats, metric, today, period
        self.days = stats.days
        self.sessions = stats.sessions
        self.start_hour, self.end_hour = hour_range(self.sessions)
        height = len(self.days) * self.ROW + self.AXIS + (self.LINE_CHART + 16 if period == "today" else 0)
        self.setFixedHeight(height)
        rows = []
        for day in self.days:
            on_day = stats.sessions_on(day)
            value = combined_metric(on_day, metric)
            rows.append(f"{day_name(day, today)}: " + (
                f"{format_duration(sum(s.study_seconds for s in on_day))} study, "
                f"{METRICS[metric]['name'].lower()} {format_metric(metric, value)}" if on_day else "no sessions"))
        self.setAccessibleDescription("; ".join(rows))
        self.update()

    def _band(self):
        right = VALUE_WIDTH + 16 if self.period != "today" else 0
        return QRectF(DAY_LABEL_WIDTH + 14, 0, self.width() - DAY_LABEL_WIDTH - 14 - right, 0)

    def _x(self, band, moment):
        hours = moment.hour + moment.minute / 60 + moment.second / 3600
        return band.left() + band.width() * (hours - self.start_hour) / (self.end_hour - self.start_hour)

    def paintEvent(self, event):
        if self.stats is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        band = self._band()
        m = METRICS[self.metric_key]

        for i, day in enumerate(self.days):
            top = i * self.ROW
            p.setFont(theme.ui_font(14))
            p.setPen(theme.color(theme.INK))
            p.drawText(QRectF(0, top, DAY_LABEL_WIDTH, self.ROW), Qt.AlignmentFlag.AlignVCenter, day_name(day, self.today))
            p.setPen(QPen(theme.color(theme.RULE), 1))
            p.drawLine(QPointF(band.left(), top + self.ROW - 6), QPointF(band.right(), top + self.ROW - 6))
            on_day = self.stats.sessions_on(day)
            if not on_day:
                p.setFont(theme.ui_font(13))
                p.setPen(theme.color(theme.GRAPHITE))
                p.drawText(QRectF(band.left(), top, 200, self.ROW), Qt.AlignmentFlag.AlignVCenter, "No sessions")
            for s in on_day:
                for start, end in s.segments:
                    x1, x2 = self._x(band, start), self._x(band, end)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(theme.color(theme.INK)))
                    p.drawRoundedRect(QRectF(x1, top + 8, max(2.0, x2 - x1), 18), 3, 3)
                for start, end in s.untracked:
                    x1, x2 = self._x(band, start), self._x(band, end)
                    p.setPen(QPen(theme.color(theme.GRAPHITE), 1.25, Qt.PenStyle.DashLine))
                    p.setBrush(QBrush(theme.color(theme.PAPER)))
                    p.drawRoundedRect(QRectF(x1, top + 8, max(3.0, x2 - x1), 18), 3, 3)
            if self.period != "today":
                value = combined_metric(on_day, self.metric_key)
                vx = self.width() - VALUE_WIDTH
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(theme.color(theme.PAPER_DEEP)))
                p.drawRect(QRectF(vx, top + 14, 56, 6))
                if value is not None:
                    p.setBrush(QBrush(theme.color(theme.COBALT)))
                    p.drawRect(QRectF(vx, top + 14, 56 * min(1.0, value / m["scale_max"]), 6))
                p.setFont(theme.number_font(13))
                p.setPen(theme.color(theme.INK if value is not None else theme.GRAPHITE))
                p.drawText(QRectF(vx + 64, top, VALUE_WIDTH - 64, self.ROW), Qt.AlignmentFlag.AlignVCenter,
                           format_metric(self.metric_key, value, with_unit=False) if value is not None else "no data")

        axis_top = len(self.days) * self.ROW
        p.setFont(theme.number_font(12))
        p.setPen(theme.color(theme.GRAPHITE))
        span = self.end_hour - self.start_hour
        step = 1 if span <= 8 else 2 if span <= 14 else 3
        for hour in range(self.start_hour, self.end_hour + 1, step):
            x = self._x(band, datetime.combine(self.today, dtime(hour % 24)) if hour < 24 else datetime.combine(self.today, dtime(23, 59, 59)))
            left = min(max(x - 30, band.left() - 30), band.right() - 60)
            p.drawText(QRectF(left, axis_top + 2, 60, 18), Qt.AlignmentFlag.AlignHCenter, f"{hour:02d}:00")
        if self.period != "today":
            p.drawText(QRectF(self.width() - VALUE_WIDTH, axis_top + 2, VALUE_WIDTH, 18),
                       Qt.AlignmentFlag.AlignLeft, f"{m['short']} per day")
            return

        # Today: per-minute values on the same time axis. Gaps stay gaps.
        chart = QRectF(band.left(), axis_top + self.AXIS + 8, band.width(), self.LINE_CHART - 16)
        p.setPen(QPen(theme.color(theme.INK), 1.5))
        p.drawLine(chart.bottomLeft(), chart.topLeft())
        p.drawLine(chart.bottomLeft(), chart.bottomRight())
        p.setFont(theme.number_font(12))
        p.setPen(theme.color(theme.GRAPHITE))
        top_label = f"{m['scale_max']}" + ("%" if self.metric_key == "closed" else f" {m['short']}")
        p.drawText(QRectF(0, chart.top() - 4, DAY_LABEL_WIDTH + 6, 16), Qt.AlignmentFlag.AlignRight, top_label)
        p.drawText(QRectF(0, chart.bottom() - 12, DAY_LABEL_WIDTH + 6, 16), Qt.AlignmentFlag.AlignRight, "0")
        path = QPainterPath()
        pen_down = False
        for moment, value in minute_series(self.sessions, self.metric_key):
            if value is None:
                pen_down = False
                continue
            x = self._x(band, moment) + band.width() / ((self.end_hour - self.start_hour) * 120)  # middle of the minute
            y = chart.bottom() - chart.height() * min(1.0, value / m["scale_max"])
            if pen_down:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(theme.color(theme.COBALT)))
                p.drawEllipse(QPointF(x, y), 1.8, 1.8)  # a lone minute stays visible
            pen_down = True
        p.setPen(QPen(theme.color(theme.COBALT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


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


class StatsPage(QScrollArea):
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
        outer.setContentsMargins(56, 40, 56, 72)
        outer.setSpacing(28)

        # Title
        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(_label("Your patterns", font=theme.ui_font(44, QFont.Weight.Bold)))
        self.tag = _label("", font=theme.ui_font(12, QFont.Weight.Bold))
        self.tag.setStyleSheet(f"color: {theme.GRAPHITE}; border: 1px dashed {theme.GRAPHITE}; border-radius: 6px; padding: 2px 8px;")
        heading.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
        heading.addStretch(1)
        title_col.addLayout(heading)
        title_col.addWidget(_label("A personal record of your study time and what the camera measured. "
                                   "Not a medical assessment.", "secondary", theme.ui_font(16), wrap=True))
        self.period_switch = Segmented([("today", "Today"), ("week", "This week"), ("month", "This month")],
                                       self.period, "Period")
        self.period_switch.changed.connect(self._set_period)
        title_col.addWidget(self.period_switch, 0, Qt.AlignmentFlag.AlignLeft)
        title_row.addLayout(title_col, 1)
        outer.addLayout(title_row)

        # New-user state
        self.empty = QWidget()
        empty_row = QHBoxLayout(self.empty)
        empty_row.setContentsMargins(0, 8, 0, 8)
        empty_row.setSpacing(40)
        empty_row.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        empty_text = QVBoxLayout()
        empty_text.addWidget(_label("Your patterns will appear as you complete sessions.",
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
        for i, (key, text) in enumerate((("study", "Study time"), ("sessions", "Sessions completed"),
                                         ("coverage", "Tracking coverage"))):
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(0 if i == 0 else 24, 18, 24, 18)
            col.addWidget(_label(text, "secondary", theme.ui_font(14)))
            value = _label("—", font=theme.number_font(36))
            self.summary_values[key] = value
            col.addWidget(value)
            if i:
                summary_row.addWidget(_vline())
            summary_row.addWidget(cell, 1)
        body.addWidget(_rule())
        body.addWidget(summary)
        body.addWidget(_rule(1, "hairline"))
        body.addSpacing(30)

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

        # Self-reports: honest placeholder until break check-ins exist in the app
        body.addWidget(_label("How you felt · What seems helpful", font=theme.ui_font(28, QFont.Weight.Bold)))
        body.addWidget(_rule())
        body.addWidget(_label("These sections appear once break check-ins are added to the app. "
                              "They will show your own before-and-after ratings — never a score.",
                              "secondary", theme.ui_font(15), wrap=True))
        body.addSpacing(30)

        # Recent sessions
        body.addWidget(_label("Recent sessions", font=theme.ui_font(28, QFont.Weight.Bold)))
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

    def refresh(self, completed, current=None, demo=False):
        self.sessions, self.current, self.demo = completed, current, demo
        self.render()

    def render(self):
        today = date.today()
        everything = self.sessions + ([self.current] if self.current else [])
        self.period_switch.set_current(self.period)
        self.metric_switch.set_current(self.metric_key)
        self.tag.setText("Demo data" if self.demo else "Kept until you quit")
        self.tag.setToolTip("" if self.demo else "Sessions are kept in memory only and forgotten when OcuSense quits.")
        has_any = bool(everything)
        self.empty.setVisible(not has_any)
        self.body.setVisible(has_any)
        self.empty_detail.setText("Press Start on the Study page. For now, sessions are kept only until "
                                  "you quit OcuSense — nothing is saved to disk.")
        if not has_any:
            return

        stats = period_stats(everything, self.period, today)
        completed = [s for s in stats.sessions if not s.in_progress]
        self.summary_values["study"].setText(format_duration(stats.study_seconds) if stats.study_seconds else "—")
        self.summary_values["sessions"].setText(str(len(completed)))
        self.summary_values["coverage"].setText(f"{stats.coverage * 100:.0f}%" if stats.coverage is not None else "—")

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


def _vline():
    line = QFrame()
    line.setProperty("role", "hairline")
    line.setFixedWidth(1)
    return line


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
