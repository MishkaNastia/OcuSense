"""Shared data structures for measurements and session summaries.

Units: all durations are in seconds, times are time.monotonic() seconds unless
named *_at (wall clock, only to identify sessions). Openness values are
fractions (1 = calibrated open, 0 = calibrated closed). Display code converts
(to %, ms, …).
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from ocusense.config import MIN_TRACKED_PER_MINUTE


@dataclass(frozen=True)
class FrameObservation:
    """Input to the measurements: one processed camera frame, already calibrated.

    valid is True only when both eyes were measured reliably with a calibration;
    invalid frames are missing observation and never enter any denominator.
    The detector fields describe the existing blink detector's bilateral state
    (both-eyes openness) on this frame; measurements only read them.
    """
    t: float  # time.monotonic() seconds when the frame was taken
    valid: bool
    left_raw: float | None = None  # unclamped personal openness fractions
    right_raw: float | None = None
    left_ear: float | None = None  # raw EAR values (diagnostics only)
    right_ear: float | None = None
    detector_closed: bool = False  # detector is in its CLOSED state after this frame
    closing_started: bool = False  # detector went OPEN → CLOSED on this frame
    blink_completed: bool = False  # detector went CLOSED → OPEN on this frame (a counted blink)


@dataclass(frozen=True)
class CalibrationInfo:
    """Which calibration and settings produced a session's numbers."""
    calibrated_at: datetime
    left_open_ear: float
    left_closed_ear: float
    right_open_ear: float
    right_closed_ear: float
    close_below: float
    reopen_above: float
    measurement_version: str
    reference_face_scale: float | None = None  # eye-centre distance ÷ frame width at calibration (distance reminder)


@dataclass(frozen=True)
class RollingSnapshot:
    """The live interface's "last 60 seconds" numbers. None = not available."""
    window_seconds: float
    running_seconds: float  # time monitoring was running inside the window (pauses excluded)
    valid_seconds: float  # valid observation time inside the window
    coverage: float | None  # valid / running, 0–1
    enough_data: bool  # valid_seconds >= the configured minimum
    blinks: int  # completed bilateral blinks inside the window
    blink_rate: float | None  # blinks per minute of valid observation
    closure_count: int  # completed closure events with a measured duration
    median_closure: float | None  # seconds
    closed_seconds: float
    closed_percent: float | None  # % of valid observation in the detector's closed state
    processing_rate: float | None  # frames processed per second (valid or not)


@dataclass
class MinuteBin:
    """Per-minute summary for session history (numbers only)."""
    start: datetime
    tracked: float = 0.0  # valid observation seconds
    blinks: int = 0
    closures: list = field(default_factory=list)  # seconds, detector closing → reopening, per completed event
    closed: float = 0.0  # seconds in the detector's closed state

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
    tracked_seconds: float  # valid observation time
    blinks: int
    closure_seconds: list
    closed_seconds: float
    segments: list  # [(start, end)] running periods
    untracked: list  # [(start, end)] periods without valid observation
    minutes: list  # [MinuteBin]
    in_progress: bool = False
    calibration: CalibrationInfo | None = None

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


@dataclass(frozen=True)
class PostureReading:
    """Posture measured on one frame (core/posture.py). None = couldn't be measured on this frame."""
    pitch: float | None  # degrees; positive = chin down (head dropped)
    yaw: float | None  # degrees; head turned sideways (shown only, not judged)
    roll: float | None  # degrees; head tilted towards a shoulder
    distance_cm: float | None  # estimated eye-to-camera distance, from the iris width
    centre_y: float  # face centre height in the picture: 0 = top, 1 = bottom
    size: float  # face width ÷ frame width
    aspect: float = 4 / 3  # frame width ÷ height (to turn a screen tilt into a shift in the picture)
    lid_angle: float | None = None  # MacBook screen angle in degrees, or None without the sensor


@dataclass(frozen=True)
class PostureBaseline:
    """The posture reference: median values from the posture calibration (1 min of normal work)."""
    pitch: float
    roll: float
    distance_cm: float | None  # None when the iris wasn't measured often enough (no "closer than" check then)
    centre_y: float
    size: float
    lid_angle: float | None = None  # screen angle during calibration, or None without the sensor


@dataclass(frozen=True)
class PostureStatus:
    """Posture on one frame, compared with the baseline. Numbers are for display only."""
    tracked: bool  # False: no face (or no head angle) on this frame; nothing is judged
    poor: bool = False  # at least one limit has been exceeded for the sustained time
    problems: tuple = ()  # names of the limits exceeded for the sustained time, e.g. ("head dropped",)
    outside: tuple = ()  # names of the limits exceeded right now (not yet for long enough)
    longest_outside: float = 0.0  # seconds the longest current excess has lasted
    pitch_change: float | None = None  # degrees, + = chin lower than at calibration
    roll_change: float | None = None  # degrees, either way
    distance_cm: float | None = None
    baseline_distance_cm: float | None = None
    centre_drop: float | None = None  # fraction of the frame height, + = lower than at calibration
    size_ratio: float | None = None  # face size now ÷ at calibration (> 1 = bigger: closer or slid forward)
    lid_change: float | None = None  # screen tilted since calibration, degrees (+ = opened further); corrected for
