"""Automatic checks for the blink rules. Run with:  python -m unittest"""

import unittest

from blink_counter import BlinkCounter

# Personal eye openness values: 1 = open, 0 = closed.
OPEN = 0.95
CLOSED = 0.05
MIDDLE = 0.5  # between the two thresholds
LOST = None


def run(values):
    counter = BlinkCounter()
    for v in values:
        counter.update(v)
    return counter


class BlinkCounterTest(unittest.TestCase):
    def test_one_blink(self):
        self.assertEqual(run([OPEN, CLOSED, OPEN]).count, 1)

    def test_long_closed_counts_once(self):
        self.assertEqual(run([OPEN] + [CLOSED] * 50 + [OPEN]).count, 1)

    def test_closed_without_reopening_does_not_count(self):
        self.assertEqual(run([OPEN, CLOSED, CLOSED]).count, 0)

    def test_two_blinks(self):
        self.assertEqual(run([OPEN, CLOSED, OPEN, CLOSED, OPEN]).count, 2)

    def test_starting_with_closed_eyes_does_not_count(self):
        self.assertEqual(run([CLOSED, CLOSED, OPEN]).count, 0)

    def test_wobble_in_middle_does_not_count(self):
        self.assertEqual(run([OPEN, MIDDLE, OPEN, MIDDLE, CLOSED, MIDDLE]).count, 0)

    def test_half_reopen_then_close_counts_once(self):
        self.assertEqual(run([OPEN, CLOSED, MIDDLE, CLOSED, OPEN]).count, 1)

    def test_tracking_lost_resets_incomplete_blink(self):
        counter = run([OPEN, CLOSED, LOST, OPEN])
        self.assertEqual(counter.count, 0)
        # After tracking comes back, a normal blink still counts.
        for v in [CLOSED, OPEN]:
            counter.update(v)
        self.assertEqual(counter.count, 1)

    def test_tracking_lost_keeps_total(self):
        self.assertEqual(run([OPEN, CLOSED, OPEN, LOST, OPEN]).count, 1)

    def test_thresholds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            BlinkCounter(close_below=0.7, reopen_above=0.3)


if __name__ == "__main__":
    unittest.main()
