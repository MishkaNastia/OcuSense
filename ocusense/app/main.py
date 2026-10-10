"""Start the OcuSense desktop app."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ocusense.core.monitor import MODEL_PATH

from . import theme
from .window import MainWindow


def run():
    if not MODEL_PATH.exists():
        print(f"Model file not found: {MODEL_PATH}\nRun this first:  python download_model.py")
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("OcuSense")
    app.setStyle("Fusion")  # predictable styling; our own colours come from the style sheet
    app.setStyleSheet(theme.STYLE_SHEET)
    # Let Tab reach every button on macOS, not only text fields.
    app.styleHints().setTabFocusBehavior(Qt.TabFocusBehavior.TabFocusAllControls)
    window = MainWindow()
    window.show()
    return app.exec()
