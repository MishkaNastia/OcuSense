"""Statistics timeline: one row per day, plus a per-minute line for Today. Drawing only.

Values arrive in internal units and are converted with core.stats.to_display.
"""

from datetime import date, datetime, time as dtime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ocusense.core.stats import METRICS, combined_metric, format_duration, format_metric, hour_range, minute_series, to_display

from .. import theme

DAY_LABEL_WIDTH = 104
VALUE_WIDTH = 132


def day_name(day: date, today: date) -> str:
    return "Today" if day == today else day.strftime("%a %-d %b")


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
                    p.drawRect(QRectF(vx, top + 14, 56 * min(1.0, to_display(self.metric_key, value) / m["scale_max"]), 6))
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
            y = chart.bottom() - chart.height() * min(1.0, to_display(self.metric_key, value) / m["scale_max"])
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
