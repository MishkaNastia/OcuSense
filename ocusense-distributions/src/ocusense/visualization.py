"""Figures for single-dataset fits and Monte Carlo summaries.

Conventions: each family keeps one color everywhere (color follows the
entity, never its rank); line style and marker give a second, non-color
identity channel; the true generating law is always a dashed ink curve;
grids are hairline and recessive; text stays in ink colors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter  # noqa: E402
from scipy import stats  # noqa: E402

from .distributions import families_for_track, get_distribution  # noqa: E402
from .fitting import FitResult  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8985"
GRID = "#e4e3df"
FILL = "#d9d8d3"

_SLOTS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
_STYLES = ("-", "--", "-.", ":")
_MARKERS = ("o", "s", "^", "D")
FAMILY_COLOR = {}
FAMILY_STYLE = {}
FAMILY_MARKER = {}
for _track in ("count", "interval"):
    for _i, _family in enumerate(families_for_track(_track)):
        FAMILY_COLOR[_family] = _SLOTS[_i]
        FAMILY_STYLE[_family] = _STYLES[_i]
        FAMILY_MARKER[_family] = _MARKERS[_i]

SEQUENTIAL = LinearSegmentedColormap.from_list(
    "blue_seq", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281", "#0d366b"])

LABELS = {
    "poisson": "Poisson", "negbin": "Negative binomial", "zip": "ZIP", "zinb": "ZINB",
    "lognormal": "Log-normal", "gamma": "Gamma", "weibull": "Weibull",
    "exponential": "Exponential",
}


def apply_style() -> None:
    """Quiet matplotlib defaults shared by every figure."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 9.5,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "font.size": 9.5,
    })


apply_style()


def save(fig: plt.Figure, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


SHORT_LABELS = {**LABELS, "negbin": "NB", "lognormal": "LogN", "exponential": "Exp"}


def _label(family: str) -> str:
    return LABELS.get(family, family)


def _short(family: str) -> str:
    return SHORT_LABELS.get(family, family)


def _percent_log_axis(ax: plt.Axes) -> None:
    """Readable percentage ticks on a logarithmic y axis."""
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2g}".rstrip("0") if v >= 1
                                               else f"{100 * v:.2g}%"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def _line_kw(family: str) -> dict:
    return {"color": FAMILY_COLOR[family], "linestyle": FAMILY_STYLE[family],
            "marker": FAMILY_MARKER[family], "label": _label(family)}


def _successful(fits: Sequence[FitResult]) -> list[FitResult]:
    return [f for f in fits if f.success]


# ---------------------------------------------------------------------------
# Single-dataset figures
# ---------------------------------------------------------------------------


def plot_fitted_distributions(data: np.ndarray, fits: Sequence[FitResult], true_family: str,
                              true_params: Mapping[str, float], title: str = "") -> plt.Figure:
    """Observed data with every fitted model and the true law (dashed)."""
    x = np.asarray(data, dtype=float)
    track = get_distribution(true_family).track
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    true_spec = get_distribution(true_family)
    if track == "count":
        support = np.arange(0, int(x.max() * 1.15) + 2)
        values, counts = np.unique(x, return_counts=True)
        ax.bar(values, counts / x.size, width=0.8, color=FILL, label="Observed (empirical PMF)",
               zorder=1)
        for fit in _successful(fits):
            pmf = np.exp(get_distribution(fit.distribution).logprob(support.astype(float), fit.params))
            ax.plot(support, pmf, markersize=3.5, linewidth=1.5, zorder=3,
                    **_line_kw(fit.distribution))
        true_pmf = np.exp(true_spec.logprob(support.astype(float), true_params))
        ax.plot(support, true_pmf, color=INK, linestyle=(0, (4, 3)), linewidth=1.6,
                label=f"True: {_label(true_family)}", zorder=4)
        ax.set_xlabel("Blinks per 60 s window")
        ax.set_ylabel("Probability")
    else:
        upper = np.quantile(x, 0.995)
        grid = np.linspace(upper / 400, upper, 400)
        ax.hist(x[x <= upper], bins=40, density=True, color=FILL, label="Observed (histogram)",
                zorder=1)
        for fit in _successful(fits):
            pdf = np.exp(get_distribution(fit.distribution).logprob(grid, fit.params))
            ax.plot(grid, pdf, markevery=40, markersize=5, zorder=3, **_line_kw(fit.distribution))
        ax.plot(grid, np.exp(true_spec.logprob(grid, true_params)), color=INK,
                linestyle=(0, (4, 3)), linewidth=1.6, label=f"True: {_label(true_family)}", zorder=4)
        ax.set_xlabel("Interblink interval (s)")
        ax.set_ylabel("Density")
    ax.set_title(title or f"Fitted distributions (n = {x.size})", loc="left")
    ax.legend(loc="upper right")
    return fig


