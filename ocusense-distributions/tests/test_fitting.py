"""MLE fitting: recovery, parameter counts, failure handling, immutability."""

import numpy as np
import pytest
from scipy import optimize

from ocusense import fitting
from ocusense.distributions import REGISTRY, log_likelihood
from ocusense.fitting import fit_distribution
from ocusense.synthetic import default_scenarios, generate_synthetic_data

EXAMPLE = {s.distribution: s.params for s in default_scenarios()}
EXPECTED_K = {"poisson": 1, "negbin": 2, "zip": 2, "zinb": 3,
              "lognormal": 2, "gamma": 2, "weibull": 2, "exponential": 1}


@pytest.mark.parametrize("family", list(REGISTRY))
def test_recovers_parameters_on_large_samples(family):
    true = EXAMPLE[family]
    x = generate_synthetic_data(family, true, 20_000, seed=123)
    fit = fit_distribution(x, family)
    assert fit.success
    for name, value in true.items():
        assert fit.params[name] == pytest.approx(value, rel=0.12), name


@pytest.mark.parametrize("family", list(REGISTRY))
def test_parameter_count(family):
    x = generate_synthetic_data(family, EXAMPLE[family], 300, seed=2)
    fit = fit_distribution(x, family)
    assert fit.k == EXPECTED_K[family] == REGISTRY[family].k
    assert set(fit.params) == set(REGISTRY[family].param_names)


@pytest.mark.parametrize("family", list(REGISTRY))
def test_reported_loglik_matches_registry(family):
    x = generate_synthetic_data(family, EXAMPLE[family], 300, seed=4)
    fit = fit_distribution(x, family)
    assert fit.log_likelihood == pytest.approx(log_likelihood(x, family, fit.params), rel=1e-12)


@pytest.mark.parametrize("family", list(REGISTRY))
def test_mle_beats_true_parameters(family):
    """The maximized likelihood must be at least the likelihood at the truth."""
    x = generate_synthetic_data(family, EXAMPLE[family], 500, seed=8)
    fit = fit_distribution(x, family)
    assert fit.log_likelihood >= log_likelihood(x, family, EXAMPLE[family]) - 1e-6


def test_nested_models_never_fit_worse():
    x = generate_synthetic_data("negbin", {"mu": 15, "r": 10}, 1000, seed=3)
    ll = {f: fit_distribution(x, f).log_likelihood for f in ("poisson", "negbin", "zip", "zinb")}
    assert ll["negbin"] >= ll["poisson"] - 1e-4
    assert ll["zip"] >= ll["poisson"] - 1e-4
    assert ll["zinb"] >= ll["negbin"] - 1e-4
    y = generate_synthetic_data("exponential", {"scale": 3}, 1000, seed=3)
    ll_exp = fit_distribution(y, "exponential").log_likelihood
    assert fit_distribution(y, "gamma").log_likelihood >= ll_exp - 1e-6
    assert fit_distribution(y, "weibull").log_likelihood >= ll_exp - 1e-6


@pytest.mark.parametrize("family", list(REGISTRY))
def test_input_is_not_modified(family):
    x = generate_synthetic_data(family, EXAMPLE[family], 200, seed=6)
    original = x.copy()
    fit_distribution(x, family)
    np.testing.assert_array_equal(x, original)
    assert x.dtype == original.dtype
    as_list = x.tolist()
    fit_distribution(as_list, family)
    assert as_list == original.tolist()


def test_all_zero_counts_handled():
    zeros = np.zeros(50, dtype=int)
    pois = fit_distribution(zeros, "poisson")
    assert pois.success and pois.at_boundary and pois.params == {"lam": 0.0}
    for family in ("negbin", "zip", "zinb"):
        fit = fit_distribution(zeros, family)
        assert not fit.success
        assert fit.status == "failed"
        assert fit.params == {}
        assert np.isnan(fit.log_likelihood)
        assert "zero" in fit.message


def test_constant_intervals_fail_safely():
    x = np.full(20, 2.5)
    for family in ("lognormal", "gamma", "weibull"):
        fit = fit_distribution(x, family)
        assert fit.status == "failed" and fit.params == {}
    assert fit_distribution(x, "exponential").params["scale"] == pytest.approx(2.5)


def test_underdispersed_counts_flag_negbin_boundary():
    x = np.array([14, 15, 15, 16, 14, 15, 16, 15, 14, 16] * 10)  # variance << mean
    nb = fit_distribution(x, "negbin")
    pois = fit_distribution(x, "poisson")
    assert nb.success and nb.at_boundary
    assert nb.params["r"] > fitting.R_EFFECTIVELY_INFINITE
    assert nb.log_likelihood == pytest.approx(pois.log_likelihood, abs=0.05)
    assert "not identifiable" in nb.message


def test_no_zeros_flags_zero_inflation_boundary():
    x = generate_synthetic_data("poisson", {"lam": 20}, 500, seed=1)
    assert x.min() > 0
    fit = fit_distribution(x, "zip")
    assert fit.success and fit.at_boundary
    assert fit.params["pi"] < fitting.PI_EFFECTIVELY_ZERO


@pytest.mark.parametrize(
    "family, data",
    [
        ("poisson", [1, 2, -1]),
        ("negbin", [1.5, 2, 3]),
        ("gamma", [1.0, 0.0, 2.0]),
        ("weibull", [1.0, -2.0]),
        ("exponential", [1.0, np.nan]),
        ("poisson", [[1, 2], [3, 4]]),
        ("lognormal", []),
    ],
)
def test_invalid_data_rejected(family, data):
    with pytest.raises(ValueError):
        fit_distribution(data, family)


def test_unknown_distribution():
    with pytest.raises(KeyError):
        fit_distribution([1, 2, 3], "normal")


def test_optimizer_failure_is_reported_not_guessed(monkeypatch):
    def always_fail(fun, x0, **kwargs):
        return optimize.OptimizeResult(x=np.asarray(x0), fun=fun(x0), success=False,
                                       message="forced failure")

    monkeypatch.setattr(fitting.optimize, "minimize", always_fail)
    x = generate_synthetic_data("negbin", {"mu": 15, "r": 10}, 200, seed=0)
    fit = fit_distribution(x, "negbin")
    assert fit.status == "failed"
    assert fit.params == {}
    assert np.isnan(fit.log_likelihood)
    assert "forced failure" in fit.message


def test_scipy_exception_is_reported(monkeypatch):
    def boom(x):
        raise RuntimeError("solver exploded")

    monkeypatch.setitem(fitting._SCIPY_FITTERS, "gamma", boom)
    fit = fit_distribution([1.0, 2.0, 3.0], "gamma")
    assert fit.status == "failed" and "solver exploded" in fit.message
