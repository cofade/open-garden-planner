"""What the frozen build has to carry for the 3D workspace — and what it must not (L1.3).

The workspace and everything behind it are imported lazily (behind ``OGP_QUICK3D=1``,
and most of it only on the first switch to 3D), so ``installer/ogp.spec`` names the
modules. The GATE build (``installer/workspace_gate.spec``) is the product build
plus one runtime hook that moves the settings store: test tooling that must never
drift from the product recipe, and a hook the product must never ship.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = (REPO / "installer" / "ogp.spec").read_text(encoding="utf-8")
GATE_SPEC = (REPO / "installer" / "workspace_gate.spec").read_text(encoding="utf-8")
HOOK = REPO / "tests" / "integration" / "workspace_gate_hook.py"
WORKSPACE_MODULES = (
    "open_garden_planner.ui.view3d.workspace",
    "open_garden_planner.ui.view3d.sync_controller",
    "open_garden_planner.ui.view3d.init_guard",
    "open_garden_planner.ui.view3d.orbit_input",
    "open_garden_planner.ui.view3d.problems_dialog",
    "open_garden_planner.ui.sim_clock_subscription",
    "open_garden_planner.core.scene3d.camera",
    "open_garden_planner.core.plain_text",
)


def test_every_module_of_the_workspace_exists_and_is_a_hidden_import() -> None:
    for name in WORKSPACE_MODULES:
        path = REPO / "src" / Path(*name.split(".")).with_suffix(".py")
        assert path.is_file(), f"{name} is named for the build and does not exist"
        assert f'"{name}"' in SPEC, f"{name} is missing from ogp.spec's hiddenimports"


def test_no_module_beside_the_workspace_was_forgotten() -> None:
    """Every module in ``ui/view3d/`` itself is named in the spec — a new one that is
    only ever imported inside a function would otherwise be found by luck or not."""
    folder = REPO / "src" / "open_garden_planner" / "ui" / "view3d"
    for path in sorted(folder.glob("*.py")):
        if path.name == "__init__.py":
            continue
        assert f'"open_garden_planner.ui.view3d.{path.stem}"' in SPEC, path.name


def test_the_product_build_ships_no_runtime_hook() -> None:
    """The gate's hook rebinds the settings names and arms a scripted scenario: it
    belongs to the gate build alone."""
    assert SPEC.count("    runtime_hooks=[],\n") == 1
    assert "runtime_hooks=[" not in SPEC.replace("    runtime_hooks=[],\n", "")
    assert "workspace_gate" not in SPEC


def test_the_gate_build_is_the_product_recipe_with_one_hook() -> None:
    assert HOOK.is_file()
    # the two anchors the gate spec rewrites are in the product spec exactly as often
    # as it expects — the gate spec refuses to build otherwise, and so does this test
    assert SPEC.count('    name="OpenGardenPlanner",\n') == 2
    assert '("    runtime_hooks=[],\\n"' in GATE_SPEC and '\'    name="OpenGardenPlanner",\\n\'' in GATE_SPEC
    assert "workspace_gate_hook.py" in GATE_SPEC
    # no recipe of its own: it executes the product spec's text
    tree = ast.parse(GATE_SPEC)
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "exec" in called and not called & {"Analysis", "EXE", "COLLECT", "PYZ"}
    assert 'Path(SPECPATH) / "ogp.spec"' in GATE_SPEC
