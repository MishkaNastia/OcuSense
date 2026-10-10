"""Replay a saved EAR recording through the app's own calibration, detector and measurements.

Input: rows (unix time, left EAR, right EAR, reliable) plus the calibration saved
with them. Output: the same FrameObservations the live pipeline would have made,
fed through MeasurementTracker and DistributionBuilder — so offline analysis uses
exactly the live definitions:

* openness per eye = (EAR − closed EAR) / (open EAR − closed EAR) (EyeReference)
* the detector (BlinkCounter) gets the mean of the two CLIPPED values, with the
  recorded close/reopen thresholds (never hard-coded ones)
* a frame is valid only when it is reliable and both EARs are present

One difference is unavoidable: a timestamp gap longer than MAX_FRAME_GAP is
treated like a pause (the detector forgets a half-finished blink). Live, only a
real pause does that; a gap inside a file can only come from a rare processing
stall, so at most one blink per stall could be counted differently.

Pure Python: no files, no interface. Loading lives in ocusense/recording_files.py.
"""

import math
from dataclasses import dataclass, field

from ocusense.config import MAX_FRAME_GAP

from .blink_counter import BlinkCounter
from .calibration import EyeReference, PersonalCalibration
from .distributions import DistributionBuilder, Distributions
from .measurements import MeasurementTracker
from .models import FrameObservation

STORED_OPENNESS_TOLERANCE = 0.001  # stored values are rounded to 4 decimals, like the EAR they come from


@dataclass(frozen=True)
class Row:
    t: float  # unix time, seconds
    left_ear: float | None
    right_ear: float | None
    reliable: bool
    left_openness: float | None = None  # as stored in the file (0–1, not clipped), for checking only
    right_openness: float | None = None


@dataclass(frozen=True)
class RecordedCalibration:
    left_open_ear: float
    left_closed_ear: float
    right_open_ear: float
    right_closed_ear: float
    close_below: float
    reopen_above: float
    calibrated_at: str
    measurement_version: str
    reference_face_scale: float | None = None  # only in recordings made after the distance reminder was added

    @classmethod
    def from_json(cls, values: dict) -> "RecordedCalibration":
        optional = {"reference_face_scale"}
        return cls(**{name: values.get(name) if name in optional else values[name]
                      for name in cls.__dataclass_fields__})

    def personal(self) -> PersonalCalibration:
        return PersonalCalibration(EyeReference(self.left_open_ear, self.left_closed_ear),
                                   EyeReference(self.right_open_ear, self.right_closed_ear))

    def label(self) -> str:
        return (f"calibrated {self.calibrated_at.replace('T', ' ')} · closes below {self.close_below:.0%}, "
                f"reopens above {self.reopen_above:.0%} · {self.measurement_version}")


@dataclass
class Timeline:
    """Per-frame data for the "Inspect detection" view (only for imported recordings)."""
    times: list = field(default_factory=list)  # seconds since the recording started
    left: list = field(default_factory=list)  # unclipped openness, NaN when not valid
    right: list = field(default_factory=list)
    detector: list = field(default_factory=list)  # what the detector saw: mean of the clipped values, NaN if none
    gaps: list = field(default_factory=list)  # [(start, end)] seconds without valid observation
    blinks: list = field(default_factory=list)  # completion times of every counted blink


@dataclass
class Replay:
    distributions: Distributions
    timeline: Timeline
    frames: int
    valid_frames: int
    stored_mismatches: int  # rows whose stored openness differs from the recomputed one
    start_unix: float


def replay(rows: list[Row], calibration: RecordedCalibration) -> Replay:
    personal = calibration.personal()
    counter = BlinkCounter(calibration.close_below, calibration.reopen_above)
    tracker = MeasurementTracker()
    start = rows[0].t if rows else 0.0
    builder = DistributionBuilder(start=0.0)  # times below are seconds since the start
    timeline = Timeline()
    mismatches = valid_frames = 0
    previous_t: float | None = None
    gap_since: float | None = None

    for row in rows:
        t = row.t - start
        if previous_t is not None and t - previous_t > MAX_FRAME_GAP:
            counter.update(None)  # like a pause: no blink or closure across the gap
            tracker.interrupt()
            builder.interrupt(t)
            if gap_since is None:
                gap_since = previous_t
        previous_t = t

        clipped = raw = None
        if row.reliable and row.left_ear is not None and row.right_ear is not None:
            ears = {"left": row.left_ear, "right": row.right_ear}
            clipped = personal.openness(ears)
            raw = personal.raw_openness(ears)
        before = counter.state
        blinked = counter.update(clipped[2] if clipped else None)
        after = counter.state
        obs = FrameObservation(
            t=t, valid=clipped is not None,
            left_raw=raw[0] if raw else None, right_raw=raw[1] if raw else None,
            left_ear=row.left_ear, right_ear=row.right_ear,
            detector_closed=after == BlinkCounter.CLOSED,
            closing_started=before == BlinkCounter.OPEN and after == BlinkCounter.CLOSED,
            blink_completed=blinked,
        )
        builder.add(obs, tracker.add(obs))

        if raw:
            valid_frames += 1
            for stored, value in ((row.left_openness, raw[0]), (row.right_openness, raw[1])):
                if stored is not None and abs(stored - value) > STORED_OPENNESS_TOLERANCE:
                    mismatches += 1
                    break
            if gap_since is not None:
                timeline.gaps.append((gap_since, t))
                gap_since = None
        elif gap_since is None:
            gap_since = t
        timeline.times.append(t)
        timeline.left.append(raw[0] if raw else math.nan)
        timeline.right.append(raw[1] if raw else math.nan)
        timeline.detector.append(clipped[2] if clipped else math.nan)
        if blinked:
            timeline.blinks.append(t)

    if gap_since is not None and previous_t is not None and previous_t > gap_since:
        timeline.gaps.append((gap_since, previous_t))
    builder.interrupt()
    return Replay(builder.snapshot(finished=True), timeline, len(rows), valid_frames, mismatches, start)
