"""Statistical recovery benchmark as pytest checks.

One test per pre-declared floor (see ocusense/recovery.py): BIC/AIC selection
accuracy at large n, parameter accuracy, and count-noise behaviour. Each test
reports the measured percentage. The full recovery tables (every n, AIC and
BIC, confusions, noise) are printed at the end of the session.

Run:  pytest benchmarks            (about 5 minutes with 100 datasets per cell)
"""

import pytest
from bench_config import CONFIG

from ocusense.recovery import evaluate_check, plan_checks

SPECS = plan_checks(CONFIG)
_CACHE: dict = {}


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_recovery_floor(spec, recovery_results):
    result = evaluate_check(spec, recovery_results, _CACHE)
    assert result.passed, result.line()
