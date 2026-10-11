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
  the chair moves the face lower and (almost always) closer, so both must change.
* Screen tilt: on MacBooks with a lid angle sensor, the camera tilts with the screen.
  Tilting it moves the face up or down in the picture and changes the measured head
  angle, so both are corrected for the change in lid angle since the baseline; a clear,
  settled tilt (TiltWatcher) asks for a new baseline instead.

The baseline (PostureCalibration) is the median of each value over the first minute of
normal work in each study session. PostureMonitor then marks posture as
poor when a limit stays exceeded for POSTURE_SUSTAIN_SECONDS without a break, so a
glance away or a quick stretch never counts. A frame without a face is handled like
lost tracking in the blink counter: the half-finished count is forgotten and starts again.

Like the rest of OcuSense, this describes position only; it is not a health assessment.
"""

import math
import statistics

from ocusense.config import (
    FOCAL_LENGTH_PER_FRAME_WIDTH, IRIS_DIAMETER_MM, LID_RECALIBRATE_DEGREES, LID_SETTLE_SECONDS,
    POSTURE_CALIBRATION_SECONDS, POSTURE_CENTRE_DROP, POSTURE_CLOSER_FRACTION, POSTURE_GRACE_SECONDS,
    POSTURE_MAX_PITCH_SPREAD, POSTURE_MIN_DISTANCE_CM, POSTURE_MIN_SAMPLES, POSTURE_PITCH_DROP_DEGREES,
    POSTURE_REMINDER_GAP_SECONDS, POSTURE_REMINDER_REPEAT_SECONDS, POSTURE_ROLL_DEGREES, POSTURE_SLUMP_GROWTH, POSTURE_SUSTAIN_SECONDS,
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
# Distance isn't one of them: being close to the screen has its own reminder (core/proximity.py), so the
# posture message is only about how you sit. The estimated distance is still shown.
LIMITS = (HEAD_DROPPED, HEAD_TILTED, SLUMPED)


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


def read_posture(matrix, points, frame_width: int, frame_height: int,
                 lid_angle: float | None = None) -> PostureReading | None:
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
        aspect=frame_width / frame_height,
        lid_angle=lid_angle,
    )


def angle_difference(a: float, b: float) -> float:
    """a − b in degrees, between −180 and 180 (so 179° and −179° are 2° apart)."""
    return (a - b + 180) % 360 - 180


def corrected_for_tilt(reading: PostureReading, baseline: PostureBaseline,
                       focal_per_width: float = FOCAL_LENGTH_PER_FRAME_WIDTH) -> tuple[float, float, float | None]:
    """(pitch, centre_y, lid change) as if the screen were still at the baseline's angle.

    Opening the screen further (lid angle +δ) turns the camera upwards by δ: the head then
    looks δ more "chin down" to the camera, and everything in the picture moves down by
    about focal length × tan(δ), i.e. focal_per_width × aspect × tan(δ) of the frame height.
    Without lid angles (no sensor) nothing is corrected.
    """
    if reading.lid_angle is None or baseline.lid_angle is None:
        return reading.pitch, reading.centre_y, None
    delta = reading.lid_angle - baseline.lid_angle
    shift = focal_per_width * reading.aspect * math.tan(math.radians(delta))
    return reading.pitch - delta, reading.centre_y - shift, delta


# ------------------------------------------------------------------ calibration
class PostureCalibration:
    """The posture baseline: readings over POSTURE_CALIBRATION_SECONDS of normal work, then their medians."""
    IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"

    def __init__(self, seconds: float = POSTURE_CALIBRATION_SECONDS, min_samples: int = POSTURE_MIN_SAMPLES,
                 max_pitch_spread: float = POSTURE_MAX_PITCH_SPREAD):
        self.seconds = seconds
        self.min_samples = min_samples
        self.max_pitch_spread = max_pitch_spread
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
        if reading is not None and reading.pitch is not None:
            self._samples.append(reading)  # frames with a head angle (the distance may be missing)
        if now - self._started < self.seconds:
            return
        if len(self._samples) < self.min_samples:
            self.status = self.FAILED
            self.error = "Your face wasn't seen clearly enough. Sit facing the camera and try again."
            return
        s = self._samples
        pitch = statistics.median(r.pitch for r in s)
        # Spread of the middle half of the values (interquartile range, scaled to a standard deviation).
        # Robust to odd frames, and unlike the median deviation it also sees two alternating postures.
        q1, _, q3 = statistics.quantiles((r.pitch for r in s), n=4)
        spread = (q3 - q1) / 1.349
        if spread > self.max_pitch_spread:
            self.status = self.FAILED
            self.error = (f"Your head angle kept changing (about ±{spread:.0f}°), so there was no single posture "
                          "to keep. Sit the way you want to and try again.")
            return
        lids = [r.lid_angle for r in s if r.lid_angle is not None]
        distances = [r.distance_cm for r in s if r.distance_cm is not None]
        self.result = PostureBaseline(
            pitch=pitch,
            roll=statistics.median(r.roll for r in s),
            distance_cm=statistics.median(distances) if len(distances) * 2 >= len(s) else None,  # mostly, or not
            centre_y=statistics.median(r.centre_y for r in s),
            size=statistics.median(r.size for r in s),
            lid_angle=statistics.median(lids) if len(lids) * 2 >= len(s) else None,  # mostly read, or not at all
        )
        self.status = self.DONE


# ------------------------------------------------------------------ monitoring
class PostureMonitor:
    """Compares each frame with the baseline; poor only after a limit stays exceeded long enough.

    "Without a break" allows for the camera's wobble: a limit's count only starts again after
    being back within it for more than `grace_seconds`, and lost tracking only resets the
    counts after `grace_seconds` without a face (a blink of lost tracking isn't sitting up).
    """

    def __init__(self, baseline: PostureBaseline, sustain_seconds: float = POSTURE_SUSTAIN_SECONDS,
                 pitch_drop: float = POSTURE_PITCH_DROP_DEGREES, roll_limit: float = POSTURE_ROLL_DEGREES,
                 min_distance_cm: float = POSTURE_MIN_DISTANCE_CM, closer_fraction: float = POSTURE_CLOSER_FRACTION,
                 centre_drop: float = POSTURE_CENTRE_DROP, slump_growth: float = POSTURE_SLUMP_GROWTH,
                 grace_seconds: float = POSTURE_GRACE_SECONDS):
        self.baseline = baseline
        self.sustain_seconds, self.grace_seconds = sustain_seconds, grace_seconds
        self.pitch_drop, self.roll_limit = pitch_drop, roll_limit
        self.min_distance_cm, self.closer_fraction = min_distance_cm, closer_fraction
        self.centre_drop, self.slump_growth = centre_drop, slump_growth
        self._since: dict[str, float] = {}  # limit → when this run of exceeding it started
        self._last_out: dict[str, float] = {}  # limit → the last frame it was exceeded
        self._last_seen: float | None = None  # the last frame with a face

    def exceeded(self, reading: PostureReading) -> set[str]:
        """The limits this reading exceeds right now (head angle and face height corrected for screen tilt)."""
        b = self.baseline
        pitch, centre_y, lid_change = corrected_for_tilt(reading, b)
        out = set()
        if angle_difference(pitch, b.pitch) > self.pitch_drop:
            out.add(HEAD_DROPPED)
        if reading.roll is not None and abs(angle_difference(reading.roll, b.roll)) > self.roll_limit:
            out.add(HEAD_TILTED)
        lower = centre_y - b.centre_y > self.centre_drop
        bigger = bool(b.size) and reading.size / b.size >= 1 + self.slump_growth
        if lower and (bigger or lid_change is not None):
            out.add(SLUMPED)  # lower alone only when the screen tilt is known and corrected
        return out

    def update(self, now: float, reading: PostureReading | None) -> PostureStatus:
        if self._last_seen is not None and now - self._last_seen > self.grace_seconds:
            self.reset()  # no face for too long (or a gap): start counting again
        if reading is None or reading.pitch is None:
            return PostureStatus(tracked=False)
        self._last_seen = now
        outside = self.exceeded(reading)
        for name in LIMITS:
            if name in outside:
                self._since.setdefault(name, now)
                self._last_out[name] = now
            elif name in self._since and now - self._last_out[name] > self.grace_seconds:
                del self._since[name], self._last_out[name]  # really back within the limit
        problems = tuple(n for n in LIMITS if n in self._since and now - self._since[n] >= self.sustain_seconds)
        b = self.baseline
        pitch, centre_y, lid_change = corrected_for_tilt(reading, b)
        return PostureStatus(
            tracked=True, poor=bool(problems), problems=problems,
            outside=tuple(n for n in LIMITS if n in outside),
            longest_outside=max((now - t for t in self._since.values()), default=0.0),
            pitch_change=angle_difference(pitch, b.pitch),
            roll_change=angle_difference(reading.roll, b.roll) if reading.roll is not None else None,
            distance_cm=reading.distance_cm, baseline_distance_cm=b.distance_cm,
            centre_drop=centre_y - b.centre_y,
            size_ratio=reading.size / b.size if b.size else None,
            lid_change=lid_change,
        )

    def reset(self) -> None:
        """Monitoring paused, or no face for too long: forget how long limits have been exceeded."""
        self._since.clear()
        self._last_out.clear()
        self._last_seen = None


# ------------------------------------------------------------------ screen tilt
class TiltWatcher:
    """Notices a clear screen tilt that has settled: the posture baseline then no longer fits.

    The reference is the lid angle the current baseline (or the one being recorded) was made
    at. A tilt counts when the angle is at least `threshold` degrees away from it and has
    stayed within ±1° for `settle_seconds`, so adjusting the screen gives one event, at the end.
    """
    WOBBLE = 1.0  # degrees; the sensor reads whole degrees

    def __init__(self, threshold: float = LID_RECALIBRATE_DEGREES, settle_seconds: float = LID_SETTLE_SECONDS):
        self.threshold = threshold
        self.settle_seconds = settle_seconds
        self.reference: float | None = None
        self._settling: float | None = None  # the angle the screen is (maybe) resting at
        self._since: float | None = None

    def set_reference(self, angle: float | None) -> None:
        self.reference = angle
        self._settling = self._since = None

    def update(self, now: float, angle: float | None) -> bool:
        """True once per settled tilt; the new angle then becomes the reference."""
        if angle is None or self.reference is None or abs(angle - self.reference) < self.threshold:
            self._settling = self._since = None
            return False
        if self._settling is None or abs(angle - self._settling) > self.WOBBLE:
            self._settling, self._since = angle, now  # still moving
            return False
        if now - self._since < self.settle_seconds:
            return False
        self.set_reference(angle)
        return True


# ------------------------------------------------------------------ reminder
class PostureReminder:
    """When to say "stop slouching": as soon as posture turns poor, and again while it stays poor.

    A poor stretch starts when the status turns poor (a limit exceeded for POSTURE_SUSTAIN_SECONDS)
    and ends when posture is judged good again. The first message of a stretch comes at once
    (but at least `gap_seconds` after the previous message); while the stretch lasts it is
    repeated every `repeat_seconds`. Frames without a face or before the baseline don't end a
    stretch (the monitor already restarts its timers then), so tracking dropouts can't cause a
    burst of messages.
    """

    def __init__(self, gap_seconds: float = POSTURE_REMINDER_GAP_SECONDS,
                 repeat_seconds: float = POSTURE_REMINDER_REPEAT_SECONDS):
        self.gap_seconds = gap_seconds
        self.repeat_seconds = repeat_seconds
        self.sent_in_stretch = False  # this poor stretch has had its first message
        self.last: float | None = None

    def update(self, now: float, status: PostureStatus | None) -> bool:
        """True when a message is due with this frame's status."""
        if status is None or not status.tracked:
            return False
        if not status.poor:
            self.sent_in_stretch = False  # sat up: the next poor stretch is a new one
            return False
        wait = self.repeat_seconds if self.sent_in_stretch else self.gap_seconds
        if self.last is not None and now - self.last < wait:
            return False
        self.last = now
        self.sent_in_stretch = True
        return True
