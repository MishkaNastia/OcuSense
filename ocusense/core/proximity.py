"""The distance reminder: notices when someone has moved much closer to the screen.

Input per frame: closeness = the face's size now ÷ its size during calibration
(eye-centre distance ÷ frame width, see eye_metrics.py), or None when the frame
isn't reliable. Apparent size grows as 1 / distance, so 1.6 means roughly 60 % of
the calibration distance (about an arm's length).

Rules (values in config.py):
* remind when closeness stays at or above PROXIMITY_WARN_RATIO for
  PROXIMITY_SUSTAIN_SECONDS — a quick lean forward doesn't count;
* the person counts as "moved back" only below PROXIMITY_CLEAR_RATIO (two levels,
  like the blink detector, so the reminder doesn't flicker on and off);
* at most one reminder every `cooldown_seconds` (5 s to 10 minutes, chosen in
  Settings): still too close when that time has passed → reminded again.

It measures size, not centimetres, and never affects blink detection.
"""

from ocusense.config import (
    PROXIMITY_CLEAR_RATIO, PROXIMITY_COOLDOWN_SECONDS, PROXIMITY_SUSTAIN_SECONDS, PROXIMITY_WARN_RATIO,
)


class ProximityMonitor:
    def __init__(self, warn_ratio: float = PROXIMITY_WARN_RATIO, clear_ratio: float = PROXIMITY_CLEAR_RATIO,
                 sustain_seconds: float = PROXIMITY_SUSTAIN_SECONDS,
                 cooldown_seconds: float = PROXIMITY_COOLDOWN_SECONDS):
        if clear_ratio >= warn_ratio:
            raise ValueError("clear_ratio must be lower than warn_ratio")
        self.warn_ratio, self.clear_ratio = warn_ratio, clear_ratio
        self.sustain_seconds, self.cooldown_seconds = sustain_seconds, cooldown_seconds
        self.too_close = False  # a reminder is active until the person moves back
        self._close_since: float | None = None
        self._last_reminder: float | None = None

    def update(self, now: float, closeness: float | None) -> bool:
        """Feed one frame (time.monotonic(), closeness or None). Returns True when a reminder should be shown."""
        if closeness is None:
            self._close_since = None  # unreliable frame: start counting again
            return False
        if closeness < self.clear_ratio:
            self._close_since = None
            self.too_close = False
            return False
        if closeness < self.warn_ratio:
            self._close_since = None  # in between: not close enough to count, not far enough to clear
            return False
        if self._close_since is None:
            self._close_since = now
        if now - self._close_since < self.sustain_seconds:
            return False
        if self._last_reminder is not None and now - self._last_reminder < self.cooldown_seconds:
            return False
        self.too_close = True
        self._last_reminder = now
        return True

    def reset(self) -> None:
        """Monitoring paused or stopped: forget the current closeness, keep the cooldown."""
        self._close_since = None
        self.too_close = False
