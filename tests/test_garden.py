import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ocusense.core.garden import Garden, PLANTS
from ocusense.core.garden_exercise import EyeExercise, GardenReminder
from ocusense.garden_store import GardenStore


def hold(exercise, start, left, right, seconds=2):
    for i in range(round(seconds * 10) + 1):
        exercise.feed(start + i / 10, left, right)


class ExerciseTest(unittest.TestCase):
    def test_continuous_bilateral_steps_and_reopen(self):
        e = EyeExercise()
        hold(e, 0, 1, .2)
        self.assertEqual(e.step, 0)
        hold(e, 3, 1, 1)
        self.assertEqual(e.step, 1)
        hold(e, 6, 0, 0)
        self.assertEqual(e.step, 2)
        hold(e, 9, 0, 0, 4)
        self.assertFalse(e.complete)
        e.feed(13.1, 1, 1)
        hold(e, 13.2, 0, 0)
        self.assertTrue(e.complete)

    def test_interruption_resets_current_hold(self):
        e = EyeExercise()
        hold(e, 0, 1, 1, 1)
        e.feed(1.1, None, None, False)
        hold(e, 1.2, 1, 1, 1.9)
        self.assertEqual(e.step, 0)
        e.feed(3.2, 1, 1)
        self.assertEqual(e.step, 1)

    def test_frame_gap_wrong_state_and_nonmonotonic(self):
        for interruption in ((3, 1, 1), (1.1, 0, 0), (.8, 1, 1)):
            e = EyeExercise()
            hold(e, 0, 1, 1, 1)
            e.feed(*interruption)
            self.assertEqual(e.progress, 0)
            self.assertEqual(e.step, 0)

    def test_unsupported_squeeze_mode(self):
        with self.assertRaises(ValueError):
            EyeExercise(closure_mode='squeeze')


class GardenTest(unittest.TestCase):
    def test_lifecycle_and_duplicate_harvest(self):
        g = Garden()
        self.assertEqual(g.plots[0].state(0), 'NEEDS_WATER')
        self.assertFalse(g.water(0, 0))
        self.assertTrue(g.begin(0, 0))
        self.assertEqual(g.plots[0].state(0), 'EXERCISING')
        g.cancel(0)
        self.assertEqual(g.plots[0].state(0), 'NEEDS_WATER')
        g.begin(0, 0)
        self.assertTrue(g.water(0, 100))
        self.assertFalse(g.water(0, 101))
        self.assertEqual(g.plots[0].ready_at, 7300)
        self.assertEqual(g.harvest(0, 7299), 0)
        self.assertEqual(g.harvest(0, 7300), 25)
        self.assertEqual(g.harvest(0, 7300), 0)
        self.assertEqual(g.coins, 50)
        self.assertTrue(g.plant(0, 'carrot'))
        self.assertFalse(g.plant(0, 'carrot'))
        self.assertEqual(g.seeds['carrot'], 0)

    def test_all_crops_and_growth_stages(self):
        g = Garden()
        for i, (key, plant) in enumerate(PLANTS.items()):
            g.begin(i, 0)
            g.water(i, 100)
            for fraction in (0, .25, .5, .75, 1):
                self.assertAlmostEqual(g.plots[i].growth(100 + fraction * plant.seconds), fraction)
            self.assertEqual(g.harvest(i, 100 + plant.seconds), plant.reward)

    def test_legacy_carrots_use_three_minutes_after_reload(self):
        data = Garden().to_dict()
        data['plots'][1].update(watered_at=100, ready_at=3700)
        garden = Garden.from_dict(data)
        self.assertEqual(garden.plots[1].ready_at, 280)
        self.assertEqual(garden.plots[1].state(279), 'GROWING')
        self.assertEqual(garden.plots[1].state(280), 'READY_TO_HARVEST')
        self.assertEqual(Garden.from_dict(garden.to_dict()).plots[1].ready_at, 280)

    def test_legacy_tomatoes_use_five_minutes_after_reload(self):
        data = Garden().to_dict()
        data['plots'][2].update(watered_at=100, ready_at=10900)
        garden = Garden.from_dict(data)
        self.assertEqual(garden.plots[2].ready_at, 400)
        self.assertEqual(garden.plots[2].state(399), 'GROWING')
        self.assertEqual(garden.plots[2].state(400), 'READY_TO_HARVEST')
        self.assertEqual(Garden.from_dict(garden.to_dict()).plots[2].ready_at, 400)

    def test_shop(self):
        g = Garden(coins=0)
        self.assertFalse(g.buy('flowers'))
        g.coins = 300
        self.assertTrue(g.buy('flowers'))
        self.assertFalse(g.buy('flowers'))
        self.assertTrue(g.buy('carrot'))
        self.assertEqual(g.seeds['carrot'], 2)
        for _ in range(3):
            self.assertTrue(g.buy('plot'))
        self.assertFalse(g.buy('plot'))
        self.assertEqual(g.coins, 98)

    def test_persistence_restart_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'garden.json'
            store = GardenStore(path)
            store.garden.begin(0, 0)
            self.assertTrue(store.change(lambda g: g.water(0, 100)))
            restored = GardenStore(path)
            self.assertEqual(restored.garden.plots[0].state(7300), 'READY_TO_HARVEST')
            with patch.object(Path, 'replace', side_effect=OSError):
                self.assertFalse(restored.change(lambda g: g.harvest(0, 7300)))
            self.assertEqual(restored.garden.coins, 25)
            self.assertEqual(restored.garden.plots[0].state(7300), 'READY_TO_HARVEST')
            self.assertEqual(restored.change(lambda g: g.harvest(0, 7300)), 25)
            again = GardenStore(path)
            self.assertEqual(again.garden.coins, 50)
            self.assertEqual(again.garden.harvest(0, 8000), 0)

    def test_bad_save_preserved_and_interrupted_exercise_not_restored(self):
        g = Garden()
        g.begin(0, 0)
        self.assertEqual(Garden.from_dict(g.to_dict()).plots[0].state(0), 'NEEDS_WATER')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'garden.json'
            path.write_text('broken')
            store = GardenStore(path)
            self.assertTrue(store.read_only)
            self.assertFalse(store.change(lambda g: g.buy('carrot')))
            self.assertEqual(path.read_text(), 'broken')

    def test_reminder_monitoring_snooze_and_disable(self):
        r = GardenReminder()
        for t in range(301):
            due = r.update(t, True, True, 5, True)
        self.assertTrue(due)
        r.snooze(300)
        for t in range(301, 901):
            due = r.update(t, True, True, 5, True)
            if t < 900:
                self.assertFalse(due)
        self.assertTrue(due)
        self.assertFalse(r.update(901, True, False, 5, True))
        self.assertEqual(r.elapsed, 0)


class GardenUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_camera_complete_harvest_replant_and_cancel(self):
        from ocusense.preferences import Preferences
        from ocusense.ui.blink_garden_page import BlinkGardenGame
        with tempfile.TemporaryDirectory() as folder:
            window = SimpleNamespace(preferences=Preferences(), state='ready', start_game_camera=Mock(return_value='Calibrate first'), stop_game_camera=Mock())
            widget = BlinkGardenGame(window, store=GardenStore(Path(folder) / 'garden.json'))
            widget.show()
            widget.select_plot(0)
            dialog = widget.exercise_dialog
            dialog.start_camera()
            self.assertIsNone(dialog.mode)
            self.assertIsNone(widget.store.garden.plots[0].ready_at)
            from PySide6.QtWidgets import QPushButton
            self.assertEqual(
                [b.text() for b in dialog.findChildren(QPushButton)],
                ['Use my eyes', 'Cancel'],
            )
            dialog.tick()
            self.assertEqual(dialog.exercise.step, 0)
            window.start_game_camera.return_value = ''
            window.state = 'playing'
            dialog.start_camera()
            for t, value in [(i / 10, 1) for i in range(21)] + [(3 + i / 10, 0) for i in range(21)] + [(5.1, 1)] + [(5.2 + i / 10, 0) for i in range(22)]:
                dialog.feed(SimpleNamespace(observation=SimpleNamespace(t=t, valid=True), openness=(value, value, value)))
            self.assertIsNone(widget.exercise_dialog)
            deadline = widget.store.garden.plots[0].ready_at
            self.assertIsNotNone(deadline)
            with patch('ocusense.ui.blink_garden_page.time.time', return_value=deadline):
                widget.select_plot(0)
            self.assertEqual(widget.store.garden.coins, 50)
            widget.select_plot(0)
            widget.shop_dialog.choose('carrot')
            self.assertEqual(widget.store.garden.plots[0].plant, 'carrot')
            widget.select_plot(0)
            widget.hide()
            self.assertIsNone(widget.exercise_dialog)
            self.assertEqual(widget.store.garden.plots[0].state(0), 'NEEDS_WATER')
            self.assertFalse(widget.timer.isActive())
            widget.close()

    def test_camera_drives_exercise_and_stops(self):
        from ocusense.ui.garden_dialogs import EyeExerciseDialog
        window = SimpleNamespace(state='playing', start_game_camera=Mock(return_value=''), stop_game_camera=Mock())
        dialog = EyeExerciseDialog(window, 'strawberry')
        completed = Mock()
        dialog.watered.connect(completed)
        dialog.start_camera()
        for t, value in [(i / 10, 1) for i in range(21)] + [(3 + i / 10, 0) for i in range(21)] + [(5.1, 1)] + [(5.2 + i / 10, 0) for i in range(22)]:
            dialog.feed(SimpleNamespace(observation=SimpleNamespace(t=t, valid=True), openness=(value, value, value)))
        completed.assert_called_once()
        window.stop_game_camera.assert_called()
        dialog.close()
