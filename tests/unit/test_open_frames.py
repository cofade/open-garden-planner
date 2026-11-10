"""Open frames in the 2D sun study (#698): a pergola, a trellis, a swing, a hammock and
a garden light cast their footprint prism WEIGHTED by the share of the sun their own
members let through.

What is held here, Qt-free:

- **the registry and its drift guard** — which kinds are open frames is a recorded
  decision (``core.object_height``); every kind whose 3D model is mostly air is in one
  of three lists (open frame / solid by decision / no 2D shadow), so a new open kind
  cannot become a solid prism by being forgotten;
- **the number** — the transmittance of every open kind against an independent
  measurement (``scripts/measure_built_world_shadows.py``: every triangle of the
  production mesh projected and united), over sizes, elevations and azimuths;
- **the turn** — a frame carries its members in its own coordinates and its turn
  beside them; a turned frame is held to the geometry turned by hand. A defect
  proportional to a rotation is 0 at rotation 0, so nothing here is tested at 0 alone;
- **many of them** — fifty garden lights are one frame fifty times: one weighing a sun
  position, one region, and the partition of the weighted shades asks no clip of two
  shades that cannot meet (and still gives what the plain pairwise partition gives);
- **the consumers** — the weighted shadow regions (what the overlay paints and the 3D
  drape lays), the hours-of-sun grid and the per-plant estimate each read the SAME
  transmittance, also for a plant standing on raised soil.

The Qt half (the caster walk, the painted overlay, the heatmap controller, undo) is
``tests/integration/test_open_frame_shade.py``.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from datetime import date
from functools import cache
from pathlib import Path
from types import ModuleType

import numpy as np
import pyclipper
import pytest

from open_garden_planner.core import object_height
from open_garden_planner.core.object_height import (
    NO_2D_SHADOW_TYPE_NAMES,
    OPEN_FRAME_TYPE_NAMES,
    SOLID_2D_DECISIONS,
    is_open_frame,
)
from open_garden_planner.core.scene3d.builders import OBJECT_KINDS, production_registry
from open_garden_planner.core.scene3d.builders.common import nominal_height_cm
from open_garden_planner.core.scene3d.builders.open_frames import (
    OPEN_FRAME_BUILDERS,
    open_frame_triangles,
    open_frame_triangles_for_record,
)
from open_garden_planner.core.shade_aggregation import (
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    _slice_frame_for_elevation,
    compute_sun_exposure,
    daylight_samples,
    point_rasterizer_reference,
)
from open_garden_planner.core.shadow_geometry import (
    CLIPPER_SCALE,
    MIN_SUN_ELEVATION_DEG,
    GroupedCaster,
    OpenFrame,
    WeightedShadowRegion,
    _boxes_meeting_another,
    _diff_int,
    _frame_shadow_area_cm2,
    _intersect_int,
    _open_frame_transmittance,
    _to_int,
    _union_int,
    caster_transmittance,
    circle_footprint,
    compute_scene_shadows,
    compute_weighted_shadows,
    open_frame_transmittance,
    shadow_direction_scene,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "measure_built_world_shadows.py"
OPEN_KINDS = sorted(OPEN_FRAME_TYPE_NAMES)
#: A kind is "mostly air" when its 3D shadow covers less than this share of its 2D
#: prism's at one of the table's three elevations.
MOSTLY_AIR = 0.5
#: Footprints per open kind: the shadow-agreement table's own, a larger one and a
#: smaller one (a circle: its radius). The capped member sizes do not scale with the
#: footprint, so a table of shares per kind would be wrong for two of every three.
SIZES: dict[str, tuple[object, ...]] = {
    "PERGOLA": ((300.0, 300.0), (600.0, 400.0), (200.0, 260.0)),
    "TRELLIS": ((200.0, 20.0), (400.0, 20.0), (100.0, 10.0)),
    "SWING": ((200.0, 150.0), (300.0, 200.0), (150.0, 120.0)),
    "HAMMOCK": ((300.0, 120.0), (350.0, 150.0), (250.0, 100.0)),
    "GARDEN_LIGHT": (20.0, 30.0, 10.0),
}
ELEVATIONS = (8.0, 15.0, 35.0, 60.0, 78.0)
AZIMUTHS = (0.0, 40.0, 90.0, 135.0, 180.0, 250.0, 300.0)
BERLIN = (52.52, 13.405)


@cache
def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_built_world_shadows_open_frames", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    w, d = width / 2.0, depth / 2.0
    return ((-w, -d), (w, -d), (w, d), (-w, d))


def _record(kind: str, size: object, height: float | None = None):
    script = _script()
    height = nominal_height_cm(kind) if height is None else height
    assert height is not None
    if isinstance(size, float):
        return script._circle(kind, size, height)
    return script._polygon(kind, script._rectangle(*size), height)  # type: ignore[misc]


def _measured_share(record, elevation: float, azimuth: float) -> float:
    """The independent number: ALL triangles of the production mesh, projected and
    united by the measuring script, over the 2D prism's shadow."""
    script = _script()
    parts = production_registry().build(record)
    in_3d = script._area_cm2(script.mesh_shadow(parts, elevation, azimuth))
    in_2d = script._area_cm2(script.caster_shadow(record, elevation, azimuth))
    return in_3d / in_2d


