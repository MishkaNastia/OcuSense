"""Start the OcuSense desktop app (also used by the packaged OcuSense.app).

Options:
  --demo-history   fill Statistics with clearly labelled demo sessions
  --self-test      check a build without a camera: model loads, one frame is analysed
  --notification-test  send every kind of notification once (test copies) and quit: check the
                       name, icon, permission and wording of each
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ocusense.config import MODEL_PATH
from ocusense.system import IS_MAC, keep_running_in_background, set_windows_app_id

from . import theme, window_chrome
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


def all_notifications() -> list[tuple[str, str]]:
    """Every notification OcuSense can send, as (title, message), for --notification-test."""
    from .eye_rest_card import BODY as EYE_REST_BODY, TITLE as EYE_REST_TITLE
    from .lighting_card import BODY as LIGHTING_BODY, TITLE as LIGHTING_TITLE
    from .blink_garden_page import GARDEN_BODY, GARDEN_TITLE
    from .main_window import BREAK_MESSAGE, DISTANCE_BODY, DISTANCE_TITLE, POMODORO_MESSAGES, TILT_MESSAGE
    return ([(DISTANCE_TITLE, DISTANCE_BODY), ("Time for a break", BREAK_MESSAGE),
             (EYE_REST_TITLE, EYE_REST_BODY), (LIGHTING_TITLE, LIGHTING_BODY), ("OcuSense", TILT_MESSAGE),
             (GARDEN_TITLE, GARDEN_BODY)]
            + [POMODORO_MESSAGES[phase] for phase in ("short_break", "long_break", "focus")])


def _notification_test() -> int:
    """Send every kind of notification once, a couple of seconds apart, then quit."""
    import time

    from ocusense import notifications
    sent = 0
    for title, message in all_notifications():
        if notifications.post(f"{message} (Test)", title):
            sent += 1
        time.sleep(2)  # one at a time, so each can be read
    time.sleep(3)  # macOS answers asynchronously; give it a moment before quitting
    print(f"{sent} notifications requested" if sent else "notifications unavailable here")
    return 0 if sent else 1


def run() -> int:
    if "--notification-test" in sys.argv:
        return _notification_test()
    set_windows_app_id()  # before any window or notification exists
    app = QApplication(sys.argv)
    app.setApplicationName("OcuSense")
    app.setStyle("Fusion")  # predictable styling; our own colours come from the style sheet
    app.setStyleSheet(theme.STYLE_SHEET)
    keep_running_in_background()  # macOS: no App Nap, so timers and notifications stay on time
    if not IS_MAC:  # macOS takes the icon from OcuSense.app; Windows needs it on the windows themselves
        from .menu_bar import tray_icon
        app.setWindowIcon(tray_icon())
    # Let Tab reach every button on macOS, not only text fields.
    app.styleHints().setTabFocusBehavior(Qt.TabFocusBehavior.TabFocusAllControls)
    window_chrome.install(app)  # no grey title bar on any window (macOS)

    if not MODEL_PATH.exists():
        return _fail("The face model file is missing.",
                     f"Expected at: {MODEL_PATH}\nDuring development, run:  python download_model.py")
    try:
        window = MainWindow(demo_history="--demo-history" in sys.argv)
    except Exception as error:  # e.g. MediaPipe's native library or a damaged model file
        return _fail("The eye tracking model couldn’t be loaded.", f"{type(error).__name__}: {error}")

    if "--self-test" in sys.argv:
        code = _self_test(window)
        window.close()
        return code
    window.show()
    return app.exec()
