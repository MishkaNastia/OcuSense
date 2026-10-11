"""No grey macOS title bar on any OcuSense window.

On a Mac every window (the main window, the session summary, the garden windows,
confirmations) gets a transparent title bar: the window's own paper runs right to
the top and the three window buttons sit on it, like in the Claude app. The title
text is hidden. Done with Qt's own window hints (Qt 6.9+: "expanded client area" =
the old MaximizeUsingFullscreenGeometryHint value, plus NoTitleBarBackgroundHint),
so no extra package is needed. Content that would sit under the buttons is moved
down by TITLE_BAR_HEIGHT. Elsewhere windows keep their normal frame. Installed
once for the whole app in ui/app.py (install()).
"""

import sys
import warnings

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget

TITLE_BAR_HEIGHT = 28  # the band the window buttons sit in
# Qt 6.9 renamed this value ExpandedClientAreaHint (PySide6 still lists the old name)
EXPANDED = getattr(Qt.WindowType, "ExpandedClientAreaHint", Qt.WindowType.MaximizeUsingFullscreenGeometryHint)
NO_BACKGROUND = getattr(Qt.WindowType, "NoTitleBarBackgroundHint", None)
SAFE_AREA = getattr(Qt.WidgetAttribute, "WA_ContentsMarginsRespectsSafeArea", None)


def applies(widget: QWidget) -> bool:
    return (sys.platform == "darwin" and NO_BACKGROUND is not None and isinstance(widget, (QMainWindow, QDialog))
            and widget.isWindow() and not widget.windowFlags() & Qt.WindowType.FramelessWindowHint)


def blend_title_bar(widget: QWidget) -> bool:
    """Give this (not yet shown) window a transparent title bar. Returns whether it was done."""
    if not applies(widget) or widget.property("ocusense_chrome"):
        return False
    widget.setProperty("ocusense_chrome", True)
    with warnings.catch_warnings():  # PySide6 flags the old name as deprecated; the value is the new hint
        warnings.simplefilter("ignore", DeprecationWarning)
        widget.setWindowFlag(EXPANDED, True)
    widget.setWindowFlag(NO_BACKGROUND, True)
    # No title text over the paper. A single space, because an empty title makes macOS show the
    # app's name instead. The Dock and the menu bar still say OcuSense.
    widget.setWindowTitle(" ")
    if SAFE_AREA is not None:  # we place the content ourselves, so Qt doesn't add a band of its own
        widget.setAttribute(SAFE_AREA, False)
        if isinstance(widget, QMainWindow) and widget.centralWidget() is not None:
            widget.centralWidget().setAttribute(SAFE_AREA, False)
    hook = getattr(widget, "title_bar_blended", None)
    if callable(hook):
        hook(TITLE_BAR_HEIGHT)  # the window moves its own content (MainWindow: the sidebar)
    elif widget.layout() is not None:
        m = widget.layout().contentsMargins()
        widget.layout().setContentsMargins(m.left(), m.top() + TITLE_BAR_HEIGHT, m.right(), m.bottom())
    return True


class _Chrome(QObject):
    def eventFilter(self, obj, event) -> bool:
        # Polish comes once, just before a window is first shown: window flags can still change then
        if event.type() == QEvent.Type.Polish and isinstance(obj, QWidget) and not obj.isVisible():
            blend_title_bar(obj)
        return False


_filter: _Chrome | None = None


def install(app: QApplication) -> None:
    global _filter
    if _filter is None:
        _filter = _Chrome(app)
        app.installEventFilter(_filter)
