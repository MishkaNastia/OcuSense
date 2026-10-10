"""The monitoring status (in the sidebar): a shape plus words, so it never relies on colour alone."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from .. import theme
from .common import label


class StatusGlyph(QWidget):
    KINDS = ("ready", "calibrating", "monitoring", "paused", "warning")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = "ready"
        self.setFixedSize(14, 14)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = QPen(theme.color(theme.INK), 1.6)
        if self.kind == "monitoring":  # filled cobalt circle
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.COBALT)))
            p.drawEllipse(QPointF(7, 7), 5.5, 5.5)
        elif self.kind == "calibrating":  # cobalt ring with a centre dot
            p.setPen(QPen(theme.color(theme.COBALT), 1.8))
            p.drawEllipse(QPointF(7, 7), 5, 5)
            p.setBrush(QBrush(theme.color(theme.COBALT)))
            p.drawEllipse(QPointF(7, 7), 1.8, 1.8)
        elif self.kind == "paused":  # empty ink ring
            p.setPen(ink)
            p.drawEllipse(QPointF(7, 7), 5, 5)
        elif self.kind == "warning":  # golden triangle with an ink outline
            path = QPainterPath(QPointF(7, 1.5))
            path.lineTo(13, 12.5)
            path.lineTo(1, 12.5)
            path.closeSubpath()
            p.setPen(ink)
            p.setBrush(QBrush(theme.color(theme.GOLDEN)))
            p.drawPath(path)
        else:  # ready: ink square
            p.setPen(ink)
            p.drawRect(QRectF(2, 2, 10, 10))


class StatusIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None, compact: bool = False):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.glyph = StatusGlyph()
        self.text = label("Ready", "secondary" if compact else None,
                          theme.ui_font(13 if compact else 15, QFont.Weight.Medium))
        layout.addWidget(self.glyph)
        layout.addWidget(self.text)
        layout.addStretch(1)

    def set(self, kind: str, text: str) -> None:
        self.glyph.set_kind(kind)
        self.text.setText(text)
        self.setAccessibleName("Status: " + text)
