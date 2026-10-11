"""A little Miró-style painter in the sidebar, painting at an easel. Decorative only.

He is built from the same shapes as the rest of OcuSense: a round head with a
vermilion beret, a cobalt body, a golden palette. His arm reaches to the canvas and
dabs Miró marks onto it one by one — a cobalt circle, a vermilion dot, an ink star, a
golden crescent, a curved line — then the finished painting fades and he starts again.
Now and then he blinks.

The animation runs only while he is visible and animations are on; otherwise he is
drawn still, next to a finished painting. He takes no focus and carries no data.
"""

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import theme
from .artwork import draw_star

STEP = 1.5  # seconds per mark: reach (0–0.55), dab (0.55–0.8), return (0.8–1)
HOLD, FADE = 1.6, 0.7  # admire the finished painting, then fade it


def _c(hex_value: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_value)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class PainterCharacter(QWidget):
    # marks on the canvas: (kind, x, y as fractions of the canvas, paint colour)
    MARKS = (("circle", 0.34, 0.38, theme.COBALT), ("dot", 0.72, 0.28, theme.VERMILION),
             ("star", 0.68, 0.66, theme.INK), ("moon", 0.26, 0.74, theme.GOLDEN), ("curve", 0.5, 0.5, theme.INK))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(118)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("A little painter at an easel (decoration)")
        self.animate = True
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)

    def set_animations(self, on: bool) -> None:
        self.animate = on
        self._update_timer()
        self.update()

    def _update_timer(self) -> None:
        if self.animate and self.isVisible():
            self._timer.start(50)  # 20 frames per second is plenty for a small decoration
        else:
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    # ------------------------------------------------------------ timeline
    def _state(self) -> tuple[int, float, float, float]:
        """(marks finished, progress in the current mark 0–1, painting opacity, time) for this moment."""
        n = len(self.MARKS)
        if not self.animate:
            return n, 0.0, 1.0, 0.0
        t = self._clock.elapsed() / 1000.0
        cycle = n * STEP + HOLD + FADE
        local = t % cycle
        if local < n * STEP:
            return int(local // STEP), (local % STEP) / STEP, 1.0, t
        if local < n * STEP + HOLD:
            return n, 0.0, 1.0, t
        return n, 0.0, 1.0 - (local - n * STEP - HOLD) / FADE, t

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        scale = min(w / 200, h / 118)
        p.translate((w - 200 * scale) / 2, h - 118 * scale)
        p.scale(scale, scale)
        done, progress, opacity, t = self._state()
        canvas = QRectF(112, 14, 74, 58)

        # the easel
        p.setPen(_pen(_c(theme.INK), 2.4))
        p.drawLine(QPointF(122, 112), QPointF(140, 20))
        p.drawLine(QPointF(176, 112), QPointF(158, 20))
        p.drawLine(QPointF(149, 70), QPointF(149, 112))
        p.setBrush(QBrush(_c(theme.CARD)))
        p.drawRect(canvas)

        # the painting so far (the mark being dabbed grows in)
        current = self.MARKS[done] if done < len(self.MARKS) else None
        for mark in self.MARKS[:done]:
            self._mark(p, canvas, mark, 1.0, opacity)
        if current is not None and progress > 0.55:
            self._mark(p, canvas, current, _ease((progress - 0.55) / 0.25), 1.0)

        # the painter
        shoulder = QPointF(52, 66)
        rest = QPointF(74, 80)
        target = QPointF(canvas.x() + canvas.width() * (current[1] if current else 0.5) - 6,
                         canvas.y() + canvas.height() * (current[2] if current else 0.5) + 4)
        if current is None or progress <= 0:
            reach = 0.0
        elif progress < 0.55:
            reach = _ease(progress / 0.55)
        elif progress < 0.8:
            reach = 1.0
        else:
            reach = 1.0 - _ease((progress - 0.8) / 0.2)
        wiggle = math.sin(t * 22) * 2.2 if 0.55 <= progress < 0.8 else 0.0  # the little dab
        hand = QPointF(rest.x() + (target.x() - rest.x()) * reach + wiggle,
                       rest.y() + (target.y() - rest.y()) * reach - wiggle * 0.5)

        body = QPainterPath(QPointF(30, 112))  # a cobalt body, Miró-blocky
        body.cubicTo(28, 88, 38, 64, 52, 62)
        body.cubicTo(66, 64, 74, 88, 72, 112)
        body.closeSubpath()
        p.setPen(_pen(_c(theme.INK), 2.2))
        p.setBrush(QBrush(_c(theme.COBALT)))
        p.drawPath(body)

        p.setPen(_pen(_c(theme.INK), 2.4))  # the other arm, holding the palette
        p.drawLine(QPointF(40, 72), QPointF(22, 86))
        palette = QPainterPath(QPointF(8, 86))
        palette.cubicTo(8, 76, 30, 74, 34, 84)
        palette.cubicTo(36, 94, 12, 98, 8, 86)
        p.setBrush(QBrush(_c(theme.GOLDEN)))
        p.drawPath(palette)
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y), colour in zip(((14, 84), (21, 80), (27, 86)), (theme.VERMILION, theme.COBALT, theme.GREEN)):
            p.setBrush(QBrush(_c(colour)))
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)

        p.setPen(_pen(_c(theme.INK), 2.6))  # the painting arm and the brush
        elbow = QPointF((shoulder.x() + hand.x()) / 2, max(shoulder.y(), hand.y()) + 8)
        arm = QPainterPath(shoulder)
        arm.quadTo(elbow, hand)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(arm)
        direction = QPointF(target.x() - rest.x(), target.y() - rest.y())
        length = math.hypot(direction.x(), direction.y()) or 1
        tip = QPointF(hand.x() + direction.x() / length * 14, hand.y() + direction.y() / length * 14)
        p.setPen(_pen(_c(theme.INK), 2))
        p.drawLine(hand, tip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(current[3] if current else theme.VERMILION)))
        p.drawEllipse(tip, 3, 3)

        head = QPointF(52, 46)  # the head, with a vermilion beret
        p.setPen(_pen(_c(theme.INK), 2.2))
        p.setBrush(QBrush(_c(theme.CARD)))
        p.drawEllipse(head, 13, 13)
        beret = QPainterPath(QPointF(37, 38))
        beret.cubicTo(38, 26, 64, 24, 68, 36)
        beret.cubicTo(58, 34, 46, 34, 37, 38)
        p.setBrush(QBrush(_c(theme.VERMILION)))
        p.drawPath(beret)
        p.drawLine(QPointF(53, 27), QPointF(55, 22))  # the beret's stalk
        blinking = self.animate and (t % 4.3) < 0.15
        for x in (47, 57):
            if blinking:
                p.drawLine(QPointF(x - 2.2, 46), QPointF(x + 2.2, 46))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(theme.INK)))
                p.drawEllipse(QPointF(x, 46), 1.9, 1.9)
                p.setPen(_pen(_c(theme.INK), 2.2))
        p.setPen(_pen(_c(theme.INK), 1.8))
        smile = QPainterPath(QPointF(47, 52))
        smile.quadTo(52, 56, 57, 52)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(smile)
        draw_star(p, 86, 18, 5, theme.INK, 1.6)  # a little star above, like on the other pages
        p.end()

    def _mark(self, p: QPainter, canvas: QRectF, mark, grow: float, alpha: float) -> None:
        kind, fx, fy, colour = mark
        c = QPointF(canvas.x() + canvas.width() * fx, canvas.y() + canvas.height() * fy)
        if grow <= 0 or alpha <= 0:
            return
        p.save()
        p.setOpacity(alpha)
        p.translate(c)
        p.scale(grow, grow)
        if kind == "circle":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(colour)))
            p.drawEllipse(QPointF(0, 0), 10, 10)
        elif kind == "dot":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(colour)))
            p.drawEllipse(QPointF(0, 0), 4.5, 4.5)
        elif kind == "star":
            draw_star(p, 0, 0, 6, colour, 1.6)
        elif kind == "moon":
            moon = QPainterPath()
            moon.addEllipse(QPointF(0, 0), 7, 7)
            bite = QPainterPath()
            bite.addEllipse(QPointF(3.5, -2.5), 6, 6)
            p.setPen(_pen(_c(theme.INK), 1.2))
            p.setBrush(QBrush(_c(colour)))
            p.drawPath(moon.subtracted(bite))
        else:
            p.setPen(_pen(_c(colour), 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            curve = QPainterPath(QPointF(-28, 18))
            curve.cubicTo(-12, -16, 8, 22, 30, -14)
            p.drawPath(curve)
        p.restore()
