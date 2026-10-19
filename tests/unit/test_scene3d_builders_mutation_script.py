"""``scripts/mutation_check_built_world.py`` stays honest between its runs (Phase 17 L1.6).

The script is not part of the suite: it rewrites source files and takes minutes.
What can rot between two runs of it is checked here, statically, on every run —
as ``test_scene3d_mutation_script.py`` does for the scene contract's script:

- a mutant whose text is no longer in its file exactly once mutates nothing;
- a mutant whose tests or ``-k`` words no longer exist selects nothing, and pytest
  then exits with a code that is not "a test failed";
- only "pytest exit 1 with a failed test" is a kill.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mutation_check_built_world", REPO / "scripts" / "mutation_check_built_world.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its own module up while it is defined
    spec.loader.exec_module(module)
    return module


@cache
def _text(relative: str) -> str:
    return (REPO / relative).read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_only_exit_code_1_with_a_failed_test_is_a_kill() -> None:
    module = script()
    assert module.verdict_of(0, False) == "SURVIVED"
    assert module.verdict_of(1, True) == "KILLED"
    assert module.verdict_of(1, False) == "BROKEN"  # a fixture error, a collection error
    assert [module.verdict_of(code, True) for code in (2, 3, 4, 5, -1, 137)] == ["BROKEN"] * 6


def test_every_mutant_still_matches_its_file_exactly_once() -> None:
    mutants = script().MUTANTS
    stale = [(mutant.label, _text(mutant.path).count(mutant.old)) for mutant in mutants
             if _text(mutant.path).count(mutant.old) != 1]
    assert stale == []
    assert all(mutant.old != mutant.new for mutant in mutants)
    assert len({mutant.label for mutant in mutants}) == len(mutants) >= 30


def test_every_test_file_and_every_selection_word_exists() -> None:
    """``-k`` matches test names, class names and parameter ids. Every word of every
    selection must occur in one of the files the mutant runs — a renamed test would
    otherwise leave a mutant that selects nothing (pytest exit 5: BROKEN, not killed)."""
    missing = []
    for mutant in script().MUTANTS:
        assert mutant.tests, mutant.label
        for relative in mutant.tests:
            if not (REPO / relative).is_file():
                missing.append((mutant.label, relative))
        texts = [_text(relative) for relative in mutant.tests if (REPO / relative).is_file()]
        for word in re.split(r"\s+or\s+", mutant.select) if mutant.select else []:
            assert re.fullmatch(r"[\w\-]+", word), (mutant.label, word)  # plain words only
            if not any(word in text for text in texts):
                missing.append((mutant.label, word))
    assert missing == []


def test_a_run_that_is_not_all_kills_fails_the_script(monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    module = script()
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *_a, **_k: type("Done", (), {"stdout": ""})())  # a clean tree
    monkeypatch.setattr(module, "MUTANTS", module.MUTANTS[:3])
    for verdicts, expected, line in ((["KILLED", "BROKEN", "KILLED"], 1, "2/3 mutants killed"),
                                     (["KILLED", "SURVIVED", "STALE"], 1, "1/3 mutants killed"),
                                     (["KILLED", "KILLED", "KILLED"], 0, "3/3 mutants killed")):
        answers = iter(verdicts)
        monkeypatch.setattr(module, "run", lambda _mutant, _appdata, answers=answers: (next(answers), "…"))
        assert module.main([]) == expected
        assert line in capsys.readouterr().out


def test_the_script_itself_imports_nothing_of_the_app_and_isolates_its_children() -> None:
    """The last pass: can this script reach the owner's settings or data? Not by
    itself — it imports the standard library only, so no module of the app (and no
    ``QSettings``) exists in its process — and not through the test runs it starts:
    those are pytest, whose ``tests/conftest.py`` rebinds the settings names and
    redirects the data folders before any app import, and they get a throw-away
    ``APPDATA`` on top. Read from the source, so a later import is noticed."""
    source = _text("scripts/mutation_check_built_world.py")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.add((node.module or "").split(".")[0])
    assert imported == {"__future__", "argparse", "os", "subprocess", "sys", "tempfile",
                        "dataclasses", "pathlib"}
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}
    # every child is ``python -m pytest …`` with the throw-away APPDATA — nothing else is started
    module = script()
    assert 'command = [sys.executable, "-m", "pytest", *mutant.tests' in source
    assert 'env={**os.environ, "APPDATA": appdata}' in source
    assert source.count("subprocess.run(") == 2  # the test run, and ``git status`` for the dirty check
    assert "tempfile.TemporaryDirectory(prefix=" in source and module.REPO == REPO


def test_it_refuses_a_dirty_tree(monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    module = script()
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *_a, **_k: type("Done", (), {"stdout": " M src/x.py\n"})())
    monkeypatch.setattr(module, "run", lambda *_a: pytest.fail("a mutant ran on a dirty tree"))
    assert module.main([]) == 2
    assert "refusing to run" in capsys.readouterr().out
