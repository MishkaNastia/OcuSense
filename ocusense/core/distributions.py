"""Blink distributions: descriptive statistics of one calibration segment.

The same DistributionBuilder is fed live (by SessionRecorder) and offline (by
core/replay.py from saved recordings), so both use one set of definitions. It
consumes the (FrameObservation, Step) pairs that measurements.MeasurementTracker
already produces and never changes how blinks are detected.

Definitions (times in seconds; openness as fractions, 1 = calibrated open):

* Valid segment: a run of valid frames with no gap longer than MAX_FRAME_GAP.
  An invalid frame (face not tracked, unreliable, not calibrated), a longer gap,
  a pause or the end of the data ends the segment.
* Closure event: the detector's bilateral closing → reopening interval (see
  measurements.py). Completed events have a duration; an event that started but
  was cut off by the end of its segment is "interrupted": excluded, but counted.
* Time between blinks: onset-to-onset time between consecutive completed events
  inside the same valid segment. Never across gaps, pauses or recalibration.
* Blink rate windows: non-overlapping 60 s windows from the start of the data.
  Rate = completed blinks / valid minutes inside the window. A window is
  eligible only with at least MIN_VALID_SECONDS_FOR_RATE of valid observation
  (the same coverage rule as the live "last 60 seconds"). A window still in
  progress is not used.
* Personal eye openness: each valid interval (between two valid frames) adds its
  duration to the bin of the openness at the interval's start frame — the same
  convention as "time classified as closed". So the histogram is a share of
  valid observed TIME, not of frames. Values below 0 % and above 100 % are kept
  in their own bins.

Nothing here classifies fatigue or health: these are descriptive distributions.
"""

import math
import statistics
from dataclasses import dataclass, field

from ocusense.config import MIN_VALID_SECONDS_FOR_RATE

from .models import FrameObservation

WINDOW_SECONDS = 60.0


