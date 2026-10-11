"""Native, keyboard-accessible exercise and seed/shop dialogs."""
import time
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget
from ocusense.core.garden import PLANTS, SHOP
from ocusense.core.garden_exercise import EyeExercise
from . import theme
from .widgets.common import label
from .widgets.garden_coins import CoinBalance


def button(text, action, kind='secondary'):
    b = QPushButton(text)
    b.setProperty('kind', kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(action)
    return b


class EyeStepMark(QWidget):
    def __init__(self, opened, parent=None):
        super().__init__(parent)
        self.opened = opened
        self.setFixedSize(65, 40)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.color(theme.INK), 2))
        for x in (18, 46):
            if self.opened:
                p.setBrush(theme.color(theme.PAPER))
                p.drawEllipse(QPointF(x, 20), 10, 13)
                p.setBrush(theme.color(theme.COBALT))
                p.drawEllipse(QPointF(x + 2, 20), 5, 7)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath(QPointF(x - 10, 15))
                path.cubicTo(x - 6, 29, x + 6, 29, x + 10, 15)
                p.drawPath(path)
                p.drawLine(QPointF(x - 5, 23), QPointF(x - 8, 29))
                p.drawLine(QPointF(x + 5, 23), QPointF(x + 8, 29))
        p.end()


class EyeExerciseDialog(QDialog):
    watered = Signal()

    def __init__(self, window, plant, parent=None):
        super().__init__(parent)
        self.window = window
        self.exercise = EyeExercise()
        self.mode = None
        self.last_received = None
        self.setWindowTitle('Water ' + PLANTS[plant].name)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(f'QDialog {{ background: {theme.PAPER}; }}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(label('A MOMENT FOR YOU', 'eyebrow', theme.ui_font(12)))
        layout.addWidget(label('Water ' + PLANTS[plant].name, font=theme.ui_font(28)))
        layout.addWidget(label('Settle in. Follow each step gently; there is no rush.', wrap=True))
        self.rows = []
        for index, text in enumerate(('Open eyes. Count 1, 2.', 'Close eyes. Count 1, 2.', 'Gently close again. Count 1, 2.')):
            row = label(text, font=theme.ui_font(17), wrap=True)
            line = QHBoxLayout()
            line.addWidget(EyeStepMark(index == 0))
            line.addWidget(row, 1)
            layout.addLayout(line)
            self.rows.append(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setAccessibleName('Current hold progress (two seconds)')
        layout.addWidget(self.bar)
        self.status = label('Use the camera to verify each eye exercise step.', wrap=True)
        layout.addWidget(self.status)
        layout.addWidget(label('The camera verifies bilateral closure only. Eyelid squeezing is not independently measured.',
                               'secondary', theme.ui_font(12), wrap=True))
        self.camera = button('Use my eyes', self.start_camera, 'primary')
        layout.addWidget(self.camera)
        layout.addWidget(button('Cancel', self.reject, 'quiet'))
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.render()

    def start_camera(self):
        problem = self.window.start_game_camera()
        if problem:
            self.status.setText(problem)
            return
        self.mode = 'eyes'
        self.last_received = None
        self.exercise = EyeExercise()
        self.camera.hide()
        self.status.setText('Camera starting · waiting for both eyes.')
        self.render()

    def feed(self, update):
        if self.mode != 'eyes' or self.exercise.complete:
            return
        self.last_received = time.monotonic()
        obs = update.observation
        valid = obs is not None and obs.valid and update.openness is not None
        left, right = update.openness[:2] if valid else (None, None)
        previous = self.exercise.step
        self.exercise.feed(obs.t if obs else self.last_received, left, right, valid)
        self.status.setText('Tracking both eyes' if valid else 'Tracking lost · face the camera. This hold starts again.')
        if self.exercise.reopen_required:
            self.status.setText('Open your eyes briefly before the final gentle closure.')
        elif self.exercise.step != previous and not self.exercise.complete:
            self.status.setText('Step complete · follow the next instruction.')
        self.render()
        self.finish_if_ready()

    def render(self):
        for i, row in enumerate(self.rows):
            text = ('Open eyes. Count 1, 2.', 'Close eyes. Count 1, 2.', 'Gently close again. Count 1, 2.')[i]
            row.setText(('✓  ' if i < self.exercise.step else f'{i + 1}.  ') + text)
            color = theme.GREEN if i < self.exercise.step else theme.COBALT if i == self.exercise.step else theme.GRAPHITE
            row.setStyleSheet(f'color: {color}; padding: 9px; border-radius: 9px; background: {theme.PAPER_DEEP};')
        self.bar.setValue(round(self.exercise.progress * 100))

    def tick(self):
        if self.mode == 'eyes':
            if self.window.state != 'playing':
                self.exercise.interrupt()
                self.status.setText('Camera stopped · restart detection to continue.')
                self.camera.show()
                self.mode = None
            elif self.last_received is None or time.monotonic() - self.last_received > .5:
                self.exercise.interrupt()
                self.status.setText('Waiting for reliable eye tracking · current hold reset.')
        self.render()

    def finish_if_ready(self):
        if self.exercise.complete:
            self.timer.stop()
            self.window.stop_game_camera()
            self.watered.emit()
            self.accept()

    def done(self, result):
        self.timer.stop()
        self.window.stop_game_camera()
        super().done(result)


class GardenShop(QDialog):
    def __init__(self, store, on_change, parent=None, planting=None):
        super().__init__(parent)
        self.store, self.on_change, self.planting = store, on_change, planting
        self.setWindowTitle('Choose a seed' if planting is not None else 'The garden shop')
        self.setMinimumWidth(400)
        self.setStyleSheet(f'QDialog {{ background: {theme.PAPER}; }}')
        layout = QVBoxLayout(self)
        self.balance = label('', font=theme.ui_font(23)) if planting is not None else CoinBalance()
        layout.addWidget(self.balance)
        self.buttons = {}
        for key in list(PLANTS) + ([] if planting is not None else list(SHOP)):
            b = button('', lambda checked=False, k=key: self.choose(k))
            layout.addWidget(b)
            self.buttons[key] = b
        self.status = label('', wrap=True)
        layout.addWidget(self.status)
        layout.addWidget(button('Close', self.accept, 'quiet'))
        self.refresh()

    def refresh(self):
        g = self.store.garden
        self.balance.setText('Choose a seed' if self.planting is not None else f'{g.coins} coins')
        for key, b in self.buttons.items():
            if key in PLANTS:
                plant = PLANTS[key]
                b.setText(f'{plant.name} · {g.seeds[key]} seeds' + ('' if self.planting is not None else f' · buy 1 for {plant.seed_price}'))
                enabled = g.seeds[key] > 0 if self.planting is not None else g.coins >= plant.seed_price
            else:
                name, cost = SHOP[key]
                owned = key in g.decorations or (key == 'plot' and len(g.plots) >= 9)
                b.setText(name + (' · owned' if owned else f' · {cost} coins'))
                enabled = not owned and g.coins >= cost
            b.setEnabled(enabled and not self.store.read_only)

    def choose(self, key):
        if self.planting is not None:
            ok = self.store.change(lambda g: g.plant(self.planting, key))
        else:
            ok = self.store.change(lambda g: g.buy(key))
        message = ('Planted!' if self.planting is not None else 'Added to your garden.') if ok else 'Not enough coins or seeds.'
        self.status.setText(self.store.error or message)
        self.on_change()
        self.refresh()
        if ok and self.planting is not None:
            self.accept()
