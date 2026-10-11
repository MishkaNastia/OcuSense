"""Start the OcuSense desktop app (also used by the packaged OcuSense.app).

Options:
  --demo-history   fill Statistics with clearly labelled demo sessions
  --demo-wallet    developer test wallet: 1000 test coins in a separate collection file, for trying the Art
                   shop (never mixed with the real collection; also OCUSENSE_DEMO_WALLET=1)
  --self-test      check a build without a camera: model loads, one frame is analysed
  --notification-test  send one test Mac notification and quit (check name, icon and permission)
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ocusense.config import MODEL_PATH
from ocusense.system import IS_MAC

from . import theme
from .main_window import MainWindow


def _self_test(window: MainWindow) -> int:
    import numpy as np

    result = window.monitor.process(np.zeros((480, 640, 3), np.uint8), now=1.0)
    report = f"OcuSense self-test OK · model: {MODEL_PATH} · face found: {result.landmarks is not None}"
    print(report)
    log = os.environ.get("OCUSENSE_SELF_TEST_LOG")  # a windowed Windows build has no console to print to
    if log:
        with open(log, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0


def _fail(message: str, details: str = "") -> int:
    """Show a startup problem in a window (the packaged app has no terminal) and on stderr."""
    print(message, details, file=sys.stderr)
    if "--self-test" not in sys.argv:
        box = QMessageBox(QMessageBox.Icon.Critical, "OcuSense can’t start", message)
        if details:
            box.setDetailedText(details)
        box.exec()
    return 1


def _notification_test() -> int:
    import time

    from ocusense import notifications
    sent = notifications.post("Go easy on your eyes and move back a little. (Test)", "Trying to lick the screen?")
    time.sleep(3)  # macOS answers asynchronously; give it a moment before quitting
    print("notification requested" if sent else "notifications unavailable here")
    return 0 if sent else 1


def run() -> int:
    if "--notification-test" in sys.argv:
        return _notification_test()
    app = QApplication(sys.argv)
    app.setApplicationName("OcuSense")
    app.setStyle("Fusion")  # predictable styling; our own colours come from the style sheet
    app.setStyleSheet(theme.STYLE_SHEET)
    if not IS_MAC:  # macOS takes the icon from OcuSense.app; Windows needs it on the windows themselves
        from .menu_bar import tray_icon
        app.setWindowIcon(tray_icon())
    # Let Tab reach every button on macOS, not only text fields.
    app.styleHints().setTabFocusBehavior(Qt.TabFocusBehavior.TabFocusAllControls)

    if not MODEL_PATH.exists():
        return _fail("The face model file is missing.",
                     f"Expected at: {MODEL_PATH}\nDuring development, run:  python download_model.py")
    try:
        window = MainWindow(demo_history="--demo-history" in sys.argv,
                            demo_wallet="--demo-wallet" in sys.argv or bool(os.environ.get("OCUSENSE_DEMO_WALLET")))
    except Exception as error:  # e.g. MediaPipe's native library or a damaged model file
        return _fail("The eye-tracking model could not be loaded.", f"{type(error).__name__}: {error}")

    if "--self-test" in sys.argv:
        code = _self_test(window)
        window.close()
        return code
    window.show()
    return app.exec()
