"""Posture score over time: one bar per minute (share of tracked time within all posture limits). Drawing only.

Values come from core/posture.PostureScore as core.models.PostureMinute; a minute without
enough tracked time has no bar, just a short tick, so a gap never looks like a score of 0.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import theme

LEFT = 40  # room for the 0 / 50 / 100 % labels
BOTTOM = 22  # room for the minute labels
TOP = 8


class PostureChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.minutes = []  # [PostureMinute]
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(130)
        self.setMouseTracking(True)
        self.setAccessibleName("Posture score per minute")

    def set_data(self, minutes) -> None:
        self.minutes = list(minutes)
        scored = [m for m in self.minutes if m.score is not None]
        self.setAccessibleDescription("; ".join(f"minute {m.index + 1}: {m.score * 100:.0f} %" for m in scored)
                                      or "no posture score yet")
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(LEFT, TOP, max(1.0, self.width() - LEFT - 4), self.height() - TOP - BOTTOM)

    def _slot(self, plot: QRectF) -> float:
        return plot.width() / max(len(self.minutes), 10)  # at least 10 slots, so a few minutes aren't huge bars

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        p.setFont(theme.ui_font(11))
        # recessive grid: 0, 50 and 100 %
        for share in (0.0, 0.5, 1.0):
            y = plot.bottom() - share * plot.height()
            p.setPen(QPen(theme.color(theme.RULE), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(theme.color(theme.GRAPHITE))
            p.drawText(QRectF(0, y - 8, LEFT - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{share * 100:.0f} %")
        if not self.minutes:
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "No posture score yet")
            return
        slot = self._slot(plot)
        bar = max(2.0, slot - 2)  # a 2 px gap between bars
        for i, minute in enumerate(self.minutes):
            x = plot.left() + i * slot + 1
            if minute.score is None:  # not enough tracked time: a short tick on the baseline, no bar
                p.setPen(QPen(theme.color(theme.GRAPHITE), 1))
                p.drawLine(QPointF(x + bar / 2, plot.bottom()), QPointF(x + bar / 2, plot.bottom() - 4))
                continue
            height = max(1.0, minute.score * plot.height())
            path = QPainterPath()
            radius = min(3.0, bar / 2, height / 2)
            path.addRoundedRect(QRectF(x, plot.bottom() - height, bar, height + radius), radius, radius)
            p.save()
            p.setClipRect(QRectF(x, plot.top(), bar, plot.height()))  # rounded top, square at the baseline
            p.fillPath(path, QBrush(theme.color(theme.COBALT)))
            p.restore()
        # minute labels: the first, the last and every 5th in between
        p.setPen(theme.color(theme.GRAPHITE))
        for i, minute in enumerate(self.minutes):
            number = minute.index + 1
            last = len(self.minutes) - 1
            if i in (0, last) or (number % 5 == 0 and last - i > 2):  # no every-5th label right beside the last
                x = plot.left() + i * slot + slot / 2
                p.drawText(QRectF(x - 20, plot.bottom() + 4, 40, 16), Qt.AlignmentFlag.AlignCenter, f"{number}")

    def mouseMoveEvent(self, event) -> None:
        plot = self._plot()
        i = int((event.position().x() - plot.left()) // self._slot(plot))
        if 0 <= i < len(self.minutes):
            m = self.minutes[i]
            text = (f"Minute {m.index + 1}: {m.score * 100:.0f} % within your limits "
                    f"({m.judged_seconds:.0f} s tracked)" if m.score is not None
                    else f"Minute {m.index + 1}: not enough tracked time ({m.judged_seconds:.0f} s)")
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()