def plot_aic_comparison(table: pd.DataFrame, title: str = "") -> plt.Figure:
    """ΔAIC per successfully fitted candidate; best model highlighted."""
    ok = table[table["status"] != "failed"].sort_values("aic", ascending=False)
    fig, ax = plt.subplots(figsize=(7.5, 0.6 * len(ok) + 1.4))
    best = ok["aic"].idxmin()
    y = np.arange(len(ok))
    colors = [FAMILY_COLOR[d] if i == best else FILL for i, d in zip(ok.index, ok["distribution"])]
    ax.barh(y, ok["delta_aic"], height=0.45, color=colors, zorder=2)
    ax.scatter([0], [y[list(ok.index).index(best)]], s=60, color=FAMILY_COLOR[ok.loc[best, "distribution"]],
               edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.set_xscale("symlog", linthresh=2)
    ax.set_xlim(left=-0.5, right=max(10.0, ok["delta_aic"].max() * 4))
    ax.set_yticks(y, [_label(d) for d in ok["distribution"]])
    ax.grid(axis="y", visible=False)
    for yi, (_, row) in zip(y, ok.iterrows()):
        tag = "lowest AIC" if row.name == best else f"ΔAIC {row['delta_aic']:.1f}"
        ax.text(max(row["delta_aic"], 0) * 1.15 + 0.15, yi,
                f"  AIC {row['aic']:.1f}  ·  {tag}  ·  w = {row['akaike_weight']:.2f}",
                va="center", fontsize=8.5, color=INK_2)
    ax.axvline(2, color=MUTED, linewidth=0.8, zorder=1)
    ax.text(2, -0.55, " ΔAIC = 2", color=MUTED, fontsize=8, va="center")
    ax.set_ylim(-0.75, len(ok) - 0.5)
    ax.set_xlabel("ΔAIC relative to the best candidate (symlog scale)")
    ax.set_title(title or "AIC comparison", loc="left")
    return fig


def randomized_quantile_residuals(x: np.ndarray, family: str, params: Mapping[str, float],
                                  seed: int = 0) -> np.ndarray:
    """Dunn-Smyth randomized quantile residuals for discrete data.

    For a correct model they are exactly standard normal, which makes a
    normal Q-Q plot valid despite the discreteness of the counts.
    """
    spec = get_distribution(family)
    x = np.asarray(x, dtype=float)
    upper = spec.cdf(x, params)
    lower = np.where(x > 0, spec.cdf(x - 1, params), 0.0)
    u = lower + np.random.default_rng(seed).random(x.size) * (upper - lower)
    return stats.norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))


