"""The vertical sidebar: logo, monitoring status, and navigation.

  Study
  Pomodoro (shows the time left while it runs)
  Time log (shows the running timer)
  Games
  Statistics ›  Current session / All time
  ...
  Settings
  Log in (or Account)

Navigation only: it emits `navigate(key)` and never touches the camera or the
session, so switching pages cannot stop or restart monitoring.

Keyboard: Tab reaches the items, ↑/↓ move between them, → / ← expand or
collapse Statistics, Return or Space opens the focused item.
"""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from . import theme
from .widgets.artwork import LogoMark
from .widgets.common import label, rule
from .widgets.icons import draw_chevron, draw_icon
from .widgets.painter_character import PainterCharacter
from .widgets.status_indicator import StatusIndicator

SIDEBAR_WIDTH = 224
HOVER = "#E3D7BB"  # one step deeper than the sidebar's paper
STATISTICS_PAGES = ("current", "all_time")


class SidebarItem(QAbstractButton):
    """One navigation row, painted directly so icon, text, selection and focus stay consistent."""

    def __init__(self, key: str, text: str, icon: str | None = None, level: int = 0,
                 expandable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.key, self.icon, self.level, self.expandable = key, icon, level, expandable
        self.selected = False
        self.ancestor = False  # a page inside this group is selected
        self.expanded = False
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # focus ring for keyboard users, not after every click
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._update_accessibility()

    TEXT_LEFT = 42  # icon column; child rows line up with their parent's text

    def _font(self) -> QFont:
        bold = self.selected or self.ancestor
        return theme.ui_font(15 if self.level == 0 else 14, QFont.Weight.Bold if bold else QFont.Weight.Medium)

    def _text_width(self, width: int) -> int:
        return width - self.TEXT_LEFT - (30 if self.expandable else 10)

    def sizeHint(self) -> QSize:
        width = SIDEBAR_WIDTH - 24
        base = 38 if self.level == 0 else 34
        bold = theme.ui_font(15 if self.level == 0 else 14, QFont.Weight.Bold)  # room for the selected weight
        text = QFontMetrics(bold).boundingRect(0, 0, self._text_width(width), 200,
                                               int(Qt.TextFlag.TextWordWrap), self.text())
        return QSize(width, max(base, text.height() + 14))  # long labels wrap instead of being cut off

    def set_text(self, text: str) -> None:
        self.setText(text)
        self._update_accessibility()

    def set_state(self, selected: bool, ancestor: bool = False, expanded: bool | None = None) -> None:
        self.selected, self.ancestor = selected, ancestor
        if expanded is not None:
            self.expanded = expanded
        self._update_accessibility()
        self.update()

    def _update_accessibility(self) -> None:
        self.setAccessibleName(self.text())
        parts = []
        if self.expandable:
            parts.append("expanded" if self.expanded else "collapsed")
        if self.selected:
            parts.append("current page")
        self.setAccessibleDescription(", ".join(parts))

    def keyPressEvent(self, event) -> None:
        bar = self.parent()
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and isinstance(bar, Sidebar):
            bar.move_focus(self, 1 if key == Qt.Key.Key_Down else -1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Left) and self.expandable and isinstance(bar, Sidebar):
            bar.set_expanded(key == Qt.Key.Key_Right)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        filled = self.selected or (self.ancestor and not self.expanded)
        enabled = self.isEnabled()
        if filled:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(theme.INK))
            p.drawRoundedRect(r, 8, 8)
        elif self.underMouse() and enabled:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(HOVER))
            p.drawRoundedRect(r, 8, 8)
        if self.hasFocus():
            p.setPen(QPen(theme.color(theme.COBALT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        ink = theme.color(theme.PAPER if filled else (theme.INK if enabled else theme.GRAPHITE))
        if not enabled:
            ink.setAlphaF(0.55)
        if self.icon:
            draw_icon(p, self.icon, QRectF(12, (r.height() - 20) / 2 + 1, 20, 20), ink,
                      theme.color(theme.INK if filled else theme.PAPER_DEEP))
        p.setFont(self._font())
        p.setPen(ink)
        p.drawText(QRectF(self.TEXT_LEFT, 0, self._text_width(self.width()), self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.text())
        if self.expandable:
            draw_chevron(p, QPointF(self.width() - 18, self.height() / 2), self.expanded, ink)
        p.end()


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.current = "study"
        self.expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 22, 12, 16)
        layout.setSpacing(2)

        brand = QWidget()
        row = QVBoxLayout(brand)
        row.setContentsMargins(8, 0, 0, 0)
        row.setSpacing(10)
        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        logo_row.addWidget(LogoMark(30))
        wordmark = label("OcuSense", font=theme.ui_font(21, QFont.Weight.Bold))
        wordmark.setStyleSheet("letter-spacing: -0.4px;")
        logo_row.addWidget(wordmark)
        logo_row.addStretch(1)
        row.addLayout(logo_row)
        self.status = StatusIndicator(compact=True)
        row.addWidget(self.status)
        layout.addWidget(brand)
        layout.addSpacing(22)

        self.items: dict[str, SidebarItem] = {}
        self._add(layout, SidebarItem("study", "Study", "study"))
        self._add(layout, SidebarItem("pomodoro", "Pomodoro", "pomodoro"))
        self._add(layout, SidebarItem("time_log", "Time log", "time_log"))
        self._add(layout, SidebarItem("games", "Games", "games"))
        self._add(layout, SidebarItem("library", "Gallery", "library"))
        self._add(layout, SidebarItem("statistics", "Statistics", "statistics", expandable=True))
        for key, text in (("current", "Current session"), ("all_time", "All time")):
            self._add(layout, SidebarItem(key, text, level=1))
        self.paintings_layout = QVBoxLayout()
        self.paintings_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.paintings_layout)
        layout.addStretch(1)
        self.painter = PainterCharacter()  # a little Miró painter at his easel, just above Settings
        layout.addWidget(self.painter)
        layout.addSpacing(6)
        layout.addWidget(rule(1, "hairline"))
        layout.addSpacing(8)
        self._add(layout, SidebarItem("settings", "Settings", "settings"))
        self._add(layout, SidebarItem("account", "Log in", "account"))
        self.set_expanded(False)
        self.set_current("study")

    def _add(self, layout: QVBoxLayout, item: SidebarItem) -> None:
        self.items[item.key] = item
        item.clicked.connect(lambda _=False, k=item.key: self._clicked(k))
        layout.addWidget(item)

    def _clicked(self, key: str) -> None:
        if key == "statistics":
            if self.expanded and self.current in STATISTICS_PAGES:
                self.set_expanded(False)  # collapse; the group stays highlighted
                return
            self.set_expanded(True)
            if self.current not in STATISTICS_PAGES:
                self.navigate.emit("current")
            return
        self.navigate.emit(key)

    # ------------------------------------------------------------- state
    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        for key in STATISTICS_PAGES:
            self.items[key].setVisible(expanded)
        self._paint_state()

    def set_current(self, key: str) -> None:
        """Highlight the page that is shown (called by the window, never by a click directly)."""
        self.current = key
        if key in STATISTICS_PAGES and not self.expanded:
            self.set_expanded(True)
        self._paint_state()

    def set_pomodoro_status(self, status: str) -> None:
        """e.g. "18:42" while a Pomodoro phase runs, "" when it isn't."""
        self.items["pomodoro"].set_text(f"Pomodoro · {status}" if status else "Pomodoro")

    def set_time_log_status(self, status: str) -> None:
        """e.g. "0:12:03" while a time-log timer runs, "" when none does."""
        self.items["time_log"].set_text(f"Time log · {status}" if status else "Time log")

    def set_account_label(self, text: str) -> None:
        self.items["account"].set_text(text)

    def set_only_enabled(self, keys: set[str] | None) -> None:
        """None enables everything; a set enables only those items (e.g. during calibration)."""
        for key, item in self.items.items():
            enabled = keys is None or key in keys or (key == "statistics" and keys & set(STATISTICS_PAGES))
            item.setEnabled(bool(enabled))
            item.setToolTip("" if enabled else "Available again when calibration is finished")

    def _paint_state(self) -> None:
        for key, item in self.items.items():
            if key == "statistics":
                item.set_state(False, ancestor=self.current in STATISTICS_PAGES, expanded=self.expanded)
            else:
                item.set_state(key == self.current)

    def move_focus(self, item: SidebarItem, step: int) -> None:
        order = [i for i in self.items.values() if not i.isHidden() and i.isEnabled()]
        if item in order:
            order[(order.index(item) + step) % len(order)].setFocus(Qt.FocusReason.TabFocusReason)
