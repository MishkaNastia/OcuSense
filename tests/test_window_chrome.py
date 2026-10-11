"""The transparent macOS title bar: harmless elsewhere, applied once per window, before it shows."""

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QVBoxLayout, QWidget  # noqa: E402

from ocusense.ui import window_chrome  # noqa: E402

app = QApplication.instance() or QApplication([])
window_chrome.install(app)


class ChromeTest(unittest.TestCase):
    def test_off_the_mac_nothing_changes(self):
        with mock.patch.object(sys, "platform", "linux"):
            dialog = QDialog()
            dialog.show()
            self.assertFalse(dialog.windowFlags() & window_chrome.NO_BACKGROUND)
            dialog.close()

    def test_on_the_mac_a_dialog_gets_the_hints_once_and_moves_down(self):
        with mock.patch.object(sys, "platform", "darwin"):
            dialog = QDialog()
            dialog.setWindowTitle("Clear history?")
            QVBoxLayout(dialog).setContentsMargins(10, 10, 10, 10)
            dialog.show()
            dialog.hide()
            dialog.show()
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.windowFlags() & window_chrome.NO_BACKGROUND)
            self.assertTrue(dialog.windowFlags() & window_chrome.EXPANDED)
            self.assertEqual(dialog.windowTitle().strip(), "")
            self.assertEqual(dialog.layout().contentsMargins().top(), 10 + window_chrome.TITLE_BAR_HEIGHT)
            dialog.close()

    def test_main_window_moves_its_own_content(self):
        class Window(QMainWindow):
            moved = 0

            def title_bar_blended(self, height):
                self.moved += height
        with mock.patch.object(sys, "platform", "darwin"):
            window = Window()
            window.setCentralWidget(QWidget())
            window.show()
            self.assertEqual(window.moved, window_chrome.TITLE_BAR_HEIGHT)
            window.close()

    def test_frameless_sheets_are_left_alone(self):
        with mock.patch.object(sys, "platform", "darwin"):
            sheet = QDialog(None, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
            sheet.show()
            self.assertFalse(sheet.property("ocusense_chrome"))
            sheet.close()


if __name__ == "__main__":
    unittest.main()