def _turned(points, degrees: float):
    """Scene points (x, y[, z]) turned counter-clockwise about the origin (north up)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return tuple((c * p[0] - s * p[1], s * p[0] + c * p[1], *p[2:]) for p in points)


def _placed(points, turn_deg: float, offset=(0.0, 0.0)):
    """Local points as they stand in the scene: turned about the origin, then moved."""
    return tuple((p[0] + offset[0], p[1] + offset[1], *p[2:]) for p in _turned(points, turn_deg))


def _frame(kind: str, size: object, turn_deg: float = 0.0) -> OpenFrame:
    record = _record(kind, size)
    local = open_frame_triangles_for_record(record)
    assert local is not None
    return OpenFrame(local, record.footprints[0], turn_deg)


def _caster(kind: str, size: object, *, turn_deg: float = 0.0, offset=(0.0, 0.0),
            base_cm: float = 0.0, item_id: str | None = None) -> IdentifiedCaster:
    """The caster the walk makes of an item of ``kind``: its footprint prism where the
    item stands, and its frame — the members in the item's own coordinates, with its
    turn."""
    record = _record(kind, size)
    footprint = _placed(record.footprints[0], turn_deg, offset)
    return IdentifiedCaster(item_id or kind, (footprint,), float(record.height_cm), base_cm,
                            frame=_frame(kind, size, turn_deg))


def _by_hand(kind: str, size: object, turn_deg: float, elevation: float, azimuth: float) -> float:
    """The transmittance of an item TURNED IN THE SCENE, with nothing of the code under
    test: every member triangle turned by hand, moved along the sun ray, united by
    pyclipper here; the prism swept by ``compute_scene_shadows`` from the turned
    footprint."""
    record = _record(kind, size)
    local = open_frame_triangles_for_record(record)
    assert local is not None
    offset = (410.0, -130.0)
    footprint = _placed(record.footprints[0], turn_deg, offset)
    corners = np.asarray([_placed(triangle, turn_deg, offset) for triangle in local], dtype=np.float64)
    direction = shadow_direction_scene(azimuth)
    reach = corners[:, :, 2] / math.tan(math.radians(elevation))
    grid = np.rint(np.stack([corners[:, :, 0] + reach * direction[0],
                             corners[:, :, 1] + reach * direction[1]], axis=2)
                   * CLIPPER_SCALE).astype(np.int64).tolist()
    clipper = pyclipper.Pyclipper()
    for path in grid:
        if pyclipper.Area(path) != 0:
            clipper.AddPath(path if pyclipper.Orientation(path) else path[::-1],
                            pyclipper.PT_SUBJECT, True)
    union = clipper.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    frame_area = sum(pyclipper.Area(path) for path in union)
    prism = compute_scene_shadows([(list(footprint), float(record.height_cm))], elevation, azimuth)
    prism_area = sum(pyclipper.Area(_to_int(polygon)) for polygon in prism)
    return 1.0 - frame_area / prism_area


# ── the registry and its drift guard ─────────────────────────────────────────


def test_the_three_lists_name_real_object_types_and_do_not_overlap() -> None:
    from open_garden_planner.core.object_types import ObjectType

    real = {member.name for member in ObjectType}
    lists = {"open frames": set(OPEN_FRAME_TYPE_NAMES), "solid by decision": set(SOLID_2D_DECISIONS),
             "no 2D shadow": set(NO_2D_SHADOW_TYPE_NAMES)}
    for label, names in lists.items():
        assert names and names <= real, (label, names - real)
        assert names <= OBJECT_KINDS, (label, names - OBJECT_KINDS)  # each has a 3D model of its own
    names = [name for group in lists.values() for name in group]
    assert len(names) == len(set(names))  # one decision a kind
    assert sorted(OPEN_FRAME_TYPE_NAMES) == ["GARDEN_LIGHT", "HAMMOCK", "PERGOLA", "SWING", "TRELLIS"]
    assert all(reason.strip() for reason in SOLID_2D_DECISIONS.values())  # a decision has a reason


def test_every_open_kind_has_the_production_builder_its_members_come_from() -> None:
    """A kind listed open without a builder here would have no members, and be cast
    solid without a word."""
    assert set(OPEN_FRAME_BUILDERS) == OPEN_FRAME_TYPE_NAMES
    registry = production_registry()
    for kind, builder in OPEN_FRAME_BUILDERS.items():
        assert registry.builder_for(kind) is builder, kind
    from open_garden_planner.core.object_types import ObjectType

    for member in ObjectType:  # asked of the real enum, by member and by name
        assert is_open_frame(member) == is_open_frame(member.name) == (member.name in OPEN_FRAME_TYPE_NAMES)


@cache
def _prism_shares() -> dict[str, tuple[float, ...]]:
    """Every object kind of the shadow-agreement table: the share of its 2D PRISM's
    shadow which its 3D model covers, at the table's three elevations (unweighted)."""
    script = _script()
    shares = {}
    for kind, size in script.L4_OBJECT_SIZES.items():
        record = _record(kind, size)
        shares[kind] = tuple(_measured_share(record, elevation, script.SOUTH)
                             for elevation in script.ELEVATIONS_DEG)
    return shares


