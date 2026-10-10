"""Vector artwork drawn with QPainter: the OcuSense logo (option B) and the
small Miró-style composition on the study screen. Nothing here carries data.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme


def _pen(hex_value, width):
    pen = QPen(theme.color(hex_value), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _star(painter, cx, cy, r, hex_value, width):
    painter.setPen(_pen(hex_value, width))
    d = r * 0.7
    painter.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
    painter.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    painter.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
    painter.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))


def paint_logo(painter, size, monochrome=None):
    """Logo B, the one-line eye, drawn in a size x size square (designed on a 64 grid)."""
    painter.save()
    painter.scale(size / 64, size / 64)
    ink = monochrome or theme.INK
    eye = QPainterPath(QPointF(6, 33))
    eye.cubicTo(16, 17, 46, 13, 58, 29)
    eye.cubicTo(47, 45, 20, 48, 10, 38)
    painter.setPen(_pen(ink, 6 if monochrome else 4.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(eye)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(theme.color(monochrome or theme.COBALT)))
    painter.drawEllipse(QPointF(33, 31), 8.5, 8.5)
    _star(painter, 53, 9, 6, monochrome or theme.VERMILION, 3.4 if monochrome else 2.6)
    painter.restore()


class LogoMark(QWidget):
    def __init__(self, size=36, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAccessibleName("OcuSense logo")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_logo(painter, self.width())


class Composition(QWidget):
    """One quiet composition placed in empty space: curve, circle, crescent, dot, star."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(256, 200)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(0.8, 0.8)  # drawn on a 320 x 250 grid

        curve = QPainterPath(QPointF(14, 232))
        curve.cubicTo(30, 130, 112, 64, 178, 112)
        curve.cubicTo(244, 160, 268, 196, 296, 74)
        p.setPen(_pen(theme.INK, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(curve)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawEllipse(QPointF(214, 66), 34, 34)

        outer = QPainterPath()
        outer.addEllipse(QRectF(36, 194, 44, 44))
        inner = QPainterPath()
        inner.addEllipse(QRectF(50, 184, 38, 38))
        p.setPen(_pen(theme.INK, 2))
        p.setBrush(QBrush(theme.color(theme.GOLDEN)))
        p.drawPath(outer.subtracted(inner))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        p.drawEllipse(QPointF(296, 74), 8, 8)
        p.setBrush(QBrush(theme.color(theme.GREEN)))
        p.drawEllipse(QPointF(252, 214), 5, 5)

        _star(p, 104, 35, 13, theme.INK, 2.2)
