"""Maximum-likelihood fitting of the candidate distributions.

Estimation strategy
-------------------
* Poisson: closed-form MLE, ``lam = mean(x)``.
* Log-normal, Gamma, Weibull, Exponential: SciPy ``.fit`` with ``floc=0``
  (SciPy solves the MLE equations analytically/by root finding for these
  families when the location is fixed).
* Negative binomial, ZIP, ZINB: numerical MLE with :func:`scipy.optimize.minimize`
  on transformed parameters (``log`` for positive, ``logit`` for
  probabilities), box-bounded, from several starting points, with a Powell
  fallback when L-BFGS-B does not report convergence.

A fit that fails is reported as failed (``converged=False``, NaN
log-likelihood, empty ``params``) together with the optimizer messages. No
guessed or moment-based estimates are substituted.

Identifiability
---------------
Several candidates contain others as limiting or boundary cases:

* NB(mu, r) -> Poisson(mu) as r -> inf. If the sample variance does not
  exceed the mean, the NB likelihood increases monotonically in r and the MLE
  is at infinity: r is not identifiable and the NB log-likelihood equals the
  Poisson one, so NB loses on AIC by exactly its extra parameter (2 units).
* ZIP(lam, pi) -> Poisson(lam) and ZINB(mu, r, pi) -> NB(mu, r) at pi = 0.
  With no excess zeros the estimate sits on the boundary pi = 0.
* ZINB -> ZIP as r -> inf.
* Gamma(shape=1) and Weibull(shape=1) are exactly Exponential.

Fits ending on (or numerically at) such a boundary are flagged with
``at_boundary=True`` and an explanatory message. They are still valid
maximum-likelihood fits and stay in the AIC ranking, where the parameter
penalty handles the redundancy.
"""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import asdict, dataclass, field, replace
from typing import Callable, Sequence

import numpy as np
from scipy import optimize, special, stats

from .distributions import COUNT, INTERVAL, Track, get_distribution

# Box bounds on the *transformed* scale for the numerical models.
LOG_MEAN_BOUNDS = (np.log(1e-6), np.log(1e5))
LOG_R_BOUNDS = (np.log(1e-3), np.log(1e6))
LOGIT_PI_BOUNDS = (-25.0, 10.0)

# Semantic thresholds for "numerically at the boundary". Optimizers stop
# early on very flat likelihood surfaces, so hitting the box exactly is rare.
R_EFFECTIVELY_INFINITE = 1e4
PI_EFFECTIVELY_ZERO = 1e-4

_BOUND_TOL = 1e-4
_OPTIONS = {
    "L-BFGS-B": {"ftol": 1e-14, "gtol": 1e-9, "maxiter": 5000},
    "Powell": {"xtol": 1e-8, "ftol": 1e-12, "maxiter": 20000},
}


@dataclass(frozen=True)
class FitResult:
    """Outcome of fitting one distribution to one dataset.

    Attributes:
        distribution: Registry name of the fitted family.
        track: ``"count"`` or ``"interval"``.
        params: MLE parameters (empty if the fit failed).
        k: Number of free parameters.
        n: Number of observations used.
        log_likelihood: Maximized log-likelihood (NaN if failed).
        converged: Whether a valid maximum was found.
        at_boundary: Whether the MLE lies on/near the parameter-space boundary.
        message: Diagnostics: optimizer messages, boundary explanations.
        data_hash: Fingerprint of the exact observations, used to refuse AIC
            comparisons across different datasets.
    """

    distribution: str
    track: Track
    params: dict[str, float]
    k: int
    n: int
    log_likelihood: float
    converged: bool
    at_boundary: bool = False
    message: str = ""
    data_hash: str = field(default="", repr=False)

    @property
    def success(self) -> bool:
        return self.converged and bool(np.isfinite(self.log_likelihood))

    @property
    def status(self) -> str:
        if not self.success:
            return "failed"
        return "boundary" if self.at_boundary else "ok"

    def to_dict(self) -> dict:
        out = asdict(self)
        out["status"] = self.status
        return out


