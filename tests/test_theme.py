"""Themes: Miró (default) and Keith Haring, chosen in Settings and applied when OcuSense opens."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ocusense.preferences import Preferences

ROOT = Path(__file__).resolve().parents[1]


def theme_in_fresh_process(preferences: dict) -> dict:
    """Import the theme in a new Python with the given preferences file (the theme is read at import)."""
    folder = tempfile.mkdtemp()
    (Path(folder) / "p.json").write_text(json.dumps(preferences))
    code = ("import json; from ocusense.ui import theme; "
            "print(json.dumps(dict(active=theme.ACTIVE, paper=theme.PAPER, line=theme.LINE, "
            "sheet_line=('3px solid' in theme.STYLE_SHEET))))")
    env = dict(os.environ, OCUSENSE_PREFERENCES_FILE=str(Path(folder) / "p.json"), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


class ThemeTest(unittest.TestCase):
    def test_default_is_miro_and_haring_can_be_chosen(self):
        miro = theme_in_fresh_process({})
        self.assertEqual((miro["active"], miro["paper"], miro["line"]), ("miro", "#F6F0E1", 2))
        haring = theme_in_fresh_process({"theme": "haring"})
        self.assertEqual((haring["active"], haring["line"]), ("haring", 3))
        self.assertTrue(haring["sheet_line"])  # thicker black lines in the style sheet
        self.assertEqual(theme_in_fresh_process({"theme": "neon"})["active"], "miro")  # unknown: default

    def test_both_palettes_define_every_colour(self):
        from ocusense.ui import theme
        self.assertEqual(set(theme.THEMES["miro"]), set(theme.THEMES["haring"]))
        self.assertEqual(set(theme.THEMES), set(theme.THEME_NAMES))

    def test_preference_is_validated(self):
        path = Path(tempfile.mkdtemp()) / "p.json"
        path.write_text(json.dumps({"theme": "haring"}))
        self.assertEqual(Preferences.load(path).theme, "haring")
        path.write_text(json.dumps({"theme": 42}))
        self.assertEqual(Preferences.load(path).theme, "miro")


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class ThemeSettingTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None

    def tearDown(self):
        self.window.close()

    def test_choosing_a_theme_switches_at_once_without_closing(self):
        from PySide6.QtWidgets import QApplication
        from ocusense.ui import theme
        from ocusense.ui.widgets.haring_dancer import HaringDancer
        from ocusense.ui.widgets.painter_character import PainterCharacter
        w = self.window
        app = QApplication.instance()
        w.monitor.calibration = object()
        w._start_camera = lambda: (setattr(w, "thread", FakeThread()), True)[1]
        w.show()
        w.start()
        self.assertEqual(w.state, "monitoring")
        banner_sheet = w.distance_banner.styleSheet()
        self.assertIn(theme.THEMES["miro"]["CARD"], banner_sheet)
        try:
            w.settings_page.theme_switch.buttons["haring"].click()
            self.assertEqual(theme.ACTIVE, "haring")
            self.assertEqual(Preferences.load().theme, "haring")  # remembered for next time
            self.assertEqual(app.styleSheet(), theme.STYLE_SHEET)
            self.assertIn("#FFFFFF", w.distance_banner.styleSheet())  # baked-in colours swapped too
            self.assertIsInstance(w.sidebar.painter, HaringDancer)
            self.assertTrue(w.isVisible())  # nothing closed
            self.assertEqual(w.state, "monitoring")  # the session carries on
            self.assertFalse(w.sidebar.painter.grab().isNull())
        finally:
            w.settings_page.theme_switch.buttons["miro"].click()
        self.assertEqual(theme.ACTIVE, "miro")
        self.assertIsInstance(w.sidebar.painter, PainterCharacter)
        self.assertIn(theme.THEMES["miro"]["CARD"], w.distance_banner.styleSheet())

    def test_haring_dancers_draw_and_stay_still_without_animations(self):
        from ocusense.ui.widgets.haring_dancer import HaringDancer
        dancer = HaringDancer()
        dancer.resize(200, 118)
        self.assertFalse(dancer.grab().isNull())
        dancer.set_animations(False)
        self.assertFalse(dancer._timer.isActive())
        self.assertEqual(dancer._time(), 0.0)


if __name__ == "__main__":
    unittest.main()
