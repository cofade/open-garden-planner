"""The Qt Quick 3D spike stays dormant and keeps its import boundary (ADR-047, L0).

ADR-038's precedent for a spike that ships in the tree: it must never load at
app startup, and its engine imports are confined to ONE module so the
production package (L1.2) inherits a clean boundary. ``meshes`` is the Qt-free
prototype core that graduates into ``core/`` — it must not import Qt at all.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "spike_q3d"
ENGINE_MODULES = ("PyQt6.QtQuick3D", "PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
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


def test_spike_never_imported_at_startup(qtbot) -> None:
    """Constructing the app loads neither the spike nor the Qt Quick 3D bindings."""
    from open_garden_planner.app.application import GardenPlannerApp

    watched = ("open_garden_planner.spike_q3d", "PyQt6.QtQuick3D")
    before = {m for m in sys.modules if m.startswith(watched)}
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    after = {m for m in sys.modules if m.startswith(watched)}
    assert after == before


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
