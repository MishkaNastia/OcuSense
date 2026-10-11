"""The OcuSense eye in the macOS menu bar (or the Windows system tray), with a small menu.

    Monitoring · 00:12:31          (status, not clickable)
    Pomodoro · Focus 18:42         (only while a Pomodoro runs)
    ───────
    Pause monitoring / Start / Resume
    Stop session
    Pause Pomodoro / Start / Resume focus round
    ───────
    Open OcuSense
    Quit OcuSense

On macOS the icon is the logo drawn in one colour as a "template" image, so it follows
light and dark menu bars. On Windows it is the full-colour logo on paper (template
images don't exist there), a click opens the window, and the tray also shows OcuSense's
notifications (see notifications.set_fallback). The menu only calls the window's existing actions (start,
pause, resume, stop, the Pomodoro button) — no separate logic. Without a menu bar
(e.g. in tests) the menu is still built, just not shown.
"""

import time

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ocusense import notifications
from ocusense.core.pomodoro import PHASE_NAMES
from ocusense.system import IS_MAC

from .pomodoro_page import clock
from .widgets.artwork import paint_logo


def template_icon() -> QIcon:
    pixmap = QPixmap(44, 44)  # 22 pt at 2x
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_logo(p, 44, monochrome="#000000")
    p.end()
    pixmap.setDevicePixelRatio(2.0)
    icon = QIcon(pixmap)
    icon.setIsMask(True)  # macOS draws it in the menu bar's own colour
    return icon


def tray_icon() -> QIcon:
    """Windows / other systems: the colour logo on a small paper tile (visible on dark and light taskbars)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor

    from ocusense.ui import theme

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(theme.PAPER))
    p.setPen(QColor(theme.INK))
    p.drawRoundedRect(QRectF(1, 1, 62, 62), 14, 14)
    p.translate(6, 6)
    paint_logo(p, 52)
    p.end()
    return QIcon(pixmap)


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


class MenuBarIcon(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.menu = QMenu()
        self.status = self._add("Ready", None, enabled=False)
        self.pomodoro_status = self._add("", None, enabled=False)
        self.menu.addSeparator()
        self.monitor_action = self._add("Start monitoring", self._monitor)
        self.stop_action = self._add("Stop session", lambda: self.window.stop())
        self.pomodoro_action = self._add("Start focus round", lambda: self.window.pomodoro_page._main_action())
        self.menu.addSeparator()
        self._add("Open OcuSense", self._open)
        self._add("Quit OcuSense", self._quit)
        self.menu.aboutToShow.connect(self.refresh)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(template_icon() if IS_MAC else tray_icon(), self)
            self.tray.setContextMenu(self.menu)
            self.tray.setToolTip("OcuSense")
            if not IS_MAC:
                self.tray.activated.connect(self._activated)
                notifications.set_fallback(self._notify)
            self.tray.show()
        self.refresh()

    def _add(self, text: str, handler, enabled: bool = True) -> QAction:
        action = QAction(text, self.menu)
        action.setEnabled(enabled)
        if handler is not None:
            action.triggered.connect(handler)
        self.menu.addAction(action)
        return action

    # ------------------------------------------------------------ actions
    def _monitor(self) -> None:
        w = self.window
        if w.state == "monitoring":
            w.pause()
        elif w.state == "paused":
            w.resume()
        elif w.state in ("ready", "error"):
            w.start()
            self._open()  # the first start may calibrate: show the window

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # a plain click on the Windows tray icon
            self._open()

    def _notify(self, message: str, title: str) -> bool:
        if self.tray is None or not QSystemTrayIcon.supportsMessages():
            return False
        self.tray.showMessage(title, message, tray_icon(), 10_000)
        return True

    def _open(self) -> None:
        w = self.window
        w.showNormal()
        w.raise_()
        w.activateWindow()

    def _quit(self) -> None:
        self.window.close()  # saves the session and the recording, releases the camera
        QApplication.instance().quit()

    # ------------------------------------------------------------ status
    def refresh(self) -> None:
        w = self.window
        state = w.state
        running = w.elapsed + (time.monotonic() - w.running_since if w.running_since is not None else 0.0)
        self.status.setText({"monitoring": f"Monitoring · {_clock(running)}", "paused": "Monitoring paused",
                             "calibrating": "Calibrating…", "error": "Camera unavailable",
                             "playing": "Playing a game"}.get(state, "Ready"))
        self.monitor_action.setText({"monitoring": "Pause monitoring", "paused": "Resume monitoring"}
                                    .get(state, "Start monitoring"))
        self.monitor_action.setEnabled(state not in ("calibrating", "playing"))
        self.stop_action.setEnabled(state in ("monitoring", "paused"))  # not while a game uses the camera
        page = w.pomodoro_page
        t = page.timer
        if t.state == "idle":
            self.pomodoro_status.setVisible(False)
            self.pomodoro_action.setText("Start focus round" if t.phase == "focus" else "Start break")
        else:
            left = clock(t.remaining(page.now()))
            self.pomodoro_status.setText(f"Pomodoro · {PHASE_NAMES[t.phase]} {left}"
                                         + (" (paused)" if t.state == "paused" else ""))
            self.pomodoro_status.setVisible(True)
            self.pomodoro_action.setText("Pause Pomodoro" if t.state == "running" else "Resume Pomodoro")
        if self.tray is not None:
            self.tray.setToolTip(f"OcuSense — {self.status.text()}")
