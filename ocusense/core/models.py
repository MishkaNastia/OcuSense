"""Shared data structures for measurements and session summaries.

Units: all durations are in seconds. Display code converts (e.g. to ms).
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from ocusense.config import MIN_TRACKED_PER_MINUTE


@dataclass
class MinuteBin:
    start: datetime
    tracked: float = 0.0
    blinks: int = 0
    closures: list = field(default_factory=list)  # seconds below the closing threshold, per blink
    closed: float = 0.0  # seconds below the closing threshold

    def value(self, metric: str) -> float | None:
        """Blink rate (blinks/min), median closure (seconds) or time closed (%) for this minute."""
        if metric == "closure":
            return statistics.median(self.closures) if self.closures else None
        if self.tracked < MIN_TRACKED_PER_MINUTE:
            return None
        if metric == "rate":
            return self.blinks / (self.tracked / 60)
        return self.closed / self.tracked * 100  # "closed"


@dataclass
class SessionSummary:
    started_at: datetime
    ended_at: datetime
    study_seconds: float  # time the session was running (pauses excluded)
    tracked_seconds: float  # time with reliable tracking
    blinks: int
    closure_seconds: list
    closed_seconds: float
    segments: list  # [(start, end)] running periods
    untracked: list  # [(start, end)] periods without tracking
    minutes: list  # [MinuteBin]
    in_progress: bool = False

    @property
    def coverage(self) -> float | None:
        return self.tracked_seconds / self.study_seconds if self.study_seconds else None

    def metric(self, name: str) -> float | None:
        """Blink rate (blinks/min), median closure (seconds) or time closed (%), or None without data."""
        if name == "closure":
            return statistics.median(self.closure_seconds) if self.closure_seconds else None
        if self.tracked_seconds < 1:
            return None
        if name == "rate":
            return self.blinks / (self.tracked_seconds / 60)
        return self.closed_seconds / self.tracked_seconds * 100
