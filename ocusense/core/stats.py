"""Turns session summaries into what the Statistics page shows. No UI here.

Values are computed in internal units (closure in seconds). to_display()
is the one place that converts them for people to read (closure in ms).
"""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from .models import SessionSummary

# scale_max is in display units. display_factor converts internal → display units.
METRICS = {
    "rate": dict(name="Blink rate", unit="blinks per minute", short="blinks/min", decimals=1, scale_max=24, display_factor=1,
                 explain="Complete blinks counted per minute of tracked study time."),
    "closure": dict(name="Median closure duration", unit="milliseconds", short="ms", decimals=0, scale_max=300,
                    display_factor=1000,  # stored in seconds, shown in milliseconds
                    explain="The typical time your eyes stayed below the closing threshold during a blink. "
                            "The median keeps a few long blinks from dominating."),
    "closed": dict(name="Time classified as closed", unit="% of tracked time", short="%", decimals=1, scale_max=6,
                   display_factor=1,
                   explain="Share of tracked time when your personal eye openness was below the closing threshold."),
}


def to_display(name: str, value: float | None) -> float | None:
    """Convert an internal value (e.g. closure in seconds) to display units (ms)."""
    return None if value is None else value * METRICS[name]["display_factor"]


def format_metric(name: str, value: float | None, with_unit: bool = True) -> str:
    """Format an internal value for display, including the unit conversion."""
    if value is None:
        return "—"
    m = METRICS[name]
    text = f"{to_display(name, value):.{m['decimals']}f}"
    if not with_unit:
        return text + ("%" if name == "closed" else "")
    return text + ("%" if name == "closed" else " " + m["short"])


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)} s"
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h" + (f" {minutes % 60} min" if minutes % 60 else "")


def period_days(period: str, today: date) -> list[date]:
    """The calendar days shown for a period, oldest first."""
    if period == "today":
        return [today]
    first = today - timedelta(days=today.weekday()) if period == "week" else today.replace(day=1)
    return [first + timedelta(days=i) for i in range((today - first).days + 1)]


def combined_metric(sessions: list[SessionSummary], name: str) -> float | None:
    """One value for several sessions, weighted by tracked time (not a plain average). Internal units."""
    tracked = sum(s.tracked_seconds for s in sessions)
    if name == "closure":
        closures = [c for s in sessions for c in s.closure_seconds]
        return statistics.median(closures) if closures else None
    if tracked < 1:
        return None
    if name == "rate":
        return sum(s.blinks for s in sessions) / (tracked / 60)
    return sum(s.closed_seconds for s in sessions) / tracked * 100


@dataclass
class PeriodStats:
    days: list
    sessions: list
    study_seconds: float
    tracked_seconds: float

    @property
    def coverage(self):
        return self.tracked_seconds / self.study_seconds if self.study_seconds else None

    def sessions_on(self, day):
        return [s for s in self.sessions if s.started_at.date() == day]


def period_stats(sessions: list[SessionSummary], period: str, today: date | None = None) -> PeriodStats:
    today = today or date.today()
    days = period_days(period, today)
    chosen = [s for s in sessions if days[0] <= s.started_at.date() <= days[-1]]
    return PeriodStats(
        days=days,
        sessions=chosen,
        study_seconds=sum(s.study_seconds for s in chosen),
        tracked_seconds=sum(s.tracked_seconds for s in chosen),
    )


def hour_range(sessions: list[SessionSummary], minimum_span: int = 6) -> tuple[int, int]:
    """Start and end hour for the timeline axis, covering every session shown."""
    if not sessions:
        return 8, 20
    start = min(s.started_at.hour for s in sessions)

    def end_hour(s):  # time of day, not date: sessions come from different days
        if s.ended_at.date() > s.started_at.date():
            return 24
        return s.ended_at.hour + (1 if s.ended_at.minute or s.ended_at.second else 0)

    end = max(max(end_hour(s) for s in sessions), start + minimum_span)
    if end > 24:
        start, end = max(0, 24 - max(minimum_span, end - start)), 24
    return start, end


def minute_series(sessions: list[SessionSummary], metric: str) -> list:
    """[(datetime, internal value or None)] per minute across sessions, for the Today chart."""
    points = []
    for s in sorted(sessions, key=lambda s: s.started_at):
        for minute in s.minutes:
            points.append((minute.start, minute.value(metric)))
        points.append((s.ended_at, None))  # never join two sessions with a line
    return points
