"""Blink counting logic.

This file knows nothing about cameras. It receives a "personal eye
openness" value for every video frame and decides when a full blink
happened.

Personal eye openness comes from calibration.py:
1.0 = as open as during your calibration, 0.0 = as closed as during it.
"""

# Eyes count as CLOSED when openness drops below this value...
CLOSE_BELOW = 0.35
# ...and only count as OPEN again once it rises above this value.
# Using two different values stops tiny wobbles around one number from
# being counted as many blinks.
REOPEN_ABOVE = 0.65


class BlinkCounter:
    # The three states the eyes can be in, from the counter's point of view.
    UNKNOWN = "unknown"  # not measuring yet, or tracking was just lost
    OPEN = "open"
    CLOSED = "closed"

    def __init__(self, close_below=CLOSE_BELOW, reopen_above=REOPEN_ABOVE):
        if close_below >= reopen_above:
            raise ValueError("close_below must be lower than reopen_above")
        self.close_below = close_below
        self.reopen_above = reopen_above
        self.count = 0
        self.state = self.UNKNOWN

    def update(self, openness):
        """Feed in one frame.

        openness is the personal eye openness, or None when measurement is
        paused (no face, unreliable tracking, not calibrated).
        Returns True if this frame finished a blink.
        """
        if openness is None:
            # Measurement paused: forget any half-finished blink.
            self.state = self.UNKNOWN
            return False

        if self.state == self.UNKNOWN:
            # We only start watching once we've seen the eyes clearly open,
            # so starting (or coming back) with closed eyes never counts.
            if openness > self.reopen_above:
                self.state = self.OPEN
            return False

        if self.state == self.OPEN:
            if openness < self.close_below:
                self.state = self.CLOSED  # open -> closed
            return False

        # self.state == CLOSED: keeping the eyes shut does nothing extra.
        if openness > self.reopen_above:
            self.state = self.OPEN  # closed -> open = one full blink
            self.count += 1
            return True
        return False
