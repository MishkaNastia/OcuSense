"""Posture from the face: head angle, screen distance and slumping.

Everything comes from the Face Landmarker that already runs for the eyes, as plain
numbers (no camera, no MediaPipe objects):

* Head angle: MediaPipe's 4x4 facial transformation matrix (rows) gives the head's
  rotation. We read it as pitch (nodding; + = chin down), yaw (turning sideways) and
  roll (tilting towards a shoulder), in degrees.
* Distance: the visible iris is about IRIS_DIAMETER_MM wide in every adult, so
      distance ≈ focal length (px) × iris width (mm) ÷ iris width in the picture (px).
  The focal length is a typical laptop value (config.py), so centimetres are approximate.
* Slumping: the face's vertical centre in the picture and its size. Sliding down in
  the chair moves the face lower; leaning forward makes it bigger.

A short "sit up straight" step (PostureCalibration) records the median of each value.
PostureMonitor then marks posture as poor when a limit stays exceeded for
POSTURE_SUSTAIN_SECONDS without a break, so a glance away or a quick stretch never
counts. A frame without a face is handled like lost tracking in the blink counter:
the half-finished count is forgotten and starts again.

Like the rest of OcuSense, this describes position only; it is not a health assessment.
"""

import math
import statistics

from ocusense.config import (
    FOCAL_LENGTH_PER_FRAME_WIDTH, IRIS_DIAMETER_MM, POSTURE_CALIBRATION_SECONDS, POSTURE_CENTRE_DROP,
    POSTURE_CLOSER_FRACTION, POSTURE_MIN_DISTANCE_CM, POSTURE_MIN_SAMPLES, POSTURE_PITCH_DROP_DEGREES,
    POSTURE_ROLL_DEGREES, POSTURE_SUSTAIN_SECONDS,
)

from .models import PostureBaseline, PostureReading, PostureStatus

# MediaPipe iris landmarks (only in the 478-point model): the two horizontal edge points of each iris.
# Horizontal, because the eyelids often cover the top and bottom of the iris.
IRIS_EDGES = ((469, 471), (474, 476))
IRIS_POINT_COUNT = 478

# The four limits, by the name shown to the user.
HEAD_DROPPED = "head dropped"
HEAD_TILTED = "head tilted"
TOO_CLOSE = "too close"
SLUMPED = "slumped"
LIMITS = (HEAD_DROPPED, HEAD_TILTED, TOO_CLOSE, SLUMPED)


# ------------------------------------------------------------------ measurements
def head_pose(matrix) -> tuple[float, float, float]:
    """(pitch, yaw, roll) in degrees from a 4x4 transformation matrix given as rows.

    The rotation part is read as R = Rz(roll) · Ry(yaw) · Rx(pitch).
    """
    r = matrix
    pitch = math.degrees(math.atan2(r[2][1], r[2][2]))
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -r[2][0]))))  # clamped: rounding can go just past ±1
    roll = math.degrees(math.atan2(r[1][0], r[0][0]))
    return pitch, yaw, roll


def iris_width_px(points, frame_width: int, frame_height: int) -> float | None:
    """Mean horizontal iris width of both eyes in pixels; None without iris landmarks."""
    if len(points) < IRIS_POINT_COUNT:
        return None
    widths = []
    for a, b in IRIS_EDGES:
        (ax, ay), (bx, by) = points[a], points[b]
        widths.append(math.hypot((ax - bx) * frame_width, (ay - by) * frame_height))
    width = sum(widths) / len(widths)
    return width if width > 0 else None


def distance_cm(iris_px: float | None, frame_width: int,
                focal_per_width: float = FOCAL_LENGTH_PER_FRAME_WIDTH, iris_mm: float = IRIS_DIAMETER_MM) -> float | None:
    """Estimated eye-to-camera distance in cm from the iris width in pixels."""
    if not iris_px:
        return None
    focal_px = focal_per_width * frame_width
    return focal_px * iris_mm / iris_px / 10  # mm → cm


def read_posture(matrix, points, frame_width: int, frame_height: int) -> PostureReading | None:
    """One frame's posture. matrix: 4x4 rows or None; points: [(x, y)] in MediaPipe's 0–1 units."""
    if not points:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    pitch = yaw = roll = None
    if matrix is not None:
        pitch, yaw, roll = head_pose(matrix)
    return PostureReading(
        pitch=pitch, yaw=yaw, roll=roll,
        distance_cm=distance_cm(iris_width_px(points, frame_width, frame_height), frame_width),
        centre_y=(min(ys) + max(ys)) / 2,
        size=max(xs) - min(xs),
    )


def angle_difference(a: float, b: float) -> float:
    """a − b in degrees, between −180 and 180 (so 179° and −179° are 2° apart)."""
    return (a - b + 180) % 360 - 180


