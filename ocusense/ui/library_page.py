"""Coin-funded painting collection and persistent decoration placement."""
from PySide6.QtCore import QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from ocusense.config import resource_path
from ocusense.core.library import MET_RIGHTS, PAINTINGS, SLOTS, SLOT_LABELS
from .widgets.page import Page
from .widgets.common import label
from . import theme


class PaintingArtwork(QWidget):
    """Draw the original pixels directly at the display's native resolution.

    Keeping the full source avoids enlarging a 1x thumbnail on Retina screens;
    Qt's painter also follows changes in screen density when moving the window.
    """
    def __init__(self, key, width, height):
        super().__init__()
        self.art_width = width
        self.setFixedHeight(height)
        self.setMinimumWidth(0)
        painting = PAINTINGS[key]
        self.source = QPixmap(str(resource_path('ocusense/assets/paintings/' + painting.filename)))
        self.framed = bool(painting.artist)
        self.setAccessibleName(painting.name)
        self.setToolTip(painting.name)

    def sizeHint(self):
        return QSize(self.art_width, self.height())

    def paintEvent(self, event):
        if self.source.isNull():
            return
        size = QSizeF(self.source.size()).scaled(
            QSizeF(min(self.art_width, self.width()), self.height()),
            Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width() - size.width()) / 2,
                        (self.height() - size.height()) / 2, size.width(), size.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.framed:  # museum photos have no frame: give them gold ones like the supplied pictures
            thick = max(5.0, min(target.width(), target.height()) * 0.075)
            target = target.adjusted(thick, thick, -thick, -thick)
            outer = target.adjusted(-thick, -thick, thick, thick)
            gold = QLinearGradient(outer.topLeft(), outer.bottomRight())
            gold.setColorAt(0.0, QColor("#F4D47C"))
            gold.setColorAt(0.5, QColor("#C9952B"))
            gold.setColorAt(1.0, QColor("#F0C75E"))
            painter.setPen(QPen(QColor("#7A5A12"), 1.2))
            painter.setBrush(QBrush(gold))
            painter.drawRect(outer)
            painter.setPen(QPen(QColor("#FFF1C2"), 1))
            painter.drawRect(outer.adjusted(thick * 0.35, thick * 0.35, -thick * 0.35, -thick * 0.35))
        painter.drawPixmap(target, self.source, QRectF(self.source.rect()))
        if self.framed:
            painter.setPen(QPen(QColor("#5C430C"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target)
        painter.end()


def artwork(key, width, height):
    return PaintingArtwork(key, width, height)


class PaintingWall(QWidget):
    """Two staggered decorations beneath sidebar navigation."""
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(8, 6, 8, 6)
        self.column.setSpacing(8)  # lift the lower painting 16 px clear of the painter
        self.refresh()

    def refresh(self):
        while self.column.count():
            item = self.column.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, slot in enumerate(SLOTS):
            key = self.store.garden.painting_slots.get(slot)
            if key:
                widget = artwork(key, 120, 105)
                widget.setFixedWidth(120)
                self.column.addWidget(widget, 0, Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight)
            else:
                placeholder = QWidget()
                placeholder.setFixedHeight(105)
                self.column.addWidget(placeholder)
        self.setVisible(bool(self.store.garden.painting_slots))


class LibraryPage(Page):
    changed = Signal()

    def __init__(self, store):
        super().__init__('A little art, earned by you', 'Gallery',
                         'Build your collection with garden coins: our own pictures plus famous paintings by many '
                         'different artists. Display up to two favourites beneath Statistics in the sidebar.')
        self.store = store
        self.balance = label('', font=theme.ui_font(20))
        self.body.addWidget(self.balance)
        self.body.addWidget(label('Earn coins by harvesting crops in Games → OcuSense Garden. Paintings are yours to keep.',
                                  'secondary', wrap=True))
        self.status = label('', wrap=True)
        self.status.setAccessibleName('Gallery status')
        self.body.addWidget(self.status)
        self.filter = QComboBox()
        self.filter.addItems(['All paintings', 'My collection'])
        self.filter.setAccessibleName('Filter paintings')
        self.filter.currentIndexChanged.connect(self.refresh)
        self.body.addWidget(self.filter)
        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        self.body.addLayout(self.grid)
        self.cards = {}
        for key, painting in PAINTINGS.items():
            card = QFrame()
            card.setStyleSheet('QFrame { background: #FFF9EC; border-radius: 12px; }')
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.addWidget(artwork(key, 210, 190))
            layout.addWidget(label(painting.name, font=theme.ui_font(16), wrap=True))
            if painting.artist:
                layout.addWidget(label(f'{painting.artist}, {painting.year}', 'secondary', theme.ui_font(13), wrap=True))
                source = QLabel(f'<a style="color:{theme.COBALT}" href="{painting.source_url}">At The Met</a> · public domain')
                source.setTextFormat(Qt.TextFormat.RichText)
                source.setOpenExternalLinks(True)
                source.setToolTip(MET_RIGHTS)
                source.setFont(theme.ui_font(12))
                layout.addWidget(source)
            buy = QPushButton()
            buy.clicked.connect(lambda checked=False, k=key: self.purchase(k))
            layout.addWidget(buy)
            placement = QComboBox()
            placement.setAccessibleName(f'Place {painting.name}')
            placement.addItem('Keep in collection', None)
            for slot, name in zip(SLOTS, SLOT_LABELS):
                placement.addItem(name, slot)
            placement.activated.connect(lambda index, k=key, c=placement: self.place(k, c.itemData(index)))
            layout.addWidget(placement)
            self.cards[key] = (card, buy, placement)
        self.body.addWidget(label('Choose an occupied position to replace its painting. The previous painting stays in your collection.',
                                  'secondary', wrap=True))
        self.finish()
        self.refresh()

    def refresh(self, *_):
        garden = self.store.garden
        self.balance.setText(f'{garden.coins:,} coins  ·  {len(garden.paintings)} / {len(PAINTINGS)} collected')
        while self.grid.count():
            self.grid.takeAt(0)
        visible = 0
        for key, (card, buy, placement) in self.cards.items():
            owned = key in garden.paintings
            price = PAINTINGS[key].price
            show = self.filter.currentIndex() == 0 or owned
            card.setVisible(show)
            if show:
                self.grid.addWidget(card, visible // 3, visible % 3)
                visible += 1
            buy.setText('Owned' if owned else (f'Buy · {price} coins' if garden.coins >= price else f'{price} coins · need {price - garden.coins} more'))
            buy.setEnabled(not owned and garden.coins >= price and not self.store.read_only)
            placement.setVisible(owned)
            placement.setEnabled(not self.store.read_only)
            slot = next((s for s, k in garden.painting_slots.items() if k == key), None)
            placement.setCurrentIndex(placement.findData(slot))
        if self.store.error:
            self.status.setText(self.store.error)
        elif not visible:
            self.status.setText('Your collection is waiting for its first painting. Harvest a crop to get started.')
        self.fit_height()

    def purchase(self, key):
        ok = self.store.change(lambda g: g.buy_painting(key))
        self.status.setText(f'{PAINTINGS[key].name} is yours! Choose where to display it below.' if ok
                            else self.store.error or 'Not enough coins, or this painting is already owned.')
        self.refresh()
        self.changed.emit()

    def place(self, key, slot):
        ok = self.store.change(lambda g: g.place_painting(key, slot))
        self.status.setText('Saved. Your painting is in place.' if ok and slot else
                            'Saved to your collection.' if ok else self.store.error or 'Could not place this painting.')
        self.refresh()
        self.changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
