"""Checks for the EAR maths and tracking-quality rules. Run with:  python -m unittest"""

import unittest
from types import SimpleNamespace

from eye_metrics import EYE_LANDMARKS, eye_aspect_ratio, measure_eyes


def fake_landmarks(eyes):
    """478 landmarks at the centre, with the given eyes' six points placed.

    eyes: {"left": (cx, cy, w, h), "right": ...} in MediaPipe's 0-1 units.
    """
    points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
    for name, (cx, cy, w, h) in eyes.items():
        p1, p2, p3, p4, p5, p6 = EYE_LANDMARKS[name]
        layout = {
            p1: (cx - w / 2, cy), p4: (cx + w / 2, cy),
            p2: (cx - w / 6, cy - h / 2), p3: (cx + w / 6, cy - h / 2),
            p6: (cx - w / 6, cy + h / 2), p5: (cx + w / 6, cy + h / 2),
        }
        for index, (x, y) in layout.items():
            points[index] = SimpleNamespace(x=x, y=y)
    return points


class EarTest(unittest.TestCase):
    def test_ear_formula(self):
        # width 100, both vertical distances 30 -> EAR = 60 / 200 = 0.3
        points = [(0, 0), (30, -15), (70, -15), (100, 0), (70, 15), (30, 15)]
        self.assertAlmostEqual(eye_aspect_ratio(points), 0.3)

    def test_closed_eye_has_lower_ear(self):
        open_eye = [(0, 0), (30, -15), (70, -15), (100, 0), (70, 15), (30, 15)]
        closed_eye = [(0, 0), (30, -2), (70, -2), (100, 0), (70, 2), (30, 2)]
        self.assertLess(eye_aspect_ratio(closed_eye), eye_aspect_ratio(open_eye))

    def test_ear_ignores_size_and_rotation(self):
        small = [(0, 0), (30, -15), (70, -15), (100, 0), (70, 15), (30, 15)]
        big_rotated = [(-2 * y, 2 * x) for x, y in small]  # 2x bigger, turned 90 degrees
        self.assertAlmostEqual(eye_aspect_ratio(small), eye_aspect_ratio(big_rotated))

    def test_zero_width_is_none(self):
        self.assertIsNone(eye_aspect_ratio([(0, 0)] * 6))

    def test_uses_pixel_coordinates(self):
        # In 0-1 units this eye is 0.1 wide and 0.0333 tall (EAR 0.333),
        # but a 640x480 frame stretches x more: 64 px wide, 16 px tall -> 0.25.
        eye = (0.1, 1 / 30)
        landmarks = fake_landmarks({"left": (0.4, 0.5, *eye), "right": (0.6, 0.5, *eye)})
        result = measure_eyes(landmarks, 640, 480)
        self.assertAlmostEqual(result.ears["left"], 0.25)
        self.assertTrue(result.reliable)


class TrackingQualityTest(unittest.TestCase):
    def test_face_turned_is_unreliable(self):
        landmarks = fake_landmarks({"left": (0.4, 0.5, 0.1, 0.03), "right": (0.6, 0.5, 0.04, 0.012)})
        result = measure_eyes(landmarks, 640, 480)
        self.assertFalse(result.reliable)
        self.assertIn("head turned", result.reason)

    def test_face_too_small_is_unreliable(self):
        landmarks = fake_landmarks({"left": (0.48, 0.5, 0.01, 0.003), "right": (0.52, 0.5, 0.01, 0.003)})
        self.assertFalse(measure_eyes(landmarks, 640, 480).reliable)

    def test_eye_outside_picture_is_unreliable(self):
        landmarks = fake_landmarks({"left": (0.0, 0.5, 0.1, 0.03), "right": (0.2, 0.5, 0.1, 0.03)})
        self.assertFalse(measure_eyes(landmarks, 640, 480).reliable)


if __name__ == "__main__":
    unittest.main()
