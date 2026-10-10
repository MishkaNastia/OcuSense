"""Records one study session as numbers (never images) for the Statistics page.

Fed once per processed frame with the "both eyes" personal openness (or None
when measurement is paused) and whether that frame completed a blink.
It does not change how blinks are detected; it only measures around them.
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .blink_counter import CLOSE_BELOW

MAX_FRAME_GAP = 0.5  # seconds; a longer gap between frames is not counted as tracked time
UNTRACKED_MIN = 2.0  # seconds without tracking before it is shown as a gap
MIN_TRACKED_PER_MINUTE = 20.0  # seconds of tracking needed to show a per-minute value


@dataclass
class MinuteBin:
    start: datetime
    tracked: float = 0.0
    blinks: int = 0
    closures: list = field(default_factory=list)  # seconds below the closing threshold, per blink
    closed: float = 0.0  # seconds below the closing threshold

    def value(self, metric):
        if metric == "closure":
            return statistics.median(self.closures) * 1000 if self.closures else None
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
    def coverage(self):
        return self.tracked_seconds / self.study_seconds if self.study_seconds else None

    def metric(self, name):
        """Blink rate (/min), median closure (ms) or time closed (%), or None without data."""
        if name == "closure":
            return statistics.median(self.closure_seconds) * 1000 if self.closure_seconds else None
        if self.tracked_seconds < 1:
            return None
        if name == "rate":
            return self.blinks / (self.tracked_seconds / 60)
        return self.closed_seconds / self.tracked_seconds * 100


class SessionRecorder:
    def __init__(self, now, wall_clock=None):
        """now: time.monotonic() at the start; wall_clock: the matching datetime."""
        self._mono0 = now
        self._wall0 = wall_clock or datetime.now()
        self.running = True
        self.finished = False
        self._segment_start = now
        self._segments = []
        self._untracked = []
        self._untracked_since = None
        self.tracked = 0.0
        self.closed = 0.0
        self.blinks = 0
        self.closures = []
        self._bins = {}
        self._last_t = None
        self._last_value = None
        self._below_since = None
        self._last_span = None

    def wall(self, t):
        return self._wall0 + timedelta(seconds=t - self._mono0)

    def _bin(self, t):
        index = int((t - self._mono0) // 60)
        if index not in self._bins:
            self._bins[index] = MinuteBin(self.wall(self._mono0 + index * 60))
        return self._bins[index]

    def add_frame(self, t, openness, blinked):
        if not self.running:
            return
        if openness is None:
            if self._untracked_since is None:
                self._untracked_since = t
            self._last_t = None
            self._below_since = None
            self._last_span = None
            return
        self._close_untracked(t)
        minute = self._bin(t)
        if self._last_t is not None and t - self._last_t <= MAX_FRAME_GAP:
            dt = t - self._last_t
            self.tracked += dt
            minute.tracked += dt
            if self._last_value < CLOSE_BELOW:
                self.closed += dt
                minute.closed += dt
        if openness < CLOSE_BELOW:
            if self._below_since is None:
                self._below_since = t
        elif self._below_since is not None:
            self._last_span = t - self._below_since
            self._below_since = None
        if blinked:
            self.blinks += 1
            minute.blinks += 1
            if self._last_span is not None:
                self.closures.append(self._last_span)
                minute.closures.append(self._last_span)
                self._last_span = None
        self._last_t = t
        self._last_value = openness

    def _close_untracked(self, t):
        if self._untracked_since is not None:
            if t - self._untracked_since >= UNTRACKED_MIN:
                self._untracked.append((self._untracked_since, t))
            self._untracked_since = None

    def pause(self, t):
        if not self.running:
            return
        self._close_untracked(t)
        self._segments.append((self._segment_start, t))
        self.running = False
        self._last_t = None
        self._below_since = None

    def resume(self, t):
        if self.running:
            return
        self.running = True
        self._segment_start = t

    def summary(self, t):
        """A snapshot; if still running, the open period counts up to t."""
        segments = list(self._segments)
        untracked = list(self._untracked)
        if self.running:
            segments.append((self._segment_start, t))
            if self._untracked_since is not None and t - self._untracked_since >= UNTRACKED_MIN:
                untracked.append((self._untracked_since, t))
        end = segments[-1][1] if segments else t
        return SessionSummary(
            started_at=self._wall0,
            ended_at=self.wall(end),
            study_seconds=sum(b - a for a, b in segments),
            tracked_seconds=self.tracked,
            blinks=self.blinks,
            closure_seconds=list(self.closures),
            closed_seconds=self.closed,
            segments=[(self.wall(a), self.wall(b)) for a, b in segments],
            untracked=[(self.wall(a), self.wall(b)) for a, b in untracked],
            minutes=[self._bins[k] for k in sorted(self._bins)],
            in_progress=not self.finished,
        )

    def finish(self, t):
        self.pause(t)
        self.finished = True
        return self.summary(t)


class SessionStore:
    """Completed sessions.

    For now they live in memory and are forgotten when the app quits. A version
    that saves to a file on this Mac can replace this class later.
    """

    def __init__(self, sessions=None):
        self._sessions = list(sessions or [])

    def add(self, summary):
        self._sessions.append(summary)

    def all(self):
        return sorted(self._sessions, key=lambda s: s.started_at)

    def clear(self):
        self._sessions.clear()
