"""Registry of candidate probability distributions.

Every distribution is defined exactly once here, and the same definition is
used for data generation, likelihood evaluation, plotting and reporting. This
guarantees that, e.g., the negative binomial ``(mu, r)`` parameterization used
to simulate data is the one whose likelihood is maximized.

Two measurement tracks are kept strictly separate:

* ``"count"``: nonnegative integer blink counts per fixed window
  (probability *mass* functions).
* ``"interval"``: positive continuous interblink intervals in seconds
  (probability *density* functions, location fixed at zero).

Log-likelihoods from the two tracks are not comparable, so AIC rankings must
never mix them (enforced in :mod:`ocusense.selection`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping

import numpy as np
from scipy import special, stats

Track = Literal["count", "interval"]
Params = Mapping[str, float]

COUNT: Track = "count"
INTERVAL: Track = "interval"


@dataclass(frozen=True)
class ParamSpec:
    """One distribution parameter and its valid domain.

    ``domain`` is ``"positive"`` for (0, inf), ``"unit"`` for [0, 1) or
    ``"real"`` for any finite value.
    """

    name: str
    domain: Literal["positive", "unit", "real"]
    description: str


@dataclass(frozen=True)
class DistributionSpec:
    """Complete definition of a candidate distribution family."""

    name: str
    track: Track
    params: tuple[ParamSpec, ...]
    logprob: Callable[[np.ndarray, Params], np.ndarray]
    sample: Callable[[np.random.Generator, Params, int], np.ndarray]
    cdf: Callable[[np.ndarray, Params], np.ndarray]
    mean: Callable[[Params], float]
    formula: str
    ppf: Callable[[np.ndarray, Params], np.ndarray] | None = None

    @property
    def k(self) -> int:
        """Number of free parameters (location is fixed, never counted)."""
        return len(self.params)

    @property
    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def validate_params(self, params: Params) -> dict[str, float]:
        """Return params as floats, raising ``ValueError`` if any is invalid."""
        missing = set(self.param_names) - set(params)
        extra = set(params) - set(self.param_names)
        if missing or extra:
            raise ValueError(
                f"{self.name} expects parameters {self.param_names}; "
                f"missing={sorted(missing)}, unexpected={sorted(extra)}"
            )
        clean: dict[str, float] = {}
        for p in self.params:
            value = float(params[p.name])
            if not np.isfinite(value):
                raise ValueError(f"{self.name}.{p.name} must be finite, got {value}")
            if p.domain == "positive" and value <= 0:
                raise ValueError(f"{self.name}.{p.name} must be > 0, got {value}")
            if p.domain == "unit" and not 0 <= value < 1:
                raise ValueError(f"{self.name}.{p.name} must be in [0, 1), got {value}")
            clean[p.name] = value
        return clean


# ---------------------------------------------------------------------------
# Count track
# ---------------------------------------------------------------------------


def _nb_logpmf(x: np.ndarray, mu: float, r: float) -> np.ndarray:
    """Negative binomial log-pmf with mean ``mu`` and dispersion ``r``.

    Var(X) = mu + mu**2 / r. Written with ``log1p``/``xlogy`` so it stays
    accurate when ``r`` is very large (near-Poisson) or ``mu`` is tiny.
    """
    return (
        special.gammaln(x + r)
        - special.gammaln(r)
        - special.gammaln(x + 1)
        - r * np.log1p(mu / r)
        + special.xlogy(x, mu)
        - x * np.log(r + mu)
    )


def _nb_scipy(mu: float, r: float):
    """Frozen SciPy ``nbinom`` with the (mu, r) parameterization."""
    return stats.nbinom(n=r, p=r / (r + mu))


def _zero_inflate(base_logpmf: np.ndarray, x: np.ndarray, pi: float) -> np.ndarray:
    """Mix a point mass at zero (weight ``pi``) into a count log-pmf."""
    with np.errstate(divide="ignore"):
        log_pi = np.log(pi)
    log_keep = np.log1p(-pi)
    out = log_keep + base_logpmf
    zeros = x == 0
    out[zeros] = np.logaddexp(log_pi, log_keep + base_logpmf[zeros])
    return out


def _poisson_logprob(x: np.ndarray, p: Params) -> np.ndarray:
    return stats.poisson.logpmf(x, p["lam"])


def _negbin_logprob(x: np.ndarray, p: Params) -> np.ndarray:
    return _nb_logpmf(x, p["mu"], p["r"])


def _zip_logprob(x: np.ndarray, p: Params) -> np.ndarray:
    return _zero_inflate(stats.poisson.logpmf(x, p["lam"]), x, p["pi"])


def _zinb_logprob(x: np.ndarray, p: Params) -> np.ndarray:
    return _zero_inflate(_nb_logpmf(x, p["mu"], p["r"]), x, p["pi"])


def _structural_zeros(rng: np.random.Generator, pi: float, n: int) -> np.ndarray:
    return rng.random(n) < pi


def _sample_poisson(rng: np.random.Generator, p: Params, n: int) -> np.ndarray:
    return rng.poisson(p["lam"], n)


def _sample_negbin(rng: np.random.Generator, p: Params, n: int) -> np.ndarray:
    mu, r = p["mu"], p["r"]
    return rng.negative_binomial(r, r / (r + mu), n)


def _sample_zip(rng: np.random.Generator, p: Params, n: int) -> np.ndarray:
    counts = rng.poisson(p["lam"], n)
    counts[_structural_zeros(rng, p["pi"], n)] = 0
    return counts


def _sample_zinb(rng: np.random.Generator, p: Params, n: int) -> np.ndarray:
    counts = _sample_negbin(rng, p, n)
    counts[_structural_zeros(rng, p["pi"], n)] = 0
    return counts


def _zi_cdf(base_cdf: np.ndarray, x: np.ndarray, pi: float) -> np.ndarray:
    return np.where(np.asarray(x) >= 0, pi + (1 - pi) * base_cdf, 0.0)


# ---------------------------------------------------------------------------
# Interval track (location fixed at 0)
# ---------------------------------------------------------------------------


def _lognorm(p: Params):
    return stats.lognorm(s=p["sigma"], scale=np.exp(p["mu_log"]))


def _gamma(p: Params):
    return stats.gamma(a=p["shape"], scale=p["scale"])


def _weibull(p: Params):
    return stats.weibull_min(c=p["shape"], scale=p["scale"])


def _expon(p: Params):
    return stats.expon(scale=p["scale"])


def _continuous(name: str, frozen: Callable[[Params], object], params: tuple[ParamSpec, ...],
                formula: str) -> DistributionSpec:
    """Build an interval-track spec from a frozen-SciPy-distribution factory."""
    return DistributionSpec(
        name=name,
        track=INTERVAL,
        params=params,
        logprob=lambda x, p: frozen(p).logpdf(x),
        sample=lambda rng, p, n: frozen(p).rvs(size=n, random_state=rng),
        cdf=lambda x, p: frozen(p).cdf(x),
        ppf=lambda q, p: frozen(p).ppf(q),
        mean=lambda p: float(frozen(p).mean()),
        formula=formula,
    )


_SHAPE = ParamSpec("shape", "positive", "shape parameter")
_SCALE = ParamSpec("scale", "positive", "scale parameter (seconds)")

REGISTRY: dict[str, DistributionSpec] = {
    "poisson": DistributionSpec(
        name="poisson",
        track=COUNT,
        params=(ParamSpec("lam", "positive", "mean blinks per window"),),
        logprob=_poisson_logprob,
        sample=_sample_poisson,
        cdf=lambda x, p: stats.poisson.cdf(x, p["lam"]),
        mean=lambda p: p["lam"],
        formula="P(X=x) = exp(-lam) lam^x / x!",
    ),
    "negbin": DistributionSpec(
        name="negbin",
        track=COUNT,
        params=(
            ParamSpec("mu", "positive", "mean blinks per window"),
            ParamSpec("r", "positive", "dispersion; Var = mu + mu^2/r"),
        ),
        logprob=_negbin_logprob,
        sample=_sample_negbin,
        cdf=lambda x, p: _nb_scipy(p["mu"], p["r"]).cdf(x),
        mean=lambda p: p["mu"],
        formula="P(X=x) = G(x+r)/(G(r) x!) (r/(r+mu))^r (mu/(r+mu))^x",
    ),
    "zip": DistributionSpec(
        name="zip",
        track=COUNT,
        params=(
            ParamSpec("lam", "positive", "Poisson mean of the non-structural part"),
            ParamSpec("pi", "unit", "structural-zero probability"),
        ),
        logprob=_zip_logprob,
        sample=_sample_zip,
        cdf=lambda x, p: _zi_cdf(stats.poisson.cdf(x, p["lam"]), x, p["pi"]),
        mean=lambda p: (1 - p["pi"]) * p["lam"],
        formula="P(0) = pi + (1-pi) e^-lam;  P(x>0) = (1-pi) Poisson(x; lam)",
    ),
    "zinb": DistributionSpec(
        name="zinb",
        track=COUNT,
        params=(
            ParamSpec("mu", "positive", "NB mean of the non-structural part"),
            ParamSpec("r", "positive", "NB dispersion"),
            ParamSpec("pi", "unit", "structural-zero probability"),
        ),
        logprob=_zinb_logprob,
        sample=_sample_zinb,
        cdf=lambda x, p: _zi_cdf(_nb_scipy(p["mu"], p["r"]).cdf(x), x, p["pi"]),
        mean=lambda p: (1 - p["pi"]) * p["mu"],
        formula="P(0) = pi + (1-pi) NB(0; mu, r);  P(x>0) = (1-pi) NB(x; mu, r)",
    ),
    "lognormal": _continuous(
        "lognormal",
        _lognorm,
        (
            ParamSpec("mu_log", "real", "mean of log(interval)"),
            ParamSpec("sigma", "positive", "SD of log(interval)"),
        ),
        "f(x) = 1/(x sigma sqrt(2pi)) exp(-(ln x - mu_log)^2 / (2 sigma^2)); "
        "SciPy lognorm(s=sigma, scale=exp(mu_log), loc=0)",
    ),
    "gamma": _continuous(
        "gamma",
        _gamma,
        (_SHAPE, _SCALE),
        "f(x) = x^(a-1) e^(-x/scale) / (G(a) scale^a); SciPy gamma(a=shape, scale, loc=0)",
    ),
    "weibull": _continuous(
        "weibull",
        _weibull,
        (_SHAPE, _SCALE),
        "f(x) = (c/scale)(x/scale)^(c-1) exp(-(x/scale)^c); "
        "SciPy weibull_min(c=shape, scale, loc=0)",
    ),
    "exponential": _continuous(
        "exponential",
        _expon,
        (_SCALE,),
        "f(x) = exp(-x/scale)/scale; SciPy expon(scale, loc=0)",
    ),
}

COUNT_FAMILIES: tuple[str, ...] = tuple(n for n, s in REGISTRY.items() if s.track == COUNT)
INTERVAL_FAMILIES: tuple[str, ...] = tuple(n for n, s in REGISTRY.items() if s.track == INTERVAL)


def get_distribution(name: str) -> DistributionSpec:
    """Look up a distribution by name, raising ``KeyError`` with the options."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown distribution {name!r}; choose from {sorted(REGISTRY)}") from None


def families_for_track(track: Track) -> tuple[str, ...]:
    """All candidate families belonging to one measurement track."""
    if track == COUNT:
        return COUNT_FAMILIES
    if track == INTERVAL:
        return INTERVAL_FAMILIES
    raise ValueError(f"Unknown track {track!r}; expected 'count' or 'interval'")


def log_likelihood(data: np.ndarray, name: str, params: Params) -> float:
    """Total log-likelihood of ``data`` under ``name(params)``."""
    spec = get_distribution(name)
    return float(np.sum(spec.logprob(np.asarray(data, dtype=float), spec.validate_params(params))))
