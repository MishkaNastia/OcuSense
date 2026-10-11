"""Draws EyeGame (core/runner.py) with QPainter: her Pygame drawing, ported to Qt.

The 960 × 360 scene is scaled to the widget's width (height follows). Art comes from
ocusense/assets/eye_runner/ (her avatar, power-ups and obstacles).
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ocusense.core import runner as R

from .. import theme

# Her palette (EyeGame settings.py): cream paper, black ink, pure Miró colours.
BG = QColor(243, 236, 216)
INK = QColor(22, 20, 20)
RED = QColor(206, 38, 30)
BLUE = QColor(28, 62, 160)
YELLOW = QColor(244, 192, 28)
GREEN = QColor(34, 128, 76)
MIRO = (RED, BLUE, YELLOW, GREEN)
EMPTY = QColor(226, 216, 190)  # the empty part of meters
POOP = (QColor(92, 58, 28), QColor(122, 78, 38), QColor(106, 68, 32), QColor(140, 92, 48))
POOP_SHINE = QColor(176, 128, 80)
SUN_POS, SUN_R = (840, 150), 28
BACKGROUND_OPACITY = 70 / 255  # the sun and doodles stay faded: scenery, never obstacles


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


class RunnerCanvas(QWidget):
    def __init__(self, game: R.RunnerGame, parent=None):
        super().__init__(parent)
        self.game = game
        self.eyes = ""  # HUD line: "eyes open", "eyes closed", "keyboard", "camera: …"
        self.eyes_closed = False
        size = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        size.setHeightForWidth(True)
        self.setSizePolicy(size)
        self.setMinimumSize(480, 180)
        self.setAccessibleName("EyeGame: blink to jump")
        self._load_art()

    def _load_art(self) -> None:
        folder = R.ASSETS
        avatar = QPixmap(str(folder / "avatar.png"))
        w = R.AVATAR_WIDTH
        h = round(avatar.height() * w / avatar.width())
        avatar = avatar.scaled(w * 2, h * 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)  # 2× for sharp Retina drawing
        split = self.game.player.split * 2
        self.spark = avatar.copy(0, 0, w * 2, split)
        self.eye = avatar.copy(0, split, w * 2, h * 2 - split)
        self.powerups = {k: QPixmap(str(folder / f"{k}.png")) for k in R.POWERUPS}
        self.obstacles = {o.id: QPixmap(str(folder / "obstacles" / o.file)) for o in self.game.sizes.obstacles}

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(width * R.HEIGHT / R.WIDTH)

    def sizeHint(self) -> QSize:
        return QSize(R.WIDTH, R.HEIGHT)

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        k = min(self.width() / R.WIDTH, self.height() / R.HEIGHT)
        p.translate((self.width() - R.WIDTH * k) / 2, (self.height() - R.HEIGHT * k) / 2)
        p.scale(k, k)
        p.setClipRect(QRectF(0, 0, R.WIDTH, R.HEIGHT))
        p.fillRect(QRectF(0, 0, R.WIDTH, R.HEIGHT), BG)
        g = self.game
        self._scenery(p)
        self._ground(p, g.ground_offset)
        for o in g.obstacles:
            r = o.rect
            p.drawPixmap(QRectF(r.x, r.y, r.w, r.h), self.obstacles[o.item.id], QRectF(self.obstacles[o.item.id].rect()))
        for u in g.powerups:
            r = u.rect
            p.drawPixmap(QRectF(r.x, r.y, r.w, r.h), self.powerups[u.kind], QRectF(self.powerups[u.kind].rect()))
        self._player(p, g.player)
        self._hud(p)
        self._messages(p)
        p.setPen(_pen(INK, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(1.5, 1.5, R.WIDTH - 3, R.HEIGHT - 3), 10, 10)
        p.end()

    def _scenery(self, p: QPainter) -> None:
        p.save()
        p.setOpacity(BACKGROUND_OPACITY)
        sx, sy = SUN_POS
        p.setPen(_pen(INK, 2))
        p.drawLine(QPointF(sx - SUN_R + 4, sy + SUN_R - 4), QPointF(sx - 70, sy + 50))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        p.drawEllipse(QPointF(sx - 74, sy + 53), 5, 5)
        p.setPen(_pen(INK, 3))
        p.setBrush(RED)
        p.drawEllipse(QPointF(sx, sy), SUN_R, SUN_R)
        for d in self.game.doodles:
            self._doodle(p, d)
        p.restore()

    def _doodle(self, p: QPainter, d: R.Doodle) -> None:
        x, y, r = d.x, d.y, d.size
        colour = MIRO[d.color]
        if d.kind == "star":  # Miró's black asterisk-star
            p.setPen(_pen(INK, 3))
            for i in range(4):
                a = d.angle + i * math.pi / 4
                dx, dy = math.cos(a) * r, math.sin(a) * r
                p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))
        elif d.kind == "moon":  # a coloured disc with a paper-coloured bite
            p.setPen(_pen(INK, 2))
            p.setBrush(colour)
            p.drawEllipse(QPointF(x, y), r, r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(BG)
            p.drawEllipse(QPointF(x + r // 2, y - r // 3), r - 2, r - 2)
        elif d.kind == "dot":
            p.setPen(_pen(INK, 2))
            p.setBrush(colour)
            rr = r // 2 + 3
            p.drawEllipse(QPointF(x, y), rr, rr)
        else:
            if d.kind == "squiggle":
                points = [QPointF(x + i * 4, y + math.sin(d.angle * 3 + i * 0.8) * 5) for i in range(r)]
                p.setPen(_pen(INK, 3))
            else:  # spiral
                points = [QPointF(x + math.cos(t * 0.5 + d.angle) * t * 0.9, y + math.sin(t * 0.5 + d.angle) * t * 0.9)
                          for t in range(0, r + 6)]
                p.setPen(_pen(INK, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(points)

    @staticmethod
    def _ground(p: QPainter, offset: float) -> None:
        p.setPen(_pen(INK, 4))
        p.drawLine(QPointF(0, R.GROUND_Y), QPointF(R.WIDTH, R.GROUND_Y))
        p.setPen(_pen(INK, 2))
        for x in range(-int(offset), R.WIDTH, 40):
            p.drawLine(QPointF(x, R.GROUND_Y + 8), QPointF(x + 12, R.GROUND_Y + 8))
            p.drawLine(QPointF(x + 22, R.GROUND_Y + 16), QPointF(x + 26, R.GROUND_Y + 16))

    def _player(self, p: QPainter, pl: R.Player) -> None:
        eye = pl.eye_rect()
        cx = eye.x + eye.w / 2
        foot_y = R.GROUND_Y - int(pl.y) - 1
        swing = math.sin(pl.anim_t * 22) * 6 if (pl.on_ground and not pl.dead) else 4
        p.setPen(_pen(INK, 4))
        for side, phase in ((-9, 1), (9, -1)):  # legs
            fx = cx + side + swing * phase
            p.drawLine(QPointF(cx + side, eye.bottom - 4), QPointF(fx, foot_y))
            p.drawLine(QPointF(fx, foot_y), QPointF(fx + 6, foot_y))
        if (pl.dead and not pl.splat) or pl.blink_t > 0:  # squashed flat: the avatar blinks with you
            h = max(4, eye.h // 5)
            p.drawPixmap(QRectF(eye.x, eye.y + (eye.h - h) / 2, eye.w, h), self.eye, QRectF(self.eye.rect()))
        else:
            p.drawPixmap(QRectF(eye.x, eye.y, eye.w, eye.h), self.eye, QRectF(self.eye.rect()))
        spark_w, spark_h = self.spark.width() / 2, self.spark.height() / 2
        p.save()  # the asterisk sits above the eye, tilted when dead
        p.translate(eye.right - spark_w / 2, eye.y + 2 - spark_h / 2)
        if pl.dead:
            p.rotate(-30)
        p.drawPixmap(QRectF(-spark_w / 2, -spark_h / 2, spark_w, spark_h), self.spark, QRectF(self.spark.rect()))
        p.restore()
        if pl.splat:
            self._splat(p, pl, eye)

    @staticmethod
    def _splat(p: QPainter, pl: R.Player, eye: R.Rect) -> None:
        t = pl.splat_age
        cx, cy = eye.x + eye.w / 2, eye.y + eye.h / 2
        grow = min(1.0, t / 0.12) * (1 + 0.25 * max(0.0, 1 - t / 0.25))  # pops in with a little overshoot
        dark = POOP[0]
        for dx, length, w in pl.splat["drips"]:
            run = length * min(1.0, t / 1.2)  # drips run down over ~1 s
            x, y0 = cx + dx, cy + eye.h * 0.2
            p.setPen(_pen(dark, w))
            p.drawLine(QPointF(x, y0), QPointF(x, y0 + run))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dark)
            p.drawEllipse(QPointF(x, y0 + run), w / 2 + 1, w / 2 + 1)
        p.setPen(Qt.PenStyle.NoPen)
        for dx, dy, r, colour in pl.splat["blobs"]:
            rr = max(1.0, r * grow)
            pos = QPointF(cx + dx, cy + dy)
            p.setBrush(POOP[colour])
            p.drawEllipse(pos, rr, rr)
            p.setBrush(POOP_SHINE)
            p.drawEllipse(pos - QPointF(rr / 3, rr / 3), max(1.0, rr / 4), max(1.0, rr / 4))
        p.setBrush(dark)
        for vx, vy, r in pl.splat["flecks"]:
            x = cx + vx * t
            y = min(R.GROUND_Y - r, cy + vy * t + 0.5 * R.GRAVITY * t * t)  # fly, then land on the ground
            p.drawEllipse(QPointF(x, y), r, r)

    def _text(self, p: QPainter, text: str, font: QFont, colour: QColor, x: float, y: float,
              align=Qt.AlignmentFlag.AlignCenter) -> None:
        p.setFont(font)
        p.setPen(colour)
        width = 900
        if align & Qt.AlignmentFlag.AlignRight:
            rect = QRectF(x - width, y - 14, width, 28)
        elif align & Qt.AlignmentFlag.AlignLeft:
            rect = QRectF(x, y - 14, width, 28)
        else:
            rect = QRectF(x - width / 2, y - 20, width, 40)
        p.drawText(rect, int(align | Qt.AlignmentFlag.AlignVCenter), text)

    def _hud(self, p: QPainter) -> None:
        g = self.game
        mono = theme.number_font(20, QFont.Weight.Bold)
        small = theme.number_font(14)
        visible = g.flash_timer == 0 or int(g.flash_timer * 8) % 2 == 0
        score = f"HI {g.highscore:05d}  " + (f"{int(g.score):05d}" if visible else "     ")
        doubled = g.double_timer > 0
        self._text(p, score, mono, RED if doubled else INK, R.WIDTH - 20, 28, Qt.AlignmentFlag.AlignRight)
        if doubled and g.double_kind:  # power-up icon + "2x" + a shrinking bar
            icon = self.powerups[g.double_kind]
            w = icon.width() * 26 / icon.height()
            x0 = R.WIDTH - 190
            p.drawPixmap(QRectF(x0, 42, w, 26), icon, QRectF(icon.rect()))
            self._text(p, f"2x  {g.double_timer:3.1f}s", small, RED, x0 + 36, 54, Qt.AlignmentFlag.AlignLeft)
            p.fillRect(QRectF(x0 + 36, 66, 140, 6), EMPTY)
            p.fillRect(QRectF(x0 + 36, 66, 140 * g.double_timer / R.DOUBLE_POINTS_S, 6), YELLOW)
        bold = theme.number_font(20, QFont.Weight.Bold)
        for pop in g.popups:
            p.save()
            p.setOpacity(max(0.0, 1 - pop.age))
            self._text(p, pop.text, bold, RED, pop.x, pop.y)
            p.restore()
        if self.eyes:  # how you're playing: eyes (open / closed) or keyboard
            x, y = 16, 24
            if self.eyes in ("eyes open", "eyes closed"):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(YELLOW if self.eyes_closed else QColor(90, 190, 120))
                p.drawEllipse(QPointF(x + 6, y), 6, 6)
                x += 18
            self._text(p, self.eyes, small, INK, x, y, Qt.AlignmentFlag.AlignLeft)

    def _messages(self, p: QPainter) -> None:
        g = self.game
        cx = R.WIDTH / 2
        big = theme.number_font(34, QFont.Weight.Bold)
        mid = theme.number_font(20, QFont.Weight.Bold)
        small = theme.number_font(14)
        if g.state == "title":
            self._text(p, "EYEGAME", big, RED, cx, 110)
            self._text(p, "blink (or press Space) to start and to jump", mid, INK, cx, 155)
            self._text(p, "double blink (or double-tap Space) = extra jump in mid-air", small, INK, cx, 185)
            self._text(p, "Down = duck   P = pause", small, INK, cx, 205)
        elif g.state == "over":
            self._text(p, "G A M E   O V E R", big, RED, cx, 100)
            if g.killed_by:
                self._text(p, f"cause of death: {g.killed_by}", mid, INK, cx, 140)
            if g.new_record:
                self._text(p, "new high score!", small, RED, cx, 172 - 0)
            if g.over_timer > R.RESTART_DELAY_S:
                self._text(p, "blink or press Space to play again", small, INK, cx, 192 if g.new_record else 172)
        if g.paused:
            self._text(p, "PAUSED", big, RED, cx, 120)