def test_no_mostly_air_kind_is_a_solid_prism_without_a_recorded_decision() -> None:
    """THE drift guard. The script holds a case for every object kind that casts in 2D
    (its own assertion: ``L4_OBJECT_SIZES`` is ``OBJECT_KINDS`` less the no-shadow
    kinds). Every one whose 3D model shades less than half of its prism's shadow is
    an open frame or a solid BY DECISION — a new pergola-like kind, or a builder that
    opens an old kind up, fails here until someone decides."""
    script = _script()
    assert set(script.L4_OBJECT_SIZES) == OBJECT_KINDS - NO_2D_SHADOW_TYPE_NAMES
    mostly_air = {kind for kind, shares in _prism_shares().items() if min(shares) < MOSTLY_AIR}
    decided = OPEN_FRAME_TYPE_NAMES | set(SOLID_2D_DECISIONS)
    assert mostly_air - decided == set(), "decide: an open frame, or solid with a reason"
    # … and the lists do not rot: nothing is recorded as mostly air that no longer is
    assert decided - mostly_air == set()
    assert mostly_air == {
        "PERGOLA", "TRELLIS", "SWING", "HAMMOCK", "GARDEN_LIGHT",          # open frames
        "TABLE_RECTANGULAR", "TABLE_ROUND", "PICNIC_TABLE", "TRAMPOLINE", "BENCH", "CHAIR",
        "BBQ_GRILL", "WHEELBARROW", "BIRD_BATH", "PARASOL", "GREENHOUSE",  # solid by decision
    }


def test_an_open_frame_is_thin_members_at_every_elevation_a_canopy_is_not() -> None:
    """Why the parasol is not on the list although it is mostly air: an open frame's
    share hardly moves with the sun (its members are thin from every side), a solid
    top on a pole swings from a quarter of its prism to well over half."""
    shares = _prism_shares()
    for kind in OPEN_KINDS:
        assert max(shares[kind]) < MOSTLY_AIR, kind
        assert max(shares[kind]) - min(shares[kind]) < 0.2, kind
    parasol = shares["PARASOL"]
    assert max(parasol) > MOSTLY_AIR and max(parasol) - min(parasol) > 0.3


# ── the number ───────────────────────────────────────────────────────────────


def test_no_members_no_sun_no_prism_all_let_the_sun_through() -> None:
    ring = _rect(300.0, 300.0)
    triangles = open_frame_triangles("PERGOLA", "rectangle", ring, 250.0)
    assert triangles is not None and len(triangles) == 22 * 10  # 22 members, a box is 10 triangles
    assert max(z for triangle in triangles for _x, _y, z in triangle) == pytest.approx(250.0)
    frame = OpenFrame(triangles, ring)
    assert open_frame_transmittance(OpenFrame((), ring), 250.0, 35.0, 180.0) == 1.0
    assert open_frame_transmittance(frame, 250.0, MIN_SUN_ELEVATION_DEG / 2, 180.0) == 1.0
    assert open_frame_transmittance(frame, 0.0, 35.0, 180.0) == 1.0
    assert open_frame_transmittance(OpenFrame(triangles, ()), 250.0, 35.0, 180.0) == 1.0
    assert 0.0 < open_frame_transmittance(frame, 250.0, 35.0, 180.0) < 1.0


def test_what_is_no_open_frame_has_no_members() -> None:
    """None, never an empty tuple: None is "cast it solid", empty is "nothing solid"."""
    ring = _rect(300.0, 300.0)
    assert open_frame_triangles("PARASOL", "rectangle", ring, 250.0) is None
    assert open_frame_triangles("GREENHOUSE", "rectangle", ring, 220.0) is None
    assert open_frame_triangles("PERGOLA", "rectangle", ring, 0.0) is None
    assert open_frame_triangles("PERGOLA", "rectangle", ring[:2], 250.0) is None
    # the 3D builder has no pergola for a round footprint and no swing for a
    # triangle: it builds the plain block, and the 2D model casts the solid prism
    disc = tuple(circle_footprint(0.0, 0.0, 150.0))
    assert open_frame_triangles("PERGOLA", "circle", disc, 250.0, radius_cm=150.0) is None
    assert open_frame_triangles("SWING", "polygon", ((0.0, 0.0), (300.0, 0.0), (0.0, 300.0)), 220.0) is None


@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_transmittance_is_the_measured_share_at_the_table_s_elevations(kind: str) -> None:
    """The issue's gate, as #440 set it for fences: the 2D model's weighted shadow is
    within 10 % of the 3D model's — here within 2 %, at 15 / 35 / 60 degrees."""
    script = _script()
    record = _record(kind, SIZES[kind][0])
    row = {case.name: case for case in script.cases()}[kind.lower().replace("_", " ")]
    assert row.record.footprints == record.footprints and row.record.height_cm == record.height_cm
    for elevation in script.ELEVATIONS_DEG:
        measured = _measured_share(record, elevation, script.SOUTH)
        weight = script.caster_occlusion(record, elevation, script.SOUTH)
        assert 0.1 < weight < MOSTLY_AIR, (kind, elevation, weight)
        assert measured / weight == pytest.approx(1.0, abs=0.02), (kind, elevation)


@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_transmittance_follows_the_size_the_elevation_and_the_azimuth(kind: str) -> None:
    """Three sizes, five elevations, seven azimuths, against ALL triangles of the
    production mesh united: a table of shares per kind could hold one of the 105."""
    worst = 0.0
    seen = set()
    for size in SIZES[kind]:
        record = _record(kind, size)
        frame = _frame(kind, size)
        height = float(record.height_cm)
        for elevation in ELEVATIONS:
            for azimuth in AZIMUTHS:
                through = open_frame_transmittance(frame, height, elevation, azimuth)
                measured = _measured_share(record, elevation, azimuth)
                worst = max(worst, abs((1.0 - through) - measured))
                seen.add(round(1.0 - through, 2))
    assert worst <= 0.02, (kind, worst)
    assert max(seen) - min(seen) > 0.08, (kind, sorted(seen))  # … and it is no constant


