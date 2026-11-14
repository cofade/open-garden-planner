"""The warning about tests that creep toward the hang guard (#918)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests import slow_test_warning
from tests.slow_test_warning import (
    GUARD_PROPERTY,
    SlowTestWarning,
    guard_seconds,
    is_slow,
    marker_seconds,
    warning_line,
)


def _report(node_id: str, duration: float, *, when: str = "call", properties=()):
    return SimpleNamespace(
        nodeid=node_id, duration=duration, when=when, user_properties=list(properties)
    )


class _Terminal:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.sections: list[str] = []

    def section(self, title: str) -> None:
        self.sections.append(title)

    def write_line(self, line: str) -> None:
        self.lines.append(line)


class _Config:
    def __init__(self, *, option=None, ini="180") -> None:
        self._option, self._ini = option, ini

    def getoption(self, name, default=None):
        return self._option

    def getini(self, name):
        if self._ini is None:
            raise ValueError("unknown configuration value: 'timeout'")
        return self._ini


def test_the_guard_is_the_projects_hang_guard(pytestconfig, monkeypatch) -> None:
    """The plugin reads the real setting, not a copy of its number."""
    monkeypatch.delenv("PYTEST_TIMEOUT", raising=False)
    if pytestconfig.getoption("timeout", None) is None:
        assert guard_seconds(pytestconfig) == float(pytestconfig.getini("timeout")) > 0


def test_the_plugin_is_registered_for_every_run(pytestconfig) -> None:
    assert isinstance(
        pytestconfig.pluginmanager.get_plugin(slow_test_warning.PLUGIN_NAME), SlowTestWarning
    )


def test_the_command_line_then_the_environment_then_the_ini_set_the_guard(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_TIMEOUT", raising=False)
    assert guard_seconds(_Config(ini="180")) == 180.0
    monkeypatch.setenv("PYTEST_TIMEOUT", "300")
    assert guard_seconds(_Config(ini="180")) == 300.0
    assert guard_seconds(_Config(option=100.0, ini="180")) == 100.0
    assert guard_seconds(_Config(option=0.0, ini="180")) == 0.0  # --timeout=0 turns it off
    monkeypatch.delenv("PYTEST_TIMEOUT")
    assert guard_seconds(_Config(ini=None)) == 0.0  # pytest-timeout is not installed
    assert guard_seconds(_Config(ini="")) == 0.0


@pytest.mark.parametrize(
    ("mark", "seconds"),
    [
        (pytest.mark.timeout(900), 900.0),
        (pytest.mark.timeout(timeout=42), 42.0),
        (pytest.mark.timeout(0), 0.0),
        (None, None),
    ],
)
def test_a_tests_own_marker_sets_its_guard(mark, seconds) -> None:
    item = SimpleNamespace(get_closest_marker=lambda _name: mark.mark if mark else None)
    assert marker_seconds(item) == seconds


@pytest.mark.parametrize(
    ("seconds", "guard", "slow"),
    [
        (90.0, 180.0, False),  # exactly half is not named
        (90.5, 180.0, True),
        (157.0, 180.0, True),  # #918's test under coverage, before it failed
        (49.0, 180.0, False),
        (1000.0, 0.0, False),  # no guard, nothing to compare with
    ],
)
def test_more_than_half_of_the_guard_is_slow(seconds: float, guard: float, slow: bool) -> None:
    assert is_slow(seconds, guard) is slow


def test_only_slow_call_phases_are_named_against_the_guard_that_applies() -> None:
    plugin = SlowTestWarning(180.0)
    plugin.pytest_runtest_logreport(_report("a.py::slow", 120.0))
    plugin.pytest_runtest_logreport(_report("a.py::fast", 3.0))
    plugin.pytest_runtest_logreport(_report("a.py::slow_setup", 120.0, when="setup"))
    plugin.pytest_runtest_logreport(
        _report("a.py::own_budget_quiet", 400.0, properties=[(GUARD_PROPERTY, 900.0)])
    )
    plugin.pytest_runtest_logreport(
        _report("a.py::own_budget_named", 500.0, properties=[(GUARD_PROPERTY, 900.0)])
    )
    plugin.pytest_runtest_logreport(
        _report("a.py::guard_off", 999.0, properties=[(GUARD_PROPERTY, 0.0)])
    )
    assert plugin.slow == [("a.py::slow", 120.0, 180.0), ("a.py::own_budget_named", 500.0, 900.0)]


def test_the_summary_is_a_github_warning_only_under_github_actions(monkeypatch) -> None:
    plugin = SlowTestWarning(180.0)
    plugin.pytest_runtest_logreport(_report("a.py::b", 100.0))
    plugin.pytest_runtest_logreport(_report("a.py::c", 150.0))

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    terminal = _Terminal()
    plugin.pytest_terminal_summary(terminal)
    assert terminal.lines[0].startswith("::warning title=Slow test::a.py::c took 150 s")
    assert terminal.lines[1].startswith("::warning title=Slow test::a.py::b took 100 s")

    monkeypatch.delenv("GITHUB_ACTIONS")
    terminal = _Terminal()
    plugin.pytest_terminal_summary(terminal)
    assert terminal.lines[0].startswith("SLOW TEST: a.py::c took 150 s")


def test_a_run_without_slow_tests_prints_nothing() -> None:
    terminal = _Terminal()
    SlowTestWarning(180.0).pytest_terminal_summary(terminal)
    assert terminal.lines == [] and terminal.sections == []


def test_the_line_names_the_test_the_time_and_its_guard() -> None:
    line = warning_line("t.py::x", 124.4, 900.0, github=False)
    assert "t.py::x" in line and "124 s" in line and "its 900 s" in line and "#918" in line
