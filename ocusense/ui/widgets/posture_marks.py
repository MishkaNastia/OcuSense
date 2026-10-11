"""Marks for the posture cards, in the Miró style. Drawing only.

TiltMark: a laptop whose screen swung to a new angle (screen angle changed).
PostureMark: a figure sitting up straight next to a screen (calibrating posture).
"""

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


class PostureMark(QWidget):
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
        p.drawLine(QPointF(24, 22), QPointF(24, 44))  # a straight back…
        p.drawLine(QPointF(24, 44), QPointF(38, 44))  # …seated…
        p.drawLine(QPointF(38, 44), QPointF(38, 55))
        p.drawLine(QPointF(24, 30), QPointF(36, 34))  # …arm towards the desk
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawEllipse(QPointF(24, 13), 7, 7)  # cobalt head, level
        p.setPen(QPen(theme.color(theme.INK), 3))
        p.drawLine(QPointF(52, 14), QPointF(52, 36))  # the screen
        p.setPen(QPen(theme.color(theme.VERMILION), 2.5, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(32, 13), QPointF(49, 16))  # eye level to the screen
        draw_star(p, 8, 46, 4.5, theme.INK, 2)
        p.end()
