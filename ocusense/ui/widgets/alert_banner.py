"""An in-app reminder card in the OcuSense alert style (same design as the website's alerts).

Paper card, ink border, a small Miró-style mark on the left, a title, one
muted line, and quiet buttons. Gentle and dismissible: it never takes focus.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .. import theme
from .artwork import draw_star
from .common import label

PAPER_LIGHT = theme.CARD


class TooCloseMark(QWidget):
    """The distance-reminder mark: an eye right up against the screen, tongue out."""

    def __init__(self, size: int = 60, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 60, self.height() / 60)
        ink = QPen(theme.color(theme.INK), 3)
        ink.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ink)
        p.drawLine(QPointF(53, 5), QPointF(53, 55))  # the screen
        eye = QPainterPath(QPointF(6, 27))  # a cobalt eye pressed close to it
        eye.cubicTo(14, 13, 40, 11, 50, 25)
        eye.cubicTo(40, 38, 16, 40, 6, 27)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawPath(eye)
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawEllipse(QPointF(30, 26), 6.5, 6.5)
        p.setBrush(QBrush(theme.color(theme.PAPER)))
        p.drawEllipse(QPointF(32.5, 23.5), 1.9, 1.9)
        tongue = QPainterPath(QPointF(30, 41))  # a vermilion tongue reaching for the screen
        tongue.cubicTo(36, 39, 44, 39, 48, 43)
        tongue.cubicTo(51, 47, 48, 52, 43, 51)
        tongue.cubicTo(38, 50, 33, 47, 30, 41)
        p.setPen(QPen(theme.color(theme.INK), 1.6))
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        p.drawPath(tongue)
        p.drawLine(QPointF(37, 44), QPointF(44, 46.5))
        draw_star(p, 9, 9, 4.5, theme.INK, 2)
        p.end()


class AlertBanner(QFrame):
    """Title + one line + buttons. Emits `action` with the button text."""
    action = Signal(str)

    def __init__(self, title: str, body: str, actions: tuple[str, ...], mark: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("AlertBanner")
        self.setStyleSheet(f"QFrame#AlertBanner {{ background: {PAPER_LIGHT}; border: 2px solid {theme.INK}; "
                           "border-radius: 14px; }")
        self.setAccessibleName(title)
        self.setAccessibleDescription(body)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(18)
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(4)
        self.title = label(title, font=theme.ui_font(19, QFont.Weight.Bold), wrap=True)
        self.body = label(body, "secondary", theme.ui_font(15), wrap=True)
        text.addWidget(self.title)
        text.addWidget(self.body)
        row.addLayout(text, 1)
        self.buttons = {}
        for i, name in enumerate(actions):
            button = QPushButton(name)
            button.setProperty("kind", "secondary" if i == 0 else "quiet")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(lambda _=False, n=name: self.action.emit(n))
            self.buttons[name] = button
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
