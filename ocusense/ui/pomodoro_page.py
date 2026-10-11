"""Pomodoro: focused rounds with short breaks, in the OcuSense (Miró) style.

The timer (core/pomodoro.py) runs here all the time, also while another page is
shown; the dial only animates while it is visible. Choices are remembered in
preferences.json. When a phase ends the page emits `phase_ended`; the window turns
that into a Mac notification if OcuSense isn't in view. Independent of eye
monitoring: starting or pausing one never starts or pauses the other.
"""

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ocusense.core.pomodoro import (
    FOCUS, IDLE, LIMITS, LONG_BREAK, PAUSED, PHASE_NAMES, PRESETS, RUNNING, SHORT_BREAK, PomodoroSettings, PomodoroTimer,
)
from ocusense.core.stats import format_duration
from ocusense.system import NOTIFICATION_START

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph
from .widgets.pomodoro_dial import PomodoroDial
from .widgets.segmented import Segmented


def system_reduce_motion() -> bool:
    """The system's reduce-motion setting (macOS Reduce motion, Windows Animation effects off)."""
    try:
        from ocusense.system import reduce_motion
        return reduce_motion()
    except Exception:
        return False


def clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _button(text: str, kind: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


class PomodoroPage(Page):
    phase_ended = Signal(object)  # core.pomodoro.PhaseEnded
    status_text = Signal(str)  # short text for the sidebar, e.g. "18:42" or "paused" ("" when idle)
    state_changed = Signal(str, str)  # (phase, state) whenever either changes — the window links monitoring to it

    def __init__(self, preferences, parent=None):
        super().__init__("Focus", "Pomodoro",
                         "Study in focused rounds with short breaks in between. Change the lengths below — your "
                         "choices are remembered.", parent)
        self.preferences = preferences
        self.timer = PomodoroTimer(preferences.pomodoro())
        self.reduce_motion = system_reduce_motion()

        self.dial = PomodoroDial()
        self.body.addWidget(self.dial)
        controls = QHBoxLayout()
        controls.addStretch(1)
        self.main_button = _button("Start", "primary")
        self.main_button.setMinimumWidth(130)
        self.main_button.clicked.connect(self._main_action)
        self.skip_button = _button("Skip", "quiet")
        self.skip_button.setToolTip("End this phase now and go to the next one")
        self.skip_button.clicked.connect(self._skip)
        self.reset_button = _button("Reset", "quiet")
        self.reset_button.setToolTip("Back to the start of a focus round")
        self.reset_button.clicked.connect(self._reset)
        for widget in (self.main_button, self.skip_button, self.reset_button):
            controls.addWidget(widget)
        controls.addStretch(1)
        self.body.addLayout(controls)
        self.round_label = label("", "secondary", theme.ui_font(15), wrap=True)
        self.round_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(self.round_label)
        self.today_label = label("", "secondary", theme.ui_font(13), wrap=True)
        self.today_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(self.today_label)

        # Presets and settings
        self.section("Rhythm")
        options = [(key, name) for key, (name, _) in PRESETS.items()] + [("custom", "Custom")]
        self.presets = Segmented(options, self._preset_key(), "Pomodoro preset")
        self.presets.changed.connect(self._choose_preset)
        self.body.addWidget(self.presets, 0, Qt.AlignmentFlag.AlignLeft)
        grid = QWidget()
        rows = QVBoxLayout(grid)
        rows.setContentsMargins(0, 8, 0, 0)
        rows.setSpacing(10)
        self.spins: dict[str, QSpinBox] = {}
        for name, text, suffix in (("focus_minutes", "Focus", " min"), ("short_break_minutes", "Short break", " min"),
                                   ("long_break_minutes", "Long break", " min"),
                                   ("rounds_before_long_break", "Long break after", " focus rounds")):
            row = QHBoxLayout()
            title = label(text, font=theme.ui_font(15, QFont.Weight.DemiBold))
            title.setMinimumWidth(150)
            row.addWidget(title)
            spin = QSpinBox()
            low, high = LIMITS[name]
            spin.setRange(low, high)
            spin.setSuffix(suffix)
            spin.setValue(getattr(self.timer.settings, name))
            spin.setAccessibleName(text)
            spin.setMinimumWidth(170)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spin.valueChanged.connect(self._settings_changed)
            self.spins[name] = spin
            minus, plus = _button("−", "step"), _button("+", "step")
            minus.setAccessibleName(f"{text}: less")
            plus.setAccessibleName(f"{text}: more")
            minus.clicked.connect(spin.stepDown)
            plus.clicked.connect(spin.stepUp)
            row.addWidget(minus)
            row.addWidget(spin)
            row.addWidget(plus)
            row.addStretch(1)
            rows.addLayout(row)
        self.body.addWidget(grid)

        self.section("While it runs")
        self.checks: dict[str, QCheckBox] = {}
        for name, text in (("pomodoro_monitoring", "Run eye monitoring in focus rounds and pause it in breaks"),
                           ("auto_start_breaks", "Start breaks automatically"),
                           ("auto_start_focus", "Start the next focus round automatically"),
                           ("pomodoro_notify", f"{NOTIFICATION_START} when a focus round or a break ends"),
                           ("pomodoro_sound", "A short sound when a phase ends"),
                           ("animations", "Animations")):
            box = QCheckBox(text)
            box.setChecked(getattr(preferences, name))
            box.toggled.connect(lambda on, n=name: self._toggle(n, on))
            self.checks[name] = box
            self.body.addWidget(box)
        self.motion_note = paragraph("", 13, secondary=True)
        self.body.addWidget(self.motion_note)
        self.body.addWidget(paragraph(
            "The timer keeps running while you look at other pages. With the first option on, starting a focus "
            "round starts eye monitoring, and breaks turn the camera off so your eyes can rest.", 13,
            secondary=True))
        self.finish()

        self._last_second = None
        self._last_state = (self.timer.phase, self.timer.state)
        self.ticker = QTimer(self)  # drives the timer even while another page is shown
        self.ticker.timeout.connect(self.tick)
        self.ticker.start(250)
        self._apply_animations()
        self.refresh()

    # ------------------------------------------------------------ actions
    def now(self) -> float:
        return time.monotonic()

    def _main_action(self) -> None:
        if self.timer.state == RUNNING:
            self.timer.pause(self.now())
        elif self.timer.state == PAUSED:
            self.timer.resume(self.now())
        else:
            self.timer.start(self.now())
        self.refresh()

    def _skip(self) -> None:
        self.phase_ended.emit(self.timer.skip(self.now()))
        self.refresh()

    def _reset(self) -> None:
        self.timer.reset()
        self.refresh()

    def tick(self) -> None:
        ended = self.timer.tick(self.now())
        if ended is not None:
            self.phase_ended.emit(ended)
        second = int(self.timer.remaining(self.now()))
        if ended is not None or second != self._last_second:
            self._last_second = second
            self.refresh()

    # ------------------------------------------------------------ settings
    def _preset_key(self) -> str:
        current = self.timer.settings
        for key, (_, preset) in PRESETS.items():
            if (preset.focus_minutes, preset.short_break_minutes, preset.long_break_minutes,
                    preset.rounds_before_long_break) == (current.focus_minutes, current.short_break_minutes,
                                                         current.long_break_minutes, current.rounds_before_long_break):
                return key
        return "custom"

    def _choose_preset(self, key: str) -> None:
        if key == "custom":
            return
        preset = PRESETS[key][1]
        for name, spin in self.spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(preset, name))
            spin.blockSignals(False)
        self._settings_changed()

    def _settings_changed(self, *_args) -> None:
        values = {name: spin.value() for name, spin in self.spins.items()}
        settings = PomodoroSettings(**values, auto_start_breaks=self.preferences.auto_start_breaks,
                                    auto_start_focus=self.preferences.auto_start_focus)
        self.timer.apply_settings(settings, self.now())
        self.preferences.set_pomodoro(self.timer.settings)
        self.preferences.save()
        self.presets.set_current(self._preset_key())
        self.refresh()

    def _toggle(self, name: str, on: bool) -> None:
        setattr(self.preferences, name, on)
        if name in ("auto_start_breaks", "auto_start_focus"):
            self._settings_changed()
            return
        self.preferences.save()
        if name == "animations":
            self._apply_animations()

    def _apply_animations(self) -> None:
        on = self.preferences.animations and not self.reduce_motion
        self.dial.set_animations(on)
        self.motion_note.setText("Animations are off because “Reduce motion” is on in macOS System Settings › "
                                 "Accessibility." if self.reduce_motion else "")
        self.motion_note.setVisible(self.reduce_motion)

    # ------------------------------------------------------------ display
    def refresh(self) -> None:
        t, now = self.timer, self.now()
        remaining = t.remaining(now)
        n = t.settings.rounds_before_long_break
        done_in_cycle = min(n, t.round_in_cycle - (1 if t.phase == FOCUS else 0))
        self.dial.show_state(t.phase, t.state == RUNNING, t.state == PAUSED, t.progress(now), clock(remaining),
                             n, done_in_cycle)
        self.main_button.setText({RUNNING: "Pause", PAUSED: "Resume"}.get(t.state, "Start"))
        if t.phase == FOCUS:
            nxt = LONG_BREAK if t.round_in_cycle >= n else SHORT_BREAK
            text = (f"Focus round {t.round_in_cycle} of {n} · then a {PHASE_NAMES[nxt].lower()} "
                    f"({t.settings.minutes(nxt)} min)")
        else:
            text = f"{PHASE_NAMES[t.phase]} · then focus ({t.settings.focus_minutes} min)"
        self.round_label.setText(text)
        spent = t.focus_time(now)
        rounds = t.completed_focus
        self.today_label.setText(
            f"Since OcuSense opened: {rounds} focus round{'s' if rounds != 1 else ''} completed · "
            f"{format_duration(spent) if spent >= 1 else '0 s'} of focus")
        self.status_text.emit("" if t.state == IDLE else "paused" if t.state == PAUSED else clock(remaining))
        if (t.phase, t.state) != self._last_state:
            self._last_state = (t.phase, t.state)
            self.state_changed.emit(t.phase, t.state)