@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_sunlit_triangles_cover_what_all_triangles_cover(kind: str) -> None:
    """``_frame_shadow_area_cm2`` unites the triangles that face the sun only. That is
    the whole shadow for the solids the builders make; this holds each kind to it."""
    for size in SIZES[kind]:
        triangles = open_frame_triangles_for_record(_record(kind, size))
        assert triangles is not None
        corners = np.asarray(triangles, dtype=np.float64)
        for elevation in ELEVATIONS:
            for azimuth in AZIMUTHS:
                direction = shadow_direction_scene(azimuth)
                reach = corners[:, :, 2] / math.tan(math.radians(elevation))
                grid = np.rint(np.stack([corners[:, :, 0] + reach * direction[0],
                                         corners[:, :, 1] + reach * direction[1]], axis=2)
                               * CLIPPER_SCALE).astype(np.int64).tolist()
                clipper = pyclipper.Pyclipper()
                for path in grid:
                    if pyclipper.Area(path) == 0:
                        continue
                    clipper.AddPath(path if pyclipper.Orientation(path) else path[::-1],
                                    pyclipper.PT_SUBJECT, True)
                union = clipper.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
                every = sum(pyclipper.Area(path) for path in union) / CLIPPER_SCALE ** 2
                lit = _frame_shadow_area_cm2(triangles, elevation, direction)
                # to a ten-thousandth: edge-on slivers round differently on the grid
                assert lit == pytest.approx(every, rel=1e-4), (kind, size, elevation, azimuth)


def test_a_pergola_s_members_are_its_one_layout() -> None:
    """The 2D shade reads ``core.pergola``'s layout — the one its 2D picture and its 3D
    timber come from: a wider pergola has the same nine rafters and lets more sun
    through; one built twice as high shades less of a prism twice as long."""
    from open_garden_planner.core import pergola

    plan = pergola.layout(300.0, 300.0, 250.0)
    assert plan is not None
    members = len(plan.posts) + len(plan.beams) + len(plan.rafters) + len(plan.purlins)
    assert members == 22
    triangles = open_frame_triangles("PERGOLA", "rectangle", _rect(300.0, 300.0), 250.0)
    assert triangles is not None and len(triangles) == members * 10
    xs = sorted({round(x, 6) for triangle in triangles for x, _y, _z in triangle})
    assert xs[0] == pytest.approx(min(r.x0 for r in plan.purlins))  # the layout's own edges
    assert xs[-1] == pytest.approx(max(r.x1 for r in plan.purlins))

    def through(width: float, depth: float, height: float) -> float:
        ring = _rect(width, depth)
        made = open_frame_triangles("PERGOLA", "rectangle", ring, height)
        assert made is not None
        return open_frame_transmittance(OpenFrame(made, ring), height, 35.0, 180.0)

    assert through(600.0, 400.0, 250.0) > through(300.0, 300.0, 250.0) + 0.05
    assert through(300.0, 300.0, 500.0) > through(300.0, 300.0, 250.0) + 0.05


# ── the turn ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("turn_deg", [0.0, 17.0, 90.0, 213.0])
@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_a_turned_frame_is_weighed_as_the_geometry_turned_by_hand(kind: str, turn_deg: float) -> None:
    """A frame's members stay in its own coordinates and its turn is a number beside
    them. This holds that number to the real thing: the item turned counter-clockwise
    in the scene (+x east, +y north), every member projected and united here. A frame
    read with the turn the wrong way round — or not at all — fails, and only away from
    a turn of 0."""
    caster = _caster(kind, SIZES[kind][0], turn_deg=turn_deg, offset=(730.0, -260.0))
    for elevation in (15.0, 35.0, 60.0):
        for azimuth in (100.0, 180.0, 245.0):
            want = _by_hand(kind, SIZES[kind][0], turn_deg, elevation, azimuth)
            got = caster_transmittance(caster, elevation, azimuth)
            assert got == pytest.approx(want, abs=0.02), (kind, turn_deg, elevation, azimuth)


@pytest.mark.parametrize("turn_deg", [17.0, 213.0])
@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_a_frame_turned_with_the_sun_shades_the_same(kind: str, turn_deg: float) -> None:
    """Turning the item counter-clockwise by t and the sun's bearing by -t (a bearing
    runs clockwise) is the same garden seen from another side."""
    plain = _caster(kind, SIZES[kind][0])
    turned = _caster(kind, SIZES[kind][0], turn_deg=turn_deg, offset=(730.0, -260.0))
    for elevation in (15.0, 35.0, 60.0):
        for azimuth in (100.0, 180.0, 245.0):
            want = caster_transmittance(plain, elevation, azimuth)
            got = caster_transmittance(turned, elevation, azimuth - turn_deg)
            assert got == pytest.approx(want, abs=1e-9), (kind, turn_deg, elevation, azimuth)


