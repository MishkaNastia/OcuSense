"""Colours, fonts and the Qt style sheet. Two looks, chosen in Settings › Appearance:

    miro     the original: warm paper, black ink, restrained cobalt, vermilion and gold
    haring   inspired by Keith Haring: white page, bold saturated colours, thicker black
             lines and a dancing figure in the sidebar (our own drawing, no copied artwork)

Colour meanings stay the same in both (see the style board): cobalt = main action and
the eye-openness line, vermilion = counted blink, golden + triangle = tracking needs
attention, ink = text and structure. The theme is read from preferences.json when this
module is first imported, and apply() switches it while OcuSense runs (no restart).
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase

THEMES = {
    "miro": dict(
        PAPER="#F6F0E1", PAPER_DEEP="#EDE3CC", PAPER_HOVER="#EFE7D4", CARD="#FBF7EC",
        INK="#1A1714", GRAPHITE="#5A5148", RULE="#CFC3A8",
        COBALT="#1F43B8", COBALT_DARK="#16328A", COBALT_PRESSED="#112870",
        VERMILION="#D2381F", GOLDEN="#F2B705", GREEN="#2E7A4D", PINK="#E07AA0",
        LINE=2,
    ),
    "haring": dict(
        PAPER="#FFFDF7", PAPER_DEEP="#FFE135", PAPER_HOVER="#FFF3A6", CARD="#FFFFFF",
        INK="#000000", GRAPHITE="#383838", RULE="#BDBDBD",
        COBALT="#0050FF", COBALT_DARK="#003DC4", COBALT_PRESSED="#002C8F",
        VERMILION="#FF1E1E", GOLDEN="#FFC800", GREEN="#00A651", PINK="#FF3EA5",
        LINE=3,
    ),
}
THEME_NAMES = {"miro": "Miró", "haring": "Keith Haring"}
DEFAULT_THEME = "miro"


def _chosen_theme() -> str:
    try:
        from ocusense.preferences import Preferences
        name = Preferences.load().theme
    except Exception:  # unreadable preferences never stop the app
        name = DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


ACTIVE = _chosen_theme()
PAPER = PAPER_DEEP = PAPER_HOVER = CARD = INK = GRAPHITE = RULE = ""
COBALT = COBALT_DARK = COBALT_PRESSED = VERMILION = GOLDEN = GREEN = PINK = ""
LINE = 2
globals().update(THEMES[ACTIVE])


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


def style_sheet() -> str:
    """The application style sheet in the active palette."""
    return f"""
QWidget#Root {{ background: {PAPER}; }}
QLabel {{ color: {INK}; background: transparent; }}
QLabel[role="secondary"] {{ color: {GRAPHITE}; }}
QLabel[role="eyebrow"] {{ color: {GRAPHITE}; font-weight: 700; }}
QLabel[role="error"] {{ color: {VERMILION}; font-weight: 600; }}
QFrame[role="rule"] {{ background: {INK}; border: none; }}
QFrame[role="hairline"] {{ background: {RULE}; border: none; }}

QPushButton {{
    min-height: 40px; padding: 0 18px; border-radius: 10px;
    font-size: 15px; font-weight: 700;
}}
QPushButton[kind="primary"] {{ background: {COBALT}; color: {PAPER}; border: {LINE}px solid {COBALT}; }}
QPushButton[kind="primary"]:hover {{ background: {COBALT_DARK}; border-color: {COBALT_DARK}; }}
QPushButton[kind="primary"]:pressed {{ background: {COBALT_PRESSED}; }}
QPushButton[kind="primary"]:focus {{ border-color: {INK}; }}
QPushButton[kind="secondary"] {{ background: transparent; color: {INK}; border: {LINE}px solid {INK}; }}
QPushButton[kind="secondary"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="secondary"]:focus {{ border-color: {COBALT}; }}
QPushButton[kind="quiet"] {{ background: transparent; color: {INK}; border: {LINE}px solid transparent; font-weight: 500; }}
QPushButton[kind="quiet"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="quiet"]:focus {{ border-color: {COBALT}; }}