# ------------------------------------------------------------------ binning
@dataclass(frozen=True)
class Binning:
    """Fixed, documented histogram edges, identical for every session so they can be compared.

    Values below `low` go to an underflow bin and values at or above `high` to an
    overflow bin, when those are enabled — nothing is silently dropped.
    """
    key: str
    low: float
    high: float
    width: float
    unit: str
    underflow: bool = False
    overflow: bool = True

    @property
    def edges(self) -> list[float]:
        n = round((self.high - self.low) / self.width)
        return [self.low + i * self.width for i in range(n + 1)]

    def index(self, value: float) -> int:
        """Bin position: 0 is the underflow bin if enabled, then the regular bins, then overflow."""
        offset = 1 if self.underflow else 0
        n = len(self.edges) - 1
        if value < self.low:
            return 0 if self.underflow else offset  # without underflow, clamp into the first bin
        if value >= self.high:
            return offset + n if self.overflow else offset + n - 1
        return offset + min(n - 1, int((value - self.low) // self.width))

    @property
    def size(self) -> int:
        return (1 if self.underflow else 0) + len(self.edges) - 1 + (1 if self.overflow else 0)

    def labels(self) -> list[tuple[float | None, float | None]]:
        """(from, to) for every bin; None marks an open end (underflow / overflow)."""
        e = self.edges
        bins = [(e[i], e[i + 1]) for i in range(len(e) - 1)]
        return ([(None, self.low)] if self.underflow else []) + bins + ([(self.high, None)] if self.overflow else [])


# Widths are kept at or above the timing precision (~33 ms per frame at 30 fps).
CLOSURE_BINS = Binning("closure", 0, 1000, 50, "ms")  # last bin: ≥ 1000 ms (prolonged closures stay visible)
INTERVAL_BINS = Binning("interval", 0, 30, 1, "s")  # last bin: ≥ 30 s
RATE_BINS = Binning("rate", 0, 40, 2, "blinks/min")  # last bin: ≥ 40
OPENNESS_BINS = Binning("openness", 0, 100, 5, "%", underflow=True, overflow=True)  # < 0 % and ≥ 100 %
BINNINGS = {b.key: b for b in (CLOSURE_BINS, INTERVAL_BINS, RATE_BINS, OPENNESS_BINS)}


def histogram(values, binning: Binning, weights=None) -> list[float]:
    counts = [0.0] * binning.size
    for i, value in enumerate(values):
        counts[binning.index(value)] += 1.0 if weights is None else weights[i]
    return counts


def quartiles(values: list[float]) -> tuple[float, float, float] | None:
    """(Q1, median, Q3) using the inclusive method; None without data."""
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0]
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, median, q3


# ------------------------------------------------------------------ results
@dataclass(frozen=True)
class BlinkEvent:
    onset: float  # detector entered the closed state
    end: float  # detector reopened (the blink was counted here)
    segment: int

    @property
    def duration(self) -> float:
        return self.end - self.onset


@dataclass
class WindowStat:
    start: float
    end: float
    valid_seconds: float = 0.0
    blinks: int = 0
    complete: bool = True  # False while a live window is still in progress

    @property
    def eligible(self) -> bool:
        return self.complete and self.valid_seconds >= MIN_VALID_SECONDS_FOR_RATE

    @property
    def rate(self) -> float | None:
        return self.blinks / (self.valid_seconds / 60) if self.eligible and self.valid_seconds > 0 else None


@dataclass
class OpennessHistogram:
    """Seconds of valid observation per openness bin, per eye ("left", "right", "both")."""
    seconds: dict = field(default_factory=lambda: {k: [0.0] * OPENNESS_BINS.size for k in ("left", "right", "both")})
    total: float = 0.0
    lowest: dict = field(default_factory=dict)
    highest: dict = field(default_factory=dict)

    def add(self, eye: str, value: float, seconds: float) -> None:
        percent = value * 100
        self.seconds[eye][OPENNESS_BINS.index(percent)] += seconds
        self.lowest[eye] = min(self.lowest.get(eye, math.inf), percent)
        self.highest[eye] = max(self.highest.get(eye, -math.inf), percent)

    def shares(self, eye: str) -> list[float]:
        """Percentage of valid observed time in each bin."""
        return [s / self.total * 100 if self.total else 0.0 for s in self.seconds[eye]]


@dataclass
class Distributions:
    """A snapshot of everything the four histograms need, for one calibration segment."""
    events: list  # [BlinkEvent], completed closure events
    interrupted: int  # events that started (or completed without timing) but couldn't be timed
    intervals: list  # [(onset_a, onset_b)] within the same valid segment
    windows: list  # [WindowStat]
    openness: OpennessHistogram
    valid_seconds: float
    blinks: int  # completed blinks counted by the detector (same as the live count)
    segments: int  # number of valid segments
    start: float
    end: float

    def closure_ms(self) -> list[float]:
        return [e.duration * 1000 for e in self.events]

    def interval_seconds(self) -> list[float]:
        return [b - a for a, b in self.intervals]

    def eligible_rates(self) -> list[float]:
        return [w.rate for w in self.windows if w.eligible]

    def excluded_windows(self) -> int:
        return sum(1 for w in self.windows if w.complete and not w.eligible)


# ------------------------------------------------------------------ builder
class DistributionBuilder:
    """Accumulates distributions from the measurement stream. Memory: a few numbers per blink and per minute."""

    def __init__(self, start: float):
        self.start = start
        self.events: list[BlinkEvent] = []
        self.intervals: list[tuple[float, float]] = []
        self.interrupted = 0
        self.blinks = 0
        self.valid_seconds = 0.0
        self.openness = OpennessHistogram()
        self._windows: dict[int, WindowStat] = {}
        self._segment = 0
        self._in_segment = False
        self._pending_onset: float | None = None  # closing started, not yet reopened
        self._last_onset: float | None = None  # previous completed event's onset in this segment
        self._last_obs: FrameObservation | None = None  # previous valid frame in this segment
        self._last_t = start

    # -- segment boundaries
    def interrupt(self, t: float | None = None) -> None:
        """End the current valid segment (invalid frame, gap, pause, end of data)."""
        if self._pending_onset is not None:
            self.interrupted += 1
        self._pending_onset = None
        self._last_onset = None
        self._last_obs = None
        if self._in_segment:
            self._segment += 1
        self._in_segment = False
        if t is not None:
            self._last_t = max(self._last_t, t)

    def _window(self, index: int) -> WindowStat:
        if index not in self._windows:
            start = self.start + index * WINDOW_SECONDS
            self._windows[index] = WindowStat(start, start + WINDOW_SECONDS)
        return self._windows[index]

    def _add_valid_time(self, a: float, b: float) -> None:
        """Split a valid interval across the 60 s windows it touches."""
        self.valid_seconds += b - a
        i = int((a - self.start) // WINDOW_SECONDS)
        while a < b:
            window = self._window(i)
            part_end = min(b, window.end)
            window.valid_seconds += part_end - a
            a = part_end
            i += 1

    # -- one frame
    def add(self, obs: FrameObservation, step) -> None:
        """obs: the frame; step: what MeasurementTracker.add(obs) returned for it."""
        self._last_t = max(self._last_t, obs.t)
        if not obs.valid:
            self.interrupt()
            return
        if self._in_segment and step.interval is None:
            self.interrupt()  # a gap longer than MAX_FRAME_GAP: the tracker started over
        self._in_segment = True
        if step.interval is not None:
            start, end, _closed = step.interval
            self._add_valid_time(start, end)
            previous = self._last_obs
            if previous is not None and previous.left_raw is not None and previous.right_raw is not None:
                seconds = end - start
                self.openness.total += seconds
                self.openness.add("left", previous.left_raw, seconds)
                self.openness.add("right", previous.right_raw, seconds)
                self.openness.add("both", (previous.left_raw + previous.right_raw) / 2, seconds)
        if obs.closing_started:
            if self._pending_onset is not None:
                self.interrupted += 1
            self._pending_onset = obs.t
        if obs.blink_completed:
            self.blinks += 1
            self._window(int((obs.t - self.start) // WINDOW_SECONDS)).blinks += 1
            if step.closure is not None and self._pending_onset is not None:
                event = BlinkEvent(self._pending_onset, obs.t, self._segment)
                self.events.append(event)
                if self._last_onset is not None:
                    self.intervals.append((self._last_onset, event.onset))
                self._last_onset = event.onset
            else:
                self.interrupted += 1  # counted as a blink, but its closure couldn't be timed
            self._pending_onset = None
        self._last_obs = obs

    def snapshot(self, now: float | None = None, finished: bool = False) -> Distributions:
        """The distributions so far. Live (finished=False), the window containing `now` is still in progress."""
        end = self._last_t if now is None else max(now, self._last_t)
        windows = []
        last_index = int((end - self.start) // WINDOW_SECONDS)
        for index in range(0, last_index + 1):
            w = self._windows.get(index) or WindowStat(self.start + index * WINDOW_SECONDS,
                                                       self.start + (index + 1) * WINDOW_SECONDS)
            in_progress = not finished and w.end > end
            windows.append(WindowStat(w.start, min(w.end, end) if finished else w.end,
                                      w.valid_seconds, w.blinks, complete=not in_progress))
        interrupted = self.interrupted + (1 if finished and self._pending_onset is not None else 0)
        return Distributions(
            events=list(self.events), interrupted=interrupted, intervals=list(self.intervals),
            windows=windows, openness=self.openness, valid_seconds=self.valid_seconds, blinks=self.blinks,
            segments=self._segment + (1 if self._in_segment else 0), start=self.start, end=end,
        )
