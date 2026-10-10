"""Start the OcuSense desktop app."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ocusense.core.monitor import MODEL_PATH

from . import theme
from .window import MainWindow


def self_test(window):
    """Check a packaged build without a camera: model loads and a frame can be analysed."""
    import numpy as np

    result = window.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
    print(f"OcuSense self-test OK · model: {MODEL_PATH} · face found: {result.landmarks is not None}")
    return 0


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
    window = MainWindow(demo_history="--demo-history" in sys.argv)
    if "--self-test" in sys.argv:
        code = self_test(window)
        window.close()
        return code
    window.show()
    return app.exec()
