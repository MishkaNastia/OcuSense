"""Measure the eyes from MediaPipe face landmarks.

MediaPipe gives 478 points on the face. For each eye we use six of them
and compute the Eye Aspect Ratio (EAR):

        p2   p3                 EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    p1          p4
        p6   p5                 i.e. "how tall is the eye compared to how wide"

An open eye has a larger EAR than a closed one. EAR on its own is NOT
compared to any fixed number; calibration.py turns it into a personal
value using your own open and closed references.
"""

import math
from dataclasses import dataclass

# MediaPipe face-mesh indices, in the order p1..p6 shown above.
# The frame is mirrored before detection, so the eye MediaPipe calls
# "right" (index 33...) is the one on the left of the screen, which in a
# mirror view is your own left eye.
EYE_LANDMARKS = {
    "left": (33, 160, 158, 133, 153, 144),
    "right": (362, 385, 387, 263, 373, 380),
}

# Tracking-quality limits used to pause measurement (documented in config.py).
from ocusense.config import MIN_EYE_WIDTH_PX, MIN_EYE_WIDTH_RATIO


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(points: list[tuple[float, float]]) -> float | None:
    """EAR from six (x, y) pixel points ordered p1..p6."""
    p1, p2, p3, p4, p5, p6 = points
    width = distance(p1, p4)
    if width == 0:
        return None
    return (distance(p2, p6) + distance(p3, p5)) / (2 * width)


def eye_points_px(landmarks, indices: tuple[int, ...], frame_width: int, frame_height: int) -> list[tuple[float, float]]:
    """Convert MediaPipe's 0-1 coordinates into pixel coordinates.

    This matters because camera images are not square: a 0.1 step
    sideways is more pixels than a 0.1 step up/down in a 640x480 frame.
    """
    return [(landmarks[i].x * frame_width, landmarks[i].y * frame_height) for i in indices]


@dataclass
class EyeMeasurement:
    ears: dict  # {"left": EAR, "right": EAR}
    reliable: bool
    reason: str  # why it's unreliable ("" when reliable)
    # Distance between the two eye centres ÷ frame width: grows as the face comes closer.
    # Used only for the distance reminder; None when the eyes weren't both in the picture.
    face_scale: float | None = None


def measure_eyes(landmarks, frame_width: int, frame_height: int) -> "EyeMeasurement":
    """Compute both EARs and decide whether this frame is trustworthy."""
    ears = {}
    widths = {}
    centres = {}
    for name, indices in EYE_LANDMARKS.items():
        if any(not (0 <= landmarks[i].x <= 1 and 0 <= landmarks[i].y <= 1) for i in indices):
            return EyeMeasurement({}, False, "eye outside the picture")
        points = eye_points_px(landmarks, indices, frame_width, frame_height)
        widths[name] = distance(points[0], points[3])
        ears[name] = eye_aspect_ratio(points)
        centres[name] = ((points[0][0] + points[3][0]) / 2, (points[0][1] + points[3][1]) / 2)  # between the corners
    scale = distance(centres["left"], centres["right"]) / frame_width

    if min(widths.values()) < MIN_EYE_WIDTH_PX:
        return EyeMeasurement(ears, False, "face too small - move closer", scale)
    if min(widths.values()) / max(widths.values()) < MIN_EYE_WIDTH_RATIO:
        return EyeMeasurement(ears, False, "head turned - face the camera", scale)
    return EyeMeasurement(ears, True, "", scale)
