"""Blink Code: the Morse decoder, the game rules, and playing in the window."""

import os
import random
import time
import unittest

from ocusense.core.morse import (
    DECODE, LEARN_ORDER, MORSE, WORDS, ChallengeGame, LearnGame, MorseDecoder, encode,
)


def blink(decoder, start, durations, gap=0.3):
    """Feed closures of the given durations with `gap` seconds between them; returns the end time."""
    t = start
    for d in durations:
        decoder.closure(t, t + d)
        t += d + gap
    return t


class DecoderTest(unittest.TestCase):
    def test_table_is_complete_and_unique(self):
        self.assertEqual(len(MORSE), 26)
        self.assertEqual(len(DECODE), 26)
        self.assertEqual(sorted(LEARN_ORDER), sorted(MORSE))
        self.assertEqual(encode("sos"), "... --- ...")
        for word in WORDS:
            self.assertTrue(all(c in MORSE for c in word), word)

    def test_short_is_dot_long_is_dash(self):
        d = MorseDecoder(dash_seconds=0.45)
        self.assertEqual(d.closure(0, 0.2).symbol.mark, ".")
        self.assertEqual(d.closure(1, 1.45).symbol.mark, "-")  # exactly the dash length counts as a dash

    def test_a_pause_ends_the_letter_then_the_word(self):
        d = MorseDecoder(dash_seconds=0.45, letter_gap=1.2, word_gap=2.6)
        end = blink(d, 0, (0.2, 0.2, 0.2))  # S
        self.assertIsNone(d.tick(end + 0.5))
        letter = d.tick(end + 1.3)
        self.assertEqual((letter.kind, letter.code, letter.letter), ("letter", "...", "S"))
        self.assertEqual(d.tick(end + 2.7).kind, "space")
        self.assertIsNone(d.tick(end + 9))  # only one space per pause

    def test_unknown_code_is_none(self):
        d = MorseDecoder()
        end = blink(d, 0, (0.6,) * 6)
        self.assertIsNone(d.tick(end + 2).letter)

    def test_letter_fuse(self):
        d = MorseDecoder(letter_gap=1.0)
        end = blink(d, 0, (0.2,), gap=0)
        self.assertAlmostEqual(d.letter_progress(end + 0.5), 0.5)


class GameRulesTest(unittest.TestCase):
    def test_learn_unlocks_after_three_right(self):
        game = LearnGame(rng=random.Random(1))
        for _ in range(3):
            target = game.next_target()
            right, unlocked = game.answer(target)
            self.assertTrue(right)
        self.assertTrue(unlocked)
        self.assertEqual(game.unlocked, 3)  # E, T, then I
        self.assertEqual(game.answer("Z"), (False, False))
        self.assertEqual(game.streak, 0)
        self.assertEqual(game.best_streak, 3)

    def test_challenge_scores_combos_and_words(self):
        game = ChallengeGame(rng=random.Random(2))
        game.start(0)
        word = game.word
        for letter in word:
            right, finished = game.answer(letter)
        self.assertTrue(finished)
        self.assertEqual(game.words_done, 1)
        self.assertGreater(game.score, 25 * len(word))
        self.assertNotEqual(game.word, word)  # a new word
        combo = game.combo
        game.answer("?")
        self.assertEqual(game.combo, 0)
        self.assertGreater(combo, 0)
        self.assertTrue(game.over(91))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.helpers import Observer  # noqa: E402
from tests.test_main_window import MODEL_PATH, FakeThread, update  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class BlinkCodeWindowTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]
        self.window.show_page("games")
        self.page = self.window.games_page
        self.page.open_blink_code()
        self.game = self.page.blink_code

    def tearDown(self):
        self.window.close()

    def finish_letter(self):
        self.game.decoder._last_end -= 5  # the pause that ends the letter has passed
        self.game.tick()

    def test_in_the_sidebar(self):
        self.window.sidebar.items["games"].click()
        self.assertIs(self.window.pages.currentWidget(), self.page)

    def test_space_bar_plays_learn_mode(self):
        g = self.game
        g.set_input("keys")
        g.learn.target = "E"
        g._show_learn()
        QTest.keyPress(g, Qt.Key.Key_Space)
        QTest.keyRelease(g, Qt.Key.Key_Space)  # a quick tap: a dot
        self.assertEqual(g.decoder.code, ".")
        self.finish_letter()
        self.assertEqual(g.learn.correct, 1)
        self.assertIn("Yes! E", g.canvas.message)
        self.assertFalse(g.canvas.grab().isNull())

    def test_eyes_need_a_calibration_then_play_without_recording(self):
        w, g = self.window, self.game
        g.toggle_camera()
        self.assertIn("Calibrate once", g.status.text())  # no calibration yet
        self.assertNotEqual(w.state, "playing")
        w.monitor.calibration = object()
        w.start()  # a study session is running…
        g.toggle_camera()
        self.assertEqual(w.state, "playing")  # …and now waits, paused
        self.assertIsNotNone(w.recorder)
        blinks_before = w.recorder.blinks
        rows_before = len(w.ear_log.rows)
        g.mode = "free"
        g.set_mode("free")
        observe = Observer()
        t0 = time.monotonic()
        for i in range(60):  # a long closure (a dash) through the real detector
            t = t0 + i / 30
            value = 0.05 if 0.5 <= t - t0 < 1.3 else 0.9
            obs = observe(t, value)
            w._on_update(update(now=t, openness=(value, value, value), blinked=obs.blink_completed,
                                observation=obs))
        self.assertEqual(g.decoder.code, "-")
        self.finish_letter()
        self.assertEqual(g.canvas.typed, "T")
        self.assertEqual(w.recorder.blinks, blinks_before)  # never in the study session
        self.assertEqual(len(w.ear_log.rows), rows_before)  # never in the EAR recording
        self.page.show_hub()
        self.assertEqual(w.state, "paused")  # the session is still there, paused
        self.assertTrue(self.thread.stopped)

    def test_challenge_and_high_score(self):
        g = self.game
        g.set_input("keys")
        g.set_mode("challenge")
        g.start_challenge()
        for letter in g.challenge.word:
            g._letter(letter, MORSE[letter])
        self.assertEqual(g.challenge.words_done, 1)
        g.challenge.started_at -= 100  # time is up
        g.tick()
        self.assertIn("high score", g.canvas.message)
        self.assertGreater(self.window.preferences.morse_high_score, 0)

    def test_dash_length_is_remembered(self):
        self.game.dash_slider.setValue(600)
        self.assertEqual(self.game.decoder.dash_seconds, 0.6)
        self.assertEqual(self.window.preferences.morse_dash_ms, 600)


if __name__ == "__main__":
    unittest.main()
