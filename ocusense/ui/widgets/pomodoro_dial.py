"""The Pomodoro dial: a Miró-style composition that shows the time left, drawn with QPainter.

Each phase has its own picture and movement:
  focus        a cobalt sun; the remaining time is an ink ring that shrinks; a vermilion
               star travels along the ring (spinning, with a short tail)
  short break  a golden crescent moon rocking gently; small green dots rise and fade
  long break   the moon, plus ink stars that twinkle one after another
  change       the old picture fades into the new one; the star "pops" in with a little overshoot
  round done   the new round marker springs in (scale with overshoot)
  paused       everything stops and dims, with an ink pause sign

With animations off (setting or macOS "Reduce motion") the same pictures are drawn
without movement, and changes are instant. Display only: the timer lives in core/pomodoro.py.
"""

import math

from PySide6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme
from .artwork import draw_star

FOCUS, SHORT_BREAK, LONG_BREAK = "focus", "short_break", "long_break"
LABELS = {FOCUS: "FOCUS", SHORT_BREAK: "SHORT BREAK", LONG_BREAK: "LONG BREAK"}


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _color(hex_value: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_value)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class PomodoroDial(QWidget):
    FPS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(440)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Pomodoro timer")
        self.phase, self.previous_phase = FOCUS, None
        self.running = self.paused = False
        self.progress = 0.0  # 0 → 1 through the phase
        self.time_text = "25:00"
        self.rounds_total, self.rounds_done = 4, 0  # markers for the current cycle
        self.animate = True
        self._clock = QElapsedTimer()
        self._clock.start()
        self._fade = 1.0  # cross-fade between phases (1 = only the current picture)
        self._pop = 1.0  # star / marker overshoot
        self._marker_pop = 1.0
        self._fade_anim = self._animation(700, QEasingCurve.Type.OutCubic, "_fade")
        self._pop_anim = self._animation(650, QEasingCurve.Type.OutBack, "_pop")
        self._marker_anim = self._animation(550, QEasingCurve.Type.OutBack, "_marker_pop")
        self._frame = QTimer(self)  # repaints while something moves and the dial is visible
        self._frame.timeout.connect(self.update)

    def _animation(self, ms: int, curve, attribute: str) -> QVariantAnimation:
        anim = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve(curve))
        anim.valueChanged.connect(lambda v, a=attribute: (setattr(self, a, float(v)), self.update()))
        return anim

    # ------------------------------------------------------------ input
    def set_animations(self, on: bool) -> None:
        self.animate = on
        if not on:
            for anim in (self._fade_anim, self._pop_anim, self._marker_anim):
                anim.stop()
            self._fade = self._pop = self._marker_pop = 1.0
        self._update_frame_timer()
        self.update()

    def show_state(self, phase: str, running: bool, paused: bool, progress: float, time_text: str,
                   rounds_total: int, rounds_done: int) -> None:
        if phase != self.phase:
            self.previous_phase = self.phase
            self.phase = phase
            if self.animate:
                self._fade_anim.stop()
                self._fade_anim.start()
                self._pop_anim.stop()
                self._pop_anim.start()
        if rounds_done > self.rounds_done and self.animate:
            self._marker_anim.stop()
            self._marker_anim.start()
        self.running, self.paused = running, paused
        self.progress = max(0.0, min(1.0, progress))
        self.time_text = time_text
        self.rounds_total, self.rounds_done = rounds_total, rounds_done
        self.setAccessibleDescription(f"{LABELS[phase].capitalize()}, {time_text} left"
                                      + (", paused" if paused else ""))
        self._update_frame_timer()
        self.update()

    def _update_frame_timer(self) -> None:
        moving = self.animate and self.running and self.isVisible()
        if moving and not self._frame.isActive():
            self._frame.start(1000 // self.FPS)
        elif not moving and self._frame.isActive():
            self._frame.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_frame_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._update_frame_timer()  # no painting work while another page is shown

    # ------------------------------------------------------------ painting
    def _t(self) -> float:
        """Animation time in seconds; frozen while paused or without animations."""
        return self._clock.elapsed() / 1000.0 if (self.animate and self.running) else 0.0

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = size * 0.40
        t = self._t()
        if self.previous_phase is not None and self._fade < 1.0:
            self._paint_phase(p, self.previous_phase, center, radius, t, 1.0 - self._fade)
        self._paint_phase(p, self.phase, center, radius, t, self._fade)
        self._paint_ring(p, center, radius, t)
        self._paint_text(p, center, radius)
        self._paint_markers(p, center, radius)
        if self.paused:
            p.fillRect(self.rect(), _color(theme.PAPER, 0.45))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_color(theme.INK)))
            for dx in (-14, 6):
                p.drawRoundedRect(QRectF(center.x() + dx, center.y() + radius * 0.40, 8, 26), 2, 2)  # under the label
        p.end()

    def _paint_phase(self, p: QPainter, phase: str, c: QPointF, r: float, t: float, alpha: float) -> None:
        if alpha <= 0:
            return
        if phase == FOCUS:
            # A cobalt sun behind the time, and a small vermilion moon-dot on the horizon line
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_color(theme.COBALT, 0.92 * alpha)))
            p.drawEllipse(c, r * 0.56, r * 0.56)
            p.setPen(_pen(_color(theme.INK, alpha), 3))
            wave = QPainterPath(QPointF(c.x() - r * 1.35, c.y() + r * 0.95))
            wave.cubicTo(c.x() - r * 0.6, c.y() + r * 0.70, c.x() + r * 0.2, c.y() + r * 1.25,
                         c.x() + r * 1.35, c.y() + r * 0.92)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(wave)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_color(theme.GREEN, alpha)))
            p.drawEllipse(QPointF(c.x() - r * 1.18, c.y() - r * 0.95), 6, 6)
        else:
            # A golden crescent moon that rocks gently
            angle = 7 * math.sin(t * 2 * math.pi / 3.2) if self.animate else 0.0
            p.save()
            p.translate(c.x(), c.y() - r * 0.52)  # above the time, so the digits stay clear
            p.rotate(angle)
            moon = QPainterPath()
            moon.addEllipse(QPointF(0, 0), r * 0.27, r * 0.27)
            bite = QPainterPath()
            bite.addEllipse(QPointF(r * 0.12, -r * 0.08), r * 0.23, r * 0.23)
            p.setPen(QPen(_color(theme.INK, alpha), 2.5))
            p.setBrush(QBrush(_color(theme.GOLDEN, alpha)))
            p.drawPath(moon.subtracted(bite))
            p.restore()
            # Small green dots rising and fading (each on its own loop)
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(7):
                period = 4.0 + i * 0.37
                phase_t = ((t + i * 0.9) % period) / period if self.animate else (i + 1) / 8
                x = c.x() + (i - 3) * r * 0.32 + (6 * math.sin(t * 1.3 + i) if self.animate else 0)
                y = c.y() + r * 1.05 - phase_t * r * 0.9
                p.setBrush(QBrush(_color(theme.GREEN, alpha * (1 - phase_t) * 0.9)))
                p.drawEllipse(QPointF(x, y), 4.5, 4.5)
            if phase == LONG_BREAK:
                # Ink stars that twinkle one after another
                for i, (dx, dy, size) in enumerate(((-1.25, -0.85, 13), (1.2, -0.95, 10), (1.3, 0.55, 8),
                                                     (-1.35, 0.45, 9))):
                    pulse = 0.5 + 0.5 * math.sin(t * 2.2 + i * 1.6) if self.animate else 1.0
                    draw_star(p, c.x() + dx * r, c.y() + dy * r, size * (0.7 + 0.3 * pulse),
                              theme.INK, 2.0)

    def _paint_ring(self, p: QPainter, c: QPointF, r: float, t: float) -> None:
        box = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_color(theme.RULE), 10))
        p.drawEllipse(box)
        remaining = 1.0 - self.progress
        color = theme.INK if self.phase == FOCUS else theme.GREEN
        if remaining > 0:
            p.setPen(_pen(_color(color), 10))
            p.drawArc(box, 90 * 16, int(-remaining * 360 * 16))  # from 12 o'clock, clockwise
        # The vermilion star travels with the end of the ring, spinning, with a short tail
        angle = math.radians(90 - remaining * 360)
        tip = QPointF(c.x() + r * math.cos(angle), c.y() - r * math.sin(angle))
        if self.animate and self.running:
            for k in range(1, 6):
                a = math.radians(90 - (remaining + k * 0.006) * 360)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_color(theme.VERMILION, 0.35 - k * 0.06)))
                p.drawEllipse(QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a)), 5 - k * 0.6, 5 - k * 0.6)
        p.save()
        p.translate(tip)
        p.rotate(t * 90)  # a quarter turn per second while running
        p.scale(self._pop, self._pop)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_color(theme.VERMILION)))
        p.drawEllipse(QPointF(0, 0), 7, 7)
        draw_star(p, 0, 0, 13, theme.VERMILION, 2.4)
        p.restore()

    def _paint_text(self, p: QPainter, c: QPointF, r: float) -> None:
        on_sun = self.phase == FOCUS and self._fade > 0.5
        p.setPen(_color(theme.PAPER if on_sun else theme.INK))
        p.setFont(theme.number_font(int(r * 0.34), QFont.Weight.DemiBold))
        p.drawText(QRectF(c.x() - r, c.y() - r * 0.28, 2 * r, r * 0.42), Qt.AlignmentFlag.AlignCenter, self.time_text)
        p.setFont(theme.ui_font(13, QFont.Weight.Bold))
        p.setPen(_color(theme.PAPER if on_sun else theme.GRAPHITE))
        p.drawText(QRectF(c.x() - r, c.y() + r * 0.16, 2 * r, 20), Qt.AlignmentFlag.AlignCenter, LABELS[self.phase])

    def _paint_markers(self, p: QPainter, c: QPointF, r: float) -> None:
        n = self.rounds_total
        gap = 22
        x0 = c.x() - (n - 1) * gap / 2
        y = c.y() + r + 30
        for i in range(n):
            done = i < self.rounds_done
            scale = self._marker_pop if done and i == self.rounds_done - 1 else 1.0
            p.setPen(QPen(_color(theme.INK), 1.6))
            p.setBrush(QBrush(_color(theme.VERMILION if done else theme.PAPER)))
            p.drawEllipse(QPointF(x0 + i * gap, y), 6 * scale, 6 * scale)
