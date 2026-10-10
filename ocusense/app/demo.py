"""Clearly labelled demo sessions, only used with:  python -m ocusense --demo-history

They let you check the Statistics page (or show it to a jury) before you have
real history. The page shows a "Demo data" label whenever these are loaded.
"""

import math
import random
from datetime import date, datetime, timedelta

from ocusense.core.session import MinuteBin, SessionSummary

# (days ago, start "HH:MM", study minutes, blink rate, median closure ms, % closed, tracked share)
PLAN = [
    (9, "14:00", 45, 15.2, 182, 2.9, 0.96), (9, "19:00", 35, 13.8, 205, 3.6, 0.91),
    (8, "10:00", 60, 16.0, 175, 2.7, 0.97), (8, "15:00", 40, 14.1, 198, 3.4, 0.93),
    (6, "16:00", 60, 12.9, 214, 3.9, 0.88),
    (5, "09:30", 50, 15.5, 180, 2.8, 0.95), (5, "14:00", 45, 13.2, 207, 3.7, 0.90),
    (4, "10:00", 70, 16.4, 172, 2.6, 0.98), (4, "16:00", 50, 14.0, 201, 3.3, 0.94),
    (2, "09:00", 55, 15.8, 178, 2.8, 0.96), (2, "13:00", 45, 14.6, 190, 3.1, 0.95), (2, "17:00", 40, 12.7, 219, 4.0, 0.89),
    (1, "10:30", 60, 15.9, 176, 2.7, 0.97), (1, "15:30", 50, 13.9, 199, 3.5, 0.92),
    (0, "09:10", 90, 15.1, 184, 3.0, 0.94), (0, "11:30", 45, 14.4, 193, 3.2, 0.96),
]


def demo_session(day, start, minutes, rate, closure_ms, closed_pct, tracked_share, rng):
    started = datetime.combine(day, datetime.strptime(start, "%H:%M").time())
    gap_minute = int(minutes * 0.55)  # one stretch of lost tracking in the middle
    gap_seconds = round(minutes * 60 * (1 - tracked_share))
    bins, closures = [], []
    remaining_gap = gap_seconds
    for i in range(minutes):
        missing = min(60.0, remaining_gap) if i >= gap_minute else 0.0
        remaining_gap -= missing
        tracked = 60.0 - missing
        wobble = 1 + 0.05 * math.sin(i / 4 + rng.uniform(0, 6)) + 0.02 * rng.uniform(-1, 1)
        blinks = round(rate * wobble * tracked / 60)
        minute_closures = [max(0.06, rng.gauss(closure_ms, 25) / 1000) for _ in range(blinks)]
        closures += minute_closures
        bins.append(MinuteBin(started + timedelta(minutes=i), tracked, blinks, minute_closures,
                              tracked * closed_pct / 100 * wobble))
    gap_start = started + timedelta(minutes=gap_minute)
    return SessionSummary(
        started_at=started,
        ended_at=started + timedelta(minutes=minutes),
        study_seconds=minutes * 60.0,
        tracked_seconds=sum(b.tracked for b in bins),
        blinks=sum(b.blinks for b in bins),
        closure_seconds=closures,
        closed_seconds=sum(b.closed for b in bins),
        segments=[(started, started + timedelta(minutes=minutes))],
        untracked=[(gap_start, gap_start + timedelta(seconds=gap_seconds))] if gap_seconds >= 2 else [],
        minutes=bins,
    )


def demo_sessions(today=None):
    today = today or date.today()
    rng = random.Random(7)
    return [demo_session(today - timedelta(days=ago), *rest, rng) for ago, *rest in PLAN]
