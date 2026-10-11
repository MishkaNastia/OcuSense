"""Checks for the posture maths and rules, with made-up matrices and landmarks. Run with:  python -m unittest"""

import math
import unittest

from ocusense.core.models import PostureBaseline, PostureReading, PostureStatus
from ocusense.core.posture import (
    HEAD_DROPPED, HEAD_TILTED, IRIS_EDGES, SLUMPED, TOO_CLOSE, PostureCalibration, PostureMonitor, PostureReminder,
    TiltWatcher,
    angle_difference, corrected_for_tilt, distance_cm, head_pose, iris_width_px, read_posture,
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


def reading(pitch=2.0, roll=1.0, distance=65.0, centre_y=0.45, size=0.30, lid=None):
    return PostureReading(pitch=pitch, yaw=0.0, roll=roll, distance_cm=distance, centre_y=centre_y, size=size,
                          lid_angle=lid)


SLUMP = dict(centre_y=0.6, size=0.36)  # lower and 20 % bigger


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
        r = read_posture(pose_matrix(10, 0, -5), face_points(centre=(0.5, 0.6), size=0.3, iris=0.018), 640, 480,
                         lid_angle=118.0)
        self.assertEqual((r.aspect, r.lid_angle), (640 / 480, 118.0))
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
    def record(self, readings, seconds=120.0):
        """Feed readings at 30 frames/s over `seconds`, the last one at the end."""
        cal = PostureCalibration(seconds=seconds)
        cal.start(0.0)
        n = int(seconds * 30)
        for i in range(n):
            cal.update(i / 30, readings(i))
        cal.update(seconds, readings(n))
        return cal

    def test_medians_after_the_recording(self):
        cal = self.record(lambda i: reading(pitch=50.0 if i % 100 == 0 else 2.0 + (i % 3) - 1,  # odd frames ignored
                                            distance=64.0 + (i % 3), lid=118.0))
        self.assertEqual(cal.status, PostureCalibration.DONE)
        self.assertEqual(cal.result.pitch, 2.0)
        self.assertEqual(cal.result.distance_cm, 65.0)
        self.assertEqual(cal.result.centre_y, 0.45)
        self.assertEqual(cal.result.lid_angle, 118.0)

    def test_still_running_before_the_end(self):
        cal = PostureCalibration()
        cal.start(0.0)
        cal.update(59.0, reading())
        self.assertEqual(cal.status, PostureCalibration.RUNNING)
        self.assertAlmostEqual(cal.seconds_left(40.0), 20.0)
        self.assertEqual(PostureCalibration().seconds_left(5.0), 0.0)

    def test_fails_without_enough_measured_frames(self):
        cal = self.record(lambda i: reading() if i < 200 else None)  # face seen for ~7 s of 120
        self.assertEqual(cal.status, PostureCalibration.FAILED)
        self.assertIn("try again", cal.error)
        self.assertIsNone(cal.result)

    def test_fails_when_the_posture_kept_changing(self):
        cal = self.record(lambda i: reading(pitch=-10.0 + 20.0 * ((i // 300) % 2)))  # head up and down in turns
        self.assertEqual(cal.status, PostureCalibration.FAILED)
        self.assertIn("kept changing", cal.error)

    def test_no_lid_angle_without_the_sensor(self):
        self.assertIsNone(self.record(lambda i: reading()).result.lid_angle)


class LimitTest(unittest.TestCase):
    def check(self, **change):
        return PostureMonitor(BASE).exceeded(reading(**change))

    def test_upright_is_within_all_limits(self):
        self.assertEqual(self.check(), set())

    def test_head_dropped_only_downwards(self):
        self.assertEqual(self.check(pitch=2.0 + 12.5), {HEAD_DROPPED})
        self.assertEqual(self.check(pitch=2.0 + 11.5), set())
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

    def test_slumped_means_lower_and_bigger(self):
        self.assertEqual(self.check(centre_y=0.45 + 0.06, size=0.30 * 1.06), {SLUMPED})
        self.assertEqual(self.check(centre_y=0.45 + 0.09, size=0.30), set())  # lower only: could be a tilted screen
        self.assertEqual(self.check(centre_y=0.45 + 0.04, size=0.40), set())
        self.assertEqual(self.check(centre_y=0.45 - 0.2, size=0.40), set())  # higher (sitting up more) is fine

    def test_with_the_lid_sensor_lower_alone_is_slumped(self):
        base = PostureBaseline(pitch=2.0, roll=1.0, distance_cm=65.0, centre_y=0.45, size=0.30, lid_angle=118.0)
        self.assertEqual(PostureMonitor(base).exceeded(reading(centre_y=0.45 + 0.06, lid=118.0)), {SLUMPED})


class SustainedRuleTest(unittest.TestCase):
    def run_frames(self, monitor, seconds, start=0.0, fps=30, **change):
        status = None
        for i in range(int(seconds * fps)):
            status = monitor.update(start + i / fps, reading(**change))
        return status

    def test_poor_only_after_twenty_seconds(self):
        monitor = PostureMonitor(BASE)
        status = self.run_frames(monitor, 19.9, **SLUMP)
        self.assertFalse(status.poor)
        self.assertEqual(status.outside, (SLUMPED,))
        self.assertGreater(status.longest_outside, 19)
        status = monitor.update(20.0, reading(**SLUMP))
        self.assertTrue(status.poor)
        self.assertEqual(status.problems, (SLUMPED,))
        self.assertAlmostEqual(status.centre_drop, 0.15)
        self.assertAlmostEqual(status.size_ratio, 1.2)

    def test_camera_wobble_doesnt_restart_the_count(self):
        monitor = PostureMonitor(BASE)
        status = None
        for i in range(int(21 * 30)):  # slumped for 21 s, but every 10th frame measures just inside the limit
            status = monitor.update(i / 30, reading() if i % 10 == 0 else reading(**SLUMP))
        self.assertTrue(status.poor)

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
        self.assertTrue(self.run_frames(monitor, 21, pitch=30.0).poor)
        status = self.run_frames(monitor, 3.5, start=21.0)  # sitting up again for more than the 3 s grace
        self.assertFalse(status.poor)
        self.assertEqual(status.outside, ())
        self.assertFalse(self.run_frames(monitor, 15, start=25.0, pitch=30.0).poor)  # counting from zero again

    def test_brief_tracking_loss_is_bridged(self):
        monitor = PostureMonitor(BASE)
        self.run_frames(monitor, 15, **SLUMP)
        self.assertFalse(monitor.update(15.0, None).tracked)  # face lost for 2 s
        self.assertFalse(monitor.update(16.9, None).tracked)
        self.assertTrue(self.run_frames(monitor, 6, start=17.0, **SLUMP).poor)  # 15 + 2 + 6 s: still one stretch

    def test_lost_face_for_longer_resets_like_lost_tracking(self):
        monitor = PostureMonitor(BASE)
        self.run_frames(monitor, 15, **SLUMP)
        monitor.update(15.0, None)
        monitor.update(19.0, None)  # 4 s without a face: more than the grace
        status = self.run_frames(monitor, 15, start=19.1, **SLUMP)  # 30 s slumped in total, but not in a row
        self.assertFalse(status.poor)

    def test_each_limit_has_its_own_timer(self):
        monitor = PostureMonitor(BASE)
        self.run_frames(monitor, 15, **SLUMP)  # slumped from 0 s
        status = self.run_frames(monitor, 10, start=15.0, roll=20.0, **SLUMP)  # also tilted from 15 s
        self.assertEqual(status.problems, (SLUMPED,))  # slumped 25 s; tilted only 10 s
        self.assertEqual(set(status.outside), {SLUMPED, HEAD_TILTED})



class ScreenTiltTest(unittest.TestCase):
    LID_BASE = PostureBaseline(pitch=2.0, roll=1.0, distance_cm=65.0, centre_y=0.45, size=0.30, lid_angle=118.0)

    def test_no_correction_without_the_sensor(self):
        self.assertEqual(corrected_for_tilt(reading(pitch=5.0, centre_y=0.5), BASE), (5.0, 0.5, None))
        self.assertEqual(corrected_for_tilt(reading(pitch=5.0, centre_y=0.5), self.LID_BASE)[2], None)  # no lid now

    def test_opening_the_screen_is_subtracted(self):
        # screen opened 5° further: the camera looks 5° up, so the head looks 5° more "chin down"
        # and the face sits 1.0 × 4/3 × tan(5°) ≈ 11.7 % of the frame height lower
        shift = 4 / 3 * math.tan(math.radians(5))
        pitch, centre_y, change = corrected_for_tilt(reading(pitch=7.0, centre_y=0.45 + shift, lid=123.0),
                                                     self.LID_BASE)
        self.assertAlmostEqual(pitch, 2.0)
        self.assertAlmostEqual(centre_y, 0.45)
        self.assertEqual(change, 5.0)

    def test_tilted_screen_isnt_bad_posture(self):
        shift = 4 / 3 * math.tan(math.radians(4))
        r = reading(pitch=6.0, centre_y=0.45 + shift, size=0.36, lid=122.0)  # 4° tilt, face looks lower
        self.assertEqual(PostureMonitor(BASE).exceeded(r), {SLUMPED})  # without the sensor this would look slumped
        self.assertEqual(PostureMonitor(self.LID_BASE).exceeded(r), set())
        status = PostureMonitor(self.LID_BASE).update(0.0, r)
        self.assertAlmostEqual(status.centre_drop, 0.0)
        self.assertEqual(status.lid_change, 4.0)


class TiltWatcherTest(unittest.TestCase):
    def feed(self, watcher, angles, start=0.0, step=0.5):
        return [t for i, a in enumerate(angles) if watcher.update(t := start + i * step, a)]

    def test_settled_tilt_gives_one_event(self):
        w = TiltWatcher()
        w.set_reference(118.0)
        moving = [118, 120, 123, 126, 129]  # being adjusted…
        resting = [129, 129, 130, 129, 129, 129, 129]  # …then left there
        events = self.feed(w, moving + resting)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], 4.0)  # it reached 129° at 2.0 s and stayed within ±1° until 4.0 s
        self.assertEqual(w.reference, 129.0)
        self.assertEqual(self.feed(w, [129] * 20, start=10.0), [])  # staying there: no more events

    def test_small_or_passing_moves_dont_count(self):
        w = TiltWatcher()
        w.set_reference(118.0)
        self.assertEqual(self.feed(w, [118, 120, 121, 122, 121, 120] * 5), [])  # under 5°
        self.assertEqual(self.feed(w, [118, 125, 131, 125, 118, 118], start=20.0), [])  # moved and came back

    def test_needs_a_reference_and_a_reading(self):
        w = TiltWatcher()
        self.assertEqual(self.feed(w, [140] * 10), [])
        w.set_reference(118.0)
        self.assertEqual(self.feed(w, [None] * 10), [])




class PostureReminderTest(unittest.TestCase):
    POOR = PostureStatus(tracked=True, poor=True, problems=(SLUMPED,))
    GOOD = PostureStatus(tracked=True)
    LOST = PostureStatus(tracked=False)

    def test_once_per_poor_stretch(self):
        r = PostureReminder()
        self.assertTrue(r.update(30.0, self.POOR))
        self.assertFalse(any(r.update(30.0 + i, self.POOR) for i in range(1, 900)))  # still poor, 15 min: no more

    def test_a_new_stretch_after_the_gap(self):
        r = PostureReminder(gap_seconds=600)
        self.assertTrue(r.update(0.0, self.POOR))
        r.update(60.0, self.GOOD)
        self.assertFalse(r.update(300.0, self.POOR))  # a new stretch, but within 10 min of the last message
        r.update(400.0, self.GOOD)
        self.assertTrue(r.update(700.0, self.POOR))  # a new stretch, 11+ min later

    def test_lost_face_doesnt_end_a_stretch(self):
        r = PostureReminder(gap_seconds=0)
        self.assertTrue(r.update(0.0, self.POOR))
        r.update(1.0, self.LOST)
        r.update(2.0, None)
        self.assertFalse(r.update(3.0, self.POOR))  # same stretch: no second message


if __name__ == "__main__":
    unittest.main()
