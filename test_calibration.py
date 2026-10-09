"""Checks for personal calibration. Run with:  python -m unittest"""

import unittest

from ocusense.core.calibration import (
    STEPS, CalibrationError, EyeReference, GuidedCalibration, PersonalCalibration,
    build_eye_reference, combine, count_blinks, robust_reference,
)

FPS = 30


def jitter(value, n, amount=0.004):
    """n values that wobble slightly around value, like real measurements."""
    return [value + amount * ((i % 5) - 2) / 2 for i in range(n)]


class ReferenceTest(unittest.TestCase):
    def test_median_ignores_a_stray_blink(self):
        samples = jitter(0.30, 40) + [0.08, 0.09]  # two frames of an accidental blink
        median, spread = robust_reference(samples)
        self.assertAlmostEqual(median, 0.30, places=2)
        self.assertLess(spread, 0.01)

    def test_good_calibration(self):
        ref = build_eye_reference("left", jitter(0.30, 40), jitter(0.10, 40))
        self.assertAlmostEqual(ref.openness(0.30), 1.0, places=1)
        self.assertAlmostEqual(ref.openness(0.10), 0.0, places=1)
        self.assertAlmostEqual(ref.openness(0.20), 0.5, places=1)

    def test_openness_is_clipped(self):
        ref = EyeReference(open_ear=0.30, closed_ear=0.10)
        self.assertEqual(ref.openness(0.02), 0.0)
        self.assertEqual(ref.openness(0.45), 1.0)

    def test_rejects_too_few_frames(self):
        with self.assertRaisesRegex(CalibrationError, "Not enough"):
            build_eye_reference("left", jitter(0.30, 5), jitter(0.10, 40))

    def test_rejects_open_and_closed_too_similar(self):
        with self.assertRaisesRegex(CalibrationError, "too similar"):
            build_eye_reference("left", jitter(0.30, 40), jitter(0.27, 40))

    def test_rejects_closed_higher_than_open(self):
        with self.assertRaises(CalibrationError):
            build_eye_reference("left", jitter(0.10, 40), jitter(0.30, 40))

    def test_rejects_unstable_measurements(self):
        wobbly_open = [0.20, 0.40] * 20
        with self.assertRaisesRegex(CalibrationError, "unstable"):
            build_eye_reference("left", wobbly_open, jitter(0.10, 40))

    def test_works_for_any_eye_size(self):
        # Two very different eye shapes both map to the same 0..1 scale.
        narrow = build_eye_reference("left", jitter(0.18, 40), jitter(0.07, 40))
        wide = build_eye_reference("left", jitter(0.36, 40), jitter(0.12, 40))
        for ref in (narrow, wide):
            self.assertAlmostEqual(ref.openness(ref.open_ear), 1.0)
            self.assertAlmostEqual(ref.openness(ref.closed_ear), 0.0)


class CombineTest(unittest.TestCase):
    def setUp(self):
        # Asymmetric eyes: the right eye is naturally narrower.
        self.cal = PersonalCalibration(
            left=EyeReference(open_ear=0.30, closed_ear=0.10),
            right=EyeReference(open_ear=0.22, closed_ear=0.08),
        )

    def test_both_open(self):
        self.assertAlmostEqual(self.cal.openness({"left": 0.30, "right": 0.22})[2], 1.0)

    def test_both_closed(self):
        self.assertAlmostEqual(self.cal.openness({"left": 0.10, "right": 0.08})[2], 0.0)

    def test_combine_is_average(self):
        self.assertAlmostEqual(combine(1.0, 0.0), 0.5)

    def test_wink_is_not_a_blink(self):
        wink = self.cal.openness({"left": 0.30, "right": 0.08})[2]
        opened = self.cal.openness({"left": 0.30, "right": 0.22})[2]
        self.assertEqual(count_blinks([opened, wink, opened]), 0)

    def test_per_eye_values_see_the_wink(self):
        frames = [{"left": 0.30, "right": 0.22}, {"left": 0.30, "right": 0.08}, {"left": 0.30, "right": 0.22}]
        values = [self.cal.openness(ears) for ears in frames]
        self.assertEqual(count_blinks([v[0] for v in values]), 0)  # left eye stayed open
        self.assertEqual(count_blinks([v[1] for v in values]), 1)  # right eye winked
        self.assertEqual(count_blinks([v[2] for v in values]), 0)  # both together: no blink


def run_guided(open_ear, closed_ear, blink_ears, unreliable=lambda t: False):
    """Simulate the whole guided calibration at 30 frames per second.

    blink_ears(t) gives the EAR during the blink step (t = seconds into it).
    """
    cal = GuidedCalibration()
    cal.start(0.0)
    now = 0.0
    while cal.status == GuidedCalibration.RUNNING and now < 120:
        step = cal.step
        t = now - cal._step_start - step.get_ready_seconds
        if step.name == "open" or t < 0:
            ear = open_ear
        elif step.name == "closed":
            ear = closed_ear
        else:
            ear = blink_ears(t)
        ears = None if unreliable(now) else {"left": ear, "right": ear * 0.9}
        cal.update(now, ears)
        now += 1 / FPS
    return cal


def five_blinks(t):
    """Open eyes with a 0.15-second blink every second."""
    return 0.09 if (t % 1.0) < 0.15 else 0.30


class GuidedCalibrationTest(unittest.TestCase):
    def test_three_steps(self):
        self.assertEqual([s.name for s in STEPS], ["open", "closed", "blinks"])

    def test_successful_calibration(self):
        cal = run_guided(0.30, 0.10, five_blinks)
        self.assertEqual(cal.status, GuidedCalibration.DONE, cal.error)
        self.assertAlmostEqual(cal.result.left.open_ear, 0.30, places=2)
        self.assertAlmostEqual(cal.result.left.closed_ear, 0.10, places=2)
        self.assertAlmostEqual(cal.result.right.open_ear, 0.27, places=2)

    def test_fails_if_eyes_never_closed(self):
        cal = run_guided(0.30, 0.29, five_blinks)
        self.assertEqual(cal.status, GuidedCalibration.FAILED)
        self.assertIn("too similar", cal.error)

    def test_fails_if_no_blinks(self):
        cal = run_guided(0.30, 0.10, lambda t: 0.30)
        self.assertEqual(cal.status, GuidedCalibration.FAILED)
        self.assertIn("blink", cal.error)

    def test_fails_if_face_lost_whole_time(self):
        cal = run_guided(0.30, 0.10, five_blinks, unreliable=lambda now: True)
        self.assertEqual(cal.status, GuidedCalibration.FAILED)
        self.assertIn("Not enough", cal.error)

    def test_short_tracking_gap_is_tolerated(self):
        # Half a second of lost tracking during the open step is just skipped.
        cal = run_guided(0.30, 0.10, five_blinks, unreliable=lambda now: 4.0 <= now < 4.5)
        self.assertEqual(cal.status, GuidedCalibration.DONE, cal.error)

    def test_restart_clears_previous_result(self):
        cal = run_guided(0.30, 0.10, five_blinks)
        cal.start(200.0)
        self.assertEqual(cal.status, GuidedCalibration.RUNNING)
        self.assertIsNone(cal.result)


if __name__ == "__main__":
    unittest.main()
