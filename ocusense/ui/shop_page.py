"""Art shop: paintings from The Met's Open Access collection, bought with coins from games.

No real money, no checkout, no paid currency: coins are earned by finishing game
rounds (ocusense/art/rewards.py). The purchase flow is: choose a painting → confirm
(price and the balance afterwards) → the coins and the painting are saved together
→ "Added to your gallery", with a way to view it there.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QWidget

from ocusense.art import rewards

from . import theme
from .art_collection import ArtCollection
from .artwork_dialog import ArtworkDialog, ConfirmPurchase
from .widgets.art_frame import ArtCard, CardGrid, CoinBadge, _CoinMark
from .widgets.common import button, label
from .widgets.page import Page, paragraph


class _Footer(QWidget):
    """Price and Buy, or "In your gallery"."""

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        coin = _CoinMark(22)
        coin.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.coin = coin
        row.addWidget(coin)
        self.price = label(f"{artwork.price}", font=theme.number_font(15))
        row.addWidget(self.price)
        row.addStretch(1)
        self.owned = label("In your gallery", "secondary", theme.ui_font(13))
        row.addWidget(self.owned)
        self.buy = button("Buy", "secondary")
        self.buy.setAccessibleName(f"Buy {artwork.title} for {artwork.price} coins")
        row.addWidget(self.buy)

    def show_owned(self, owned: bool, available: bool) -> None:
        self.owned.setVisible(owned)
        self.buy.setVisible(not owned)
        self.buy.setEnabled(available)
        self.coin.setVisible(not owned)
        self.price.setVisible(not owned)


class ShopPage(Page):
    view_gallery = Signal(str)  # artwork id

    def __init__(self, collection: ArtCollection, parent=None):
        super().__init__("Art shop", "Art shop",
                         "Famous paintings from The Met’s Open Access collection. Coins come from finishing game "
                         "rounds — nothing here costs real money.", parent)
        self.collection = collection
        self.busy = False  # one purchase at a time: double clicks can't start a second one
        self.dialog: ArtworkDialog | None = None
        self.confirm = self._confirm  # replaceable in tests

        self.badge = CoinBadge()
        self.body.addWidget(self.badge)
        self.body.addWidget(paragraph(
            f"Earn coins by finishing a Blink Code challenge or an EyeGame run — up to "
            f"{rewards.DAILY_GAME_COIN_LIMIT} a day, so a few short breaks are enough.", 13, secondary=True))
        self.problem = paragraph("", 13)
        self.problem.setProperty("role", "error")
        self.body.addWidget(self.problem)

        self.notice = QWidget()  # "Added to your gallery  [View in gallery]"
        notice_row = QHBoxLayout(self.notice)
        notice_row.setContentsMargins(14, 10, 10, 10)
        self.notice.setObjectName("Notice")
        self.notice.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.notice.setStyleSheet(f"QWidget#Notice {{ background: #FBF7EC; border: 2px solid {theme.INK}; "
                                  "border-radius: 12px; }")
        self.notice_text = QLabel("")
        self.notice_text.setTextFormat(Qt.TextFormat.PlainText)
        self.notice_text.setWordWrap(True)
        self.notice_text.setFont(theme.ui_font(15))
        notice_row.addWidget(self.notice_text, 1)
        self.notice_view = button("View in gallery", "secondary")
        self.notice_view.clicked.connect(lambda: self.view_gallery.emit(self._last_bought or ""))
        notice_row.addWidget(self.notice_view)
        self.notice.setVisible(False)
        self._last_bought: str | None = None
        self.body.addWidget(self.notice)
        self.body.addSpacing(6)

        self.grid = CardGrid()
        self.footers: dict[str, _Footer] = {}
        cards = []
        for artwork in collection.catalogue:
            footer = _Footer(artwork)
            footer.buy.clicked.connect(lambda _=False, a=artwork.id: self.start_purchase(a))
            self.footers[artwork.id] = footer
            card = ArtCard(artwork, footer)
            card.activated.connect(self.open_artwork)
            cards.append(card)
        self.grid.set_cards(cards)
        self.body.addWidget(self.grid)
        if not collection.catalogue:
            self.body.addWidget(paragraph("No paintings to show right now.", 15))
        self.body.addSpacing(10)
        self.body.addWidget(paragraph(
            "All images: public-domain paintings released by The Metropolitan Museum of Art under CC0 "
            "(Open Access). Open a painting for its source and rights details.", 12, secondary=True))
        self.finish()
        collection.changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ display
    def refresh(self) -> None:
        c = self.collection
        self.badge.show_balance(c.balance(), c.demo, c.available)
        self.problem.setText(c.problem)
        self.problem.setVisible(bool(c.problem))
        for artwork_id, footer in self.footers.items():
            footer.show_owned(c.is_owned(artwork_id), c.available)
        self.fit_height()

    def _say(self, text: str, view_id: str | None = None) -> None:
        self.notice_text.setText(text)
        self._last_bought = view_id
        self.notice_view.setVisible(view_id is not None)
        self.notice.setVisible(bool(text))
        self.fit_height()

    # ------------------------------------------------------------ actions
    def open_artwork(self, artwork_id: str) -> None:
        c = self.collection
        artwork = c.by_id[artwork_id]
        self.dialog = ArtworkDialog(artwork, "shop", c.owned().get(artwork_id), c.balance(), c.available, self)
        self.dialog.buy_requested.connect(self._buy_from_dialog)
        self.dialog.view_in_gallery.connect(self._view_from_dialog)
        self.dialog.open()

    def _buy_from_dialog(self, artwork_id: str) -> None:
        if self.dialog is not None:
            self.dialog.accept()
        self.start_purchase(artwork_id)

    def _view_from_dialog(self, artwork_id: str) -> None:
        if self.dialog is not None:
            self.dialog.accept()
        self.view_gallery.emit(artwork_id)

    def _confirm(self, artwork, balance: int) -> bool:
        return ConfirmPurchase(artwork, balance, self).exec() == QDialog.DialogCode.Accepted

    def start_purchase(self, artwork_id: str) -> None:
        if self.busy:  # a second click while the first purchase is still open
            return
        c = self.collection
        artwork = c.by_id.get(artwork_id)
        if artwork is None:
            return
        if c.is_owned(artwork_id):
            self._say(f"“{artwork.title}” is already in your gallery.", artwork_id)
            return
        balance = c.balance()
        if balance < artwork.price:
            self._say(f"“{artwork.title}” needs {artwork.price - balance} more coins. Finishing a game round in "
                      "Games earns coins.")
            return
        self.busy = True
        footer = self.footers[artwork_id]
        footer.buy.setEnabled(False)
        try:
            if not self.confirm(artwork, balance):
                self._say("")  # cancelled: nothing changes
                return
            result = c.buy(artwork)
            if result.ok:
                self._say(f"{result.message}: “{artwork.title}”.", artwork_id)
            else:
                self._say(result.message, artwork_id if c.is_owned(artwork_id) else None)
        finally:
            self.busy = False
            self.refresh()
