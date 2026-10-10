"""Baseline drift: do a person's blink intervals still look like their baseline?

Pure Python: no files, no interface. The intervals come from the app's own code
(replay() → Distributions.intervals); nothing here detects blinks.

Definitions (times in seconds since the end of calibration, i.e. the first row
of the first calibrated recording):

* Interval: onset-to-onset time between consecutive completed blinks inside one
  valid segment — the (onset_a, onset_b) pairs of Distributions.intervals.
  Intervals ≤ 0 can't be logged: they are excluded and counted.
* Baseline: the intervals with both onsets in [start, start + 600 s).
* Log-normal fit (maximum likelihood) on y = ln(interval):
  mu = mean(y), sigma² = mean((y − mu)²) — ddof = 0, the MLE, not the sample std.
  Fewer than 2 intervals, or sigma = 0, gives no fit worth testing.
* Sliding windows: 300 s long, the first starting at `start`, each next one STEP
  seconds later (default 30 s). Only full windows (ending by `end`) are used. An
  interval belongs to a window when both onsets are in [window start, window end).
  A window with fewer than MIN_INTERVALS intervals (default 15) is "not enough
  data" and isn't tested.
* Likelihood-ratio test, two samples (baseline, window):
    H0: one (mu, sigma) for both, fitted by MLE on the pooled intervals.
    H1: each has its own (mu, sigma), fitted by MLE separately.
    LR = 2 · [ℓ(baseline | own fit) + ℓ(window | own fit) − ℓ(both | pooled fit)]
  H1 has 2 more free parameters, so LR ~ chi-square with 2 degrees of freedom under
  H0, whose survival function is exactly p = exp(−LR / 2). A window is "different"
  when p < ALPHA (default 0.01).
* Confirmed: a window is "confirmed different" when it and the CONFIRM_WINDOWS − 1
  windows just before it (default 3 in a row, i.e. 6 min of data) are all different.
  A window that couldn't be tested breaks the run: the count starts again.
* Break reminder (BreakReminder): when CONFIRM_WINDOWS windows in a row are below the
  line AND blinking less often than the baseline (window mu > baseline mu, i.e. a
  longer median interval). One reminder per slow stretch; a stretch ends after
  STRETCH_CLEAR_SECONDS without such a window; reminders at least
  REMINDER_GAP_SECONDS apart. Faster blinking never triggers one.
* Windows that start inside the baseline period overlap it: they are still tested
  but marked, as a sanity check (they share data with the baseline, so they should
  rarely be flagged).
* Live (LiveDrift): the same windows, each tested once it has ended — never before
  the baseline is complete, so the first results appear 10 min into a session.

Nothing here classifies fatigue or health: it only says whether the intervals in a
window are unlikely under the baseline's distribution.
"""

import math
from dataclasses import dataclass, replace

BASELINE_SECONDS = 600.0
WINDOW_SECONDS = 300.0
STEP_SECONDS = 30.0
MIN_INTERVALS = 15
ALPHA = 0.01
CONFIRM_WINDOWS = 3
STRETCH_CLEAR_SECONDS = 300.0  # a slow stretch ends after 5 min without a slow window below the line
REMINDER_GAP_SECONDS = 1200.0  # at least 20 min between break reminders

# window / test status
TESTED = "tested"
NOT_ENOUGH_DATA = "not enough data"
NO_SPREAD = "no spread (sigma = 0)"
NO_BASELINE = "baseline unusable"


@dataclass(frozen=True)
class Fit:
    mu: float  # mean of ln(interval)
    sigma: float  # MLE standard deviation of ln(interval) (ddof = 0)
    n: int  # intervals used (> 0 s)


@dataclass(frozen=True)
class TestResult:
    lr: float | None
    p: float | None
    baseline: Fit | None
    window: Fit | None
    pooled: Fit | None
    status: str


@dataclass(frozen=True)
class WindowResult:
    start: float
    end: float
    n: int  # intervals > 0 s inside the window
    excluded: int  # intervals ≤ 0 s inside the window, not used
    fit: Fit | None
    lr: float | None
    p: float | None
    different: bool  # p < alpha (False when not tested)
    status: str
    overlaps_baseline: bool
    run: int = 0  # consecutive "different" windows ending with this one (0 if this one isn't)
    confirmed: bool = False  # run ≥ CONFIRM_WINDOWS


def _logs(intervals) -> tuple[list[float], int]:
    """ln of every positive interval, plus how many were ≤ 0 and excluded."""
    logs = [math.log(x) for x in intervals if x > 0]
    return logs, len(intervals) - len(logs)


def _fit_logs(logs: list[float]) -> Fit | None:
    n = len(logs)
    if n < 2:
        return None
    mu = sum(logs) / n
    sigma = math.sqrt(sum((y - mu) ** 2 for y in logs) / n)  # ddof = 0: the MLE
    return Fit(mu, sigma, n)


def fit_lognormal(intervals) -> tuple[float, float, int] | None:
    """(mu, sigma, n) of the MLE log-normal fit; None with fewer than 2 positive intervals."""
    fit = _fit_logs(_logs(intervals)[0])
    return (fit.mu, fit.sigma, fit.n) if fit else None


