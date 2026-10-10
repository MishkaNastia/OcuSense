"""The lighting-check card: "Your room looks quite dark" — same alert style as the other reminders.

Its Miró mark is a golden desk lamp with ink rays. "Got it" closes it; "Turn off"
switches the lighting check off (Settings › Reminders). It never takes focus.
"""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import theme
from .widgets.alert_banner import AlertBanner
from .widgets.artwork import draw_star

TITLE = "Your room looks quite dark"
BODY = "A lamp near your desk is easier on your eyes than a bright screen in a dark room."


class LampMark(QWidget):
    def __init__(self, size: int = 60, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 60, self.height() / 60)
        ink = QPen(theme.color(theme.INK), 2.4)
        ink.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ink)
        p.drawLine(QPointF(14, 54), QPointF(38, 54))  # base
        p.drawLine(QPointF(26, 54), QPointF(26, 34))  # arm
        p.drawLine(QPointF(26, 34), QPointF(36, 24))
        shade = QPainterPath(QPointF(28, 20))
        shade.lineTo(46, 12)
        shade.lineTo(50, 28)
        shade.closeSubpath()
        p.setBrush(QBrush(theme.color(theme.GOLDEN)))
        p.drawPath(shade)
        for x1, y1, x2, y2 in ((44, 33, 47, 40), (51, 31, 56, 36), (53, 25, 58, 26)):  # light rays
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawEllipse(QPointF(10, 14), 6, 6)  # the night outside
        draw_star(p, 22, 6, 4, theme.VERMILION, 1.8)
        p.end()


class LightingCard(QWidget):
    finished = Signal(str)  # "got it" or "turn off"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 16, 40, 0)
        self.banner = AlertBanner(TITLE, BODY, ("Got it", "Turn off"), LampMark())
        self.banner.action.connect(self._action)
        layout.addWidget(self.banner)
        self.setVisible(False)

    def _action(self, name: str) -> None:
        self.setVisible(False)
        self.finished.emit("turn off" if name == "Turn off" else "got it")
