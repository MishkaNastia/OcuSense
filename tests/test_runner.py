"""EyeGame (MishkaNastia's blink runner): the rules, double blinks, and playing it in the window."""

import os
import random
import time
import unittest

from ocusense.core import runner as R
from ocusense.core.runner import EyeClosures, Obstacle, Presses, Rect, RunnerGame, Sizes, png_size


def new_game(**kw):
    return RunnerGame(Sizes.load(), rng=random.Random(4), **kw)


def run(game, seconds, dt=1 / 60, down=False):
    for _ in range(int(seconds / dt)):
        game.update(dt, down)


class AssetsTest(unittest.TestCase):
    def test_all_art_is_there(self):
        sizes = Sizes.load()
        self.assertEqual(png_size(R.ASSETS / "avatar.png"), (536, 418))
        self.assertEqual([o.id for o in sizes.obstacles], ["toilet"])  # only toilets
        self.assertEqual(sizes.obstacles[0].effect, "poop")
        for o in sizes.obstacles:
            self.assertTrue((R.ASSETS / "obstacles" / o.file).exists(), o.file)
        self.assertEqual(set(sizes.powerups), set(R.POWERUPS))


class BlinkInputTest(unittest.TestCase):
    def test_one_jump_per_press(self):
        d = Presses(cooldown_s=0.1)
        self.assertTrue(d.press(0.0))
        self.assertFalse(d.press(0.05))  # within the cooldown: the same blink
        self.assertTrue(d.press(0.3))
        self.assertTrue(d.press(2.0))

    def feed(self, closures, values):
        """Openness per frame → the frames on which the eyes closed."""
        return [i for i, v in enumerate(values) if closures.update(v)]

    def test_a_quick_double_blink_with_a_half_reopening_counts_twice(self):
        # open → closed → only 55 % open → closed again → open (a fast double blink at 30 fps)
        values = [0.9] * 3 + [0.1] * 3 + [0.55] * 2 + [0.1] * 3 + [0.9] * 3
        self.assertEqual(self.feed(EyeClosures(), values), [3, 8])
        from ocusense.core.blink_counter import BlinkCounter  # the study detector would only see one
        study, seen = BlinkCounter(), []
        for i, v in enumerate(values):
            before = study.state
            study.update(v)
            if before == BlinkCounter.OPEN and study.state == BlinkCounter.CLOSED:
                seen.append(i)
        self.assertEqual(seen, [3])

    def test_lost_eyes_and_starting_closed_never_jump(self):
        closures = EyeClosures()
        self.assertEqual(self.feed(closures, [0.1, 0.1, None, 0.1]), [])  # must see open eyes first
        self.assertEqual(self.feed(closures, [0.9, None, 0.1, 0.9, 0.1]), [4])  # a lost frame forgets "open"


