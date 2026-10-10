"""The "Inspect detection" timeline for an imported recording. Display only.

Shows a short, selectable stretch of time:
  cobalt line       left-eye personal openness (unclipped)
  graphite line     right-eye personal openness (unclipped)
  thin ink line     what the detector used: the mean of both eyes, each clipped to 0–100 %
  dashed lines      the recorded closing and reopening detection thresholds
  pale cobalt band  each completed closure event (closing → reopening)
  vermilion dot     each counted blink
  hatched band      no valid tracking (unreliable frames, no face, or a time gap)
"""

import bisect
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme

Y_LOW, Y_HIGH = -0.2, 1.2  # room to show values below 0 % and above 100 %


class DetectionTimeline(QWidget):
    LEFT, RIGHT, TOP, BOTTOM = 56, 16, 12, 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.events = []
        self.thresholds = (0.35, 0.65)
        self.start, self.span = 0.0, 30.0
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Detection timeline")

    def set_data(self, timeline, events, thresholds) -> None:
        self.timeline, self.events, self.thresholds = timeline, events, thresholds
        self.update()

    def set_range(self, start: float, span: float) -> None:
        self.start, self.span = start, span
        if self.timeline is not None:
            blinks = sum(1 for t in self.timeline.blinks if start <= t <= start + span)
            self.setAccessibleDescription(f"{start:.0f} to {start + span:.0f} seconds: {blinks} blinks counted")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(self.LEFT, self.TOP, self.width() - self.LEFT - self.RIGHT, self.height() - self.TOP - self.BOTTOM)
        t0, t1 = self.start, self.start + self.span

        def x_of(t):
            return plot.left() + plot.width() * (t - t0) / self.span

        def y_of(v):
            return plot.bottom() - plot.height() * (v - Y_LOW) / (Y_HIGH - Y_LOW)

        p.setFont(theme.number_font(11))
        for value in (0, 0.5, 1):
            y = y_of(value)
            p.setPen(QPen(theme.color(theme.RULE), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(theme.color(theme.GRAPHITE))
            p.drawText(QRectF(0, y - 8, self.LEFT - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{value:.0%}")
        if self.timeline is None:
            p.end()
            return
        p.setClipRect(plot.adjusted(0, -2, 0, 2))

        # gaps and closure events (backgrounds)
        hatch = QBrush(theme.color(theme.GRAPHITE), Qt.BrushStyle.BDiagPattern)
        for a, b in self.timeline.gaps:
            if b >= t0 and a <= t1:
                p.fillRect(QRectF(x_of(a), plot.top(), max(2, x_of(b) - x_of(a)), plot.height()), hatch)
        band = QColor(theme.COBALT)
        band.setAlphaF(0.16)
        for e in self.events:
            if e.end >= t0 and e.onset <= t1:
                p.fillRect(QRectF(x_of(e.onset), plot.top(), max(2, x_of(e.end) - x_of(e.onset)), plot.height()), band)

        # thresholds
        close, reopen = self.thresholds
        p.setPen(QPen(theme.color(theme.GRAPHITE), 1.2, Qt.PenStyle.DashLine))
        for value, text in ((close, f"closes {close:.0%}"), (reopen, f"reopens {reopen:.0%}")):
            p.drawLine(QPointF(plot.left(), y_of(value)), QPointF(plot.right(), y_of(value)))
            p.drawText(QRectF(plot.right() - 110, y_of(value) - 16, 106, 14), Qt.AlignmentFlag.AlignRight, text)

        # openness lines (only the frames in range)
        times = self.timeline.times
        lo = max(0, bisect.bisect_left(times, t0) - 1)
        hi = min(len(times), bisect.bisect_right(times, t1) + 1)
        for values, color, width in ((self.timeline.detector, theme.INK, 1.0),
                                     (self.timeline.right, theme.GRAPHITE, 1.6),
                                     (self.timeline.left, theme.COBALT, 2.0)):
            path = QPainterPath()
            drawing = False
            for i in range(lo, hi):
                v = values[i]
                if math.isnan(v):
                    drawing = False
                    continue
                point = QPointF(x_of(times[i]), y_of(max(Y_LOW, min(Y_HIGH, v))))
                if drawing:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    drawing = True
            p.setPen(QPen(theme.color(color), width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # counted blinks
        p.setPen(QPen(theme.color(theme.INK), 1.1))
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        for t in self.timeline.blinks:
            if t0 <= t <= t1:
                p.drawEllipse(QPointF(x_of(t), y_of(reopen)), 4.5, 4.5)
        p.setClipping(False)

        # time axis
        p.setPen(QPen(theme.color(theme.INK), 1.4))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        p.setPen(theme.color(theme.GRAPHITE))
        step = 1 if self.span <= 10 else 5 if self.span <= 30 else 10
        first = math.ceil(t0 / step) * step
        t = first
        while t <= t1:
            x = x_of(t)
            p.drawText(QRectF(x - 30, plot.bottom() + 6, 60, 14), Qt.AlignmentFlag.AlignHCenter, f"{t:.0f} s")
            t += step
        p.end()
