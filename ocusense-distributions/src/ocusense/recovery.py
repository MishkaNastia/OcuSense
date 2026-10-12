"""Statistical recovery benchmark: empirical accuracy with PASS/FAIL floors.

This module *measures* how often the pipeline recovers the generating
distribution and its parameters. Success on every dataset is never expected.
Recovery percentages are reported for every scenario and sample size. Only a
small set of pre-declared, theory-based floors produce PASS/FAIL; everything
else is reported for information.

Floors (see :class:`Thresholds`) and why they are set where they are:

* **BIC selection at large n.** BIC is consistent, so recovery must approach
  100%: at least 95% at n = 5000 and at least 75% at n = 1000.
* **AIC selection at n = 5000: at least 70%.** AIC is not consistent for
  nested models. With a true simpler model and two nested competitors
  (Exponential vs Gamma/Weibull), its asymptotic recovery is about 0.80. The
  floor sits about 3 Monte Carlo SEs below that for 100 datasets.
* **Parameter accuracy of the true family.** Median |relative error| at most
  10% at n = 5000 and at most 20% at n = 1000, since MLE error shrinks like 1/sqrt(n).
* **Count noise, fitted mean.** Every count-family MLE reproduces the sample
  mean exactly, and the observed mean under misses (q) and false positives
  (nu) is (1 - q) E[X] + nu. So the fitted mean must be unbiased for it: the
  average over datasets must be within 1% for n >= 1000. With 100 datasets,
  the Monte Carlo SE of that average is at most about 0.2%, so the floor sits
  about 5 SE out. An individual dataset's error is ordinary sampling noise and
  is reported, not graded.
* **Count noise, family-preserving conditions** (pure thinning; Poisson with
  false positives): the same selection floors as clean data, and parameter
  floors measured against the theoretically transformed parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import pandas as pd

from .distributions import families_for_track, get_distribution
from .evaluation import BenchmarkResults, run_blocks
from .noise import CountDetectionNoise, noisy_count_mean, noisy_count_params
from .synthetic import PRIMARY_SCENARIOS, Scenario, get_scenario

SAMPLE_SIZES = (30, 60, 100, 300, 1000, 5000)
# (miss probability q, false positives per 60 s window nu)
NOISE_CONDITIONS = ((0.1, 0.0), (0.2, 0.0), (0.3, 0.0),
                    (0.0, 0.5), (0.0, 1.0), (0.0, 3.0),
                    (0.1, 1.0), (0.2, 3.0))
CRITERIA = ("aic", "bic")


@dataclass(frozen=True)
class Thresholds:
    """Pre-declared PASS/FAIL floors (sample size -> limit)."""

    selection: dict[str, dict[int, float]] = field(default_factory=lambda: {
        "bic": {1000: 0.75, 5000: 0.95},
        "aic": {5000: 0.70},
    })
    param_median_abs_rel_error: dict[int, float] = field(
        default_factory=lambda: {1000: 0.20, 5000: 0.10})
    noise_mean_abs_rel_bias: dict[int, float] = field(
        default_factory=lambda: {1000: 0.01, 5000: 0.01})


@dataclass(frozen=True)
class RecoveryConfig:
    """Everything that defines one benchmark run."""

    scenarios: tuple[Scenario, ...] = PRIMARY_SCENARIOS
    sample_sizes: tuple[int, ...] = SAMPLE_SIZES
    n_reps: int = 100
    base_seed: int = 20251010
    n_jobs: int = 1
    noise_conditions: tuple[tuple[float, float], ...] = NOISE_CONDITIONS
    noise_sample_sizes: tuple[int, ...] = SAMPLE_SIZES
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def count_scenarios(self) -> tuple[Scenario, ...]:
        return tuple(s for s in self.scenarios if s.track == "count")


@dataclass
class RecoveryResults:
    clean: BenchmarkResults
    noise: BenchmarkResults | None


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_recovery(config: RecoveryConfig) -> RecoveryResults:
    """Generate, fit and select for every scenario x n (x noise condition)."""
    clean_tasks = [{"scenario": s, "n": n, "n_reps": config.n_reps, "base_seed": config.base_seed}
                   for s in config.scenarios for n in config.sample_sizes]
    clean = run_blocks(clean_tasks, config.n_jobs)
    noise = None
    if config.noise_conditions and config.count_scenarios:
        noise_tasks = [
            {"scenario": s, "n": n, "n_reps": config.n_reps, "base_seed": config.base_seed,
             "data_fn": CountDetectionNoise(q, nu),
             "condition": {"miss_prob": q, "fp_rate": nu},
             # Parameter errors are measured against the transformed parameters
             # when the family survives the noise, else against the originals.
             "reference_params": noisy_count_params(s.distribution, s.params, q, nu) or s.params}
            for s in config.count_scenarios for (q, nu) in config.noise_conditions
            for n in config.noise_sample_sizes
        ]
        noise = run_blocks(noise_tasks, config.n_jobs)
    return RecoveryResults(clean, noise)


def family_preserved(distribution: str, miss_prob: float, fp_rate: float) -> bool:
    """Whether the observed counts still belong to the generating family."""
    placeholder = {p.name: 0.5 for p in get_distribution(distribution).params}
    return noisy_count_params(distribution, placeholder, miss_prob, fp_rate) is not None


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def selection_summary(replicates: pd.DataFrame, group_cols: Sequence[str]) -> pd.DataFrame:
    """AIC and BIC accuracy plus the most common wrong pick per group."""
    rows = []
    for keys, g in replicates.groupby(list(group_cols), sort=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(group_cols, keys))
        row["n_datasets"] = len(g)
        for c in CRITERIA:
            row[f"{c}_accuracy"] = float(g[f"correct_{c}"].mean())
            wrong = g.loc[~g[f"correct_{c}"], f"selected_{c}"].value_counts()
            row[f"{c}_top_confusion"] = wrong.index[0] if len(wrong) else ""
            row[f"{c}_top_confusion_share"] = wrong.iloc[0] / len(g) if len(wrong) else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def confusion_table(replicates: pd.DataFrame, criterion: str) -> pd.DataFrame:
    """Share of each (true family -> selected family) pair, per track and n."""
    g = replicates.groupby(["track", "n", "true_family", f"selected_{criterion}"], sort=False)
    out = g.size().rename("count").reset_index()
    totals = out.groupby(["track", "n", "true_family"])["count"].transform("sum")
    out["share"] = out["count"] / totals
    return out.rename(columns={f"selected_{criterion}": "selected"})


def parameter_summary(params: pd.DataFrame, group_cols: Sequence[str]) -> pd.DataFrame:
    """Median |relative error|, median relative bias and RMSE of the true family's fit."""
    g = params.groupby(list(group_cols), sort=False)
    return g.agg(
        true_value=("true_value", "first"),
        n_fits=("estimate", "size"),
        median_abs_rel_error=("rel_error", lambda e: float(e.abs().median())),
        median_rel_bias=("rel_error", "median"),
        rmse=("error", lambda e: float(np.sqrt(np.mean(e ** 2)))),
    ).reset_index()


