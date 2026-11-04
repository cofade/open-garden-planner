"""``scripts/mutation_check_scene3d.py`` stays honest between its runs (L1.1 fix round 2, #385).

The script is not part of the suite — it rewrites source files and takes
minutes. But two ways it can rot ARE checkable here, statically and in
milliseconds, and the re-review found the second one live:

- a mutant whose pattern no longer matches its file exactly once mutates
  nothing (the script reports it as STALE, but only when someone runs it);
- a mutant that names a single test id which has since been renamed makes
  pytest exit with code 4 — and "any non-zero exit" used to count as KILLED.
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
        "mutation_check_scene3d", REPO / "scripts" / "mutation_check_scene3d.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its own module up while it is defined
    spec.loader.exec_module(module)
    return module


@cache
def _text(relative: str) -> str:
    return (REPO / relative).read_bytes().decode("utf-8").replace("\r\n", "\n")


@cache
def _test_names(relative: str) -> frozenset[str]:
    """Every ``Class::test`` and module-level ``test`` a test file defines."""
    names: set[str] = set()
    for node in ast.parse(_text(relative)).body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            names.update(f"{node.name}::{child.name}" for child in node.body
                         if isinstance(child, ast.FunctionDef))
    return frozenset(names)


def test_only_failed_tests_count_as_a_kill() -> None:
    """Review round 2, P2-10. pytest: 0 all passed, 1 tests failed, 2 interrupted
    (a collection error among them), 3 internal error, 4 usage error (a test id
    that does not exist), 5 no tests collected."""
    module = script()
    assert module.verdict_of(0) == "SURVIVED"
    assert module.verdict_of(1) == "KILLED"
    assert [module.verdict_of(code) for code in (2, 3, 4, 5, -1, 137)] == ["BROKEN"] * 6


def test_a_broken_run_fails_the_script(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    module = script()
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *_a, **_k: type("Done", (), {"stdout": ""})())  # a clean tree
    verdicts = iter(["KILLED", "BROKEN", "KILLED"])
    monkeypatch.setattr(module, "run", lambda _mutant: (next(verdicts), "detail"))
    monkeypatch.setattr(module, "MUTANTS", module.MUTANTS[:3])
    assert module.main([]) == 1
    assert "2/3 mutants killed" in capsys.readouterr().out
    verdicts = iter(["KILLED", "KILLED", "KILLED"])
    assert module.main([]) == 0


def test_every_mutant_still_matches_its_file_exactly_once() -> None:
    """A pattern that matches nowhere mutates nothing; one that matches twice
    breaks two rules at once. The script calls both STALE — here the suite does,
    on every run, so a refactoring of the pipeline cannot leave it behind."""
    stale = [(mutant.label, _text(mutant.path).count(mutant.old)) for mutant in script().MUTANTS
             if _text(mutant.path).count(mutant.old) != 1]
    assert stale == []
    assert all(mutant.old != mutant.new for mutant in script().MUTANTS)
    assert len(script().MUTANTS) >= 180


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
