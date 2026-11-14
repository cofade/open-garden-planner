"""Name the tests that use more than half of the per-test hang guard (#918).

pytest-timeout fails a test after ``timeout`` seconds (``pyproject.toml``). A
test that creeps toward that limit does not fail until a slow runner pushes it
over, and then it fails only now and then. Branch coverage makes the creep
worse: the Coverage partitions run every non-perf test 2.5 to 3 times slower
than the Test job. ``test_no_point_of_a_large_plan_is_a_label_nobody_can_see``
took 33-76 s in the Test job and 124-157 s under coverage for days, until runs
crossed 180 s and failed the required Coverage check (#918).

This plugin fails nothing, so it cannot be flaky itself. After the run it names
every test whose call phase took more than half of the guard. Under GitHub
Actions each line is a ``::warning`` annotation, so the creep shows on the pull
request while there is still room. A test with its own ``timeout`` marker set
its budget on purpose and is left out. ``tests/conftest.py`` registers the
plugin for every run, local or CI.
"""

from __future__ import annotations

import os

import pytest

#: The share of the hang guard above which a test is named.
SHARE = 0.5


def guard_seconds(config: pytest.Config) -> float:
    """The per-test hang guard in seconds, or 0 when there is none."""
    try:
        value = config.getini("timeout")
    except ValueError:  # pytest-timeout is not installed: no such ini key
        return 0.0
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def is_slow(seconds: float, guard: float) -> bool:
    """True when ``seconds`` is more than ``SHARE`` of a set ``guard``."""
    return guard > 0 and seconds > guard * SHARE


def warning_line(node_id: str, seconds: float, guard: float, *, github: bool) -> str:
    text = (
        f"{node_id} took {seconds:.0f} s, more than {SHARE:.0%} of the {guard:.0f} s"
        " hang guard; under branch coverage it runs 2.5 to 3 times slower (#918)"
    )
    return f"::warning title=Slow test::{text}" if github else f"SLOW TEST: {text}"


class SlowTestWarning:
    """Collects the slow call phases and names them in the terminal summary."""

    def __init__(self, guard: float) -> None:
        self.guard = guard
        self.slow: list[tuple[str, float]] = []

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Under xdist the controller receives every worker's reports here, so
        # the summary of the controller covers the whole run.
        if report.when != "call" or "timeout" in report.keywords:
            return
        if is_slow(report.duration, self.guard):
            self.slow.append((report.nodeid, report.duration))

    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if not self.slow:
            return
        github = os.environ.get("GITHUB_ACTIONS") == "true"
        terminalreporter.section("tests near the hang guard (#918)")
        for node_id, seconds in sorted(self.slow, key=lambda entry: -entry[1]):
            terminalreporter.write_line(warning_line(node_id, seconds, self.guard, github=github))


PLUGIN_NAME = "slow-test-warning"


def register(config: pytest.Config) -> None:
    """Register the warning once, when the run has a hang guard."""
    guard = guard_seconds(config)
    if guard > 0 and config.pluginmanager.get_plugin(PLUGIN_NAME) is None:
        config.pluginmanager.register(SlowTestWarning(guard), PLUGIN_NAME)
