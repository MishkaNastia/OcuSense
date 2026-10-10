"""Outline icons for the sidebar, drawn with QPainter on a 20 x 20 grid.

One stroke weight and round caps everywhere, so the set looks consistent.
Each function draws in the painter's current pen colour; nothing here carries data.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen

STROKE = 1.7


def _pen(color) -> QPen:
    pen = QPen(color, STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _study(p):  # an open eye, like the logo
    eye = QPainterPath(QPointF(2, 10.5))
    eye.cubicTo(5.5, 5, 14.5, 4.2, 18, 9.5)
    eye.cubicTo(14.5, 15, 6, 15.8, 3.2, 12.6)
    p.drawPath(eye)
    p.drawEllipse(QPointF(10.2, 10), 2.6, 2.6)


def _statistics(p):  # three bars on a baseline
    p.drawLine(QPointF(2.5, 17.5), QPointF(17.5, 17.5))
    for x, top in ((4.5, 10), (9, 5), (13.5, 8)):
        p.drawRoundedRect(QRectF(x, top, 2.6, 17.5 - top - 2.2), 0.8, 0.8)


def _settings(p):  # two sliders
    p.drawLine(QPointF(3, 6.5), QPointF(17, 6.5))
    p.drawLine(QPointF(3, 13.5), QPointF(17, 13.5))
    p.setBrush(p.background())
    p.drawEllipse(QPointF(7, 6.5), 2.2, 2.2)
    p.drawEllipse(QPointF(13, 13.5), 2.2, 2.2)


def _account(p):  # head and shoulders
    p.drawEllipse(QPointF(10, 7), 3.3, 3.3)
    shoulders = QPainterPath(QPointF(3.5, 17.5))
    shoulders.cubicTo(4.5, 12.5, 15.5, 12.5, 16.5, 17.5)
    p.drawPath(shoulders)


ICONS = {"study": _study, "statistics": _statistics, "settings": _settings, "account": _account}


def draw_icon(painter, name: str, rect: QRectF, color, background) -> None:
    """Draw icon `name` scaled into `rect`; `background` fills shapes that must hide lines behind them."""
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 20, rect.height() / 20)
    painter.setPen(_pen(color))
    painter.setBackground(background)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ICONS[name](painter)
    painter.restore()


def draw_chevron(painter, center: QPointF, expanded: bool, color) -> None:
    """A small disclosure chevron: pointing right when collapsed, down when expanded."""
    painter.save()
    painter.setPen(_pen(color))
    path = QPainterPath()
    if expanded:
        path.moveTo(center + QPointF(-3.5, -1.5))
        path.lineTo(center + QPointF(0, 2))
        path.lineTo(center + QPointF(3.5, -1.5))
    else:
        path.moveTo(center + QPointF(-1.5, -3.5))
        path.lineTo(center + QPointF(2, 0))
        path.lineTo(center + QPointF(-1.5, 3.5))
    painter.drawPath(path)
    painter.restore()
