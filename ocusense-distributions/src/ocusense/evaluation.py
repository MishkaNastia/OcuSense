"""Monte Carlo evaluation of model selection and parameter recovery.

Every replicate's data are produced from a seed derived deterministically
from ``(base_seed, scenario name, n, replicate, condition...)`` (see
:func:`ocusense.synthetic.derive_seed`). Results are therefore reproducible
and independent of worker count or scenario order.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .distributions import COUNT_FAMILIES, INTERVAL_FAMILIES, families_for_track, get_distribution
from .fitting import FitResult, fit_distribution
from .selection import best_model, rank_fits
from .synthetic import Scenario, derive_seed

DataFn = Callable[[Scenario, int, int], np.ndarray]
ALL_FAMILIES = COUNT_FAMILIES + INTERVAL_FAMILIES


def _params_json(params: Mapping[str, float]) -> str:
    return json.dumps({k: round(float(v), 6) for k, v in params.items()})


# ---------------------------------------------------------------------------
# One dataset
# ---------------------------------------------------------------------------


def evaluate_dataset(
    data: np.ndarray,
    scenario: Scenario,
    reference_params: Mapping[str, float] | None = None,
    candidates: Sequence[str] | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """Fit all candidates to one dataset and score the selection.

    Args:
        data: Observations generated under ``scenario``.
        scenario: The generating configuration.
        reference_params: Parameters estimates are compared with (defaults to
            the generating parameters; e.g. thinned parameters for missed-blink
            experiments).
        candidates: Candidate families (default: all families of the track).

    Returns:
        ``(replicate_record, fit_rows, parameter_rows)``.
    """
    candidates = tuple(candidates or families_for_track(scenario.track))
    table = rank_fits([fit_distribution(data, name) for name in candidates])
    by_name = table.set_index("distribution")
    true = scenario.distribution
    selected = {c: best_model(table, c) or "none" for c in ("aic", "aicc", "bic")}
    acceptable = {true, *scenario.equivalent_families}
    ok = table[table["status"] != "failed"]
    true_row = by_name.loc[true] if true in by_name.index else None
    true_ok = true_row is not None and true_row["status"] != "failed"

    record = {
        "scenario": scenario.name,
        "regime": scenario.regime,
        "track": scenario.track,
        "true_family": true,
        "n": int(len(data)),
        **{f"selected_{c}": s for c, s in selected.items()},
        **{f"correct_{c}": s == true for c, s in selected.items()},
        "equivalent_aic": selected["aic"] in acceptable,
        "true_delta_aic": float(true_row["delta_aic"]) if true_ok else np.nan,
        "true_akaike_weight": float(true_row["akaike_weight"]) if true_ok else np.nan,
        "true_fit_status": true_row["status"] if true_row is not None else "not_candidate",
        "runner_up_delta_aic": float(ok["delta_aic"].nsmallest(2).iloc[-1]) if len(ok) > 1 else np.nan,
        "n_failed": int((table["status"] == "failed").sum()),
        "n_boundary": int((table["status"] == "boundary").sum()),
    }

    fit_rows = [
        {
            "scenario": scenario.name,
            "true_family": true,
            "n": int(len(data)),
            "rank": int(row["rank"]),
            "candidate": row["distribution"],
            "parameters": _params_json(row["parameters"]),
            "log_likelihood": row["log_likelihood"],
            "k": int(row["k"]),
            "aic": row["aic"],
            "aicc": row["aicc"],
            "bic": row["bic"],
            "delta_aic": row["delta_aic"],
            "akaike_weight": row["akaike_weight"],
            "status": row["status"],
        }
        for _, row in table.iterrows()
    ]

    param_rows = []
    reference = dict(reference_params or scenario.params)
    if true_ok:
        for pname, estimate in true_row["parameters"].items():
            truth = float(reference[pname])
            param_rows.append({
                "scenario": scenario.name,
                "true_family": true,
                "n": int(len(data)),
                "parameter": pname,
                "true_value": truth,
                "estimate": float(estimate),
                "error": float(estimate) - truth,
                "rel_error": (float(estimate) - truth) / abs(truth) if truth != 0 else np.nan,
                "fit_status": true_row["status"],
            })
    return record, fit_rows, param_rows


def held_out_validation(
    data: np.ndarray,
    candidates: Sequence[str],
    test_fraction: float = 0.3,
    seed: int = 0,
) -> pd.DataFrame:
    """Random train/test split; AIC from training data, predictive LL on test.

    AIC is computed only from the training log-likelihood and training sample
    size. The held-out log-likelihood evaluates the training-fitted
    parameters on the unseen observations. (Random splits are appropriate for
    independent synthetic samples; temporally dependent sequences would need
    chronological splits.)
    """
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be in (0, 1)")
    x = np.asarray(data)
    order = np.random.default_rng(seed).permutation(x.size)
    n_test = max(1, int(round(test_fraction * x.size)))
    if x.size - n_test < 2:
        raise ValueError("too few observations to split")
    test, train = x[order[:n_test]], x[order[n_test:]]

    table = rank_fits([fit_distribution(train, name) for name in candidates])
    rows = []
    for _, row in table.iterrows():
        spec = get_distribution(row["distribution"])
        if row["status"] == "failed":
            test_ll = np.nan
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                test_ll = float(np.sum(spec.logprob(test.astype(float), row["parameters"])))
        rows.append({
            "candidate": row["distribution"],
            "n_train": int(train.size),
            "n_test": int(test.size),
            "train_log_likelihood": row["log_likelihood"],
            "aic_train": row["aic"],
            "delta_aic_train": row["delta_aic"],
            "test_log_likelihood": test_ll,
            "test_ll_per_obs": test_ll / test.size,
            "status": row["status"],
        })
    out = pd.DataFrame(rows)
    out["delta_test_ll"] = out["test_log_likelihood"].max() - out["test_log_likelihood"]
    selected = best_model(table, "aic")
    finite = out["test_log_likelihood"].replace(-np.inf, np.nan)
    best_test = out.loc[finite.idxmax(), "candidate"] if finite.notna().any() else None
    out["selected_by_train_aic"] = out["candidate"] == selected
    out["best_on_test"] = out["candidate"] == best_test
    return out


# ---------------------------------------------------------------------------
# Monte Carlo blocks
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResults:
    """Long-format outputs of a Monte Carlo run."""

    replicates: pd.DataFrame
    fits: pd.DataFrame
    params: pd.DataFrame
    heldout: pd.DataFrame


def run_block(
    scenario: Scenario,
    n: int,
    n_reps: int,
    base_seed: int,
    data_fn: DataFn | None = None,
    condition: Mapping[str, object] | None = None,
    reference_params: Mapping[str, float] | None = None,
    heldout_fraction: float | None = None,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Run ``n_reps`` replicates of one scenario at one sample size.

    ``condition`` labels (e.g. ``{"miss_prob": 0.1}``) are added to every row
    and mixed into the seed. ``data_fn(scenario, n, seed)`` overrides plain
    generation (used for noise experiments).
    """
    condition = dict(condition or {})
    reps, fits, params, heldout = [], [], [], []
    for rep in range(n_reps):
        seed = derive_seed(base_seed, scenario.name, n, rep, *sorted(condition.items()))
        data = data_fn(scenario, n, seed) if data_fn else scenario.generate(n, seed)
        record, fit_rows, param_rows = evaluate_dataset(data, scenario, reference_params)
        meta = {"rep": rep, "seed": seed, **condition}
        reps.append({**record, **meta})
        fits.extend({**row, **meta} for row in fit_rows)
        params.extend({**row, **meta} for row in param_rows)
        if heldout_fraction:
            ho = held_out_validation(data, families_for_track(scenario.track), heldout_fraction,
                                     derive_seed(seed, "split"))
            ho.insert(0, "scenario", scenario.name)
            ho.insert(1, "track", scenario.track)
            ho.insert(2, "true_family", scenario.distribution)
            ho.insert(3, "n", n)
            for key, value in meta.items():
                ho[key] = value
            heldout.extend(ho.to_dict("records"))
    return reps, fits, params, heldout


