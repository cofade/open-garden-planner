"""The slow-test warning in a real pytest run with xdist workers (#918).

The unit tests feed the plugin hand-made reports. This runs it the way CI
does: tests on xdist workers, the summary in the controller, a ``timeout``
marker read on the worker and carried over with the report, and the
command-line limit winning over the ini value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INNER_TESTS = """\
import time

import pytest


def test_slow():
    time.sleep(1.2)


def test_fast():
    pass


@pytest.mark.timeout(60)
def test_own_budget_quiet():
    time.sleep(1.2)


@pytest.mark.timeout(3)
def test_own_budget_named():
    time.sleep(1.6)
"""


def test_the_controller_names_the_slow_worker_tests_against_their_own_guard(tmp_path: Path) -> None:
    (tmp_path / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    # A real ini value, which the command line's limit must beat.
    (tmp_path / "pytest.ini").write_text("[pytest]\ntimeout = 60\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONUTF8="1", GITHUB_ACTIONS="true")
    for name in ("PYTEST_TIMEOUT", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(name, None)
    run = subprocess.run(
        [
            sys.executable, "-m", "pytest", "test_inner.py", "-q", "-n", "2",
            "-p", "tests.slow_test_warning", "-p", "no:cacheprovider",
            # The ini says 60 s; the command line's 2 s must win (a 1 s threshold).
            "--timeout=2",
        ],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300, check=False,
    )
    output = run.stdout + run.stderr
    assert run.returncode == 0, output
    prefix = "::warning title=Slow test::"
    warnings = [line for line in output.splitlines() if line.startswith(prefix)]
    named = {line.removeprefix(prefix).split(" took ")[0] for line in warnings}
    assert named == {"test_inner.py::test_slow", "test_inner.py::test_own_budget_named"}, output
    by_test = {line.removeprefix(prefix).split(" took ")[0]: line for line in warnings}
    # The run's limit (the command line, not the ini) for the unmarked test,
    # the marker's own limit for the marked one.
    assert "of its 2 s hang guard" in by_test["test_inner.py::test_slow"], output
    assert "of its 3 s hang guard" in by_test["test_inner.py::test_own_budget_named"], output