class RulesTest(unittest.TestCase):
    def test_blink_starts_and_jumps(self):
        g = new_game()
        self.assertEqual(g.state, "title")
        g.jump()
        self.assertEqual(g.state, "play")
        run(g, 0.2)
        self.assertGreater(g.player.y, 50)  # in the air
        run(g, 1.0)
        self.assertEqual(g.player.y, 0)  # landed

    def test_extra_jump_only_in_the_air_once(self):
        g = new_game()
        g.jump()
        run(g, 0.3)
        g.jump()
        self.assertTrue(g.player.extra)
        vy = g.player.vy
        g.jump()
        self.assertEqual(g.player.vy, vy)  # only one extra jump per jump
        peak = 0.0
        for _ in range(120):
            g.update(1 / 60)
            peak = max(peak, g.player.y)
        self.assertAlmostEqual(peak, R.EXTRA_JUMP_APEX, delta=8)  # a fixed peak: stays on screen

    def test_a_late_second_blink_still_gives_the_extra_jump(self):
        g = new_game()
        g.jump()
        run(g, 0.6)  # well after the old 0.5 s double-blink window, still in the air
        self.assertGreater(g.player.y, 0)
        g.jump()
        self.assertTrue(g.player.extra)
        self.assertLess(g.player.vy, 0)  # going up again

    def test_score_speed_and_crash(self):
        g = new_game(highscore=5)
        g.jump()
        run(g, 0.7)
        self.assertGreater(g.score, 5)
        self.assertGreater(g.speed, R.START_SPEED)
        g.obstacles = [Obstacle(R.PLAYER_X - 20, "ground", g.sizes.obstacles[0], g.rng)]
        g.update(1 / 60)
        self.assertEqual(g.state, "over")
        self.assertEqual(g.killed_by, "Grades went down the drain")
        self.assertTrue(g.new_record)
        g.jump()
        self.assertEqual(g.state, "over")  # the crash blink doesn't restart right away
        run(g, 0.7)
        g.jump()
        self.assertEqual(g.state, "play")
        self.assertEqual(g.score, 0)

    def test_toilet_splats(self):
        g = new_game()
        g.jump()
        g.update(1 / 60)
        while g.player.y > 0:
            g.update(1 / 60)
        toilet = next(o for o in g.sizes.obstacles if o.effect == "poop")
        g.obstacles = [Obstacle(R.PLAYER_X - 20, "ground", toilet, g.rng)]
        g.update(1 / 60)
        self.assertIsNotNone(g.player.splat)

    def test_run_under_a_high_flyer_and_ducking(self):
        g = new_game()
        g.jump()
        run(g, 1.0)
        g.obstacles = [Obstacle(R.PLAYER_X - 20, "high", g.sizes.obstacles[0], g.rng)]
        g.update(1 / 60)
        self.assertEqual(g.state, "play")  # high flyers pass over you
        g.update(1 / 60, down=True)
        self.assertLess(g.player.eye_rect().h, g.player.eye_size[1])

    def test_powerup_doubles_points(self):
        g = new_game()
        g.jump()
        run(g, 1.0)
        g.obstacles = []
        g.powerups = [R.PowerUp(R.PLAYER_X - 20, False, "coffee", g.sizes.powerups["coffee"], g.rng)]
        g.update(1 / 60)
        self.assertGreater(g.double_timer, 4.9)
        self.assertEqual(g.double_kind, "coffee")
        self.assertEqual(g.popups[0].text, "2x POINTS!")

    def test_a_long_run_spawns_and_never_breaks(self):
        g = new_game()
        g.jump()
        kinds = set()
        for i in range(60 * 60):
            g.update(1 / 60)
            kinds |= {o.kind for o in g.obstacles}
            if g.state == "over":
                g.over_timer = 1
                g.jump()
                g.score = 400  # so flyers show up too
        self.assertIn("ground", kinds)
        self.assertTrue(kinds & {"low", "high"})

    def test_rect(self):
        self.assertTrue(Rect(0, 0, 10, 10).collides(Rect(9, 9, 5, 5)))
        self.assertFalse(Rect(0, 0, 10, 10).collides(Rect(10, 0, 5, 5)))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.helpers import Observer  # noqa: E402
from tests.test_main_window import MODEL_PATH, FakeThread, update  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class EyeGameWindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.window.show_page("games")
        self.page = self.window.games_page
        self.page.open_eye_runner()
        self.game = self.page.eye_runner

    def tearDown(self):
        self.window.close()

    def test_space_starts_and_draws(self):
        g = self.game
        QTest.keyClick(g, Qt.Key.Key_Space)
        self.assertEqual(g.game.state, "play")
        g.tick()
        self.assertFalse(g.canvas.grab().isNull())

    def test_eyes_jump_without_recording_and_high_score_is_kept(self):
        w, g = self.window, self.game
        w.monitor.calibration = object()
        w.start()  # a study session is running…
        g.toggle_camera()
        self.assertEqual(w.state, "playing")  # …and now waits, paused
        blinks_before = w.recorder.blinks
        rows_before = len(w.ear_log.rows)
        observe = Observer()
        t0 = time.monotonic()
        for i in range(30):  # one blink through the real detector
            t = t0 + i / 30
            value = 0.05 if 0.3 <= t - t0 < 0.5 else 0.9
            obs = observe(t, value)
            w._on_update(update(now=t, openness=(value, value, value), blinked=obs.blink_completed, observation=obs))
        self.assertEqual(g.game.state, "play")  # the blink started the run
        self.assertEqual(w.recorder.blinks, blinks_before)  # never in the study session
        self.assertEqual(len(w.ear_log.rows), rows_before)
        g.game.score = 123
        g.game.obstacles = [R.Obstacle(R.PLAYER_X - 20, "ground", g.game.sizes.obstacles[0], g.game.rng)]
        g.game.player.y, g.game.player.vy = 0, 0
        g.clock.restart()
        QTest.qWait(20)  # one real frame step
        g.tick()
        self.assertEqual(g.game.state, "over")
        self.assertEqual(w.preferences.runner_high_score, 123)
        self.page.show_hub()
        self.assertEqual(w.state, "paused")
        self.assertTrue(self.thread.stopped)

    def test_on_the_games_hub(self):
        self.page.show_hub()
        self.page.open_eye_runner()
        self.assertIs(self.page.stack.currentWidget(), self.game)


if __name__ == "__main__":
    unittest.main()
