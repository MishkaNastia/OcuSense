"""Baseline drift: MLE log-normal fits, the two-sample likelihood-ratio test and sliding windows."""

import math
import random
import unittest

from ocusense.core.baseline_drift import (
    NO_BASELINE, NO_SPREAD, NOT_ENOUGH_DATA, TESTED, BreakReminder, Fit, LiveDrift, WindowResult, baseline_intervals,
    break_reminders, fit_lognormal, likelihood_ratio_test, log_likelihood, sliding_windows, with_run,
)
from ocusense.core.replay import replay
from tests.test_distributions import CAL, blinks, rows_from

try:
    from scipy import stats
except ImportError:  # scipy is not an app dependency; the cross-check is optional
    stats = None


def lognormal(rng, n, mu, sigma):
    return [rng.lognormvariate(mu, sigma) for _ in range(n)]


class FitTest(unittest.TestCase):
    def test_mle_matches_closed_form(self):
        values = [1.0, math.e, math.e ** 2, math.e ** 3]  # logs 0, 1, 2, 3
        mu, sigma, n = fit_lognormal(values)
        self.assertEqual(n, 4)
        self.assertAlmostEqual(mu, 1.5)
        self.assertAlmostEqual(sigma, math.sqrt(1.25))  # (2.25 + 0.25 + 0.25 + 2.25) / 4: ddof = 0, not 5 / 3

    def test_non_positive_intervals_are_excluded(self):
        self.assertEqual(fit_lognormal([0.0, -1.0, 1.0, math.e])[2], 2)

    def test_fewer_than_two_intervals_gives_no_fit(self):
        self.assertIsNone(fit_lognormal([2.0]))
        self.assertIsNone(fit_lognormal([0.0, 3.0]))

    def test_log_likelihood_is_normal_on_the_logs(self):
        values = [0.5, 2.0, 3.0]
        expected = sum(-0.5 * math.log(2 * math.pi * 0.64) - (math.log(x) - 0.2) ** 2 / (2 * 0.64) for x in values)
        self.assertAlmostEqual(log_likelihood(values, 0.2, 0.8), expected)

    @unittest.skipUnless(stats, "scipy not installed")
    def test_matches_scipy(self):
        values = lognormal(random.Random(1), 200, 0.7, 0.9)
        mu, sigma, _ = fit_lognormal(values)
        s, _loc, scale = stats.lognorm.fit(values, floc=0)
        self.assertAlmostEqual(sigma, s, places=4)
        self.assertAlmostEqual(mu, math.log(scale), places=4)
        logs = [math.log(x) for x in values]
        self.assertAlmostEqual(log_likelihood(values, mu, sigma), stats.norm.logpdf(logs, mu, sigma).sum(), places=6)


class LikelihoodRatioTest(unittest.TestCase):
    def test_window_equal_to_baseline_gives_lr_zero(self):
        values = lognormal(random.Random(2), 60, 0.7, 0.9)
        test = likelihood_ratio_test(values, values)
        self.assertEqual(test.status, TESTED)
        self.assertAlmostEqual(test.lr, 0.0, places=9)
        self.assertAlmostEqual(test.p, 1.0, places=9)

    @unittest.skipUnless(stats, "scipy not installed")
    def test_p_value_is_chi_square_two_degrees_of_freedom(self):
        rng = random.Random(3)
        test = likelihood_ratio_test(lognormal(rng, 80, 0.7, 0.9), lognormal(rng, 30, 1.0, 0.9))
        self.assertAlmostEqual(test.p, stats.chi2.sf(test.lr, 2), places=12)

    def test_same_distribution_is_rarely_flagged(self):
        rng = random.Random(4)
        flagged = sum(likelihood_ratio_test(lognormal(rng, 100, 0.7, 0.9), lognormal(rng, 30, 0.7, 0.9)).p < 0.01
                      for _ in range(500))
        self.assertLess(flagged / 500, 0.04)  # about 1 % expected

    def test_twice_as_long_intervals_are_flagged(self):
        rng = random.Random(5)
        flagged = sum(likelihood_ratio_test(lognormal(rng, 100, 0.7, 0.6),
                                            lognormal(rng, 40, 0.7 + math.log(2), 0.6)).p < 0.01
                      for _ in range(200))
        self.assertGreater(flagged / 200, 0.95)

    def test_degenerate_cases_are_not_tested(self):
        good = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(likelihood_ratio_test([2.0, 2.0, 2.0], good).status, NO_BASELINE)
        self.assertEqual(likelihood_ratio_test([5.0], good).status, NO_BASELINE)
        self.assertEqual(likelihood_ratio_test(good, [3.0]).status, NOT_ENOUGH_DATA)
        test = likelihood_ratio_test(good, [3.0, 3.0, 3.0])
        self.assertEqual(test.status, NO_SPREAD)
        self.assertIsNone(test.p)