def test_a_trellis_turned_against_the_sun_shades_differently() -> None:
    """The control of the test above: the turn matters. Square to the sun a trellis is
    its lattice; a quarter turn on, the sun runs along it and meets post and rail end on."""
    square = _caster("TRELLIS", (200.0, 20.0))
    along = _caster("TRELLIS", (200.0, 20.0), turn_deg=90.0)
    assert abs(caster_transmittance(square, 60.0, 180.0)
               - caster_transmittance(along, 60.0, 180.0)) > 0.08
    # … and which WAY: a trellis turned 30 degrees one way is not one turned the other
    one_way = _by_hand("TRELLIS", (200.0, 20.0), 30.0, 29.0, 224.0)
    other_way = _by_hand("TRELLIS", (200.0, 20.0), -30.0, 29.0, 224.0)
    assert abs(one_way - other_way) > 0.03
    assert caster_transmittance(_caster("TRELLIS", (200.0, 20.0), turn_deg=30.0), 29.0, 224.0) \
        == pytest.approx(one_way, abs=0.02)


@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_a_frame_standing_on_a_base_lets_the_same_sun_through(kind: str) -> None:
    """Raised as a whole, a frame's shadow and its prism's both move ``base / tan a``
    along the sun ray: where the shade falls changes (the weighted region's outline
    moves), how dark it is does not."""
    on_ground = _caster(kind, SIZES[kind][0], turn_deg=20.0)
    raised = _caster(kind, SIZES[kind][0], turn_deg=20.0, base_cm=38.0)
    for elevation, azimuth in ((15.0, 120.0), (35.0, 180.0), (60.0, 230.0)):
        assert caster_transmittance(raised, elevation, azimuth) == pytest.approx(
            caster_transmittance(on_ground, elevation, azimuth), abs=1e-4)
        low = compute_weighted_shadows([on_ground], elevation, azimuth)
        high = compute_weighted_shadows([raised], elevation, azimuth)
        assert low is not None and high is not None
        assert high.union_polygons != low.union_polygons
        assert high.weighted_regions[0].transmittance == pytest.approx(
            low.weighted_regions[0].transmittance, abs=1e-4)


def test_an_explicit_transmittance_still_wins_and_a_plain_caster_is_opaque() -> None:
    pergola = _caster("PERGOLA", (300.0, 300.0))
    assert pergola.frame is not None
    explicit = GroupedCaster(pergola.footprints, pergola.height_cm, transmittance=0.25,
                             frame=pergola.frame)
    assert caster_transmittance(explicit, 35.0, 180.0) == 0.25
    solid = GroupedCaster(pergola.footprints, pergola.height_cm)
    assert caster_transmittance(solid, 35.0, 180.0) == 0.0
    emptied = GroupedCaster(pergola.footprints, pergola.height_cm,
                            frame=pergola.frame.with_triangles(()))
    assert caster_transmittance(emptied, 35.0, 180.0) == 1.0  # an open frame with nothing solid


def test_a_frame_is_plain_immutable_data_compared_by_value() -> None:
    """What crosses to the heatmap worker and sits in the overlay's cache key: equal
    frames are equal and hash alike (a snapshot of an unchanged plan compares equal),
    a different turn or member is a different frame, and nothing can be assigned."""
    ring = _rect(300.0, 300.0)
    triangles = open_frame_triangles("PERGOLA", "rectangle", ring, 250.0)
    assert triangles is not None
    one, same = OpenFrame(triangles, ring, 30.0), OpenFrame(list(triangles), list(ring), 30.0)
    assert one == same and hash(one) == hash(same) and one is not same
    assert one != OpenFrame(triangles, ring, 31.0)
    assert one != OpenFrame(triangles[:-1], ring, 30.0)
    assert one != OpenFrame(triangles, _rect(300.0, 301.0), 30.0)
    assert one != "a frame" and one.with_triangles(()).triangles == ()
    assert one.with_triangles(()).footprint == one.footprint
    with pytest.raises(AttributeError):
        one.rotation_deg = 0.0  # type: ignore[misc]
    assert "220 triangles" in repr(one)
    caster = IdentifiedCaster("a", (ring,), 250.0, frame=one)
    assert caster == IdentifiedCaster("a", (ring,), 250.0, frame=same)
    assert hash(caster) == hash(IdentifiedCaster("a", (ring,), 250.0, frame=same))


# ── the consumers ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("turn_deg", [0.0, 30.0, 90.0])
@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_weighted_regions_carry_the_frame_s_transmittance(kind: str, turn_deg: float) -> None:
    """What the overlay paints and the 3D drape lays: ONE region, the prism's own
    outline, at the frame's transmittance — not the solid union region."""
    caster = _caster(kind, SIZES[kind][0], turn_deg=turn_deg, offset=(500.0, 500.0))
    solid = IdentifiedCaster("solid", caster.footprints, caster.height_cm)
    for elevation, azimuth in ((15.0, 120.0), (35.0, 180.0), (60.0, 230.0)):
        weighted = compute_weighted_shadows([caster], elevation, azimuth)
        opaque = compute_weighted_shadows([solid], elevation, azimuth)
        assert weighted is not None and opaque is not None
        (region,) = weighted.weighted_regions
        through = caster_transmittance(caster, elevation, azimuth)
        assert 0.5 < through < 0.9
        assert region.transmittance == pytest.approx(through, abs=1e-6)
        assert region.occlusion == pytest.approx(1.0 - through, abs=1e-6)
        assert weighted.union_polygons == opaque.union_polygons  # the same ground, lighter
        assert opaque.weighted_regions[0].occlusion == 1.0


