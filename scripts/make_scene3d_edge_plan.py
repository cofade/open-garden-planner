"""Generate the committed 3D edge-case plan (Phase 17 L1.1, fix rounds 1 to 3, #385).

``tests/fixtures/plans/scene3d_edge_cases.ogp`` holds the shapes the two bench
plans do not contain and the first scene contract therefore got wrong without a
single gate noticing — above all a fence that closes on itself, whose stroke is
an outer ring and a HOLE. One item per case, on a 40 x 30 m canvas:

* a HOUSE turned by 25 degrees, with its roof ridge item (ADR-046);
* an ellipse (a pond), turned by 40 degrees;
* a closed-loop fence, 10 m x 8 m, 10 cm wide — outer ring + hole;
* a nearly closed one: its two ends stop 2 cm apart AT A CORNER, and the strokes
  of the two sides overlap there — also a hole;
* an open U — no hole;
* a raised bed turned by 30 degrees, with two planted children;
* a round container with a plant;
* a polygon with a concave corner (an L-shaped hedge);

and, since fix round 2:

* a ladder drawn as one stroke — two rails, five rungs: ONE outer ring and FOUR
  holes;
* a fence whose ends stop 6 cm apart at a corner. A stroke has butt ends
  (``core/shadow_geometry.polyline_footprint``): it reaches half its width past
  the centre line sideways and not at all past its end, so a 10 cm stroke closes
  a corner gap of up to 5 cm and no more — this one stays open, no hole. (A gap
  in the middle of a straight run never closes, however small.)
* a HOUSE whose outline crosses itself and encloses a pocket: resolved into
  three parts that stand a hair apart, with ``outline_resolved`` set and no
  ``ridge`` — although the plan holds a ridge item for it.

and, since fix round 3:

* a fence drawn round three sides and back to a point one stroke width above
  its start: its two butt ends meet corner to corner, in ONE point. The clipper
  hands such a stroke out as a single ring that touches itself — no polygon —
  and the record holds it drawn in by 0.002 cm, the two ends a hair apart. (The
  re-review's fence: every fence of this kind takes that path, and no test did.)

``tests/integration/test_scene3d_edge_plan.py`` runs the pipeline's gates over
it (snapshot stability, mesh validity and plan area, transform ∘ local footprint
== the 2D footprint) and pins that regenerating reproduces the committed file.
It is written through the real ``ProjectManager`` serializer with seeded ids,
exactly like ``scripts/make_bench_plans.py``, whose plumbing it reuses — and
which it never modifies: the bench plans stay byte for byte what they were.

Saving through ``ProjectManager`` records Recent Files. Run as a script this
file therefore isolates itself before it builds anything — the profile before
the app is imported, the settings names first thing in ``main()``
(``scripts/script_isolation.py``): it never touches the user's own settings or
app data. Imported by a test it changes nothing; pytest has isolated the process.

One difference from the bench plans: this plan has TURNED items, so some of its
numbers went through ``cos`` / ``sin`` (the ridge item Qt re-derives when the
house turns, the two plants placed inside the turned bed), and the last bit of
those belongs to the platform's C library. "Regenerating reproduces the
committed plan" therefore means ``same_plan``: the same structure, the same
strings and integers, every float within 1e-9 cm (section 8.10.5, "a golden
fixture before a move"). The committed file was generated on Windows.

Usage::

    venv/bin/python scripts/make_scene3d_edge_plan.py           # (re)write the fixture
    venv/bin/python scripts/make_scene3d_edge_plan.py --check   # verify it is current
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import script_isolation  # noqa: E402  (before the app is imported — below, through make_bench_plans)

if __name__ == "__main__":  # run as a script: nothing from here on may reach the user's own stores
    script_isolation.isolate_profile()

import make_bench_plans as bench  # noqa: E402  (sets up sys.path for the package and Qt's platform)
from PyQt6.QtWidgets import QApplication  # noqa: E402

from open_garden_planner.core.item_look import adopt_pen  # noqa: E402
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle  # noqa: E402
from open_garden_planner.ui.canvas.geometry_apply import apply_rotation  # noqa: E402
from open_garden_planner.ui.canvas.items import EllipseItem  # noqa: E402

NAME = "scene3d_edge_cases.ogp"
#: How far a regenerated float may lie from the committed one, in the plan's own
#: unit (cm, degrees): far above one bit of a coordinate, far below anything real.
FLOAT_TOLERANCE = 1e-9
FENCE_WIDTH_CM = 10.0
HOUSE_TURN_DEG = 25.0
POND_TURN_DEG = 40.0
BED_TURN_DEG = 30.0

#: name → centre line; each is the 10 m x 8 m rectangle, shifted to its place
FENCES: dict[str, list[tuple[float, float]]] = {
    "Closed fence": [(200, 200), (1200, 200), (1200, 1000), (200, 1000), (200, 200)],
    "Nearly closed fence": [(1500, 202), (1500, 1000), (2500, 1000), (2500, 200), (1500, 200)],
    "Open U fence": [(2800, 1000), (2800, 200), (3800, 200), (3800, 1000)],
}
#: Fix round 2. Appended AFTER everything else, so the ids of the items above —
#: drawn from one seeded sequence — stay what they were.
LADDER_CELLS = 4
LADDER_CELL_CM = 150.0
MORE_FENCES: dict[str, list[tuple[float, float]]] = {
    # two rails and five rungs without lifting the pen: along the bottom rail, up
    # the last rung, back along the top rail, down the first, then rung by rung
    "Ladder fence": [(300, 1300), (900, 1300), (900, 1450), (300, 1450), (300, 1300),
                     (450, 1300), (450, 1450), (600, 1450), (600, 1300), (750, 1300), (750, 1450)],
    # its ends stop 6 cm apart at the corner (1100, 1250): more than half the stroke
    "Fence with a gap": [(1100, 1256), (1100, 1450), (1400, 1450), (1400, 1250), (1100, 1250)],
}
#: The second outline of the re-review (item-local numbers there), moved to its place.
CROSSED_HOUSE = [(3300, 1200), (3300, 1300), (3550, 1550), (3250, 1350), (3350, 1300),
                 (3200, 1200), (3400, 1450)]
#: Fix round 3. Appended after the crossed house and ITS ridge item, for the same reason.
#: It ends at (2500, 1600), one stroke width under where it began: the stroke of the
#: first run ends at x = 2500 between y = 1605 and 1615, that of the last one between
#: 1595 and 1605 — they share the point (2500, 1605) and nothing else.
LAST_FENCES: dict[str, list[tuple[float, float]]] = {
    "Fence that meets itself": [(2500, 1610), (2400, 1610), (2400, 1300), (2600, 1300),
                                (2600, 1600), (2500, 1600)],
}


def _turned(point: tuple[float, float], centre: tuple[float, float], degrees: float) -> tuple[float, float]:
    """``point`` turned counter-clockwise about ``centre`` (the canvas is Y-up)."""
    angle = math.radians(degrees)
    dx, dy = point[0] - centre[0], point[1] - centre[1]
    return (centre[0] + dx * math.cos(angle) - dy * math.sin(angle),
            centre[1] + dx * math.sin(angle) + dy * math.cos(angle))


def build_edge_cases() -> bench.PlanBuilder:
    b = bench.PlanBuilder(4000.0, 3000.0, seed="ogp-scene3d-edge-cases-v1")
    T = ObjectType

    house = b.house([(300, 2000), (1200, 2000), (1200, 2540), (300, 2540)])
    apply_rotation(house, HOUSE_TURN_DEG)  # PolygonItem re-derives the ridge item (ADR-046)

    pond = b._add(EllipseItem(1700.0, 2100.0, 600.0, 300.0, object_type=T.POND_POOL, name="Pond"))
    apply_rotation(pond, POND_TURN_DEG)

    for name, centre_line in FENCES.items():
        # No style preset: the loader lets a preset override a saved stroke width
        # (``core/project.py`` restores it only for ``PathFenceStyle.NONE``), and
        # these three are about a stroke of exactly 10 cm.
        fence = b.polyline(centre_line, T.FENCE, PathFenceStyle.NONE, name)
        pen = fence.pen()
        pen.setWidthF(FENCE_WIDTH_CM)
        adopt_pen(fence, pen)

    bed = b.rect(1700.0, 1300.0, 520.0, 120.0, T.RAISED_BED, "Turned raised bed")
    apply_rotation(bed, BED_TURN_DEG)
    centre = (1960.0, 1360.0)
    for offset, crop in ((-130.0, "Tomato"), (130.0, "Basil")):
        x, y = _turned((centre[0] + offset, centre[1]), centre, BED_TURN_DEG)
        b.plant(x, y, crop, T.PERENNIAL, parent=bed)

    pot = b.circle(2900.0, 1500.0, 30.0, T.CONTAINER_ROUND, "Pot")
    b.plant(2900.0, 1500.0, "Rosemary", T.PERENNIAL, spread_cm=45, height_cm=50, parent=pot)

    b.polygon([(3000, 2000), (3900, 2000), (3900, 2300), (3400, 2300), (3400, 2700), (3000, 2700)],
              T.HEDGE_POLYGON, "L-shaped hedge")

    for name, centre_line in MORE_FENCES.items():
        fence = b.polyline(centre_line, T.FENCE, PathFenceStyle.NONE, name)
        pen = fence.pen()
        pen.setWidthF(FENCE_WIDTH_CM)
        adopt_pen(fence, pen)
    b.house(CROSSED_HOUSE, "Crossed house")  # with a ridge item, as the polygon tool makes one
    for name, centre_line in LAST_FENCES.items():
        fence = b.polyline(centre_line, T.FENCE, PathFenceStyle.NONE, name)
        pen = fence.pen()
        pen.setWidthF(FENCE_WIDTH_CM)
        adopt_pen(fence, pen)
    return b


def same_plan(fresh: Any, committed: Any, tolerance: float = FLOAT_TOLERANCE) -> bool:
    """True when two parsed plans are the same plan: equal structure, equal
    strings / integers / booleans, floats within ``tolerance`` (module docstring)."""
    if isinstance(fresh, bool) or isinstance(committed, bool):
        return fresh is committed
    if isinstance(fresh, float) or isinstance(committed, float):
        return (isinstance(fresh, int | float) and isinstance(committed, int | float)
                and math.isclose(fresh, committed, rel_tol=0.0, abs_tol=tolerance))
    if isinstance(fresh, dict) and isinstance(committed, dict):
        return (fresh.keys() == committed.keys()
                and all(same_plan(fresh[key], committed[key], tolerance) for key in fresh))
    if isinstance(fresh, list) and isinstance(committed, list):
        return (len(fresh) == len(committed)
                and all(same_plan(a, b, tolerance) for a, b in zip(fresh, committed, strict=True)))
    return bool(fresh == committed)


def main(argv: list[str] | None = None) -> int:
    # Saving through ``ProjectManager`` records Recent Files, and the scene reads the
    # app-data folder: both are pointed away from the user's own before anything is built
    # (``script_isolation``; a key of this process, cleared at exit — not the bench
    # generator's standing one).
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate to a temp dir and compare with the committed fixture")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841

    committed = bench.OUT_DIR / NAME
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / NAME
            bench._save(build_edge_cases(), fresh)
            current = committed.is_file() and same_plan(bench._normalised(fresh),
                                                         bench._normalised(committed))
        if not current:
            print(f"STALE: {committed.relative_to(bench.REPO)} — rerun scripts/make_scene3d_edge_plan.py")
        print("scene3d edge-case plan: " + ("OK" if current else "FAIL"))
        return 0 if current else 1

    builder = build_edge_cases()
    bench._save(builder, committed)
    print(f"wrote {committed.relative_to(bench.REPO)}: {builder.count} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
