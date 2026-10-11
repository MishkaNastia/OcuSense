"""OcuSense Garden: native farming game, using the existing game-camera lifecycle."""
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QSpinBox, QVBoxLayout, QWidget
from ocusense.core.garden import PLANTS
from ocusense.core.garden_exercise import GardenReminder
from ocusense.garden_store import GardenStore
from . import theme
from .garden_dialogs import EyeExerciseDialog, GardenShop, button
from .pomodoro_page import system_reduce_motion
from .widgets.common import label
from .widgets.garden_art import GardenPlot, GardenSky, crop
from .widgets.garden_coins import CoinCounter
from .widgets.artwork import draw_star
from .widgets.alert_banner import AlertBanner


class GardenCanvas(QWidget):
    """Small original crop mark for the hub and reminder."""
    def __init__(self, prefs=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 72)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        crop(p, 'strawberry', 3, 48, 60, .65)
        draw_star(p, 83, 15, 8, theme.COBALT, 1.6)
        p.end()


class BlinkGardenGame(QWidget):
    back = Signal()

    def __init__(self, window, parent=None, store=None):
        super().__init__(parent)
        self.window = window
        self.store = store or GardenStore()
        self.exercise_dialog = None
        self.shop_dialog = None
        self.active_plot = None
        self.cards = []
        self.columns = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(button('Garden shop', self.open_shop, 'primary'))
        top.addWidget(button('← All games', self.back.emit, 'quiet'))
        layout.addLayout(top)
        self.sky = GardenSky()
        self.coins = CoinCounter(self.sky)
        self.coins.move(12, 10)
        layout.addWidget(self.sky)
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(38, 158, 38, 44)
        self.sky.setLayout(self.grid)
        self.info_panel = QFrame()
        self.info_panel.setObjectName('GardenInfoPanel')
        self.info_panel.setStyleSheet(f"""
            QFrame#GardenInfoPanel {{ background: #FFF9EC; border: 1px solid #D6C7A6; border-radius: 16px; }}
            QFrame#GardenReminderBox {{ background: #F0EAD8; border: none; border-radius: 10px; }}
            QSpinBox {{ background: #FFFDF5; border: 1px solid #BBA984; border-radius: 8px;
                        padding: 7px 10px; min-height: 26px; font-size: 14px; }}
        """)
        panel = QVBoxLayout(self.info_panel)
        panel.setContentsMargins(20, 17, 20, 17)
        panel.setSpacing(13)
        panel.addWidget(label('A little pause, a growing garden', font=theme.ui_font(18)))
        self.status = label(self.store.error or 'Choose a thirsty plant to begin. We’ll guide you through a gentle eye break.',
                            'secondary', theme.ui_font(14), wrap=True)
        panel.addWidget(self.status)
        reminder_box = QFrame()
        reminder_box.setObjectName('GardenReminderBox')
        reminder_layout = QVBoxLayout(reminder_box)
        reminder_layout.setContentsMargins(14, 12, 14, 12)
        reminder_layout.setSpacing(8)
        self.reminders = QCheckBox('Remind me to take a garden break')
        self.reminders.setChecked(self.store.garden.reminders)
        reminder_layout.addWidget(self.reminders)
        reminder_row = QHBoxLayout()
        reminder_row.setSpacing(10)
        reminder_row.addWidget(label('After every', 'secondary', theme.ui_font(13)))
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 120)
        self.minutes.setSuffix(' min')
        self.minutes.setFixedWidth(110)
        self.minutes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minutes.setValue(self.store.garden.reminder_minutes)
        self.minutes.setAccessibleName('Garden reminder interval in minutes of study')
        reminder_row.addWidget(self.minutes)
        reminder_row.addWidget(label('of study', 'secondary', theme.ui_font(13)))
        reminder_row.addStretch()
        reminder_layout.addLayout(reminder_row)
        panel.addWidget(reminder_box)
        self.reminders.toggled.connect(self.save_settings)
        self.minutes.valueChanged.connect(self.save_settings)
        panel.addWidget(label('Your plants keep growing while you’re away.', font=theme.ui_font(13), wrap=True))
        panel.addWidget(label('Camera exercises are kept separate from your study statistics.',
                              'secondary', theme.ui_font(12), wrap=True))
        layout.addWidget(self.info_panel)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.animate)
        self.last_refresh = 0
        self.refresh()

    def save_settings(self, *_):
        def apply(g):
            g.reminders, g.reminder_minutes = self.reminders.isChecked(), self.minutes.value()
            return True
        if not self.store.change(apply):
            self.status.setText(self.store.error)
            self.reminders.blockSignals(True)
            self.minutes.blockSignals(True)
            self.reminders.setChecked(self.store.garden.reminders)
            self.minutes.setValue(self.store.garden.reminder_minutes)
            self.reminders.blockSignals(False)
            self.minutes.blockSignals(False)

    def refresh(self):
        g = self.store.garden
        self.coins.setText(f'{g.coins:,} coins')
        self.sky.decorations = g.decorations
        self.sky.update()
        while len(self.cards) < len(g.plots):
            index = len(self.cards)
            card = GardenPlot(index)
            card.clicked.connect(lambda checked=False, i=index: self.select_plot(i))
            self.cards.append(card)
            self.columns = 0
        for card, plot in zip(self.cards, g.plots):
            card.plot = plot
            card.decorations = g.decorations
            card.animations = self.window.preferences.animations and not system_reduce_motion()
            state = plot.state(time.time())
            card.setAccessibleName((PLANTS[plot.plant].name if plot.plant else 'Empty garden bed') + ': ' + state.replace('_', ' ').lower())
            card.setEnabled(not self.store.read_only)
            card.update()
        self.reflow()

    def reflow(self):
        columns = 3 if self.width() >= 690 else 2 if self.width() >= 450 else 1
        if self.columns == columns:
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns)
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def select_plot(self, index):
        if self.exercise_dialog or self.shop_dialog:
            return
        plot = self.store.garden.plots[index]
        state = plot.state(time.time())
        if state == 'EMPTY':
            self.open_shop(planting=index)
        elif state == 'NEEDS_WATER':
            self.store.garden.begin(index, time.time())
            self.active_plot = index
            dialog = EyeExerciseDialog(self.window, plot.plant, self)
            self.exercise_dialog = dialog
            dialog.watered.connect(self.water)
            dialog.finished.connect(self.exercise_closed)
            dialog.open()
            self.refresh()
        elif state == 'READY_TO_HARVEST':
            key = plot.plant
            reward = self.store.change(lambda g: g.harvest(index, time.time()))
            if reward:
                self.status.setText(f'+{reward} coins! {PLANTS[key].name} collected. Your bed is ready for a new seed.')
                self.cards[index].celebrate(key)
            else:
                self.status.setText(self.store.error or 'This crop has already been collected.')
            self.refresh()
        else:
            self.status.setText('This plant is growing. Come back later; the timer continues with the app closed.')

    def water(self):
        if self.active_plot is None or not self.exercise_dialog or not self.exercise_dialog.exercise.complete:
            return
        index = self.active_plot
        if self.store.change(lambda g: g.water(index, time.time())):
            self.cards[index].celebrate('water')
            self.status.setText('Exercise complete! Your plant is watered. Take your time — it will grow while you are away.')
        else:
            self.status.setText(self.store.error)
        self.refresh()

    def exercise_closed(self, _result):
        if self.active_plot is not None:
            self.store.garden.cancel(self.active_plot)
        if self.exercise_dialog:
            self.exercise_dialog.deleteLater()
        self.active_plot = self.exercise_dialog = None
        self.refresh()

    def feed(self, update):
        if self.exercise_dialog:
            self.exercise_dialog.feed(update)

    def open_shop(self, checked=False, planting=None):
        if self.exercise_dialog or self.shop_dialog:
            return
        self.shop_dialog = GardenShop(self.store, self.refresh, self, planting)
        self.shop_dialog.finished.connect(self.shop_closed)
        self.shop_dialog.open()

    def shop_closed(self, _result):
        if self.shop_dialog:
            self.shop_dialog.deleteLater()
        self.shop_dialog = None

    def animate(self):
        now = time.monotonic()
        if now - self.last_refresh >= 1:
            self.last_refresh = now
            self.refresh()
        else:
            for card in self.cards:
                if card.animations and card.effect and now - card.effect_started < 2.6:
                    card.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        if self.exercise_dialog:
            self.exercise_dialog.reject()
        if self.shop_dialog:
            self.shop_dialog.reject()
        self.window.stop_game_camera()
        super().hideEvent(event)


