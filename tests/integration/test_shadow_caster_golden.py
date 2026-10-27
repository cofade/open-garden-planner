"""Golden gate for the 2D shadows of everything that stands on the ground
(Phase 17 L1.6, #385, gate G4).

L1.6 teaches the shared 2D caster model a ``base_cm``: a plant in a raised bed
casts from the bed's soil, not from the ground (ADR-037 addendum). That changes
SHIPPED 2D behaviour — the sun & shade overlay and the hours-of-sun heatmap — for
exactly one class of item: one whose parent is a soil container with a height.
This file pins that **nothing else moved**.

The fixture ``tests/fixtures/shadows/shadow_golden.json`` was generated from the
code as it stood BEFORE the change, with the exact value of every float. "Before"
is release **v1.29.10**: ``core/shadow_geometry.py`` and
``core/shade_aggregation.py`` had not changed since Phase 14 and are byte-identical
to that tag (the generating commit, ``aaec048`` on the integration branch, will not
survive a squash merge — the tag will):

- ``core`` — ``compute_scene_shadows`` for five footprints (convex, concave,
  clockwise, a 24-gon, a fence strip) x two heights x four sun elevations x three
  azimuths, plus a union and the night case;
- ``plans`` — both bench plans on 21 June: the caster walk itself, the union of
  every caster's shadow as the code computed it then, and the union of the
  casters that stand on the ground (everything but the plants in raised beds —
  22 and 240 of them). The walk hides the nine kinds L4's second owner pass gave
  a default height (``GIVEN_A_HEIGHT_IN_L4``), which had none in v1.29.10; a test
  of its own pins what they add;
- ``overlay`` — the painter path of the real ``SunShadowController`` overlay on a
  hand-built scene without raised plants, at a high and a low sun;
- ``heatmap`` — ``compute_heatmap`` minutes for the campaign's wall toy case.

**What each platform enforces** (review round 1, P1-2 — the gate is NOT the same
everywhere, and the CI test jobs run on Linux):

=====================  =======================================================
win32 (the platform    every float of every section equal, bit for bit; the
that generated the     SHA-256 of the bench plans' caster lists and shadow
fixture; the dev box)  unions equal
anywhere else          the same structure (polygon and vertex counts, path
(Linux CI)             element types, heatmap shape); every coordinate within
                       2e-3 cm — two steps of the 1/1000 cm grid; every union
                       area within 1e-6 relative; no hashes
=====================  =======================================================

Why it cannot be exact everywhere, cheaply: the numbers leave the integer grid
only at the very end (``k / 1000``, correctly rounded on any IEEE machine), so
comparing integer paths instead of floats would change nothing. What can differ
is how a number gets ONTO the grid: a sweep displacement is
``round(sin(az) * h / tan(a) * 1000)``, and ``math.sin`` / ``cos`` / ``tan`` are
the C library's — not correctly rounded on every one — so a value within an ulp
of a half grid step may round the other way. Removing that would mean replacing
libm in the shipped shadow code.

So the claim "nothing on the ground changed" does not rest on this file alone.
Its platform-INDEPENDENT half is
``tests/unit/test_shadow_caster_base.py::TestTheGroundPathIsTheReleasedCode``:
the shadow functions of v1.29.10, copied verbatim, give the very same integer
paths as today's for every caster on the ground — on whatever machine the test
runs, because old and new then share its libm. That is a proof of "unchanged";
this file adds the absolute numbers (exact where it was generated, to the grid
elsewhere) and the walk over real plans.

The tolerant comparison runs on EVERY platform (it is implied by the exact one),
so it is exercised where the fixture was generated too, and
``test_the_portable_comparison_can_fail`` shows it is not vacuous.

Regenerating is a deliberate act (a ground-level shadow really changed): run

    OGP_WRITE_SHADOW_GOLDEN=1 pytest tests/integration/test_shadow_caster_golden.py

which rewrites the fixture and FAILS, so the run cannot be mistaken for a pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_height import (
    DEFAULT_HEIGHTS_CM,
    METADATA_KEY,
    effective_height_cm,
    explicit_height_cm,
)
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle, is_bed_type
from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    compute_heatmap,
    point_rasterizer_reference,
)
from open_garden_planner.core.shadow_geometry import (
    circle_footprint,
    compute_scene_shadows,
    polyline_footprint,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.footprints import item_footprints
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    SunShadowController,
    SunShadowOverlayItem,
    collect_identified_casters,
    collect_shadow_casters,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "fixtures" / "shadows" / "shadow_golden.json"
PLANS = ROOT / "fixtures" / "plans"
WRITE_ENV = "OGP_WRITE_SHADOW_GOLDEN"
PLAN_NAMES = ("bench_small.ogp", "bench_large.ogp")
JUNE = date(2026, 6, 21)
BERLIN = {"latitude": 52.52, "longitude": 13.405}
#: Off the generating platform a coordinate may sit up to two steps of the 1/1000 cm
#: grid away (module docstring: libm before the rounding onto the grid).
PORTABLE_TOLERANCE_CM = 2e-3
#: Where "before" is: a release tag, which survives a squash merge.
GENERATED_FROM = ("release v1.29.10 - core/shadow_geometry.py and core/shade_aggregation.py are "
                  "byte-identical to it - as of integration-branch commit aaec048: the shadow "
                  "code before L1.6 (base stacking)")

Pair = tuple[list[tuple[float, float]], float]

FOOTPRINTS: dict[str, list[tuple[float, float]]] = {
    "square": [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
    "square_clockwise": [(0.0, 100.0), (100.0, 100.0), (100.0, 0.0), (0.0, 0.0)],
    "concave_l": [(0.0, 0.0), (300.0, 0.0), (300.0, 120.0), (120.0, 120.0), (120.0, 400.0),
                  (0.0, 400.0)],
    "circle_24": circle_footprint(300.0, 200.0, 50.0),
    "fence_strip": polyline_footprint([(0.0, 0.0), (400.0, 0.0), (400.0, 250.0)], 3.0)[0],
}
HEIGHTS = (100.0, 450.0)
ELEVATIONS = (15.0, 35.0, 60.0, 0.5)
AZIMUTHS = (135.0, 203.74, 300.0)
PLAN_SUNS = ((35.0, 203.74), (15.0, 135.0), (60.0, 300.0))
OVERLAY_INSTANTS = (datetime(2026, 6, 21, 12, 0, tzinfo=UTC), datetime(2026, 12, 21, 11, 0, tzinfo=UTC))
HEATMAP_DAYS = (date(2026, 6, 21), date(2026, 12, 21))


def _sha(value: Any) -> str:
    return hashlib.sha256(repr(value).encode()).hexdigest()


def _area(polygons: list[list[tuple[float, float]]]) -> float:
    """Signed shoelace area of a polygon set (holes come out negative)."""
    total = 0.0
    for polygon in polygons:
        count = len(polygon)
        for index in range(count):
            x1, y1 = polygon[index]
            x2, y2 = polygon[(index + 1) % count]
            total += x1 * y2 - x2 * y1
    return total / 2.0


def _summary(polygons: list[list[tuple[float, float]]]) -> dict[str, Any]:
    return {
        "polygons": len(polygons),
        "vertices": sum(len(p) for p in polygons),
        "area_cm2": _area(polygons),
        "sha256": _sha(polygons),
    }


#: The kinds L4's second owner pass gave a default height (ADR-065). v1.29.10 — the
#: golden's "before" — gave them none, so the golden's plan walk sees the bench plans
#: without them; what they add is pinned on its own
#: (``test_the_kinds_given_a_height_in_l4_add_only_their_own_casters``).
GIVEN_A_HEIGHT_IN_L4 = frozenset({"PARASOL", "FIRE_PIT", "PLANTER_POT", "COLD_FRAME", "RAIN_BARREL",
                                  "WATER_TAP", "SWING", "HAMMOCK", "PERGOLA"})


def _given_a_height_in_l4(item: Any) -> bool:
    object_type = getattr(item, "object_type", None)
    return (object_type is not None and object_type.name in GIVEN_A_HEIGHT_IN_L4
            and explicit_height_cm(getattr(item, "metadata", None)) is None)


def _load(plan: str, *, with_l4_heights: bool = False) -> CanvasScene:
    """A bench plan as v1.29.10 saw its casters (the kinds without a height then are
    hidden), or as it is (``with_l4_heights``)."""
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    if not with_l4_heights:
        for item in scene.items():
            if _given_a_height_in_l4(item):
                item.setVisible(False)
    return scene


def _walk(scene: Any, at: date) -> tuple[list[Pair], list[Pair], int]:
    """An independent caster walk: (every caster, those that stand on the ground,
    how many stand on a raised soil parent).

    Written against the pre-L1.6 API on purpose, so it is the ORACLE for which
    items the base rule touches: the same visibility / height / footprint rule as
    ``collect_shadow_casters`` (asserted equal below), plus the parent test —
    ``parent_bed_id`` names a visible soil container (``is_bed_type``) whose own
    effective height is not None, AND the item's centre is inside that parent's
    shape (review round 1: the link alone is bookkeeping). Spelled out with Qt's
    own calls here, not through the helpers under test.
    """
    items = scene.items()
    by_id = {str(i.item_id): i for i in items if hasattr(i, "item_id")}
    every: list[Pair] = []
    ground: list[Pair] = []
    raised = 0
    for item in items:
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        height = effective_height_cm(object_type, getattr(item, "metadata", None), at_date=at)
        if height is None:
            continue
        parent_id = getattr(item, "parent_bed_id", None)
        parent = by_id.get(str(parent_id)) if parent_id is not None else None
        on_soil = (
            parent is not None
            and parent.isVisible()
            and is_bed_type(parent.object_type)
            and effective_height_cm(parent.object_type, parent.metadata, at_date=at) is not None
            and bool(parent.contains(parent.mapFromScene(
                item.mapToScene(item.boundingRect().center()))))
        )
        for footprint in item_footprints(item, at):
            if len(footprint) >= 3:
                every.append((footprint, height))
                if on_soil:
                    raised += 1
                else:
                    ground.append((footprint, height))
    return every, ground, raised


def _overlay_scene() -> CanvasScene:
    """A garden with every caster class and NO plant in a raised bed."""
    scene = CanvasScene(3000.0, 2000.0)
    house = PolygonItem(
        [QPointF(400.0, 300.0), QPointF(900.0, 300.0), QPointF(900.0, 700.0), QPointF(650.0, 820.0),
         QPointF(400.0, 700.0)], object_type=ObjectType.HOUSE)
    fence = PolylineItem([QPointF(100.0, 100.0), QPointF(1500.0, 100.0), QPointF(1500.0, 600.0)],
                         object_type=ObjectType.FENCE, path_fence_style=PathFenceStyle.WOODEN_FENCE)
    wall = PolylineItem([QPointF(1800.0, 900.0), QPointF(2400.0, 1200.0)],
                        object_type=ObjectType.WALL)
    tree = CircleItem(1300.0, 1300.0, 150.0, object_type=ObjectType.TREE)
    tree.metadata[METADATA_KEY] = 600.0
    bed = RectangleItem(1900.0, 300.0, 300.0, 120.0, object_type=ObjectType.RAISED_BED)
    bed.setTransformOriginPoint(bed.rect().center())
    bed.setRotation(30.0)
    perennial = CircleItem(700.0, 1300.0, 25.0, object_type=ObjectType.PERENNIAL)
    perennial.metadata[METADATA_KEY] = 60.0
    pot = CircleItem(2500.0, 500.0, 30.0, object_type=ObjectType.CONTAINER_ROUND)
    lawn = RectangleItem(100.0, 1500.0, 800.0, 300.0, object_type=ObjectType.LAWN)
    for item in (house, fence, wall, tree, bed, perennial, pot, lawn):
        scene.addItem(item)
    return scene


def _overlay_paths(scene: CanvasScene) -> list[dict[str, Any]]:
    """The real overlay's painter path at each instant, as (element type, x, y)."""
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(OVERLAY_INSTANTS[0])
    controller.set_enabled(True)
    overlay = next(i for i in scene.items() if isinstance(i, SunShadowOverlayItem))
    paths = []
    for instant in OVERLAY_INSTANTS:
        controller.set_sim_datetime(instant)
        path = overlay.path()
        elements = []
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            elements.append([int(element.type.value), element.x, element.y])
        paths.append({"instant_utc": instant.isoformat(), "elements": elements})
    controller.set_enabled(False)
    return paths


