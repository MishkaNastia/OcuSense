"""Measurement-imperfection models for blink data.

Missed blinks (event level)
---------------------------
A missed detection deletes a blink *event*. The two intervals around it merge
into one longer interval, so missed blinks are simulated on timestamps and the
intervals are rebuilt from the surviving events (:func:`delete_events`). Deleting
interval observations independently would be wrong: it leaves the interval
distribution unchanged.

For a renewal process with independent misses at probability ``q``, an
observed interval is the sum of a Geometric(1 - q) number of true intervals.
This preserves the Exponential family (scale -> scale / (1 - q)) but not the
Gamma, Weibull or log-normal families.

For blink counts per window, each blink is missed independently, which is
binomial thinning of the count (:func:`thin_counts`).

False positives (count data)
----------------------------
Spurious detections (e.g. head movement or lighting changes mistaken for a
blink) are added as an independent Poisson(``fp_rate``) count per window
(:func:`add_false_positives`). The full count observation model is

    observed = Binomial(true_count, 1 - miss_prob) + Poisson(fp_rate)

The observed mean is (1 - q) E[X] + fp_rate for every family
(:func:`noisy_count_mean`). Poisson stays Poisson, with rate
(1 - q) lam + fp_rate. The other families do not survive false positives:
NB + Poisson is not NB, and structural zeros of ZIP/ZINB get filled by
spurious events. Thinning preserves all
four count families: Poisson(lam) -> Poisson((1-q) lam),
NB(mu, r) -> NB((1-q) mu, r), and the zero-inflated versions keep ``pi``.
See :func:`thinned_count_params`.

Timestamp noise
---------------
:func:`jitter_timestamps` adds i.i.d. Gaussian noise to each timestamp, then:

1. **Re-sorts** the timestamps. A detector reports events in time order, so a
   pair whose noise swaps their order is observed as the swapped order.
2. **Merges detections closer than** ``min_separation`` seconds (default
   0.05 s) by dropping the later one. A real blink lasts about 100-400 ms and a
   30 fps camera samples every 33 ms, so two detections within 50 ms cannot be
   two distinct blinks. This guarantees strictly positive intervals.

The distortions this introduces are reported, not hidden. The interval
variance grows by about ``2 sigma**2``. Consecutive intervals become
negatively correlated (each timestamp error enters two neighbouring intervals
with opposite signs). The merge rule removes very short intervals and
lengthens their neighbours, slightly left-truncating the distribution. The
merge rule also applies when ``sigma = 0``, which is why experiments use the
``sigma = 0`` condition, not raw draws, as the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .distributions import get_distribution
from .synthetic import Scenario, generate_synthetic_data

DEFAULT_MIN_SEPARATION = 0.05


def _check_probability(q: float) -> None:
    if not 0 <= q < 1:
        raise ValueError(f"miss probability must be in [0, 1), got {q}")


def intervals_from_timestamps(timestamps: np.ndarray) -> np.ndarray:
    """Interblink intervals between consecutive (sorted) timestamps."""
    ts = np.asarray(timestamps, dtype=float)
    if ts.ndim != 1:
        raise ValueError("timestamps must be one-dimensional")
    if np.any(np.diff(ts) < 0):
        raise ValueError("timestamps must be sorted")
    return np.diff(ts)


def counts_from_timestamps(timestamps: np.ndarray, window: float, duration: float) -> np.ndarray:
    """Number of events in consecutive ``[i*window, (i+1)*window)`` bins.

    Only complete windows within ``[0, duration)`` are returned.
    """
    if window <= 0 or duration < window:
        raise ValueError("need window > 0 and duration >= window")
    n_windows = int(duration // window)
    edges = np.arange(n_windows + 1) * window
    counts, _ = np.histogram(np.asarray(timestamps, dtype=float), bins=edges)
    return counts.astype(np.int64)


def delete_events(timestamps: np.ndarray, miss_prob: float, seed: int) -> np.ndarray:
    """Independently drop each event with probability ``miss_prob``.

    Returns a new sorted array; the input is not modified.
    """
    _check_probability(miss_prob)
    ts = np.asarray(timestamps, dtype=float)
    keep = np.random.default_rng(seed).random(ts.size) >= miss_prob
    return ts[keep].copy()


def thin_counts(counts: np.ndarray, miss_prob: float, seed: int) -> np.ndarray:
    """Binomial thinning: each of the ``x`` blinks in a window survives w.p. ``1-q``."""
    _check_probability(miss_prob)
    x = np.asarray(counts)
    if np.any(x < 0) or np.any(x != np.round(x)):
        raise ValueError("counts must be nonnegative integers")
    return np.random.default_rng(seed).binomial(x.astype(np.int64), 1.0 - miss_prob)


def add_false_positives(counts: np.ndarray, fp_rate: float, seed: int) -> np.ndarray:
    """Add an independent Poisson(``fp_rate``) number of spurious events per window."""
    if fp_rate < 0:
        raise ValueError(f"fp_rate must be >= 0, got {fp_rate}")
    x = np.asarray(counts)
    if np.any(x < 0) or np.any(x != np.round(x)):
        raise ValueError("counts must be nonnegative integers")
    return x.astype(np.int64) + np.random.default_rng(seed).poisson(fp_rate, x.size)


def noisy_count_mean(distribution: str, params: Mapping[str, float], miss_prob: float,
                     fp_rate: float) -> float:
    """Exact mean of the observed counts under misses and false positives."""
    _check_probability(miss_prob)
    spec = get_distribution(distribution)
    return (1.0 - miss_prob) * spec.mean(spec.validate_params(params)) + fp_rate


def noisy_count_params(distribution: str, params: Mapping[str, float], miss_prob: float,
                       fp_rate: float) -> dict[str, float] | None:
    """Parameters of the observed counts when the family is preserved, else ``None``.

    Preserved cases: any family with ``fp_rate == 0`` (pure thinning), and
    Poisson with false positives (Poisson + Poisson is Poisson).
    """
    if fp_rate == 0:
        return thinned_count_params(distribution, params, miss_prob)
    if distribution == "poisson":
        return {"lam": (1.0 - miss_prob) * float(params["lam"]) + fp_rate}
    return None


def thinned_count_params(distribution: str, params: Mapping[str, float],
                         miss_prob: float) -> dict[str, float]:
    """Exact parameters of a count law after binomial thinning (same family)."""
    _check_probability(miss_prob)
    spec = get_distribution(distribution)
    if spec.track != "count":
        raise ValueError("thinning formula applies to count distributions only")
    out = spec.validate_params(params)
    rate_key = "lam" if "lam" in out else "mu"
    out[rate_key] *= 1.0 - miss_prob
    return out


def jitter_timestamps(
    timestamps: np.ndarray,
    sigma: float,
    seed: int,
    min_separation: float = DEFAULT_MIN_SEPARATION,
) -> tuple[np.ndarray, int]:
    """Add N(0, sigma^2) timing noise, re-sort, merge near-coincident detections.

    Returns ``(noisy_timestamps, n_merged)`` where ``n_merged`` is the number
    of detections removed by the ``min_separation`` rule.
    """
    if sigma < 0:
        raise ValueError("sigma must be >= 0")
    if min_separation < 0:
        raise ValueError("min_separation must be >= 0")
    ts = np.asarray(timestamps, dtype=float)
    noisy = np.sort(ts + np.random.default_rng(seed).normal(0.0, sigma, ts.size))
    if noisy.size == 0:
        return noisy, 0
    kept = [noisy[0]]
    for t in noisy[1:]:
        if t - kept[-1] >= min_separation and t > kept[-1]:
            kept.append(t)
    kept_arr = np.asarray(kept)
    return kept_arr, int(noisy.size - kept_arr.size)


def _event_level_intervals(distribution: str, params: Mapping[str, float], n_intervals: int,
                           seed: int, transform) -> tuple[np.ndarray, dict]:
    """Generate enough renewal events, apply ``transform`` to the timestamps,
    and return the first ``n_intervals`` observed intervals."""
    seeds = np.random.SeedSequence(seed).generate_state(8)
    n_raw = int(n_intervals * 1.5) + 50
    for attempt in range(4):
        intervals = generate_synthetic_data(distribution, params, n_raw, int(seeds[2 * attempt]))
        ts = np.concatenate([[0.0], np.cumsum(intervals)])
        observed_ts, info = transform(ts, int(seeds[2 * attempt + 1]))
        observed = intervals_from_timestamps(observed_ts)
        if observed.size >= n_intervals:
            return observed[:n_intervals].copy(), info
        n_raw *= 3
    raise RuntimeError("could not generate enough observed intervals")


def intervals_with_missed_blinks(distribution: str, params: Mapping[str, float],
                                 n_intervals: int, miss_prob: float, seed: int) -> np.ndarray:
    """Observed intervals after independent missed detections (event level)."""
    _check_probability(miss_prob)

    def transform(ts: np.ndarray, s: int) -> tuple[np.ndarray, dict]:
        return delete_events(ts, miss_prob, s), {}

    return _event_level_intervals(distribution, params, n_intervals, seed, transform)[0]


def intervals_with_timestamp_noise(
    distribution: str,
    params: Mapping[str, float],
    n_intervals: int,
    sigma: float,
    seed: int,
    min_separation: float = DEFAULT_MIN_SEPARATION,
) -> tuple[np.ndarray, float]:
    """Observed intervals after Gaussian timestamp noise.

    Returns ``(intervals, merged_fraction)``, where ``merged_fraction`` is the
    share of detections removed by the minimum-separation rule.
    """

    def transform(ts: np.ndarray, s: int) -> tuple[np.ndarray, dict]:
        noisy, merged = jitter_timestamps(ts, sigma, s, min_separation)
        return noisy, {"merged_fraction": merged / ts.size}

    intervals, info = _event_level_intervals(distribution, params, n_intervals, seed, transform)
    return intervals, info["merged_fraction"]


def counts_with_missed_blinks(distribution: str, params: Mapping[str, float],
                              n_windows: int, miss_prob: float, seed: int) -> np.ndarray:
    """Per-window counts after independent missed detections (binomial thinning)."""
    return counts_with_detection_noise(distribution, params, n_windows, miss_prob, 0.0, seed)


def counts_with_detection_noise(distribution: str, params: Mapping[str, float], n_windows: int,
                                miss_prob: float, fp_rate: float, seed: int) -> np.ndarray:
    """Per-window counts after missed detections and Poisson false positives."""
    gen_seed, thin_seed, fp_seed = np.random.SeedSequence(seed).generate_state(3)
    counts = generate_synthetic_data(distribution, params, n_windows, int(gen_seed))
    observed = thin_counts(counts, miss_prob, int(thin_seed))
    return add_false_positives(observed, fp_rate, int(fp_seed)) if fp_rate > 0 else observed


@dataclass(frozen=True)
class MissedBlinks:
    """Data generator for Monte Carlo runs: missed detections at ``miss_prob``.

    Counts use binomial thinning; intervals use event deletion on a renewal
    process. Picklable, so it can be sent to worker processes.
    """

    miss_prob: float

    def __call__(self, scenario: Scenario, n: int, seed: int) -> np.ndarray:
        if scenario.track == "count":
            return counts_with_missed_blinks(scenario.distribution, scenario.params, n,
                                             self.miss_prob, seed)
        return intervals_with_missed_blinks(scenario.distribution, scenario.params, n,
                                            self.miss_prob, seed)


@dataclass(frozen=True)
class TimestampNoise:
    """Data generator: Gaussian timestamp noise (interval track only)."""

    sigma: float
    min_separation: float = DEFAULT_MIN_SEPARATION

    def __call__(self, scenario: Scenario, n: int, seed: int) -> np.ndarray:
        if scenario.track != "interval":
            raise ValueError("timestamp noise is defined for the interval track")
        return intervals_with_timestamp_noise(scenario.distribution, scenario.params, n,
                                              self.sigma, seed, self.min_separation)[0]


@dataclass(frozen=True)
class CountDetectionNoise:
    """Data generator: missed detections plus Poisson false positives (count track)."""

    miss_prob: float
    fp_rate: float

    def __call__(self, scenario: Scenario, n: int, seed: int) -> np.ndarray:
        if scenario.track != "count":
            raise ValueError("count detection noise is defined for the count track")
        return counts_with_detection_noise(scenario.distribution, scenario.params, n,
                                           self.miss_prob, self.fp_rate, seed)
