"""Measure how much of the four array dialogs the test suite actually executes.

Committed so the #395 coverage figure has a source a reader can re-run, like the
two task-window harnesses. Measured 2026-10 (AST-derived statements, same method on
both trees):

    master (c42532d) : 325 statements,   4 run, 321 never run
    this branch      : 325 statements, 219 run, 106 never run
    -> 215 newly covered, 106 still unrun

Statement lines come from AST ``ast.stmt`` nodes. A blank/comment text heuristic
was tried first and rejected: it counts the continuation lines of a multi-line
call as separate statements, which inflates the denominator and made the master
baseline read 317 rather than 321 -- which is how a *before* number ended up in
the documentation quoted as an *after* number.

Usage (from the repo root, or a worktree of another ref):

    venv/Scripts/python.exe scripts/measure_array_tool_coverage.py
    venv/Scripts/python.exe scripts/measure_array_tool_coverage.py <other-worktree>

A second argument overrides which tests are run; the default is the whole suite,
because that is what "never run" means on master (where the array tests do not yet
exist).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
EXTRA = sys.argv[2:]

# The interpreter running this script. A hardcoded venv path made this harness
# unrunnable off the author's machine — the same defect fixed in
# `test_status_message_route.py` one commit earlier, reintroduced here.
PYTHON = Path(sys.executable)
TARGET_REL = "ui/canvas/canvas_view.py"
TARGET = REPO / "src" / "open_garden_planner" / TARGET_REL

ENTRY_POINTS = (
    "create_linear_array",
    "create_grid_array",
    "create_circular_array",
    "create_array_along_path",
)

#: The new test file, when it exists. On master it does not (that IS the point),
#: so the baseline runs the whole suite instead — which is what "never run" means.
DEFAULT_TESTS = ["tests/"]


def statement_lines() -> dict[str, set[int]]:
    """Executable lines per entry point."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    out: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ENTRY_POINTS:
            continue
        lines: set[int] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.stmt):
                lines.add(child.lineno)
        out[node.name] = lines
    return out


def executed_lines(tests: list[str]) -> set[int]:
    """Lines coverage recorded as executed in the target module.

    ``tests`` is passed in rather than closed over: the docstring promises a second
    argument scopes the run, and an earlier version parsed that argument, printed
    it, and then hardcoded the default here — a promise the code did not keep.
    """
    env = dict(os.environ, PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen")
    subprocess.run(
        [str(PYTHON), "-m", "coverage", "run", "-m", "pytest", *tests, "-q",
         "--timeout=300", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, env=env, check=False,
    )
    report = REPO / "coverage-report.json"
    subprocess.run(
        [str(PYTHON), "-m", "coverage", "json", "-o", str(report)],
        cwd=REPO, capture_output=True, text=True, env=env, check=False,
    )
    if not report.exists():
        raise SystemExit("coverage produced no JSON report")
    files = json.loads(report.read_text(encoding="utf-8")).get("files", {})
    entry = next(
        (v for k, v in files.items()
         if k.replace("\\", "/").endswith(TARGET_REL)),
        None,
    )
    if entry is None:
        raise SystemExit(
            f"{TARGET_REL} is absent from the report; recorded files: "
            f"{sorted(files)[:5]}"
        )
    return set(entry.get("executed_lines", []))


def main() -> int:
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    tests = EXTRA or DEFAULT_TESTS
    print(f"repo   : {REPO}")
    print(f"branch : {branch}")
    print(f"target : {TARGET_REL}")
    print(f"tests  : {' '.join(tests)}")
    print()

    executed = executed_lines(tests)
    per: dict[str, dict[str, int]] = {}
    for name, lines in statement_lines().items():
        per[name] = {
            "statements": len(lines),
            "run": len(lines & executed),
            "never_run": len(lines - executed),
        }

    totals = {"statements": 0, "run": 0, "never_run": 0}
    for name in ENTRY_POINTS:
        row = per[name]
        for k in totals:
            totals[k] += row[k]
        print(
            f"  {name:<24} statements={row['statements']:>3}  "
            f"run={row['run']:>3}  never_run={row['never_run']:>3}"
        )
    print()
    print(f"  {'TOTAL':<24} statements={totals['statements']:>3}  "
          f"run={totals['run']:>3}  never_run={totals['never_run']:>3}")
    print(f"RESULT {json.dumps(totals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