def fitted_mean_errors(noise: BenchmarkResults) -> pd.DataFrame:
    """Per dataset: relative error of the fitted model mean vs the theoretical observed mean."""
    keys = ["scenario", "true_family", "n", "rep", "miss_prob", "fp_rate"]
    wide = noise.params.pivot_table(index=keys, columns="parameter", values="estimate",
                                    aggfunc="first").reset_index()
    rows = []
    for _, row in wide.iterrows():
        scenario = get_scenario(row["scenario"])
        spec = get_distribution(scenario.distribution)
        fitted = spec.mean({p: row[p] for p in spec.param_names})
        expected = noisy_count_mean(scenario.distribution, scenario.params, row["miss_prob"],
                                    row["fp_rate"])
        rows.append({**{k: row[k] for k in keys}, "fitted_mean": fitted,
                     "expected_mean": expected, "rel_error": fitted / expected - 1})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# PASS / FAIL checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckSpec:
    """One pre-declared threshold check (known before any data are generated)."""

    kind: str  # selection | parameter | noise_selection | noise_parameter | noise_mean
    scenario: str
    n: int
    threshold: float
    criterion: str = ""
    parameter: str = ""
    miss_prob: float = 0.0
    fp_rate: float = 0.0

    @property
    def name(self) -> str:
        parts = [self.kind, self.scenario, f"n={self.n}"]
        if self.kind.startswith("noise"):
            parts.append(f"q={self.miss_prob:g},fp={self.fp_rate:g}")
        if self.criterion:
            parts.append(self.criterion.upper())
        if self.parameter:
            parts.append(self.parameter)
        return " ".join(parts)

    @property
    def higher_is_better(self) -> bool:
        return self.kind in ("selection", "noise_selection")


