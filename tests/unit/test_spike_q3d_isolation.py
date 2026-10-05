"""The Qt Quick 3D spike stays dormant and keeps its import boundary (ADR-048, L0).

ADR-038's precedent for a spike that ships in the tree: it must never load at
app startup, and its engine imports are confined to ONE module so the
production package (L1.2) inherits a clean boundary. ``meshes`` is the Qt-free
prototype core that graduates into ``core/`` — it must not import Qt at all.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

SPIKE = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "spike_q3d"
ENGINE_MODULES = ("PyQt6.QtQuick3D", "PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets")


def _imports(path: Path) -> set[str]:
    """Every imported module, including ``from PyQt6 import QtQuick3D`` spelled as
    ``PyQt6.QtQuick3D`` (the repo's own style in main.py — the first version of this
    scan recorded it as plain ``PyQt6`` and matched nothing)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_meshes_module_is_qt_free() -> None:
    assert not any(n.startswith("PyQt6") for n in _imports(SPIKE / "meshes.py"))


def test_only_quick_module_imports_the_engine() -> None:
    offenders = []
    for path in SPIKE.glob("*.py"):
        if path.name == "quick.py":
            continue
        if any(n.startswith(m) for n in _imports(path) for m in ENGINE_MODULES):
            offenders.append(path.name)
    assert offenders == []


def test_scan_sees_the_from_package_import_spelling(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("from PyQt6 import QtQuick3D\n", encoding="utf-8")
    assert "PyQt6.QtQuick3D" in _imports(probe)


def test_spike_never_imported_at_startup() -> None:
    """Constructing the app loads neither the spike nor the Qt Quick 3D bindings.

    In a fresh interpreter: an in-process ``sys.modules`` diff passes vacuously
    once any earlier test has imported the spike (senior review).
    """
    code = (
        "import sys\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from open_garden_planner.app.application import GardenPlannerApp\n"
        "win = GardenPlannerApp()\n"
        "print(sorted(m for m in sys.modules if m.startswith("
        "('open_garden_planner.spike_q3d', 'PyQt6.QtQuick3D'))))\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    # THIS checkout's src: without it the child imports whatever the venv's editable
    # install points at, which from a git worktree is the main checkout (creator round 4)
    src = str(SPIKE.parents[1])
    env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH")) if p)
    proc = subprocess.run(  # noqa: S603 — fixed argv, our own code
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=170,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "[]"


def test_spike_points_settings_at_a_throwaway_store() -> None:
    """Loading a plan records Recent Files: the spike must never touch the user's store."""
    import open_garden_planner.app.settings as app_settings
    from open_garden_planner.spike_q3d import runner

    saved = (app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME)
    try:
        runner._isolate_settings()
        assert app_settings.ORGANIZATION_NAME == runner.SETTINGS_ORGANIZATION
        assert app_settings.ORGANIZATION_NAME != "cofade"
    finally:  # keep this session's own test redirection (tests/conftest.py)
        app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME = saved


def test_main_dispatches_spike_flag_lazily() -> None:
    """``--spike-q3d`` is dispatched inside main(), never at module import."""
    src = (SPIKE.parent / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top_level = {
        node.module for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(m and m.startswith("open_garden_planner.spike_q3d") for m in top_level)
    assert '"--spike-q3d" in sys.argv' in src


def test_a_typo_in_any_flag_is_refused_before_any_work() -> None:
    """``parse_known_args`` keeps unknown flags; ``_validate`` refuses them (and bad
    presets) before the plan is loaded, so a typo never runs another experiment."""
    from open_garden_planner.spike_q3d import runner

    args = runner._parse(["--spike-q3d", "--out", "x", "--sooak", "5"])
    assert args.unknown == ["--sooak", "5"]
    abbreviated = runner._parse(["--spike-q3d", "--out", "x", "--ori"])
    assert abbreviated.orient is False and abbreviated.unknown == ["--ori"]  # no prefixes
    with pytest.raises(ValueError, match="unknown arguments: --sooak 5"):
        runner._validate(args, None)
    with pytest.raises(ValueError, match="unknown presets"):
        runner._validate(runner._parse(["--spike-q3d", "--out", "x", "--presets", "lo"]), None)
    runner._validate(runner._parse(["--spike-q3d", "--out", "x", "--shots", "nope"]), None)
    with pytest.raises(ValueError, match="unknown shots"):  # shots need the plan's size
        runner._validate(runner._parse(["--spike-q3d", "--out", "x", "--shots", "nope"]),
                         {"noon"})


def test_sky_keys_are_exactly_what_rebuild_sky_reads() -> None:
    """preserved_state() rebuilds the sky when a SKY_KEYS property changed. The list is
    kept by hand, so it is pinned to what GardenSpike.qml's rebuildSky() reads: a new
    sky input missing from it would leave a probe's sky on screen (senior review)."""
    import re

    from open_garden_planner.spike_q3d.quick import SpikeRenderer

    qml = (SPIKE / "qml" / "GardenSpike.qml").read_text(encoding="utf-8")
    body = qml[qml.index("function rebuildSky()"):]
    body = body[:body.index("\n        }\n")]
    assert set(re.findall(r"root\.(\w+)", body)) == set(SpikeRenderer.SKY_KEYS)
