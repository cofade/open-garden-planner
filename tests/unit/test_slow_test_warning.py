"""The warning about tests that creep toward the hang guard (#918)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests import slow_test_warning
from tests.slow_test_warning import SlowTestWarning, guard_seconds, is_slow, warning_line


def _report(node_id: str, duration: float, *, when: str = "call", keywords=None):
    return SimpleNamespace(nodeid=node_id, duration=duration, when=when, keywords=keywords or {})


class _Terminal:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.sections: list[str] = []

    def section(self, title: str) -> None:
        self.sections.append(title)

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_the_guard_is_the_projects_hang_guard(pytestconfig) -> None:
    """The plugin reads the real setting, not a copy of its number."""
    assert guard_seconds(pytestconfig) == float(pytestconfig.getini("timeout")) > 0


def test_the_plugin_is_registered_for_every_run(pytestconfig) -> None:
    assert isinstance(
        pytestconfig.pluginmanager.get_plugin(slow_test_warning.PLUGIN_NAME), SlowTestWarning
    )


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


def test_only_slow_call_phases_without_their_own_timeout_are_named() -> None:
    plugin = SlowTestWarning(180.0)
    plugin.pytest_runtest_logreport(_report("a.py::slow", 120.0))
    plugin.pytest_runtest_logreport(_report("a.py::fast", 3.0))
    plugin.pytest_runtest_logreport(_report("a.py::slow_setup", 120.0, when="setup"))
    plugin.pytest_runtest_logreport(_report("a.py::own_budget", 400.0, keywords={"timeout": 1}))
    assert plugin.slow == [("a.py::slow", 120.0)]


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


def test_the_line_names_the_test_the_time_and_the_guard() -> None:
    line = warning_line("t.py::x", 124.4, 180.0, github=False)
    assert "t.py::x" in line and "124 s" in line and "180 s" in line and "#918" in line
