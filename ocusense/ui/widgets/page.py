"""A scrolling page with the shared title block, used by the Statistics, Settings and Account pages."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .. import theme
from .common import label, rule


class Page(QScrollArea):
    """Scrolls when the window is small. Add content to `self.body` (a QVBoxLayout)."""

    def __init__(self, eyebrow: str, title: str, intro: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Root")
        self.setWidget(content)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(48, 36, 48, 56)
        self.body.setSpacing(16)
        self.body.addWidget(label(eyebrow.upper(), "eyebrow", theme.ui_font(13, QFont.Weight.Bold)))
        heading = QHBoxLayout()
        heading.setSpacing(14)
        self.tag = tag_label("")
        self.tag.setVisible(False)
        if title:  # without one the page starts with its own content under the eyebrow (Time log)
            heading.addWidget(label(title, font=theme.ui_font(40, QFont.Weight.Bold)))
            heading.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
            heading.addStretch(1)
            self.body.addLayout(heading)
        if intro:
            self.body.addWidget(label(intro, "secondary", theme.ui_font(16), wrap=True))
        self.body.addSpacing(8)

    def fit_height(self) -> None:
        """Give the content the height its wrapped text needs at the current width.

        QScrollArea doesn't pass height-for-width to its content, so rows with
        wrapped labels would otherwise be squeezed to their bare minimum.
        """
        layout = self.widget().layout()
        if layout is not None and layout.hasHeightForWidth():
            self.widget().setMinimumHeight(layout.heightForWidth(self.viewport().width()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_height()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_height()

    def set_tag(self, text: str, tooltip: str = "") -> None:
        self.tag.setText(text)
        self.tag.setToolTip(tooltip)
        self.tag.setVisible(bool(text))

    def section(self, title: str, into: QVBoxLayout | None = None) -> None:
        """A section heading with an ink rule underneath."""
        target = into or self.body
        target.addSpacing(18)
        target.addWidget(label(title, font=theme.ui_font(24, QFont.Weight.Bold)))
        target.addWidget(rule())

    def finish(self) -> None:
        self.body.addStretch(1)


def tag_label(text: str):
    """A small dashed tag, e.g. "Not available yet" or "Kept until you quit"."""
    tag = label(text, font=theme.ui_font(12, QFont.Weight.Bold))
    tag.setStyleSheet(f"color: {theme.GRAPHITE}; border: 1px dashed {theme.GRAPHITE}; border-radius: 6px; padding: 2px 8px;")
    return tag


class _Paragraph(QLabel):
    """A wrapped label with a readable line length whose height is computed at that capped width."""

    def heightForWidth(self, width: int) -> int:
        return super().heightForWidth(min(width, self.maximumWidth()))


def paragraph(text: str, size: int = 15, secondary: bool = False, rich: bool = False):
    widget = _Paragraph(text)
    if secondary:
        widget.setProperty("role", "secondary")
    widget.setFont(theme.ui_font(size))
    widget.setWordWrap(True)
    if rich:
        widget.setTextFormat(Qt.TextFormat.RichText)
    widget.setMaximumWidth(760)
    return widget