class SlidingWindowTest(unittest.TestCase):
    @staticmethod
    def pairs(onsets):
        return list(zip(onsets, onsets[1:]))

    def test_window_starts_and_overlap_with_baseline(self):
        windows = sliding_windows([], 0.0, 1000.0)
        self.assertEqual([w.start for w in windows], [i * 30.0 for i in range(24)])  # last full one: 690–990
        self.assertTrue(all(w.end == w.start + 300 for w in windows))
        self.assertEqual(sum(w.overlaps_baseline for w in windows), 20)  # starts 0 … 570
        self.assertTrue(all(w.status == NOT_ENOUGH_DATA and w.p is None for w in windows))

    def test_custom_step_and_start(self):
        windows = sliding_windows([], 100.0, 700.0, step=60)
        self.assertEqual([w.start for w in windows], [100.0, 160.0, 220.0, 280.0, 340.0, 400.0])

    def test_interval_needs_both_onsets_inside(self):
        windows = sliding_windows(self.pairs([290.0, 310.0]), 0.0, 600.0, min_intervals=1)
        self.assertEqual(windows[0].n, 0)  # 0–300: the second onset is outside
        self.assertEqual(windows[1].n, 1)  # 30–330

    def test_not_enough_data_then_tested(self):
        onsets = [1.0 + 3.0 * i + (i % 3) * 0.5 for i in range(200)]
        windows = sliding_windows(self.pairs(onsets), 0.0, 600.0, min_intervals=15)
        self.assertTrue(all(w.status == TESTED for w in windows))
        sparse = sliding_windows(self.pairs(onsets[:10]), 0.0, 600.0, min_intervals=15)
        self.assertTrue(all(w.status == NOT_ENOUGH_DATA and not w.different for w in sparse))

    def test_excluded_intervals_are_counted(self):
        windows = sliding_windows([(10.0, 10.0), (10.0, 12.0)], 0.0, 300.0, min_intervals=1)
        self.assertEqual((windows[0].n, windows[0].excluded), (1, 1))



class ConfirmationTest(unittest.TestCase):
    @staticmethod
    def chain(flags):
        """flags: per window True (different), False (similar) or None (not tested)."""
        results, previous = [], None
        for i, flag in enumerate(flags):
            status = NOT_ENOUGH_DATA if flag is None else TESTED
            r = WindowResult(i * 30.0, i * 30.0 + 300, 20, 0, None, None, None if flag is None else 0.5,
                             bool(flag), status, False)
            previous = with_run(r, previous)
            results.append(previous)
        return results

    def test_three_in_a_row_confirms(self):
        results = self.chain([True, True, False, True, True, True, True])
        self.assertEqual([r.run for r in results], [1, 2, 0, 1, 2, 3, 4])
        self.assertEqual([r.confirmed for r in results], [False, False, False, False, False, True, True])

    def test_an_untested_window_breaks_the_run(self):
        results = self.chain([True, True, None, True, True])
        self.assertEqual([r.run for r in results], [1, 2, 0, 1, 2])
        self.assertFalse(any(r.confirmed for r in results))

class BreakReminderTest(unittest.TestCase):
    BASE_MU = 1.0

    @staticmethod
    def windows(kinds):
        """kinds per 30 s window: "slow" / "fast" (below the line), "ok" (similar), None (not tested)."""
        results, previous = [], None
        for i, kind in enumerate(kinds):
            mu = {"slow": 1.8, "fast": 0.3, "ok": 1.0, None: 1.0}[kind]
            r = WindowResult(i * 30.0, i * 30.0 + 300, 20, 0, Fit(mu, 0.8, 20), None,
                             None if kind is None else (0.001 if kind in ("slow", "fast") else 0.5),
                             kind in ("slow", "fast"), NOT_ENOUGH_DATA if kind is None else TESTED, False)
            previous = with_run(r, previous)
            results.append(previous)
        return results

    def test_three_slow_windows_in_a_row_remind_once(self):
        times = break_reminders(self.windows(["slow", "slow", "slow", "slow", "slow"]), self.BASE_MU)
        self.assertEqual(times, [360.0])  # the third window (start 60 s) ends at 360 s

    def test_faster_blinking_never_reminds(self):
        self.assertEqual(break_reminders(self.windows(["fast"] * 10), self.BASE_MU), [])

    def test_two_slow_then_a_gap_doesnt_remind(self):
        self.assertEqual(break_reminders(self.windows(["slow", "slow", None, "slow", "slow"]), self.BASE_MU), [])

    def test_one_reminder_per_stretch(self):
        # a slow stretch with a short break (< 5 min) in the middle is still one stretch
        kinds = ["slow"] * 3 + ["ok"] * 4 + ["slow"] * 3
        self.assertEqual(len(break_reminders(self.windows(kinds), self.BASE_MU, gap_seconds=0)), 1)

    def test_new_stretch_after_five_clear_minutes_and_the_cooldown(self):
        kinds = ["slow"] * 3 + ["ok"] * 10 + ["slow"] * 3  # clear for 5 min → a new stretch
        self.assertEqual(len(break_reminders(self.windows(kinds), self.BASE_MU, gap_seconds=0)), 2)
        self.assertEqual(len(break_reminders(self.windows(kinds), self.BASE_MU)), 1)  # but within 20 min
        later = ["slow"] * 3 + ["ok"] * 40 + ["slow"] * 3  # 20 min later
        self.assertEqual(break_reminders(self.windows(later), self.BASE_MU), [360.0, 360.0 + 43 * 30])

    def test_stretch_suppressed_by_the_cooldown_doesnt_remind_later(self):
        kinds = ["slow"] * 3 + ["ok"] * 10 + ["slow"] * 30  # second stretch starts inside the cooldown
        times = BreakReminder()
        for r in self.windows(kinds):
            times.update(r, self.BASE_MU)
        self.assertEqual(len(times.reminders), 1)


