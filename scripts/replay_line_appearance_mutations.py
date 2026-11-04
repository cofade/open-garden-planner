"""Replay five line-appearance regressions without rewriting source (#524–#526, #471).

Each isolated pytest process loads a temporary plugin that replaces one runtime
operation. A mutation counts as caught only for assertion failures, with no setup
errors. The last process runs all new integration tests without a plugin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = "tests/integration/test_line_appearance_history.py"
BOUNDS = "tests/integration/test_styled_line_bounds.py"
_RESTORE_IMPORTS = """
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen
from open_garden_planner.core import item_look as look
from open_garden_planner.core.object_types import PathFenceStyle, get_path_fence_style_info
from open_garden_planner.ui.panels import properties_panel as panel
original = look.apply_line_look
"""
_MUTATIONS = {
    "preset_name_only": (_RESTORE_IMPORTS + """
def broken(item, state):
    previous = QPen(item.pen())
    keep = state.preset is PathFenceStyle.NONE and state.object_type is item.object_type
    original(item, state)
    if keep:
        look.adopt_pen(item, previous)
look.apply_line_look = panel.apply_line_look = broken
""", [f"{HISTORY}::test_preset_history_restores_the_complete_pen"]),
    "reapply_preset_defaults": (_RESTORE_IMPORTS + """
def broken(item, state):
    original(item, state)
    if state.preset is not PathFenceStyle.NONE:
        defaults = get_path_fence_style_info(state.preset)
        pen = item.pen()
        pen.setColor(defaults.stroke_color)
        pen.setWidthF(defaults.stroke_width)
        look.adopt_pen(item, pen)
look.apply_line_look = panel.apply_line_look = broken
""", [f"{HISTORY}::test_type_changes_clear_presets_and_restore_exactly"]),
    "square_bevel_pen": (_RESTORE_IMPORTS + """
def broken(item, state):
    original(item, state)
    pen = item.pen()
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    pen.setJoinStyle(Qt.PenJoinStyle.BevelJoin)
    look.adopt_pen(item, pen)
look.apply_line_look = panel.apply_line_look = broken
""", [f"{HISTORY}::test_panel_type_change_keeps_round_caps_and_joins"]),
    "old_paint_bounds": ("""
from PyQt6.QtWidgets import QGraphicsPathItem
from open_garden_planner.ui.canvas.items import PolylineItem
def old_bounds(item):
    margin = item.pen().widthF() / 2 + 2 + item._shadow_margin()
    return QGraphicsPathItem.boundingRect(item).adjusted(-margin, -margin, margin, margin)
PolylineItem.boundingRect = old_bounds
""", [f"{BOUNDS}::test_uncached_pixels_fit_the_declared_bounds",
       "-k", "straight and wide and METAL_FENCE"]),
    "late_geometry_notification": ("""
from open_garden_planner.ui.canvas.items import PolylineItem
def late(item, value):
    item._path_fence_style = value
    item.prepareGeometryChange()
    item.update()
PolylineItem.path_fence_style = property(PolylineItem.path_fence_style.fget, late)
""", [f"{BOUNDS}::test_pen_and_preset_notify_before_the_bounds_change"]),
}


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory(prefix="ogp-line-mutants-") as temporary:
        for name, (body, targets) in [*_MUTATIONS.items(), ("control", ("", [HISTORY, BOUNDS]))]:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                [temporary, str(ROOT / "src"), env.get("PYTHONPATH", "")])
            options = []
            if body:
                module = f"line_mutant_{name}"
                plugin = Path(temporary) / f"{module}.py"
                plugin.write_text("def pytest_configure(config):\n" +
                                  textwrap.indent(textwrap.dedent(body).strip(), "    ") + "\n",
                                  encoding="utf-8")
                options = ["-p", module]
            report = output / f"{name}.xml"
            report.unlink(missing_ok=True)
            command = [sys.executable, "-m", "pytest", *options, *targets, "-q", "-n", "0",
                       "--tb=short", f"--junitxml={report}"]
            with (output / f"{name}.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=180, check=False)
            document = ET.parse(report)
            failures = document.findall(".//failure")
            errors = document.findall(".//error")
            assertion_only = all(
                "AssertionError" in (failure.text or "")
                or failure.get("message", "").startswith(("assert ", "AssertionError"))
                for failure in failures)
            passed = (process.returncode == 0 and not failures and not errors) if not body else (
                process.returncode == 1 and bool(failures) and not errors and assertion_only)
            results[name] = {"exit": process.returncode, "failures": len(failures),
                             "errors": len(errors), "expected_result": passed}
            print(f"{name}: {'PASS' if passed else 'FAIL'} {results[name]}", flush=True)
    (output / "summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0 if all(result["expected_result"] for result in results.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "line-mutations")
    args = parser.parse_args()
    return run(args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