def plot_diagnostics(data: np.ndarray, fits: Sequence[FitResult], title: str = "") -> plt.Figure:
    """Q-Q diagnostics, one panel per successful candidate.

    Intervals: observed vs fitted quantiles (Hazen plotting positions).
    Counts: randomized quantile residuals vs standard normal quantiles.
    """
    ok = _successful(fits)
    x = np.asarray(data, dtype=float)
    fig, axes = plt.subplots(1, len(ok), figsize=(3.1 * len(ok), 3.3), squeeze=False)
    probs = (np.arange(1, x.size + 1) - 0.5) / x.size
    for ax, fit in zip(axes[0], ok):
        spec = get_distribution(fit.distribution)
        if fit.track == "count":
            theo = stats.norm.ppf(probs)
            obs = np.sort(randomized_quantile_residuals(x, fit.distribution, fit.params))
            ax.set_xlabel("Standard normal quantile")
            ax.set_ylabel("Randomized quantile residual" if ax is axes[0][0] else "")
        else:
            theo = spec.ppf(probs, fit.params)
            obs = np.sort(x)
            ax.set_xlabel("Fitted quantile (s)")
            ax.set_ylabel("Observed quantile (s)" if ax is axes[0][0] else "")
        lim = [min(theo.min(), obs.min()), max(theo.max(), obs.max())]
        ax.plot(lim, lim, color=MUTED, linewidth=1, zorder=1)
        ax.scatter(theo, obs, s=9, color=FAMILY_COLOR[fit.distribution],
                   marker=FAMILY_MARKER[fit.distribution], linewidths=0, alpha=0.7, zorder=2)
        ax.set_title(_label(fit.distribution), loc="left", fontsize=10)
    fig.suptitle(title or "Q-Q diagnostics", x=0.01, ha="left", fontweight="bold",
                 color=INK, fontsize=11)
    fig.tight_layout()
    return fig


