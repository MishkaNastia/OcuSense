"""A histogram drawn with QPainter in the OcuSense style. Display only: bins and counts come from core.

Regular bins are cobalt. Open-ended bins (below the first edge, at or above the
last) are drawn in ink with a hatch, so out-of-range values stay visible and are
clearly marked as such. Hovering a bar shows its range and value.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import theme


def _number(value: float) -> str:
    return f"{value:g}"


class Histogram(QWidget):
    LEFT, RIGHT, TOP, BOTTOM = 64, 16, 14, 52

    def __init__(self, parent=None):
        super().__init__(parent)
        self.counts: list[float] = []
        self.binning = None
        self.y_label = ""
        self.value_text = lambda v: _number(v)  # how a bar's value is described in the tooltip
        self.markers: list[tuple[float, str]] = []  # vertical lines in x units, e.g. detection thresholds
        self.message = ""
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setAccessibleName("Histogram")

    def set_data(self, counts, binning, y_label: str, value_text=None, markers=(), message: str = "") -> None:
        self.counts, self.binning, self.y_label = list(counts), binning, y_label
        self.value_text = value_text or (lambda v: _number(v))
        self.markers = list(markers)
        self.message = message
        if binning is not None and counts:
            parts = [f"{self._range_text(i)}: {self.value_text(c)}" for i, c in enumerate(self.counts) if c]
            self.setAccessibleDescription("; ".join(parts) or "No values")
        else:
            self.setAccessibleDescription(message)
        self.update()

    def clear(self, message: str) -> None:
        self.set_data([], None, "", message=message)

    # ----------------------------------------------------------- geometry
    def _plot(self) -> QRectF:
        return QRectF(self.LEFT, self.TOP, self.width() - self.LEFT - self.RIGHT, self.height() - self.TOP - self.BOTTOM)

    def _bar_rect(self, i: int, top: float) -> QRectF:
        plot = self._plot()
        n = len(self.counts)
        gap = 2.0 if n < 40 else 1.0
        width = plot.width() / n
        biggest = max(top, 1e-9)
        h = plot.height() * self.counts[i] / biggest
        return QRectF(plot.left() + i * width + gap / 2, plot.bottom() - h, width - gap, h)

    def _range_text(self, i: int) -> str:
        low, high = self.binning.labels()[i]
        unit = self.binning.unit
        sep = "" if unit == "%" else " "
        if low is None:
            return f"below {_number(high)}{sep}{unit}"
        if high is None:
            return f"{_number(low)}{sep}{unit} or more"
        return f"{_number(low)} to {_number(high)}{sep}{unit}"

    def _x_of(self, value: float) -> float:
        """x position of a value on the regular-bin scale (open-ended bins take one bin width each)."""
        plot = self._plot()
        b = self.binning
        width = plot.width() / len(self.counts)
        offset = 1 if b.underflow else 0
        return plot.left() + (offset + (value - b.low) / b.width) * width

    # ----------------------------------------------------------- painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        if not self.counts or self.binning is None:
            p.setPen(theme.color(theme.GRAPHITE))
            p.setFont(theme.ui_font(15))
            p.drawText(QRectF(self.rect()).adjusted(24, 0, -24, 0),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            p.end()
            return

        top = _nice_top(max(self.counts))
        small = theme.number_font(12)
        p.setFont(small)
        # y axis: 0, half and top — the half only when it is a whole number for whole-number counts
        whole = all(float(c).is_integer() for c in self.counts)
        fractions = (0, 0.5, 1) if not whole or (top / 2).is_integer() else (0, 1)
        for fraction in fractions:
            y = plot.bottom() - plot.height() * fraction
            p.setPen(QPen(theme.color(theme.RULE), 1))
            if fraction:
                p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(theme.color(theme.GRAPHITE))
            p.drawText(QRectF(0, y - 8, self.LEFT - 10, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _number(round(top * fraction, 2)))
        p.save()
        p.translate(12, plot.center().y())
        p.rotate(-90)
        p.setFont(theme.ui_font(12))
        p.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 16), Qt.AlignmentFlag.AlignCenter, self.y_label)
        p.restore()

        # bars
        labels = self.binning.labels()
        for i, count in enumerate(self.counts):
            if count <= 0:
                continue
            rect = self._bar_rect(i, top)
            open_ended = labels[i][0] is None or labels[i][1] is None
            p.setPen(QPen(theme.color(theme.INK), 1.2))
            p.setBrush(QBrush(theme.color(theme.INK if open_ended else theme.COBALT),
                              Qt.BrushStyle.BDiagPattern if open_ended else Qt.BrushStyle.SolidPattern))
            p.drawRect(rect)

        # x axis and labels
        p.setPen(QPen(theme.color(theme.INK), 1.5))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        p.setPen(theme.color(theme.GRAPHITE))
        for value in _ticks(self.binning):
            x = self._x_of(value)
            p.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 4))
            p.drawText(QRectF(x - 30, plot.bottom() + 6, 60, 16), Qt.AlignmentFlag.AlignHCenter, _number(value))
        width = plot.width() / len(self.counts)
        if self.binning.underflow:
            p.drawText(QRectF(plot.left() - 10, plot.bottom() + 6, width + 20, 16), Qt.AlignmentFlag.AlignHCenter,
                       f"<{_number(self.binning.low)}")
        if self.binning.overflow:
            p.drawText(QRectF(plot.right() - width - 10, plot.bottom() + 22, width + 20, 16),
                       Qt.AlignmentFlag.AlignHCenter, f"≥{_number(self.binning.high)}")
        p.setFont(theme.ui_font(12))
        p.drawText(QRectF(plot.left(), plot.bottom() + 30, plot.width(), 18), Qt.AlignmentFlag.AlignHCenter,
                   self.binning.unit if self.binning.unit != "%" else "personal openness, %")

        # markers (e.g. detection thresholds)
        for value, text in self.markers:
            x = self._x_of(value)
            p.setPen(QPen(theme.color(theme.GRAPHITE), 1.3, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setFont(theme.ui_font(11))
            p.drawText(QRectF(x + 4, plot.top(), 160, 14), Qt.AlignmentFlag.AlignLeft, text)
        p.end()

    def mouseMoveEvent(self, event) -> None:
        if not self.counts or self.binning is None:
            return
        plot = self._plot()
        x = event.position().x()
        if not plot.left() <= x <= plot.right():
            QToolTip.hideText()
            return
        i = min(len(self.counts) - 1, int((x - plot.left()) / (plot.width() / len(self.counts))))
        QToolTip.showText(event.globalPosition().toPoint(), f"{self._range_text(i)}\n{self.value_text(self.counts[i])}", self)


def _is_round(value: float) -> bool:
    """1, 2, 2.5 or 5 times a power of ten."""
    power = 10 ** math.floor(math.log10(value))
    return any(math.isclose(value / power, m) for m in (1, 2, 2.5, 5))


def _ticks(binning) -> list[float]:
    """Axis labels on bin edges at a round step, at most 8 steps (e.g. 0, 200, … 1000 ms)."""
    span = binning.high - binning.low
    for k in range(1, 1000):
        step = binning.width * k
        if span / step <= 8 and _is_round(step):
            count = math.floor(span / step + 1e-9)  # never a tick beyond the last edge
            return [round(binning.low + i * step, 10) for i in range(count + 1)]
    return [binning.low, binning.high]


def _nice_top(value: float) -> float:
    """The smallest round number (1, 2, 2.5 or 5 × a power of ten) at or above value, for the y axis."""
    if value <= 0:
        return 1
    return min(c for c in (s * 10 ** p for p in range(-2, 8) for s in (1, 2, 2.5, 5)) if c >= value)
