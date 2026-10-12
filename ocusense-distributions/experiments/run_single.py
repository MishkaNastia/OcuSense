"""Fit every candidate to one synthetic dataset per track and plot the results.

Outputs (under --out):
    tables/model_selection_results.csv     ranked candidates for each dataset
    tables/single_parameter_recovery.csv   true vs estimated (+ bootstrap CI)
    figures/single_<track>_fit.png         data with fitted and true curves
    figures/single_<track>_aic.png         AIC / ΔAIC comparison
    figures/single_<track>_diagnostics.png Q-Q diagnostics
    figures/single_<track>_recovery.png    parameter recovery

Example:
    python experiments/run_single.py --n 500 --seed 2024
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ocusense import visualization as viz
from ocusense.distributions import families_for_track
from ocusense.evaluation import parametric_bootstrap
from ocusense.selection import best_model, fit_candidates, rank_fits
from ocusense.synthetic import get_scenario

ROOT = Path(__file__).resolve().parents[1]


def run_one(scenario_name: str, n: int, seed: int, n_boot: int, out: Path) -> pd.DataFrame:
    scenario = get_scenario(scenario_name)
    data = scenario.generate(n, seed)
    fits = fit_candidates(data, families_for_track(scenario.track))
    table = rank_fits(fits)
    track = scenario.track
    label = f"{scenario.name}, n = {n}, seed = {seed}"

    viz.save(viz.plot_fitted_distributions(data, fits, scenario.distribution, scenario.params,
                                           f"Observed data and fitted models ({label})"),
             out / "figures" / f"single_{track}_fit.png")
    viz.save(viz.plot_aic_comparison(table, f"AIC comparison ({label})"),
             out / "figures" / f"single_{track}_aic.png")
    viz.save(viz.plot_diagnostics(data, fits, f"Q-Q diagnostics ({label})"),
             out / "figures" / f"single_{track}_diagnostics.png")

    true_fit = next(f for f in fits if f.distribution == scenario.distribution)
    recovery = pd.DataFrame()
    if true_fit.success:
        recovery = parametric_bootstrap(true_fit, n_boot=n_boot, seed=seed)
        recovery.insert(0, "scenario", scenario.name)
        recovery.insert(3, "true_value", recovery["parameter"].map(scenario.params))
        viz.save(viz.plot_parameter_recovery_single(
            recovery, f"Parameter recovery, {scenario.distribution} ({label})"),
            out / "figures" / f"single_{track}_recovery.png")

    print(f"\n=== {label}: true = {scenario.distribution}, AIC selects {best_model(table)} ===")
    show = table[["rank", "distribution", "log_likelihood", "k", "aic", "aicc", "bic",
                  "delta_aic", "akaike_weight", "status"]]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    for _, row in table[table["status"] != "ok"].iterrows():
        print(f"  note [{row['distribution']}]: {row['message']}")
    if not recovery.empty:
        print(recovery[["parameter", "true_value", "estimate", "ci_low", "ci_high"]]
              .to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    table.insert(0, "scenario", scenario.name)
    table.insert(1, "true_family", scenario.distribution)
    table.insert(2, "seed", seed)
    return table, recovery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count-scenario", default="negbin_m15_r10")
    parser.add_argument("--interval-scenario", default="lognormal_m1.0_s0.4")
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2024)
    parser.add_argument("--n-boot", type=int, default=200)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()

    tables, recoveries = zip(*(run_one(name, args.n, args.seed, args.n_boot, args.out)
                               for name in (args.count_scenario, args.interval_scenario)))
    (args.out / "tables").mkdir(parents=True, exist_ok=True)
    pd.concat(tables).to_csv(args.out / "tables" / "model_selection_results.csv", index=False)
    pd.concat(recoveries).to_csv(args.out / "tables" / "single_parameter_recovery.csv",
                                 index=False)
    print(f"\nWrote tables and figures under {args.out}")


if __name__ == "__main__":
    main()