def _normal_ll(logs: list[float], mu: float, sigma: float) -> float:
    return sum(-0.5 * math.log(2 * math.pi * sigma ** 2) - (y - mu) ** 2 / (2 * sigma ** 2) for y in logs)


def log_likelihood(intervals, mu: float, sigma: float) -> float:
    """Normal log-likelihood of ln(interval), intervals ≤ 0 left out.

    The log-normal log-likelihood would subtract Σ ln(interval) as well (the 1/x
    Jacobian). That term depends only on the data, so it is identical under H0 and
    H1 and cancels in the likelihood ratio; it is left out here.
    """
    return _normal_ll(_logs(intervals)[0], mu, sigma)


def likelihood_ratio_test(baseline_intervals, window_intervals) -> TestResult:
    """Two-sample LR test: same log-normal for both (H0) or one each (H1). p from chi-square, 2 df."""
    b_logs, _ = _logs(baseline_intervals)
    w_logs, _ = _logs(window_intervals)
    b, w, pooled = _fit_logs(b_logs), _fit_logs(w_logs), _fit_logs(b_logs + w_logs)
    if b is None or b.sigma == 0:
        return TestResult(None, None, b, w, pooled, NO_BASELINE)
    if w is None:
        return TestResult(None, None, b, w, pooled, NOT_ENOUGH_DATA)
    if w.sigma == 0:
        return TestResult(None, None, b, w, pooled, NO_SPREAD)
    lr = 2 * (_normal_ll(b_logs, b.mu, b.sigma) + _normal_ll(w_logs, w.mu, w.sigma)
              - _normal_ll(b_logs + w_logs, pooled.mu, pooled.sigma))
    lr = max(lr, 0.0)  # it can't be negative; rounding can make it −1e-12
    return TestResult(lr, math.exp(-lr / 2), b, w, pooled, TESTED)


def inside(interval_pairs, start: float, end: float) -> list[float]:
    """Intervals (seconds) whose two onsets are both in [start, end)."""
    return [b - a for a, b in interval_pairs if start <= a < end and start <= b < end]


def baseline_intervals(interval_pairs, start: float, seconds: float = BASELINE_SECONDS) -> list[float]:
    return inside(interval_pairs, start, start + seconds)


def sliding_windows(interval_pairs, start: float, end: float, length: float = WINDOW_SECONDS,
                    step: float = STEP_SECONDS, min_intervals: int = MIN_INTERVALS, alpha: float = ALPHA,
                    baseline_seconds: float = BASELINE_SECONDS, baseline=None,
                    confirm_windows: int = CONFIRM_WINDOWS) -> list[WindowResult]:
    """Test every full window from `start` to `end` against the baseline.

    interval_pairs: [(onset_a, onset_b)], seconds on the same clock as start/end.
    baseline: interval lengths to compare with; by default the first
    `baseline_seconds` after `start` of interval_pairs itself.
    """
    if baseline is None:
        baseline = baseline_intervals(interval_pairs, start, baseline_seconds)
    results = []
    i = 0
    while True:
        w_start = start + i * step  # multiplied, not accumulated: no drift in floating point
        if w_start + length > end + 1e-9:
            break
        result = evaluate_window(interval_pairs, baseline, w_start, length, min_intervals, alpha,
                                 start + baseline_seconds)
        results.append(with_run(result, results[-1] if results else None, confirm_windows))
        i += 1
    return results


def with_run(result: WindowResult, previous: WindowResult | None,
             confirm_windows: int = CONFIRM_WINDOWS) -> WindowResult:
    """The result with its run of consecutive "different" windows (the previous window's run + 1, or 0)."""
    run = (previous.run if previous else 0) + 1 if result.different else 0
    return replace(result, run=run, confirmed=run >= confirm_windows)


def evaluate_window(interval_pairs, baseline, w_start: float, length: float = WINDOW_SECONDS,
                    min_intervals: int = MIN_INTERVALS, alpha: float = ALPHA,
                    baseline_end: float = BASELINE_SECONDS) -> WindowResult:
    """Test one window [w_start, w_start + length) against the baseline intervals."""
    w_end = w_start + length
    values = inside(interval_pairs, w_start, w_end)
    logs, excluded = _logs(values)
    overlaps = w_start < baseline_end
    if len(logs) < min_intervals:
        return WindowResult(w_start, w_end, len(logs), excluded, _fit_logs(logs), None, None, False,
                            NOT_ENOUGH_DATA, overlaps)
    test = likelihood_ratio_test(baseline, values)
    different = test.p is not None and test.p < alpha
    return WindowResult(w_start, w_end, len(logs), excluded, test.window, test.lr, test.p, different, test.status,
                        overlaps)


