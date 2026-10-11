"""EyeGame in the Games section: our teammate MishkaNastia's blink runner (core/runner.py).

Blinks come from OcuSense's calibrated detector through the window's "playing"
state, like Blink Code: the jump fires the moment your eyes close, nothing is
recorded in the study session, and leaving the game turns the camera off.
Keys work too: Space / Up = jump (double-tap = extra jump), Down = duck, P = pause.
"""

import time

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.core.runner import DoubleBlink, RunnerGame, Sizes

from . import theme
from .widgets.common import label
from .widgets.page import paragraph
from .widgets.runner_canvas import RunnerCanvas


def _button(text: str, kind: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


class EyeRunnerGame(QWidget):
    back = Signal()

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.game = RunnerGame(Sizes.load(), highscore=window.preferences.runner_high_score)
        self.blinks = DoubleBlink()  # eye closures → jump / extra jump
        self.keys = DoubleBlink(cooldown_s=0.0)  # Space taps → jump / extra jump
        self.down = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(label("Blink to jump, blink twice quickly to jump again in mid-air.", "secondary",
                            theme.ui_font(15)))
        top.addStretch(1)
        back = _button("← All games", "quiet")
        back.clicked.connect(self.back.emit)
        top.addWidget(back)
        layout.addLayout(top)

        self.canvas = RunnerCanvas(self.game)
        self.canvas.setFocusProxy(self)
        layout.addWidget(self.canvas)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.camera_button = _button("Play with my eyes", "primary")
        self.camera_button.clicked.connect(self.toggle_camera)
        self.pause_button = _button("Pause", "secondary")
        self.pause_button.clicked.connect(self.toggle_pause)
        actions.addWidget(self.camera_button)
        actions.addWidget(self.pause_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.status = label("", "secondary", theme.ui_font(14), wrap=True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)
        layout.addWidget(paragraph(
            "Made by our teammate MishkaNastia. Keys work too: Space or ↑ jumps (tap twice for the extra jump), "
            "↓ ducks, P pauses. If your eyes feel tired or dry, stop and rest them — game blinks never count in "
            "your study statistics.", 13, secondary=True))
        layout.addStretch(1)

        self.clock = QElapsedTimer()
        self.clock.start()
        self.frames = QTimer(self)
        self.frames.setTimerType(Qt.TimerType.PreciseTimer)
        self.frames.timeout.connect(self.tick)
        self._show_input()

    # ------------------------------------------------------------ camera
    def toggle_camera(self) -> None:
        if self.window.state == "playing":
            self.window.stop_game_camera()
            self.status.setText("Camera off — Space still works.")
        else:
            problem = self.window.start_game_camera()
            self.status.setText(problem or "Camera on — blink to jump!")
        self._show_input()
        self.setFocus()

    def _show_input(self) -> None:
        playing = self.window.state == "playing"
        self.camera_button.setText("Stop camera" if playing else "Play with my eyes")
        if not playing:
            self.canvas.eyes = "keyboard: Space = jump"
            self.canvas.eyes_closed = False

    def feed(self, update) -> None:
        """A camera frame while playing (called by the window on the interface thread)."""
        obs = update.observation
        if obs is None or not obs.valid:
            self.canvas.eyes = "looking for your eyes…" if not update.face_found else "eyes not clear"
            self.canvas.eyes_closed = False
            return
        self.canvas.eyes_closed = obs.detector_closed
        self.canvas.eyes = "eyes closed" if obs.detector_closed else "eyes open"
        if obs.closing_started:  # jump the instant the eyes close, no lag
            self._press(self.blinks, obs.t)

    # ------------------------------------------------------------ keys
    def _press(self, pairing: DoubleBlink, t: float) -> None:
        event = pairing.press(t)
        if event:
            self.game.jump(double=event == "double_blink")

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Up):
            if not event.isAutoRepeat():
                self._press(self.keys, time.monotonic())
            return
        if key == Qt.Key.Key_Down:
            self.down = True
            return
        if key == Qt.Key.Key_P and not event.isAutoRepeat():
            self.toggle_pause()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Down and not event.isAutoRepeat():
            self.down = False
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.down = False

    def toggle_pause(self) -> None:
        if self.game.state != "play":
            return
        self.game.paused = not self.game.paused
        self.pause_button.setText("Resume" if self.game.paused else "Pause")
        self.canvas.update()
        self.setFocus()

    # ------------------------------------------------------------ loop
    def tick(self) -> None:
        if not self.clock.isValid():
            self.clock.start()
        dt = max(0.0, min(self.clock.restart() / 1000, 1 / 20))  # clamp, so a hiccup can't teleport things
        was_over = self.game.state == "over"
        self.game.update(dt, self.down)
        if self.game.state == "over" and not was_over and self.game.new_record:
            prefs = self.window.preferences
            prefs.runner_high_score = self.game.highscore
            prefs.save()
        self.pause_button.setEnabled(self.game.state == "play")
        if self.game.state != "play" and self.game.paused:
            self.game.paused = False
        self.canvas.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.clock.start()
        self.frames.start(16)  # ~60 frames per second, only while the game is on screen
        self._show_input()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.frames.stop()
        if self.game.state == "play" and not self.game.paused:
            self.toggle_pause()  # leaving mid-run pauses it
