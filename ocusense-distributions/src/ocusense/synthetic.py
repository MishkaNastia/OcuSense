"""Synthetic data generation for the two OcuSense measurement tracks.

* Track A (``"count"``): blinks per fixed 60-second window.
* Track B (``"interval"``): interblink intervals in seconds, optionally turned
  into blink timestamps through a renewal process (cumulative sums of
  intervals) so that missed detections and timing noise can be simulated at
  the event level (see :mod:`ocusense.noise`).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .distributions import COUNT, INTERVAL, Track, get_distribution

WINDOW_SECONDS = 60.0


def generate_synthetic_data(
    distribution: str,
    parameters: Mapping[str, float],
    n_samples: int,
    seed: int,
) -> np.ndarray:
    """Draw ``n_samples`` i.i.d. observations from a registered distribution.

    Count distributions return an ``int64`` array; interval distributions
    return a strictly positive ``float64`` array (seconds).

    Args:
        distribution: Registry name, e.g. ``"negbin"`` or ``"gamma"``.
        parameters: Parameters in the registry's parameterization.
        n_samples: Number of observations (>= 1).
        seed: Seed for :func:`numpy.random.default_rng`.
    """
    if int(n_samples) != n_samples or n_samples < 1:
        raise ValueError(f"n_samples must be a positive integer, got {n_samples}")
    spec = get_distribution(distribution)
    params = spec.validate_params(parameters)
    rng = np.random.default_rng(seed)
    draws = spec.sample(rng, params, int(n_samples))
    if spec.track == COUNT:
        return np.asarray(draws, dtype=np.int64)
    draws = np.asarray(draws, dtype=np.float64)
    # Positive-support densities can underflow to exactly 0.0 in floating
    # point for extreme parameters; surface that rather than hiding it.
    if np.any(draws <= 0):
        raise FloatingPointError(f"{distribution}{params} produced non-positive draws")
    return draws


def generate_blink_timestamps(
    interval_distribution: str,
    parameters: Mapping[str, float],
    n_intervals: int,
    seed: int,
) -> np.ndarray:
    """Blink timestamps (seconds) from a renewal process.

    The first blink is at ``t = 0`` and each subsequent blink follows after an
    i.i.d. interval, so ``np.diff`` of the result recovers the intervals
    exactly. Returns ``n_intervals + 1`` timestamps.
    """
    if get_distribution(interval_distribution).track != INTERVAL:
        raise ValueError("Timestamps require an interval-track distribution")
    intervals = generate_synthetic_data(interval_distribution, parameters, n_intervals, seed)
    return np.concatenate([[0.0], np.cumsum(intervals)])


def derive_seed(base_seed: int, *keys: object) -> int:
    """Deterministic 32-bit seed from a base seed and arbitrary labels.

    Labels are hashed with CRC32 (stable across processes and Python runs,
    unlike ``hash``), so a replicate's data do not depend on scenario order
    or on how work is split across worker processes.
    """
    words = [int(base_seed) & 0xFFFFFFFF]
    for key in keys:
        words.append(zlib.crc32(repr(key).encode()) & 0xFFFFFFFF)
    return int(np.random.SeedSequence(words).generate_state(1)[0])


@dataclass(frozen=True)
class Scenario:
    """A named data-generating configuration.

    Attributes:
        name: Unique label, used in tables and seeds.
        distribution: Generating family (registry name).
        params: Generating parameters.
        regime: ``"primary"`` for the main benchmark, ``"overlap"`` for
            deliberately hard-to-distinguish settings.
        equivalent_families: Other families that contain this exact
            distribution at an attainable parameter value (e.g. Gamma with
            shape 1 *is* an Exponential). Selecting one of these is not an
            error in the generating law, only in its nominal label.
        note: Free-text explanation, mostly for overlap regimes.
    """

    name: str
    distribution: str
    params: dict[str, float]
    regime: str = "primary"
    equivalent_families: tuple[str, ...] = field(default=())
    note: str = ""

    @property
    def track(self) -> Track:
        return get_distribution(self.distribution).track

    def generate(self, n_samples: int, seed: int) -> np.ndarray:
        return generate_synthetic_data(self.distribution, self.params, n_samples, seed)


def _s(name: str, dist: str, **params: float) -> Scenario:
    return Scenario(name, dist, dict(params))


PRIMARY_SCENARIOS: tuple[Scenario, ...] = (
    # Track A: blink counts per 60 s window (typical resting rate 10-20/min).
    _s("poisson_l15", "poisson", lam=15),
    _s("poisson_l8", "poisson", lam=8),
    _s("poisson_l25", "poisson", lam=25),
    _s("negbin_m15_r10", "negbin", mu=15, r=10),
    _s("negbin_m15_r3", "negbin", mu=15, r=3),
    _s("negbin_m20_r30", "negbin", mu=20, r=30),
    _s("zip_l15_p0.2", "zip", lam=15, pi=0.2),
    _s("zip_l10_p0.1", "zip", lam=10, pi=0.1),
    _s("zip_l20_p0.35", "zip", lam=20, pi=0.35),
    _s("zinb_m15_r10_p0.2", "zinb", mu=15, r=10, pi=0.2),
    _s("zinb_m12_r4_p0.1", "zinb", mu=12, r=4, pi=0.1),
    _s("zinb_m20_r20_p0.3", "zinb", mu=20, r=20, pi=0.3),
    # Track B: interblink intervals in seconds.
    _s("lognormal_m1.0_s0.4", "lognormal", mu_log=1.0, sigma=0.4),
    _s("lognormal_m0.8_s0.7", "lognormal", mu_log=0.8, sigma=0.7),
    _s("lognormal_m1.3_s0.25", "lognormal", mu_log=1.3, sigma=0.25),
    _s("gamma_a3_s1", "gamma", shape=3, scale=1),
    _s("gamma_a1.5_s2", "gamma", shape=1.5, scale=2),
    _s("gamma_a6_s0.5", "gamma", shape=6, scale=0.5),
    _s("weibull_c1.5_s3", "weibull", shape=1.5, scale=3),
    _s("weibull_c2.5_s4", "weibull", shape=2.5, scale=4),
    _s("weibull_c0.8_s3", "weibull", shape=0.8, scale=3),
    _s("exponential_s3", "exponential", scale=3),
    _s("exponential_s1.5", "exponential", scale=1.5),
    _s("exponential_s5", "exponential", scale=5),
)

_EXP_EQUIV = ("gamma", "weibull", "exponential")

OVERLAP_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("gamma_a1_s3", "gamma", {"shape": 1, "scale": 3}, "overlap", _EXP_EQUIV,
             "Gamma(shape=1) is exactly Exponential(scale=3)"),
    Scenario("weibull_c1_s3", "weibull", {"shape": 1, "scale": 3}, "overlap", _EXP_EQUIV,
             "Weibull(shape=1) is exactly Exponential(scale=3)"),
    Scenario("gamma_a1.2_s2.5", "gamma", {"shape": 1.2, "scale": 2.5}, "overlap", (),
             "Gamma close to Exponential"),
    Scenario("weibull_c1.1_s3", "weibull", {"shape": 1.1, "scale": 3}, "overlap", (),
             "Weibull close to Exponential"),
    Scenario("lognormal_m1.0_s0.2", "lognormal", {"mu_log": 1.0, "sigma": 0.2}, "overlap", (),
             "Low-variance log-normal resembles a high-shape Gamma"),
    Scenario("negbin_m15_r200", "negbin", {"mu": 15, "r": 200}, "overlap", (),
             "Var/mean = 1.075: barely overdispersed, close to Poisson"),
    Scenario("negbin_m15_r1000", "negbin", {"mu": 15, "r": 1000}, "overlap", (),
             "Var/mean = 1.015: practically Poisson"),
    Scenario("zip_l15_p0.01", "zip", {"lam": 15, "pi": 0.01}, "overlap", (),
             "1% structural zeros: at small n often no zero is observed"),
    Scenario("zip_l4_p0.05", "zip", {"lam": 4, "pi": 0.05}, "overlap", (),
             "Low rate: Poisson already puts 1.8% mass at zero"),
    Scenario("zinb_m15_r500_p0.2", "zinb", {"mu": 15, "r": 500, "pi": 0.2}, "overlap", (),
             "ZINB with huge r is practically ZIP"),
)

ALL_SCENARIOS: tuple[Scenario, ...] = PRIMARY_SCENARIOS + OVERLAP_SCENARIOS


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name."""
    for scenario in ALL_SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(f"Unknown scenario {name!r}; choose from {[s.name for s in ALL_SCENARIOS]}")


def default_scenarios(track: Track | None = None) -> tuple[Scenario, ...]:
    """The first primary scenario of each family (the prompt's example values)."""
    seen: set[str] = set()
    chosen = []
    for scenario in PRIMARY_SCENARIOS:
        if scenario.distribution not in seen and (track is None or scenario.track == track):
            seen.add(scenario.distribution)
            chosen.append(scenario)
    return tuple(chosen)