def _run_block_star(kwargs: dict):
    return run_block(**kwargs)


def run_blocks(tasks: Sequence[dict], n_jobs: int = 1) -> BenchmarkResults:
    """Execute ``run_block`` keyword-argument dicts, optionally in parallel.

    Output row order follows ``tasks`` regardless of ``n_jobs``.
    """
    if n_jobs > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=n_jobs) as pool:
            outputs = list(pool.map(_run_block_star, tasks))
    else:
        outputs = [run_block(**task) for task in tasks]
    frames = [pd.DataFrame([row for out in outputs for row in out[i]]) for i in range(4)]
    return BenchmarkResults(*frames)


def run_benchmark(
    scenarios: Iterable[Scenario],
    sample_sizes: Sequence[int] = (30, 100, 300, 1000, 5000),
    n_reps: int = 100,
    base_seed: int = 20240601,
    n_jobs: int = 1,
    heldout_fraction: float | None = 0.3,
) -> BenchmarkResults:
    """Repeated generate -> fit all candidates -> AIC selection experiment."""
    tasks = [
        {"scenario": s, "n": int(n), "n_reps": n_reps, "base_seed": base_seed,
         "heldout_fraction": heldout_fraction}
        for s in scenarios for n in sample_sizes
    ]
    return run_blocks(tasks, n_jobs)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def wilson_interval(successes: float, trials: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials == 0:
        return np.nan, np.nan
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return centre - half, centre + half


def summarize_accuracy(replicates: pd.DataFrame, group_cols: Sequence[str] | None = None,
                       ) -> pd.DataFrame:
    """Recovery accuracy, selection frequencies and AIC statistics per group."""
    group_cols = list(group_cols or ["scenario", "regime", "track", "true_family", "n"])
    rows = []
    for keys, g in replicates.groupby(group_cols, sort=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        hits = int(g["correct_aic"].sum())
        lo, hi = wilson_interval(hits, len(g))
        row = dict(zip(group_cols, keys))
        row.update({
            "n_reps": len(g),
            "accuracy_aic": hits / len(g),
            "accuracy_aic_ci_low": lo,
            "accuracy_aic_ci_high": hi,
            "accuracy_aicc": g["correct_aicc"].mean(),
            "accuracy_bic": g["correct_bic"].mean(),
            "equivalent_accuracy_aic": g["equivalent_aic"].mean(),
            "true_within_2_aic": (g["true_delta_aic"] <= 2).mean(),
            "mean_true_delta_aic": g["true_delta_aic"].mean(),
            "median_true_delta_aic": g["true_delta_aic"].median(),
            "mean_true_akaike_weight": g["true_akaike_weight"].mean(),
            "median_runner_up_delta_aic": g["runner_up_delta_aic"].median(),
            "true_fit_failure_rate": (g["true_fit_status"] == "failed").mean(),
            "any_fit_failure_rate": (g["n_failed"] > 0).mean(),
            "mean_boundary_fits": g["n_boundary"].mean(),
        })
        track_families = families_for_track(g["track"].iloc[0])
        for family in ALL_FAMILIES:
            row[f"freq_{family}"] = (g["selected_aic"] == family).mean() if family in track_families else np.nan
        wrong = g.loc[~g["correct_aic"], "selected_aic"]
        row["most_common_wrong"] = wrong.mode().iloc[0] if not wrong.empty else ""
        rows.append(row)
    return pd.DataFrame(rows)


def confusion_matrix(replicates: pd.DataFrame, track: str, n: int | None = None,
                     criterion: str = "aic", normalize: bool = True) -> pd.DataFrame:
    """True family (rows) x selected family (columns), pooling scenarios."""
    families = list(families_for_track(track))
    sub = replicates[replicates["track"] == track]
    if n is not None:
        sub = sub[sub["n"] == n]
    columns = families + (["none"] if (sub[f"selected_{criterion}"] == "none").any() else [])
    table = pd.crosstab(sub["true_family"], sub[f"selected_{criterion}"])
    table = table.reindex(index=[f for f in families if f in table.index], columns=columns,
                          fill_value=0)
    if normalize:
        table = table.div(table.sum(axis=1), axis=0)
    table.index.name, table.columns.name = "true_family", "selected_family"
    return table


def parameter_recovery_summary(params: pd.DataFrame,
                               group_cols: Sequence[str] | None = None) -> pd.DataFrame:
    """Bias and error of the true family's estimates per group."""
    group_cols = list(group_cols or ["scenario", "true_family", "n", "parameter"])
    g = params.groupby(group_cols, sort=False)
    out = g.agg(
        true_value=("true_value", "first"),
        n_fits=("estimate", "size"),
        mean_estimate=("estimate", "mean"),
        median_estimate=("estimate", "median"),
        bias=("error", "mean"),
        mean_abs_error=("error", lambda e: e.abs().mean()),
        median_abs_error=("error", lambda e: e.abs().median()),
        rmse=("error", lambda e: float(np.sqrt(np.mean(e ** 2)))),
        mean_rel_error=("rel_error", "mean"),
        median_abs_rel_error=("rel_error", lambda e: e.abs().median()),
        boundary_rate=("fit_status", lambda s: (s == "boundary").mean()),
    )
    return out.reset_index()


def fit_status_rates(fits: pd.DataFrame, group_cols: Sequence[str] | None = None) -> pd.DataFrame:
    """Failure and boundary rates per candidate."""
    group_cols = list(group_cols or ["scenario", "true_family", "n", "candidate"])
    g = fits.groupby(group_cols, sort=False)["status"]
    return pd.DataFrame({
        "n_fits": g.size(),
        "failure_rate": g.apply(lambda s: (s == "failed").mean()),
        "boundary_rate": g.apply(lambda s: (s == "boundary").mean()),
    }).reset_index()


def heldout_summary(heldout: pd.DataFrame, tolerance: float = 1.0) -> pd.DataFrame:
    """Agreement of training-AIC choice with held-out predictive performance.

    ``agreement_rate`` requires the AIC choice to be *exactly* the best model
    on the test set; with nested candidates whose test log-likelihoods differ
    by hundredths, that is close to a coin flip among ties. ``near_best_rate``
    counts the AIC choice as agreeing when its held-out log-likelihood is
    within ``tolerance`` (default 1, i.e. 2 units on the deviance/AIC scale)
    of the best candidate's.
    """
    rows = []
    keys = ["scenario", "track", "true_family", "n"]
    for key, g in heldout.groupby(keys, sort=False):
        per_rep = []
        for _, rep in g.groupby("rep"):
            sel = rep[rep["selected_by_train_aic"]]
            truth = rep[rep["candidate"] == key[2]]
            per_rep.append({
                "agree": bool(rep.loc[rep["selected_by_train_aic"], "best_on_test"].any()),
                "aic_regret": float(sel["delta_test_ll"].iloc[0]) if len(sel) else np.nan,
                "aic_vs_true_test_ll": (float(sel["test_log_likelihood"].iloc[0])
                                        - float(truth["test_log_likelihood"].iloc[0]))
                if len(sel) and len(truth) else np.nan,
            })
        reps = pd.DataFrame(per_rep)
        rows.append({
            **dict(zip(keys, key)),
            "n_reps": len(reps),
            "agreement_rate": reps["agree"].mean(),
            "near_best_rate": (reps["aic_regret"] <= tolerance).mean(),
            "mean_test_ll_regret": reps["aic_regret"].mean(),
            "median_test_ll_regret": reps["aic_regret"].median(),
            "mean_test_ll_vs_true_family": reps["aic_vs_true_test_ll"].mean(),
        })
    return pd.DataFrame(rows)


def parametric_bootstrap(fit: FitResult, n_boot: int = 200, seed: int = 0,
                         level: float = 0.95) -> pd.DataFrame:
    """Percentile intervals for a fit's parameters by parametric bootstrap.

    Datasets of the original size are simulated from the fitted model and
    refitted with the same family. Failed refits are dropped and counted.
    """
    if not fit.success:
        raise ValueError("cannot bootstrap a failed fit")
    spec = get_distribution(fit.distribution)
    draws: list[dict[str, float]] = []
    failures = 0
    for b in range(n_boot):
        rng = np.random.default_rng(derive_seed(seed, "boot", b))
        sample = np.asarray(spec.sample(rng, fit.params, fit.n))
        refit = fit_distribution(sample, fit.distribution)
        if refit.success:
            draws.append(refit.params)
        else:
            failures += 1
    boot = pd.DataFrame(draws)
    alpha = (1 - level) / 2
    return pd.DataFrame({
        "family": fit.distribution,
        "parameter": list(fit.params),
        "estimate": list(fit.params.values()),
        "ci_low": [boot[p].quantile(alpha) if len(boot) else np.nan for p in fit.params],
        "ci_high": [boot[p].quantile(1 - alpha) if len(boot) else np.nan for p in fit.params],
        "n_boot_ok": len(boot),
        "n_boot_failed": failures,
    })
