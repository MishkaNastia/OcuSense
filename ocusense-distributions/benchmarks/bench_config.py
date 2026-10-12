"""Configuration shared by the statistical pytest suite.

Environment variables:
    OCUSENSE_BENCH_REPS   datasets per cell (default 100; floors are calibrated for 100)
    OCUSENSE_BENCH_JOBS   worker processes (default: CPU count - 1)
"""

import os

from ocusense.recovery import RecoveryConfig

CONFIG = RecoveryConfig(
    n_reps=int(os.environ.get("OCUSENSE_BENCH_REPS", 100)),
    n_jobs=int(os.environ.get("OCUSENSE_BENCH_JOBS", max(1, (os.cpu_count() or 2) - 1))),
)
