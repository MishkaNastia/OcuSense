"""The little Miró painter in the sidebar: where he sits, and that he follows the Animations switch."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.ui.widgets.painter_character import PainterCharacter, STEP  # noqa: E402
from tests.test_main_window import MODEL_PATH  # noqa: E402

app = QApplication.instance() or QApplication([])


class PainterCharacterTest(unittest.TestCase):
    def test_paints_and_still_when_animations_are_off(self):
        painter = PainterCharacter()
        painter.resize(200, 118)
        self.assertFalse(painter.grab().isNull())
        painter.set_animations(False)
        self.assertFalse(painter._timer.isActive())
        self.assertEqual(painter._state()[:3], (len(painter.MARKS), 0.0, 1.0))  # a finished painting, no motion

    def test_paints_the_marks_one_by_one(self):
        painter = PainterCharacter()
        painter._clock.restart()
        done, progress, opacity, _t = painter._state()
        self.assertEqual((done, opacity), (0, 1.0))
        self.assertLess(progress, 0.2)

    def test_animates_only_while_visible(self):
        painter = PainterCharacter()
        painter.set_animations(True)
        self.assertFalse(painter._timer.isActive())  # not shown yet
        painter.show()
        self.assertTrue(painter._timer.isActive())
        painter.hide()
        self.assertFalse(painter._timer.isActive())


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class PainterInSidebarTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None

    def tearDown(self):
        self.window.close()

    def test_sits_above_settings_and_follows_the_switch(self):
        sidebar = self.window.sidebar
        layout = sidebar.layout()
        index = [layout.itemAt(i).widget() for i in range(layout.count())]
        self.assertLess(index.index(sidebar.painter), index.index(sidebar.items["settings"]))
        self.assertGreater(index.index(sidebar.painter), index.index(sidebar.items["patterns"]))
        box = self.window.pomodoro_page.checks["animations"]
        box.setChecked(True)
        on = not self.window.pomodoro_page.reduce_motion
        self.assertEqual(sidebar.painter.animate, on)
        box.setChecked(False)
        self.assertFalse(sidebar.painter.animate)
        box.setChecked(True)


if __name__ == "__main__":
    unittest.main()
