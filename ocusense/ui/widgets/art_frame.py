"""Pieces shared by the Art shop and Your gallery: framed paintings, the coin badge, cards and a reflowing grid.

Paintings are shown like a small collection: an ivory mat inside a black ink frame.
Images are decoded at the size they're shown (and cached), so the shop stays light.
A missing image is drawn as a clearly marked placeholder, never as something it isn't.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ocusense.art.catalogue import Artwork

from .. import theme
from .common import label

MAT = "#FBF7EC"
_cache: dict[tuple[str, int], QPixmap] = {}


def load_pixmap(path: Path | None, longest_side: int) -> QPixmap | None:
    """The image scaled so its longest side is at most `longest_side` pixels, or None if it can't be read."""
    if path is None:
        return None
    key = (str(path), longest_side)
    if key not in _cache:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > longest_side:
            reader.setScaledSize(size.scaled(longest_side, longest_side, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return None
        _cache[key] = QPixmap.fromImage(image)
    return _cache[key]


def paint_coin(p: QPainter, center: QPointF, r: float) -> None:
    """A golden coin with an ink rim and a little Miró star."""
    p.save()
    p.setPen(QPen(QColor(theme.INK), max(1.2, r / 6)))
    p.setBrush(QColor(theme.GOLDEN))
    p.drawEllipse(center, r, r)
    p.setPen(QPen(QColor(theme.INK), max(1.0, r / 8)))
    d = r * 0.42
    for dx, dy in ((0, d), (d, 0), (d * 0.7, d * 0.7), (d * 0.7, -d * 0.7)):
        p.drawLine(center - QPointF(dx, dy), center + QPointF(dx, dy))
    p.restore()


class FramedPainting(QWidget):
    """A painting in an ink frame with an ivory mat, scaled into the widget."""

    def __init__(self, artwork: Artwork, size: QSize, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.setFixedSize(size)
        self.setAccessibleName(f"{artwork.title} by {artwork.artist}")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        draw_framed(p, QRectF(self.rect()), self.artwork, self.devicePixelRatioF())
        p.end()


def draw_framed(p: QPainter, area: QRectF, artwork: Artwork, ratio: float = 2.0) -> None:
    """Frame + mat + picture, centred in `area`, keeping the painting's proportions."""
    pixmap = load_pixmap(artwork.image_path, int(max(area.width(), area.height()) * max(1.0, ratio)))
    aspect = (pixmap.width() / pixmap.height()) if pixmap else 4 / 3
    frame, mat = 4.0, max(8.0, min(area.width(), area.height()) * 0.07)
    inner_w, inner_h = area.width() - 2 * (frame + mat), area.height() - 2 * (frame + mat)
    if inner_w / inner_h > aspect:
        inner_w = inner_h * aspect
    else:
        inner_h = inner_w / aspect
    outer = QRectF(0, 0, inner_w + 2 * (frame + mat), inner_h + 2 * (frame + mat))
    outer.moveCenter(area.center())
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 28))  # a soft shadow on the wall
    p.drawRoundedRect(outer.translated(2, 3), 3, 3)
    p.setPen(QPen(QColor(theme.INK), frame))
    p.setBrush(QColor(MAT))
    p.drawRoundedRect(outer.adjusted(frame / 2, frame / 2, -frame / 2, -frame / 2), 2, 2)
    picture = QRectF(0, 0, inner_w, inner_h)
    picture.moveCenter(outer.center())
    if pixmap is not None:
        p.drawPixmap(picture, pixmap, QRectF(pixmap.rect()))
        p.setPen(QPen(QColor(theme.INK), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(picture)
    else:  # clearly a placeholder, never a substitute painting
        p.setPen(QPen(QColor(theme.GRAPHITE), 1, Qt.PenStyle.DashLine))
        p.setBrush(QColor(theme.PAPER_DEEP))
        p.drawRect(picture)
        p.setPen(QColor(theme.GRAPHITE))
        font = theme.ui_font(max(10, int(inner_h / 12)), QFont.Weight.DemiBold)
        p.setFont(font)
        p.drawText(picture, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                   "Image unavailable\n(placeholder)")
    p.restore()


class CoinBadge(QWidget):
    """The balance: a coin and "240 coins", calm and readable. Shows a DEMO tag for the demo wallet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.coin = _CoinMark()
        row.addWidget(self.coin)
        self.text = label("", font=theme.ui_font(22, QFont.Weight.Bold))
        row.addWidget(self.text)
        self.demo = label("DEMO WALLET · test coins", font=theme.ui_font(12, QFont.Weight.Bold))
        self.demo.setStyleSheet(f"color: {theme.VERMILION}; border: 1.5px dashed {theme.VERMILION}; "
                                "border-radius: 6px; padding: 2px 8px;")
        self.demo.setVisible(False)
        row.addWidget(self.demo)
        row.addStretch(1)

    def show_balance(self, coins: int, demo: bool = False, available: bool = True) -> None:
        self.text.setText(f"{coins:,} coin{'s' if coins != 1 else ''}" if available else "Coins unavailable")
        self.demo.setVisible(demo)
        self.setAccessibleName(f"Balance: {coins} coins" + (" (demo wallet)" if demo else ""))


class _CoinMark(QWidget):
    def __init__(self, size: int = 30, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        paint_coin(p, QPointF(self.width() / 2, self.height() / 2), side / 2 - 2)
        p.end()


class ArtCard(QFrame):
    """A focusable card: framed painting, title, artist and an optional footer. Enter/Space/click opens it."""
    activated = Signal(str)  # artwork id

    WIDTH = 236

    def __init__(self, artwork: Artwork, footer: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.setObjectName("ArtCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAccessibleName(f"{artwork.title}, {artwork.artist}")
        self.setAccessibleDescription("Press Enter to see it larger.")
        self._pressed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        self.picture = FramedPainting(artwork, QSize(self.WIDTH - 28, 176))
        layout.addWidget(self.picture)
        layout.addSpacing(4)
        self.title = QLabel(artwork.title)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFont(theme.ui_font(15, QFont.Weight.Bold))
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        artist = QLabel(artwork.artist)
        artist.setTextFormat(Qt.TextFormat.PlainText)
        artist.setProperty("role", "secondary")
        artist.setFont(theme.ui_font(13))
        artist.setWordWrap(True)
        layout.addWidget(artist)
        if footer is not None:
            layout.addSpacing(4)
            layout.addWidget(footer)
        self._style()

    def _style(self) -> None:
        border = theme.COBALT if self.hasFocus() else theme.INK
        width = 3 if self.hasFocus() else 2
        background = theme.PAPER_DEEP if self._pressed else MAT
        self.setStyleSheet(f"QFrame#ArtCard {{ background: {background}; border: {width}px solid {border}; "
                           "border-radius: 14px; }")

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._style()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._style()

    def mousePressEvent(self, event) -> None:  # feedback on press, action on release (Apple's pattern)
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._style()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._style()
            if self.rect().contains(event.position().toPoint()):
                self.activated.emit(self.artwork.id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and not event.isAutoRepeat():
            self.activated.emit(self.artwork.id)
            return
        super().keyPressEvent(event)


class CardGrid(QWidget):
    """Cards in as many columns as fit; reflows when the window gets narrower or wider."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(18)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.cards: list[QWidget] = []
        self._columns = 0

    def set_cards(self, cards: list[QWidget]) -> None:
        for card in self.cards:
            self.grid.removeWidget(card)
            card.hide()  # gone at once, even before Qt gets round to deleting it
            card.deleteLater()
        self.cards = cards
        self._columns = 0
        self._place()

    def _columns_for(self, width: int) -> int:
        return max(1, (width + self.grid.horizontalSpacing()) // (ArtCard.WIDTH + self.grid.horizontalSpacing()))

    def _place(self) -> None:
        columns = self._columns_for(self.width() if self.width() > 0 else 800)
        if columns == self._columns:
            return
        self._columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns, Qt.AlignmentFlag.AlignTop)
        # Keep keyboard order the same as reading order (left to right, top to bottom).
        for first, second in zip(self.cards, self.cards[1:]):
            QWidget.setTabOrder(first, second)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if not self.cards:
            return 0
        columns = self._columns_for(width)
        rows = [self.cards[i:i + columns] for i in range(0, len(self.cards), columns)]
        spacing = self.grid.verticalSpacing()
        return sum(max(c.sizeHint().height() for c in row) for row in rows) + spacing * (len(rows) - 1)


def paint_empty_wall(p: QPainter, area: QRectF) -> None:
    """The empty gallery: a bare wall with an empty frame, a nail and a Miró sun peeking in."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = area.center().x(), area.center().y()
    p.setPen(QPen(QColor(theme.INK), 2))
    p.drawLine(QPointF(cx, cy - 46), QPointF(cx - 34, cy - 22))
    p.drawLine(QPointF(cx, cy - 46), QPointF(cx + 34, cy - 22))
    p.setBrush(QColor(theme.INK))
    p.drawEllipse(QPointF(cx, cy - 47), 2.5, 2.5)
    p.setPen(QPen(QColor(theme.INK), 4))
    p.setBrush(QColor(MAT))
    p.drawRoundedRect(QRectF(cx - 52, cy - 22, 104, 76), 3, 3)
    p.setPen(QPen(QColor(theme.RULE), 1.5, Qt.PenStyle.DashLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(cx - 38, cy - 9, 76, 50))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.VERMILION))
    p.drawEllipse(QPointF(cx + 78, cy - 34), 13, 13)
    p.setBrush(QColor(theme.COBALT))
    p.drawEllipse(QPointF(cx - 82, cy + 40), 7, 7)
    path = QPainterPath(QPointF(cx - 96, cy + 62))
    path.cubicTo(cx - 40, cy + 40, cx + 30, cy + 84, cx + 96, cy + 58)
    p.setPen(QPen(QColor(theme.INK), 1.6))
    p.drawPath(path)
    p.restore()