@dataclass(frozen=True)
class CheckResult:
    spec: CheckSpec
    value: float
    n_datasets: int

    @property
    def passed(self) -> bool:
        if not np.isfinite(self.value):
            return False
        if self.spec.higher_is_better:
            return self.value >= self.spec.threshold
        return self.value <= self.spec.threshold

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def line(self) -> str:
        op = ">=" if self.spec.higher_is_better else "<="
        what = {"selection": "recovery", "noise_selection": "recovery",
                "noise_mean": "|bias of mean|"}.get(self.spec.kind, "median |rel err|")
        return (f"{self.status}  {self.spec.name:<58} {what} {self.value:6.1%}  "
                f"(floor {op} {self.spec.threshold:.0%}, {self.n_datasets} datasets)")


def plan_checks(config: RecoveryConfig) -> list[CheckSpec]:
    """All PASS/FAIL checks implied by the config and its thresholds."""
    th = config.thresholds
    specs: list[CheckSpec] = []
    for s in config.scenarios:
        for crit, by_n in th.selection.items():
            specs += [CheckSpec("selection", s.name, n, lim, criterion=crit)
                      for n, lim in by_n.items() if n in config.sample_sizes]
        for n, lim in th.param_median_abs_rel_error.items():
            if n in config.sample_sizes:
                specs += [CheckSpec("parameter", s.name, n, lim, parameter=p) for p in s.params]
    for s in config.count_scenarios:
        for q, nu in config.noise_conditions:
            expected = noisy_count_params(s.distribution, s.params, q, nu)
            for n, lim in th.noise_mean_abs_rel_bias.items():
                if n in config.noise_sample_sizes:
                    specs.append(CheckSpec("noise_mean", s.name, n, lim, miss_prob=q, fp_rate=nu))
            if expected is None:
                continue  # family not preserved: selection is reported, not graded
            for crit, by_n in th.selection.items():
                specs += [CheckSpec("noise_selection", s.name, n, lim, criterion=crit,
                                    miss_prob=q, fp_rate=nu)
                          for n, lim in by_n.items() if n in config.noise_sample_sizes]
            for n, lim in th.param_median_abs_rel_error.items():
                if n in config.noise_sample_sizes:
                    specs += [CheckSpec("noise_parameter", s.name, n, lim, parameter=p,
                                        miss_prob=q, fp_rate=nu) for p in expected]
    return specs


def evaluate_check(spec: CheckSpec, results: RecoveryResults,
                   _cache: dict | None = None) -> CheckResult:
    """Compute the statistic a check refers to and compare it with its floor."""
    noisy = spec.kind.startswith("noise")
    data = results.noise if noisy else results.clean
    if data is None:
        raise ValueError("noise results missing")

    def subset(frame: pd.DataFrame) -> pd.DataFrame:
        m = (frame["scenario"] == spec.scenario) & (frame["n"] == spec.n)
        if noisy:
            m &= np.isclose(frame["miss_prob"], spec.miss_prob)
            m &= np.isclose(frame["fp_rate"], spec.fp_rate)
        return frame[m]

    if spec.kind in ("selection", "noise_selection"):
        reps = subset(data.replicates)
        return CheckResult(spec, float(reps[f"correct_{spec.criterion}"].mean()), len(reps))
    if spec.kind in ("parameter", "noise_parameter"):
        rows = subset(data.params)
        rows = rows[rows["parameter"] == spec.parameter]
        value = float(rows["rel_error"].abs().median()) if len(rows) else float("nan")
        return CheckResult(spec, value, len(rows))
    if spec.kind == "noise_mean":
        cache = _cache if _cache is not None else {}
        if "mean_errors" not in cache:
            cache["mean_errors"] = fitted_mean_errors(results.noise)
        rows = subset(cache["mean_errors"])
        value = (abs(rows["fitted_mean"].mean() / rows["expected_mean"].iloc[0] - 1)
                 if len(rows) else float("nan"))
        return CheckResult(spec, value, len(rows))
    raise ValueError(f"unknown check kind {spec.kind!r}")


