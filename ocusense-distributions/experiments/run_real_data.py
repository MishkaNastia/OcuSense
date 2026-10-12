"""Test which candidate distribution best describes the real blinks in the Artwork Gallery dataset.

Reads ``../data`` (27 Pupil Labs recordings, participants P1-P3, see
``data/README.md``). Blink onsets come from ``blinks.csv``; recording length
comes from the first and last ``gaze.csv`` timestamps. Detections closer than
``--merge-ms`` (end of one to start of the next) are merged into one blink,
because the headset detector often splits a single blink into two rows a few
milliseconds apart.

Intervals are onset-to-onset and never span two recordings. Counts use
complete ``--window``-second windows within each recording. Each track is
tested per participant and pooled over all participants.

For every dataset three questions are answered:

1. Which candidate is best?  Lowest AIC.
2. Is it significantly better than the runner-up?  Likelihood-ratio test when
   the runner-up is nested in the best (or vice versa), Vuong test otherwise.
3. Does it actually fit?  Parametric-bootstrap Kolmogorov-Smirnov test: the
   KS distance to the fitted model is compared with the distances obtained by
   simulating from the fitted model and refitting (this accounts for the
   parameters being estimated from the same data). p < alpha rejects the fit.

Outputs (under --out):
    tables/real_verdicts.csv     one row per track x group: best, runner-up, tests, verdict
    tables/real_candidates.csv   every candidate: parameters, AIC, ΔAIC, weight, GOF p-value

Example:
    python experiments/run_real_data.py --merge-ms 100 --window 60 --n-boot 500
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from ocusense.distributions import COUNT_FAMILIES, INTERVAL_FAMILIES, get_distribution
from ocusense.fitting import FitResult, fit_distribution
from ocusense.noise import counts_from_timestamps, intervals_from_timestamps
from ocusense.selection import fit_candidates, rank_fits
from ocusense.synthetic import derive_seed

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "data"

# (simpler, larger) pairs where the simpler family is a special case of the larger.
NESTED = {
    ("poisson", "negbin"), ("poisson", "zip"), ("poisson", "zinb"),
    ("negbin", "zinb"), ("zip", "zinb"),
    ("exponential", "gamma"), ("exponential", "weibull"),
}


def load_recording(folder: Path, merge_ms: float) -> tuple[np.ndarray, float]:
    """Blink onsets (s since recording start, split blinks merged) and duration (s)."""
    gaze_ts = pd.read_csv(folder / "gaze.csv", usecols=["timestamp [ns]"])["timestamp [ns]"]
    t0, t1 = int(gaze_ts.iloc[0]), int(gaze_ts.iloc[-1])
    blinks = pd.read_csv(folder / "blinks.csv").sort_values("start timestamp [ns]")
    starts = blinks["start timestamp [ns]"].to_numpy(np.int64)
    ends = blinks["end timestamp [ns]"].to_numpy(np.int64)
    keep = np.ones(starts.size, dtype=bool)
    keep[1:] = (starts[1:] - ends[:-1]) / 1e6 >= merge_ms
    return (starts[keep] - t0) / 1e9, (t1 - t0) / 1e9


def ks_distance(x: np.ndarray, fit: FitResult) -> float:
    """Largest gap between the empirical CDF and the fitted CDF."""
    spec = get_distribution(fit.distribution)
    if fit.track == "interval":
        return float(stats.kstest(x, lambda v: spec.cdf(v, fit.params)).statistic)
    values, counts = np.unique(x, return_counts=True)
    ecdf = np.cumsum(counts) / x.size
    return float(np.max(np.abs(ecdf - spec.cdf(values.astype(float), fit.params))))


def bootstrap_gof(x: np.ndarray, fit: FitResult, n_boot: int, seed: int) -> tuple[float, float]:
    """KS distance and its parametric-bootstrap p-value (failed refits are skipped)."""
    spec = get_distribution(fit.distribution)
    observed = ks_distance(x, fit)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_boot):
        simulated = spec.sample(rng, fit.params, x.size)
        refit = fit_distribution(simulated, fit.distribution)
        if refit.success:
            null.append(ks_distance(simulated, refit))
    return observed, (np.sum(np.array(null) >= observed) + 1) / (len(null) + 1)


def compare(x: np.ndarray, best: FitResult, other: FitResult) -> tuple[str, float]:
    """Test best vs other: likelihood ratio if nested, Vuong otherwise. Returns (test, p)."""
    pair = (best.distribution, other.distribution)
    if pair in NESTED or pair[::-1] in NESTED:
        small, large = (best, other) if pair in NESTED else (other, best)
        lr = max(2 * (large.log_likelihood - small.log_likelihood), 0.0)
        return "likelihood ratio", float(stats.chi2.sf(lr, large.k - small.k))
    ll = [get_distribution(f.distribution).logprob(x.astype(float), f.params) for f in (best, other)]
    d = ll[0] - ll[1]
    if np.std(d) == 0:
        return "vuong", 1.0
    z = np.sqrt(x.size) * d.mean() / d.std(ddof=1)
    return "vuong", float(2 * stats.norm.sf(abs(z)))


def verdict(best: str, runner: str, test: str, p_compare: float, gof: dict[str, float],
            alpha: float) -> str:
    fits = [f for f, p in gof.items() if p >= alpha]
    fit_note = (f"{best} fits (GOF p = {gof[best]:.3f})" if gof[best] >= alpha
                else f"{best} does NOT fit (GOF p = {gof[best]:.3f})")
    others = f"; families not rejected: {', '.join(fits) or 'none'}"
    if test == "likelihood ratio" and (best, runner) in NESTED:
        return (f"{best}: simplest adequate model, extra {runner} parameters not needed "
                f"(LR p = {p_compare:.3f}); {fit_note}{others}")
    if p_compare < alpha:
        return f"{best}: significantly better than {runner} ({test} p = {p_compare:.3f}); {fit_note}{others}"
    return (f"{best} ~ {runner}: data cannot separate them ({test} p = {p_compare:.3f}); "
            f"{fit_note}{others}")


def test_dataset(x: np.ndarray, candidates, track: str, group: str, n_boot: int, seed: int,
                 alpha: float) -> tuple[dict, list[dict]]:
    fits = {f.distribution: f for f in fit_candidates(x, candidates)}
    table = rank_fits(list(fits.values()))
    ok = table[table["status"] != "failed"]
    best, runner = ok["distribution"].iloc[0], ok["distribution"].iloc[1]
    gof = {}
    rows = []
    for _, row in table.iterrows():
        name = row["distribution"]
        p = np.nan
        if fits[name].success:
            _, p = bootstrap_gof(x, fits[name], n_boot, derive_seed(seed, track, group, name))
            gof[name] = p
        rows.append({"track": track, "group": group, "n": x.size, "distribution": name,
                     "parameters": json.dumps({k: round(v, 6) for k, v in row["parameters"].items()}),
                     "aic": row["aic"], "delta_aic": row["delta_aic"],
                     "akaike_weight": row["akaike_weight"], "gof_p": p, "status": row["status"]})
    test, p_compare = compare(x, fits[best], fits[runner])
    summary = {"track": track, "group": group, "n": x.size, "best": best,
               "best_params": rows[0]["parameters"], "runner_up": runner,
               "delta_aic_runner_up": float(ok["delta_aic"].iloc[1]), "comparison_test": test,
               "comparison_p": p_compare, "best_gof_p": gof[best],
               "verdict": verdict(best, runner, test, p_compare, gof, alpha)}
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--merge-ms", type=float, default=100.0)
    parser.add_argument("--window", type=float, default=60.0)
    parser.add_argument("--n-boot", type=int, default=500)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=2024)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "real_data")
    args = parser.parse_args()

    assignment = json.loads((args.data / "patterns.json").read_text())["assignment"]
    intervals: dict[str, list[np.ndarray]] = {}
    counts: dict[str, list[np.ndarray]] = {}
    for rec, meta in sorted(assignment.items()):
        onsets, duration = load_recording(args.data / "recordings" / rec, args.merge_ms)
        intervals.setdefault(meta["source"], []).append(intervals_from_timestamps(onsets))
        if duration >= args.window:
            counts.setdefault(meta["source"], []).append(
                counts_from_timestamps(onsets, args.window, duration))

    summaries, candidates_rows = [], []
    for track, groups, candidates in (("interval", intervals, INTERVAL_FAMILIES),
                                      ("count", counts, COUNT_FAMILIES)):
        datasets = {g: np.concatenate(v) for g, v in sorted(groups.items())}
        datasets["ALL"] = np.concatenate(list(datasets.values()))
        for group, x in datasets.items():
            summary, rows = test_dataset(x, candidates, track, group, args.n_boot, args.seed,
                                         args.alpha)
            summaries.append(summary)
            candidates_rows.extend(rows)
            print(f"[{track:8} {group:3} n={x.size:3}] {summary['verdict']}")

    (args.out / "tables").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(args.out / "tables" / "real_verdicts.csv", index=False)
    pd.DataFrame(candidates_rows).to_csv(args.out / "tables" / "real_candidates.csv", index=False)
    print(f"\nmerge-ms = {args.merge_ms}, window = {args.window} s, n-boot = {args.n_boot}, "
          f"alpha = {args.alpha}. Wrote tables under {args.out}")


if __name__ == "__main__":
    main()