def test_a_solid_in_front_of_a_frame_stays_dark_and_two_frames_multiply() -> None:
    pergola = _caster("PERGOLA", (300.0, 300.0), offset=(500.0, 500.0), item_id="pergola")
    second = _caster("PERGOLA", (300.0, 300.0), offset=(560.0, 520.0), item_id="second")
    wall = IdentifiedCaster("wall", (tuple((x + 500.0, y + 500.0) for x, y in _rect(300.0, 20.0)),), 250.0)
    weighted = compute_weighted_shadows([pergola, second, wall], 35.0, 180.0)
    assert weighted is not None
    through = caster_transmittance(pergola, 35.0, 180.0)
    found = sorted(round(region.transmittance, 4) for region in weighted.weighted_regions)
    assert found[0] == 0.0                                    # the wall's own shadow
    assert round(through * through, 4) in found               # where the two frames overlap
    assert round(through, 4) in found                         # one frame alone


def _exposure(casters, receivers, day: date, cell_cm: float = 50.0, size_cm: float = 1500.0):
    grid = HeatmapGrid.for_rect(0.0, 0.0, size_cm, size_cm, cell_cm)
    result = compute_sun_exposure(casters, receivers, *BERLIN, day, grid, point_rasterizer_reference)
    assert result is not None
    return grid, result


@pytest.mark.parametrize("turn_deg", [0.0, 35.0])
@pytest.mark.parametrize("kind", ["PERGOLA", "TRELLIS"])
def test_the_hours_of_sun_grid_and_a_plant_collect_the_transmittance(kind: str, turn_deg: float) -> None:
    """The map and the estimate, sample by sample: a cell (and a plant) inside the
    frame's prism shadow collects ``step * transmittance`` of each sample it lies in —
    more than behind a solid of that prism, less than in the open."""
    day = date(2026, 3, 20)
    centre = (750.0, 600.0)
    caster = _caster(kind, SIZES[kind][0], turn_deg=turn_deg, offset=centre, item_id="frame")
    solid = IdentifiedCaster("frame", caster.footprints, caster.height_cm)
    # a plant 60 cm north of the frame's middle: in its shadow around noon
    spot = (centre[0] + 25.0, centre[1] + 75.0)
    plant = SunReceiver("plant", *spot)
    grid, open_run = _exposure([caster], [plant], day)
    _grid, solid_run = _exposure([solid], [plant], day)
    row, col = grid.cell_at(*spot)
    samples = daylight_samples(*BERLIN, day)
    daylight = SAMPLE_STEP_MINUTES * len(samples)

    expected = 0.0
    for sample in samples:
        elevation = max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG)
        shadow = compute_weighted_shadows([caster], elevation, sample.azimuth_deg)
        assert shadow is not None
        mask = point_rasterizer_reference(shadow.union_polygons, grid) if shadow.union_polygons else None
        shaded = bool(mask[row, col]) if mask is not None else False
        factor = caster_transmittance(caster, elevation, sample.azimuth_deg) if shaded else 1.0
        expected += SAMPLE_STEP_MINUTES * factor

    got, behind_solid = float(open_run.minutes[row, col]), float(solid_run.minutes[row, col])
    assert got == pytest.approx(expected, abs=0.05)
    assert behind_solid + 30.0 < got < daylight - 15.0      # lighter than a solid, darker than open
    assert dict(open_run.receiver_minutes)["plant"] == pytest.approx(got, abs=0.05)
    assert dict(solid_run.receiver_minutes)["plant"] == pytest.approx(behind_solid, abs=0.05)
    # nowhere darker than the solid, nowhere brighter than the open ground
    assert np.all(open_run.minutes >= solid_run.minutes - 1e-3)
    assert np.all(open_run.minutes <= daylight + 1e-3)
    assert float((open_run.minutes - solid_run.minutes).max()) > 60.0


def test_a_plant_on_raised_soil_is_shaded_by_the_frame_s_slice_above_it() -> None:
    """A receiver at 100 cm sees the pergola's upper 150 cm: the posts shortened, the
    roof whole — weighed against the SLICED prism. One above the roof sees none."""
    day = date(2026, 3, 20)
    caster = _caster("PERGOLA", (300.0, 300.0), offset=(750.0, 600.0), item_id="pergola")
    spot = (775.0, 625.0)  # under the roof
    low, raised, above = (SunReceiver(name, *spot, elevation_cm=elevation)
                          for name, elevation in (("low", 0.0), ("raised", 100.0), ("above", 260.0)))
    _grid, run = _exposure([caster], [low, raised, above], day)
    minutes = dict(run.receiver_minutes)
    daylight = SAMPLE_STEP_MINUTES * len(daylight_samples(*BERLIN, day))
    assert minutes["above"] == pytest.approx(daylight)
    # under the roof both lie in the prism's shadow all day; the slice above the raised
    # plant is the dense roof on shorter posts, so its shade is the deeper one
    assert 0.4 * daylight < minutes["raised"] < minutes["low"] < 0.85 * daylight
    _grid, solid = _exposure([IdentifiedCaster("pergola", caster.footprints, caster.height_cm)],
                             [low], day)
    assert dict(solid.receiver_minutes)["low"] == 0.0