class GardenReminderCard(QWidget):
    """Gentle in-app invitation driven only by the existing monitoring state."""
    def __init__(self, window, game, parent=None):
        super().__init__(parent)
        self.window, self.game = window, game
        self.clock = GardenReminder()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 12, 40, 0)
        self.banner = AlertBanner('Your garden needs a little water', 'Time for a quick eye break?',
                                  ('Open garden', 'Snooze 10 min', 'Disable'), GardenCanvas())
        self.banner.action.connect(self.action)
        layout.addWidget(self.banner)
        self.hide()

    def tick(self, now):
        g = self.game.store.garden
        thirsty = any(p.state(time.time()) == 'NEEDS_WATER' for p in g.plots)
        if not g.reminders:
            self.hide()
        due = self.clock.update(now, self.window.state == 'monitoring', g.reminders, g.reminder_minutes, thirsty)
        if due and not self.window.eye_rest_card.isVisible() and self.window.banner_holder.isHidden():
            plant = next(p for p in g.plots if p.state(time.time()) == 'NEEDS_WATER')
            self.banner.body.setText(f'Your {PLANTS[plant.plant].name.lower()} need watering. Time for a quick eye break?')
            self.show()
        if self.window.state != 'monitoring':
            self.hide()

    def action(self, name):
        self.hide()
        self.clock.snooze(time.monotonic())
        if name == 'Open garden':
            self.window.show_page('games')
            self.window.games_page.open_blink_garden()
        elif name == 'Disable':
            self.game.reminders.setChecked(False)