def data_fingerprint(x: np.ndarray) -> str:
    """Short SHA-1 fingerprint of an array's float64 values."""
    return hashlib.sha1(np.ascontiguousarray(x, dtype=np.float64).tobytes()).hexdigest()[:16]


def validate_data(data: Sequence[float] | np.ndarray, track: Track) -> np.ndarray:
    """Return a float64 *copy* of ``data`` after checking it suits ``track``.

    Raises ``ValueError`` for wrong shape, non-finite values or values outside
    the track's support. These are caller errors, not fit failures.
    """
    x = np.array(data, dtype=np.float64, copy=True)
    if x.ndim != 1:
        raise ValueError(f"data must be one-dimensional, got shape {x.shape}")
    if x.size == 0:
        raise ValueError("data must contain at least one observation")
    if not np.all(np.isfinite(x)):
        raise ValueError("data contain non-finite values")
    if track == COUNT:
        if np.any(x < 0) or np.any(x != np.round(x)):
            raise ValueError("count data must be nonnegative integers")
    elif track == INTERVAL:
        if np.any(x <= 0):
            raise ValueError("interval data must be strictly positive (seconds)")
    else:
        raise ValueError(f"Unknown track {track!r}")
    return x


def fit_distribution(data: Sequence[float] | np.ndarray, distribution_name: str) -> FitResult:
    """Fit one candidate distribution by maximum likelihood.

    The input is never modified (a validated copy is used).
    """
    spec = get_distribution(distribution_name)
    x = validate_data(data, spec.track)
    if spec.track == INTERVAL:
        fit = _fit_interval(distribution_name, x)
    elif distribution_name == "poisson":
        fit = _fit_poisson(x)
    else:
        fit = _fit_count_numeric(distribution_name, x)
    return replace(fit, data_hash=data_fingerprint(x))


def _failed(name: str, n: int, message: str) -> FitResult:
    spec = get_distribution(name)
    return FitResult(name, spec.track, {}, spec.k, n, float("nan"), False, False, message)


def _total_loglik(name: str, x: np.ndarray, params: dict[str, float]) -> float:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return float(np.sum(get_distribution(name).logprob(x, params)))


# ---------------------------------------------------------------------------
# Interval track: SciPy MLE with loc fixed at 0
# ---------------------------------------------------------------------------

_SCIPY_FITTERS: dict[str, Callable[[np.ndarray], dict[str, float]]] = {
    "exponential": lambda x: {"scale": stats.expon.fit(x, floc=0)[1]},
    "gamma": lambda x: dict(zip(("shape", "scale"), stats.gamma.fit(x, floc=0)[::2])),
    "weibull": lambda x: dict(zip(("shape", "scale"), stats.weibull_min.fit(x, floc=0)[::2])),
    "lognormal": lambda x: _lognormal_from_scipy(stats.lognorm.fit(x, floc=0)),
}


def _lognormal_from_scipy(fitted: tuple[float, float, float]) -> dict[str, float]:
    sigma, _, scale = fitted
    return {"mu_log": float(np.log(scale)), "sigma": float(sigma)}


def _fit_interval(name: str, x: np.ndarray) -> FitResult:
    spec = get_distribution(name)
    n = x.size
    if spec.k >= 2 and (n < 2 or np.ptp(x) == 0):
        return _failed(name, n, "degenerate sample: all observations identical, "
                                "so the spread/shape parameter has no finite MLE")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            raw = _SCIPY_FITTERS[name](x)
        except Exception as exc:  # SciPy raises several exception types here
            return _failed(name, n, f"SciPy fit raised {type(exc).__name__}: {exc}")
    params = {key: float(value) for key, value in raw.items()}
    try:
        params = spec.validate_params(params)
    except ValueError as exc:
        return _failed(name, n, f"SciPy returned invalid parameters: {exc}")
    loglik = _total_loglik(name, x, params)
    if not np.isfinite(loglik):
        return _failed(name, n, f"non-finite log-likelihood at {params}")
    notes = "; ".join(sorted({str(w.message) for w in caught}))
    at_boundary = name in ("gamma", "weibull") and abs(params["shape"] - 1) < 1e-6
    return FitResult(name, INTERVAL, params, spec.k, n, loglik, True, at_boundary,
                     notes or "closed-form/SciPy MLE (loc fixed at 0)")


