"""Time log: record which subject or project you work on, and when — like Toggl, in the Miró style.

  Timer        pick a subject, add a note, Start / Stop (one timer at a time)
  Subjects     a card per course or project: today / this week, Start or Stop, Edit
  Week         a calendar of the week's entries (click one to edit it) and the entries listed by day
  Totals       time per subject today, this week, this month or all time

Everything is kept in timelog.json (ocusense/timelog_store.py) and saved on every
change, so a running timer keeps counting while OcuSense is closed. With "Run eye
monitoring while a timer runs" on (the default), starting a timer starts eye
monitoring and stopping it ends that session: the page emits `running_changed` and
the window does the rest.
"""

import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QBrush, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QLayout,
    QLineEdit, QPushButton, QSizePolicy, QTimeEdit, QVBoxLayout, QWidget,
)

from ocusense.core.stats import format_duration
from ocusense.core.timelog import COLOURS, KINDS, MAX_NAME, MAX_NOTE, day_start, period_bounds, week_monday
from ocusense.timelog_store import TimeLogStore

from . import theme
from .widgets.artwork import draw_star
from .widgets.common import button, label
from .widgets.page import Page, paragraph
from .widgets.segmented import Segmented

HEX = {"cobalt": theme.COBALT, "vermilion": theme.VERMILION, "golden": theme.GOLDEN, "green": theme.GREEN,
       "sky": "#7FA6D6", "ink": theme.INK, "orange": "#E8742A", "rose": "#E89AAE", "violet": "#6A4C9C",
       "teal": "#1F8A8A", "ochre": "#B5832B", "lime": "#A9C23F", "plum": "#8E2F5A", "brown": "#7A4A2A",
       "lilac": "#B9A3D9", "navy": "#152A5C", "peach": "#F2B48C", "stone": "#A59C8C"}
LIGHT = {"golden", "sky", "rose", "lime", "lilac", "peach", "stone"}  # colours that need ink text on top
COLOUR_NAMES = {"cobalt": "Cobalt blue", "vermilion": "Vermilion", "golden": "Golden yellow", "green": "Green",
                "sky": "Sky blue", "ink": "Ink", "orange": "Orange", "rose": "Rose", "violet": "Violet",
                "teal": "Teal", "ochre": "Ochre", "lime": "Lime", "plum": "Plum", "brown": "Brown",
                "lilac": "Lilac", "navy": "Navy", "peach": "Peach", "stone": "Stone grey"}
SWATCH_COLUMNS = 9
KIND_NAMES = {"subject": "Subject", "project": "Project"}
PERIODS = (("today", "Today"), ("week", "This week"), ("month", "This month"), ("all", "All time"))
CARD_COLUMNS = 3


