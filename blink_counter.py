"""Blink counting logic.

This file knows nothing about cameras. It just receives an "eye closed
score" for every video frame and decides when a full blink happened.

The score comes from MediaPipe and goes from 0.0 (eyes wide open)
to 1.0 (eyes fully closed).
"""

# The eyes count as CLOSED when the score goes above this value...
CLOSED_THRESHOLD = 0.5
# ...and only count as OPEN again once the score drops below this value.
# Using two different values stops tiny wobbles around one number from
# being counted as many blinks.
OPEN_THRESHOLD = 0.3


class BlinkCounter:
    # The three states the eyes can be in, from the counter's point of view.
    UNKNOWN = "unknown"  # no face yet, or tracking was just lost
    OPEN = "open"
    CLOSED = "closed"

    def __init__(self, closed_threshold=CLOSED_THRESHOLD, open_threshold=OPEN_THRESHOLD):
        if open_threshold >= closed_threshold:
            raise ValueError("open_threshold must be lower than closed_threshold")
        self.closed_threshold = closed_threshold
        self.open_threshold = open_threshold
        self.count = 0
        self.state = self.UNKNOWN

    def update(self, closed_score):
        """Feed in one frame.

        closed_score is a number from 0 to 1, or None when no face is
        tracked in this frame. Returns True if this frame finished a blink.
        """
        if closed_score is None:
            # Tracking lost: forget any half-finished blink.
            self.state = self.UNKNOWN
            return False

        if self.state == self.UNKNOWN:
            # We only start watching once we've seen the eyes clearly open,
            # so starting (or coming back) with closed eyes never counts.
            if closed_score < self.open_threshold:
                self.state = self.OPEN
            return False

        if self.state == self.OPEN:
            if closed_score > self.closed_threshold:
                self.state = self.CLOSED  # open -> closed
            return False

        # self.state == CLOSED: keeping the eyes shut does nothing extra.
        if closed_score < self.open_threshold:
            self.state = self.OPEN  # closed -> open = one full blink
            self.count += 1
            return True
        return False
