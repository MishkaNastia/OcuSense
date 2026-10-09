"""Personal calibration: turn raw EAR into "personal eye openness".

Everyone's eyes are shaped differently, so a raw EAR of 0.20 can mean
"wide open" for one person and "half closed" for another. Instead of a
fixed threshold, we measure YOUR eyes:

  1. comfortably open   -> open reference   (per eye)
  2. gently closed      -> closed reference (per eye)
  3. a few natural blinks -> check that blinks are actually detectable

Then for each eye:
    personal openness = (EAR - closed reference) / (open reference - closed reference)
so 1.0 means "as open as in calibration" and 0.0 "as closed as in calibration".

This is a measure of eye openness relative to your own calibration only.
It says nothing about fatigue or health.
"""

import statistics
from dataclasses import dataclass

from blink_counter import BlinkCounter

# A calibration is rejected unless all of these hold.
MIN_SAMPLES = 15  # reliable frames needed per phase
MIN_RELATIVE_SEPARATION = 0.25  # closed reference must be at least 25% below open
MAX_SPREAD_FRACTION = 0.25  # wobble within a phase vs. the open-closed gap
MIN_CALIBRATION_BLINKS = 3  # blinks that must be detected in the blink phase


class CalibrationError(Exception):
    """Calibration was not good enough; the message says why."""


def robust_reference(samples):
    """Median and robust spread of a list of EAR values.

    The median ignores a few odd frames (e.g. an accidental blink while
    "keeping eyes open"). The spread uses the median absolute deviation,
    scaled so it is comparable to a standard deviation.
    """
    median = statistics.median(samples)
    mad = statistics.median(abs(s - median) for s in samples)
    return median, 1.4826 * mad


@dataclass(frozen=True)
class EyeReference:
    open_ear: float
    closed_ear: float

    def openness(self, ear):
        value = (ear - self.closed_ear) / (self.open_ear - self.closed_ear)
        # Clip to 0..1 so one eye squeezed extra hard (or opened extra
        # wide) can't dominate when the two eyes are combined.
        return min(1.0, max(0.0, value))


def build_eye_reference(eye_name, open_samples, closed_samples):
    """Make one eye's reference, or raise CalibrationError explaining why not."""
    if len(open_samples) < MIN_SAMPLES or len(closed_samples) < MIN_SAMPLES:
        raise CalibrationError(
            f"Not enough clear frames of your {eye_name} eye. "
            "Face the camera in good light and keep still."
        )
    open_ear, open_spread = robust_reference(open_samples)
    closed_ear, closed_spread = robust_reference(closed_samples)

    gap = open_ear - closed_ear
    if open_ear <= 0 or gap < MIN_RELATIVE_SEPARATION * open_ear:
        raise CalibrationError(
            f"Open and closed {eye_name} eye looked too similar. "
            "Keep eyes comfortably open, then fully (but gently) closed."
        )
    if max(open_spread, closed_spread) > MAX_SPREAD_FRACTION * gap:
        raise CalibrationError(
            f"{eye_name.capitalize()} eye measurements were unstable. "
            "Keep your head still and avoid blinking during the open step."
        )
    return EyeReference(open_ear, closed_ear)


def combine(left_openness, right_openness):
    """Combine the two eyes into one value by averaging.

    Each eye was already scaled to its own 0..1 range, so an eye that is
    naturally narrower counts exactly as much as the other one. Averaging
    smooths out noise from either eye. Because a real blink closes both
    eyes, the average only drops below the closing threshold when BOTH
    eyes close: a one-eyed wink stays around 0.5 and is not counted.
    """
    return (left_openness + right_openness) / 2


@dataclass(frozen=True)
class PersonalCalibration:
    left: EyeReference
    right: EyeReference

    def openness(self, ears):
        """Return (left, right, combined) personal eye openness."""
        left = self.left.openness(ears["left"])
        right = self.right.openness(ears["right"])
        return left, right, combine(left, right)


def count_blinks(openness_values):
    """How many blinks the normal counter finds in a list (None = paused)."""
    counter = BlinkCounter()
    for value in openness_values:
        counter.update(value)
    return counter.count


@dataclass(frozen=True)
class Step:
    name: str
    instruction: str
    get_ready_seconds: float
    measure_seconds: float
    # Only frames between these two times (from the start of measuring)
    # are used, to skip the moment you are still closing/opening your eyes.
    use_from: float
    use_until: float


STEPS = (
    Step("open", "Keep your eyes comfortably OPEN and look at the screen", 3.0, 3.0, 0.5, 3.0),
    Step("closed", "When the countdown ends, gently CLOSE your eyes and slowly count to 5",
         4.0, 4.5, 1.0, 3.5),
    Step("blinks", "Blink naturally about 5 times", 3.0, 6.0, 0.0, 6.0),
)


class GuidedCalibration:
    """Walks through the calibration steps using the clock.

    Call start(now) to begin, then update(now, ears) every frame, where
    ears is {"left": EAR, "right": EAR} or None when tracking is
    unreliable (those frames are simply not used).
    """

    IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"

    def __init__(self):
        self.status = self.IDLE
        self.result = None  # PersonalCalibration once DONE
        self.error = ""  # message once FAILED

    def start(self, now):
        self.status = self.RUNNING
        self.result = None
        self.error = ""
        self._samples = {"open": {"left": [], "right": []}, "closed": {"left": [], "right": []}}
        self._blink_openness = []
        self._candidate = None
        self._step_index = 0
        self._step_start = now

    @property
    def step(self):
        return STEPS[self._step_index] if self.status == self.RUNNING else None

    def measuring(self, now):
        """True once the get-ready countdown of the current step is over."""
        return self.step is not None and now - self._step_start >= self.step.get_ready_seconds

    def seconds_left(self, now):
        step = self.step
        if step is None:
            return 0
        elapsed = now - self._step_start
        if elapsed < step.get_ready_seconds:
            return step.get_ready_seconds - elapsed
        return step.get_ready_seconds + step.measure_seconds - elapsed

    def update(self, now, ears):
        step = self.step
        if step is None:
            return
        t = now - self._step_start - step.get_ready_seconds  # time since measuring started

        if 0 <= t < step.measure_seconds and step.use_from <= t <= step.use_until:
            if step.name == "blinks":
                # None pauses the counter, just like during normal use.
                value = None if ears is None else self._candidate.openness(ears)[2]
                self._blink_openness.append(value)
            elif ears is not None:
                for eye in ("left", "right"):
                    self._samples[step.name][eye].append(ears[eye])

        if t >= step.measure_seconds:
            self._finish_step(step, now)

    def _finish_step(self, step, now):
        try:
            if step.name == "closed":
                self._candidate = PersonalCalibration(
                    left=build_eye_reference(
                        "left", self._samples["open"]["left"], self._samples["closed"]["left"]),
                    right=build_eye_reference(
                        "right", self._samples["open"]["right"], self._samples["closed"]["right"]),
                )
            elif step.name == "blinks":
                found = count_blinks(self._blink_openness)
                if found < MIN_CALIBRATION_BLINKS:
                    raise CalibrationError(
                        f"Only {found} blink(s) detected (need {MIN_CALIBRATION_BLINKS}). "
                        "During the closed step, close your eyes gently - don't squeeze."
                    )
                self.result = self._candidate
                self.status = self.DONE
                return
        except CalibrationError as problem:
            self.error = str(problem)
            self.status = self.FAILED
            return
        self._step_index += 1
        self._step_start = now
