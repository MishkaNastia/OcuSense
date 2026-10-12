"""Information criteria and model ranking.

AIC is the primary criterion; AICc and BIC are always reported alongside.
A ranking is only produced from fits that share the same measurement track
*and* the exact same observations (checked via a data fingerprint), because
AIC values from different data or from mass vs density likelihoods are not
comparable.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .distributions import Track, families_for_track, get_distribution
from .fitting import FitResult, fit_distribution

CRITERIA = ("aic", "aicc", "bic")


def calculate_aic(log_likelihood: float, k: int) -> float:
    """AIC = 2k - 2 log L."""
    _check_k(k)
    return 2.0 * k - 2.0 * log_likelihood


def calculate_aicc(log_likelihood: float, k: int, n: int) -> float:
    """AICc = AIC + 2k(k+1)/(n-k-1); infinite when n <= k + 1."""
    _check_k(k)
    _check_n(n)
    if n <= k + 1:
        return float("inf")
    return calculate_aic(log_likelihood, k) + 2.0 * k * (k + 1) / (n - k - 1)


def calculate_bic(log_likelihood: float, k: int, n: int) -> float:
    """BIC = k log(n) - 2 log L."""
    _check_k(k)
    _check_n(n)
    return k * np.log(n) - 2.0 * log_likelihood


def _check_k(k: int) -> None:
    if k < 0 or int(k) != k:
        raise ValueError(f"k must be a nonnegative integer, got {k}")


def _check_n(n: int) -> None:
    if n < 1 or int(n) != n:
        raise ValueError(f"n must be a positive integer, got {n}")


def akaike_weights(delta: np.ndarray) -> np.ndarray:
    """Normalize exp(-delta/2); NaN/inf deltas (failed fits) get weight 0.

    Weights describe relative support among the *candidates considered*;
    they are not probabilities that a model is literally true.
    """
    delta = np.asarray(delta, dtype=float)
    raw = np.where(np.isfinite(delta), np.exp(-0.5 * np.where(np.isfinite(delta), delta, 0)), 0.0)
    total = raw.sum()
    return raw / total if total > 0 else np.full_like(raw, np.nan)


def check_same_track(candidate_names: Iterable[str]) -> Track:
    """Return the shared track of the candidates or raise ``ValueError``."""
    names = list(candidate_names)
    if not names:
        raise ValueError("At least one candidate distribution is required")
    tracks = {get_distribution(name).track for name in names}
    if len(tracks) > 1:
        raise ValueError(
            "Cannot rank count (probability mass) and interval (probability density) "
            f"models together: got {sorted(names)} spanning tracks {sorted(tracks)}"
        )
    return tracks.pop()


def fit_candidates(data: Sequence[float] | np.ndarray,
                   candidate_names: Sequence[str] | None = None,
                   track: Track | None = None) -> list[FitResult]:
    """Fit every candidate to the same data. Defaults to all families of ``track``."""
    if candidate_names is None:
        if track is None:
            raise ValueError("Give candidate_names or track")
        candidate_names = families_for_track(track)
    check_same_track(candidate_names)
    return [fit_distribution(data, name) for name in candidate_names]


def rank_fits(fits: Sequence[FitResult], criterion: str = "aic") -> pd.DataFrame:
    """Rank already-fitted candidates by an information criterion.

    Columns: rank, distribution, parameters, log_likelihood, k, n, aic, aicc,
    bic, delta_aic, akaike_weight, delta_bic, status, message. Failed fits are
    kept (with NaN criteria) at the bottom so failures are visible.
    """
    if criterion not in CRITERIA:
        raise ValueError(f"criterion must be one of {CRITERIA}")
    if not fits:
        raise ValueError("No fits to rank")
    check_same_track(f.distribution for f in fits)
    if len({f.n for f in fits}) > 1 or len({f.data_hash for f in fits}) > 1:
        raise ValueError("All fits must use the identical observations to compare AIC values")

    rows = []
    for fit in fits:
        ok = fit.success
        ll = fit.log_likelihood if ok else np.nan
        rows.append({
            "distribution": fit.distribution,
            "track": fit.track,
            "parameters": dict(fit.params),
            "log_likelihood": ll,
            "k": fit.k,
            "n": fit.n,
            "aic": calculate_aic(ll, fit.k) if ok else np.nan,
            "aicc": calculate_aicc(ll, fit.k, fit.n) if ok else np.nan,
            "bic": calculate_bic(ll, fit.k, fit.n) if ok else np.nan,
            "status": fit.status,
            "message": fit.message,
        })
    table = pd.DataFrame(rows)
    table["delta_aic"] = table["aic"] - table["aic"].min()
    table["akaike_weight"] = akaike_weights(table["delta_aic"].to_numpy())
    table["delta_bic"] = table["bic"] - table["bic"].min()
    table = table.sort_values([criterion, "distribution"], na_position="last", kind="stable")
    table.insert(0, "rank", np.arange(1, len(table) + 1))
    columns = ["rank", "distribution", "track", "parameters", "log_likelihood", "k", "n",
               "aic", "aicc", "bic", "delta_aic", "akaike_weight", "delta_bic",
               "status", "message"]
    return table[columns].reset_index(drop=True)


def select_best_distribution(data: Sequence[float] | np.ndarray,
                             candidate_names: Sequence[str],
                             criterion: str = "aic") -> pd.DataFrame:
    """Fit all candidates to ``data`` and return them ranked by ``criterion``.

    Raises ``ValueError`` if the candidates mix count and interval families.
    The best model is ``table.iloc[0]`` provided its ``status`` is not
    ``"failed"`` (if every fit failed, no model is selected).
    """
    return rank_fits(fit_candidates(data, candidate_names), criterion=criterion)


def best_model(table: pd.DataFrame, criterion: str = "aic") -> str | None:
    """Name of the lowest-criterion successful model, or None if all failed."""
    ok = table[table["status"] != "failed"]
    if ok.empty:
        return None
    return str(ok.loc[ok[criterion].idxmin(), "distribution"])
