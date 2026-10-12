"""Correctness of the count-noise model and the benchmark bookkeeping.

These tests check the implementation, not statistical performance: no test
here depends on how often a family is recovered.
"""

import numpy as np
import pandas as pd
import pytest

from ocusense.distributions import get_distribution
from ocusense.evaluation import BenchmarkResults
from ocusense.noise import (
    CountDetectionNoise,
    add_false_positives,
    counts_with_detection_noise,
    counts_with_missed_blinks,
    noisy_count_mean,
    noisy_count_params,
)
from ocusense.recovery import (
    CheckResult,
    CheckSpec,
    RecoveryConfig,
    RecoveryResults,
    Thresholds,
    confusion_table,
    evaluate_all,
    evaluate_check,
    family_preserved,
    format_report,
    plan_checks,
    run_recovery,
    selection_summary,
)
from ocusense.synthetic import get_scenario


def test_false_positives_zero_rate_is_identity():
    counts = np.array([0, 3, 7, 12])
    np.testing.assert_array_equal(add_false_positives(counts, 0.0, seed=1), counts)


def test_false_positives_only_add_events():
    counts = np.random.default_rng(0).poisson(10, 50_000)
    noisy = add_false_positives(counts, 2.0, seed=1)
    assert np.all(noisy >= counts)
    assert (noisy - counts).mean() == pytest.approx(2.0, rel=0.02)
    assert (noisy - counts).var() == pytest.approx(2.0, rel=0.05)


def test_false_positives_reject_invalid_input():
    with pytest.raises(ValueError):
        add_false_positives(np.array([1, 2]), -1.0, seed=0)
    with pytest.raises(ValueError):
        add_false_positives(np.array([1.5]), 1.0, seed=0)


def test_detection_noise_without_false_positives_equals_missed_blinks():
    a = counts_with_detection_noise("negbin", {"mu": 15, "r": 10}, 200, 0.2, 0.0, seed=4)
    b = counts_with_missed_blinks("negbin", {"mu": 15, "r": 10}, 200, 0.2, seed=4)
    np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("family, params", [
    ("poisson", {"lam": 15}), ("negbin", {"mu": 15, "r": 10}),
    ("zip", {"lam": 15, "pi": 0.2}), ("zinb", {"mu": 15, "r": 10, "pi": 0.2})])
def test_observed_mean_formula(family, params):
    x = counts_with_detection_noise(family, params, 200_000, 0.2, 1.5, seed=7)
    expected = noisy_count_mean(family, params, 0.2, 1.5)
    assert expected == pytest.approx(0.8 * get_distribution(family).mean(params) + 1.5)
    assert x.mean() == pytest.approx(expected, rel=0.01)


def test_poisson_with_false_positives_stays_poisson():
    params = noisy_count_params("poisson", {"lam": 10}, 0.2, 3.0)
    assert params == {"lam": pytest.approx(11.0)}
    x = counts_with_detection_noise("poisson", {"lam": 10}, 200_000, 0.2, 3.0, seed=2)
    assert x.var() / x.mean() == pytest.approx(1.0, abs=0.02)


def test_family_preservation_rules():
    assert family_preserved("negbin", 0.3, 0.0)
    assert family_preserved("poisson", 0.1, 3.0)
    assert not family_preserved("negbin", 0.0, 1.0)
    assert not family_preserved("zip", 0.1, 1.0)
    assert noisy_count_params("zinb", {"mu": 15, "r": 10, "pi": 0.2}, 0.0, 1.0) is None


def test_count_detection_noise_rejects_interval_scenarios():
    with pytest.raises(ValueError):
        CountDetectionNoise(0.1, 1.0)(get_scenario("gamma_a3_s1"), 10, 0)


def test_check_comparison_directions():
    sel = CheckSpec("selection", "s", 1000, 0.75, criterion="bic")
    assert CheckResult(sel, 0.75, 100).passed
    assert not CheckResult(sel, 0.74, 100).passed
    par = CheckSpec("parameter", "s", 1000, 0.20, parameter="mu")
    assert CheckResult(par, 0.20, 100).passed
    assert not CheckResult(par, 0.21, 100).passed
    assert not CheckResult(par, float("nan"), 0).passed
    assert "FAIL" in CheckResult(par, 0.5, 100).line()


