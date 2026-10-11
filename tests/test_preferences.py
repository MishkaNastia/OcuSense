"""Remembered Settings choices: saved between launches, never trusted when invalid."""

import json
import tempfile
import unittest
from pathlib import Path

from ocusense.preferences import Preferences


class PreferencesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "OcuSense" / "preferences.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_defaults_without_a_file(self):
        prefs = Preferences.load(self.path)
        self.assertTrue(prefs.distance_reminder)
        self.assertEqual(prefs.distance_reminder_interval, 300)

    def test_round_trip(self):
        Preferences(distance_reminder=False, distance_reminder_interval=5).save(self.path)
        prefs = Preferences.load(self.path)
        self.assertFalse(prefs.distance_reminder)
        self.assertEqual(prefs.distance_reminder_interval, 5)

    def test_posture_monitoring_is_off_until_ticked(self):
        self.assertFalse(Preferences.load(self.path).posture_monitoring)
        Preferences(posture_monitoring=True).save(self.path)
        self.assertTrue(Preferences.load(self.path).posture_monitoring)
        self.path.write_text(json.dumps({"posture_monitoring": "yes"}))
        self.assertFalse(Preferences.load(self.path).posture_monitoring)  # not a tick: off

    def test_invalid_values_fall_back_to_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"distance_reminder": "yes", "distance_reminder_interval": 7}))
        prefs = Preferences.load(self.path)
        self.assertTrue(prefs.distance_reminder)
        self.assertEqual(prefs.distance_reminder_interval, 300)  # 7 s isn't one of the choices

    def test_damaged_file_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{oops")
        self.assertEqual(Preferences.load(self.path), Preferences())


if __name__ == "__main__":
    unittest.main()
