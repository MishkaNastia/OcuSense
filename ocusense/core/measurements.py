"""Measurement foundation: one implementation of observed time, closures and the rolling window.

Definitions (all times from time.monotonic(), in seconds):

* Valid observation interval: the time between two consecutive VALID frames,
  if they are at most MAX_FRAME_GAP apart. Longer gaps, invalid frames
  (face not tracked, measurement paused) and pauses are missing observation.
* Detector closed time: a valid interval counts as "closed" when the blink
  detector was in its bilateral CLOSED state at the interval's start frame.
  An ongoing closure therefore counts up to the latest valid frame, and a
  long closure counts even if it never produces a blink.
* Closure event: from the frame where the detector went OPEN → CLOSED
  (both-eyes openness fell below CLOSE_BELOW) to the frame where it went
  CLOSED → OPEN (rose above REOPEN_ABOVE) — the same frame that counts the
  blink. This is the threshold-defined closed interval, not the whole blink
  movement. An event is discarded (no duration) if tracking was lost, a
  frame gap occurred, or monitoring paused while it was in progress.
  Durations are only as precise as the frame interval (~33 ms at 30 fps).
"""

import math
import statistics
from collections import deque

from ocusense.config import (
    MAX_FRAME_GAP, MIN_VALID_SECONDS_FOR_RATE, PROCESSING_RATE_WINDOW, ROLLING_WINDOW_SECONDS,
)

from .models import FrameObservation, RollingSnapshot


# --------------------------------------------------------------- display values
def openness_percent(raw: float | None) -> float | None:
    """Displayed personal eye openness for one eye: 0–100 %, or None when unavailable."""
    if raw is None or math.isnan(raw):
        return None
    return min(100.0, max(0.0, raw * 100))


def combined_openness_percent(left_raw: float | None, right_raw: float | None) -> float | None:
    """Mean of the two separately normalised (and clamped) eyes; None unless both are valid."""
    left, right = openness_percent(left_raw), openness_percent(right_raw)
    if left is None or right is None:
        return None
    return (left + right) / 2


# ------------------------------------------------------------ observation steps
class Step:
    """What one observation added: an interval of valid time and/or a finished event."""
    __slots__ = ("interval", "closure", "blink", "t")

    def __init__(self, t: float, interval=None, closure=None, blink=False):
        self.t = t
        self.interval = interval  # (start, end, closed) or None
        self.closure = closure  # completed closure duration (s) or None
        self.blink = blink  # a bilateral blink was completed on this frame


class MeasurementTracker:
    """Turns a stream of FrameObservations into valid intervals and closure events."""

    def __init__(self):
        self._last: FrameObservation | None = None  # last valid frame, if still continuous
        self._closure_start: float | None = None

    def interrupt(self) -> None:
        """Tracking lost or monitoring paused: break continuity and discard any open closure."""
        self._last = None
        self._closure_start = None

    def add(self, obs: FrameObservation) -> Step:
        if not obs.valid:
            self.interrupt()
            return Step(obs.t)
        interval = None
        if self._last is not None:
            dt = obs.t - self._last.t
            if 0 < dt <= MAX_FRAME_GAP:
                interval = (self._last.t, obs.t, self._last.detector_closed)
            else:
                self._closure_start = None  # can't time an event across an unobserved gap
        if obs.closing_started:
            self._closure_start = obs.t
        closure = None
        if obs.blink_completed:
            if self._closure_start is not None:
                closure = obs.t - self._closure_start
            self._closure_start = None
        self._last = obs
        return Step(obs.t, interval, closure, obs.blink_completed)


# --------------------------------------------------------------- rolling window
def _overlap(start: float, end: float, low: float, high: float) -> float:
    return max(0.0, min(end, high) - max(start, low))


class RollingWindow:
    """The last ROLLING_WINDOW_SECONDS of measurements. Memory is bounded: old items are dropped."""

    def __init__(self, now: float, seconds: float = ROLLING_WINDOW_SECONDS,
                 min_valid_seconds: float = MIN_VALID_SECONDS_FOR_RATE):
        self.seconds = seconds
        self.min_valid_seconds = min_valid_seconds
        self._intervals: deque = deque()  # (start, end, closed)
        self._blinks: deque = deque()  # completion times
        self._closures: deque = deque()  # (completion time, duration)
        self._frames: deque = deque()  # times of every processed frame (for processing rate)
        self._running: deque = deque([[now, None]])  # [start, end or None] monitoring periods

    def add(self, step: Step) -> None:
        self._frames.append(step.t)
        if step.interval:
            self._intervals.append(step.interval)
        if step.blink:
            self._blinks.append(step.t)
        if step.closure is not None:
            self._closures.append((step.t, step.closure))
        self._prune(step.t)

    def pause(self, t: float) -> None:
        if self._running and self._running[-1][1] is None:
            self._running[-1][1] = t

    def resume(self, t: float) -> None:
        if not self._running or self._running[-1][1] is not None:
            self._running.append([t, None])

    def _prune(self, now: float) -> None:
        low = now - self.seconds
        while self._intervals and self._intervals[0][1] <= low:
            self._intervals.popleft()
        while self._blinks and self._blinks[0] < low:
            self._blinks.popleft()
        while self._closures and self._closures[0][0] < low:
            self._closures.popleft()
        while self._frames and self._frames[0] < now - max(PROCESSING_RATE_WINDOW, 1.0):
            self._frames.popleft()
        while len(self._running) > 1 and self._running[0][1] is not None and self._running[0][1] <= low:
            self._running.popleft()

    def snapshot(self, now: float) -> RollingSnapshot:
        low = now - self.seconds
        valid = closed = 0.0
        for start, end, is_closed in self._intervals:
            part = _overlap(start, end, low, now)  # intervals crossing the window edge count partly
            valid += part
            if is_closed:
                closed += part
        running = sum(_overlap(start, end if end is not None else now, low, now) for start, end in self._running)
        blinks = sum(1 for t in self._blinks if low <= t <= now)
        durations = [d for t, d in self._closures if low <= t <= now]
        enough = valid >= self.min_valid_seconds
        recent = [t for t in self._frames if t > now - PROCESSING_RATE_WINDOW]
        rate = None
        if len(recent) >= 2 and recent[-1] > recent[0]:
            rate = (len(recent) - 1) / (recent[-1] - recent[0])
        return RollingSnapshot(
            window_seconds=self.seconds,
            running_seconds=running,
            valid_seconds=valid,
            coverage=(valid / running) if running > 0 else None,
            enough_data=enough,
            blinks=blinks,
            blink_rate=(blinks / valid * 60) if enough else None,
            closure_count=len(durations),
            median_closure=statistics.median(durations) if durations else None,
            closed_seconds=closed,
            closed_percent=(closed / valid * 100) if enough else None,
            processing_rate=rate,
        )
