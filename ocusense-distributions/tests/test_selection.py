"""Information criteria, ranking, track separation and held-out validation."""

import numpy as np
import pytest

from ocusense.distributions import COUNT_FAMILIES, INTERVAL_FAMILIES
from ocusense.evaluation import held_out_validation
from ocusense.fitting import FitResult, fit_distribution
from ocusense.selection import (
    akaike_weights,
    best_model,
    calculate_aic,
    calculate_aicc,
    calculate_bic,
    rank_fits,
    select_best_distribution,
)
from ocusense.synthetic import generate_synthetic_data


def test_aic_formula():
    assert calculate_aic(-100.0, 2) == pytest.approx(204.0)
    assert calculate_aic(0.0, 0) == 0.0


def test_aicc_formula():
    # AIC = 204, correction = 2*2*3/(50-2-1) = 12/47
    assert calculate_aicc(-100.0, 2, 50) == pytest.approx(204.0 + 12 / 47)


def test_aicc_infinite_for_tiny_samples():
    assert calculate_aicc(-10.0, 2, 3) == float("inf")
    assert calculate_aicc(-10.0, 3, 4) == float("inf")
    assert np.isfinite(calculate_aicc(-10.0, 2, 4))


def test_bic_formula():
    assert calculate_bic(-100.0, 2, 50) == pytest.approx(2 * np.log(50) + 200.0)


def test_invalid_k_n():
    with pytest.raises(ValueError):
        calculate_aic(-1.0, -1)
    with pytest.raises(ValueError):
        calculate_bic(-1.0, 1, 0)


def test_akaike_weights_from_delta():
    w = akaike_weights(np.array([0.0, 2.0, np.nan]))
    assert w.sum() == pytest.approx(1.0)
    assert w[2] == 0.0
    assert w[0] / w[1] == pytest.approx(np.exp(1.0))


@pytest.mark.parametrize("family, candidates", [("negbin", COUNT_FAMILIES),
                                                ("gamma", INTERVAL_FAMILIES)])
def test_ranking_is_ascending_in_aic(family, candidates):
    params = {"negbin": {"mu": 15, "r": 10}, "gamma": {"shape": 3, "scale": 1}}[family]
    x = generate_synthetic_data(family, params, 400, seed=10)
    table = select_best_distribution(x, candidates)
    aic = table["aic"].to_numpy()
    assert np.all(np.diff(aic) >= 0)
    assert list(table["rank"]) == list(range(1, len(candidates) + 1))
    assert table["delta_aic"].iloc[0] == 0
    assert table["akaike_weight"].sum() == pytest.approx(1.0)
    row = table.iloc[1]
    assert row["aic"] == pytest.approx(calculate_aic(row["log_likelihood"], row["k"]))
    assert row["bic"] == pytest.approx(calculate_bic(row["log_likelihood"], row["k"], row["n"]))


def test_criterion_option_sorts_by_bic():
    x = generate_synthetic_data("exponential", {"scale": 3}, 200, seed=1)
    table = select_best_distribution(x, INTERVAL_FAMILIES, criterion="bic")
    assert np.all(np.diff(table["bic"].to_numpy()) >= 0)


def test_count_and_interval_cannot_be_ranked_together():
    x = generate_synthetic_data("poisson", {"lam": 5}, 100, seed=0)
    with pytest.raises(ValueError, match="Cannot rank count"):
        select_best_distribution(x, ["poisson", "gamma"])
    fits = [fit_distribution(x, "poisson"), fit_distribution(x + 1.0, "gamma")]
    with pytest.raises(ValueError):
        rank_fits(fits)


def test_fits_on_different_data_cannot_be_ranked():
    a = generate_synthetic_data("poisson", {"lam": 5}, 100, seed=0)
    b = generate_synthetic_data("poisson", {"lam": 5}, 100, seed=1)
    with pytest.raises(ValueError, match="identical observations"):
        rank_fits([fit_distribution(a, "poisson"), fit_distribution(b, "negbin")])


def test_failed_fits_rank_last_with_zero_weight():
    zeros = np.zeros(40, dtype=int)
    table = select_best_distribution(zeros, COUNT_FAMILIES)
    assert table.iloc[0]["distribution"] == "poisson"
    failed = table[table["status"] == "failed"]
    assert len(failed) == 3
    assert failed.index.min() > 0
    assert failed["aic"].isna().all() and (failed["akaike_weight"] == 0).all()
    assert best_model(table) == "poisson"


def test_best_model_none_when_everything_failed():
    fit = FitResult("negbin", "count", {}, 2, 10, float("nan"), False, data_hash="x")
    assert best_model(rank_fits([fit])) is None


def test_held_out_uses_training_likelihood_and_size():
    x = generate_synthetic_data("gamma", {"shape": 3, "scale": 1}, 300, seed=4)
    ho = held_out_validation(x, INTERVAL_FAMILIES, test_fraction=0.3, seed=1)
    assert (ho["n_train"] == 210).all() and (ho["n_test"] == 90).all()
    for _, row in ho.iterrows():
        assert row["aic_train"] == pytest.approx(
            calculate_aic(row["train_log_likelihood"], {"exponential": 1}.get(row["candidate"], 2)))
    assert ho["selected_by_train_aic"].sum() == 1
    assert ho["best_on_test"].sum() == 1
    assert ho.loc[ho["best_on_test"], "delta_test_ll"].iloc[0] == 0


def test_held_out_split_is_reproducible():
    x = generate_synthetic_data("poisson", {"lam": 15}, 200, seed=4)
    a = held_out_validation(x, COUNT_FAMILIES, seed=3)
    b = held_out_validation(x, COUNT_FAMILIES, seed=3)
    assert a.equals(b)
