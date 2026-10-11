"""The screen-tilt reminder mark: a laptop whose screen swung to a new angle, in the Miró style. Drawing only."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import theme
from .artwork import draw_star


class TiltMark(QWidget):
    def __init__(self, size: int = 60, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 60, self.height() / 60)
        ink = QPen(theme.color(theme.INK), 3)
        ink.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ink)
        p.drawLine(QPointF(8, 50), QPointF(44, 50))  # the base of the laptop
        p.setPen(QPen(theme.color(theme.GRAPHITE), 2, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(10, 49), QPointF(16, 13))  # where the screen was…
        p.setPen(ink)
        p.drawLine(QPointF(10, 49), QPointF(30, 16))  # …and where it is now
        arc = QPainterPath(QPointF(19, 22))  # the swing between them, in vermilion
        arc.quadTo(23, 16, 28, 21)
        p.setPen(QPen(theme.color(theme.VERMILION), 2.5))
        p.drawPath(arc)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawEllipse(QRectF(40, 28, 12, 12))  # a cobalt eye-dot watching
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawEllipse(QPointF(46, 34), 2.6, 2.6)
        draw_star(p, 50, 10, 4.5, theme.INK, 2)
        p.end()