def test_the_slice_of_a_frame_above_a_raised_receiver() -> None:
    frame = _frame("PERGOLA", (300.0, 300.0), 25.0)
    assert _slice_frame_for_elevation(None, 0.0, 100.0) is None      # no open frame
    assert _slice_frame_for_elevation(frame, 0.0, 0.0) is frame
    assert _slice_frame_for_elevation(frame, 120.0, 100.0) is frame  # stands above the plane
    cut = _slice_frame_for_elevation(frame, 0.0, 100.0)
    assert cut is not None and cut != frame
    assert cut.footprint == frame.footprint and cut.rotation_deg == 25.0
    zs = [z for triangle in cut.triangles for _x, _y, z in triangle]
    assert min(zs) == pytest.approx(0.0) and max(zs) == pytest.approx(150.0)   # from the plane up
    above = _slice_frame_for_elevation(frame, 0.0, 250.0)
    assert above is not None and above.triangles == ()               # nothing above the top
    # the weighing of the slice: the prism shortened to what stands above the plane
    whole = open_frame_transmittance(frame, 250.0, 35.0, 180.0)
    upper = open_frame_transmittance(cut, 150.0, 35.0, 180.0)
    assert 0.0 < upper < whole < 1.0   # the roof is the dense part: the upper slice is darker


# ── many of them ─────────────────────────────────────────────────────────────