def _wall_toy() -> tuple[list[Pair], HeatmapGrid]:
    """The campaign's toy case: a 200 cm east-west wall, cells north and south of it."""
    wall = [(-600.0, -5.0), (600.0, -5.0), (600.0, 5.0), (-600.0, 5.0)]
    return [(wall, 200.0)], HeatmapGrid.for_rect(-150.0, -300.0, 300.0, 600.0, cell_cm=50.0)


def build_golden() -> dict[str, Any]:
    """Everything this gate pins, computed by the code as it stands."""
    core = []
    for name, footprint in FOOTPRINTS.items():
        for height in HEIGHTS:
            for elevation in ELEVATIONS:
                for azimuth in AZIMUTHS:
                    polygons = compute_scene_shadows([(footprint, height)], elevation, azimuth)
                    core.append({"footprint": name, "height_cm": height, "elevation_deg": elevation,
                                 "azimuth_deg": azimuth,
                                 "polygons": [[list(p) for p in poly] for poly in polygons]})
    union = compute_scene_shadows(
        [(FOOTPRINTS["square"], 100.0), (FOOTPRINTS["circle_24"], 450.0),
         (FOOTPRINTS["concave_l"], 37.5)], 35.0, 203.74)
    night = compute_scene_shadows([(FOOTPRINTS["square"], 100.0)], -3.0, 180.0)

    plans: dict[str, Any] = {}
    for plan in PLAN_NAMES:
        scene = _load(plan)
        every, ground, raised = _walk(scene, JUNE)
        suns = []
        for elevation, azimuth in PLAN_SUNS:
            suns.append({
                "elevation_deg": elevation, "azimuth_deg": azimuth,
                "all_from_the_ground": _summary(compute_scene_shadows(every, elevation, azimuth)),
                "ground_casters_only": _summary(compute_scene_shadows(ground, elevation, azimuth)),
            })
        plans[plan] = {"casters": len(every), "casters_sha256": _sha(every),
                       "on_raised_soil": raised, "suns": suns}

    overlay = _overlay_paths(_overlay_scene())

    casters, grid = _wall_toy()
    heatmap = []
    for day in HEATMAP_DAYS:
        minutes = compute_heatmap(casters, BERLIN["latitude"], BERLIN["longitude"], day, grid,
                                  point_rasterizer_reference)
        assert minutes is not None
        heatmap.append({"day": day.isoformat(), "minutes": minutes.tolist()})

    return {
        "meta": {
            "generated_from": GENERATED_FROM,
            "platform": sys.platform,
            "python": platform.python_version(),
        },
        "core": core,
        "union": [[list(p) for p in poly] for poly in union],
        "night": night,
        "plans": plans,
        "overlay": overlay,
        "heatmap": heatmap,
    }


