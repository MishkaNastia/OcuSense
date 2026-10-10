"""Records one study session as numbers (never images or landmarks).

Fed once per processed frame with a FrameObservation. It does not change how
blinks are detected; it only measures around the detector, using the single
implementation in measurements.py for both:
  * the rolling "last 60 seconds" window shown live, and
  * small per-minute summaries kept for the session history (Statistics).

A new session (or a recalibration, which starts a new session) gets a new
recorder, so rolling measurements reset. A pause creates a gap but keeps
everything recorded so far.
"""

from datetime import datetime, timedelta

from ocusense.config import UNTRACKED_MIN

from .measurements import MeasurementTracker, RollingWindow
from .models import CalibrationInfo, FrameObservation, MinuteBin, RollingSnapshot, SessionSummary


class SessionRecorder:
    def __init__(self, now: float, wall_clock: datetime | None = None, calibration: CalibrationInfo | None = None):
        """now: time.monotonic() at the start; wall_clock: the matching datetime (identifies the session)."""
        self._mono0 = now
        self._wall0 = wall_clock or datetime.now()
        self.calibration = calibration
        self.running = True
        self.finished = False
        self._segment_start = now
        self._segments = []
        self._untracked = []
        self._untracked_since: float | None = None
        self._last_valid_t: float | None = None
        self.tracked = 0.0
        self.closed = 0.0
        self.blinks = 0
        self.closures = []
        self._bins = {}
        self._tracker = MeasurementTracker()
        self.window = RollingWindow(now)
        self.latest: FrameObservation | None = None  # last frame, for the live openness display

    def wall(self, t: float) -> datetime:
        return self._wall0 + timedelta(seconds=t - self._mono0)

    def _bin(self, t: float) -> MinuteBin:
        index = int((t - self._mono0) // 60)
        if index not in self._bins:
            self._bins[index] = MinuteBin(self.wall(self._mono0 + index * 60))
        return self._bins[index]

    def add_observation(self, obs: FrameObservation) -> None:
        if not self.running:
            return
        self.latest = obs
        step = self._tracker.add(obs)
        self.window.add(step)
        if not obs.valid:
            if self._untracked_since is None:
                self._untracked_since = obs.t
            return
        if step.interval is None and self._untracked_since is None and self._last_valid_t is not None:
            self._untracked_since = self._last_valid_t  # a long gap between valid frames is also missing time
        self._close_untracked(obs.t)
        minute = self._bin(obs.t)
        if step.interval:
            start, end, is_closed = step.interval
            dt = end - start
            self.tracked += dt
            minute.tracked += dt
            if is_closed:
                self.closed += dt
                minute.closed += dt
        if step.blink:
            self.blinks += 1
            minute.blinks += 1
        if step.closure is not None:
            self.closures.append(step.closure)
            minute.closures.append(step.closure)
        self._last_valid_t = obs.t

    def _close_untracked(self, t: float) -> None:
        if self._untracked_since is not None:
            if t - self._untracked_since >= UNTRACKED_MIN:
                self._untracked.append((self._untracked_since, t))
            self._untracked_since = None

    def pause(self, t: float) -> None:
        if not self.running:
            return
        self._close_untracked(t)
        self._segments.append((self._segment_start, t))
        self.running = False
        self._tracker.interrupt()  # an unfinished closure is discarded
        self.window.pause(t)
        self._last_valid_t = None

    def resume(self, t: float) -> None:
        if self.running:
            return
        self.running = True
        self._segment_start = t
        self.window.resume(t)

    def live(self, now: float) -> RollingSnapshot:
        """The rolling last-60-seconds measurements."""
        return self.window.snapshot(now)

    def summary(self, t: float) -> SessionSummary:
        """A snapshot of the whole session; if still running, the open period counts up to t."""
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
            calibration=self.calibration,
        )

    def finish(self, t: float) -> SessionSummary:
        self.pause(t)
        self.finished = True
        return self.summary(t)
