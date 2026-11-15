"""Name the tests that use more than half of their hang guard (#918).

pytest-timeout fails a test after its time limit (``timeout`` in
``pyproject.toml``). A test that creeps toward that limit does not fail until a
slow runner pushes it over, and then it fails only now and then. Branch
coverage makes the creep worse: the Coverage partitions trace every non-perf
test, and how much slower that makes a test depends on how much of its work is
Python (§8.10). ``test_no_point_of_a_large_plan_is_a_label_nobody_can_see`` ran
for 124-157 s under coverage for days, until runs crossed 180 s and failed the
required Coverage check (#918).

This plugin fails nothing, so it cannot be flaky itself. After the run it names
every test whose setup, call and teardown together took more than half of the
limit that applied to it (pytest-timeout times all three): the test's own ``timeout`` marker if it has one, otherwise the run's limit
(``--timeout``, then ``PYTEST_TIMEOUT``, then the ini value). Under GitHub
Actions each line is a ``::warning`` annotation, so the creep shows on the pull
request while there is still room. ``tests/conftest.py`` registers the plugin
for every run, local or CI.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest

#: The share of the hang guard above which a test is named.
SHARE = 0.5
#: The ``user_properties`` key that carries a test's own limit to the
#: controller (xdist sends ``user_properties`` with each report).
GUARD_PROPERTY = "hang_guard_s"
PLUGIN_NAME = "slow-test-warning"


def _seconds(value: object) -> float | None:
    """``value`` as seconds, or None when it is unset or not a number."""
    if value is None or value == "":
        return None
    try:
        return max(float(value), 0.0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def guard_seconds(config: pytest.Config) -> float:
    """The run's limit: ``--timeout``, then ``PYTEST_TIMEOUT``, then the ini; 0 is none."""
    try:
        option = config.getoption("timeout", None)
    except ValueError:
        option = None
    for value in (option, os.environ.get("PYTEST_TIMEOUT")):
        seconds = _seconds(value)
        if seconds is not None:
            return seconds
    try:
        ini = config.getini("timeout")
    except ValueError:  # pytest-timeout is not installed: no such ini key
        return 0.0
    return _seconds(ini) or 0.0


def marker_seconds(item: pytest.Item) -> float | None:
    """The limit of the test's own ``timeout`` marker, or None without one."""
    marker = item.get_closest_marker("timeout")
    if marker is None:
        return None
    return _seconds(marker.kwargs.get("timeout", marker.args[0] if marker.args else None))


def is_slow(seconds: float, guard: float) -> bool:
    """True when ``seconds`` is more than ``SHARE`` of a set ``guard``."""
    return guard > 0 and seconds > guard * SHARE


def warning_line(node_id: str, seconds: float, guard: float, *, github: bool) -> str:
    text = (
        f"{node_id} took {seconds:.0f} s, more than {SHARE:.0%} of its {guard:.0f} s"
        " hang guard; cut its work before a slower or traced run crosses it (#918)"
    )
    return f"::warning title=Slow test::{text}" if github else f"SLOW TEST: {text}"


class SlowTestWarning:
    """Collects the slow tests and names them in the terminal summary."""

    def __init__(self, guard: float) -> None:
        self.guard = guard
        self.slow: list[tuple[str, float, float]] = []
        self._running: dict[str, tuple[float, float]] = {}

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[Any]
    ) -> Generator[None, pytest.TestReport, pytest.TestReport]:
        # Runs where the test runs (an xdist worker), the only place that sees
        # the marker; the controller gets the limit with each report.
        report = yield
        seconds = marker_seconds(item)
        if seconds is not None:
            report.user_properties.append((GUARD_PROPERTY, seconds))
        return report

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Under xdist the controller receives every worker's reports here, so
        # the summary of the controller covers the whole run. A test's phases
        # are summed; its teardown report, which every test gets, decides.
        seconds, guard = self._running.get(report.nodeid, (0.0, self.guard))
        for key, value in report.user_properties:
            if key == GUARD_PROPERTY:
                guard = float(value)
        seconds += report.duration
        if report.when != "teardown":
            self._running[report.nodeid] = (seconds, guard)
            return
        self._running.pop(report.nodeid, None)
        if is_slow(seconds, guard):
            self.slow.append((report.nodeid, seconds, guard))

    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if not self.slow:
            return
        github = os.environ.get("GITHUB_ACTIONS") == "true"
        terminalreporter.section("tests near the hang guard (#918)")
        for node_id, seconds, guard in sorted(self.slow, key=lambda entry: -entry[1]):
            terminalreporter.write_line(warning_line(node_id, seconds, guard, github=github))


def register(config: pytest.Config) -> None:
    """Register the warning once per process."""
    if config.pluginmanager.get_plugin(PLUGIN_NAME) is None:
        config.pluginmanager.register(SlowTestWarning(guard_seconds(config)), PLUGIN_NAME)


def pytest_configure(config: pytest.Config) -> None:
    """Lets ``-p tests.slow_test_warning`` load it into a run without this conftest."""
    register(config)
