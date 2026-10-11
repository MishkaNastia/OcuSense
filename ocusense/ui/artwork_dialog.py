"""The larger view of a painting (Art shop and Your gallery) and the purchase confirmation.

The larger view shows the painting with its title, artist, the museum's date, medium,
where it is, and its source and rights statement (every image is public domain,
released by The Met under CC0). In the shop it carries the purchase action; in the
gallery it shows when you acquired it.
"""

import html
from datetime import datetime

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ocusense.art.catalogue import Artwork

from . import theme
from .widgets.art_frame import draw_framed
from .widgets.common import button, label


class _BigPainting(QWidget):
    def __init__(self, artwork: Artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.setMinimumSize(QSize(320, 300))
        self.setAccessibleName(f"{artwork.title} by {artwork.artist}")

    def sizeHint(self) -> QSize:
        return QSize(520, 460)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        draw_framed(p, QRectF(self.rect()).adjusted(4, 4, -6, -8), self.artwork, self.devicePixelRatioF())
        p.end()


def _plain(text: str, size: int = 14, secondary: bool = False, bold: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setFont(theme.ui_font(size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    if secondary:
        widget.setProperty("role", "secondary")
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def acquired_text(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    return f"In your gallery since {when.day} {when:%B %Y}"


class ArtworkDialog(QDialog):
    buy_requested = Signal(str)
    view_in_gallery = Signal(str)

    def __init__(self, artwork: Artwork, mode: str, owned_since: str | None = None, balance: int = 0,
                 can_buy: bool = True, parent=None):
        """mode = "shop" or "gallery"."""
        super().__init__(parent)
        self.artwork = artwork
        self.setWindowTitle(artwork.title)
        self.setObjectName("Root")
        self.setModal(True)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 24)
        outer.setSpacing(28)
        outer.addWidget(_BigPainting(artwork), 3)

        info = QVBoxLayout()
        info.setSpacing(8)
        info.addWidget(_plain(artwork.full_title, 22, bold=True))
        info.addWidget(_plain(artwork.artist + (f"  ·  {artwork.artist_bio}" if artwork.artist_bio else ""),
                              15, secondary=True))
        info.addSpacing(6)
        for name, value in (("Date", artwork.date), ("Medium", artwork.medium), ("Size", artwork.dimensions),
                            ("Collection", artwork.institution), ("Accession", artwork.accession_number),
                            ("Credit", artwork.credit_line)):
            if value:
                info.addWidget(_plain(f"{name}: {value}", 13))
        info.addSpacing(6)
        source = QLabel(
            f'<a href="{html.escape(artwork.source_url, quote=True)}">See it at the museum</a> · '
            f'<a href="{html.escape(artwork.license_url, quote=True)}">CC0 1.0</a>')
        source.setTextFormat(Qt.TextFormat.RichText)
        source.setOpenExternalLinks(True)
        source.setFont(theme.ui_font(13))
        source.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        info.addWidget(source)
        info.addWidget(_plain(artwork.rights + (f" Checked {artwork.rights_checked}." if artwork.rights_checked else ""),
                              12, secondary=True))
        info.addStretch(1)

        self.message = _plain("", 13)
        self.message.setVisible(False)
        info.addWidget(self.message)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.buy_button = None
        if mode == "shop" and owned_since is None:
            self.buy_button = button(f"Buy for {artwork.price} coins", "primary")
            self.buy_button.clicked.connect(lambda: self.buy_requested.emit(artwork.id))
            self.buy_button.setEnabled(can_buy)
            actions.addWidget(self.buy_button)
            if can_buy and balance < artwork.price:
                self._say(f"You have {balance} coins — {artwork.price - balance} more needed. "
                          "Finished game rounds in Games earn coins.")
        elif owned_since is not None:
            info.insertWidget(2, _plain(acquired_text(owned_since), 13, secondary=True))
            if mode == "shop":
                view = button("View in gallery", "secondary")
                view.clicked.connect(lambda: self.view_in_gallery.emit(artwork.id))
                actions.addWidget(view)
        close = button("Close", "quiet")
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        actions.addStretch(1)
        info.addLayout(actions)
        holder = QWidget()
        holder.setLayout(info)
        holder.setMinimumWidth(300)
        holder.setMaximumWidth(380)
        outer.addWidget(holder, 2)
        self.resize(940, 560)

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))


class ConfirmPurchase(QDialog):
    """“Buy … for 350 coins? Your balance afterwards: 50 coins.”  Cancel / Buy painting."""

    def __init__(self, artwork: Artwork, balance: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buy painting")
        self.setObjectName("Root")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)
        layout.addWidget(_plain(f"Buy “{artwork.title}”?", 20, bold=True))
        layout.addWidget(_plain(f"{artwork.artist}, {artwork.date}", 14, secondary=True))
        layout.addSpacing(6)
        layout.addWidget(_plain(f"Price: {artwork.price} coins", 15))
        layout.addWidget(_plain(f"Your balance afterwards: {balance - artwork.price} coins", 15))
        layout.addWidget(label("Coins are game rewards; nothing here costs real money.", "secondary",
                               theme.ui_font(12), wrap=True))
        layout.addSpacing(8)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = button("Cancel", "quiet")
        cancel.clicked.connect(self.reject)
        self.confirm = button("Buy painting", "primary")
        self.confirm.clicked.connect(self.accept)
        self.confirm.setDefault(True)
        actions.addWidget(cancel)
        actions.addWidget(self.confirm)
        layout.addLayout(actions)
        self.setMinimumWidth(420)
