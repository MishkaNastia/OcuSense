"""Guards for the project structure. Run with:  python -m unittest

These fail if someone accidentally makes core depend on the camera or the
interface, or makes the interface re-implement measurement logic.
"""

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

from ocusense import config

ROOT = Path(__file__).resolve().parent.parent


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class ArchitectureTest(unittest.TestCase):
    def test_core_is_pure(self):
        forbidden = ("PySide6", "cv2", "mediapipe", "ocusense.ui", "ocusense.monitoring")
        for path in (ROOT / "ocusense" / "core").glob("*.py"):
            for module in imported_modules(path):
                with self.subTest(file=path.name, module=module):
                    self.assertFalse(module.startswith(forbidden), f"{path.name} imports {module}")

    def test_interface_does_not_reimplement_measurements(self):
        # The UI shows results; EAR and the blink rule must only live in core.
        forbidden = ("ocusense.core.eye_metrics", "ocusense.core.blink_counter", "cv2", "mediapipe")
        for path in (ROOT / "ocusense" / "ui").rglob("*.py"):
            for module in imported_modules(path):
                with self.subTest(file=path.name, module=module):
                    self.assertFalse(module.startswith(forbidden), f"{path.name} imports {module}")


class ConfigTest(unittest.TestCase):
    def test_blink_thresholds_are_ordered(self):
        self.assertLess(config.CLOSE_BELOW, config.REOPEN_ABOVE)

    def test_model_path_during_development(self):
        self.assertEqual(config.resource_path(config.MODEL_RELATIVE_PATH), ROOT / "models" / "face_landmarker.task")

    def test_model_path_inside_packaged_app(self):
        with mock.patch.object(sys, "_MEIPASS", "/Applications/OcuSense.app/Contents/Frameworks", create=True):
            self.assertEqual(config.resource_path(config.MODEL_RELATIVE_PATH),
                             Path("/Applications/OcuSense.app/Contents/Frameworks/models/face_landmarker.task"))


if __name__ == "__main__":
    unittest.main()
