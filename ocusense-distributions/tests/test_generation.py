"""Synthetic data: support, shape, reproducibility, moments."""

import numpy as np
import pytest

from ocusense.distributions import COUNT_FAMILIES, INTERVAL_FAMILIES, REGISTRY, get_distribution
from ocusense.synthetic import (
    ALL_SCENARIOS,
    default_scenarios,
    derive_seed,
    generate_blink_timestamps,
    generate_synthetic_data,
    get_scenario,
)

EXAMPLE = {s.distribution: s.params for s in default_scenarios()}


@pytest.mark.parametrize("family", COUNT_FAMILIES)
def test_count_support_and_shape(family):
    x = generate_synthetic_data(family, EXAMPLE[family], 500, seed=1)
    assert x.shape == (500,)
    assert x.dtype == np.int64
    assert np.all(x >= 0)


@pytest.mark.parametrize("family", INTERVAL_FAMILIES)
def test_interval_support_and_shape(family):
    x = generate_synthetic_data(family, EXAMPLE[family], 500, seed=1)
    assert x.shape == (500,)
    assert x.dtype == np.float64
    assert np.all(x > 0) and np.all(np.isfinite(x))


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.name)
def test_every_scenario_generates_valid_data(scenario):
    x = scenario.generate(50, seed=3)
    spec = get_distribution(scenario.distribution)
    assert np.all(np.isfinite(spec.logprob(x.astype(float), scenario.params)))


@pytest.mark.parametrize("family", list(REGISTRY))
def test_reproducible_for_fixed_seed(family):
    a = generate_synthetic_data(family, EXAMPLE[family], 200, seed=42)
    b = generate_synthetic_data(family, EXAMPLE[family], 200, seed=42)
    c = generate_synthetic_data(family, EXAMPLE[family], 200, seed=43)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


@pytest.mark.parametrize("family", list(REGISTRY))
def test_sample_mean_matches_population_mean(family):
    spec = get_distribution(family)
    x = generate_synthetic_data(family, EXAMPLE[family], 100_000, seed=7)
    assert x.mean() == pytest.approx(spec.mean(EXAMPLE[family]), rel=0.02)


def test_negative_binomial_variance_parameterization():
    mu, r = 15.0, 10.0
    x = generate_synthetic_data("negbin", {"mu": mu, "r": r}, 200_000, seed=11)
    assert x.var() == pytest.approx(mu + mu**2 / r, rel=0.03)


def test_zero_inflation_fraction():
    lam, pi = 15.0, 0.2
    x = generate_synthetic_data("zip", {"lam": lam, "pi": pi}, 200_000, seed=5)
    expected_zeros = pi + (1 - pi) * np.exp(-lam)
    assert np.mean(x == 0) == pytest.approx(expected_zeros, abs=0.005)


def test_pmfs_sum_to_one():
    support = np.arange(0, 400, dtype=float)
    for family in COUNT_FAMILIES:
        spec = get_distribution(family)
        total = np.exp(spec.logprob(support, EXAMPLE[family])).sum()
        assert total == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    "family, params",
    [
        ("poisson", {"lam": -1}),
        ("negbin", {"mu": 15}),
        ("zip", {"lam": 15, "pi": 1.0}),
        ("gamma", {"shape": 3, "scale": 0}),
        ("lognormal", {"mu_log": 1.0, "sigma": -0.4}),
        ("exponential", {"scale": 3, "loc": 1}),
    ],
)
def test_invalid_parameters_rejected(family, params):
    with pytest.raises(ValueError):
        generate_synthetic_data(family, params, 10, seed=0)


def test_invalid_sample_size_and_name():
    with pytest.raises(ValueError):
        generate_synthetic_data("poisson", {"lam": 3}, 0, seed=0)
    with pytest.raises(KeyError):
        generate_synthetic_data("normal", {}, 10, seed=0)


def test_timestamps_reconstruct_intervals():
    ts = generate_blink_timestamps("gamma", {"shape": 3, "scale": 1}, 100, seed=9)
    intervals = generate_synthetic_data("gamma", {"shape": 3, "scale": 1}, 100, seed=9)
    assert ts[0] == 0 and ts.size == 101
    np.testing.assert_allclose(np.diff(ts), intervals)


def test_derive_seed_is_stable_and_distinct():
    assert derive_seed(1, "a", 30, 0) == derive_seed(1, "a", 30, 0)
    assert derive_seed(1, "a", 30, 0) != derive_seed(1, "a", 30, 1)
    assert derive_seed(1, "a", 30, 0) != derive_seed(2, "a", 30, 0)


def test_scenario_names_unique_and_lookup():
    names = [s.name for s in ALL_SCENARIOS]
    assert len(names) == len(set(names))
    assert get_scenario("poisson_l15").params == {"lam": 15}
    assert {s.distribution for s in default_scenarios()} == set(REGISTRY)