def evaluate_all(config: RecoveryConfig, results: RecoveryResults) -> list[CheckResult]:
    cache: dict = {}
    return [evaluate_check(spec, results, cache) for spec in plan_checks(config)]


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}" if np.isfinite(x) else "  n/a"


def _grid(df: pd.DataFrame, index: list[str], value: str, fmt=_pct, sort: bool = False) -> str:
    table = df.pivot_table(index=index, columns="n", values=value, aggfunc="first", sort=sort)
    return table.map(fmt).to_string()


def _confusion_grid(conf: pd.DataFrame, track: str, min_share: float) -> str:
    """Rows: true family; columns: n; cell: most frequent wrong pick and its share."""
    sub = conf[(conf["track"] == track) & (conf["selected"] != conf["true_family"])]
    lines = []
    for family in families_for_track(track):
        cells = []
        for n in sorted(conf["n"].unique()):
            g = sub[(sub["true_family"] == family) & (sub["n"] == n)].sort_values("share")
            if len(g) and g["share"].iloc[-1] >= min_share:
                cells.append(f"{g['selected'].iloc[-1]} {100 * g['share'].iloc[-1]:.0f}%")
            else:
                cells.append("-")
        lines.append((family, cells))
    sizes = sorted(conf["n"].unique())
    width = 15
    header = f"{'true family':<12}" + "".join(f"{'n=' + str(n):>{width}}" for n in sizes)
    body = [f"{fam:<12}" + "".join(f"{c:>{width}}" for c in cells) for fam, cells in lines]
    return "\n".join([header] + body)


