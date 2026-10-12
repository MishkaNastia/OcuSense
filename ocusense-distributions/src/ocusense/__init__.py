"""OcuSense distribution-fitting and model-selection research prototype."""

from .distributions import COUNT_FAMILIES, INTERVAL_FAMILIES, REGISTRY, get_distribution
from .fitting import FitResult, fit_distribution
from .selection import (
    calculate_aic,
    calculate_aicc,
    calculate_bic,
    rank_fits,
    select_best_distribution,
)
from .synthetic import generate_synthetic_data

__all__ = [
    "COUNT_FAMILIES",
    "INTERVAL_FAMILIES",
    "REGISTRY",
    "FitResult",
    "calculate_aic",
    "calculate_aicc",
    "calculate_bic",
    "fit_distribution",
    "generate_synthetic_data",
    "get_distribution",
    "rank_fits",
    "select_best_distribution",
]
