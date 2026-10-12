"""Run the recovery benchmark once per session and print its report at the end."""

import pytest
from bench_config import CONFIG

from ocusense.recovery import evaluate_all, format_report, run_recovery

_STATE: dict = {}


@pytest.fixture(scope="session")
def recovery_results():
    if "results" not in _STATE:
        _STATE["results"] = run_recovery(CONFIG)
    return _STATE["results"]


def pytest_terminal_summary(terminalreporter):
    if "results" in _STATE:
        checks = evaluate_all(CONFIG, _STATE["results"])
        terminalreporter.write_line(format_report(CONFIG, _STATE["results"], checks))