class LiveDrift:
    """The same windows as sliding_windows(), each tested as soon as it can be, while a session runs.

    With a saved `reference` (interval lengths from an earlier session), every window
    is compared with it from the start: the first result comes when the first window
    has ended, and no window overlaps the baseline.

    Without one, the session's own first `baseline_seconds` are the baseline. Nothing
    can be tested before they are complete: then every window that has already ended
    is tested at once (they all overlap the baseline), and from then on each window
    when its end has passed. `baseline_pairs` then holds the baseline's (onset_a,
    onset_b) pairs, so it can be saved as the reference.

    A window is tested SETTLE_SECONDS after its end, not at the end itself: an interval
    is only recorded when its second blink reopens, which can be just after the window
    ends. With that margin the live results equal sliding_windows() on the same
    intervals, except for a closure still open SETTLE_SECONDS after a window's end.
    """
    SETTLE_SECONDS = 5.0

    def __init__(self, start: float, length: float = WINDOW_SECONDS, step: float = STEP_SECONDS,
                 min_intervals: int = MIN_INTERVALS, alpha: float = ALPHA,
                 baseline_seconds: float = BASELINE_SECONDS, reference=None,
                 confirm_windows: int = CONFIRM_WINDOWS):
        self.start = start
        self.length = length
        self.step = step
        self.min_intervals = min_intervals
        self.alpha = alpha
        self.confirm_windows = confirm_windows
        self.fixed = reference is not None  # compared with a saved reference, not the session's own start
        self.baseline_seconds = 0.0 if self.fixed else baseline_seconds
        self.baseline: list[float] | None = list(reference) if self.fixed else None  # interval lengths
        self.baseline_pairs: list | None = None  # the session's own baseline, once complete (not when fixed)
        self.baseline_fit: Fit | None = _fit_logs(_logs(self.baseline)[0]) if self.fixed else None
        self.results: list[WindowResult] = []

    @property
    def baseline_end(self) -> float:
        return self.start + self.baseline_seconds

    def collecting(self, interval_pairs, now: float) -> tuple[float, int]:
        """While the baseline isn't complete: (seconds collected so far, intervals so far)."""
        seconds = min(max(now - self.start, 0.0), self.baseline_seconds)
        return seconds, len(baseline_intervals(interval_pairs, self.start, seconds))

    def update(self, interval_pairs, now: float) -> list[WindowResult]:
        """Test every window that has become due by `now`; returns the new results (oldest first)."""
        if self.baseline is None:
            if now < self.baseline_end + self.SETTLE_SECONDS:
                return []
            self.baseline_pairs = [(a, b) for a, b in interval_pairs
                                   if self.start <= a < self.baseline_end and self.start <= b < self.baseline_end]
            self.baseline = [b - a for a, b in self.baseline_pairs]
            self.baseline_fit = _fit_logs(_logs(self.baseline)[0])
        new = []
        while True:
            w_start = self.start + len(self.results) * self.step
            if w_start + self.length + self.SETTLE_SECONDS > now:
                break
            result = evaluate_window(interval_pairs, self.baseline, w_start, self.length, self.min_intervals,
                                     self.alpha, self.baseline_end)
            result = with_run(result, self.results[-1] if self.results else None, self.confirm_windows)
            self.results.append(result)
            new.append(result)
        return new


class BreakReminder:
    """Decides when to suggest a break: blinking less often than the baseline, confirmed, rate-limited.

    Fed every window result in order (live or offline), with the baseline's mu.
    Times are the windows' end times, i.e. when the result became known.
    """

    def __init__(self, confirm_windows: int = CONFIRM_WINDOWS, clear_seconds: float = STRETCH_CLEAR_SECONDS,
                 gap_seconds: float = REMINDER_GAP_SECONDS):
        self.confirm_windows = confirm_windows
        self.clear_seconds = clear_seconds
        self.gap_seconds = gap_seconds
        self.run = 0  # consecutive slow windows below the line
        self.in_stretch = False
        self.last_slow: float | None = None
        self.last_reminder: float | None = None
        self.reminders: list[float] = []  # times reminders were given

    @staticmethod
    def slow(result: WindowResult, baseline_mu: float) -> bool:
        """Below the line and a longer median interval than the baseline."""
        return result.different and result.fit is not None and result.fit.mu > baseline_mu

    def update(self, result: WindowResult, baseline_mu: float) -> bool:
        """True when a break reminder is due with this result."""
        t = result.end
        if self.slow(result, baseline_mu):
            self.run += 1
            self.last_slow = t
        else:
            self.run = 0
            if self.in_stretch and self.last_slow is not None and t - self.last_slow >= self.clear_seconds:
                self.in_stretch = False
        if self.run < self.confirm_windows or self.in_stretch:
            return False
        self.in_stretch = True  # one reminder per stretch, even if the cooldown suppresses this one
        if self.last_reminder is not None and t - self.last_reminder < self.gap_seconds:
            return False
        self.last_reminder = t
        self.reminders.append(t)
        return True


def break_reminders(results, baseline_mu: float, **settings) -> list[float]:
    """Offline: the times (window ends) at which break reminders would have been given."""
    reminder = BreakReminder(**settings)
    for result in results:
        reminder.update(result, baseline_mu)
    return reminder.reminders
