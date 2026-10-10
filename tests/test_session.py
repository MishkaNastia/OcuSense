"""Checks for the session recorder and statistics maths. Run with:  python -m unittest"""

import unittest
from datetime import date, datetime

from ocusense.core.session import SessionRecorder
from ocusense.storage import SessionStore
from ocusense.core.stats import combined_metric, format_duration, format_metric, hour_range, period_days, period_stats

FPS = 30
START = datetime(2026, 10, 10, 9, 0, 0)


def feed(recorder, t0, seconds, blink_every=None, closed_for=0.2, openness=0.9):
    """Simulate `seconds` of frames from t0; a blink of `closed_for` s every `blink_every` s."""
    n = int(seconds * FPS)
    was_closed = False
    for i in range(n + 1):
        t = t0 + i / FPS
        value = openness
        if blink_every and 1.0 <= (t - t0) % blink_every < 1.0 + closed_for:
            value = 0.05
        closed = value < 0.35
        recorder.add_frame(t, value, was_closed and not closed)  # blink completes on reopening
        was_closed = closed
    return t0 + n / FPS


class RecorderTest(unittest.TestCase):
    def test_blink_rate_closure_and_closed_time(self):
        r = SessionRecorder(0.0, START)
        end = feed(r, 0.0, 60, blink_every=4, closed_for=0.2)
        s = r.finish(end)
        self.assertEqual(s.blinks, 15)
        self.assertAlmostEqual(s.metric("rate"), 15, delta=0.5)
        self.assertAlmostEqual(s.metric("closure"), 0.200, delta=0.040)  # seconds, within a frame or so
        self.assertAlmostEqual(s.metric("closed"), 15 * 0.2 / 60 * 100, delta=0.6)
        self.assertAlmostEqual(s.coverage, 1.0, delta=0.02)

    def test_pause_is_not_study_time(self):
        r = SessionRecorder(0.0, START)
        feed(r, 0.0, 30)
        r.pause(30.0)
        r.resume(130.0)  # 100 s paused
        end = feed(r, 130.0, 30)
        s = r.finish(end)
        self.assertAlmostEqual(s.study_seconds, 60, delta=0.1)
        self.assertEqual(len(s.segments), 2)
        self.assertEqual(s.ended_at, datetime(2026, 10, 10, 9, 2, 40))

    def test_lost_tracking_is_a_gap_not_zero(self):
        r = SessionRecorder(0.0, START)
        feed(r, 0.0, 10)
        for i in range(int(5 * FPS)):
            r.add_frame(10 + i / FPS, None, False)
        end = feed(r, 15.0, 10)
        s = r.finish(end)
        self.assertEqual(len(s.untracked), 1)
        self.assertAlmostEqual(s.coverage, 20 / 25, delta=0.03)
        self.assertAlmostEqual(s.metric("closed"), 0.0)  # missing time is not "closed"

    def test_short_dropout_is_not_drawn_as_a_gap(self):
        r = SessionRecorder(0.0, START)
        feed(r, 0.0, 5)
        r.add_frame(5.1, None, False)
        end = feed(r, 5.5, 5)
        self.assertEqual(r.finish(end).untracked, [])

    def test_in_progress_summary(self):
        r = SessionRecorder(0.0, START)
        end = feed(r, 0.0, 20)
        s = r.summary(end)
        self.assertTrue(s.in_progress)
        self.assertAlmostEqual(s.study_seconds, 20, delta=0.1)

    def test_no_blinks_means_no_closure_value(self):
        r = SessionRecorder(0.0, START)
        end = feed(r, 0.0, 30)
        self.assertIsNone(r.finish(end).metric("closure"))

    def test_per_minute_values_need_enough_tracking(self):
        r = SessionRecorder(0.0, START)
        end = feed(r, 0.0, 70, blink_every=4)
        minutes = r.finish(end).minutes
        self.assertIsNotNone(minutes[0].value("rate"))
        self.assertIsNone(minutes[1].value("rate"))  # only ~10 s in the second minute


def session(day, hour, minutes, blinks, tracked_share=1.0):
    r = SessionRecorder(0.0, datetime.combine(day, datetime.min.time()).replace(hour=hour))
    end = feed(r, 0.0, minutes * 60 * tracked_share, blink_every=60 / max(1, blinks / minutes))
    if tracked_share < 1:
        for i in range(int(minutes * 60 * (1 - tracked_share) * FPS)):
            r.add_frame(end + i / FPS, None, False)
        end = end + minutes * 60 * (1 - tracked_share)
    return r.finish(end)


class StatsTest(unittest.TestCase):
    def test_period_days(self):
        saturday = date(2026, 10, 10)
        self.assertEqual(period_days("today", saturday), [saturday])
        self.assertEqual(period_days("week", saturday)[0], date(2026, 10, 5))  # Monday
        self.assertEqual(len(period_days("month", saturday)), 10)

    def test_period_filter_and_totals(self):
        today = date(2026, 10, 10)
        store = SessionStore([session(today, 9, 10, 150), session(date(2026, 10, 6), 14, 5, 60),
                              session(date(2026, 9, 30), 10, 5, 60)])
        self.assertEqual(len(period_stats(store.all(), "today", today).sessions), 1)
        self.assertEqual(len(period_stats(store.all(), "week", today).sessions), 2)
        self.assertEqual(len(period_stats(store.all(), "month", today).sessions), 2)  # 30 Sep excluded
        self.assertAlmostEqual(period_stats(store.all(), "week", today).study_seconds, 900, delta=1)

    def test_combined_rate_is_weighted_by_tracked_time(self):
        today = date(2026, 10, 10)
        a, b = session(today, 9, 10, 100), session(today, 11, 2, 40)
        self.assertAlmostEqual(combined_metric([a, b], "rate"), (a.blinks + b.blinks) / 12, delta=0.3)

    def test_coverage(self):
        s = session(date(2026, 10, 10), 9, 10, 100, tracked_share=0.8)
        self.assertAlmostEqual(s.coverage, 0.8, delta=0.02)

    def test_hour_range_covers_sessions(self):
        today = date(2026, 10, 10)
        self.assertEqual(hour_range([]), (8, 20))
        self.assertEqual(hour_range([session(today, 9, 30, 300)]), (9, 15))
        self.assertEqual(hour_range([session(today, 22, 30, 300)]), (18, 24))
        # Afternoon session yesterday + morning session today: the axis must reach the afternoon.
        both = [session(date(2026, 10, 9), 16, 50, 500), session(today, 9, 30, 300)]
        self.assertEqual(hour_range(both), (9, 17))

    def test_formatting(self):
        self.assertEqual(format_metric("rate", 14.72), "14.7 blinks/min")
        self.assertEqual(format_metric("closed", 3.04), "3.0%")
        self.assertEqual(format_metric("closure", None), "—")
        self.assertEqual(format_metric("closure", 0.184), "184 ms")  # seconds in, milliseconds shown
        self.assertEqual(format_duration(155 * 60), "2 h 35 min")
        self.assertEqual(format_duration(45), "45 s")


if __name__ == "__main__":
    unittest.main()