# ------------------------------------------------------------------ calibration
class PostureCalibration:
    """The "sit up straight" step: collects readings for POSTURE_CALIBRATION_SECONDS, then takes medians."""
    IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"

    def __init__(self, seconds: float = POSTURE_CALIBRATION_SECONDS, min_samples: int = POSTURE_MIN_SAMPLES):
        self.seconds = seconds
        self.min_samples = min_samples
        self.status = self.IDLE
        self.result: PostureBaseline | None = None
        self.error = ""
        self._started: float | None = None
        self._samples: list[PostureReading] = []

    def start(self, now: float) -> None:
        self.status = self.RUNNING
        self.result = None
        self.error = ""
        self._started = now
        self._samples = []

    def seconds_left(self, now: float) -> float:
        if self.status != self.RUNNING:
            return 0.0
        return max(0.0, self.seconds - (now - self._started))

    def update(self, now: float, reading: PostureReading | None) -> None:
        if self.status != self.RUNNING:
            return
        if reading is not None and reading.pitch is not None and reading.distance_cm is not None:
            self._samples.append(reading)  # only frames where everything was measured
        if now - self._started < self.seconds:
            return
        if len(self._samples) < self.min_samples:
            self.status = self.FAILED
            self.error = "Your face wasn't seen clearly enough. Sit facing the camera and try again."
            return
        s = self._samples
        self.result = PostureBaseline(
            pitch=statistics.median(r.pitch for r in s),
            roll=statistics.median(r.roll for r in s),
            distance_cm=statistics.median(r.distance_cm for r in s),
            centre_y=statistics.median(r.centre_y for r in s),
            size=statistics.median(r.size for r in s),
        )
        self.status = self.DONE


# ------------------------------------------------------------------ monitoring
class PostureMonitor:
    """Compares each frame with the baseline; poor only after a limit stays exceeded long enough."""

    def __init__(self, baseline: PostureBaseline, sustain_seconds: float = POSTURE_SUSTAIN_SECONDS,
                 pitch_drop: float = POSTURE_PITCH_DROP_DEGREES, roll_limit: float = POSTURE_ROLL_DEGREES,
                 min_distance_cm: float = POSTURE_MIN_DISTANCE_CM, closer_fraction: float = POSTURE_CLOSER_FRACTION,
                 centre_drop: float = POSTURE_CENTRE_DROP):
        self.baseline = baseline
        self.sustain_seconds = sustain_seconds
        self.pitch_drop, self.roll_limit = pitch_drop, roll_limit
        self.min_distance_cm, self.closer_fraction = min_distance_cm, closer_fraction
        self.centre_drop = centre_drop
        self._since: dict[str, float] = {}  # limit → when it started being exceeded (this time)

    def exceeded(self, reading: PostureReading) -> set[str]:
        """The limits this reading exceeds right now."""
        b = self.baseline
        out = set()
        if angle_difference(reading.pitch, b.pitch) > self.pitch_drop:
            out.add(HEAD_DROPPED)
        if reading.roll is not None and abs(angle_difference(reading.roll, b.roll)) > self.roll_limit:
            out.add(HEAD_TILTED)
        d = reading.distance_cm
        if d is not None and (d < self.min_distance_cm or d < b.distance_cm * (1 - self.closer_fraction)):
            out.add(TOO_CLOSE)
        if reading.centre_y - b.centre_y > self.centre_drop:
            out.add(SLUMPED)
        return out

    def update(self, now: float, reading: PostureReading | None) -> PostureStatus:
        if reading is None or reading.pitch is None:
            self.reset()  # like lost tracking: forget the half-finished counts
            return PostureStatus(tracked=False)
        outside = self.exceeded(reading)
        for name in LIMITS:
            if name not in outside:
                self._since.pop(name, None)  # back within the limit: start counting again next time
            else:
                self._since.setdefault(name, now)
        problems = tuple(n for n in LIMITS if n in outside and now - self._since[n] >= self.sustain_seconds)
        b = self.baseline
        return PostureStatus(
            tracked=True, poor=bool(problems), problems=problems,
            outside=tuple(n for n in LIMITS if n in outside),
            longest_outside=max((now - t for t in self._since.values()), default=0.0),
            pitch_change=angle_difference(reading.pitch, b.pitch),
            roll_change=angle_difference(reading.roll, b.roll) if reading.roll is not None else None,
            distance_cm=reading.distance_cm, baseline_distance_cm=b.distance_cm,
            centre_drop=reading.centre_y - b.centre_y,
            size_ratio=reading.size / b.size if b.size else None,
        )

    def reset(self) -> None:
        """No face, or monitoring paused: forget how long limits have been exceeded."""
        self._since.clear()
