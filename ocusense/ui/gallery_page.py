"""Your gallery: the paintings you bought in the Art shop, like a small personal collection.

The heading is "<name>’s gallery": the account's username when signed in with one,
otherwise an optional local display name (kept on this computer in preferences.json,
no login needed), otherwise simply "Your gallery". Names are always shown as plain
text. Changing the name never touches the collection itself (ocusense/art/wallet.py).
Only paintings actually bought are shown — there are no demo pictures here.
"""

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ocusense.preferences import DISPLAY_NAME_MAX, clean_display_name

from . import theme
from .art_collection import ArtCollection
from .artwork_dialog import ArtworkDialog
from .widgets.art_frame import ArtCard, CardGrid, CoinBadge, paint_empty_wall
from .widgets.common import button, label
from .widgets.page import Page, paragraph
from .widgets.segmented import Segmented

SORTS = (("recent", "Recently acquired"), ("title", "Title"), ("artist", "Artist"))


def gallery_title(name: str) -> str:
    name = clean_display_name(name)
    return f"{name}’s gallery" if name else "Your gallery"


class _EmptyWall(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(170)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        paint_empty_wall(p, QRectF(self.rect()))
        p.end()


class GalleryPage(Page):
    visit_shop = Signal()

    def __init__(self, collection: ArtCollection, preferences, account_service=None, parent=None):
        super().__init__("Your collection", "Your gallery", "", parent)
        self.collection = collection
        self.preferences = preferences
        self.account_service = account_service
        self.sort = "recent"
        self.dialog: ArtworkDialog | None = None
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)  # a name is never interpreted as markup
        self.title_label.setWordWrap(True)

        top = QHBoxLayout()
        top.setSpacing(18)
        self.count = label("", font=theme.ui_font(17, QFont.Weight.DemiBold))
        top.addWidget(self.count)
        top.addStretch(1)
        self.badge = CoinBadge()
        self.badge.text.setFont(theme.ui_font(15, QFont.Weight.Bold))
        top.addWidget(self.badge)
        self.body.addLayout(top)

        # optional local name (only when there is no account name)
        self.name_row = QWidget()
        row = QHBoxLayout(self.name_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.name_toggle = button("Name your gallery…", "quiet")
        self.name_toggle.clicked.connect(self._edit_name)
        row.addWidget(self.name_toggle)
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Your name (optional, stays on this computer)")
        self.name_field.setAccessibleName("Gallery display name")
        self.name_field.setMaxLength(DISPLAY_NAME_MAX)
        self.name_field.setMaximumWidth(320)
        self.name_field.returnPressed.connect(self.save_name)
        self.name_save = button("Save", "secondary")
        self.name_save.clicked.connect(self.save_name)
        row.addWidget(self.name_field)
        row.addWidget(self.name_save)
        row.addStretch(1)
        self._editing_name = False
        self.body.addWidget(self.name_row)

        self.sort_row = QWidget()
        sort_line = QHBoxLayout(self.sort_row)
        sort_line.setContentsMargins(0, 0, 0, 0)
        sort_line.addWidget(label("Sort by", "secondary", theme.ui_font(14)))
        self.sort_switch = Segmented(SORTS, self.sort, "Sort paintings by")
        self.sort_switch.changed.connect(self.set_sort)
        sort_line.addWidget(self.sort_switch)
        sort_line.addStretch(1)
        self.body.addWidget(self.sort_row)

        self.empty = QWidget()
        empty = QVBoxLayout(self.empty)
        empty.setContentsMargins(0, 18, 0, 0)
        empty.setSpacing(10)
        empty.addWidget(_EmptyWall())
        heading = label("Your walls are still empty", font=theme.ui_font(22, QFont.Weight.Bold))
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(heading)
        hint = label("Paintings you buy in the Art shop will hang here.", "secondary", theme.ui_font(15), wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(hint)
        self.shop_button = button("Visit the Art shop", "primary")
        self.shop_button.clicked.connect(self.visit_shop.emit)
        empty.addWidget(self.shop_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.body.addWidget(self.empty)

        self.grid = CardGrid()
        self.body.addWidget(self.grid)
        self.note = paragraph("Your collection is saved on this computer only.", 12, secondary=True)
        self.body.addSpacing(8)
        self.body.addWidget(self.note)
        self.finish()
        self._shown: tuple = ()
        collection.changed.connect(self.refresh)
        if account_service is not None:
            account_service.changed.connect(lambda _account: self.refresh())
        self.refresh()

    # ------------------------------------------------------------ name
    def account_name(self) -> str:
        account = getattr(self.account_service, "account", None)
        return (account.username or "") if account is not None else ""

    def display_name(self) -> str:
        return self.account_name() or self.preferences.display_name

    def _edit_name(self) -> None:
        self._editing_name = True
        self.name_field.setText(self.preferences.display_name)
        self._show_name_row()
        self.name_field.setFocus()

    def save_name(self) -> None:
        self.preferences.display_name = clean_display_name(self.name_field.text())
        self.preferences.save()
        self._editing_name = False
        self.refresh()
        self.name_toggle.setFocus()

    def _show_name_row(self) -> None:
        local = not self.account_name()  # the account's name wins; then there's nothing to set here
        self.name_row.setVisible(local)
        self.name_toggle.setVisible(not self._editing_name)
        self.name_toggle.setText("Change gallery name…" if self.preferences.display_name else "Name your gallery…")
        self.name_field.setVisible(self._editing_name)
        self.name_save.setVisible(self._editing_name)

    # ------------------------------------------------------------ display
    def set_sort(self, key: str) -> None:
        self.sort = key
        self.sort_switch.set_current(key)
        self.refresh()

    def ordered(self) -> list[str]:
        owned = self.collection.owned()
        by_id = self.collection.by_id
        if self.sort == "title":
            return sorted(owned, key=lambda i: by_id[i].title.casefold())
        if self.sort == "artist":
            return sorted(owned, key=lambda i: (by_id[i].artist.casefold(), by_id[i].title.casefold()))
        return list(owned)[::-1]  # newest first (owned() is in purchase order)

    def refresh(self) -> None:
        c = self.collection
        self.title_label.setText(gallery_title(self.display_name()))
        self._show_name_row()
        ids = self.ordered()
        n = len(ids)
        self.count.setText(f"{n} painting{'s' if n != 1 else ''} in your collection" if n else "No paintings yet")
        self.badge.show_balance(c.balance(), c.demo, c.available)
        self.empty.setVisible(n == 0)
        self.sort_row.setVisible(n > 1)
        self.grid.setVisible(n > 0)
        if tuple(ids) != self._shown:
            self._shown = tuple(ids)
            owned = c.owned()
            cards = []
            for artwork_id in ids:
                artwork = c.by_id[artwork_id]
                card = ArtCard(artwork, _acquired_label(owned[artwork_id]))
                card.activated.connect(self.open_artwork)
                cards.append(card)
            self.grid.set_cards(cards)
        self.fit_height()

    def focus_artwork(self, artwork_id: str) -> None:
        """After "View in gallery": put keyboard focus on that painting."""
        for card in self.grid.cards:
            if card.artwork.id == artwork_id:
                card.setFocus(Qt.FocusReason.OtherFocusReason)
                self.ensureWidgetVisible(card, 40, 40)
                return

    def open_artwork(self, artwork_id: str) -> None:
        c = self.collection
        self.dialog = ArtworkDialog(c.by_id[artwork_id], "gallery", c.owned().get(artwork_id), parent=self)
        self.dialog.open()


def _acquired_label(iso: str) -> QLabel:
    try:
        when = datetime.fromisoformat(iso)
        text = f"Acquired {when.day} {when:%b %Y}"
    except ValueError:
        text = ""
    widget = label(text, "secondary", theme.ui_font(12))
    return widget
