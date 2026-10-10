"""Shared test helpers: build FrameObservations the same way the pipeline does.

The real BlinkCounter decides closing/reopening, so tests exercise the
measurements against the actual detector rather than a re-implementation.
"""

from ocusense.core.blink_counter import BlinkCounter
from ocusense.core.models import FrameObservation

OPEN, CLOSED = 0.95, 0.05  # both-eyes personal openness fractions
FPS = 30


class Observer:
    """Turns (time, both-eyes openness or None) into FrameObservations via the real detector."""

    def __init__(self):
        self.detector = BlinkCounter()

    def __call__(self, t, openness, left=None, right=None):
        before = self.detector.state
        blinked = self.detector.update(openness)
        after = self.detector.state
        if openness is None:
            return FrameObservation(t=t, valid=False)
        left = openness if left is None else left
        right = openness if right is None else right
        return FrameObservation(
            t=t, valid=True, left_raw=left, right_raw=right, left_ear=0.3 * left, right_ear=0.3 * right,
            detector_closed=after == BlinkCounter.CLOSED,
            closing_started=before == BlinkCounter.OPEN and after == BlinkCounter.CLOSED,
            blink_completed=blinked,
        )


def frames(start, seconds, value_at, fps=FPS):
    """Yield (t, openness) at a steady frame rate; value_at(relative_time) -> openness or None."""
    n = int(round(seconds * fps))
    for i in range(n):
        yield start + i / fps, value_at(i / fps)


def blinking(every=4.0, closed_for=0.2, first=1.0):
    """Open eyes with a closure of `closed_for` seconds every `every` seconds."""
    def value(rel):
        phase = (rel - first + 1e-9) % every  # tolerance: frame times like 1.2 can be 1.1999… in floating point
        return CLOSED if rel >= first - 1e-9 and phase < closed_for - 1e-9 else OPEN
    return value
