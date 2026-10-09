"""The last few seconds of personal eye openness, for drawing a graph.

The history only lives in memory, like the video frames: nothing is
saved to disk.
"""

from collections import deque

GRAPH_SECONDS = 10.0  # how much history the graph shows


class ScoreHistory:
    """Remembers the last few seconds of openness scores.

    Each sample is (time, openness, blinked), where openness is the
    (left, right, both) tuple from calibration, or None while measurement
    is paused (shown as a gap in the graph).
    """

    def __init__(self, seconds=GRAPH_SECONDS):
        self.seconds = seconds
        self.samples = deque()

    def add(self, now, openness, blinked=False):
        self.samples.append((now, openness, blinked))
        while now - self.samples[0][0] > self.seconds:
            self.samples.popleft()

    def clear(self):
        self.samples.clear()
