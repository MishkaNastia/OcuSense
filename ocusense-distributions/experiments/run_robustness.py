"""Robustness of AIC model selection to imperfect blink measurements.

Experiment A  Missed blinks: each blink is missed independently with
              probability q in {0, .05, .1, .2, .3}. Intervals are rebuilt from
              the surviving timestamps (neighbouring intervals merge); counts use
              binomial thinning.
Experiment B  Timestamp noise: Gaussian jitter (sigma in seconds) on blink
              timestamps, re-sorted, detections < 50 ms apart merged.
Experiment C  Sample size: AIC vs AICc vs BIC recovery for n in 30..5000.
Experiment D  Distribution overlap: regimes where families nearly coincide.

Parameter bias is always measured against the ORIGINAL generating
parameters, with the theoretically expected bias added where the
observation model keeps the family (thinned counts, exponential intervals).

Outputs:
    tables/robustness_results.csv      accuracy / selection summary, all experiments
    tables/robustness_parameters.csv   parameter bias summary (A, B)
    tables/robustness_replicates.csv   one row per simulated dataset
    figures/robustness_*.png

Examples:
    python experiments/run_robustness.py --smoke
    python experiments/run_robustness.py --reps 100 --n 300
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ocusense import visualization as viz
from ocusense.evaluation import parameter_recovery_summary, run_blocks, summarize_accuracy
from ocusense.noise import (
    MissedBlinks,
    TimestampNoise,
    intervals_with_timestamp_noise,
    thinned_count_params,
)
from ocusense.synthetic import OVERLAP_SCENARIOS, Scenario, default_scenarios

ROOT = Path(__file__).resolve().parents[1]
MISS_PROBS = (0.0, 0.05, 0.1, 0.2, 0.3)
SIGMAS = (0.0, 0.02, 0.05, 0.1, 0.2, 0.5)
SAMPLE_SIZES = (30, 100, 300, 1000, 5000)


def expected_params(scenario: Scenario, miss_prob: float) -> dict[str, float] | None:
    """Parameters implied by missed blinks when the family is preserved."""
    if scenario.track == "count":
        return thinned_count_params(scenario.distribution, scenario.params, miss_prob)
    if scenario.distribution == "exponential":
        return {"scale": scenario.params["scale"] / (1 - miss_prob)}
    return None


def experiment_missed_blinks(n: int, reps: int, seed: int, n_jobs: int):
    tasks = [{"scenario": s, "n": n, "n_reps": reps, "base_seed": seed,
              "data_fn": MissedBlinks(q), "condition": {"miss_prob": q}}
             for s in default_scenarios() for q in MISS_PROBS]
    res = run_blocks(tasks, n_jobs)
    acc = summarize_accuracy(res.replicates, ["scenario", "regime", "track", "true_family", "n",
                                              "miss_prob"])
    par = parameter_recovery_summary(res.params, ["scenario", "true_family", "n", "parameter",
                                                  "miss_prob"])
    by_name = {s.name: s for s in default_scenarios()}
    par["expected_rel_error"] = [
        (expected[p] - row.true_value) / abs(row.true_value)
        if (expected := expected_params(by_name[row.scenario], row.miss_prob)) else np.nan
        for row, p in zip(par.itertuples(), par["parameter"])
    ]
    return res, acc, par


def experiment_timestamp_noise(n: int, reps: int, seed: int, n_jobs: int):
    scenarios = default_scenarios("interval")
    tasks = [{"scenario": s, "n": n, "n_reps": reps, "base_seed": seed,
              "data_fn": TimestampNoise(sigma), "condition": {"sigma": sigma}}
             for s in scenarios for sigma in SIGMAS]
    res = run_blocks(tasks, n_jobs)
    acc = summarize_accuracy(res.replicates, ["scenario", "regime", "track", "true_family", "n",
                                              "sigma"])
    # Share of detections removed by the 50 ms merge rule (diagnostic only).
    merged = {
        (s.name, sigma): np.mean([intervals_with_timestamp_noise(
            s.distribution, s.params, n, sigma, seed + r)[1] for r in range(10)])
        for s in scenarios for sigma in SIGMAS
    }
    acc["merged_fraction"] = [merged[(a, b)] for a, b in zip(acc["scenario"], acc["sigma"])]
    par = parameter_recovery_summary(res.params, ["scenario", "true_family", "n", "parameter",
                                                  "sigma"])
    par["expected_rel_error"] = np.nan
    return res, acc, par


def experiment_sample_size(reps: int, seed: int, n_jobs: int, sizes):
    tasks = [{"scenario": s, "n": n, "n_reps": reps, "base_seed": seed}
             for s in default_scenarios() for n in sizes]
    res = run_blocks(tasks, n_jobs)
    return res, summarize_accuracy(res.replicates)


def experiment_overlap(reps: int, seed: int, n_jobs: int, sizes):
    tasks = [{"scenario": s, "n": n, "n_reps": reps, "base_seed": seed}
             for s in OVERLAP_SCENARIOS for n in sizes]
    res = run_blocks(tasks, n_jobs)
    acc = summarize_accuracy(res.replicates)
    notes = {s.name: s.note for s in OVERLAP_SCENARIOS}
    acc["note"] = acc["scenario"].map(notes)
    return res, acc


def tag(df: pd.DataFrame, experiment: str, factor: str, level_col: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "experiment", experiment)
    out.insert(1, "factor", factor)
    out.insert(2, "level", out[level_col])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--n", type=int, default=300, help="sample size for experiments A and B")
    parser.add_argument("--sample-sizes", type=int, nargs="+", default=list(SAMPLE_SIZES))
    parser.add_argument("--seed", type=int, default=777)
    parser.add_argument("--n-jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--smoke", action="store_true", help="10 reps, n in {30, 100, 300}")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    if args.smoke:
        args.reps, args.sample_sizes = 10, [30, 100, 300]
    tables, figures = args.out / "tables", args.out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)
    start = time.time()

    res_a, acc_a, par_a = experiment_missed_blinks(args.n, args.reps, args.seed, args.n_jobs)
    print(f"[A] missed blinks done ({time.time() - start:.0f}s)")
    res_b, acc_b, par_b = experiment_timestamp_noise(args.n, args.reps, args.seed, args.n_jobs)
    print(f"[B] timestamp noise done ({time.time() - start:.0f}s)")
    res_c, acc_c = experiment_sample_size(args.reps, args.seed, args.n_jobs, args.sample_sizes)
    print(f"[C] sample size done ({time.time() - start:.0f}s)")
    res_d, acc_d = experiment_overlap(args.reps, args.seed, args.n_jobs, args.sample_sizes)
    print(f"[D] overlap done ({time.time() - start:.0f}s)")

    results = pd.concat([
        tag(acc_a, "A_missed_blinks", "miss_prob", "miss_prob"),
        tag(acc_b, "B_timestamp_noise", "sigma_seconds", "sigma"),
        tag(acc_c, "C_sample_size", "n", "n"),
        tag(acc_d, "D_overlap", "n", "n"),
    ], ignore_index=True)
    params = pd.concat([tag(par_a, "A_missed_blinks", "miss_prob", "miss_prob"),
                        tag(par_b, "B_timestamp_noise", "sigma_seconds", "sigma")],
                       ignore_index=True)
    replicates = pd.concat([
        res_a.replicates.assign(experiment="A_missed_blinks"),
        res_b.replicates.assign(experiment="B_timestamp_noise"),
        res_c.replicates.assign(experiment="C_sample_size"),
        res_d.replicates.assign(experiment="D_overlap"),
    ], ignore_index=True)
    results.to_csv(tables / "robustness_results.csv", index=False, float_format="%.6g")
    params.to_csv(tables / "robustness_parameters.csv", index=False, float_format="%.6g")
    replicates.to_csv(tables / "robustness_replicates.csv", index=False, float_format="%.6g")

    viz.save(viz.plot_metric_vs_level(
        acc_a, "miss_prob", "accuracy_aic", "Missed-blink probability q",
        "Exact family recovery (AIC)",
        f"Robustness to missed blinks (n = {args.n}, 95% Wilson band)"),
        figures / "robustness_missed_blinks.png")
    viz.save(viz.plot_bias_vs_level(
        par_a, "miss_prob", "Missed-blink probability q",
        f"Parameter bias vs original generating values under missed blinks (n = {args.n})"),
        figures / "robustness_missed_blinks_bias.png")
    viz.save(viz.plot_metric_vs_level(
        acc_b, "sigma", "accuracy_aic", "Timestamp noise SD (s)", "Exact family recovery (AIC)",
        f"Robustness to timestamp noise (n = {args.n}, 95% Wilson band)"),
        figures / "robustness_timestamp_noise.png")
    viz.save(viz.plot_criterion_comparison(acc_c), figures / "robustness_sample_size.png")
    viz.save(viz.plot_selection_frequencies(acc_d), figures / "robustness_overlap.png")

    print("\n[A] Exact recovery vs missed-blink probability:")
    print(acc_a.pivot_table(index=["track", "true_family"], columns="miss_prob",
                            values="accuracy_aic", sort=False).round(2).to_string())
    print("\n[A] Most common wrong pick at q = 0.3:")
    print(acc_a[acc_a["miss_prob"] == 0.3][["true_family", "accuracy_aic", "most_common_wrong"]]
          .to_string(index=False))
    print("\n[B] Exact recovery vs timestamp noise SD (s):")
    print(acc_b.pivot_table(index="true_family", columns="sigma", values="accuracy_aic",
                            sort=False).round(2).to_string())
    print("\n[C] AIC / BIC exact recovery vs n:")
    for crit in ("accuracy_aic", "accuracy_bic"):
        print(f"  {crit}")
        print(acc_c.pivot_table(index="true_family", columns="n", values=crit, sort=False)
              .round(2).to_string())
    print("\n[D] Overlap regimes: exact / equivalent-family recovery vs n:")
    print(acc_d.pivot_table(index="scenario", columns="n",
                            values=["accuracy_aic", "equivalent_accuracy_aic"], sort=False)
          .round(2).to_string())
    print(f"\nTotal {time.time() - start:.0f}s. Wrote tables to {tables}, figures to {figures}")


if __name__ == "__main__":
    main()