def test_plan_checks_only_grades_preserved_noise_families():
    config = RecoveryConfig(scenarios=(get_scenario("poisson_l15"), get_scenario("negbin_m15_r10")),
                            sample_sizes=(1000, 5000), noise_sample_sizes=(1000, 5000),
                            noise_conditions=((0.2, 0.0), (0.0, 1.0)))
    specs = plan_checks(config)
    noise_sel = {(s.scenario, s.fp_rate) for s in specs if s.kind == "noise_selection"}
    assert noise_sel == {("poisson_l15", 0.0), ("poisson_l15", 1.0), ("negbin_m15_r10", 0.0)}
    means = [s for s in specs if s.kind == "noise_mean"]
    assert len(means) == 2 * 2 * 2  # scenarios x conditions x sizes: every condition graded
    names = [s.name for s in specs]
    assert len(names) == len(set(names))


def _fake_results():
    reps = pd.DataFrame({
        "scenario": ["a"] * 4, "track": ["count"] * 4, "true_family": ["poisson"] * 4,
        "n": [1000] * 4,
        "selected_aic": ["poisson", "negbin", "poisson", "zip"],
        "selected_bic": ["poisson", "poisson", "poisson", "negbin"],
    })
    reps["correct_aic"] = reps["selected_aic"] == "poisson"
    reps["correct_bic"] = reps["selected_bic"] == "poisson"
    params = pd.DataFrame({"scenario": ["a"] * 4, "n": [1000] * 4, "parameter": ["lam"] * 4,
                           "error": [0.1, -0.2, 0.3, -0.4], "rel_error": [0.01, -0.02, 0.03, -0.04],
                           "true_value": [10.0] * 4, "estimate": [10.1, 9.8, 10.3, 9.6]})
    return RecoveryResults(BenchmarkResults(reps, pd.DataFrame(), params, pd.DataFrame()), None)


def test_selection_summary_and_confusions_count_correctly():
    res = _fake_results()
    summ = selection_summary(res.clean.replicates, ["scenario", "n"]).iloc[0]
    assert summ["aic_accuracy"] == 0.5 and summ["bic_accuracy"] == 0.75
    assert summ["bic_top_confusion"] == "negbin" and summ["bic_top_confusion_share"] == 0.25
    conf = confusion_table(res.clean.replicates, "aic")
    assert conf["share"].sum() == pytest.approx(1.0)
    assert conf.set_index("selected").loc["poisson", "share"] == 0.5


def test_evaluate_check_uses_the_right_statistic():
    res = _fake_results()
    sel = evaluate_check(CheckSpec("selection", "a", 1000, 0.7, criterion="bic"), res)
    assert sel.value == 0.75 and sel.passed and sel.n_datasets == 4
    par = evaluate_check(CheckSpec("parameter", "a", 1000, 0.02, parameter="lam"), res)
    assert par.value == pytest.approx(0.025) and not par.passed  # median of |rel errors|


def test_tiny_benchmark_runs_and_is_reproducible():
    config = RecoveryConfig(scenarios=(get_scenario("poisson_l15"), get_scenario("gamma_a3_s1")),
                            sample_sizes=(30, 1000), n_reps=3, noise_conditions=((0.2, 1.0),),
                            noise_sample_sizes=(1000,), thresholds=Thresholds())
    a, b = run_recovery(config), run_recovery(config)
    pd.testing.assert_frame_equal(a.clean.replicates, b.clean.replicates)
    pd.testing.assert_frame_equal(a.noise.replicates, b.noise.replicates)
    checks = evaluate_all(config, a)
    assert len(checks) == len(plan_checks(config))
    report = format_report(config, a, checks)
    for heading in ("1. DISTRIBUTION RECOVERY", "2. MOST COMMON CONFUSIONS",
                    "3. PARAMETER ESTIMATION", "4. COUNT DATA WITH DETECTION NOISE",
                    "OVERALL:"):
        assert heading in report
