"""Statistical recovery benchmark: console report with PASS/FAIL floors.

Generates N datasets per scenario x sample size (and per count-noise
condition), fits every candidate, selects by AIC and BIC, and reports:

  1. recovery % per scenario and n (AIC and BIC separately)
  2. the most common confusions
  3. parameter-estimation error of the true family
  4. count data with missed detections and Poisson false positives
  5. PASS/FAIL against pre-declared floors (see ocusense/recovery.py)

The exit code is 0 if every check passes and 1 otherwise.

Examples:
    python benchmarks/run_recovery_benchmark.py                 # 100 datasets per cell
    python benchmarks/run_recovery_benchmark.py --reps 20       # quick look
    python benchmarks/run_recovery_benchmark.py --verbose       # print every check
    python benchmarks/run_recovery_benchmark.py --save-csv out/ # also write CSV tables
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from ocusense.recovery import (
    NOISE_CONDITIONS,
    SAMPLE_SIZES,
    RecoveryConfig,
    confusion_table,
    evaluate_all,
    fitted_mean_errors,
    format_report,
    run_recovery,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=100, help="datasets per cell (default 100)")
    parser.add_argument("--sample-sizes", type=int, nargs="+", default=list(SAMPLE_SIZES))
    parser.add_argument("--noise-sample-sizes", type=int, nargs="+", default=None,
                        help="sample sizes for the count-noise runs (default: same as --sample-sizes)")
    parser.add_argument("--no-noise", action="store_true", help="skip the count-noise simulations")
    parser.add_argument("--seed", type=int, default=20251010)
    parser.add_argument("--n-jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--verbose", action="store_true", help="list every check, not only failures")
    parser.add_argument("--save-csv", type=Path, default=None, help="directory for CSV tables")
    args = parser.parse_args()

    config = RecoveryConfig(
        sample_sizes=tuple(args.sample_sizes),
        n_reps=args.reps,
        base_seed=args.seed,
        n_jobs=args.n_jobs,
        noise_conditions=() if args.no_noise else NOISE_CONDITIONS,
        noise_sample_sizes=tuple(args.noise_sample_sizes or args.sample_sizes),
    )
    if args.reps < 100:
        print(f"Note: {args.reps} datasets per cell. The floors are calibrated for 100; "
              "expect occasional FAILs from Monte Carlo noise alone.")
    start = time.time()
    results = run_recovery(config)
    checks = evaluate_all(config, results)
    n_datasets = len(results.clean.replicates) + (
        len(results.noise.replicates) if results.noise is not None else 0)
    print(format_report(config, results, checks, verbose=args.verbose))
    print(f"\n{n_datasets} datasets, {time.time() - start:.0f}s, {args.n_jobs} workers")

    if args.save_csv:
        args.save_csv.mkdir(parents=True, exist_ok=True)
        results.clean.replicates.to_csv(args.save_csv / "recovery_replicates.csv", index=False)
        results.clean.params.to_csv(args.save_csv / "recovery_parameters.csv", index=False)
        for crit in ("aic", "bic"):
            confusion_table(results.clean.replicates, crit).to_csv(
                args.save_csv / f"recovery_confusion_{crit}.csv", index=False)
        if results.noise is not None:
            results.noise.replicates.to_csv(args.save_csv / "noise_replicates.csv", index=False)
            results.noise.params.to_csv(args.save_csv / "noise_parameters.csv", index=False)
            fitted_mean_errors(results.noise).to_csv(args.save_csv / "noise_fitted_means.csv",
                                                    index=False)
        with open(args.save_csv / "checks.csv", "w") as fh:
            fh.write("status,check,value,threshold,n_datasets\n")
            for c in checks:
                fh.write(f"{c.status},{c.spec.name},{c.value:.6g},{c.spec.threshold},"
                         f"{c.n_datasets}\n")
        print(f"CSV tables written to {args.save_csv}")
    return 0 if all(c.passed for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
