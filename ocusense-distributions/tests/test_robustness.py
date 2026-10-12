"""Noise models and benchmark reproducibility."""

import numpy as np
import pandas as pd
import pytest

from ocusense.evaluation import confusion_matrix, run_benchmark, summarize_accuracy
from ocusense.noise import (
    counts_from_timestamps,
    counts_with_missed_blinks,
    delete_events,
    intervals_from_timestamps,
    intervals_with_missed_blinks,
    intervals_with_timestamp_noise,
    jitter_timestamps,
    thin_counts,
    thinned_count_params,
)
from ocusense.synthetic import generate_blink_timestamps, get_scenario


@pytest.fixture
def timestamps():
    return generate_blink_timestamps("gamma", {"shape": 3, "scale": 1}, 20_000, seed=1)


def test_delete_events_zero_probability_is_identity(timestamps):
    np.testing.assert_array_equal(delete_events(timestamps, 0.0, seed=0), timestamps)


def test_delete_events_rate_and_order(timestamps):
    original = timestamps.copy()
    kept = delete_events(timestamps, 0.2, seed=0)
    np.testing.assert_array_equal(timestamps, original)
    assert kept.size / timestamps.size == pytest.approx(0.8, abs=0.01)
    assert np.all(np.diff(kept) > 0)
    assert np.isin(kept, timestamps).all()


def test_missed_blinks_merge_intervals(timestamps):
    """Deleting events merges neighbouring intervals: fewer, longer intervals
    whose total span is preserved between the surviving events."""
    kept = delete_events(timestamps, 0.3, seed=2)
    merged = intervals_from_timestamps(kept)
    assert merged.sum() == pytest.approx(kept[-1] - kept[0])
    assert merged.mean() == pytest.approx(3.0 / 0.7, rel=0.03)


def test_missed_blinks_exponential_scale_inflation():
    x = intervals_with_missed_blinks("exponential", {"scale": 3}, 50_000, 0.25, seed=3)
    assert x.size == 50_000
    assert x.mean() == pytest.approx(3 / 0.75, rel=0.02)


def test_thin_counts():
    counts = np.random.default_rng(0).poisson(15, 50_000)
    np.testing.assert_array_equal(thin_counts(counts, 0.0, seed=1), counts)
    thinned = thin_counts(counts, 0.2, seed=1)
    assert np.all(thinned <= counts) and np.all(thinned >= 0)
    assert thinned.mean() == pytest.approx(12.0, rel=0.01)


def test_thinned_negbin_keeps_dispersion():
    params = thinned_count_params("negbin", {"mu": 15, "r": 10}, 0.2)
    assert params == {"mu": pytest.approx(12.0), "r": 10.0}
    x = counts_with_missed_blinks("negbin", {"mu": 15, "r": 10}, 200_000, 0.2, seed=5)
    assert x.var() == pytest.approx(12 + 12**2 / 10, rel=0.03)


def test_invalid_miss_probability():
    with pytest.raises(ValueError):
        delete_events(np.arange(5.0), 1.0, seed=0)
    with pytest.raises(ValueError):
        thin_counts(np.arange(5), -0.1, seed=0)


def test_jitter_zero_noise_is_identity(timestamps):
    noisy, merged = jitter_timestamps(timestamps, 0.0, seed=0, min_separation=0.0)
    np.testing.assert_array_equal(noisy, timestamps)
    assert merged == 0


def test_jitter_output_is_ordered_and_separated(timestamps):
    noisy, merged = jitter_timestamps(timestamps, 0.5, seed=0, min_separation=0.05)
    gaps = np.diff(noisy)
    assert np.all(gaps >= 0.05)
    assert merged == timestamps.size - noisy.size
    assert merged > 0


def test_jitter_inflates_interval_variance():
    params = {"shape": 6, "scale": 0.5}
    clean, _ = intervals_with_timestamp_noise("gamma", params, 40_000, 0.0, seed=9)
    noisy, frac = intervals_with_timestamp_noise("gamma", params, 40_000, 0.2, seed=9)
    assert np.all(noisy >= 0.05)
    assert 0 <= frac < 0.01
    assert noisy.var() == pytest.approx(clean.var() + 2 * 0.2**2, rel=0.1)


def test_counts_from_timestamps():
    ts = np.array([0.5, 10.0, 59.9, 60.0, 61.0, 125.0])
    np.testing.assert_array_equal(counts_from_timestamps(ts, 60.0, 180.0), [3, 2, 1])


def _small_benchmark(n_jobs=1):
    scenarios = [get_scenario("poisson_l15"), get_scenario("gamma_a3_s1")]
    return run_benchmark(scenarios, sample_sizes=(30, 100), n_reps=3, base_seed=7,
                         n_jobs=n_jobs, heldout_fraction=0.3)


def test_benchmark_is_reproducible():
    a, b = _small_benchmark(), _small_benchmark()
    for name in ("replicates", "fits", "params", "heldout"):
        pd.testing.assert_frame_equal(getattr(a, name), getattr(b, name))


def test_benchmark_independent_of_worker_count():
    a, b = _small_benchmark(1), _small_benchmark(2)
    pd.testing.assert_frame_equal(a.replicates, b.replicates)
    pd.testing.assert_frame_equal(a.fits, b.fits)


def test_benchmark_summaries_are_consistent():
    res = _small_benchmark()
    assert len(res.replicates) == 2 * 2 * 3
    acc = summarize_accuracy(res.replicates)
    freq_cols = [c for c in acc if c.startswith("freq_")]
    np.testing.assert_allclose(acc[freq_cols].sum(axis=1), 1.0)
    cm = confusion_matrix(res.replicates, "count")
    np.testing.assert_allclose(cm.sum(axis=1), 1.0)
