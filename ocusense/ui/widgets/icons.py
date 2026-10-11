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


def _pomodoro(p):  # a tomato: round body, stem and leaf
    p.drawEllipse(QPointF(10, 11.5), 6.8, 6.3)
    p.drawLine(QPointF(10, 5.2), QPointF(10, 2.5))
    leaf = QPainterPath(QPointF(10, 5.2))
    leaf.cubicTo(11.5, 3.2, 14.5, 3.4, 15.5, 4.8)
    leaf.cubicTo(13.8, 5.8, 11.8, 6.0, 10, 5.2)
    p.drawPath(leaf)


def _games(p):  # a game pad: rounded body, a plus and two buttons
    body = QPainterPath(QPointF(4, 8))
    body.cubicTo(1.5, 8, 1, 15.5, 3.5, 16)
    body.cubicTo(6, 16.5, 7, 13.5, 8.5, 13.5)
    body.lineTo(11.5, 13.5)
    body.cubicTo(13, 13.5, 14, 16.5, 16.5, 16)
    body.cubicTo(19, 15.5, 18.5, 8, 16, 8)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(6, 9.5), QPointF(6, 12.5))
    p.drawLine(QPointF(4.5, 11), QPointF(7.5, 11))
    p.drawEllipse(QPointF(13.5, 10), 0.9, 0.9)
    p.drawEllipse(QPointF(15.5, 12), 0.9, 0.9)


def _time_log(p):  # a stopwatch: dial, crown and one hand
    p.drawEllipse(QPointF(10, 11.5), 6.6, 6.6)
    p.drawLine(QPointF(10, 4.9), QPointF(10, 2.8))
    p.drawLine(QPointF(8, 2.5), QPointF(12, 2.5))
    p.drawLine(QPointF(15.2, 5.6), QPointF(16.4, 4.4))
    p.drawLine(QPointF(10, 11.5), QPointF(12.6, 8.9))


def _library(p):
    p.drawRect(QRectF(2, 3, 16, 14))
    p.drawEllipse(QPointF(7, 7), 1.5, 1.5)
    p.drawLine(QPointF(3, 15), QPointF(10, 9))
    p.drawLine(QPointF(10, 9), QPointF(17, 15))


ICONS = {"library": _library, "study": _study, "pomodoro": _pomodoro, "time_log": _time_log, "games": _games, "statistics": _statistics,
         "settings": _settings, "account": _account}


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
