"""Small helpers that create consistently styled basic widgets (styles live in theme.py)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QPushButton


def label(text: str = "", role: str | None = None, font: QFont | None = None, wrap: bool = False) -> QLabel:
    """A text label. role="secondary" or "eyebrow" picks a style from the style sheet."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if font:
        widget.setFont(font)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, kind: str) -> QPushButton:
    """kind = "primary", "secondary", "quiet", "nav", "segment" or "row" (see theme.py)."""
    widget = QPushButton(text)
    widget.setProperty("kind", kind)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def rule(thickness: int = 2, role: str = "rule") -> QFrame:
    """A horizontal line: "rule" = ink divider, "hairline" = fine light divider."""
    line = QFrame()
    line.setProperty("role", role)
    line.setFixedHeight(thickness)
    return line


def vline() -> QFrame:
    """A fine vertical divider."""
    line = QFrame()
    line.setProperty("role", "hairline")
    line.setFixedWidth(1)
    return line