# ---------------------------------------------------------------------------
# Count track
# ---------------------------------------------------------------------------


def _fit_poisson(x: np.ndarray) -> FitResult:
    lam = float(x.mean())
    if lam == 0:
        return FitResult("poisson", COUNT, {"lam": 0.0}, 1, x.size, 0.0, True, True,
                         "all-zero sample: MLE lam = 0 lies on the boundary of the "
                         "parameter space (degenerate point mass at 0)")
    return FitResult("poisson", COUNT, {"lam": lam}, 1, x.size,
                     _total_loglik("poisson", x, {"lam": lam}), True, False,
                     "closed-form MLE (sample mean)")


@dataclass(frozen=True)
class _Transform:
    """Maps unconstrained optimizer variables to named model parameters."""

    names: tuple[str, ...]
    kinds: tuple[str, ...]  # "log" or "logit"
    bounds: tuple[tuple[float, float], ...]

    def to_params(self, theta: np.ndarray) -> dict[str, float]:
        out = {}
        for name, kind, value in zip(self.names, self.kinds, theta):
            out[name] = float(np.exp(value) if kind == "log" else special.expit(value))
        return out

    def to_theta(self, params: dict[str, float]) -> np.ndarray:
        values = [
            np.log(params[n]) if kind == "log" else special.logit(params[n])
            for n, kind in zip(self.names, self.kinds)
        ]
        lo, hi = np.array(self.bounds).T
        return np.clip(values, lo + 1e-6, hi - 1e-6)


_TRANSFORMS: dict[str, _Transform] = {
    "negbin": _Transform(("mu", "r"), ("log", "log"), (LOG_MEAN_BOUNDS, LOG_R_BOUNDS)),
    "zip": _Transform(("lam", "pi"), ("log", "logit"), (LOG_MEAN_BOUNDS, LOGIT_PI_BOUNDS)),
    "zinb": _Transform(("mu", "r", "pi"), ("log", "log", "logit"),
                       (LOG_MEAN_BOUNDS, LOG_R_BOUNDS, LOGIT_PI_BOUNDS)),
}


def _starting_points(name: str, x: np.ndarray) -> list[dict[str, float]]:
    """Several moment-based starting values; the best converged fit wins."""
    m = float(x.mean())
    v = float(x.var(ddof=1)) if x.size > 1 else m
    zero_frac = float(np.mean(x == 0))
    positive = x[x > 0]
    m_pos = float(positive.mean()) if positive.size else m
    r_mom = m * m / (v - m) if v > m else 100.0
    lam_zip = v / m + m - 1 if m > 0 else m
    lam_zip = lam_zip if lam_zip > m else m
    pi_zip = 1 - m / lam_zip

    def clip_pi(p: float) -> float:
        return float(np.clip(p, 1e-3, 0.95))

    if name == "negbin":
        return [{"mu": m, "r": r_mom}, {"mu": m, "r": 1.0}, {"mu": m, "r": 50.0}]
    if name == "zip":
        return [{"lam": lam_zip, "pi": clip_pi(pi_zip)},
                {"lam": m_pos, "pi": clip_pi(zero_frac)},
                {"lam": m, "pi": 0.01}]
    return [{"mu": m_pos, "r": 10.0, "pi": clip_pi(zero_frac)},
            {"mu": m, "r": r_mom, "pi": 0.01},
            {"mu": lam_zip, "r": 5.0, "pi": clip_pi(pi_zip)},
            {"mu": m_pos, "r": 1.0, "pi": clip_pi(zero_frac / 2)}]


