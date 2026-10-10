"""The Blink Code play area, drawn with QPainter in the OcuSense (Miró) style. Display only.

  left    what to blink: a big letter and its code (Learn), the word tiles (Challenge),
          or the text you blinked (Free blink)
  centre  a live cobalt eye whose lids follow your blink, inside a ring that fills while
          the eyes are closed — golden before the dash line, vermilion after it
  below   your dots (vermilion) and dashes (ink) fly in from the eye; a thin fuse burns
          down until the letter is complete
  right   a golden combo sun that grows, with the score
  burst   right letter: Miró stars, moons and circles fly out · wrong letter: the code wobbles

With animations off (macOS "Reduce motion" or the Animations switch) the same picture
is drawn without bursts, wobbles or flights.
"""

import math
import random

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme
from .artwork import draw_star


def _c(hex_value: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_value)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


class MorseCanvas(QWidget):
    FPS = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(430)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Blink Code play area")
        self.mode = "learn"
        self.target, self.target_code = "E", "."
        self.word, self.position = "", 0
        self.typed = ""
        self.unlocked = "ET"
        self.code = ""  # symbols of the letter being blinked
        self.openness = 1.0  # 1 open … 0 closed (lids)
        self.closed_for: float | None = None  # seconds the eyes have been closed, while closed
        self.dash_seconds = 0.45
        self.fuse = 0.0  # 0 → 1 until the letter completes
        self.score, self.combo, self.streak, self.best = 0, 0, 0, 0
        self.time_left: float | None = None  # challenge: 1 → 0
        self.message = ""
        self.animate = True
        self._clock = QElapsedTimer()
        self._clock.start()
        self._particles: list[dict] = []
        self._flights: list[dict] = []  # symbols flying from the eye into the code line
        self._wobble_at: float | None = None
        self._frame = QTimer(self)
        self._frame.timeout.connect(self.update)
        self._rng = random.Random(7)

    # ------------------------------------------------------------ input from the game
    def now(self) -> float:
        return self._clock.elapsed() / 1000.0

    def set_animations(self, on: bool) -> None:
        self.animate = on
        if not on:
            self._particles.clear()
            self._flights.clear()
            self._wobble_at = None
        self.update()

    def add_symbol(self, mark: str) -> None:
        if self.animate:
            self._flights.append({"mark": mark, "t0": self.now(), "index": len(self.code) - 1})
        self.update()

    def celebrate(self, big: bool = False) -> None:
        if not self.animate:
            return
        cx, cy = self.width() * 0.5, self.height() * 0.40
        kinds = ("star", "moon", "dot", "circle")
        for _ in range(34 if big else 20):
            angle = self._rng.uniform(0, 2 * math.pi)
            speed = self._rng.uniform(140, 420 if big else 320)
            self._particles.append({
                "kind": self._rng.choice(kinds), "x": cx, "y": cy,
                "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed - 120,
                "spin": self._rng.uniform(-6, 6), "size": self._rng.uniform(5, 13), "t0": self.now(),
                "color": self._rng.choice((theme.COBALT, theme.VERMILION, theme.GOLDEN, theme.INK, theme.GREEN)),
            })

    def wobble(self) -> None:
        if self.animate:
            self._wobble_at = self.now()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._frame.start(1000 // self.FPS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._frame.stop()

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        now = self.now()
        self._paint_target(p, w, h)
        eye_c = QPointF(w * 0.5, h * 0.40)
        self._paint_ring(p, eye_c)
        self._paint_eye(p, eye_c)
        self._paint_code(p, w, h, now)
        self._paint_sun(p, w, h)
        if self.time_left is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(theme.RULE)))
            p.drawRoundedRect(QRectF(24, 10, w - 48, 8), 4, 4)
            p.setBrush(QBrush(_c(theme.VERMILION if self.time_left < 0.2 else theme.INK)))
            p.drawRoundedRect(QRectF(24, 10, (w - 48) * self.time_left, 8), 4, 4)
        self._paint_particles(p, now)
        if self.message:
            p.setPen(_c(theme.GRAPHITE))
            p.setFont(theme.ui_font(15, QFont.Weight.DemiBold))
            p.drawText(QRectF(0, h - 30, w, 24), Qt.AlignmentFlag.AlignCenter, self.message)
        p.end()

    def _paint_code_marks(self, p: QPainter, code: str, x: float, y: float, unit: float, color_dot, color_dash,
                          alpha: float = 1.0) -> float:
        """Dots as circles, dashes as rounded bars; returns the width used."""
        start = x
        for mark in code:
            if mark == ".":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(color_dot, alpha)))
                p.drawEllipse(QPointF(x + unit * 0.5, y), unit * 0.45, unit * 0.45)
                x += unit * 1.6
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(color_dash, alpha)))
                p.drawRoundedRect(QRectF(x, y - unit * 0.36, unit * 2.6, unit * 0.72), unit * 0.36, unit * 0.36)
                x += unit * 3.2
        return x - start

    def _paint_target(self, p: QPainter, w: float, h: float) -> None:
        left = QRectF(24, 34, w * 0.30, h - 80)
        p.setPen(_c(theme.GRAPHITE))
        p.setFont(theme.ui_font(12, QFont.Weight.Bold))
        title = {"learn": "BLINK THIS LETTER", "challenge": "SPELL THE WORD", "free": "BLINK TYPEWRITER"}[self.mode]
        p.drawText(QRectF(left.x(), left.y(), left.width(), 18), Qt.AlignmentFlag.AlignLeft, title)
        if self.mode == "learn":
            p.setPen(_c(theme.INK))
            p.setFont(theme.ui_font(130, QFont.Weight.Black))
            p.drawText(QRectF(left.x(), left.y() + 14, left.width(), 160), Qt.AlignmentFlag.AlignLeft, self.target)
            self._paint_code_marks(p, self.target_code, left.x() + 4, left.y() + 200, 16, theme.VERMILION, theme.INK)
            p.setPen(_c(theme.GRAPHITE))
            p.setFont(theme.ui_font(13))
            p.drawText(QRectF(left.x(), left.y() + 232, left.width(), 40),
                       Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, "Unlocked: " + " ".join(self.unlocked))
        elif self.mode == "challenge":
            size = min(52.0, left.width() / max(1, len(self.word)) - 6)
            for i, letter in enumerate(self.word):
                box = QRectF(left.x() + i * (size + 6), left.y() + 40, size, size * 1.15)
                done = i < self.position
                current = i == self.position
                p.setPen(_pen(_c(theme.COBALT if current else theme.INK), 3 if current else 2))
                p.setBrush(QBrush(_c(theme.INK if done else theme.PAPER)))
                p.drawRoundedRect(box, 8, 8)
                p.setPen(_c(theme.PAPER if done else theme.INK))
                p.setFont(theme.ui_font(int(size * 0.62), QFont.Weight.Black))
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, letter)
            if self.position < len(self.word):
                p.setPen(_c(theme.GRAPHITE))
                p.setFont(theme.ui_font(13))
                p.drawText(QRectF(left.x(), left.y() + 120, left.width(), 18), Qt.AlignmentFlag.AlignLeft,
                           f"Next: {self.word[self.position]}")
                self._paint_code_marks(p, self.target_code, left.x() + 4, left.y() + 154, 13, theme.VERMILION,
                                       theme.INK, alpha=0.55)
        else:
            p.setPen(_c(theme.INK))
            p.setFont(theme.number_font(34, QFont.Weight.DemiBold))
            text = self.typed[-60:] + ("▍" if int(self.now() * 2) % 2 == 0 else " ")
            p.drawText(QRectF(left.x(), left.y() + 26, left.width(), left.height() - 40),
                       Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWrapAnywhere, text)

    def _paint_ring(self, p: QPainter, c: QPointF) -> None:
        r = 96
        box = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(theme.RULE), 9))
        p.drawEllipse(box)
        full = self.dash_seconds * 2  # the ring is full at twice the dash line
        dash_angle = 0.5 * 360
        p.setPen(_pen(_c(theme.INK), 3))  # the dash line, at half the ring
        a = math.radians(90 - dash_angle)
        p.drawLine(QPointF(c.x() + (r - 14) * math.cos(a), c.y() - (r - 14) * math.sin(a)),
                   QPointF(c.x() + (r + 14) * math.cos(a), c.y() - (r + 14) * math.sin(a)))
        p.setFont(theme.ui_font(11, QFont.Weight.Bold))
        p.setPen(_c(theme.GRAPHITE))
        p.drawText(QRectF(c.x() - 40, c.y() + r + 14, 80, 16), Qt.AlignmentFlag.AlignCenter, "dash")
        p.drawText(QRectF(c.x() - 40, c.y() - r - 30, 80, 16), Qt.AlignmentFlag.AlignCenter, "dot")
        if self.closed_for is not None:
            fraction = min(1.0, self.closed_for / full)
            color = theme.VERMILION if self.closed_for >= self.dash_seconds else theme.GOLDEN
            p.setPen(_pen(_c(color), 9))
            p.drawArc(box, 90 * 16, int(-fraction * 360 * 16))

    def _paint_eye(self, p: QPainter, c: QPointF) -> None:
        open_ = max(0.06, min(1.0, self.openness))
        half_w, half_h = 62, 38 * open_
        eye = QPainterPath(QPointF(c.x() - half_w, c.y()))
        eye.cubicTo(c.x() - half_w * 0.5, c.y() - half_h * 1.5, c.x() + half_w * 0.5, c.y() - half_h * 1.5,
                    c.x() + half_w, c.y())
        eye.cubicTo(c.x() + half_w * 0.5, c.y() + half_h * 1.5, c.x() - half_w * 0.5, c.y() + half_h * 1.5,
                    c.x() - half_w, c.y())
        p.setPen(_pen(_c(theme.INK), 3))
        p.setBrush(QBrush(_c(theme.COBALT)))
        p.drawPath(eye)
        if open_ > 0.25:
            p.save()
            p.setClipPath(eye)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(theme.INK)))
            p.drawEllipse(c, 20, 20)
            p.setBrush(QBrush(_c(theme.PAPER)))
            p.drawEllipse(QPointF(c.x() + 7, c.y() - 7), 5.5, 5.5)
            p.restore()

    def _paint_code(self, p: QPainter, w: float, h: float, now: float) -> None:
        y = h * 0.40 + 150
        unit = 18
        total = sum(unit * (1.6 if m == "." else 3.2) for m in self.code)
        x = w * 0.5 - total / 2
        if self._wobble_at is not None:
            t = now - self._wobble_at
            if t > 0.5:
                self._wobble_at = None
            else:
                x += math.sin(t * 40) * 14 * (1 - t / 0.5)
        flying = {f["index"] for f in self._flights if now - f["t0"] < 0.28}
        cursor = x
        for i, mark in enumerate(self.code):
            if i not in flying:
                self._paint_code_marks(p, mark, cursor, y, unit, theme.VERMILION, theme.INK)
            cursor += unit * (1.6 if mark == "." else 3.2)
        for f in list(self._flights):  # from the eye down into place
            t = (now - f["t0"]) / 0.28
            if t >= 1 or f["index"] >= len(self.code):
                self._flights.remove(f)
                continue
            ease = 1 - (1 - t) ** 3
            target_x = x + sum(unit * (1.6 if m == "." else 3.2) for m in self.code[:f["index"]])
            fx = w * 0.5 + (target_x - w * 0.5) * ease
            fy = h * 0.40 + (y - h * 0.40) * ease
            self._paint_code_marks(p, f["mark"], fx, fy, unit * (0.6 + 0.4 * ease), theme.VERMILION, theme.INK)
        if self.fuse > 0 and self.code:  # the letter's fuse burns down
            length = 160 * (1 - self.fuse)
            p.setPen(_pen(_c(theme.GRAPHITE), 2))
            p.drawLine(QPointF(w * 0.5 - length / 2, y + 26), QPointF(w * 0.5 + length / 2, y + 26))
            if self.animate:
                draw_star(p, w * 0.5 + length / 2, y + 26, 5, theme.VERMILION, 1.6)

    def _paint_sun(self, p: QPainter, w: float, h: float) -> None:
        cx, cy = w - 110, h * 0.34
        radius = 34 + min(40, self.combo * 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(theme.GOLDEN)))
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.setPen(_c(theme.INK))
        p.setFont(theme.number_font(26, QFont.Weight.Bold))
        p.drawText(QRectF(cx - 80, cy - 18, 160, 30), Qt.AlignmentFlag.AlignCenter, str(self.score))
        p.setFont(theme.ui_font(12, QFont.Weight.Bold))
        label = {"learn": f"streak {self.streak} · best {self.best}",
                 "challenge": f"combo ×{min(5, 1 + self.combo // 3)} · best {self.best}",
                 "free": "letters blinked"}[self.mode]
        p.drawText(QRectF(cx - 90, cy + radius + 8, 180, 18), Qt.AlignmentFlag.AlignCenter, label)
        draw_star(p, cx + radius * 0.85, cy - radius * 0.85, 9, theme.INK, 2)

    def _paint_particles(self, p: QPainter, now: float) -> None:
        for part in list(self._particles):
            t = now - part["t0"]
            if t > 1.3:
                self._particles.remove(part)
                continue
            x = part["x"] + part["vx"] * t
            y = part["y"] + part["vy"] * t + 380 * t * t  # a little gravity
            alpha = 1 - t / 1.3
            size = part["size"]
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(part["spin"] * t))
            if part["kind"] == "star":
                draw_star(p, 0, 0, size, part["color"], 2.2)
            elif part["kind"] == "moon":
                moon = QPainterPath()
                moon.addEllipse(QPointF(0, 0), size, size)
                bite = QPainterPath()
                bite.addEllipse(QPointF(size * 0.45, -size * 0.3), size * 0.85, size * 0.85)
                p.setPen(_pen(_c(theme.INK, alpha), 1.4))
                p.setBrush(QBrush(_c(theme.GOLDEN, alpha)))
                p.drawPath(moon.subtracted(bite))
            else:
                p.setPen(_pen(_c(theme.INK, alpha), 1.2) if part["kind"] == "circle" else Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(part["color"], alpha)))
                p.drawEllipse(QPointF(0, 0), size * (0.5 if part["kind"] == "dot" else 1), size * (0.5 if part["kind"] == "dot" else 1))
            p.restore()
