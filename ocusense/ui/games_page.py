"""Games: little breaks for your eyes and your head, in the OcuSense (Miró) style.

Blink Code — Morse code with your blinks (core/morse.py) — and EyeGame, our
teammate MishkaNastia's blink runner (core/runner.py, eye_runner_page.py). While a
game uses the camera the window is in its "playing" state: frames go only to the
game, nothing is recorded in the study session or the EAR recording, and reminders
stay quiet. Leaving the page turns the game camera off again. The space bar works
as an alternative input (tap = dot, hold = dash).

Every finished Blink Code challenge and EyeGame run goes to the leaderboards
(leaderboard_view.py): on this Mac always, and online when you're signed in.
"""

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QPushButton, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from ocusense.core.morse import DASH_MS, LEARN_ORDER, MORSE, ChallengeGame, LearnGame, MorseDecoder
from ocusense.core.runner import ASSETS as RUNNER_ASSETS
from ocusense.system import COMPUTER

from . import theme
from .eye_runner_page import EyeRunnerGame
from .blink_garden_page import BlinkGardenGame, GardenCanvas
from .leaderboard_view import LeaderboardView, ScoreKeeper
from .pomodoro_page import system_reduce_motion
from .widgets.artwork import draw_star
from .widgets.common import label, rule
from .widgets.morse_canvas import MorseCanvas
from .widgets.page import Page, paragraph
from .widgets.segmented import Segmented

MODES = (("learn", "Learn"), ("challenge", "Challenge"), ("free", "Free blink"))
INPUTS = (("eyes", "Eyes"), ("keys", "Space bar"))


