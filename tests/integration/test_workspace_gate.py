"""The workspace gate's own safety, proven before the gate is used (Phase 17 L1.3).

``workspace_gate_hook.py`` drives the REAL app — ``main()`` from source, and the frozen
exe as a runtime hook — through the 3D workspace: open a plan, enter 3D, close. A
plan load writes Recent Files and a clean close writes the window geometry, so a
scripted run that builds its stores on the production names damages the
developer's own settings (it has happened: COMMON rules, §8.10). These tests show,
in the default tier and without a GPU, that it cannot:

- a child that runs the app's own ``main()`` on a plan builds every store on the
  throw-away key — the Recent Files entry is read back from THAT key;
- the guard fails closed: a store under any other organisation is refused before it
  exists (exit code 97) — shown with a decoy, never with the real names;
- the hook is the first thing the child imports, and imports nothing of the app.

The scenarios that need a real window are in ``test_view3d_workspace_render.py``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.app import settings as app_settings
from tests.conftest import PRODUCTION_STORE, TEST_ORGANIZATION
from tests.integration.quick3d_render_support import isolated_env
from tests.unit.test_quick3d_packaging import child_environment_problems

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHILD = HERE / "workspace_gate_child.py"
#: The hook is READ here, never imported: importing it rebinds the settings names of
#: the importing process — which is its job in a child, and would move this test
#: process off its own key (conftest's per-test check caught exactly that).
HOOK = HERE / "workspace_gate_hook.py"
REFUSED = 97
PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
FAILED_STEPS = {"REFUSED", "TIMEOUT", "EXCEPTION", "FORCED_QUIT"}


def gate_spec(scratch: Path, scenario: str, **options: Any) -> tuple[Path, Path, str]:
    """Write a scenario file; returns (the file, where the report goes, the store's name)."""
    store = f"Open Garden Planner Gate {uuid.uuid4().hex[:12]}"
    out = scratch / "gate-result.json"
    spec = scratch / "gate-spec.json"
    spec.write_text(json.dumps({"scenario": scenario, "out": str(out), "store": store,
                                **options}), encoding="utf-8")
    return spec, out, store


def read_report(out: Path) -> dict[str, Any]:
    assert out.is_file(), "the gate wrote no report"
    return json.loads(out.read_text(encoding="utf-8"))


def test_main_on_a_plan_builds_every_store_on_the_throw_away_key(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE proof. The app's own ``main()``, given a plan on its command line (its
    3D workspace is always there): it opens the plan (Recent Files is written), shows the
    window, and is closed by the scenario (the window geometry is written)."""
    spec, out, store = gate_spec(tmp_path, "never")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, str(CHILD), str(PLAN)],
        env=isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen", OGP_WORKSPACE_GATE=str(spec)),
        capture_output=True, text=True, timeout=170, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-3000:]
    report = read_report(out)
    steps = [entry["step"] for entry in report["steps"]]
    assert steps[0] == "start" and steps[-2:] == ["closing", "closed"], steps
    assert not FAILED_STEPS & set(steps) and report["late"] is False
    shown = next(entry for entry in report["steps"] if entry["step"] == "shown")
    assert shown["mode"] == "plan" and shown["state"] == "not_started"
    # every store this process built: on the throw-away key, by Qt's own account
    assert report["stores"] == [[TEST_ORGANIZATION, store]]
    assert list(PRODUCTION_STORE) not in report["stores"]
    assert PRODUCTION_STORE[0] != TEST_ORGANIZATION, "the control: these two differ"
    # … and the two writes such a run makes went INTO that store: the plan it opened
    # is its Recent File, and closing saved the window geometry
    closed = report["steps"][-1]
    assert closed["accepted"] is True and closed["geometry_saved"] is True
    assert [Path(entry) for entry in closed["recent_files"]] == [PLAN]
    # … which the child emptied when it left: this process's own key never saw any of it
    monkeypatch.setattr(app_settings, "_settings_instance", None)
    assert str(PLAN) not in app_settings.AppSettings().recent_files


_DECOY = r'''
import sys
sys.path.insert(0, sys.argv[1])
import workspace_gate_hook
import open_garden_planner.app.settings as settings
print("NAMES", settings.ORGANIZATION_NAME, "|", settings.APPLICATION_NAME, flush=True)
if sys.argv[2] == "decoy":
    settings.ORGANIZATION_NAME = "decoy_organisation_of_a_test"   # "somebody put the names back"
    settings.create_qsettings()
    print("BUILT A STORE", flush=True)
'''


def test_the_guard_refuses_a_store_under_any_other_organisation(tmp_path: Path) -> None:
    """Fail closed. A decoy organisation stands in for the production one: the process
    ends with exit code 97 BEFORE the store exists, and the report says why."""
    spec, out, store = gate_spec(tmp_path, "never")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _DECOY, str(HERE), "decoy"],
        env=isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen", OGP_WORKSPACE_GATE=str(spec)),
        capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert proc.returncode == REFUSED, proc.stderr[-2000:]
    assert f"\nREFUSED = {REFUSED}\n" in HOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert f"NAMES {TEST_ORGANIZATION} | {store}" in proc.stdout
    assert "BUILT A STORE" not in proc.stdout
    refused = read_report(out)["steps"][-1]
    assert refused["step"] == "REFUSED"
    assert refused["organization"] == "decoy_organisation_of_a_test"


def test_without_a_scenario_the_hook_still_moves_the_store(tmp_path: Path) -> None:
    """The frozen gate build carries the hook always: started without a scenario (its
    smoke test, its self-test) it must still never use the production names."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _DECOY, str(HERE), "names"],
        env=isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen", OGP_WORKSPACE_GATE=""),
        capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    (names,) = [line for line in proc.stdout.splitlines() if line.startswith("NAMES ")]
    assert names.startswith(f"NAMES {TEST_ORGANIZATION} | Open Garden Planner Gate ")


def test_the_hook_is_imported_before_the_app_and_imports_nothing_of_it() -> None:
    child = ast.parse(CHILD.read_text(encoding="utf-8"))
    imports = [node for node in child.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = [(node.names[0].name if isinstance(node, ast.Import) else node.module or "")
             for node in imports]
    assert names.index("workspace_gate_hook") < names.index("open_garden_planner.main")
    assert [name for name in names if name.startswith("open_garden_planner")] == [
        "open_garden_planner.main"]
    tree = ast.parse(HOOK.read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    assert top_level <= set(sys.stdlib_module_names) | {"__future__"}, top_level
    # it names the factory to wrap it, and never constructs a store class itself (§8.8)
    assert "QSettings(" not in HOOK.read_text(encoding="utf-8")


def test_nothing_in_the_test_tree_imports_the_hook_into_the_test_process() -> None:
    """Importing the hook rebinds the importer's settings names. Only the child runner
    may — and the measuring scenarios, which exist inside that child alone; a test
    reads the file."""
    importers = []
    for path in sorted((REPO / "tests").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [f"{node.module}.{alias.name}" for alias in node.names]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            if any(name.split(".")[-1] == "workspace_gate_hook" or "workspace_gate_hook" in
                   name.split(".") for name in names):
                importers.append(path.name)
    assert sorted(set(importers)) == ["workspace_default_measure.py", "workspace_gate_child.py",
                                      "workspace_gate_measure.py"]
    # … and nothing imports THOSE into the test process either (the default flip's
    # scenarios, L1.9, use the workspace story's tools — inside the child)
    children = {"workspace_gate_hook.py", "workspace_default_measure.py"}
    for path in sorted((REPO / "tests").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for name in ("workspace_gate_child", "workspace_gate_measure", "workspace_default_measure"):
            assert f"import {name}" not in source or path.name in children, path


@pytest.mark.parametrize("name", [
    "test_workspace_gate.py", "test_view3d_workspace.py", "test_view3d_workspace_render.py",
    "workspace_gate_hook.py", "workspace_gate_child.py", "workspace_gate_measure.py",
    "test_view3d_default_render.py", "workspace_default_measure.py",
])
def test_every_child_of_the_workspace_tests_gets_its_environment_from_the_helper(name: str) -> None:
    """The engine story's rule (``child_environment_problems``), held here too: no child
    is ever handed the developer's own environment, data or profile."""
    path = HERE / name
    if not path.is_file():
        pytest.skip(f"{name} is not part of this checkout")
    problems, _children = child_environment_problems(path.read_text(encoding="utf-8"), name)
    assert not problems, "\n".join(problems)
