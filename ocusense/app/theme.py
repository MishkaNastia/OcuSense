"""Colours, fonts and the Qt style sheet for the Miró-inspired look.

Colour meanings stay the same everywhere (see the style board):
cobalt = main action and the eye-openness line, vermilion = counted blink,
golden + triangle = tracking needs attention, ink = text and structure.
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase

PAPER = "#F6F0E1"
PAPER_DEEP = "#EDE3CC"
INK = "#1A1714"
GRAPHITE = "#5A5148"
RULE = "#CFC3A8"
COBALT = "#1F43B8"
COBALT_DARK = "#16328A"
COBALT_PRESSED = "#112870"
VERMILION = "#D2381F"
GOLDEN = "#F2B705"
GREEN = "#2E7A4D"


def color(hex_value):
    return QColor(hex_value)


def ui_font(pixel_size, weight=QFont.Weight.Normal):
    font = QFont()  # the system font (SF Pro on macOS)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def number_font(pixel_size, weight=QFont.Weight.Medium):
    """Monospaced, so the timer's digits don't jump around."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


STYLE_SHEET = f"""
QWidget#Root {{ background: {PAPER}; }}
QLabel {{ color: {INK}; background: transparent; }}
QLabel[role="secondary"] {{ color: {GRAPHITE}; }}
QLabel[role="eyebrow"] {{ color: {GRAPHITE}; font-weight: 700; }}
QFrame[role="rule"] {{ background: {INK}; border: none; }}
QFrame[role="hairline"] {{ background: {RULE}; border: none; }}

QPushButton {{
    min-height: 40px; padding: 0 18px; border-radius: 10px;
    font-size: 15px; font-weight: 700;
}}
QPushButton[kind="primary"] {{ background: {COBALT}; color: {PAPER}; border: 2px solid {COBALT}; }}
QPushButton[kind="primary"]:hover {{ background: {COBALT_DARK}; border-color: {COBALT_DARK}; }}
QPushButton[kind="primary"]:pressed {{ background: {COBALT_PRESSED}; }}
QPushButton[kind="primary"]:focus {{ border-color: {INK}; }}
QPushButton[kind="secondary"] {{ background: transparent; color: {INK}; border: 2px solid {INK}; }}
QPushButton[kind="secondary"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="secondary"]:focus {{ border-color: {COBALT}; }}
QPushButton[kind="quiet"] {{ background: transparent; color: {INK}; border: 2px solid transparent; font-weight: 500; }}
QPushButton[kind="quiet"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="quiet"]:focus {{ border-color: {COBALT}; }}

QToolTip {{ background: {PAPER}; color: {INK}; border: 1px solid {INK}; padding: 4px; }}
"""
