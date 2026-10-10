"""A row of mutually exclusive choices (e.g. Today / This week / This month), optionally wrapped into rows."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QPushButton, QWidget


class Segmented(QWidget):
    """A row of mutually exclusive choices, e.g. Today / This week / This month."""
    changed = Signal(str)

    def __init__(self, options, current, label, parent=None, columns: int | None = None):
        """columns: wrap into rows of this many choices (keeps long choice lists inside narrow windows)."""
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)  # lets the style sheet draw the border
        self.setAccessibleName(label)
        layout = QGridLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for index, (key, text) in enumerate(options):
            button = QPushButton(text)
            button.setProperty("kind", "segment")
            button.setCheckable(True)
            button.setChecked(key == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            bold = QFont(button.font())
            bold.setPixelSize(14)
            bold.setWeight(QFont.Weight.Bold)
            button.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 34)  # room for the selected (bold) text
            button.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(button)
            self.buttons[key] = button
            row, column = divmod(index, columns) if columns else (0, index)
            layout.addWidget(button, row, column)

    def set_current(self, key):
        self.buttons[key].setChecked(True)

    def current(self):
        return next(key for key, button in self.buttons.items() if button.isChecked())
