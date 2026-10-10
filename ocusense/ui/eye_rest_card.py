"""The 20-20-20 eye-rest card: "Time for a 20-second eye rest" with a built-in countdown.

Same alert style as the other reminders (paper card, ink border, a Miró mark: an
eye looking along a dashed line to a far-away sun). "Start 20 s" counts down on the
card itself; "Not now" closes it. It never takes focus.
"""

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ocusense.core.eye_rest import REST_SECONDS

from . import theme
from .widgets.alert_banner import AlertBanner
from .widgets.artwork import draw_star

TITLE = "Time for a 20-second eye rest"
BODY = "Look at something about 6 metres (20 feet) away for 20 seconds."


class FarAwayMark(QWidget):
    """An eye looking along a dashed line to a small sun in the distance."""

    def __init__(self, size: int = 60, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 60, self.height() / 60)
        eye = QPainterPath(QPointF(3, 34))
        eye.cubicTo(8, 25, 22, 24, 28, 32)
        eye.cubicTo(22, 40, 9, 41, 3, 34)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawPath(eye)
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawEllipse(QPointF(16, 33), 4, 4)
        pen = QPen(theme.color(theme.INK), 2, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(30, 31), QPointF(48, 20))
        p.setPen(QPen(theme.color(theme.INK), 1.5))
        p.setBrush(QBrush(theme.color(theme.GOLDEN)))
        p.drawEllipse(QPointF(52, 17), 5.5, 5.5)
        p.setPen(QPen(theme.color(theme.INK), 2.4))
        p.drawLine(QPointF(30, 52), QPointF(58, 52))  # the horizon
        draw_star(p, 8, 10, 4.5, theme.VERMILION, 2)
        p.end()


class EyeRestCard(QWidget):
    finished = Signal(str)  # "done" or "not now"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 16, 40, 0)
        self.banner = AlertBanner(TITLE, BODY, ("Start 20 s", "Not now"), FarAwayMark())
        self.banner.action.connect(self._action)
        layout.addWidget(self.banner)
        self.left = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._count)
        self.setVisible(False)

    def show_card(self) -> None:
        self.timer.stop()
        self.banner.title.setText(TITLE)
        self.banner.body.setText(BODY)
        for button in self.banner.buttons.values():
            button.setVisible(True)
        self.setVisible(True)

    def _action(self, name: str) -> None:
        if name == "Start 20 s":
            self.left = int(REST_SECONDS)
            for button in self.banner.buttons.values():
                button.setVisible(False)
            self.banner.buttons["Not now"].setVisible(True)  # still possible to stop early
            self._show_count()
            self.timer.start(1000)
        else:
            self._close("not now")

    def _count(self) -> None:
        self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.banner.title.setText("Nice — your eyes had a rest.")
            self.banner.body.setText("Back to it. The next reminder comes after another stretch of screen time.")
            for button in self.banner.buttons.values():
                button.setVisible(False)
            QTimer.singleShot(2500, lambda: self._close("done"))
            return
        self._show_count()

    def _show_count(self) -> None:
        self.banner.title.setText(f"Keep looking far away… {self.left}")
        self.banner.body.setText("Something about 6 metres (20 feet) away — a window, a wall across the room.")

    def _close(self, how: str) -> None:
        self.timer.stop()
        self.setVisible(False)
        self.finished.emit(how)