def _maximize(
    negll: Callable[[np.ndarray], float],
    starts: list[np.ndarray],
    bounds: tuple[tuple[float, float], ...],
) -> tuple[optimize.OptimizeResult | None, list[str], float]:
    """Minimize ``negll`` from several starts.

    Returns the best converged result (or ``None``), diagnostic notes, and the
    spread of converged objective values across starts.
    """
    converged: list[optimize.OptimizeResult] = []
    notes: list[str] = []
    for x0 in starts:
        if not np.isfinite(negll(x0)):
            notes.append(f"start {np.round(x0, 3)} has non-finite likelihood")
            continue
        for method in ("L-BFGS-B", "Powell"):
            try:
                res = optimize.minimize(negll, x0, method=method, bounds=bounds,
                                       options=_OPTIONS[method])
            except (ValueError, FloatingPointError) as exc:
                notes.append(f"{method} from {np.round(x0, 3)} raised {exc}")
                continue
            if res.success and np.isfinite(res.fun):
                if method != "L-BFGS-B":
                    notes.append(f"L-BFGS-B did not converge from {np.round(x0, 3)}; "
                                 f"{method} fallback converged")
                converged.append(res)
                break
            notes.append(f"{method} from {np.round(x0, 3)}: {res.message}")
    if not converged:
        return None, notes, float("nan")
    funs = np.array([r.fun for r in converged])
    return converged[int(np.argmin(funs))], notes, float(funs.max() - funs.min())


def _boundary_notes(name: str, theta: np.ndarray, params: dict[str, float],
                    transform: _Transform) -> list[str]:
    notes = []
    for value, (lo, hi), pname in zip(theta, transform.bounds, transform.names):
        if value - lo < _BOUND_TOL or hi - value < _BOUND_TOL:
            notes.append(f"{pname} hit its optimization bound")
    if params.get("r", 0) > R_EFFECTIVELY_INFINITE:
        limit = "Poisson" if name == "negbin" else "ZIP"
        notes.append(f"r = {params['r']:.3g} is effectively infinite: the model reduces to "
                     f"{limit} and r is not identifiable (no overdispersion detected)")
    if "pi" in params and params["pi"] < PI_EFFECTIVELY_ZERO:
        base = "Poisson" if name == "zip" else "negative binomial"
        notes.append(f"pi = {params['pi']:.2g} is effectively 0: no excess zeros detected, "
                     f"the model reduces to the {base}")
    return notes


def _fit_count_numeric(name: str, x: np.ndarray) -> FitResult:
    spec = get_distribution(name)
    n = x.size
    if x.max() == 0:
        return _failed(name, n, "degenerate sample: all counts are zero, so the mean MLE is 0 "
                                "and dispersion / zero-inflation parameters are not identifiable")
    transform = _TRANSFORMS[name]
    # Counts have few distinct values: evaluate each once and weight it.
    values, weights = np.unique(x, return_counts=True)

    def negll(theta: np.ndarray) -> float:
        with np.errstate(all="ignore"):
            value = -float(np.dot(weights, spec.logprob(values, transform.to_params(theta))))
        return value if np.isfinite(value) else np.inf

    starts = [transform.to_theta(p) for p in _starting_points(name, x)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        best, notes, spread = _maximize(negll, starts, transform.bounds)
    if best is None:
        return _failed(name, n, "optimization failed from all starts: " + " | ".join(notes))
    params = transform.to_params(best.x)
    loglik = _total_loglik(name, x, params)
    if not np.isfinite(loglik):
        return _failed(name, n, f"non-finite log-likelihood at optimum {params}")
    boundary = _boundary_notes(name, best.x, params, transform)
    if spread > 1e-2:
        notes.append(f"converged starts differ by {spread:.3g} in log-likelihood "
                     "(multiple local optima); best one kept")
    message = "; ".join(boundary + notes) or "numerical MLE converged"
    return FitResult(name, COUNT, params, spec.k, n, loglik, True, bool(boundary), message)