def _lights(count: int, spacing_cm: float = 150.0) -> list[IdentifiedCaster]:
    """``count`` identical garden lights in a grid — ONE frame object for all of them,
    as the caster walk hands it out."""
    frame = _frame("GARDEN_LIGHT", 20.0)
    ring = frame.footprint
    columns = math.ceil(math.sqrt(count))
    return [
        IdentifiedCaster(
            f"light-{index}",
            (tuple((x + 200.0 + spacing_cm * (index % columns),
                    y + 200.0 + spacing_cm * (index // columns)) for x, y in ring),),
            110.0, frame=frame)
        for index in range(count)
    ]


def test_fifty_lights_are_one_frame_weighed_once_and_painted_as_one_region() -> None:
    """A row of garden lights is the case that decides whether open frames are
    affordable: each light's own weighing cost 0.5 ms, and fifty shades that were a
    hair apart in their last digit were fifty regions to paint and rasterise."""
    lights = _lights(50, spacing_cm=300.0)
    _open_frame_transmittance.cache_clear()
    weighted = compute_weighted_shadows(lights, 35.0, 200.0)
    assert weighted is not None
    assert _open_frame_transmittance.cache_info().misses == 1          # one weighing …
    assert _open_frame_transmittance.cache_info().hits == 49
    (region,) = weighted.weighted_regions                              # … one region
    assert region.transmittance == pytest.approx(caster_transmittance(lights[0], 35.0, 200.0), abs=1e-6)
    assert len(region.polygons) == 50                                  # of fifty separate shades
    # at a grazing sun the long shades run into one another: where two overlap the
    # transmittances multiply, and the regions are still few
    low = compute_weighted_shadows(lights, 4.0, 200.0)
    assert low is not None
    through = caster_transmittance(lights[0], 4.0, 200.0)
    found = sorted({round(region.transmittance, 4) for region in low.weighted_regions})
    assert found[-1] == pytest.approx(through, abs=1e-4)
    assert any(value == pytest.approx(through * through, abs=1e-4) for value in found)


def test_the_weighted_sweep_holds_every_owner_s_shadow_as_the_grouped_sweep_makes_it() -> None:
    """A day's aggregation sweeps a plan with a weighted shade ONCE: the weighted result's
    per-owner shadows stand in for the grouped sweep's — for the plants' estimates. They
    are the same polygons: a solid, a solid on a base, an owner of two footprints, a
    pitched roof's triangles, a frame; an owner that lets everything through has none."""
    from open_garden_planner.core.shadow_geometry import compute_grouped_shadows

    ring = _rect(200.0, 120.0)
    roof = (((0.0, 0.0, 200.0), (300.0, 0.0, 200.0), (150.0, 100.0, 320.0)),
            ((0.0, 0.0, 0.0), (300.0, 0.0, 0.0), (300.0, 0.0, 200.0)))
    casters = [
        GroupedCaster((ring,), 180.0),
        GroupedCaster((tuple((x + 600.0, y) for x, y in ring),), 90.0, 38.0),
        GroupedCaster((ring, tuple((x + 150.0, y + 60.0) for x, y in ring)), 150.0),
        GroupedCaster((tuple((x, y + 700.0) for x, y in ring),), 320.0,
                      roof_triangles=tuple(tuple((x, y + 700.0, z) for x, y, z in tri) for tri in roof)),
        GroupedCaster((tuple((x - 500.0, y) for x, y in ring),), 250.0, transmittance=0.4),
        GroupedCaster((tuple((x - 500.0, y + 400.0) for x, y in _rect(300.0, 300.0)),), 250.0,
                      frame=_frame("PERGOLA", (300.0, 300.0), 0.0)),
    ]
    clear = GroupedCaster((tuple((x + 900.0, y + 900.0) for x, y in ring),), 100.0, transmittance=1.0)
    for elevation, azimuth in ((50.0, 180.0), (12.0, 95.0), (0.5, 260.0)):
        grouped = compute_grouped_shadows(casters, elevation, azimuth)
        weighted = compute_weighted_shadows([*casters, clear], elevation, azimuth)
        assert grouped is not None and weighted is not None
        union, owned = grouped
        assert [polygons for polygons, _through in weighted.owned_shadows[:-1]] == owned
        assert weighted.owned_shadows[-1] == ([], 1.0)
        assert weighted.union_polygons == union


def test_which_boxes_meet_another() -> None:
    # the first overlaps the second; the third only TOUCHES the first and overlaps the
    # second; the fourth is far off; the fifth is no box at all
    boxes = [(0, 0, 10, 10), (5, 5, 15, 15), (10, 0, 20, 8), (100, 100, 110, 110), None]
    assert _boxes_meeting_another(boxes) == [True, True, True, False, False]
    assert _boxes_meeting_another([]) == [] and _boxes_meeting_another([(0, 0, 1, 1)]) == [False]
    assert _boxes_meeting_another([(0, 0, 10, 10), (10, 0, 20, 10)]) == [False, False]  # only touch


def _pairwise_partition(casters, elevation: float, azimuth: float) -> dict[float, float]:
    """#440's partition of the weighted shades as it was before #698 pruned it — every
    porous owner clipped against every region made so far — as transmittance -> cm²."""
    owned = compute_weighted_shadows(casters, elevation, azimuth)
    assert owned is not None
    paths = [[_to_int(polygon) for polygon in polygons] for polygons, _t in owned.owned_shadows]
    through = [t for _polygons, t in owned.owned_shadows]
    opaque = _union_int([path for owner, t in zip(paths, through, strict=True) if t <= 0.0 for path in owner])
    regions: list[tuple[list, float]] = []
    for owner, t in zip(paths, through, strict=True):
        if not (0.0 < t < 1.0 and owner):
            continue
        rem = _diff_int(owner, opaque) if opaque else owner
        following: list[tuple[list, float]] = []
        for r_paths, r_t in regions:
            overlap = _intersect_int(r_paths, rem) if rem else []
            if not overlap:
                following.append((r_paths, r_t))
                continue
            r_only = _diff_int(r_paths, rem)
            if r_only:
                following.append((r_only, r_t))
            following.append((overlap, r_t * t))
            rem = _diff_int(rem, r_paths)
        if rem:
            following.append((rem, t))
        regions = following
    areas: dict[float, float] = {0.0: sum(pyclipper.Area(path) for path in opaque) / CLIPPER_SCALE ** 2}
    for r_paths, r_t in regions:
        key = round(r_t, 6)
        areas[key] = areas.get(key, 0.0) + sum(pyclipper.Area(path) for path in r_paths) / CLIPPER_SCALE ** 2
    return {key: area for key, area in areas.items() if area > 1e-6}


@pytest.mark.parametrize("seed", range(6))
def test_the_pruned_partition_gives_what_the_pairwise_one_gave(seed: int) -> None:
    """Shades that overlap, shades that only touch, shades alone, solids among them, at
    a high and at a grazing sun: region by region the same ground at the same
    transmittance as the partition that clipped every pair."""
    rng = np.random.default_rng(seed)
    casters = []
    for index in range(26):
        x, y = rng.uniform(0.0, 1800.0, size=2)
        w, d = rng.uniform(30.0, 260.0, size=2)
        ring = tuple((px + x, py + y) for px, py in _rect(float(w), float(d)))
        through = None if index % 5 == 0 else float(round(rng.uniform(0.2, 0.9), 2))  # every fifth: a solid
        casters.append(GroupedCaster((ring,), float(rng.uniform(40.0, 260.0)), transmittance=through))
    for elevation, azimuth in ((55.0, 190.0), (20.0, 120.0), (6.0, 250.0)):
        weighted = compute_weighted_shadows(casters, elevation, azimuth)
        assert weighted is not None
        got: dict[float, float] = {}
        for region in weighted.weighted_regions:
            assert isinstance(region, WeightedShadowRegion)
            area = sum(pyclipper.Area(_to_int(polygon)) for polygon in region.polygons) / CLIPPER_SCALE ** 2
            got[round(region.transmittance, 6)] = got.get(round(region.transmittance, 6), 0.0) + area
        want = _pairwise_partition(casters, elevation, azimuth)
        # slivers of the integer grid aside (a thousandth of a cm² where three shades
        # meet in a point: the final union of a region's pieces drops them)
        sliver_cm2 = 0.5
        assert ({key for key, area in got.items() if area > sliver_cm2}
                == {key for key, area in want.items() if area > sliver_cm2}), (seed, elevation)
        for key, area in want.items():
            assert got.get(key, 0.0) == pytest.approx(area, rel=1e-6, abs=sliver_cm2), (seed, elevation, key)
        assert len(want) > 10      # shades that overlap in twos and threes: a real partition
        # and the regions are a partition of the shaded ground: no overlap, nothing lost
        union_area = sum(pyclipper.Area(_to_int(polygon)) for polygon in weighted.union_polygons) / CLIPPER_SCALE ** 2
        assert sum(got.values()) == pytest.approx(union_area, rel=1e-6, abs=0.5)


def test_the_module_keeps_its_names_by_enum_name_and_qt_free() -> None:
    """``core.object_height`` matches kinds by name and imports no Qt (its docstring's
    rule); the lists added for #698 follow it."""
    assert all(isinstance(name, str) for name in OPEN_FRAME_TYPE_NAMES)
    source = Path(object_height.__file__).read_text(encoding="utf-8")
    assert "import PyQt6" not in source and "from PyQt6" not in source
