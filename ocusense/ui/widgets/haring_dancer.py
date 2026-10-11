"""Two dancing figures for the sidebar in the Keith Haring inspired theme. Decorative only.

Our own drawing in that spirit: chunky figures with thick black outlines, flat bright
colours, little motion lines around them and a pulsing heart. They swap between two
dance poses. Like the Miró painter, they move only while visible and animations are
on (the Animations switch and the system's reduce motion setting); otherwise they stand
still in one pose. They take no focus and carry no data.
"""

import math

from PySide6.QtCore import QElapsedTimer, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import theme

OUTLINE, FILL = 15.0, 9.0  # limb widths: black outline, colour inside
BEAT = 0.55  # seconds per dance step


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _mix(a: QPointF, b: QPointF, t: float) -> QPointF:
    return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)


# Two poses for one figure, on a 60 × 100 grid (feet at the bottom): head, neck, hips,
# then (elbow, hand) for each arm and (knee, foot) for each leg.
POSE_A = dict(head=QPointF(30, 18), neck=QPointF(30, 34), hips=QPointF(30, 62),
              arms=((QPointF(16, 30), QPointF(8, 12)), (QPointF(44, 40), QPointF(54, 48))),
              legs=((QPointF(20, 78), QPointF(12, 96)), (QPointF(42, 80), QPointF(48, 96))))
POSE_B = dict(head=QPointF(32, 14), neck=QPointF(31, 30), hips=QPointF(29, 58),
              arms=((QPointF(16, 40), QPointF(6, 46)), (QPointF(44, 26), QPointF(52, 8))),
              legs=((QPointF(18, 72), QPointF(22, 94)), (QPointF(42, 76), QPointF(54, 88))))


def _blend(t: float) -> dict:
    a, b = POSE_A, POSE_B
    return dict(head=_mix(a["head"], b["head"], t), neck=_mix(a["neck"], b["neck"], t),
                hips=_mix(a["hips"], b["hips"], t),
                arms=tuple((_mix(x[0], y[0], t), _mix(x[1], y[1], t)) for x, y in zip(a["arms"], b["arms"])),
                legs=tuple((_mix(x[0], y[0], t), _mix(x[1], y[1], t)) for x, y in zip(a["legs"], b["legs"])))


class HaringDancer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(118)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Two little figures dancing (decoration)")
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
            self._timer.start(50)
        else:
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _time(self) -> float:
        return self._clock.elapsed() / 1000.0 if self.animate else 0.0

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        scale = min(w / 200, h / 118)
        p.translate((w - 200 * scale) / 2, h - 118 * scale)
        p.scale(scale, scale)
        t = self._time()
        beat = (math.sin(t * math.pi / BEAT) + 1) / 2  # 0 → 1 → 0, one dance step each BEAT
        # The two dancers move in opposite steps, like a pair.
        self._figure(p, QPointF(18, 12), beat, theme.VERMILION, mirror=False)
        self._figure(p, QPointF(120, 12), 1 - beat, theme.COBALT, mirror=True)
        self._heart(p, QPointF(100, 30), 1 + 0.12 * beat)
        self._motion_lines(p, t)
        p.setPen(_pen(theme.INK, 3))
        p.drawLine(QPointF(4, 112), QPointF(196, 112))  # the floor they dance on
        p.end()

    def _figure(self, p: QPainter, origin: QPointF, step: float, colour: str, mirror: bool) -> None:
        pose = _blend(step)
        p.save()
        p.translate(origin)
        if mirror:
            p.translate(60, 0)
            p.scale(-1, 1)
        for width, ink in ((OUTLINE, theme.INK), (FILL, colour)):  # outline first, colour on top
            p.setPen(_pen(ink, width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for elbow, hand in pose["arms"]:
                limb = QPainterPath(pose["neck"])
                limb.quadTo(elbow, hand)
                p.drawPath(limb)
            for knee, foot in pose["legs"]:
                limb = QPainterPath(pose["hips"])
                limb.quadTo(knee, foot)
                p.drawPath(limb)
            p.drawLine(pose["neck"], pose["hips"])
        p.setPen(_pen(theme.INK, 3.5))
        p.setBrush(QColor(colour))
        p.drawEllipse(pose["head"], 10, 10)
        p.restore()

    def _heart(self, p: QPainter, centre: QPointF, size: float) -> None:
        p.save()
        p.translate(centre)
        p.scale(size, size)
        heart = QPainterPath(QPointF(0, 8))
        heart.cubicTo(-14, -2, -8, -14, 0, -6)
        heart.cubicTo(8, -14, 14, -2, 0, 8)
        p.setPen(_pen(theme.INK, 3))
        p.setBrush(QColor(theme.PINK))
        p.drawPath(heart)
        p.restore()

    def _motion_lines(self, p: QPainter, t: float) -> None:
        """Short strokes around the dancers that flick on and off with the beat."""
        p.setPen(_pen(theme.INK, 3))
        on = int(t / BEAT) % 2 == 0 or not self.animate
        lines = (((6, 30), (0, 26)), ((8, 44), (1, 46)), ((92, 14), (98, 8)), ((106, 14), (100, 8)),
                 ((192, 28), (199, 24)), ((190, 44), (198, 46)))
        for i, (a, b) in enumerate(lines):
            if on or i % 2:
                p.drawLine(QPointF(*a), QPointF(*b))