QScrollArea {{ background: {PAPER}; border: none; }}
/* No scroll bars anywhere: pages still scroll with the trackpad, the mouse wheel and the keyboard. */
QScrollBar:vertical {{ width: 0px; background: transparent; border: none; }}
QScrollBar:horizontal {{ height: 0px; background: transparent; border: none; }}
QWidget#Segmented {{ border: {LINE}px solid {INK}; border-radius: 11px; background: transparent; }}
QPushButton[kind="segment"] {{
    min-height: 32px; padding: 0 14px; border-radius: 8px; border: {LINE}px solid transparent;
    background: transparent; color: {INK}; font-size: 14px; font-weight: 500;
}}
QPushButton[kind="segment"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="segment"]:checked {{ background: {INK}; color: {PAPER}; font-weight: 700; }}
QPushButton[kind="segment"]:focus {{ border-color: {COBALT}; }}
QPushButton[kind="row"] {{
    text-align: left; min-height: 48px; padding: 0 6px; border-radius: 6px; border: {LINE}px solid transparent;
    background: transparent; color: {INK}; font-size: 15px; font-weight: 700;
}}
QPushButton[kind="row"]:hover {{ background: {PAPER_HOVER}; }}
QPushButton[kind="row"]:focus {{ border-color: {COBALT}; }}

QWidget#Sidebar {{ background: {PAPER_DEEP}; }}
QCheckBox {{ color: {INK}; font-size: 15px; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: {LINE}px solid {INK}; border-radius: 5px; background: {PAPER}; }}
QCheckBox::indicator:checked {{ background: {COBALT}; border-color: {COBALT}; image: none; }}
QCheckBox:focus {{ outline: none; }}
QCheckBox::indicator:focus {{ border-color: {COBALT}; }}
QPushButton:disabled {{ color: {GRAPHITE}; background: transparent; border: {LINE}px dashed {RULE}; }}

QComboBox {{
    min-height: 36px; padding: 0 12px; border: {LINE}px solid {INK}; border-radius: 10px;
    background: {PAPER}; color: {INK}; font-size: 14px;
}}
QComboBox:focus {{ border-color: {COBALT}; }}
/* No separate grey arrow box: the whole rounded field opens the list. */
QComboBox::drop-down {{ width: 0px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
QComboBox QAbstractItemView {{ background: {PAPER}; color: {INK}; selection-background-color: {INK};
    selection-color: {PAPER}; border: 1px solid {INK}; }}
QSlider::groove:horizontal {{ height: 4px; background: {RULE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 18px; height: 18px; margin: -8px 0; border-radius: 9px;
    background: {COBALT}; border: {LINE}px solid {INK}; }}
QSlider:focus {{ outline: none; }}
QSlider::handle:horizontal:focus {{ border-color: {COBALT}; background: {PAPER}; }}

QSpinBox {{
    min-height: 36px; padding: 0 8px 0 12px; border: {LINE}px solid {INK}; border-radius: 10px;
    background: {PAPER}; color: {INK}; font-size: 14px; font-weight: 600;
}}
QSpinBox:focus {{ border-color: {COBALT}; }}
QLineEdit {{
    min-height: 38px; padding: 0 12px; border: {LINE}px solid {INK}; border-radius: 10px;
    background: {PAPER}; color: {INK}; font-size: 15px; selection-background-color: {COBALT};
}}
QLineEdit:focus {{ border-color: {COBALT}; }}
QLineEdit:disabled {{ color: {GRAPHITE}; border-color: {RULE}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}  /* − / + buttons sit beside it */
QSpinBox::up-arrow, QSpinBox::down-arrow {{ image: none; width: 0; height: 0; }}
QPushButton[kind="step"] {{
    min-height: 36px; min-width: 36px; max-width: 36px; padding: 0; border-radius: 18px;
    border: {LINE}px solid {INK}; background: transparent; color: {INK}; font-size: 18px; font-weight: 700;
}}
QPushButton[kind="step"]:hover {{ background: {PAPER_DEEP}; }}
QPushButton[kind="step"]:pressed {{ background: {INK}; color: {PAPER}; }}
QPushButton[kind="step"]:focus {{ border-color: {COBALT}; }}

QToolTip {{ background: {PAPER}; color: {INK}; border: 1px solid {INK}; padding: 4px; }}
"""


STYLE_SHEET = style_sheet()


def apply(name: str) -> dict[str, str]:
    """Switch the palette while OcuSense runs. Returns {old colour: new colour} (lowercase hex),
    so styles that already baked the old colours in can be updated (see MainWindow.apply_theme)."""
    global ACTIVE, STYLE_SHEET
    if name not in THEMES:
        name = DEFAULT_THEME
    old = THEMES[ACTIVE]
    new = THEMES[name]
    changes = {old[k].lower(): new[k] for k in old if isinstance(old[k], str) and old[k] != new[k]}
    ACTIVE = name
    globals().update(new)
    STYLE_SHEET = style_sheet()
    return changes
