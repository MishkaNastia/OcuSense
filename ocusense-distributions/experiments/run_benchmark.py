"""Monte Carlo model-selection benchmark with held-out validation.

For every primary scenario and sample size: generate data, fit all candidates
of the same track, select by AIC (AICc/BIC recorded too), and on a random
70/30 split compare training-AIC choice with held-out log-likelihood.

Outputs (under --out/tables and --out/figures):
    benchmark_accuracy.csv            per scenario x n: accuracy, CI, selection freqs
    benchmark_accuracy_by_family.csv  pooled over scenarios of the same family
    confusion_matrices.csv            long format, per track x n
    parameter_recovery.csv            bias / error of the true family's estimates
    parameter_recovery_raw.csv        every estimate
    fit_status_rates.csv              failure and boundary rates per candidate
    benchmark_replicates.csv          one row per simulated dataset
    benchmark_fits.csv                one row per candidate fit
    heldout_results.csv               AIC vs held-out agreement summary
    heldout_fits.csv                  per-candidate train/test log-likelihoods
    benchmark_*.png                   figures

Examples:
    python experiments/run_benchmark.py --smoke
    python experiments/run_benchmark.py --reps 100 --n-jobs 8
    python experiments/run_benchmark.py --reps 1000 --sample-sizes 30 100 300
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd

from ocusense import visualization as viz
from ocusense.evaluation import (
    confusion_matrix,
    fit_status_rates,
    heldout_summary,
    parameter_recovery_summary,
    run_benchmark,
    summarize_accuracy,
)
from ocusense.synthetic import PRIMARY_SCENARIOS, default_scenarios, get_scenario

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--sample-sizes", type=int, nargs="+", default=[30, 100, 300, 1000, 5000])
    parser.add_argument("--scenarios", nargs="+", default=None,
                        help="scenario names (default: all primary scenarios)")
    parser.add_argument("--seed", type=int, default=20240601)
    parser.add_argument("--n-jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--heldout-fraction", type=float, default=0.3)
    parser.add_argument("--no-heldout", action="store_true")
    parser.add_argument("--smoke", action="store_true",
                        help="quick run: 10 reps, n in {30, 100, 300}, default scenarios")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    return parser.parse_args()


def write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6g")


def main() -> None:
    args = parse_args()
    if args.smoke:
        args.reps, args.sample_sizes = 10, [30, 100, 300]
        scenarios = list(default_scenarios())
    elif args.scenarios:
        scenarios = [get_scenario(name) for name in args.scenarios]
    else:
        scenarios = list(PRIMARY_SCENARIOS)
    tables, figures = args.out / "tables", args.out / "figures"

    start = time.time()
    res = run_benchmark(scenarios, args.sample_sizes, args.reps, args.seed, args.n_jobs,
                        None if args.no_heldout else args.heldout_fraction)
    print(f"{len(res.replicates)} datasets, {len(res.fits)} fits in {time.time() - start:.0f}s "
          f"({args.n_jobs} workers)")

    accuracy = summarize_accuracy(res.replicates)
    by_family = summarize_accuracy(res.replicates, ["track", "true_family", "n"])
    recovery = parameter_recovery_summary(res.params)
    status = fit_status_rates(res.fits, ["true_family", "candidate", "n"])

    matrices = {}
    long_cm = []
    for track in ("count", "interval"):
        for n in args.sample_sizes:
            if not ((res.replicates["track"] == track) & (res.replicates["n"] == n)).any():
                continue
            cm = confusion_matrix(res.replicates, track, n)
            matrices[(track, n)] = cm
            stacked = cm.stack().rename("share").reset_index()
            stacked.insert(0, "track", track)
            stacked.insert(1, "n", n)
            long_cm.append(stacked)

    write(accuracy, tables / "benchmark_accuracy.csv")
    write(by_family, tables / "benchmark_accuracy_by_family.csv")
    write(pd.concat(long_cm), tables / "confusion_matrices.csv")
    write(recovery, tables / "parameter_recovery.csv")
    write(res.params, tables / "parameter_recovery_raw.csv")
    write(status, tables / "fit_status_rates.csv")
    write(res.replicates, tables / "benchmark_replicates.csv")
    write(res.fits, tables / "benchmark_fits.csv")

    shown_n = sorted({args.sample_sizes[0], args.sample_sizes[len(args.sample_sizes) // 2],
                      args.sample_sizes[-1]})
    viz.save(viz.plot_confusion_matrices({k: v for k, v in matrices.items() if k[1] in shown_n}),
             figures / "benchmark_confusion_matrices.png")
    viz.save(viz.plot_accuracy_vs_n(by_family), figures / "benchmark_accuracy_vs_n.png")
    defaults = {s.name for s in default_scenarios()}
    viz.save(viz.plot_parameter_recovery_benchmark(recovery[recovery["scenario"].isin(defaults)]),
             figures / "benchmark_parameter_recovery.png")

    if not res.heldout.empty:
        ho = heldout_summary(res.heldout)
        write(ho, tables / "heldout_results.csv")
        write(res.heldout, tables / "heldout_fits.csv")
        viz.save(viz.plot_heldout(ho, res.heldout, scatter_n=shown_n[len(shown_n) // 2]),
                 figures / "benchmark_heldout.png")
        print("\nHeld-out: training-AIC choice exactly best on test / within 1 LL unit of best:")
        print(ho.groupby(["track", "n"])[["agreement_rate", "near_best_rate"]].mean()
              .round(3).to_string())

    pd.set_option("display.width", 200)
    print("\nExact family recovery by AIC (pooled over scenarios of each family):")
    print(by_family.pivot_table(index=["track", "true_family"], columns="n",
                                values="accuracy_aic", sort=False).round(3).to_string())
    print("\nFit failure rate by candidate (all scenarios):")
    print(status.groupby(["candidate", "n"])["failure_rate"].mean().unstack().round(4).to_string())
    print(f"\nWrote tables to {tables} and figures to {figures}")


if __name__ == "__main__":
    main()
