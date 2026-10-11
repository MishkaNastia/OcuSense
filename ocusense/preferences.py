"""Choices from Settings that OcuSense remembers between launches.

    <OcuSense data folder>/preferences.json   (see ocusense/system.py: on a Mac
    ~/Library/Application Support/OcuSense, on Windows %LOCALAPPDATA%\\OcuSense)

Reminder choices, the Pomodoro settings and whether posture monitoring is on. Unknown or
invalid values fall back to the defaults, so a damaged file never stops the app.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from ocusense.config import PROXIMITY_COOLDOWN_CHOICES, PROXIMITY_COOLDOWN_SECONDS
from ocusense.core.pomodoro import LIMITS, PomodoroSettings
from ocusense.system import user_data_dir


def default_path() -> Path:
    """OCUSENSE_PREFERENCES_FILE overrides it (e.g. in tests)."""
    override = os.environ.get("OCUSENSE_PREFERENCES_FILE")
    return Path(override) if override else user_data_dir() / "preferences.json"


DISPLAY_NAME_MAX = 40


def clean_display_name(text: str) -> str:
    """A tidy local display name: no control characters, single spaces, at most 40 characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable())
    return " ".join(text.split())[:DISPLAY_NAME_MAX].strip()


@dataclass
class Preferences:
    distance_reminder: bool = True
    distance_reminder_interval: float = PROXIMITY_COOLDOWN_SECONDS  # seconds, one of PROXIMITY_COOLDOWN_CHOICES
    # Pomodoro
    focus_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    rounds_before_long_break: int = 4
    auto_start_breaks: bool = True
    auto_start_focus: bool = False
    pomodoro_notify: bool = True  # a Mac notification when a phase ends (while OcuSense isn't in view)
    pomodoro_sound: bool = False
    animations: bool = True  # also off when macOS "Reduce motion" is on
    pomodoro_monitoring: bool = True  # eye monitoring runs in focus rounds and pauses in breaks
    time_log_monitoring: bool = True  # eye monitoring runs while a time-log timer runs
    # 20-20-20 eye rest
    eye_rest: bool = False  # off unless switched on in Settings › Reminders
    lighting_check: bool = False  # off unless switched on in Settings › Reminders
    # Games
    garden_breaks: int = 0
    garden_water: int = 0
    morse_dash_ms: int = 450  # Blink Code: closures at least this long are dashes
    morse_high_score: int = 0
    runner_high_score: int = 0  # EyeGame
    # Your gallery
    display_name: str = ""  # optional local name for "<name>’s gallery" when no account name is available
    # Posture
    posture_monitoring: bool = False  # off until ticked in Settings › Monitoring

    def pomodoro(self) -> PomodoroSettings:
        return PomodoroSettings(self.focus_minutes, self.short_break_minutes, self.long_break_minutes,
                                self.rounds_before_long_break, self.auto_start_breaks, self.auto_start_focus)

    def set_pomodoro(self, s: PomodoroSettings) -> None:
        s = s.clamped()
        self.focus_minutes, self.short_break_minutes = s.focus_minutes, s.short_break_minutes
        self.long_break_minutes, self.rounds_before_long_break = s.long_break_minutes, s.rounds_before_long_break
        self.auto_start_breaks, self.auto_start_focus = s.auto_start_breaks, s.auto_start_focus

    @classmethod
    def load(cls, path: Path | None = None) -> "Preferences":
        prefs = cls()
        try:
            values = json.loads((path or default_path()).read_text())
        except (OSError, ValueError):
            return prefs  # no file yet, or unreadable: defaults
        if isinstance(values.get("distance_reminder"), bool):
            prefs.distance_reminder = values["distance_reminder"]
        if isinstance(values.get("posture_monitoring"), bool):
            prefs.posture_monitoring = values["posture_monitoring"]
        if values.get("distance_reminder_interval") in PROXIMITY_COOLDOWN_CHOICES:
            prefs.distance_reminder_interval = float(values["distance_reminder_interval"])
        for name, (low, high) in LIMITS.items():
            value = values.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
                setattr(prefs, name, value)
        for name in ("auto_start_breaks", "auto_start_focus", "pomodoro_notify", "pomodoro_sound", "animations",
                     "pomodoro_monitoring", "time_log_monitoring", "eye_rest", "lighting_check"):
            if isinstance(values.get(name), bool):
                setattr(prefs, name, values[name])
        for name in ("garden_breaks", "garden_water"):
            value = values.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(prefs, name, value)
        dash = values.get("morse_dash_ms")
        if isinstance(dash, int) and not isinstance(dash, bool) and 250 <= dash <= 900:
            prefs.morse_dash_ms = dash
        best = values.get("morse_high_score")
        if isinstance(best, int) and not isinstance(best, bool) and best >= 0:
            prefs.morse_high_score = best
        if isinstance(values.get("display_name"), str):
            prefs.display_name = clean_display_name(values["display_name"])
        best = values.get("runner_high_score")
        if isinstance(best, int) and not isinstance(best, bool) and best >= 0:
            prefs.runner_high_score = best
        return prefs

    def save(self, path: Path | None = None) -> bool:
        target = path or default_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(self), indent=2) + "\n")
            temporary.replace(target)
        except OSError:
            return False  # not critical: the choice still applies until OcuSense quits
        return True