def clock(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def short(seconds: float) -> str:
    return format_duration(seconds) if seconds >= 30 else "under 30 s"


def hhmm(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


# ---------------------------------------------------------------- artwork
def paint_mark(p: QPainter, rect: QRectF, kind: str, colour: str) -> None:
    """A subject is a full Miró circle, a project a Miró star with a dot."""
    c = rect.center()
    r = min(rect.width(), rect.height()) / 2
    hex_value = HEX.get(colour, theme.COBALT)
    if kind == "project":
        draw_star(p, c.x(), c.y(), r * 0.92, hex_value, max(2.0, r * 0.22))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawEllipse(c, r * 0.18, r * 0.18)
    else:
        p.setPen(QPen(theme.color(theme.INK), 2))
        p.setBrush(QBrush(theme.color(hex_value)))
        p.drawEllipse(c, r * 0.86, r * 0.86)


class Mark(QWidget):
    def __init__(self, kind: str, colour: str, size: int = 34, parent=None):
        super().__init__(parent)
        self.kind, self.colour = kind, colour
        self.setFixedSize(size, size)

    def set(self, kind: str, colour: str) -> None:
        self.kind, self.colour = kind, colour
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_mark(p, QRectF(self.rect()).adjusted(2, 2, -2, -2), self.kind, self.colour)
        p.end()


def _card_style(widget: QFrame, live: bool = False, dashed: bool = False) -> None:
    border = f"3px solid {theme.VERMILION}" if live else f"2px {'dashed' if dashed else 'solid'} {theme.INK}"
    widget.setStyleSheet(f"QFrame#Card {{ background: {theme.PAPER}; border: {border}; border-radius: 14px; }}")


def _stop_style(widget: QPushButton, on: bool) -> None:
    """The Stop button is vermilion, like a counted blink: it is the thing to notice."""
    widget.setStyleSheet(f"QPushButton {{ background: {theme.VERMILION}; color: {theme.PAPER}; "
                         f"border: 2px solid {theme.VERMILION}; }} QPushButton:focus {{ border-color: {theme.INK}; }}"
                         if on else "")


class StopwatchMark(QWidget):
    """The sidebar's stopwatch icon, for the duration pill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)

    def paintEvent(self, event) -> None:
        from .widgets.icons import draw_icon
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_icon(p, "time_log", QRectF(0, 0, 20, 20), theme.color(theme.GRAPHITE), theme.color(theme.PAPER_DEEP))
        p.end()


class PlayButton(QAbstractButton):
    """The round timer button: a cobalt ▶ to start, a vermilion ■ to stop."""

    def __init__(self, size: int = 52, parent=None):
        super().__init__(parent)
        self.running = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_running(False)

    def set_running(self, running: bool) -> None:
        self.running = running
        self.setText("Stop" if running else "Start")
        self.setAccessibleName("Stop the timer" if running else "Start the timer")
        self.setToolTip("Stop" if running else "Start: recording begins at once")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        fill = theme.color(theme.VERMILION if self.running else theme.COBALT)
        if not self.isEnabled():
            fill = theme.color(theme.RULE)
        elif self.isDown():
            fill = fill.darker(115)
        k = self.width() / 52  # drawn on a 52 grid
        p.setPen(QPen(theme.color(theme.COBALT if self.hasFocus() else theme.INK), 2))
        p.setBrush(QBrush(fill))
        p.drawEllipse(c, 24 * k, 24 * k)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.PAPER)))
        if self.running:
            p.drawRoundedRect(QRectF(c.x() - 8 * k, c.y() - 8 * k, 16 * k, 16 * k), 3, 3)
        else:
            tri = QPainterPath(QPointF(c.x() - 6 * k, c.y() - 10 * k))
            tri.lineTo(QPointF(c.x() + 11 * k, c.y()))
            tri.lineTo(QPointF(c.x() - 6 * k, c.y() + 10 * k))
            tri.closeSubpath()
            p.drawPath(tri)
        p.end()


def text_colour(colour: str):
    """A subject's colour for its name in lists; light colours are darkened enough to read on paper."""
    c = theme.color(HEX.get(colour, theme.INK))
    return c.darker(170) if colour in LIGHT else c


class SubjectChip(QAbstractButton):
    """The timer's subject: a dashed "+ Project or subject" until one is chosen, then its mark and name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.subject = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(40)
        self.show_subject(None)

    def show_subject(self, subject) -> None:
        self.subject = subject
        self.setText(subject.name if subject else "Project or subject")
        self.setAccessibleName(f"Subject or project: {subject.name}" if subject else "Choose a subject or project")
        font = theme.ui_font(15, QFont.Weight.DemiBold if subject else QFont.Weight.Medium)
        width = QFontMetrics(font).horizontalAdvance(self.text())
        self.setFixedWidth(min(300, width + 56))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        pen = QPen(theme.color(theme.COBALT if self.hasFocus() else theme.GRAPHITE), 1.6)
        if self.subject is None:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QBrush(theme.color(theme.PAPER if self.underMouse() or self.subject else theme.PAPER_DEEP)))
        p.drawRoundedRect(r, 10, 10)
        if self.subject is None:
            p.setPen(QPen(theme.color(theme.GRAPHITE), 1.8))
            c = QPointF(20, r.center().y())
            p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
            p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))
        else:
            paint_mark(p, QRectF(10, r.center().y() - 10, 20, 20), self.subject.kind, self.subject.colour)
        font = theme.ui_font(15, QFont.Weight.DemiBold if self.subject else QFont.Weight.Medium)
        p.setFont(font)
        p.setPen(text_colour(self.subject.colour) if self.subject else theme.color(theme.GRAPHITE))
        text = QFontMetrics(font).elidedText(self.text(), Qt.TextElideMode.ElideRight, int(r.width() - 48))
        p.drawText(QRectF(38, 0, r.width() - 44, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()


class PickerRow(QAbstractButton):
    """One choice in the picker: Miró mark and coloured name, a tick on the current one."""

    def __init__(self, subject, current: bool, parent=None):
        super().__init__(parent)
        self.subject, self.current, self.highlighted = subject, current, False
        self.setText(subject.name if subject else "No project")
        self.setAccessibleName(self.text())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the search field keeps the keyboard
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(38)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.highlighted or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.PAPER_DEEP)))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 1, -2, -1), 8, 8)
        s = self.subject
        if s is None:  # an empty outlined circle for "No project"
            p.setPen(QPen(theme.color(theme.GRAPHITE), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(22, self.height() / 2), 7.5, 7.5)
        else:
            paint_mark(p, QRectF(12, self.height() / 2 - 10, 20, 20), s.kind, s.colour)
        p.setFont(theme.ui_font(15, QFont.Weight.DemiBold if s else QFont.Weight.Medium))
        p.setPen(text_colour(s.colour) if s else theme.color(theme.INK))
        p.drawText(QRectF(42, 0, self.width() - 80, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QFontMetrics(p.font()).elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width() - 80))
        if self.current:
            tick = QPen(theme.color(theme.COBALT), 2.2)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(tick)
            x, y = self.width() - 26, self.height() / 2
            p.drawPolyline([QPointF(x - 5, y), QPointF(x - 1, y + 4), QPointF(x + 6, y - 5)])
        p.end()


class SubjectPicker(QFrame):
    """The panel under the subject chip, as in Toggl: search, No project, subjects, projects, Create.

    Typing a name that doesn't exist and pressing Return (or a Create button) makes it at once."""
    chosen = Signal(str)  # a subject id, or "" for no project
    create = Signal(str, str)  # (kind, name)

    def __init__(self, log, current: str, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.log, self.current = log, current
        self.setObjectName("Picker")
        self.setStyleSheet(theme.STYLE_SHEET + f"QFrame#Picker {{ background: {theme.PAPER}; "
                           f"border: 2px solid {theme.INK}; border-radius: 12px; }}")
        column = QVBoxLayout(self)
        column.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)  # the panel grows and shrinks with the matches
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(4)
        self.search = QLineEdit()
        self.search.setFixedWidth(356)  # sets the panel's width
        self.search.setPlaceholderText("Search or type a new name")
        self.search.setAccessibleName("Search subjects and projects")
        self.search.textChanged.connect(self._fill)
        self.search.installEventFilter(self)
        column.addWidget(self.search)
        self.list_host = QWidget()
        self.rows_layout = QVBoxLayout(self.list_host)
        self.rows_layout.setContentsMargins(0, 4, 0, 4)
        self.rows_layout.setSpacing(0)
        column.addWidget(self.list_host)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.create_subject = button("+  Create subject", "secondary")
        self.create_project = button("+  Create project", "secondary")
        for b, kind in ((self.create_subject, "subject"), (self.create_project, "project")):
            b.setStyleSheet("min-height: 34px; padding: 0 12px; font-size: 14px;")
            b.clicked.connect(lambda _=False, k=kind: self._create(k))
            footer.addWidget(b)
        column.addLayout(footer)
        self.rows: list[PickerRow] = []
        self.highlight = 0
        self._fill()

    def _fill(self, *_args) -> None:
        _clear(self.rows_layout)
        query = self.search.text().strip().lower()
        self.rows = []
        subjects = [s for s in self.log.visible_subjects() if query in s.name.lower()]

        def add(subject):
            row = PickerRow(subject, (subject.id if subject else "") == self.current)
            row.clicked.connect(lambda _=False, sid=(subject.id if subject else ""): self._choose(sid))
            self.rows.append(row)
            self.rows_layout.addWidget(row)

        if not query or "no project".startswith(query):
            add(None)
        for kind, heading in (("subject", "SUBJECTS"), ("project", "PROJECTS")):
            group = [s for s in subjects if s.kind == kind]
            if group:
                head = label(heading, "eyebrow", theme.ui_font(11, QFont.Weight.Bold))
                head.setContentsMargins(12, 8, 0, 2)
                self.rows_layout.addWidget(head)
                for s in group:
                    add(s)
        exact = any(s.name.lower() == query for s in subjects)
        if query and not exact:
            hint = label(f"Return creates “{self.search.text().strip()}” as a subject", "secondary",
                         theme.ui_font(13), wrap=True)
            hint.setContentsMargins(12, 6, 8, 2)
            self.rows_layout.addWidget(hint)
        elif not self.log.visible_subjects():
            hint = label("Type a name above to make your first subject or project.", "secondary",
                         theme.ui_font(13), wrap=True)
            hint.setContentsMargins(12, 6, 8, 2)
            self.rows_layout.addWidget(hint)
        self.create_subject.setText(f"+  Create subject" if not query or exact else "+  As a subject")
        self.create_project.setText(f"+  Create project" if not query or exact else "+  As a project")
        self.highlight = 0 if query else next((i for i, r in enumerate(self.rows) if r.current), 0)
        self._paint_highlight()

    def _paint_highlight(self) -> None:
        for i, row in enumerate(self.rows):
            row.highlighted = i == self.highlight
            row.update()

    def _choose(self, sid: str) -> None:
        self.chosen.emit(sid)
        self.close()

    def _create(self, kind: str) -> None:
        name = self.search.text().strip()
        if not name:
            self.search.setFocus()
            self.search.setPlaceholderText(f"Type the {kind}’s name, then Return")
            return
        existing = next((s for s in self.log.visible_subjects() if s.name.lower() == name.lower()), None)
        if existing is not None:
            self._choose(existing.id)
            return
        self.create.emit(kind, name)
        self.close()

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.rows:
                self.highlight = (self.highlight + (1 if key == Qt.Key.Key_Down else -1)) % len(self.rows)
                self._paint_highlight()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                query = self.search.text().strip().lower()
                exact = any(s.name.lower() == query for s in self.log.visible_subjects())
                if query and not exact:
                    self._create("subject")
                elif self.rows:
                    self.rows[self.highlight].click()
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def open_below(self, widget: QWidget, align_left: bool = False) -> None:
        self.adjustSize()
        point = widget.mapToGlobal(widget.rect().bottomLeft() if align_left else widget.rect().bottomRight())
        self.move(point.x() - (0 if align_left else self.width()), point.y() + 6)
        self.show()
        self.search.setFocus()


# ---------------------------------------------------------------- subject cards
class MarkButton(QAbstractButton):
    """The card's Miró mark; click it to change the colour."""

    def __init__(self, kind: str, colour: str, parent=None):
        super().__init__(parent)
        self.kind, self.colour = kind, colour
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip("Change colour")

    def set(self, kind: str, colour: str, name: str = "") -> None:
        self.kind, self.colour = kind, colour
        self.setAccessibleName(f"Change the colour of {name}" if name else "Change colour")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(QPen(theme.color(theme.COBALT if self.hasFocus() else theme.RULE), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        paint_mark(p, QRectF(self.rect()).adjusted(5, 5, -5, -5), self.kind, self.colour)
        p.end()


class ColourPopup(QFrame):
    """The swatches under a card's mark: a click changes the colour at once."""
    chosen = Signal(str)

    def __init__(self, current: str, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("Picker")
        self.setStyleSheet(f"QFrame#Picker {{ background: {theme.PAPER}; border: 2px solid {theme.INK}; "
                           "border-radius: 12px; }")
        column = QVBoxLayout(self)
        column.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        column.setContentsMargins(12, 10, 12, 12)
        column.addWidget(label("COLOUR", "eyebrow", theme.ui_font(11, QFont.Weight.Bold)))
        self.choice = ColourChoice(current)
        self.choice.changed.connect(self._pick)
        column.addWidget(self.choice)

    def _pick(self, key: str) -> None:
        self.chosen.emit(key)
        self.close()

    def open_below(self, widget: QWidget) -> None:
        self.adjustSize()
        self.move(widget.mapToGlobal(widget.rect().bottomLeft()) + QPointF(0, 6).toPoint())
        self.show()
        self.choice.buttons[self.choice.current()].setFocus()


class SubjectCard(QFrame):
    colour_clicked = Signal(str)
    edit = Signal(str)

    def __init__(self, subject, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.sid = subject.id
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # cards in a row share a height
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(6)
        top = QHBoxLayout()
        self.mark = MarkButton(subject.kind, subject.colour)
        self.mark.clicked.connect(lambda: self.colour_clicked.emit(self.sid))
        top.addWidget(self.mark)
        self.kind_label = label(KIND_NAMES[subject.kind].upper(), "eyebrow", theme.ui_font(11, QFont.Weight.Bold))
        top.addWidget(self.kind_label)
        top.addStretch(1)
        self.edit_button = button("Edit", "quiet")
        self.edit_button.setStyleSheet("min-height: 28px; padding: 0 8px; font-size: 13px;")
        self.edit_button.setAccessibleName(f"Edit {subject.name}")
        self.edit_button.clicked.connect(lambda: self.edit.emit(self.sid))
        top.addWidget(self.edit_button)
        column.addLayout(top)
        self.name_label = label(subject.name, font=theme.ui_font(18, QFont.Weight.Bold), wrap=True)
        column.addWidget(self.name_label)
        self.totals_label = label("", "secondary", theme.ui_font(13))
        column.addWidget(self.totals_label)
        self.live_label = label("", font=theme.number_font(13))  # "Recording 0:12:03" while its timer runs
        self.live_label.setStyleSheet(f"color: {theme.VERMILION};")
        column.addWidget(self.live_label)
        column.addStretch(1)

    def show_state(self, subject, today: float, week: float, live_seconds: float | None) -> None:
        self.mark.set(subject.kind, subject.colour, subject.name)
        self.kind_label.setText(KIND_NAMES[subject.kind].upper())
        self.name_label.setText(subject.name)
        self.totals_label.setText(f"Today {short(today)}  ·  This week {short(week)}")
        live = live_seconds is not None
        self.live_label.setText(f"● Recording  {clock(live_seconds)}" if live else "")
        self.live_label.setVisible(live)
        _card_style(self, live)


class AddCard(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        _card_style(self, dashed=True)
        self.setMinimumHeight(118)
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.addStretch(1)
        self.button = button("+  Add a subject or project", "quiet")
        self.button.clicked.connect(self.clicked)
        column.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)
        column.addStretch(1)


# ---------------------------------------------------------------- dialogs
class Swatch(QAbstractButton):
    """One round colour; painted directly, so it looks the same on every Mac (style sheets draw squares there)."""

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(COLOUR_NAMES[key])
        self.setToolTip(COLOUR_NAMES[key])

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked() or self.hasFocus():
            p.setPen(QPen(theme.color(theme.COBALT if self.hasFocus() and not self.isChecked() else theme.INK), 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 15, 15)
        p.setPen(QPen(theme.color(theme.INK), 1.2))
        p.setBrush(QBrush(theme.color(HEX[self.key])))
        p.drawEllipse(c, 11, 11)
        p.end()


class ColourChoice(QWidget):
    """Round Miró colour swatches in rows; one is chosen."""
    changed = Signal(str)

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for n, key in enumerate(COLOURS):
            swatch = Swatch(key)
            swatch.setChecked(key == current)
            self.group.addButton(swatch)
            self.buttons[key] = swatch
            grid.addWidget(swatch, *divmod(n, SWATCH_COLUMNS))
        grid.setColumnStretch(SWATCH_COLUMNS, 1)
        self.group.buttonClicked.connect(lambda b: self.changed.emit(b.key))

    def current(self) -> str:
        return next(k for k, b in self.buttons.items() if b.isChecked())


class _Dialog(QDialog):
    """A paper sheet over the window, without the macOS title bar: Save, Cancel (or Esc) and Delete close it."""

    def __init__(self, title: str, parent=None, heading: bool = True):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # only the rounded sheet shows
        self.setStyleSheet(theme.STYLE_SHEET + f"QFrame#Sheet {{ background: {theme.PAPER}; "
                           f"border: 2px solid {theme.INK}; border-radius: 16px; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sheet = QFrame()
        sheet.setObjectName("Sheet")
        outer.addWidget(sheet)
        self.column = QVBoxLayout(sheet)
        self.column.setContentsMargins(28, 24, 28, 22)
        self.column.setSpacing(10)
        if heading:
            self.column.addWidget(label(title, font=theme.ui_font(24, QFont.Weight.Bold)))
        self.error = label("", "error", theme.ui_font(13), wrap=True)
        self.error.setVisible(False)
        self.deleted = False

    def field(self, text: str, widget: QWidget) -> None:
        self.column.addWidget(label(text, font=theme.ui_font(13, QFont.Weight.DemiBold)))
        self.column.addWidget(widget)

    def buttons(self, can_delete: bool, cancel: bool = True) -> None:
        self.column.addWidget(self.error)
        self.column.addSpacing(6)
        row = QHBoxLayout()
        if can_delete:
            self.delete_button = button("Delete", "quiet")
            self.delete_button.setStyleSheet(f"color: {theme.VERMILION};")
            self.delete_button.clicked.connect(self._delete)
            row.addWidget(self.delete_button)
        row.addStretch(1)
        if cancel:
            cancel_button = button("Cancel", "quiet")
            cancel_button.clicked.connect(self.reject)
            row.addWidget(cancel_button)
        self.ok = button("Save", "primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._save)
        row.addWidget(self.ok)
        self.button_row = QWidget()
        self.button_row.setLayout(row)
        self.column.addWidget(self.button_row)
        # Delete asks here, in the sheet itself (no second window)
        self.confirm = QWidget()
        confirm = QHBoxLayout(self.confirm)
        confirm.setContentsMargins(0, 0, 0, 0)
        self.confirm_text = label("", font=theme.ui_font(14, QFont.Weight.DemiBold), wrap=True)
        confirm.addWidget(self.confirm_text, 1)
        keep = button("Keep", "quiet")
        keep.clicked.connect(lambda: self._asking(False))
        self.really_delete = button("Delete", "primary")
        self.really_delete.setStyleSheet(
            f"QPushButton {{ background: {theme.VERMILION}; border-color: {theme.VERMILION}; }}")
        self.really_delete.clicked.connect(self._really_delete)
        confirm.addWidget(keep)
        confirm.addWidget(self.really_delete)
        self.confirm.setVisible(False)
        self.column.addWidget(self.confirm)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        window = self.parentWidget().window() if self.parentWidget() else None
        if window is not None:  # centred over OcuSense
            centre = window.geometry().center()
            self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 2)

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def delete_question(self) -> tuple[str, str]:
        return "Delete?", ""

    def _delete(self) -> None:
        title, text = self.delete_question()
        self.confirm_text.setText(f"{title} {text}".strip())
        self._asking(True)

    def _asking(self, on: bool) -> None:
        self.button_row.setVisible(not on)
        self.confirm.setVisible(on)
        (self.really_delete if on else self.ok).setFocus()

    def _really_delete(self) -> None:
        self.deleted = True
        self.accept()

    def _save(self) -> None:
        self.accept()


class SubjectDialog(_Dialog):
    def __init__(self, subject=None, entry_count: int = 0, colour: str = "cobalt", parent=None):
        super().__init__("Edit" if subject else "New subject or project", parent)
        self.entry_count = entry_count
        self.subject = subject
        self.name = QLineEdit(subject.name if subject else "")
        self.name.setMaxLength(MAX_NAME)
        self.name.setPlaceholderText("e.g. Systems Biology, or OcuSense")
        self.name.setAccessibleName("Name")
        self.field("Name", self.name)
        self.kind = Segmented([(k, KIND_NAMES[k]) for k in KINDS], subject.kind if subject else "subject", "Type")
        self.field("Type", self.kind)
        self.colour = ColourChoice(subject.colour if subject else colour)
        self.field("Colour", self.colour)
        self.buttons(subject is not None)
        self.setMinimumWidth(420)
        self.name.setFocus()

    def delete_question(self):
        n = self.entry_count
        return (f"Delete “{self.subject.name}”?",
                f"This also deletes its {n} logged entr{'y' if n == 1 else 'ies'}. It can’t be undone." if n
                else "It can’t be undone.")

    def _save(self) -> None:
        if not self.name.text().strip():
            self.show_error("Give it a name first.")
            return
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return self.name.text().strip(), self.kind.current(), self.colour.current()


def parse_duration(text: str) -> float | None:
    """ "1:30", "1h 30m", "1h", "45m" or "45" (minutes) → seconds; None if it can't be read."""
    import re
    t = text.strip().lower().replace(" ", "")
    if not t:
        return None
    if re.fullmatch(r"\d+:\d{1,2}(:\d{1,2})?", t):
        parts = [int(x) for x in t.split(":")] + [0]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m(?:in)?)?", t)
    if m and (m.group(1) or m.group(2)):
        return float(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
    if re.fullmatch(r"\d+", t):
        return int(t) * 60
    return None


def _pill(widget: QWidget) -> None:
    widget.setObjectName("Pill")
    widget.setStyleSheet(f"#Pill {{ background: {theme.PAPER_DEEP}; border: 1.5px solid {theme.RULE}; "
                         "border-radius: 12px; }")


class _TimeField(QTimeEdit):
    """A bare HH:MM field for inside a pill: no arrows, no box (↑/↓ and typing still work)."""

    def __init__(self, value: QTime, name: str, parent=None):
        super().__init__(value, parent)
        self.setDisplayFormat("HH:mm")
        self.setAccessibleName(name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.number_font(17))
        self.setFixedWidth(QFontMetrics(theme.number_font(17)).horizontalAdvance("00:00") + 24)
        self.setStyleSheet(f"QTimeEdit {{ border: 2px solid transparent; border-radius: 8px; background: transparent;"
                           f" min-height: 34px; padding: 0 4px; color: {theme.INK}; }}"
                           f" QTimeEdit:focus {{ border-color: {theme.COBALT}; background: {theme.PAPER}; }}"
                           f" QTimeEdit:disabled {{ color: {theme.GRAPHITE}; }}"
                           # its inner text field must not take the app-wide QLineEdit padding and border
                           " QTimeEdit QLineEdit { border: none; padding: 0; min-height: 0; background: transparent; }"
                           # arrows hidden by size (NoButtons plus a style sheet squeezes the text to nothing)
                           " QTimeEdit::up-button, QTimeEdit::down-button { width: 0; border: none; image: none; }"
                           " QTimeEdit::up-arrow, QTimeEdit::down-arrow { image: none; width: 0; height: 0; }")


class EntryDialog(_Dialog):
    """One entry as a card, like Toggl's: what you did, the subject, then day · start → end · duration.

    A finished entry can be continued with ▶ (a new timer with the same subject and note)."""

    def __init__(self, log, entry=None, subject_id: str | None = None, now: float | None = None, parent=None,
                 create=None):
        super().__init__("Edit entry" if entry else "Add a past entry", parent, heading=False)
        now = time.time() if now is None else now
        self.log, self.entry, self.create = log, entry, create
        self.running = entry is not None and entry.end is None
        self.continued = False
        self.sid = (entry.subject_id if entry else subject_id) or ""
        if not log.known(self.sid):
            self.sid = ""

        # header: LOGGED / RECORDING / NEW ENTRY, continue ▶ and close ×
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label("RECORDING" if self.running else "LOGGED" if entry else "NEW ENTRY", "eyebrow",
                             theme.ui_font(12, QFont.Weight.Bold)))
        head.addStretch(1)
        if entry is not None and not self.running:
            self.continue_button = PlayButton(38)
            self.continue_button.setToolTip("Continue: start a new timer with this subject and note")
            self.continue_button.setAccessibleName("Continue this entry")
            self.continue_button.clicked.connect(self._continue)
            head.addWidget(self.continue_button)
        close = button("✕", "quiet")
        close.setAccessibleName("Close without saving")
        close.setStyleSheet("min-height: 34px; min-width: 34px; max-width: 34px; padding: 0; font-size: 16px;")
        close.clicked.connect(self.reject)
        head.addWidget(close)
        self.column.addLayout(head)

        # what you did
        self.note = QLineEdit(entry.note if entry else "")
        self.note.setMaxLength(MAX_NOTE)
        self.note.setPlaceholderText("What did you work on?")
        self.note.setAccessibleName("What did you work on?")
        self.note.setStyleSheet(f"QLineEdit {{ border: none; border-bottom: 2px solid transparent; border-radius: 0;"
                                f" background: transparent; font-size: 22px; padding: 0; min-height: 40px; }}"
                                f" QLineEdit:focus {{ border-bottom-color: {theme.COBALT}; }}")
        self.column.addWidget(self.note)

        # subject chip (+ clear)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip = SubjectChip()
        self.chip.clicked.connect(self._pick_subject)
        chips.addWidget(self.chip)
        self.clear_subject = button("✕", "quiet")
        self.clear_subject.setAccessibleName("No project")
        self.clear_subject.setToolTip("Remove the subject")
        self.clear_subject.setStyleSheet("min-height: 30px; min-width: 30px; max-width: 30px; padding: 0;")
        self.clear_subject.clicked.connect(lambda: self._set_subject(""))
        chips.addWidget(self.clear_subject)
        chips.addStretch(1)
        self.column.addLayout(chips)
        self.column.addSpacing(4)

        # day · start → end · duration
        start = datetime.fromtimestamp(entry.start if entry else now - 3600)
        end = datetime.fromtimestamp(entry.end if entry and entry.end is not None else now)
        self.date = start.date()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.day_button = QPushButton()
        self.day_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.day_button.setAccessibleName("Day")
        self.day_button.setFont(theme.ui_font(15, QFont.Weight.DemiBold))
        self.day_button.setStyleSheet(
            f"QPushButton {{ background: {theme.PAPER_DEEP}; border: 1.5px solid {theme.RULE}; border-radius: 12px;"
            f" min-height: 44px; padding: 0 14px; color: {theme.INK}; }}"
            f" QPushButton:hover {{ border-color: {theme.INK}; }} QPushButton:focus {{ border-color: {theme.COBALT}; }}")
        self.day_button.clicked.connect(self._pick_day)
        row.addWidget(self.day_button)

        times = QFrame()
        _pill(times)
        line = QHBoxLayout(times)
        line.setContentsMargins(8, 3, 8, 3)
        line.setSpacing(4)
        self.start = _TimeField(QTime(start.hour, start.minute), "Start")
        self.end = _TimeField(QTime(end.hour, end.minute), "End")
        arrow = label("→", "secondary", theme.ui_font(16))
        line.addStretch(1)  # start → end sit together in the middle of the pill
        line.addWidget(self.start)
        line.addWidget(arrow)
        line.addWidget(self.end)
        self.next_day = label("+1 day", font=theme.ui_font(11, QFont.Weight.Bold))
        self.next_day.setStyleSheet(f"color: {theme.COBALT};")
        self.next_day.setToolTip("Ends the next day (ran past midnight)")
        line.addWidget(self.next_day)
        line.addStretch(1)
        if self.running:
            self.end.setEnabled(False)
            self.end.setToolTip("Still running. Stop the timer to give it an end.")
        row.addWidget(times, 1)

        clock_pill = QFrame()
        _pill(clock_pill)
        dline = QHBoxLayout(clock_pill)
        dline.setContentsMargins(10, 3, 10, 3)
        dline.setSpacing(4)
        dline.addWidget(StopwatchMark())
        self.duration = QLineEdit()
        self.duration.setAccessibleName("Duration")
        self.duration.setToolTip("Type a duration (1:30, 45m, 2h) to move the end")
        self.duration.setFont(theme.number_font(16))
        self.duration.setFixedWidth(QFontMetrics(theme.number_font(16)).horizontalAdvance("00:00:00") + 14)
        self.duration.setStyleSheet(f"QLineEdit {{ border: 2px solid transparent; border-radius: 8px;"
                                    f" background: transparent; min-height: 34px; padding: 0 4px; }}"
                                    f" QLineEdit:focus {{ border-color: {theme.COBALT}; background: {theme.PAPER}; }}")
        self.duration.setReadOnly(self.running)
        self.duration.editingFinished.connect(self._duration_typed)
        dline.addWidget(self.duration)
        row.addWidget(clock_pill)
        self.column.addLayout(row)
        self.same_day = label("", "secondary", theme.ui_font(12))
        self.column.addWidget(self.same_day)

        self.start.timeChanged.connect(self._times_changed)
        self.end.timeChanged.connect(self._times_changed)
        self.now = now
        self.buttons(entry is not None, cancel=False)
        self.setMinimumWidth(560)
        self._set_subject(self.sid)
        self._show_day()
        self._times_changed()
        if not entry:
            self.note.setFocus()

    # ------------------------------------------------------------ pieces
    def _set_subject(self, sid: str) -> None:
        self.sid = sid
        subject = self.log.subject(sid)
        self.chip.show_subject(subject)
        self.clear_subject.setVisible(subject is not None)

    def _pick_subject(self) -> None:
        self.picker = SubjectPicker(self.log, self.sid, self)
        self.picker.chosen.connect(self._set_subject)
        self.picker.create.connect(self._create_subject)
        self.picker.open_below(self.chip, align_left=True)

    def _create_subject(self, kind: str, name: str) -> None:
        subject = self.create(kind, name) if self.create else None
        if subject is not None:
            self._set_subject(subject.id)

    def _pick_day(self) -> None:
        from PySide6.QtWidgets import QCalendarWidget
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("Picker")
        popup.setStyleSheet(f"QFrame#Picker {{ background: {theme.PAPER}; border: 2px solid {theme.INK};"
                            " border-radius: 12px; }")
        box = QVBoxLayout(popup)
        box.setContentsMargins(8, 8, 8, 8)
        calendar = QCalendarWidget()
        calendar.setGridVisible(False)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setSelectedDate(QDate(self.date.year, self.date.month, self.date.day))
        calendar.setMaximumDate(QDate.currentDate())
        calendar.setStyleSheet(
            f"QCalendarWidget QWidget {{ alternate-background-color: {theme.PAPER}; }}"
            f" QCalendarWidget QAbstractItemView {{ background: {theme.PAPER}; color: {theme.INK};"
            f" selection-background-color: {theme.COBALT}; selection-color: {theme.PAPER}; outline: 0; }}"
            f" QCalendarWidget QToolButton {{ color: {theme.INK}; background: transparent; font-weight: 700;"
            f" min-height: 30px; padding: 0 8px; }}"
            f" QCalendarWidget #qt_calendar_navigationbar {{ background: {theme.PAPER_DEEP}; border-radius: 8px; }}")

        def chosen(d: QDate) -> None:
            self.date = date(d.year(), d.month(), d.day())
            self._show_day()
            popup.close()
        calendar.clicked.connect(chosen)
        calendar.activated.connect(chosen)
        box.addWidget(calendar)
        popup.adjustSize()
        popup.move(self.day_button.mapToGlobal(self.day_button.rect().bottomLeft()) + QPointF(0, 6).toPoint())
        popup.show()
        calendar.setFocus()
        self.day_popup = popup

    def _show_day(self) -> None:
        today = date.fromtimestamp(self.now) if hasattr(self, "now") else date.today()
        name = "Today" if self.date == today else "Yesterday" if self.date == today - timedelta(days=1) \
            else f"{self.date:%a} {self.date.day} {self.date:%b}" if self.date.year == today.year \
            else f"{self.date:%a} {self.date.day} {self.date:%b %Y}"
        self.day_button.setText(name)
        self._show_same_day()

    def _show_same_day(self) -> None:
        a, b = day_start(self.date), day_start(self.date + timedelta(days=1))
        others = [e for e in self.log.entries if a <= e.start < b and (self.entry is None or e.id != self.entry.id)]
        n = len(others)
        self.same_day.setText(f"Logged {n} other time{'s' if n != 1 else ''} on this day" if n else "")
        self.same_day.setVisible(bool(n))

    def _span(self) -> tuple[float, float | None, bool]:
        s, e = self.start.time(), self.end.time()
        start = datetime(self.date.year, self.date.month, self.date.day, s.hour(), s.minute())
        if self.running:
            return start.timestamp(), None, False
        end = datetime(self.date.year, self.date.month, self.date.day, e.hour(), e.minute())
        later = end <= start
        if later:
            end += timedelta(days=1)  # ran past midnight
        return start.timestamp(), end.timestamp(), later

    def _times_changed(self, *_args) -> None:
        start, end, later = self._span()
        self.next_day.setVisible(later)
        seconds = (self.now - self.entry.start) if self.running else end - start
        self.duration.setText(clock(seconds))

    def _duration_typed(self) -> None:
        seconds = parse_duration(self.duration.text())
        if seconds is None or seconds <= 0 or seconds > 24 * 3600:
            self.show_error("Type a duration like 1:30, 45m or 2h.")
            self._times_changed()
            return
        self.show_error("")
        start, _, _ = self._span()
        end = datetime.fromtimestamp(start + seconds)
        self.end.setTime(QTime(end.hour, end.minute))
        self._times_changed()

    def _continue(self) -> None:
        self.continued = True
        self.accept()

    # ------------------------------------------------------------ result
    def delete_question(self):
        return "Delete this entry?", "It can’t be undone."

    def values(self) -> tuple[str, float, float | None, str]:
        start, end, _ = self._span()
        return self.sid, start, end, self.note.text().strip()

    def _save(self) -> None:
        _, start, end, _ = self.values()
        if end is not None and end - start > 24 * 3600:
            self.show_error("An entry can be at most 24 hours long.")
            return
        if start > time.time() + 60:
            self.show_error("That start time is still in the future.")
            return
        self.accept()


# ---------------------------------------------------------------- week calendar
class WeekCalendar(QWidget):
    """Seven day columns with the week's entries as coloured blocks; click a block to edit it."""
    entry_clicked = Signal(str)
    GUTTER, HEAD, HOUR = 56, 58, 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.monday = week_monday(date.today())
        self.blocks: list[tuple[QRectF, str]] = []
        self.items = []  # (day index, start hour, end hour, colour, title, entry id, running)
        self.day_totals = [0.0] * 7
        self.first_hour, self.last_hour = 7, 22
        self.today = date.today()
        self.now_hour = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Week calendar")

    def show_week(self, log, monday: date, now: float) -> None:
        self.monday, self.today = monday, date.fromtimestamp(now)
        self.items, self.day_totals = [], []
        first, last = 7, 22
        for i in range(7):
            day = monday + timedelta(days=i)
            a, b = day_start(day), day_start(day + timedelta(days=1))
            self.day_totals.append(log.total(a, b, now))
            for e in log.between(a, b, now):
                s = log.shown_subject(e.subject_id)
                end = now if e.end is None else e.end
                h0, h1 = (max(e.start, a) - a) / 3600, (min(end, b) - a) / 3600
                if h1 - h0 <= 0:
                    continue
                first, last = min(first, int(h0)), max(last, int(h1 + 0.999))
                title = f"{s.name} · {hhmm(e.start)} to {'now' if e.end is None else hhmm(e.end)}"
                self.items.append((i, h0, h1, s.colour, s.name, title + (f"\n{e.note}" if e.note else ""),
                                   e.id, e.end is None))
        self.first_hour, self.last_hour = first, min(24, last)
        self.now_hour = (now - day_start(self.today)) / 3600 if monday <= self.today < monday + timedelta(days=7) else None
        self.setFixedHeight(self.HEAD + (self.last_hour - self.first_hour) * self.HOUR + 8)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(700, self.height())

    def _y(self, hour: float) -> float:
        return self.HEAD + (hour - self.first_hour) * self.HOUR

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width() - self.GUTTER
        col = w / 7
        bottom = self._y(self.last_hour)
        # hour lines and labels
        p.setFont(theme.number_font(11))
        for h in range(self.first_hour, self.last_hour + 1):
            y = self._y(h)
            p.setPen(QPen(theme.color(theme.RULE), 1))
            p.drawLine(QPointF(self.GUTTER, y), QPointF(self.width(), y))
            if h < self.last_hour:
                p.setPen(theme.color(theme.GRAPHITE))
                p.drawText(QRectF(0, y - 8, self.GUTTER - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{h:02d}:00")
        # day headers and columns
        for i in range(7):
            day = self.monday + timedelta(days=i)
            x = self.GUTTER + i * col
            p.setPen(QPen(theme.color(theme.RULE), 1))
            p.drawLine(QPointF(x, self.HEAD - 6), QPointF(x, bottom))
            today = day == self.today
            if today:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(theme.color(theme.PAPER_DEEP)))
                p.drawRect(QRectF(x + 1, self.HEAD, col - 1, bottom - self.HEAD))
            if today:  # today's date sits in a cobalt Miró circle
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(theme.color(theme.COBALT)))
                p.drawEllipse(QPointF(x + 22, 24), 16, 16)
            p.setPen(theme.color(theme.PAPER if today else theme.INK))
            p.setFont(theme.ui_font(22, QFont.Weight.Medium))
            p.drawText(QRectF(x + 6, 6, 32, 36), Qt.AlignmentFlag.AlignCenter, str(day.day))
            p.setPen(theme.color(theme.COBALT if today else theme.INK))
            p.setFont(theme.ui_font(13, QFont.Weight.Bold))
            p.drawText(QRectF(x + 44, 6, col - 46, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{day:%a}")
            p.setPen(theme.color(theme.GRAPHITE))
            p.setFont(theme.number_font(11))
            p.drawText(QRectF(x + 44, 24, col - 46, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       short(self.day_totals[i]) if self.day_totals else "")
        # blocks, side by side where they overlap
        self.blocks = []
        for i in range(7):
            mine = sorted((it for it in self.items if it[0] == i), key=lambda it: it[1])
            lanes, placed = [], []
            for it in mine:
                lane = next((n for n, end in enumerate(lanes) if end <= it[1]), None)
                if lane is None:
                    lane = len(lanes)
                    lanes.append(0)
                lanes[lane] = it[2]
                placed.append((it, lane))
            n = max(1, len(lanes))
            for (day, h0, h1, colour, name, title, eid, live), lane in placed:
                x = self.GUTTER + day * col + 3 + lane * (col - 6) / n
                r = QRectF(x, self._y(h0) + 1, (col - 6) / n - 2, max(4.0, (h1 - h0) * self.HOUR - 2))
                p.setPen(QPen(theme.color(theme.VERMILION if live else theme.INK), 2 if live else 1.2))
                p.setBrush(QBrush(theme.color(HEX.get(colour, theme.COBALT))))
                p.drawRoundedRect(r, 5, 5)
                if r.height() >= 18:
                    p.setPen(theme.color(theme.INK if colour in LIGHT else theme.PAPER))
                    p.setFont(theme.ui_font(11, QFont.Weight.Bold))
                    text = QFontMetrics(p.font()).elidedText(name, Qt.TextElideMode.ElideRight, int(r.width() - 8))
                    p.drawText(r.adjusted(5, 3, -4, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
                if r.height() >= 40:  # the duration at the bottom, as in Toggl
                    p.setFont(theme.number_font(11))
                    p.drawText(r.adjusted(5, 2, -4, -4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                               clock((h1 - h0) * 3600) if live else short((h1 - h0) * 3600))
                self.blocks.append((r, eid, title))
        if self.now_hour is not None and self.first_hour <= self.now_hour <= self.last_hour:
            x = self.GUTTER + (self.today - self.monday).days * col
            y = self._y(self.now_hour)
            p.setPen(QPen(theme.color(theme.VERMILION), 2))
            p.drawLine(QPointF(x, y), QPointF(x + col, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.VERMILION)))
            p.drawEllipse(QPointF(x, y), 4, 4)
        p.end()

    def _block_at(self, pos):
        return next(((eid, title) for r, eid, title in reversed(self.blocks) if r.contains(QPointF(pos))), None)

    def mouseMoveEvent(self, event) -> None:
        hit = self._block_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
        self.setToolTip(hit[1] if hit else "")

    def mouseReleaseEvent(self, event) -> None:
        hit = self._block_at(event.position())
        if hit:
            self.entry_clicked.emit(hit[0])


# ---------------------------------------------------------------- totals bars
class TotalsBars(QWidget):
    ROW = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Time per subject")

    def show_rows(self, rows) -> None:
        self.rows = rows  # [(subject, seconds)]
        total = sum(s for _, s in rows)
        self.setAccessibleDescription("; ".join(f"{sub.name}: {format_duration(sec)}" for sub, sec in rows))
        self.total = total
        self.setFixedHeight(max(1, len(rows)) * self.ROW)
        self.update()

    def paintEvent(self, event) -> None:
        if not self.rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        most = self.rows[0][1]
        w = self.width() - 32
        for n, (s, sec) in enumerate(self.rows):
            y = n * self.ROW
            paint_mark(p, QRectF(0, y + 2, 20, 20), s.kind, s.colour)
            p.setPen(theme.color(theme.INK))
            p.setFont(theme.ui_font(14, QFont.Weight.DemiBold))
            p.drawText(QRectF(30, y, w * 0.6, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(s.name, Qt.TextElideMode.ElideRight, int(w * 0.6)))
            p.setPen(theme.color(theme.GRAPHITE))
            p.setFont(theme.number_font(12))
            p.drawText(QRectF(30, y, w, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{format_duration(sec)} · {round(sec / self.total * 100)}%")
            track = QRectF(30, y + 27, w, 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(theme.color(theme.PAPER_DEEP)))
            p.drawRoundedRect(track, 4, 4)
            p.setPen(QPen(theme.color(theme.INK), 1))
            p.setBrush(QBrush(theme.color(HEX.get(s.colour, theme.COBALT))))
            p.drawRoundedRect(QRectF(30, y + 27, max(8.0, w * sec / most), 8), 4, 4)
        p.end()


# ---------------------------------------------------------------- the page
class TimeLogPage(Page):
    status_text = Signal(str)  # for the sidebar: "0:12:03" while a timer runs, "" otherwise
    running_changed = Signal(bool)  # a timer started (True) or stopped (False) here — the window links monitoring

    def __init__(self, store: TimeLogStore | None = None, preferences=None, parent=None):
        super().__init__("Time log", "", "", parent)  # opens straight on the timer and the week, like Toggl
        self.store = store or TimeLogStore()
        self.week_offset = 0
        self.period = "week"
        self.cards: dict[str, SubjectCard] = {}
        self.selected: str | None = None  # the subject the timer bar starts

        self.error_label = label("", "error", theme.ui_font(14), wrap=True)
        self.body.addWidget(self.error_label)

        # the timer bar, as in Toggl: what you're on, the subject, the clock and one round ▶ / ■ button
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setStyleSheet(f"QFrame#Card {{ background: {theme.PAPER_DEEP}; border: 2px solid {theme.INK}; "
                          "border-radius: 16px; }")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 12, 14, 12)
        row.setSpacing(14)
        self.note = QLineEdit()
        self.note.setPlaceholderText("What are you working on?")
        self.note.setMaxLength(MAX_NOTE)
        self.note.setAccessibleName("What are you working on?")
        self.note.setStyleSheet("QLineEdit { border: none; background: transparent; font-size: 22px; padding: 0; }")
        self.note.editingFinished.connect(self._note_changed)
        self.note.returnPressed.connect(self._enter_in_note)
        row.addWidget(self.note, 1)
        self.chip = SubjectChip()
        self.chip.clicked.connect(self.open_picker)
        row.addWidget(self.chip)
        self.picker: SubjectPicker | None = None
        self.clock_label = label("0:00:00", font=theme.number_font(26))
        self.clock_label.setMinimumWidth(QFontMetrics(theme.number_font(26)).horizontalAdvance("00:00:00") + 6)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.clock_label)
        self.main_button = PlayButton()
        self.main_button.clicked.connect(self._main_action)
        row.addWidget(self.main_button)
        self.body.addWidget(bar)

        # the week, right under the timer
        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.prev_button, self.this_button, self.next_button = (button("‹", "step"), button("This week", "quiet"),
                                                                 button("›", "step"))
        self.prev_button.setAccessibleName("Previous week")
        self.next_button.setAccessibleName("Next week")
        self.prev_button.clicked.connect(lambda: self._move_week(-1))
        self.this_button.clicked.connect(lambda: self._move_week(0))
        self.next_button.clicked.connect(lambda: self._move_week(1))
        nav.addWidget(self.prev_button)
        nav.addWidget(self.this_button)
        nav.addWidget(self.next_button)
        nav.addSpacing(10)
        self.week_title = label("", font=theme.ui_font(18, QFont.Weight.Bold))
        nav.addWidget(self.week_title)
        nav.addStretch(1)
        self.week_total = label("", "secondary", theme.number_font(14))
        nav.addWidget(self.week_total)
        nav.addSpacing(10)
        self.add_entry_button = button("Add a past entry", "secondary")
        self.add_entry_button.clicked.connect(lambda: self.add_entry())
        nav.addWidget(self.add_entry_button)
        self.body.addSpacing(6)
        self.body.addLayout(nav)
        self.calendar = WeekCalendar()
        self.calendar.entry_clicked.connect(self.edit_entry)
        self.body.addWidget(self.calendar)

        # subjects and projects
        self.section("Subjects & projects")
        self.cards_host = QWidget()
        self.grid = QGridLayout(self.cards_host)
        self.grid.setContentsMargins(0, 4, 0, 0)
        self.grid.setSpacing(14)
        for c in range(CARD_COLUMNS):
            self.grid.setColumnStretch(c, 1)
        self.add_card = AddCard()
        self.add_card.clicked.connect(self.add_subject)
        self.body.addWidget(self.cards_host)

        # the week's entries, listed
        self.section("Entries")
        self.entries_host = QWidget()
        self.entries = QVBoxLayout(self.entries_host)
        self.entries.setContentsMargins(0, 0, 0, 0)
        self.entries.setSpacing(4)
        self.body.addWidget(self.entries_host)
        self.live_labels: list = []

        # totals
        self.section("Totals")
        self.periods = Segmented(PERIODS, self.period, "Period")
        self.periods.changed.connect(self._set_period)
        self.body.addWidget(self.periods, 0, Qt.AlignmentFlag.AlignLeft)
        self.totals_summary = label("", "secondary", theme.ui_font(14), wrap=True)
        self.body.addWidget(self.totals_summary)
        self.bars = TotalsBars()
        self.body.addWidget(self.bars)
        self.section("While a timer runs")
        from PySide6.QtWidgets import QCheckBox
        self.preferences = preferences
        self.monitoring_check = QCheckBox("Run eye monitoring while a timer runs (stopping the timer ends the session)")
        self.monitoring_check.setChecked(getattr(preferences, "time_log_monitoring", True))
        self.monitoring_check.toggled.connect(self._set_monitoring)
        self.body.addWidget(self.monitoring_check)
        self.body.addWidget(paragraph(
            "Subjects are drawn as circles and projects as stars. An entry that runs past midnight counts on "
            "both days. The very first time, eye monitoring starts with a short calibration on the Study page.",
            13, secondary=True))
        self.finish()

        self._ticks = 0
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.tick)
        self.ticker.start(1000)
        self._was_running: bool | None = None  # None: not shown yet (a timer left running at launch starts nothing)
        self.refresh()
        self._was_running = self.log.running() is not None

    # ------------------------------------------------------------ helpers
    def _set_monitoring(self, on: bool) -> None:
        if self.preferences is not None:
            self.preferences.time_log_monitoring = on
            self.preferences.save()
    def now(self) -> float:
        return time.time()

    @property
    def log(self):
        return self.store.log

    def _change(self, action):
        try:
            result = self.store.change(action)
        except ValueError as error:
            self.error_label.setText(str(error))
            return None
        self.refresh()
        return result

    def _dialog(self, dialog: QDialog) -> bool:
        """Show a dialog and return whether it was accepted (replaced in tests)."""
        return dialog.exec() == QDialog.DialogCode.Accepted

    # ------------------------------------------------------------ actions
    def toggle(self, sid: str) -> None:
        self._change(lambda log: log.toggle(sid, self.now()))

    def _main_action(self) -> None:
        if self.log.running() is not None:
            self._change(lambda log: log.stop(self.now()))
            return
        sid = self.selected if self.log.known(self.selected or "") else ""  # starts at once, like Toggl's ▶
        note = self.note.text()
        self._change(lambda log: log.start(sid, self.now(), note))

    def open_colours(self, sid: str) -> ColourPopup | None:
        subject, card = self.log.subject(sid), self.cards.get(sid)
        if subject is None or card is None:
            return None
        popup = ColourPopup(subject.colour, self)
        popup.chosen.connect(lambda key: self._change(lambda log: log.edit_subject(sid, colour=key)))
        popup.open_below(card.mark)
        self.colour_popup = popup
        return popup

    def open_picker(self) -> SubjectPicker:
        self.picker = SubjectPicker(self.log, self.selected or "", self)
        self.picker.chosen.connect(self.choose_subject)
        self.picker.create.connect(self.create_and_choose)
        self.picker.open_below(self.chip)
        return self.picker

    def _create_subject(self, kind: str, name: str):
        colour = COLOURS[len(self.log.subjects) % len(COLOURS)]
        return self.store.change(lambda log: log.add_subject(name, kind, colour))

    def create_and_choose(self, kind: str, name: str) -> None:
        """Made from the picker: no window, the next colour, and chosen at once."""
        colour = COLOURS[len(self.log.subjects) % len(COLOURS)]
        subject = self.store.change(lambda log: log.add_subject(name, kind, colour))
        if subject is not None:
            self.choose_subject(subject.id)
        else:
            self.refresh()

    def choose_subject(self, sid: str) -> None:
        """Chosen in the picker. While a timer runs the choice goes to the running entry (as in Toggl)."""
        self.selected = sid
        current = self.log.running()
        if current is not None and current.subject_id != sid:
            self._change(lambda log: log.edit_entry(current.id, sid=sid))
        else:
            self.refresh()

    def _enter_in_note(self) -> None:
        """Return in "What are you working on?" starts the timer (as in Toggl); while it runs it just saves."""
        if self.log.running() is None:
            self._main_action()

    def _note_changed(self) -> None:
        current = self.log.running()
        if current is not None and self.note.text().strip() != current.note:
            text = self.note.text()
            self._change(lambda log: log.edit_entry(current.id, note=text))

    def add_subject(self):
        """Ask for a new subject or project; returns it (and makes it the timer's choice), or None."""
        dialog = SubjectDialog(colour=COLOURS[len(self.log.subjects) % len(COLOURS)], parent=self)
        if not self._dialog(dialog):
            return None
        name, kind, colour = dialog.values()
        subject = self.store.change(lambda log: log.add_subject(name, kind, colour))
        if subject is not None:
            self.selected = subject.id
        self.refresh()
        return subject

    def edit_subject(self, sid: str) -> None:
        subject = self.log.subject(sid)
        if subject is None:
            return
        count = sum(1 for e in self.log.entries if e.subject_id == sid)
        dialog = SubjectDialog(subject, count, parent=self)
        if not self._dialog(dialog):
            return
        if dialog.deleted:
            self._change(lambda log: log.remove_subject(sid))
        else:
            name, kind, colour = dialog.values()
            self._change(lambda log: log.edit_subject(sid, name, kind, colour))

    def add_entry(self, sid: str | None = None) -> None:
        dialog = EntryDialog(self.log, subject_id=sid or self.selected, create=self._create_subject,
                             now=self.now(), parent=self)
        if self._dialog(dialog):
            s, start, end, note = dialog.values()
            self._change(lambda log: log.add_entry(s, start, end, note))

    def edit_entry(self, eid: str) -> None:
        entry = self.log.entry(eid)
        if entry is None:
            return
        dialog = EntryDialog(self.log, entry, now=self.now(), parent=self, create=self._create_subject)
        if not self._dialog(dialog):
            return
        if dialog.deleted:
            self._change(lambda log: log.remove_entry(eid))
            return
        s, start, end, note = dialog.values()
        self._change(lambda log: log.edit_entry(eid, s, start, end, note))
        if dialog.continued:  # ▶ on a logged entry: a new timer with its subject and note, as in Toggl
            self._change(lambda log: log.start(s, self.now(), note))

    def _move_week(self, step: int) -> None:
        self.week_offset = 0 if step == 0 else self.week_offset + step
        self.refresh()

    def _set_period(self, period: str) -> None:
        self.period = period
        self.refresh()

    # ------------------------------------------------------------ display
    def tick(self) -> None:
        self._ticks += 1
        current = self.log.running()
        if current is None:
            self.status_text.emit("")
            return
        if self._ticks % 30 == 0 and self.isVisible():
            self.refresh()  # totals, calendar block and the "now" line move on
            return
        self._paint_timer()
        card = self.cards.get(current.subject_id)
        if card is not None:
            s = self.log.subject(current.subject_id)
            now = self.now()
            card.show_state(s, self.log.total(*period_bounds("today", date.fromtimestamp(now)), now, s.id),
                            self.log.total(*period_bounds("week", date.fromtimestamp(now)), now, s.id),
                            current.seconds(now))
        for widget in self.live_labels:
            widget.setText(clock(current.seconds(self.now())))
        if self._ticks % 5 == 0 and self.week_offset == 0:
            now = self.now()
            self.calendar.show_week(self.log, week_monday(date.fromtimestamp(now)), now)

    def _paint_timer(self) -> None:
        current, now = self.log.running(), self.now()
        live = current is not None
        subject = self.log.subject(current.subject_id if live else self.selected or "")  # None: no project
        self.chip.show_subject(subject)
        self.clock_label.setText(clock(current.seconds(now)) if live else "0:00:00")
        self.clock_label.setStyleSheet(f"color: {theme.VERMILION if live else theme.GRAPHITE};")
        self.main_button.set_running(live)
        self.main_button.setEnabled(not self.store.read_only)
        self.status_text.emit(clock(current.seconds(now)) if live else "")
        if self._was_running is not None and live != self._was_running:
            self._was_running = live
            self.running_changed.emit(live)

    def refresh(self) -> None:
        log, now = self.log, self.now()
        today = date.fromtimestamp(now)
        self.error_label.setText(self.store.error)
        self.error_label.setVisible(bool(self.store.error))
        current = log.running()
        subjects = log.visible_subjects()

        # timer bar
        if current is not None:
            self.selected = current.subject_id
        elif not any(s.id == self.selected for s in subjects):
            self.selected = ""  # no project
        if current is not None and not self.note.hasFocus():
            self.note.setText(current.note)
        self._paint_timer()

        # cards
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None and item.widget() is not self.add_card:
                item.widget().deleteLater()
        self.cards = {}
        day_a, day_b = period_bounds("today", today)
        week_a, week_b = period_bounds("week", today)
        for n, s in enumerate(subjects):
            card = SubjectCard(s)
            card.colour_clicked.connect(self.open_colours)
            card.edit.connect(self.edit_subject)
            card.mark.setEnabled(not self.store.read_only)
            live = current.seconds(now) if current is not None and current.subject_id == s.id else None
            card.show_state(s, log.total(day_a, day_b, now, s.id), log.total(week_a, week_b, now, s.id), live)
            self.cards[s.id] = card
            self.grid.addWidget(card, *divmod(n, CARD_COLUMNS))
        self.grid.addWidget(self.add_card, *divmod(len(subjects), CARD_COLUMNS))
        self.add_card.setEnabled(not self.store.read_only)

        # the week
        monday = week_monday(today) + timedelta(days=7 * self.week_offset)
        sunday = monday + timedelta(days=6)
        self.week_title.setText(f"{monday.day} {monday:%b} to {sunday.day} {sunday:%b %Y}  ·  W{monday.isocalendar()[1]}")
        a, b = day_start(monday), day_start(monday + timedelta(days=7))
        self.week_total.setText(f"Logged {short(log.total(a, b, now))}")
        self.this_button.setEnabled(self.week_offset != 0)
        self.calendar.show_week(log, monday, now)
        self._fill_entries(monday, now)

        # totals
        rows = log.totals_by_subject(*period_bounds(self.period, today), now)
        total = sum(sec for _, sec in rows)
        if rows:
            subjects_time = sum(sec for s, sec in rows if s.kind == "subject")
            self.totals_summary.setText(f"{format_duration(total)} in total · courses {format_duration(subjects_time)}"
                                        f" · projects {format_duration(total - subjects_time)}")
        else:
            self.totals_summary.setText("Nothing tracked in this period yet.")
        self.bars.show_rows(rows)
        self.fit_height()

    def _fill_entries(self, monday: date, now: float) -> None:
        while self.entries.count():
            item = self.entries.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                _clear(item.layout())
        self.live_labels = []
        log, any_entry = self.log, False
        for i in reversed(range(7)):
            day = monday + timedelta(days=i)
            a, b = day_start(day), day_start(day + timedelta(days=1))
            items = sorted((e for e in log.entries if a <= e.start < b), key=lambda e: -e.start)
            if not items:
                continue
            any_entry = True
            head = QHBoxLayout()
            name = "Today" if day == date.fromtimestamp(now) else f"{day:%A} {day.day} {day:%B}"
            head.addWidget(label(name, font=theme.ui_font(15, QFont.Weight.Bold)))
            head.addStretch(1)
            head.addWidget(label(short(sum(e.seconds(now) for e in items)), "secondary", theme.number_font(13)))
            holder = QWidget()
            holder.setLayout(head)
            self.entries.addSpacing(10)
            self.entries.addWidget(holder)
            for e in items:
                self.entries.addWidget(self._entry_row(e, now))
        if not any_entry:
            self.entries.addWidget(label("No entries this week yet. Press Start on a subject, or add a past entry.",
                                         "secondary", theme.ui_font(14), wrap=True))

    def _entry_row(self, e, now: float) -> QWidget:
        s = self.log.shown_subject(e.subject_id)
        row = QPushButton()
        row.setProperty("kind", "row")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row.setAccessibleName(f"{s.name}, {hhmm(e.start)} to {'now' if e.end is None else hhmm(e.end)}. Edit")
        row.clicked.connect(lambda _=False, eid=e.id: self.edit_entry(eid))
        line = QHBoxLayout(row)
        line.setContentsMargins(8, 0, 8, 0)
        line.setSpacing(12)
        line.addWidget(Mark(s.kind, s.colour, 20))
        line.addWidget(label(s.name, font=theme.ui_font(14, QFont.Weight.DemiBold)))
        note = label(e.note, "secondary", theme.ui_font(14))
        note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        line.addWidget(note, 1)
        line.addWidget(label(f"{hhmm(e.start)} to {'now' if e.end is None else hhmm(e.end)}", "secondary",
                             theme.number_font(13)))
        duration = label(clock(e.seconds(now)) if e.end is None else short(e.seconds(now)), font=theme.number_font(13))
        duration.setMinimumWidth(78)
        duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if e.end is None:
            duration.setStyleSheet(f"color: {theme.VERMILION};")
            self.live_labels.append(duration)
        line.addWidget(duration)
        for child in row.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return row


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()  # gone at once, not only when Qt gets round to deleting it
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())
