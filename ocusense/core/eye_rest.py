"""The 20-20-20 eye-rest reminder: every 20 minutes of screen time, look about 6 m (20 ft) away for 20 s.

Counts only time while eye monitoring runs (you're at the screen). A pause of at
least REST_SECONDS (for example a Pomodoro break) already rested the eyes, so the
count starts over. Pure Python: times are time.monotonic() seconds from the caller.
"""

REST_SECONDS = 20.0
INTERVAL_MINUTES = 20  # the "20" of 20-20-20


class EyeRestTimer:
    def __init__(self, interval_minutes: float = INTERVAL_MINUTES):
        self.interval = interval_minutes * 60.0
        self.screen_seconds = 0.0  # monitored time since the last rest
        self._last: float | None = None
        self._away_since: float | None = None

    def update(self, now: float, monitoring: bool) -> bool:
        """Call regularly. Returns True when it is time for an eye rest (then the count starts over)."""
        if monitoring:
            if self._away_since is not None and now - self._away_since >= REST_SECONDS:
                self.screen_seconds = 0.0  # a long enough pause was a rest
            self._away_since = None
            if self._last is not None:
                self.screen_seconds += max(0.0, min(now - self._last, 5.0))  # a stalled clock never adds minutes
            self._last = now
            if self.screen_seconds >= self.interval:
                self.screen_seconds = 0.0
                return True
            return False
        if self._away_since is None:
            self._away_since = now
        self._last = None
        return False

    def rested(self) -> None:
        """The person did the 20-second rest (or skipped it): start counting again."""
        self.screen_seconds = 0.0
