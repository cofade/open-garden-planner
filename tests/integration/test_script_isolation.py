"""A script that imports the app keeps its hands off the user's own stores.

Phase 17 L1.1 (#385), section 8.10 "Test isolation". ``tests/conftest.py``
isolates the PYTEST process. A script under ``scripts/`` runs outside it, where
the app's settings are the user's own (on Windows a registry key that no
environment variable moves) and so are its app-data folder and every
``QStandardPaths`` location; ``ProjectManager.save()`` and ``.load()`` end with
``add_recent_file``. Scripts run that way replaced a developer's whole Recent
Files list with fixture paths (found 2026-10-11).

``scripts/script_isolation.py`` is what a script calls to prevent that. Two
things are pinned here:

- EVERY script under ``scripts/`` is read (its AST): one that imports the app or
  builds a Qt application either calls the isolation — in the right places — or
  stands on ``NOT_ISOLATED`` with the reason. A new script cannot be forgotten.
- each script that calls it is RUN, as a script, in a child process — and the
  child is watched: every settings store it builds, where its profile variables
  and Qt's locations point when it ends, and whether anything appeared in the
  profile it was started with.

The child is never given the real names: a decoy pair stands where the
production names would be, so a script that failed to isolate itself would write
there (and this test would say so) — not into anybody's settings.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import script_isolation  # registered by tests/conftest.py: the module the scripts import

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"

#: Scripts that import the app or build a Qt application and do NOT call the
#: isolation — each with the reason. Read before it was written; an entry that
#: is no longer needed fails ``test_the_exemptions_are_all_needed``.
NOT_ISOLATED: dict[str, str] = {
    "script_isolation.py":
        "the isolation itself: it imports app.settings inside the function that rebinds its names",
    "dogfood_agent_api.py":
        "drives the developer's REAL app on purpose (the Agent API against the installed exe): it "
        "snapshots the real settings, Recent Files included, and restores them itself",
    "live_capture_harness.py":
        "a live harness for the real map picker with the developer's own API key and web profile; "
        "it builds a dialog and saves or loads no plan",
    "validate_exports.py":
        "a personal one-off: it loads the developer's OWN plan from Downloads and exports it — the "
        "Recent Files entry it records is that plan",
    "svg_preview.py":
        "builds a QApplication to rasterise one SVG; imports nothing of the app, builds no store",
    "measure_harvest_offsets.py":
        "imports the species data and nothing with a store; no application, no plan; three unit "
        "tests import it into the pytest process, where an isolation of its own would be wrong",
    "measure_task_window_sweep.py":
        "imports the species database and the task generator; no application, no plan saved or "
        "loaded; a unit test imports it into the pytest process",
    "measure_roof_overhang.py":
        "imports core.roof_style and core.scene3d's building and roof builders (Qt-free); no "
        "application, no store, no plan saved or loaded",
    "probe_widget_leaks.py":
        "master's #515 widget-leak probe: before it builds an application it imports "
        "tests.conftest, whose module-level code IS the suite's isolation (settings names, "
        "APPDATA / XDG variables, the redirected Qt locations); it saves and loads no plan",
}
#: Scripts of the other Phase 17 L1 stories, not on this branch: named here so that
#: merging them does not turn this test red, with what was READ on their branches
#: (L1.6 5f4692f, L1.7 5c44578) — their owners confirm the reason or call the isolation.
ARRIVING_WITH_L1: dict[str, str] = {
    "make_sprite_resolution_golden.py":
        "L1.7: imports core.plant_art and core.plant_renderer; no application, no store, no plan",
    "measure_built_world_shadows.py":
        "L1.6: imports core.scene3d and core.shadow_geometry (Qt-free); no application, no store",
    "measure_plant_art_3d.py":
        "L1.7: loads the bench plans — behind an isolation of its own (environment and settings "
        "names), written before script_isolation existed; to move onto it",
}
_QT_APPLICATIONS = {"QApplication", "QGuiApplication", "QCoreApplication"}


def _tree(script: str) -> ast.Module:
    return ast.parse((SCRIPTS / script).read_text(encoding="utf-8"))


def _imported(node: ast.AST) -> set[str]:
    """The top-level packages ``node`` imports, anywhere inside it."""
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Import):
            names.update(alias.name.split(".")[0] for alias in inner.names)
        elif isinstance(inner, ast.ImportFrom) and inner.module:
            names.add(inner.module.split(".")[0])
    return names


def _reaches_the_app(tree: ast.Module) -> bool:
    """Imports ``open_garden_planner`` anywhere, or instantiates a Qt application."""
    builds = any(isinstance(node, ast.Call) and (
        getattr(node.func, "id", None) in _QT_APPLICATIONS
        or getattr(node.func, "attr", None) in _QT_APPLICATIONS) for node in ast.walk(tree))
    return builds or "open_garden_planner" in _imported(tree)


def _calls_the_isolation(tree: ast.Module) -> bool:
    return any(isinstance(node, ast.Call) and ast.unparse(node.func) == "script_isolation.isolate"
               for node in ast.walk(tree))


ALL_SCRIPTS = sorted(path.name for path in SCRIPTS.glob("*.py"))
SELF_ISOLATING = [script for script in ALL_SCRIPTS if _calls_the_isolation(_tree(script))]


def test_the_enumeration_finds_the_scripts_that_isolate_themselves() -> None:
    """Were the reading of the scripts broken, every test below would pass on nothing."""
    assert {"make_bench_plans.py", "make_scene3d_edge_plan.py", "measure_region_work.py"} <= set(SELF_ISOLATING)
    assert len(ALL_SCRIPTS) >= 35 and len([s for s in ALL_SCRIPTS if _reaches_the_app(_tree(s))]) >= 11


@pytest.mark.parametrize("script", ALL_SCRIPTS)
def test_every_script_that_reaches_the_app_isolates_itself_or_says_why_not(script: str) -> None:
    tree = _tree(script)
    exempt = {**NOT_ISOLATED, **ARRIVING_WITH_L1}
    if not _reaches_the_app(tree):
        assert script not in exempt, "an exemption for a script that imports nothing of the app"
        return
    if script in SELF_ISOLATING:
        assert script not in exempt, "an exemption for a script that isolates itself"
        return
    assert exempt.get(script, "").strip(), (
        f"scripts/{script} imports the app or builds a Qt application and does not isolate itself: "
        "outside pytest its settings, app data and Qt locations are the user's own. Call "
        "script_isolation (see its docstring) or add it to NOT_ISOLATED with the reason.")


def test_the_exemptions_are_all_needed() -> None:
    """An exemption for a script that is gone is a hole waiting for its namesake."""
    assert set(NOT_ISOLATED) <= set(ALL_SCRIPTS)
    assert not set(NOT_ISOLATED) & set(ARRIVING_WITH_L1)
    assert all(reason.strip() for reason in (*NOT_ISOLATED.values(), *ARRIVING_WITH_L1.values()))


@pytest.mark.parametrize("script", SELF_ISOLATING)
def test_the_isolation_comes_before_the_app_is_imported(script: str) -> None:
    """Read off the script's own text: the guarded ``isolate_profile()`` stands
    above the first import of the app (or of a generator that imports it), and
    ``isolate()`` is the first statement of ``main()``."""
    tree = _tree(script)
    guard = first_app_import = None
    for position, node in enumerate(tree.body):
        if (guard is None and isinstance(node, ast.If)
                and ast.unparse(node.test) == "__name__ == '__main__'"
                and "script_isolation.isolate_profile()" in ast.unparse(node)):
            guard = position
        if first_app_import is None and isinstance(node, ast.Import | ast.ImportFrom) and (
                _imported(node) & {"open_garden_planner", "make_bench_plans", "PyQt6"}):
            first_app_import = position
    assert guard is not None and first_app_import is not None and guard < first_app_import
    (main,) = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    assert ast.unparse(main.body[0]) == "script_isolation.isolate()"


def test_the_mutation_script_imports_nothing_of_the_app() -> None:
    """It rewrites source files and runs pytest: every child it starts is pytest."""
    source = (SCRIPTS / "mutation_check_scene3d.py").read_text(encoding="utf-8")
    assert not _imported(ast.parse(source)) & {"open_garden_planner", "PyQt6"}
    assert '"-m", "pytest"' in source


#: Runs one script as ``__main__`` and reports what it did to the stores.
DRIVER = r'''
import json, os, runpy, sys

script, variables, locations, *arguments = sys.argv[1:]
import open_garden_planner.app.settings as app_settings

decoy = ["cofade_test", f"Open Garden Planner Decoy {os.getpid()}"]
app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME = decoy
built = []
make = app_settings.create_qsettings


def watched():
    built.append([app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME])
    return make()


app_settings.create_qsettings = watched
sys.argv = [script, *arguments]
try:
    runpy.run_path(script, run_name="__main__")
    code = 0
except SystemExit as stop:
    code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
names = [app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME]
app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME = decoy
store = make()  # whatever a script that did NOT isolate itself wrote to the decoy: gone again
store.clear()
store.sync()
app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME = names
from PyQt6.QtCore import QStandardPaths

isolation = sys.modules.get("script_isolation")
print("RESULT " + json.dumps({
    "exit": code, "decoy": decoy, "built": built, "names": names,
    "root": str(isolation._state.get("root")) if isolation else None,
    "environment": {name: os.environ.get(name) for name in variables.split(",")},
    "qt": {name: QStandardPaths.writableLocation(getattr(QStandardPaths.StandardLocation, name))
           for name in locations.split(",")},
}))
'''


def _under(path: str | None, root: Path | str) -> bool:
    return path is not None and Path(os.path.normcase(os.path.abspath(path))).is_relative_to(
        os.path.normcase(os.path.abspath(root)))


def _run_as_a_script(script: str, arguments: list[str], home: Path) -> dict:
    """Run ``scripts/<script>`` as ``__main__`` in a child whose whole profile is ``home``."""
    environment = dict(os.environ)
    for name in script_isolation.PROFILE_VARIABLES:
        folder = home / name.lower()
        folder.mkdir(parents=True)
        environment[name] = str(folder)
    environment["PYTHONPATH"] = str(REPO / "src")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [sys.executable, "-c", DRIVER, str(SCRIPTS / script),
         ",".join(script_isolation.PROFILE_VARIABLES), ",".join(script_isolation.QT_LOCATIONS),
         *arguments],
        capture_output=True, text=True, env=environment, cwd=str(REPO), timeout=170, check=False)
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, f"{script} did not finish:\n{done.stdout[-1500:]}\n{done.stderr[-1500:]}"
    result: dict = json.loads(lines[-1][len("RESULT "):])
    result["output"] = done.stdout
    return result


def _left_in(home: Path) -> list[str]:
    """Everything under ``home`` beyond the empty folders the child was started with."""
    started_with = {home / name.lower() for name in script_isolation.PROFILE_VARIABLES}
    return sorted(str(path.relative_to(home)) for path in home.rglob("*") if path not in started_with)


@pytest.mark.parametrize(
    ("script", "arguments", "builds_a_store", "says"),
    [("make_scene3d_edge_plan.py", ["--check"], True, "scene3d edge-case plan: OK"),
     ("make_bench_plans.py", ["--check"], True, "bench plans: OK"),  # both save plans: Recent Files
     ("measure_region_work.py", ["--help"], False, "usage:"),
     # L1.4: the production Beauty Board LOADS a plan (Recent Files) before it lists its shots
     ("render_beauty_board.py", ["--list"], True, "golden_hour")],
)
def test_a_script_run_as_a_script_reaches_none_of_the_users_stores(
    tmp_path: Path, script: str, arguments: list[str], builds_a_store: bool, says: str
) -> None:
    assert script in SELF_ISOLATING
    home = tmp_path / "home"
    result = _run_as_a_script(script, arguments, home)
    assert result["exit"] == 0 and says in result["output"], result["output"][-1500:]

    # the settings: every store the script built is a throwaway key of that process …
    organisation, application = result["names"]
    assert organisation == script_isolation.SCRIPT_ORGANIZATION
    assert application.startswith("Open Garden Planner Script ") and result["names"] != result["decoy"]
    assert all(pair == result["names"] for pair in result["built"]), result["built"]
    assert bool(result["built"]) is builds_a_store  # … and the generators did build one: the case that matters

    # the profile: every variable points into the script's own temporary root, away from
    # the profile the child was started with, and nothing appeared in that one
    root = result["root"]
    assert root and not _under(root, home)
    for name in script_isolation.PROFILE_VARIABLES:
        assert _under(result["environment"][name], root), name
    assert _left_in(home) == []

    # Qt's locations: all five under that root too — on Windows the variables alone leave
    # AppLocalDataLocation and CacheLocation in the real profile (review of fix round 3)
    assert set(result["qt"]) == set(script_isolation.QT_LOCATIONS)
    for name, answer in result["qt"].items():
        assert _under(answer, Path(root) / "qt"), (name, answer)


def test_isolating_twice_is_isolating_once(tmp_path: Path) -> None:
    """Every call is safe to repeat — a script calls ``isolate_profile()`` before
    its imports and ``isolate()`` in ``main()``. Shown in a child: this process's
    own redirection (``tests/conftest.py``) must not be moved."""
    program = (
        "import os, sys, json; sys.path.insert(0, sys.argv[1])\n"
        "import script_isolation as s\n"
        "first = s.isolate_profile(); again = s.isolate_profile(); s.isolate(); s.isolate()\n"
        "found = s.isolate_settings()\n"
        "import open_garden_planner.app.settings as a\n"
        "from PyQt6.QtCore import QStandardPaths as Q\n"
        "print('RESULT ' + json.dumps({'same': str(first) == str(again), 'root': str(first),\n"
        "    'exists': first.is_dir(), 'found': list(found), 'bound': [a.ORGANIZATION_NAME, a.APPLICATION_NAME],\n"
        "    'cache': Q.writableLocation(Q.StandardLocation.CacheLocation),\n"
        "    'temp_is_qt_s': Q.writableLocation(Q.StandardLocation.TempLocation) != '',\n"
        "    'environment': {n: os.environ[n] for n in s.PROFILE_VARIABLES}}))\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    done = subprocess.run([sys.executable, "-c", program, str(SCRIPTS)], capture_output=True, text=True,
                          env=environment, cwd=str(tmp_path), timeout=120, check=False)
    (line,) = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    result = json.loads(line[len("RESULT "):])
    assert result["same"] and result["exists"]
    assert all(_under(value, Path(result["root"])) for value in result["environment"].values())
    assert result["bound"][0] == "cofade_test" and result["bound"][1].startswith("Open Garden Planner Script ")
    assert result["found"] != result["bound"]  # what it found is what a caller could put back
    assert _under(result["cache"], Path(result["root"]) / "qt") and result["temp_is_qt_s"]
    assert not Path(result["root"]).exists()  # … and the folder is gone when the process is


def test_the_suite_and_the_scripts_share_one_stand_in() -> None:
    """``tests/conftest.py`` installs ``script_isolation.redirect_qt_locations`` —
    the function, not a copy of it — and a second call changes nothing."""
    from PyQt6.QtCore import QStandardPaths

    from tests.conftest import REDIRECTED_QT_LOCATIONS, TEST_DATA_ROOT

    assert sys.modules["script_isolation"] is script_isolation
    assert script_isolation._state["qt"] is REDIRECTED_QT_LOCATIONS
    assert {location.name for location in REDIRECTED_QT_LOCATIONS} == set(script_isolation.QT_LOCATIONS)
    installed = QStandardPaths.writableLocation
    assert script_isolation.redirect_qt_locations(Path("elsewhere")) is REDIRECTED_QT_LOCATIONS
    assert QStandardPaths.writableLocation is installed
    answer = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    assert _under(answer, TEST_DATA_ROOT) and "elsewhere" not in answer
