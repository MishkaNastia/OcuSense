"""The lighting check: notices when the room stays dark while you study.

Input per frame: the camera picture's average brightness, 0 (black) to 255 (white),
or None. A bright screen in a dark room is a common source of eye strain, so after a
sustained dark stretch OcuSense suggests turning on a lamp.

Rules, like the distance reminder (two levels so it doesn't flicker):
* remind when brightness stays below DARK_BELOW for SUSTAIN_SECONDS;
* the room counts as lit again only above CLEAR_ABOVE;
* at most one reminder every COOLDOWN_SECONDS.

Webcams adjust their exposure automatically, so this is a rough guide, not a light
meter. Only this one number is used; nothing is saved.
"""

DARK_BELOW = 55.0
CLEAR_ABOVE = 75.0
SUSTAIN_SECONDS = 60.0
COOLDOWN_SECONDS = 30 * 60.0


class LightingMonitor:
    def __init__(self, dark_below: float = DARK_BELOW, clear_above: float = CLEAR_ABOVE,
                 sustain_seconds: float = SUSTAIN_SECONDS, cooldown_seconds: float = COOLDOWN_SECONDS):
        if dark_below >= clear_above:
            raise ValueError("dark_below must be lower than clear_above")
        self.dark_below, self.clear_above = dark_below, clear_above
        self.sustain_seconds, self.cooldown_seconds = sustain_seconds, cooldown_seconds
        self.dark = False  # a reminder is active until the room is lit again
        self._dark_since: float | None = None
        self._last_reminder: float | None = None

    def update(self, now: float, brightness: float | None) -> bool:
        """Feed one frame (time.monotonic(), brightness or None). True when a reminder should be shown."""
        if brightness is None:
            return False  # no picture: keep counting from where we were
        if brightness >= self.clear_above:
            self._dark_since = None
            self.dark = False
            return False
        if brightness >= self.dark_below:
            self._dark_since = None  # in between: neither dark nor clearly lit
            return False
        if self._dark_since is None:
            self._dark_since = now
        if self.dark or now - self._dark_since < self.sustain_seconds:
            return False
        if self._last_reminder is not None and now - self._last_reminder < self.cooldown_seconds:
            return False
        self.dark = True
        self._last_reminder = now
        return True

    def reset(self) -> None:
        """Monitoring paused or stopped: forget the current stretch, keep the cooldown."""
        self._dark_since = None
        self.dark = False