def format_report(config: RecoveryConfig, results: RecoveryResults,
                  checks: Sequence[CheckResult], verbose: bool = False) -> str:
    out: list[str] = []
    rule = "=" * 100

    def section(title: str) -> None:
        out.extend(["", rule, title, rule])

    reps = results.clean.replicates
    section(f"1. DISTRIBUTION RECOVERY, clean data ({config.n_reps} datasets per cell)")
    by_scenario = selection_summary(reps, ["track", "scenario", "n"])
    for crit in CRITERIA:
        out.append(f"\n{crit.upper()} recovery (% of datasets where the true family was selected)")
        out.append(_grid(by_scenario, ["track", "scenario"], f"{crit}_accuracy"))
    by_family = selection_summary(reps, ["track", "true_family", "n"])
    out.append("\nPooled by family (AIC / BIC %)")
    by_family["cell"] = [f"{100 * a:3.0f}/{100 * b:3.0f}"
                         for a, b in zip(by_family["aic_accuracy"], by_family["bic_accuracy"])]
    out.append(_grid(by_family, ["track", "true_family"], "cell", fmt=str))

    section("2. MOST COMMON CONFUSIONS (most frequent wrong pick, share of that family's datasets)")
    for crit in CRITERIA:
        conf = confusion_table(reps, crit)
        for track in ("count", "interval"):
            if (conf["track"] == track).any():
                out.append(f"\n{crit.upper()}, {track} track ('-' = no wrong pick >= 1%)")
                out.append(_confusion_grid(conf, track, 0.01))

    section("3. PARAMETER ESTIMATION (true family's MLE): median |relative error| %")
    par = parameter_summary(results.clean.params, ["scenario", "parameter", "n"])
    out.append(_grid(par, ["scenario", "parameter"], "median_abs_rel_error"))
    big_n = max(config.sample_sizes)
    bias = par[par["n"] == big_n][["scenario", "parameter", "median_rel_bias"]]
    worst = bias.reindex(bias["median_rel_bias"].abs().sort_values(ascending=False).index).head(5)
    out.append(f"\nLargest median relative bias at n={big_n}: " + "; ".join(
        f"{r.scenario}.{r.parameter} {100 * r.median_rel_bias:+.1f}%" for r in worst.itertuples()))
    small_n = min(config.sample_sizes)
    small = par[par["n"] == small_n][["scenario", "parameter", "median_rel_bias"]]
    worst = small.reindex(small["median_rel_bias"].abs().sort_values(ascending=False).index).head(5)
    out.append(f"Largest median relative bias at n={small_n}: " + "; ".join(
        f"{r.scenario}.{r.parameter} {100 * r.median_rel_bias:+.1f}%" for r in worst.itertuples()))

    if results.noise is not None:
        noise = results.noise
        section("4. COUNT DATA WITH DETECTION NOISE: observed = Binomial(X, 1-q) + Poisson(fp)")
        summ = selection_summary(noise.replicates, ["true_family", "miss_prob", "fp_rate", "n"])
        summ["family kept?"] = ["yes" if family_preserved(f, q, nu) else "no"
                                for f, q, nu in zip(summ["true_family"], summ["miss_prob"],
                                                    summ["fp_rate"])]
        summ["cell"] = [f"{100 * a:3.0f}/{100 * b:3.0f}"
                        for a, b in zip(summ["aic_accuracy"], summ["bic_accuracy"])]
        out.append("Recovery pooled over the 3 scenarios of each family (AIC / BIC %). Clean "
                   "baseline is in section 1.")
        out.append(_grid(summ, ["true_family", "miss_prob", "fp_rate", "family kept?"], "cell",
                         fmt=str, sort=True))
        mid = [n for n in (300, 1000) if n in config.noise_sample_sizes] or [
            max(config.noise_sample_sizes)]
        top = summ[summ["n"] == mid[-1]]
        out.append(f"\nMost common wrong pick (BIC) at n={mid[-1]} (shown if >= 1%):")
        for r in top.itertuples():
            if r.bic_top_confusion and r.bic_top_confusion_share >= 0.01:
                out.append(f"  {r.true_family:<8} q={r.miss_prob:<4g} fp={r.fp_rate:<4g} -> "
                           f"{r.bic_top_confusion} {100 * r.bic_top_confusion_share:.0f}%")
        means = fitted_mean_errors(noise)
        mtab = means.groupby(["true_family", "miss_prob", "fp_rate", "n"])["rel_error"] \
            .mean().rename("bias").reset_index()
        out.append("\nFitted mean vs theoretical observed mean (1-q)E[X]+fp: average relative "
                   "error % (bias; should be ~0)")
        out.append(_grid(mtab, ["true_family", "miss_prob", "fp_rate"], "bias",
                         fmt=lambda v: f"{100 * v:+5.2f}", sort=True))

    section("5. PASS/FAIL CHECKS (pre-declared floors; everything above is informational)")
    groups: dict[str, list[CheckResult]] = {}
    for c in checks:
        groups.setdefault(c.spec.kind, []).append(c)
    for kind, items in groups.items():
        n_pass = sum(c.passed for c in items)
        out.append(f"{'PASS' if n_pass == len(items) else 'FAIL'}  {kind:<16} "
                   f"{n_pass}/{len(items)} checks passed")
    shown = [c for c in checks if verbose or not c.passed]
    if shown:
        out.append("\n" + ("All checks:" if verbose else "Failed checks:"))
        out.extend("  " + c.line() for c in shown)
    n_fail = sum(not c.passed for c in checks)
    out.extend(["", f"OVERALL: {'PASS' if n_fail == 0 else 'FAIL'}  "
                    f"({len(checks) - n_fail}/{len(checks)} checks passed)"])
    return "\n".join(out)
