"""End-to-end recovery: data generated from a known distribution must be
assigned back to that distribution by the selection pipeline.

Each scenario is checked on several independent synthetic datasets, and every
dataset's selection is reported. A rare dataset can legitimately favour
another family: for example, an NB sample with 3 SD too many zeros is better
described by ZINB. So a scenario passes when nearly all datasets recover the
true family, not when one hand-picked seed does.

Why two criteria:
* BIC is consistent: at large n it picks the true family on essentially every
  dataset, so it is used for the strict check.
* AIC (the benchmark's primary criterion) is not consistent for nested models.
  When the true family sits inside a larger candidate (Poisson in NB/ZIP,
  Exponential in Gamma/Weibull, NB and ZIP in ZINB), AIC picks the larger
  model on about 8-18% of datasets at any n, so its threshold is lower.
"""

from functools import lru_cache

import numpy as np
import pytest

from ocusense.distributions import families_for_track
from ocusense.selection import best_model, select_best_distribution
from ocusense.synthetic import OVERLAP_SCENARIOS, PRIMARY_SCENARIOS, derive_seed, get_scenario

LARGE_N = 5000
N_DATASETS = 10
MIN_BIC_HITS = 9  # at most one rare dataset per scenario


@lru_cache(maxsize=None)
def _selections(scenario_name: str, n: int, n_datasets: int, criterion: str):
    """(selected family, parameters of the selected model) for each dataset."""
    scenario = get_scenario(scenario_name)
    out = []
    for i in range(n_datasets):
        data = scenario.generate(n, derive_seed(i, scenario.name, n))
        table = select_best_distribution(data, families_for_track(scenario.track), criterion)
        selected = best_model(table, criterion)
        params = table.loc[table["distribution"] == selected, "parameters"].iloc[0]
        out.append((selected, params))
    return out


def _report(scenario, selections):
    return f"{scenario.name} (true {scenario.distribution}): selected " + ", ".join(
        f"#{i}={sel}" for i, (sel, _) in enumerate(selections))


@pytest.mark.parametrize("scenario", PRIMARY_SCENARIOS, ids=lambda s: s.name)
def test_bic_selects_true_family(scenario):
    selections = _selections(scenario.name, LARGE_N, N_DATASETS, "bic")
    hits = sum(sel == scenario.distribution for sel, _ in selections)
    assert hits >= MIN_BIC_HITS, f"{hits}/{N_DATASETS} correct. " + _report(scenario, selections)


@pytest.mark.parametrize("scenario", PRIMARY_SCENARIOS, ids=lambda s: s.name)
def test_selected_model_recovers_true_parameters(scenario):
    selections = _selections(scenario.name, LARGE_N, N_DATASETS, "bic")
    correct = [params for sel, params in selections if sel == scenario.distribution]
    for name, truth in scenario.params.items():
        median = float(np.median([p[name] for p in correct]))
        # Dispersion r and zero-inflation pi are the hardest parameters to estimate.
        tolerance = 0.15 if name in ("r", "pi") else 0.05
        assert median == pytest.approx(truth, rel=tolerance), (
            f"{scenario.name}: median {name} estimate {median:.4g}, true {truth}")


@pytest.mark.parametrize("scenario", PRIMARY_SCENARIOS, ids=lambda s: s.name)
def test_aic_selects_true_family_in_most_datasets(scenario):
    selections = _selections(scenario.name, 1000, 20, "aic")
    rate = np.mean([sel == scenario.distribution for sel, _ in selections])
    # Theoretical AIC ceiling for the worst case (Exponential, two nested
    # competitors) is about 0.80; 0.6 leaves room for Monte Carlo noise.
    assert rate >= 0.6, f"AIC recovery {rate:.2f}. " + _report(scenario, selections)


EXACTLY_EQUIVALENT = [s for s in OVERLAP_SCENARIOS if s.equivalent_families]


@pytest.mark.parametrize("scenario", EXACTLY_EQUIVALENT, ids=lambda s: s.name)
def test_shape_one_gamma_and_weibull_resolve_to_exponential(scenario):
    """Gamma(shape=1) and Weibull(shape=1) ARE Exponential, so the most
    parsimonious correct answer is Exponential."""
    selections = _selections(scenario.name, LARGE_N, N_DATASETS, "bic")
    hits = sum(sel == "exponential" for sel, _ in selections)
    assert hits >= MIN_BIC_HITS, _report(scenario, selections)