def _button(text: str, kind: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


def pretty(code: str) -> str:
    return code.replace(".", "•").replace("-", "—")


class BlinkCodeMark(QWidget):
    """The game card's mark: an eye with a dot and a dash coming out of it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 72)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        eye = QPainterPath(QPointF(6, 30))
        eye.cubicTo(18, 12, 42, 12, 54, 30)
        eye.cubicTo(42, 46, 18, 46, 6, 30)
        p.setPen(QPen(theme.color(theme.INK), 2.5))
        p.setBrush(QBrush(theme.color(theme.COBALT)))
        p.drawPath(eye)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawEllipse(QPointF(30, 30), 8, 8)
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        p.drawEllipse(QPointF(66, 30), 6, 6)
        p.setBrush(QBrush(theme.color(theme.INK)))
        p.drawRoundedRect(76, 26, 18, 8, 4, 4)
        draw_star(p, 82, 10, 6, theme.INK, 2)
        p.setBrush(QBrush(theme.color(theme.GOLDEN)))
        p.drawEllipse(QPointF(14, 62), 6, 6)
        p.end()


class EyeGameMark(QWidget):
    """The EyeGame card's mark: her runner (the OcuSense eye on legs) jumping over a toilet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 72)
        folder = RUNNER_ASSETS
        self.avatar = QPixmap(str(folder / "avatar.png"))
        self.toilet = QPixmap(str(folder / "obstacles" / "toilet.png"))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(QPen(theme.color(theme.INK), 2.5))
        p.drawLine(QPointF(2, 68), QPointF(94, 68))
        height = 34
        width = height * self.toilet.width() / max(1, self.toilet.height())
        p.drawPixmap(QRectF(92 - width, 68 - height, width, height), self.toilet, QRectF(self.toilet.rect()))
        p.drawPixmap(QRectF(8, 2, 46, 46 * self.avatar.height() / self.avatar.width()), self.avatar,
                     QRectF(self.avatar.rect()))
        p.setPen(QPen(theme.color(theme.INK), 3))
        p.drawLine(QPointF(26, 38), QPointF(22, 50))
        p.drawLine(QPointF(36, 38), QPointF(40, 50))
        p.end()


class MorseChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        for i, letter in enumerate(LEARN_ORDER):
            cell = label(f"<b>{letter}</b>&nbsp;&nbsp;{pretty(MORSE[letter])}", font=theme.number_font(15))
            cell.setTextFormat(Qt.TextFormat.RichText)
            grid.addWidget(cell, i // 6, i % 6)


class BlinkCodeGame(QWidget):
    """The game itself. The window feeds camera frames with feed(update) while it is playing."""
    back = Signal()

    def __init__(self, window, scores: ScoreKeeper | None = None, parent=None):
        super().__init__(parent)
        self.window = window
        self.scores = scores  # where finished challenges go (the leaderboards)
        prefs = window.preferences
        self.decoder = MorseDecoder(dash_seconds=prefs.morse_dash_ms / 1000)
        self.mode, self.input = "learn", "eyes"
        self.learn = LearnGame()
        self.challenge = ChallengeGame()
        self.letters_blinked = 0
        self._closing_since: float | None = None
        self._key_down: float | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # the space bar plays

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        top = QHBoxLayout()
        self.mode_switch = Segmented(MODES, self.mode, "Game mode")
        self.mode_switch.changed.connect(self.set_mode)
        self.input_switch = Segmented(INPUTS, self.input, "Input")
        self.input_switch.changed.connect(self.set_input)
        back = _button("← All games", "quiet")
        back.clicked.connect(self.back.emit)
        top.addWidget(self.mode_switch)
        top.addSpacing(12)
        top.addWidget(self.input_switch)
        top.addStretch(1)
        top.addWidget(back)
        layout.addLayout(top)

        self.canvas = MorseCanvas()
        layout.addWidget(self.canvas)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.camera_button = _button("Start camera", "primary")
        self.camera_button.clicked.connect(self.toggle_camera)
        self.challenge_button = _button("Start 90-second challenge", "secondary")
        self.challenge_button.clicked.connect(self.start_challenge)
        actions.addWidget(self.camera_button)
        actions.addWidget(self.challenge_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.status = label("", "secondary", theme.ui_font(14), wrap=True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        layout.addWidget(rule(1, "hairline"))
        speed = QHBoxLayout()
        speed.addWidget(label("A dash is a blink longer than", font=theme.ui_font(15, QFont.Weight.DemiBold)))
        self.dash_slider = QSlider(Qt.Orientation.Horizontal)
        self.dash_slider.setRange(*DASH_MS)
        self.dash_slider.setSingleStep(25)
        self.dash_slider.setPageStep(50)
        self.dash_slider.setValue(prefs.morse_dash_ms)
        self.dash_slider.setAccessibleName("Dash length, milliseconds")
        self.dash_slider.setMaximumWidth(300)
        self.dash_slider.valueChanged.connect(self._dash_changed)
        speed.addWidget(self.dash_slider)
        self.dash_label = label("", font=theme.number_font(15))
        speed.addWidget(self.dash_label)
        speed.addStretch(1)
        self.chart_toggle = QCheckBox("Show the Morse chart")
        speed.addWidget(self.chart_toggle)
        layout.addLayout(speed)
        self.chart = MorseChart()
        self.chart.setVisible(False)
        self.chart_toggle.toggled.connect(self.chart.setVisible)
        layout.addWidget(self.chart)
        layout.addWidget(paragraph(
            "Deliberate blinking is just a playful exercise. If your eyes feel tired or dry, stop and rest them. "
            "Game blinks are never counted in your study statistics.", 13, secondary=True))

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.tick)
        self.ticker.start(50)
        self.canvas.set_animations(prefs.animations and not system_reduce_motion())
        self._dash_changed(prefs.morse_dash_ms)
        self.set_mode("learn")

    # ------------------------------------------------------------ setup
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_switch.set_current(mode)
        self.decoder.reset()
        self.canvas.mode = mode
        self.canvas.code = ""
        self.canvas.time_left = None
        self.challenge.started_at = None
        if mode == "learn":
            self.learn.next_target()
            self._show_learn()
            self.canvas.message = "Blink the letter on the left. Three in a row unlocks a new one."
        elif mode == "challenge":
            self.challenge.new_word()
            self.challenge.position = 0
            self.canvas.word, self.canvas.position = self.challenge.word, 0
            self.canvas.target_code = MORSE[self.challenge.expected]
            self.canvas.score, self.canvas.combo, self.canvas.best = 0, 0, self.window.preferences.morse_high_score
            self.canvas.message = "Spell as many words as you can in 90 seconds."
        else:
            self.canvas.typed = ""
            self.canvas.score = self.letters_blinked
            self.canvas.message = "Blink anything — a short pause ends a letter, a longer one adds a space."
        self.challenge_button.setVisible(mode == "challenge")
        self.setFocus()
        self.canvas.update()

    def set_input(self, how: str) -> None:
        self.input = how
        self.input_switch.set_current(how)
        if how == "keys":
            self.window.stop_game_camera()
        self._update_camera_button()
        self.status.setText("Tap the space bar for a dot, hold it for a dash." if how == "keys" else "")
        self.setFocus()

    def _dash_changed(self, ms: int) -> None:
        self.decoder.dash_seconds = ms / 1000
        self.canvas.dash_seconds = ms / 1000
        self.dash_label.setText(f"{ms} ms")
        prefs = self.window.preferences
        if prefs.morse_dash_ms != ms:
            prefs.morse_dash_ms = ms
            prefs.save()

    def _update_camera_button(self) -> None:
        playing = self.window.state == "playing"
        self.camera_button.setVisible(self.input == "eyes")
        self.camera_button.setText("Stop camera" if playing else "Start camera")

    def toggle_camera(self) -> None:
        if self.window.state == "playing":
            self.window.stop_game_camera()
            self.status.setText("Camera off.")
        else:
            problem = self.window.start_game_camera()
            self.status.setText(problem or "Camera on — blink! Short = dot, long = dash.")
        self._update_camera_button()
        self.setFocus()

    def start_challenge(self) -> None:
        self.decoder.reset()
        self.challenge.start(time.monotonic())
        self.canvas.word, self.canvas.position = self.challenge.word, 0
        self.canvas.target_code = MORSE[self.challenge.expected]
        self.canvas.score = self.canvas.combo = 0
        self.canvas.message = "Go!"
        self.challenge_button.setText("Restart challenge")
        self.setFocus()

    # ------------------------------------------------------------ input
    def feed(self, update) -> None:
        """A camera frame while playing (called by the window on the interface thread)."""
        if self.input != "eyes":
            return
        obs = update.observation
        self.canvas.openness = update.openness[2] if update.openness else (0.5 if update.face_found else 1.0)
        if obs is None or not obs.valid:
            self._closing_since = None  # tracking lost: no half blinks
            self.canvas.closed_for = None
            return
        if obs.closing_started:
            self._closing_since = obs.t
        if obs.blink_completed and self._closing_since is not None:
            self._symbol(self.decoder.closure(self._closing_since, obs.t))
            self._closing_since = None
        self.canvas.closed_for = (obs.t - self._closing_since) if (obs.detector_closed and self._closing_since) else None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self.input != "keys":
                self.set_input("keys")
            self._key_down = time.monotonic()
            self.canvas.openness = 0.0
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._key_down is not None:
            self._symbol(self.decoder.closure(self._key_down, time.monotonic()))
            self._key_down = None
            self.canvas.openness = 1.0
            self.canvas.closed_for = None
            return
        super().keyReleaseEvent(event)

    def _symbol(self, event) -> None:
        self.canvas.code = self.decoder.code
        self.canvas.add_symbol(event.symbol.mark)

    # ------------------------------------------------------------ game loop
    def tick(self) -> None:
        now = time.monotonic()
        if self._key_down is not None:
            self.canvas.closed_for = now - self._key_down
        self.canvas.fuse = self.decoder.letter_progress(now)
        event = self.decoder.tick(now)
        if event is not None:
            if event.kind == "letter":
                self._letter(event.letter, event.code)
            elif event.kind == "space" and self.mode == "free":
                self.canvas.typed += " "
            self.canvas.code = self.decoder.code
        if self.mode == "challenge" and self.challenge.started_at is not None:
            self.canvas.time_left = self.challenge.remaining(now) / self.challenge.seconds
            if self.challenge.over(now):
                self._challenge_over()
        if self.isVisible():
            self._update_camera_button()

    def _letter(self, letter: str | None, code: str) -> None:
        shown = letter or "?"
        if self.mode == "learn":
            right, unlocked = self.learn.answer(letter)
            if right:
                self.canvas.celebrate(big=unlocked)
                self.canvas.message = (f"New letter unlocked: {LEARN_ORDER[self.learn.unlocked - 1]} "
                                       f"{pretty(MORSE[LEARN_ORDER[self.learn.unlocked - 1]])} !"
                                       if unlocked else f"Yes! {letter} is {pretty(code)}")
                self.learn.next_target()
            else:
                self.canvas.wobble()
                self.canvas.message = (f"That was {pretty(code)} ({shown}). "
                                       f"{self.learn.target} is {pretty(MORSE[self.learn.target])} — try again.")
            self._show_learn()
        elif self.mode == "challenge":
            if self.challenge.started_at is None:
                self.canvas.message = "Press “Start 90-second challenge” first."
                return
            right, finished = self.challenge.answer(letter)
            if right:
                self.canvas.celebrate(big=finished)
                self.canvas.message = "Word complete! +bonus" if finished else f"{letter} ✓"
            else:
                self.canvas.wobble()
                self.canvas.message = f"That was {shown} — need {self.challenge.expected}. Combo lost."
            self.canvas.word, self.canvas.position = self.challenge.word, self.challenge.position
            self.canvas.target_code = MORSE[self.challenge.expected]
            self.canvas.score, self.canvas.combo = self.challenge.score, self.challenge.combo
        else:
            if letter:
                self.letters_blinked += 1
                self.canvas.celebrate()
            else:
                self.canvas.wobble()
            self.canvas.typed += shown
            self.canvas.score = self.letters_blinked

    def _show_learn(self) -> None:
        self.canvas.target = self.learn.target
        self.canvas.target_code = MORSE[self.learn.target]
        self.canvas.unlocked = LEARN_ORDER[:self.learn.unlocked]
        self.canvas.score = self.learn.correct * 10
        self.canvas.streak, self.canvas.best = self.learn.streak, self.learn.best_streak
        self.canvas.combo = self.learn.streak

    def _challenge_over(self) -> None:
        score = self.challenge.score
        prefs = self.window.preferences
        record = score > prefs.morse_high_score
        if record:
            prefs.morse_high_score = score
            prefs.save()
            self.canvas.celebrate(big=True)
        place = None
        if self.scores is not None:
            place = self.scores.record("blink_code_challenge", score,
                                       {"words": self.challenge.words_done, "best_combo": self.challenge.best_combo})
        self.canvas.best = prefs.morse_high_score
        ranked = f" · #{place} on this {COMPUTER}" if place and not record else ""
        self.canvas.message = (f"Time! {score} points, {self.challenge.words_done} words"
                               + (" — a new high score!" if record else f" · best {prefs.morse_high_score}")
                               + ranked)
        self.challenge.started_at = None
        self.canvas.time_left = None
        self.challenge_button.setText("Start 90-second challenge")


class GamesPage(Page):
    def __init__(self, window, parent=None):
        super().__init__("Play", "Games", "Small games for your breaks. They use the camera only while you play, "
                         "and never count towards your study statistics.", parent)
        self.window = window
        self.scores = ScoreKeeper(window.account_service, window.preferences, parent=self)
        self.stack = QStackedWidget()
        self.hub = QWidget()
        hub_column = QVBoxLayout(self.hub)  # cards at the top, at their natural height
        hub_column.setContentsMargins(0, 0, 0, 0)
        hub = QHBoxLayout()
        hub.setSpacing(18)
        hub_column.addLayout(hub)
        hub_column.addSpacing(18)
        hub_column.addWidget(label("Leaderboards", font=theme.ui_font(24, QFont.Weight.Bold)))
        hub_column.addWidget(rule())
        self.leaderboard = LeaderboardView(self.scores, open_account=lambda: window.show_page("account"))
        self.leaderboard.rendered.connect(self._leaderboard_resized)
        hub_column.addWidget(self.leaderboard)
        hub_column.addStretch(1)
        hub.addWidget(self._card(BlinkCodeMark(), "Blink Code",
                                 "Learn Morse code with your eyes: a short blink is a dot, a long blink a dash. "
                                 "Unlock letters, chase combos in the 90-second challenge, or blink-type freely.",
                                 "Play", self.open_blink_code), 0, Qt.AlignmentFlag.AlignTop)
        hub.addWidget(self._card(EyeGameMark(), "EyeGame",
                                 "An endless runner by MishkaNastia: blink to jump over toilets (some of them fly), "
                                 "blink again in the air for an extra jump, and grab coffee for double points.",
                                 "Play", self.open_eye_runner), 0, Qt.AlignmentFlag.AlignTop)
        mark = GardenCanvas(window.preferences)
        mark.setFixedSize(96, 72)
        hub.addWidget(self._card(mark, "OcuSense Garden",
                                 "A little garden for your breaks. Water six crops with gentle eye exercises, "
                                 "come back to harvest, and make the garden your own.",
                                 "Play", self.open_blink_garden), 0, Qt.AlignmentFlag.AlignTop)
        self.stack.addWidget(self.hub)
        self.blink_code = BlinkCodeGame(window, self.scores)
        self.blink_code.back.connect(self.show_hub)
        self.stack.addWidget(self.blink_code)
        self.eye_runner = EyeRunnerGame(window, self.scores)
        self.eye_runner.back.connect(self.show_hub)
        self.stack.addWidget(self.eye_runner)
        self.blink_garden = BlinkGardenGame(window)
        self.blink_garden.back.connect(self.show_hub)
        self.stack.addWidget(self.blink_garden)
        self.body.addWidget(self.stack)
        self.finish()
        self._fit_stack()

    def _card(self, mark: QWidget, title: str, text: str, action: str, handler) -> QWidget:
        card = QWidget()
        card.setObjectName("GameCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        card.setStyleSheet(f"QWidget#GameCard {{ background: #FBF7EC; border: 2px solid {theme.INK}; "
                           "border-radius: 14px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(mark)
        layout.addWidget(label(title, font=theme.ui_font(24, QFont.Weight.Bold)))
        layout.addWidget(label(text, "secondary", theme.ui_font(14), wrap=True))
        play = _button(action, "primary")
        play.clicked.connect(handler)
        layout.addWidget(play, 0, Qt.AlignmentFlag.AlignLeft)
        card.setMinimumHeight(220)
        card.setMaximumWidth(460)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return card

    def _fit_stack(self) -> None:
        """A QStackedWidget is as tall as its tallest page; size it to the one shown instead."""
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred if page is
                               self.stack.currentWidget() else QSizePolicy.Policy.Ignored)
        self.stack.adjustSize()

    def _leaderboard_resized(self) -> None:
        if self.stack.currentWidget() is self.hub:
            self._fit_stack()
            self.fit_height()

    def open_blink_code(self) -> None:
        self.stack.setCurrentWidget(self.blink_code)
        self._fit_stack()
        self.blink_code.setFocus()
        self.fit_height()

    def open_eye_runner(self) -> None:
        self.stack.setCurrentWidget(self.eye_runner)
        self._fit_stack()
        self.eye_runner.setFocus()
        self.fit_height()

    def open_blink_garden(self) -> None:
        self.stack.setCurrentWidget(self.blink_garden)
        self._fit_stack()
        self.blink_garden.setFocus()
        self.fit_height()

    def show_hub(self) -> None:
        self.window.stop_game_camera()
        self.stack.setCurrentWidget(self.hub)
        self._fit_stack()
        self.fit_height()

    def feed(self, update) -> None:
        if self.stack.currentWidget() is self.eye_runner:
            self.eye_runner.feed(update)
        elif self.stack.currentWidget() is self.blink_garden:
            self.blink_garden.feed(update)
        elif self.stack.currentWidget() is self.blink_code:
            self.blink_code.feed(update)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.window.stop_game_camera()  # leaving Games turns the game camera off
