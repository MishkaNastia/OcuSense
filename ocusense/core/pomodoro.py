"""The Pomodoro timer: focus, short break, long break. Pure Python, no interface.

Times are time.monotonic() seconds passed in by the caller, so the timer is easy
to test and never drifts with the clock on the wall.

    focus → short break → focus → short break → … → (every Nth focus) long break → focus …

A phase ends when its time is up (or is skipped). Whether the next one starts by
itself is a setting (auto_start_breaks / auto_start_focus); otherwise it waits,
ready, for Start.
"""

from dataclasses import dataclass

FOCUS, SHORT_BREAK, LONG_BREAK = "focus", "short_break", "long_break"
IDLE, RUNNING, PAUSED = "idle", "running", "paused"  # idle = ready to start the current phase
PHASE_NAMES = {FOCUS: "Focus", SHORT_BREAK: "Short break", LONG_BREAK: "Long break"}

LIMITS = {  # minutes (and rounds): the ranges offered in the interface
    "focus_minutes": (1, 120),
    "short_break_minutes": (1, 30),
    "long_break_minutes": (1, 60),
    "rounds_before_long_break": (2, 8),
}


@dataclass
class PomodoroSettings:
    focus_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    rounds_before_long_break: int = 4
    auto_start_breaks: bool = True
    auto_start_focus: bool = False

    def minutes(self, phase: str) -> int:
        return {FOCUS: self.focus_minutes, SHORT_BREAK: self.short_break_minutes,
                LONG_BREAK: self.long_break_minutes}[phase]

    def clamped(self) -> "PomodoroSettings":
        """The same settings with every number inside its allowed range."""
        values = {}
        for name, (low, high) in LIMITS.items():
            values[name] = min(high, max(low, int(getattr(self, name))))
        return PomodoroSettings(**values, auto_start_breaks=bool(self.auto_start_breaks),
                                auto_start_focus=bool(self.auto_start_focus))


PRESETS = {  # name → (focus, short break, long break, rounds before a long break)
    "classic": ("Classic 25 / 5", PomodoroSettings(25, 5, 15, 4)),
    "deep": ("Deep work 50 / 10", PomodoroSettings(50, 10, 30, 3)),
    "short": ("Short sprints 15 / 3", PomodoroSettings(15, 3, 10, 4)),
}


@dataclass(frozen=True)
class PhaseEnded:
    """Reported by tick()/skip(): a phase finished (completed=False when it was skipped)."""
    phase: str
    next_phase: str
    completed: bool
    started_automatically: bool


class PomodoroTimer:
    def __init__(self, settings: PomodoroSettings | None = None):
        self.settings = (settings or PomodoroSettings()).clamped()
        self.phase = FOCUS
        self.state = IDLE
        self.completed_focus = 0  # focus rounds finished (not skipped) since the timer was created
        self.focus_seconds = 0.0  # focus time actually spent
        self._round = 0  # focus rounds since the last long break
        self._elapsed = 0.0  # time spent in the current phase before the current run
        self._run_start: float | None = None

    # ------------------------------------------------------------ queries
    def duration(self, phase: str | None = None) -> float:
        return self.settings.minutes(phase or self.phase) * 60.0

    def elapsed(self, now: float) -> float:
        running = now - self._run_start if self._run_start is not None else 0.0
        return min(self.duration(), self._elapsed + running)

    def remaining(self, now: float) -> float:
        return max(0.0, self.duration() - self.elapsed(now))

    def progress(self, now: float) -> float:
        """0 at the start of the phase, 1 when it is over."""
        return self.elapsed(now) / self.duration()

    def focus_time(self, now: float) -> float:
        """All focus time spent so far, including the running focus round."""
        running = 0.0
        if self.phase == FOCUS and self._run_start is not None:
            running = max(0.0, min(now - self._run_start, self.duration() - self._elapsed))
        return self.focus_seconds + running

    @property
    def round_in_cycle(self) -> int:
        """Which focus round of the cycle this is (1-based) — the current one during focus, the last one in a break."""
        return self._round + (1 if self.phase == FOCUS else 0)

    # ------------------------------------------------------------ actions
    def start(self, now: float) -> None:
        if self.state == IDLE:
            self.state, self._run_start = RUNNING, now

    def pause(self, now: float) -> None:
        if self.state == RUNNING:
            self._bank(now)
            self.state = PAUSED

    def resume(self, now: float) -> None:
        if self.state == PAUSED:
            self.state, self._run_start = RUNNING, now

    def reset(self) -> None:
        """Back to the start of a fresh focus round; finished rounds and focus time are kept."""
        self.phase, self.state = FOCUS, IDLE
        self._round = 0
        self._elapsed, self._run_start = 0.0, None

    def skip(self, now: float) -> PhaseEnded:
        return self._finish(now, completed=False)

    def tick(self, now: float) -> PhaseEnded | None:
        """Call regularly; returns PhaseEnded when the running phase's time is up."""
        if self.state == RUNNING and self.elapsed(now) >= self.duration():
            ended_at = self._run_start + (self.duration() - self._elapsed)  # exactly when time ran out
            return self._finish(ended_at, completed=True)
        return None

    def apply_settings(self, settings: PomodoroSettings, now: float) -> None:
        """New lengths apply at once; time already spent in this phase still counts."""
        self.settings = settings.clamped()
        if self.state == RUNNING:
            self._bank(now)
            self._run_start = now
        self._elapsed = min(self._elapsed, self.duration())

    # ------------------------------------------------------------ internals
    def _bank(self, now: float) -> None:
        if self._run_start is not None:
            spent = min(self.duration() - self._elapsed, now - self._run_start)
            if self.phase == FOCUS:
                self.focus_seconds += max(0.0, spent)
            self._elapsed += max(0.0, spent)
            self._run_start = None

    def _finish(self, now: float, completed: bool) -> PhaseEnded:
        self._bank(now)
        ended = self.phase
        if ended == FOCUS:
            if completed:
                self.completed_focus += 1
            self._round += 1
            next_phase = LONG_BREAK if self._round >= self.settings.rounds_before_long_break else SHORT_BREAK
        else:
            if ended == LONG_BREAK:
                self._round = 0
            next_phase = FOCUS
        auto = self.settings.auto_start_breaks if next_phase != FOCUS else self.settings.auto_start_focus
        self.phase, self._elapsed = next_phase, 0.0
        if auto:
            self.state, self._run_start = RUNNING, now
        else:
            self.state, self._run_start = IDLE, None
        return PhaseEnded(ended, next_phase, completed, auto)
