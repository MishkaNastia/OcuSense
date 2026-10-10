"""Choices from Settings that OcuSense remembers between launches.

    ~/Library/Application Support/OcuSense/preferences.json

Only reminder choices for now. Unknown or invalid values fall back to the
defaults, so a damaged file never stops the app.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from ocusense.config import PROXIMITY_COOLDOWN_CHOICES, PROXIMITY_COOLDOWN_SECONDS


def default_path() -> Path:
    """OCUSENSE_PREFERENCES_FILE overrides it (e.g. in tests)."""
    override = os.environ.get("OCUSENSE_PREFERENCES_FILE")
    return Path(override) if override else Path.home() / "Library" / "Application Support" / "OcuSense" / "preferences.json"


@dataclass
class Preferences:
    distance_reminder: bool = True
    distance_reminder_interval: float = PROXIMITY_COOLDOWN_SECONDS  # seconds, one of PROXIMITY_COOLDOWN_CHOICES

    @classmethod
    def load(cls, path: Path | None = None) -> "Preferences":
        prefs = cls()
        try:
            values = json.loads((path or default_path()).read_text())
        except (OSError, ValueError):
            return prefs  # no file yet, or unreadable: defaults
        if isinstance(values.get("distance_reminder"), bool):
            prefs.distance_reminder = values["distance_reminder"]
        if values.get("distance_reminder_interval") in PROXIMITY_COOLDOWN_CHOICES:
            prefs.distance_reminder_interval = float(values["distance_reminder_interval"])
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
