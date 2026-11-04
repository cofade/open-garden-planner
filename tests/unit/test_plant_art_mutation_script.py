"""``scripts/mutation_check_plant_art.py`` stays honest between its runs (L1.7, #385).

The script is not part of the suite — it takes about an hour. But the ways it
can rot ARE checkable here, statically and in milliseconds; they are the ones
the scene-contract script's test pins (``test_scene3d_mutation_script.py``), and
the third review found the first of them live in this script too:

- "any non-zero pytest exit" counted as KILLED. pytest exits with 4 for a test
  id that has been renamed and with 2 for a collection error: a run that did
  not test the mutant at all was reported as a kill;
- a mutant whose pattern no longer matches its file exactly once mutates
  nothing (the script reports it as STALE, but only when someone runs it);
- a mutant that names a test file or a test id that no longer exists.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mutation_check_plant_art", REPO / "scripts" / "mutation_check_plant_art.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its own module up while it is defined
    spec.loader.exec_module(module)
    return module


@cache
def _test_names(relative: str) -> frozenset[str]:
    """Every ``Class``, ``Class::test`` and module-level ``test`` a test file defines."""
    text = (REPO / relative).read_bytes().decode("utf-8").replace("\r\n", "\n")
    names: set[str] = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            names.update(f"{node.name}::{child.name}" for child in node.body
                         if isinstance(child, ast.FunctionDef))
    return frozenset(names)


FAILED_LINE = "FAILED tests/unit/test_scene3d_plants.py::test_x - AssertionError"


def test_a_kill_needs_exit_code_1_and_a_named_failed_test() -> None:
    """pytest: 0 all passed, 1 tests failed, 2 interrupted (a collection error
    among them), 3 internal error, 4 usage error (a test id that does not exist),
    5 no tests collected. Only 1 WITH a ``FAILED tests/…`` line is a kill."""
    module = script()
    assert module.PYTEST_TESTS_FAILED == 1
    assert module.verdict_of(0, "") == "SURVIVED"
    assert module.verdict_of(0, FAILED_LINE) == "SURVIVED"       # the exit code decides survival
    assert module.verdict_of(1, FAILED_LINE) == "KILLED"
    assert module.verdict_of(1, "") == "BROKEN"                  # errors only: nothing FAILED
    assert [module.verdict_of(code, FAILED_LINE) for code in (2, 3, 4, 5, -1, 137)] == ["BROKEN"] * 6


def test_the_failed_test_is_read_from_pytest_s_own_summary() -> None:
    module = script()
    output = "\n".join(["...F", "E   assert 1 == 2", "ERROR tests/unit/test_a.py::test_setup - boom",
                        FAILED_LINE, "FAILED tests/unit/test_b.py::test_y", "1 failed in 0.1s"])
    assert module.failed_test_of(output) == FAILED_LINE
    assert module.failed_test_of("ERROR tests/unit/test_a.py - ImportError\n1 error in 0.2s") == ""
    assert module.failed_test_of("") == ""


class _Done:
    """What ``subprocess.run`` hands back, as far as the script reads it."""

    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


@pytest.mark.parametrize(("returncode", "stdout", "verdict"), [
    (1, f"F\n{FAILED_LINE}\n1 failed in 1.0s", "KILLED"),
    (0, "..\n2 passed in 1.0s", "SURVIVED"),
    (4, "ERROR: not found: tests/unit/test_gone.py::test_renamed\nno tests ran in 0.01s", "BROKEN"),
    (2, "ERROR tests/unit/test_scene3d_plants.py - SyntaxError\n1 error in 0.3s", "BROKEN"),
    (5, "no tests ran in 0.01s", "BROKEN"),
    (1, "E\nERROR tests/unit/test_scene3d_plants.py::test_x - fixture failed\n1 error in 1.0s", "BROKEN"),
])
def test_run_reports_what_pytest_did(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                     returncode: int, stdout: str, verdict: str) -> None:
    """``run`` on a copy of one file, with pytest replaced by its answer: the mutant
    is applied, the verdict is the run's, and the file is put back."""
    module = script()
    mutant = module.MUTANTS[0]
    target = tmp_path / mutant.path
    target.parent.mkdir(parents=True)
    original = (REPO / mutant.path).read_bytes()
    target.write_bytes(original)
    seen: list[str] = []

    def fake_pytest(*_args: object, **_kwargs: object) -> _Done:
        seen.append(target.read_bytes().decode("utf-8"))        # what pytest would have tested
        return _Done(returncode, stdout)

    monkeypatch.setattr(module.subprocess, "run", fake_pytest)
    got, detail = module.run(mutant, tmp_path)
    assert got == verdict, detail
    assert len(seen) == 1 and mutant.edits[0][1] in seen[0]      # the mutated text was on disk
    assert target.read_bytes() == original                       # … and is not any more
    if verdict == "BROKEN":
        assert f"pytest exit code {returncode}" in detail


def test_a_broken_run_fails_the_script(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    module = script()
    monkeypatch.setattr(module, "copy_tree", lambda _target: None)
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *_a, **_k: _Done(0, "971 passed in 1.0s"))   # the unmutated copy
    monkeypatch.setattr(module, "MUTANTS", module.MUTANTS[:3])
    verdicts = iter(["KILLED", "BROKEN", "KILLED"])
    monkeypatch.setattr(module, "run", lambda _mutant, _root: (next(verdicts), "detail"))
    assert module.main([]) == 1
    assert "2/3 mutants killed" in capsys.readouterr().out
    verdicts = iter(["KILLED", "KILLED", "KILLED"])
    assert module.main([]) == 0
    assert "3/3 mutants killed" in capsys.readouterr().out


def test_every_mutant_still_matches_its_file_exactly_once() -> None:
    """A pattern that matches nowhere mutates nothing; one that matches twice
    breaks two rules at once. The script calls both STALE — here the suite does,
    on every run, so a change to the builder cannot leave the script behind."""
    module = script()
    stale = [(mutant.label, module.stale(mutant, REPO)) for mutant in module.MUTANTS
             if module.stale(mutant, REPO)]
    assert stale == []
    assert all(old != new for mutant in module.MUTANTS for old, new in mutant.edits)
    labels = [mutant.label for mutant in module.MUTANTS]
    assert len(labels) == len(set(labels))                       # `-k` picks by label
    assert len(module.MUTANTS) >= 92


def test_every_test_a_mutant_names_exists() -> None:
    missing = []
    for mutant in script().MUTANTS:
        assert mutant.tests, mutant.label
        for target in mutant.tests:
            relative, _, test_id = target.partition("::")
            if not (REPO / relative).is_file() or (
                    test_id and test_id.split("[")[0] not in _test_names(relative)):
                missing.append((mutant.label, target))
    assert missing == []