def _same_numbers(actual: Any, expected: Any, where: str = "") -> None:
    """Exact on the generating platform; elsewhere same structure, vertices ± 2e-3 cm."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), where
        for key in expected:
            _same_numbers(actual[key], expected[key], f"{where}/{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _same_numbers(a, e, f"{where}[{index}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, abs=PORTABLE_TOLERANCE_CM), where
    else:
        assert actual == expected, where


def _portable(golden: dict[str, Any]) -> dict[str, Any]:
    """The golden without what only the generating platform can reproduce: the
    hashes, and the union areas (compared with a relative tolerance instead)."""
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items()
                    if k not in ("sha256", "casters_sha256", "area_cm2", "meta")}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(golden)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def current(qapp: Any) -> dict[str, Any]:
    # through JSON, so tuples and float formatting compare like the stored file
    return json.loads(json.dumps(build_golden()))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def golden(current: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get(WRITE_ENV):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(current, separators=(",", ":")) + "\n", encoding="utf-8")
        pytest.fail(f"{GOLDEN.name} rewritten — review the diff, commit it, and unset {WRITE_ENV}")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _assert_portably_equal(current: dict[str, Any], golden: dict[str, Any]) -> None:
    """What EVERY platform enforces: structure, coordinates to the grid, areas."""
    _same_numbers(_portable(current), _portable(golden))
    for plan in PLAN_NAMES:
        for now, then in zip(current["plans"][plan]["suns"], golden["plans"][plan]["suns"],
                             strict=True):
            for key in ("all_from_the_ground", "ground_casters_only"):
                assert now[key]["area_cm2"] == pytest.approx(then[key]["area_cm2"], rel=1e-6)


def test_ground_level_shadows_match_the_golden(golden: dict[str, Any], current: dict[str, Any]) -> None:
    """Every number of the gate, against the fixture generated before L1.6: to the
    grid on any platform, and bit for bit on the one that generated it."""
    assert golden["meta"] == {"generated_from": GENERATED_FROM, "platform": "win32",
                              "python": "3.12.9"}
    _assert_portably_equal(current, golden)
    if sys.platform == golden["meta"]["platform"]:
        for section in ("core", "union", "night", "plans", "overlay", "heatmap"):
            assert current[section] == golden[section], f"{section} differs from the golden"


def test_the_portable_comparison_can_fail(golden: dict[str, Any]) -> None:
    """The gate Linux runs is a gate: it refuses a coordinate three grid steps off, a
    lost vertex, a lost polygon and an area off by a part in 100,000 — and lets a
    single grid step pass (that is the libm allowance, and its whole extent)."""
    def moved(by_cm: float) -> dict[str, Any]:
        copy = json.loads(json.dumps(golden))
        copy["core"][7]["polygons"][0][1][0] += by_cm
        return copy  # type: ignore[no-any-return]

    _assert_portably_equal(moved(0.001), golden)  # one grid step: allowed
    with pytest.raises(AssertionError, match="core"):
        _assert_portably_equal(moved(0.003), golden)
    fewer = json.loads(json.dumps(golden))
    fewer["core"][7]["polygons"][0].pop()
    with pytest.raises(AssertionError, match="core"):
        _assert_portably_equal(fewer, golden)
    lost = json.loads(json.dumps(golden))
    lost["union"].pop()
    with pytest.raises(AssertionError, match="union"):
        _assert_portably_equal(lost, golden)
    path = json.loads(json.dumps(golden))
    path["overlay"][0]["elements"][3][0] = 99  # a path element of another type
    with pytest.raises(AssertionError, match="overlay"):
        _assert_portably_equal(path, golden)
    area = json.loads(json.dumps(golden))
    area["plans"][PLAN_NAMES[0]]["suns"][0]["ground_casters_only"]["area_cm2"] *= 1.00001
    with pytest.raises(AssertionError):
        _assert_portably_equal(area, golden)
    minutes = json.loads(json.dumps(golden))
    minutes["heatmap"][0]["minutes"][0][0] += 15.0  # one heatmap sample
    with pytest.raises(AssertionError, match="heatmap"):
        _assert_portably_equal(minutes, golden)


def test_the_matrix_is_complete(golden: dict[str, Any]) -> None:
    assert len(golden["core"]) == len(FOOTPRINTS) * len(HEIGHTS) * len(ELEVATIONS) * len(AZIMUTHS)
    assert all(case["polygons"] for case in golden["core"])  # every case casts a shadow
    assert golden["night"] == []
    # bench_small: 45 perennials have a parent bed, 22 of them a RAISED one (the
    # other 23 stand in in-ground GARDEN_BEDs and keep casting from the ground)
    assert {p: golden["plans"][p]["on_raised_soil"] for p in PLAN_NAMES} == {
        "bench_small.ogp": 22, "bench_large.ogp": 240}
    assert all(len(entry["elements"]) > 20 for entry in golden["overlay"])
    summer, winter = (entry["minutes"] for entry in golden["heatmap"])
    assert max(map(max, summer)) > 600.0 and min(map(min, winter)) == 0.0


def _assert_summary(now: dict[str, Any], then: dict[str, Any], exact: bool) -> None:
    if exact:
        assert now == then
    else:
        assert (now["polygons"], now["vertices"]) == (then["polygons"], then["vertices"])
        assert now["area_cm2"] == pytest.approx(then["area_cm2"], rel=1e-6)


@pytest.mark.parametrize("plan", PLAN_NAMES)
def test_with_the_real_casters_only_the_plants_on_raised_soil_changed(
    qtbot: Any, golden: dict[str, Any], plan: str
) -> None:
    """The statement of what L1.6 changes in the shipped 2D shadows, on real plans.

    ``collect_shadow_casters`` now returns ``ShadowCaster``s with a base. Against
    the golden generated BEFORE that existed:

    - the walk finds the same footprints and heights, in the same order;
    - with every base forced to 0 — and as plain pre-L1.6 pairs — the union of
      all shadows is what it was;
    - the casters whose real base is 0 give, on their own, the golden's
      "ground casters only" union: nothing that stands on the ground moved;
    - the casters with a base are exactly the plants on raised soil the
      independent oracle counted (22 and 240), and with them the picture differs.
    """
    entry = golden["plans"][plan]
    exact = sys.platform == golden["meta"]["platform"]
    casters = collect_shadow_casters(_load(plan), at_date=JUNE)
    pairs = [(c.footprint, c.height_cm) for c in casters]
    assert len(pairs) == entry["casters"]
    if exact:
        assert _sha(pairs) == entry["casters_sha256"]
    on_the_ground = [c for c in casters if c.base_cm == 0.0]
    raised = [c for c in casters if c.base_cm > 0.0]
    assert len(raised) == entry["on_raised_soil"] > 0
    assert len(on_the_ground) + len(raised) == len(casters)
    for sun in entry["suns"]:
        elevation, azimuth = sun["elevation_deg"], sun["azimuth_deg"]
        before = sun["all_from_the_ground"]
        grounded = [c._replace(base_cm=0.0) for c in casters]
        _assert_summary(_summary(compute_scene_shadows(grounded, elevation, azimuth)), before, exact)
        _assert_summary(_summary(compute_scene_shadows(pairs, elevation, azimuth)), before, exact)
        _assert_summary(_summary(compute_scene_shadows(on_the_ground, elevation, azimuth)),
                        sun["ground_casters_only"], exact)
        now = _summary(compute_scene_shadows(casters, elevation, azimuth))
        assert now["sha256"] != before["sha256"]  # the visible change: raised plants cast further


@pytest.mark.parametrize("plan", PLAN_NAMES)
def test_the_oracle_walk_is_the_production_walk(qtbot: Any, plan: str) -> None:
    """``_walk`` is an independent re-derivation; it must see exactly the casters
    ``collect_shadow_casters`` sees, in the same order, or the golden's two unions
    would describe another scene."""
    scene = _load(plan)
    every, ground, raised = _walk(scene, JUNE)
    production = collect_shadow_casters(scene, at_date=JUNE)
    assert [(list(c[0]), c[1]) for c in production] == [(list(fp), h) for fp, h in every]
    assert len(every) == len(ground) + raised and raised > 0


@pytest.mark.parametrize(("plan", "added"), [("bench_small.ogp", 2), ("bench_large.ogp", 20)])
def test_the_kinds_given_a_height_in_l4_add_only_their_own_casters(
        qtbot: Any, plan: str, added: int) -> None:
    """L4's second owner pass (ADR-065): "doesn't make sense that a parasol doesn't
    have a height, while a trampoline has it". The nine kinds without a height got a
    default, so they cast in the 2D sun study — and that is ALL that changes: with them
    the walk is the golden's walk plus their own casters, each at its kind's default
    height, standing on the ground (bench_small: a fire pit and a rain barrel;
    bench_large: twenty rain barrels)."""
    before = [(list(c.footprint), c.height_cm, c.base_cm)
              for c in collect_shadow_casters(_load(plan), at_date=JUNE)]
    scene = _load(plan, with_l4_heights=True)
    after = [(list(c.footprint), c.height_cm, c.base_cm)
             for c in collect_shadow_casters(scene, at_date=JUNE)]
    by_id = {str(item.item_id): item for item in scene.items() if hasattr(item, "item_id")}
    theirs = [caster for caster in collect_identified_casters(scene, at_date=JUNE)
              if _given_a_height_in_l4(by_id[caster.item_id])]
    assert len(theirs) == added and len(after) == len(before) + added
    assert [pair for pair in after if pair not in before] == [
        (list(footprint), caster.height_cm, caster.base_cm)
        for caster in theirs for footprint in caster.footprints]
    for caster in theirs:
        assert caster.height_cm == DEFAULT_HEIGHTS_CM[by_id[caster.item_id].object_type.name]
        assert caster.base_cm == 0.0
