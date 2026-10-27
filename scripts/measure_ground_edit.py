"""What one small ground edit costs the 3D ground bake, across a tile border or where
four tiles meet (G3, #615). Committed with PR #613 (#388) so the readings in ADR-065
and #615 have a source a reader can re-run.

A 2.5 x 1.5 m terrace is laid on bench_large's middle, across one tile border (2 tiles)
or on the corner where four tiles meet (4 tiles), and moved back and forth by 44 cm, as
G3 moves its item. Prints one JSON line per placement: the median and max bake of a
move in ms, the tiles and passes per move, and which source tree was measured. From the
repo root::

    venv/Scripts/python.exe scripts/measure_ground_edit.py
    venv/Scripts/python.exe scripts/measure_ground_edit.py --moves 61 --across corner

**Another tree** (for example master, checked out with ``git worktree add``): set
``OGP_MEASURE_TREE`` to its root. The script then imports that tree's package and its
``tests/integration/ground_bake_support``, and loads that tree's bench plan. Alternate
the two trees run by run.

**Windows power throttling** (EcoQoS) can raise these readings about 1.8x partway
through a run (#616). On Windows the script opts its own process out first; the JSON
says whether that worked (``unthrottled``).

It keeps out of the owner's settings and data (``script_isolation``); it saves nothing.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import statistics
import sys
from pathlib import Path

import script_isolation

TREE = Path(os.environ.get("OGP_MEASURE_TREE") or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0] = [str(TREE / "src"), str(TREE)]   # that tree's package, and its tests package

if __name__ == "__main__":
    script_isolation.isolate_profile()

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from tests.integration.ground_bake_support import Bake, TimedBaker  # noqa: E402

import open_garden_planner  # noqa: E402
from open_garden_planner.core import ProjectManager  # noqa: E402
from open_garden_planner.core.commands import MoveItemsCommand  # noqa: E402
from open_garden_planner.core.object_types import ObjectType  # noqa: E402
from open_garden_planner.core.scene3d.builders import production_registry  # noqa: E402
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene  # noqa: E402
from open_garden_planner.ui.canvas.items import RectangleItem  # noqa: E402

#: ``SetProcessInformation``'s class for power throttling, and its execution-speed bit.
PROCESS_POWER_THROTTLING = 4
EXECUTION_SPEED = 1


class _PowerThrottlingState(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]


def opt_out_of_power_throttling() -> bool:
    """Ask Windows not to slow this process down (EcoQoS). False elsewhere, or refused."""
    if sys.platform != "win32":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetProcessInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    state = _PowerThrottlingState(1, EXECUTION_SPEED, 0)
    return bool(kernel.SetProcessInformation(kernel.GetCurrentProcess(), PROCESS_POWER_THROTTLING,
                                             ctypes.byref(state), ctypes.sizeof(state)))


def measure(across: str, moves: int) -> dict[str, object]:
    scene = CanvasScene()
    ProjectManager().load(scene, TREE / "tests" / "fixtures" / "plans" / "bench_large.ogp")
    baker = TimedBaker()
    bake = Bake(scene, registry=production_registry(), baker=baker)
    bake.step()
    bake.finish()
    tile_cm = bake.grid.tile_px / bake.grid.px_per_cm
    middle_x, middle_y = bake.grid.width_cm / 2.0, bake.grid.depth_cm / 2.0
    border = round(middle_x / tile_cm) * tile_cm
    row = round(middle_y / tile_cm) * tile_cm if across == "corner" else (
        (math.floor(middle_y / tile_cm) + 0.5) * tile_cm)
    item = RectangleItem(border - 125.0, row - 75.0, 250.0, 150.0, object_type=ObjectType.TERRACE_PATIO)
    scene.addItem(item)
    bake.step()
    bake.finish()
    per_move: list[float] = []
    passes: list[int] = []
    tiles: set[int] = set()
    for index in range(moves):
        baker.milliseconds.clear()
        delta = QPointF(37.5, -22.25) if index % 2 == 0 else QPointF(-37.5, 22.25)
        MoveItemsCommand([item], delta).execute()
        bake.step()
        repainted = set(baker.last_repainted)
        while bake.sync.ground_pending:
            bake.sync.continue_ground()
            repainted |= set(baker.last_repainted)
        per_move.append(sum(baker.milliseconds))
        passes.append(len(baker.milliseconds))
        tiles.add(len(repainted))
    return {"across": across, "median_ms": round(statistics.median(per_move), 2),
            "max_ms": round(max(per_move), 2), "tiles": sorted(tiles),
            "passes_median": statistics.median(passes), "passes_max": max(passes)}


def main() -> int:
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--across", choices=("border", "corner"), action="append")
    parser.add_argument("--moves", type=int, default=61)
    args = parser.parse_args()
    unthrottled = opt_out_of_power_throttling()
    package = Path(open_garden_planner.__file__).resolve()
    if not package.is_relative_to(TREE / "src"):
        raise SystemExit(f"imported {package}, not the tree {TREE}")
    _app = QApplication([])
    for across in args.across or ["border", "corner"]:
        row = measure(across, args.moves)
        print(json.dumps({"tree": str(TREE), "unthrottled": unthrottled, **row}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