class EndToEndTest(unittest.TestCase):
    def test_slower_blinking_after_the_baseline_is_flagged(self):
        # 15 min: intervals cycle 2, 3, 4, 5 s for the first 10 min, then twice as long.
        onsets, t, i = [], 1.0, 0
        while t < 900 - 1:
            onsets.append(t)
            t += (2.0 + i % 4) * (2 if t >= 600 else 1)
            i += 1
        result = replay(rows_from(blinks(905, onsets)), CAL)  # a little extra: the 600–900 s window must be full
        pairs = result.distributions.intervals
        self.assertEqual(len(pairs), len(onsets) - 1)

        base = baseline_intervals(pairs, 0.0)
        mu, sigma, n = fit_lognormal(base)
        self.assertEqual(n, sum(1 for a, b in zip(onsets, onsets[1:]) if b < 600))
        self.assertAlmostEqual(mu, sum(math.log(x) for x in base) / n)

        windows = sliding_windows(pairs, 0.0, result.timeline.times[-1])
        self.assertEqual([w.start for w in windows], [i * 30.0 for i in range(21)])  # last: 600–900
        first, last = windows[0], windows[-1]
        self.assertTrue(first.overlaps_baseline)
        self.assertFalse(first.different)  # the same pattern as the baseline
        self.assertGreater(first.p, 0.5)
        self.assertFalse(last.overlaps_baseline)
        self.assertTrue(last.different)  # entirely after the change
        self.assertTrue(last.confirmed)  # and the windows before it too
        self.assertAlmostEqual(last.fit.mu - mu, math.log(2), delta=0.05)



class LiveDriftTest(unittest.TestCase):
    @staticmethod
    def session(seconds=1200.0, start=50.0):
        """Onset pairs of a steady blinker (intervals cycling 2–5 s), on a clock starting at `start`."""
        onsets, t, i = [], start + 1.0, 0
        while t < start + seconds:
            onsets.append(t)
            t += 2.0 + i % 4
            i += 1
        return list(zip(onsets, onsets[1:]))

    def test_nothing_before_the_baseline_is_complete(self):
        pairs = self.session()
        live = LiveDrift(50.0)
        self.assertEqual(live.update(pairs, 50.0 + 599), [])
        self.assertIsNone(live.baseline)
        self.assertEqual(live.collecting(pairs, 50.0 + 300)[0], 300.0)

    def test_catches_up_then_one_window_per_step(self):
        pairs = self.session()
        live = LiveDrift(50.0)
        first = live.update(pairs, 50.0 + 600 + live.SETTLE_SECONDS)
        self.assertEqual([w.start - 50.0 for w in first], [i * 30.0 for i in range(11)])  # all ended by 600 s
        self.assertTrue(all(w.overlaps_baseline for w in first))
        self.assertEqual(live.baseline_fit.n, len(baseline_intervals(pairs, 50.0)))
        self.assertEqual(live.update(pairs, 50.0 + 629), [])  # the 330–630 s window hasn't settled yet
        self.assertEqual([w.start - 50.0 for w in live.update(pairs, 50.0 + 636)], [330.0])

    def test_live_results_equal_the_offline_windows(self):
        pairs = self.session()
        live = LiveDrift(50.0)
        now = 50.0
        while now < 50.0 + 1200:
            # only intervals whose second blink has happened by `now` exist yet
            live.update([(a, b) for a, b in pairs if b + 0.2 <= now], now)
            now += 1.0
        offline = sliding_windows(pairs, 50.0, 50.0 + 1200 - live.SETTLE_SECONDS)
        self.assertEqual(live.results, offline)
        self.assertGreater(len(offline), 20)
        self.assertTrue(all(w.status == TESTED and not w.different for w in offline))  # same pattern throughout


if __name__ == "__main__":
    unittest.main()
