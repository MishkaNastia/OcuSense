"""Checks for the posture maths and rules, with made-up matrices and landmarks. Run with:  python -m unittest"""

import math
import unittest

from ocusense.core.models import PostureBaseline, PostureReading
from ocusense.core.posture import (
    HEAD_DROPPED, HEAD_TILTED, IRIS_EDGES, SLUMPED, TOO_CLOSE, PostureCalibration, PostureMonitor, angle_difference,
    distance_cm, head_pose, iris_width_px, read_posture,
)


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def pose_matrix(pitch=0.0, yaw=0.0, roll=0.0):
    """4x4 rows with rotation Rz(roll) · Ry(yaw) · Rx(pitch) (degrees) and a translation."""
    p, y, r = (math.radians(v) for v in (pitch, yaw, roll))
    rx = [[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]]
    ry = [[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]]
    rz = [[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]]
    rot = matmul(rz, matmul(ry, rx))
    return [rot[0] + [1.0], rot[1] + [-2.0], rot[2] + [-50.0], [0, 0, 0, 1]]


def face_points(centre=(0.5, 0.5), size=0.3, iris=0.02):
    """478 points (0–1 units) spread over a square face, with both irises `iris` wide."""
    cx, cy = centre
    points = [(cx - size / 2 + size * (i % 22) / 21, cy - size / 2 + size * (i // 22) / 21) for i in range(478)]
    for k, (a, b) in enumerate(IRIS_EDGES):
        ex = cx + (-0.08 if k == 0 else 0.08)
        points[a] = (ex - iris / 2, cy - 0.05)
        points[b] = (ex + iris / 2, cy - 0.05)
    return points


BASE = PostureBaseline(pitch=2.0, roll=1.0, distance_cm=65.0, centre_y=0.45, size=0.30)


def reading(pitch=2.0, roll=1.0, distance=65.0, centre_y=0.45, size=0.30):
    return PostureReading(pitch=pitch, yaw=0.0, roll=roll, distance_cm=distance, centre_y=centre_y, size=size)


class HeadPoseTest(unittest.TestCase):
    def test_upright_is_zero(self):
        for value in head_pose(pose_matrix()):
            self.assertAlmostEqual(value, 0.0)

    def test_each_angle_on_its_own(self):
        for pitch, yaw, roll in [(20, 0, 0), (0, -30, 0), (0, 0, 12), (-10, 0, 0)]:
            got = head_pose(pose_matrix(pitch, yaw, roll))
            for g, want in zip(got, (pitch, yaw, roll)):
                self.assertAlmostEqual(g, want, places=6)

    def test_combined_angles(self):
        got = head_pose(pose_matrix(15, 25, -8))
        for g, want in zip(got, (15, 25, -8)):
            self.assertAlmostEqual(g, want, places=6)

    def test_rounding_past_one_does_not_crash(self):
        m = pose_matrix(0, 90, 0)
        m[2][0] = -1.0000001
        self.assertAlmostEqual(head_pose(m)[1], 90.0, places=3)

    def test_angle_difference_wraps(self):
        self.assertAlmostEqual(angle_difference(179, -179), -2)
        self.assertAlmostEqual(angle_difference(-179, 179), 2)


class DistanceTest(unittest.TestCase):
    def test_distance_from_iris_width(self):
        # 640 px frame, focal 640 px, iris 11.7 mm: 11.52 px wide → 640 × 11.7 / 11.52 mm = 65 cm
        self.assertAlmostEqual(distance_cm(11.52, 640), 65.0)

    def test_twice_as_wide_is_half_as_far(self):
        self.assertAlmostEqual(distance_cm(20.0, 640) / distance_cm(40.0, 640), 2.0)

    def test_focal_length_scales_the_estimate(self):
        self.assertAlmostEqual(distance_cm(10.0, 640, focal_per_width=0.87), 0.87 * distance_cm(10.0, 640))

    def test_iris_width_uses_pixels_and_both_eyes(self):
        points = face_points(iris=0.02)
        self.assertAlmostEqual(iris_width_px(points, 640, 480), 0.02 * 640)

    def test_no_iris_landmarks(self):
        self.assertIsNone(iris_width_px(face_points()[:468], 640, 480))
        self.assertIsNone(distance_cm(None, 640))

    def test_read_posture(self):
        r = read_posture(pose_matrix(10, 0, -5), face_points(centre=(0.5, 0.6), size=0.3, iris=0.018), 640, 480)
        self.assertAlmostEqual(r.pitch, 10)
        self.assertAlmostEqual(r.roll, -5)
        self.assertAlmostEqual(r.centre_y, 0.6)
        self.assertAlmostEqual(r.size, 0.3)
        self.assertAlmostEqual(r.distance_cm, 640 * 11.7 / (0.018 * 640) / 10)

    def test_without_matrix_or_face(self):
        r = read_posture(None, face_points(), 640, 480)
        self.assertIsNone(r.pitch)
        self.assertIsNone(read_posture(None, [], 640, 480))


class CalibrationTest(unittest.TestCase):
    def test_medians_after_three_seconds(self):
        cal = PostureCalibration()
        cal.start(0.0)
        for i in range(90):  # 30 frames/s
            pitch = 50.0 if i == 10 else 2.0  # one odd frame doesn't move the median
            cal.update(i / 30, reading(pitch=pitch, distance=64.0 + (i % 3)))
            self.assertEqual(cal.status, PostureCalibration.RUNNING)
        cal.update(3.0, reading())
        self.assertEqual(cal.status, PostureCalibration.DONE)
        self.assertEqual(cal.result.pitch, 2.0)
        self.assertEqual(cal.result.distance_cm, 65.0)
        self.assertEqual(cal.result.centre_y, 0.45)

    def test_fails_without_enough_measured_frames(self):
        cal = PostureCalibration()
        cal.start(0.0)
        for i in range(91):
            cal.update(i / 30, reading() if i < 5 else None)
        self.assertEqual(cal.status, PostureCalibration.FAILED)
        self.assertIn("try again", cal.error)
        self.assertIsNone(cal.result)

    def test_seconds_left(self):
        cal = PostureCalibration()
        self.assertEqual(cal.seconds_left(5.0), 0.0)
        cal.start(1.0)
        self.assertAlmostEqual(cal.seconds_left(2.0), 2.0)


class LimitTest(unittest.TestCase):
    def check(self, **change):
        return PostureMonitor(BASE).exceeded(reading(**change))

    def test_upright_is_within_all_limits(self):
        self.assertEqual(self.check(), set())

    def test_head_dropped_only_downwards(self):
        self.assertEqual(self.check(pitch=2.0 + 15.5), {HEAD_DROPPED})
        self.assertEqual(self.check(pitch=2.0 + 14.5), set())
        self.assertEqual(self.check(pitch=2.0 - 25), set())  # looking up isn't "dropped"

    def test_tilt_either_way(self):
        self.assertEqual(self.check(roll=1.0 + 11), {HEAD_TILTED})
        self.assertEqual(self.check(roll=1.0 - 11), {HEAD_TILTED})
        self.assertEqual(self.check(roll=1.0 + 9), set())

    def test_too_close_absolute_and_relative(self):
        self.assertEqual(self.check(distance=49.0), {TOO_CLOSE})  # under 50 cm
        self.assertEqual(self.check(distance=51.0), {TOO_CLOSE})  # > 20 % closer than 65 cm (< 52 cm)
        self.assertEqual(self.check(distance=53.0), set())
        far = PostureMonitor(PostureBaseline(2.0, 1.0, 100.0, 0.45, 0.3))
        self.assertEqual(far.exceeded(reading(distance=79.0)), {TOO_CLOSE})  # 21 % closer, still far away

    def test_slumped_means_lower_in_the_picture(self):
        self.assertEqual(self.check(centre_y=0.45 + 0.09), {SLUMPED})
        self.assertEqual(self.check(centre_y=0.45 + 0.07), set())
        self.assertEqual(self.check(centre_y=0.45 - 0.2), set())  # higher (sitting up more) is fine


class SustainedRuleTest(unittest.TestCase):
    def run_frames(self, monitor, seconds, start=0.0, fps=30, **change):
        status = None
        for i in range(int(seconds * fps)):
            status = monitor.update(start + i / fps, reading(**change))
        return status

    def test_poor_only_after_thirty_seconds(self):
        monitor = PostureMonitor(BASE)
        status = self.run_frames(monitor, 29.9, centre_y=0.6)
        self.assertFalse(status.poor)
        self.assertEqual(status.outside, (SLUMPED,))
        self.assertGreater(status.longest_outside, 29)
        status = monitor.update(30.0, reading(centre_y=0.6))
        self.assertTrue(status.poor)
        self.assertEqual(status.problems, (SLUMPED,))
        self.assertAlmostEqual(status.centre_drop, 0.15)

    def test_short_glance_never_counts(self):
        monitor = PostureMonitor(BASE)
        t = 0.0
        for _ in range(20):  # a 5 s glance down every 10 s for 200 s
            self.assertFalse(self.run_frames(monitor, 5, start=t, pitch=40.0).poor)
            self.assertFalse(self.run_frames(monitor, 5, start=t + 5).poor)
            t += 10
        self.assertFalse(monitor.update(t, reading()).poor)

    def test_back_within_limits_clears_and_restarts_the_count(self):
        monitor = PostureMonitor(BASE)
        self.assertTrue(self.run_frames(monitor, 31, pitch=30.0).poor)
        status = monitor.update(31.0, reading())
        self.assertFalse(status.poor)
        self.assertEqual(status.outside, ())
        self.assertFalse(self.run_frames(monitor, 20, start=32.0, pitch=30.0).poor)  # counting from zero again

    def test_lost_face_resets_like_lost_tracking(self):
        monitor = PostureMonitor(BASE)
        self.run_frames(monitor, 20, centre_y=0.6)
        self.assertFalse(monitor.update(20.0, None).tracked)
        status = self.run_frames(monitor, 20, start=20.1, centre_y=0.6)  # 40 s slumped in total, but not in a row
        self.assertFalse(status.poor)

    def test_each_limit_has_its_own_timer(self):
        monitor = PostureMonitor(BASE)
        self.run_frames(monitor, 20, centre_y=0.6)  # slumped from 0 s
        status = self.run_frames(monitor, 15, start=20.0, centre_y=0.6, roll=20.0)  # also tilted from 20 s
        self.assertEqual(status.problems, (SLUMPED,))  # slumped 35 s; tilted only 15 s
        self.assertEqual(set(status.outside), {SLUMPED, HEAD_TILTED})


if __name__ == "__main__":
    unittest.main()