def plot_parameter_recovery_single(recovery: pd.DataFrame, title: str = "") -> plt.Figure:
    """Estimate / true ratio per parameter, with bootstrap 95% intervals."""
    fig, ax = plt.subplots(figsize=(6.5, 0.7 * len(recovery) + 1.4))
    y = np.arange(len(recovery))[::-1]
    ratio = recovery["estimate"] / recovery["true_value"]
    lo = recovery["ci_low"] / recovery["true_value"]
    hi = recovery["ci_high"] / recovery["true_value"]
    color = FAMILY_COLOR[recovery["family"].iloc[0]]
    ax.hlines(y, lo, hi, color=color, linewidth=2, alpha=0.45, zorder=2)
    ax.scatter(ratio, y, s=64, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.axvline(1, color=INK, linestyle=(0, (4, 3)), linewidth=1.2, zorder=1)
    ax.set_yticks(y, recovery["parameter"])
    ax.grid(axis="y", visible=False)
    for yi, (_, row) in zip(y, recovery.iterrows()):
        ax.annotate(f"true {row['true_value']:.4g} · est {row['estimate']:.4g} "
                    f"(95% CI {row['ci_low']:.4g} to {row['ci_high']:.4g})",
                    (1, yi), xytext=(0, 9), textcoords="offset points", ha="center",
                    fontsize=8, color=INK_2)
    ax.set_xlabel("Estimate ÷ true value (dashed line = perfect recovery)")
    ax.set_ylim(-0.6, len(recovery) - 0.2)
    ax.set_title(title or "Parameter recovery", loc="left")
    return fig


# ---------------------------------------------------------------------------
# Monte Carlo figures
# ---------------------------------------------------------------------------


def plot_confusion_matrices(matrices: Mapping[tuple[str, int], pd.DataFrame],
                            title: str = "") -> plt.Figure:
    """Grid of row-normalized confusion matrices keyed by (track, n)."""
    tracks = sorted({k[0] for k in matrices})
    sizes = sorted({k[1] for k in matrices})
    fig, axes = plt.subplots(len(tracks), len(sizes), figsize=(3.3 * len(sizes), 3.2 * len(tracks)),
                             squeeze=False)
    for i, track in enumerate(tracks):
        for j, n in enumerate(sizes):
            ax = axes[i][j]
            mat = matrices.get((track, n))
            if mat is None:
                ax.axis("off")
                continue
            sns.heatmap(mat * 100, ax=ax, cmap=SEQUENTIAL, vmin=0, vmax=100, annot=True, fmt=".0f",
                        cbar=False, linewidths=2, linecolor=SURFACE, square=True,
                        annot_kws={"fontsize": 8},
                        xticklabels=[_short(c) for c in mat.columns],
                        yticklabels=[_label(r) for r in mat.index])
            ax.grid(False)
            ax.set_title(f"{track} · n = {n}", loc="left", fontsize=10)
            ax.set_xlabel("Selected (lowest AIC)" if i == len(tracks) - 1 else "")
            ax.set_ylabel("True family" if j == 0 else "")
            ax.tick_params(axis="x", rotation=0, labelsize=8)
            ax.tick_params(axis="y", rotation=0, labelsize=7.5)
    fig.suptitle(title or "Confusion matrices (% of replicates per true family)", x=0.01,
                 ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_accuracy_vs_n(acc: pd.DataFrame, metric: str = "accuracy_aic",
                       title: str = "") -> plt.Figure:
    """Exact-family recovery vs n per track, one line per true family.

    ``acc`` must be pooled by (track, true_family, n) and contain
    ``{metric}_ci_low/high`` if bands are wanted.
    """
    tracks = [t for t in ("count", "interval") if t in set(acc["track"])]
    fig, axes = plt.subplots(1, len(tracks), figsize=(5.4 * len(tracks), 3.9), squeeze=False,
                             sharey=True)
    for ax, track in zip(axes[0], tracks):
        sub = acc[acc["track"] == track]
        for family in families_for_track(track):
            g = sub[sub["true_family"] == family].sort_values("n")
            if g.empty:
                continue
            ax.plot(g["n"], g[metric], markersize=5, **_line_kw(family))
            if f"{metric}_ci_low" in g:
                ax.fill_between(g["n"], g[f"{metric}_ci_low"], g[f"{metric}_ci_high"],
                                color=FAMILY_COLOR[family], alpha=0.1, linewidth=0)
        ax.set_xscale("log")
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Sample size n")
        ax.set_title(f"{track.capitalize()} track", loc="left")
        ax.legend(loc="lower right")
    axes[0][0].set_ylabel("Exact family recovery (AIC)")
    fig.suptitle(title or "Recovery accuracy vs sample size (95% Wilson band)", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_parameter_recovery_benchmark(summary: pd.DataFrame, title: str = "") -> plt.Figure:
    """Median |relative error| vs n, one panel per family (default scenarios)."""
    families = list(dict.fromkeys(summary["true_family"]))
    ncols = 4
    nrows = int(np.ceil(len(families) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.3 * ncols, 2.9 * nrows), squeeze=False,
                             sharex=True)
    for ax, family in zip(axes.flat, families):
        sub = summary[summary["true_family"] == family]
        for i, (pname, g) in enumerate(sub.groupby("parameter", sort=False)):
            g = g.sort_values("n")
            ax.plot(g["n"], g["median_abs_rel_error"], color=_SLOTS[i], linestyle=_STYLES[i],
                    marker=_MARKERS[i], markersize=4, label=pname)
        ax.set_xscale("log")
        ax.set_yscale("log")
        _percent_log_axis(ax)
        ax.set_title(f"{_label(family)}  ({sub['scenario'].iloc[0]})", loc="left", fontsize=9)
        ax.legend(loc="upper right", fontsize=7.5)
    for ax in axes.flat[len(families):]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel("Median |relative error| (log)")
    for ax in axes[-1]:
        ax.set_xlabel("Sample size n")
    fig.suptitle(title or "Parameter recovery of the true family vs sample size", x=0.01,
                 ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_metric_vs_level(df: pd.DataFrame, level_col: str, metric: str, xlabel: str,
                         ylabel: str, title: str, logx: bool = False) -> plt.Figure:
    """Generic per-track line plot of ``metric`` against an experimental level."""
    tracks = [t for t in ("count", "interval") if t in set(df["track"])]
    fig, axes = plt.subplots(1, len(tracks), figsize=(5.4 * len(tracks), 3.8), squeeze=False)
    for ax, track in zip(axes[0], tracks):
        sub = df[df["track"] == track]
        for family in families_for_track(track):
            g = sub[sub["true_family"] == family].sort_values(level_col)
            if g.empty:
                continue
            ax.plot(g[level_col], g[metric], markersize=5, **_line_kw(family))
            if f"{metric}_ci_low" in g:
                ax.fill_between(g[level_col], g[f"{metric}_ci_low"], g[f"{metric}_ci_high"],
                                color=FAMILY_COLOR[family], alpha=0.1, linewidth=0)
        if logx:
            ax.set_xscale("log")
        if metric.startswith("accuracy"):
            ax.set_ylim(0, 1.02)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{track.capitalize()} track", loc="left")
        ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_criterion_comparison(acc: pd.DataFrame, title: str = "") -> plt.Figure:
    """AIC vs AICc vs BIC exact recovery vs n, small multiple per family."""
    families = list(dict.fromkeys(acc["true_family"]))
    ncols = 4
    nrows = int(np.ceil(len(families) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.3 * ncols, 2.8 * nrows), squeeze=False,
                             sharey=True, sharex=True)
    crits = [("accuracy_aic", "AIC"), ("accuracy_aicc", "AICc"), ("accuracy_bic", "BIC")]
    for ax, family in zip(axes.flat, families):
        g = acc[acc["true_family"] == family].sort_values("n")
        for i, (col, name) in enumerate(crits):
            ax.plot(g["n"], g[col], color=_SLOTS[i], linestyle=_STYLES[i], marker=_MARKERS[i],
                    markersize=4, label=name)
        ax.set_xscale("log")
        ax.set_ylim(0, 1.02)
        ax.set_title(_label(family), loc="left", fontsize=9.5)
    axes.flat[0].legend(loc="lower right", fontsize=7.5)
    for ax in axes.flat[len(families):]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel("Exact recovery")
    for ax in axes[-1]:
        ax.set_xlabel("Sample size n")
    fig.suptitle(title or "Sample-size sensitivity: AIC vs AICc vs BIC", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_selection_frequencies(acc: pd.DataFrame, title: str = "") -> plt.Figure:
    """Stacked AIC selection frequencies vs n, one panel per scenario.

    Each track gets its own row and legend, because family colors are reused
    across tracks.
    """
    tracks = [t for t in ("interval", "count") if t in set(acc["track"])]
    per_track = {t: list(dict.fromkeys(acc.loc[acc["track"] == t, "scenario"])) for t in tracks}
    ncols = max(len(v) for v in per_track.values())
    fig, axes = plt.subplots(len(tracks), ncols, figsize=(2.9 * ncols + 1.6, 3.1 * len(tracks)),
                             squeeze=False, sharey=True)
    for row, track in zip(axes, tracks):
        for ax, scenario in zip(row, per_track[track]):
            g = acc[acc["scenario"] == scenario].sort_values("n")
            pos = np.arange(len(g))
            bottom = np.zeros(len(g))
            for family in families_for_track(track):
                freq = g[f"freq_{family}"].fillna(0).to_numpy()
                ax.bar(pos, freq, bottom=bottom, width=0.62, color=FAMILY_COLOR[family],
                       edgecolor=SURFACE, linewidth=1.5, label=_label(family))
                bottom += freq
            ax.set_xticks(pos, g["n"].astype(int))
            ax.set_ylim(0, 1)
            ax.grid(axis="x", visible=False)
            ax.set_title(f"{scenario}\ntrue: {_label(g['true_family'].iloc[0])}", loc="left",
                         fontsize=8.5)
            ax.tick_params(axis="x", labelsize=7.5)
            ax.set_xlabel("n", fontsize=8)
        for ax in row[len(per_track[track]):]:
            ax.axis("off")
        row[0].set_ylabel(f"{track.capitalize()}: share selected")
        last = row[len(per_track[track]) - 1]
        handles, labels = last.get_legend_handles_labels()
        last.legend(handles[::-1], labels[::-1], loc="center left", bbox_to_anchor=(1.02, 0.5),
                    title=f"{track} family", title_fontsize=8)
    fig.suptitle(title or "Which family does AIC pick in overlap regimes?", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_heldout(summary: pd.DataFrame, heldout: pd.DataFrame, scatter_n: int,
                 title: str = "") -> plt.Figure:
    """One row per track. Left: share of datasets where the training-AIC choice
    is within 1 log-likelihood unit of the best held-out candidate, vs n. Right: training ΔAIC vs held-out
    deficit 2·(best test LL − test LL) for every candidate fit at ``scatter_n``."""
    tracks = [t for t in ("count", "interval") if t in set(summary["track"])]
    fig, axes = plt.subplots(len(tracks), 2, figsize=(11, 3.9 * len(tracks)), squeeze=False)
    pooled = summary.groupby(["track", "true_family", "n"], as_index=False)["near_best_rate"].mean()
    for (ax1, ax2), track in zip(axes, tracks):
        for family in families_for_track(track):
            g = pooled[pooled["true_family"] == family].sort_values("n")
            if not g.empty:
                ax1.plot(g["n"], g["near_best_rate"], markersize=4.5, **_line_kw(family))
        ax1.set_xscale("log")
        ax1.set_ylim(0, 1.02)
        ax1.set_xlabel("Total sample size n (70% train / 30% test)")
        ax1.set_ylabel("P(AIC choice within 1 LL unit of best)")
        ax1.set_title(f"{track.capitalize()} track: agreement by true family", loc="left")
        ax1.legend(fontsize=7.5, loc="lower right")

        sub = heldout[(heldout["track"] == track) & (heldout["n"] == scatter_n)
                      & (heldout["status"] != "failed")]
        deficit = 2 * sub["delta_test_ll"]
        for family in families_for_track(track):
            m = sub["candidate"] == family
            if m.any():
                ax2.scatter(sub.loc[m, "delta_aic_train"] + 0.1, deficit[m] + 0.1, s=10,
                            color=FAMILY_COLOR[family], marker=FAMILY_MARKER[family], alpha=0.45,
                            linewidths=0, label=f"{_label(family)} (candidate)")
        ax2.set_xscale("log")
        ax2.set_yscale("log")
        hi = max(ax2.get_xlim()[1], ax2.get_ylim()[1])
        ax2.plot([0.1, hi], [0.1, hi], color=MUTED, linewidth=1)
        ax2.set_xlabel("Training ΔAIC (+0.1, log scale)")
        ax2.set_ylabel("Held-out deficit (+0.1, log scale)")
        ax2.set_title(f"{track.capitalize()} track: every candidate fit, n = {scatter_n}", loc="left")
        ax2.legend(fontsize=7.5, loc="upper left", markerscale=1.5)
    fig.suptitle(title or "Training AIC vs held-out predictive performance", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def plot_bias_vs_level(summary: pd.DataFrame, level_col: str, xlabel: str,
                       title: str = "") -> plt.Figure:
    """Mean relative bias of each true-family parameter vs an experimental level.

    Dashed thin lines show the theoretically expected bias where the
    observation model preserves the family (column ``expected_rel_error``).
    """
    families = list(dict.fromkeys(summary["true_family"]))
    ncols = 4
    nrows = int(np.ceil(len(families) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.3 * ncols, 2.9 * nrows), squeeze=False,
                             sharex=True)
    for ax, family in zip(axes.flat, families):
        sub = summary[summary["true_family"] == family]
        for i, (pname, g) in enumerate(sub.groupby("parameter", sort=False)):
            g = g.sort_values(level_col)
            ax.plot(g[level_col], g["mean_rel_error"], color=_SLOTS[i], linestyle=_STYLES[i],
                    marker=_MARKERS[i], markersize=4, label=pname)
            if g["expected_rel_error"].notna().any():
                ax.plot(g[level_col], g["expected_rel_error"], color=INK, linewidth=1,
                        linestyle=(0, (4, 3)), label="theory" if i == 0 else "_nolegend_")
        ax.axhline(0, color=MUTED, linewidth=0.8)
        ax.set_title(f"{_label(family)}  ({sub['scenario'].iloc[0]})", loc="left", fontsize=9)
        ax.legend(fontsize=7, loc="best")
    for ax in axes.flat[len(families):]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean relative bias")
    for ax in axes[-1]:
        ax.set_xlabel(xlabel)
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    return fig
