"""Open frames end to end (#698): a pergola, a trellis, a swing, a hammock and a garden
light placed on a real canvas shade as the frames they are — on the shadow overlay, on
the hours-of-sun map and in a plant's sun estimate — and undo takes it back.

The numbers themselves are held Qt-free in ``tests/unit/test_open_frames.py`` against
an independent measurement. Here it is the WIRING: the one caster walk hands every
consumer the same frame, turned as the item is turned (nothing here is tested at a
rotation of 0 alone: a defect proportional to the turn vanishes there).
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import numpy as np
import pyclipper
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QPolygonF

from open_garden_planner.core.commands import CommandManager, CreateItemCommand
from open_garden_planner.core.object_height import (
    METADATA_KEY,
    OPEN_FRAME_TYPE_NAMES,
    effective_height_cm,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d.builders.open_frames import open_frame_triangles
from open_garden_planner.core.shade_aggregation import SAMPLE_STEP_MINUTES, daylight_samples
from open_garden_planner.core.shadow_geometry import (
    CLIPPER_SCALE,
    _open_frame_transmittance,
    caster_transmittance,
    circle_footprint,
    compute_scene_shadows,
    shadow_direction_scene,
)
from open_garden_planner.core.solar import solar_position
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.services.sun_mismatch_service import classify_mismatch, evaluate_sun
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    _SHADOW_COLOR,
    STATE_ACTIVE,
    SunShadowController,
    collect_identified_casters,
)

BERLIN = {"latitude": 52.52, "longitude": 13.405}
JUNE_NOON_UTC = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)   # 59.3 deg up, bearing 203.7
SEPT_AFTERNOON_UTC = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)  # 29 deg up, bearing 224
SUMMER = date(2026, 6, 21)
CENTRE = (750.0, 520.0)
#: kind -> (width, depth) of a rectangle, or the radius of a circle
SIZES: dict[str, tuple[float, float] | float] = {
    "PERGOLA": (300.0, 300.0), "TRELLIS": (200.0, 20.0), "SWING": (200.0, 150.0),
    "HAMMOCK": (300.0, 120.0), "GARDEN_LIGHT": 20.0,
}
OPEN_KINDS = sorted(OPEN_FRAME_TYPE_NAMES)
TURNS = (0.0, 30.0, 90.0)


@pytest.fixture
def scene(qtbot) -> CanvasScene:
    return CanvasScene(1500.0, 1200.0)


def _make(kind: ObjectType, size: tuple[float, float] | float, turn_deg: float = 0.0,
          centre: tuple[float, float] = CENTRE, height: float | None = None):
    """An item of ``kind`` centred on ``centre``, turned about its own middle."""
    if isinstance(size, float):
        item = CircleItem(centre[0], centre[1], size, object_type=kind)
    else:
        item = RectangleItem(centre[0] - size[0] / 2.0, centre[1] - size[1] / 2.0,
                             size[0], size[1], object_type=kind)
        if turn_deg:
            item.setTransformOriginPoint(item.rect().center())
            item.setRotation(turn_deg)
    if height is not None:
        item.metadata[METADATA_KEY] = height
    return item


def _open(kind: str, turn_deg: float = 0.0, centre: tuple[float, float] = CENTRE):
    return _make(ObjectType[kind], SIZES[kind], turn_deg, centre)


def _solid_twin(kind: str, turn_deg: float = 0.0, centre: tuple[float, float] = CENTRE):
    """The same footprint and height as a generic shape: the solid prism the 2D model
    cast for an open frame before #698."""
    size = SIZES[kind]
    generic = ObjectType.GENERIC_CIRCLE if isinstance(size, float) else ObjectType.GENERIC_RECTANGLE
    return _make(generic, size, turn_deg, centre, height=effective_height_cm(ObjectType[kind], None))


def _caster_of(scene: CanvasScene, item, at_date: date | None = None):
    (caster,) = [c for c in collect_identified_casters(scene, at_date) if c.item_id == str(item.item_id)]
    return caster


def _by_hand(kind: str, turn_deg: float, elevation: float, azimuth: float) -> float:
    """The transmittance of the item as it stands in the scene, with nothing of the code
    under test: the 3D builder's members turned by hand — counter-clockwise by
    ``turn_deg`` in the scene (+x east, +y north), which is what ``setRotation`` does to
    an item in scene coordinates — every triangle moved along the sun ray and united
    here, over the prism ``compute_scene_shadows`` sweeps from the turned footprint."""
    size = SIZES[kind]
    height = effective_height_cm(ObjectType[kind], None)
    assert height is not None
    if isinstance(size, float):
        ring = tuple(circle_footprint(0.0, 0.0, size))
        local = open_frame_triangles(kind, "circle", ring, height, radius_cm=size)
        turn_deg = 0.0  # a circle's model does not turn with its item (the 3D record's rule)
    else:
        w, d = size[0] / 2.0, size[1] / 2.0
        ring = ((-w, -d), (w, -d), (w, d), (-w, d))
        local = open_frame_triangles(kind, "rectangle", ring, height)
    assert local is not None
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))

    def place(point):
        return (CENTRE[0] + c * point[0] - s * point[1], CENTRE[1] + s * point[0] + c * point[1], *point[2:])

    footprint = [place(point) for point in ring]
    corners = np.asarray([[place(point) for point in triangle] for triangle in local], dtype=np.float64)
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
    prism = compute_scene_shadows([(footprint, height)], elevation, azimuth)
    prism_area = sum(pyclipper.Area([(round(x * CLIPPER_SCALE), round(y * CLIPPER_SCALE))
                                     for x, y in polygon]) for polygon in prism)
    return 1.0 - frame_area / prism_area


def _render(scene: CanvasScene, region: QRectF, px_per_cm: float) -> QImage:
    width, height = round(region.width() * px_per_cm), round(region.height() * px_per_cm)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        render_scene_region(scene, painter, QRectF(0, 0, width, height), region, y_flip=True)
    finally:
        painter.end()
    return image


def _darkening(scene: CanvasScene, controller: SunShadowController, points, px_per_cm: float = 4.0):
    """How much darker each scene point is painted with the overlay on than off (the sum
    of the three channels' loss), through the export pipeline (§8.19: raw scene cm in)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    region = QRectF(min(xs) - 10.0, min(ys) - 10.0, max(xs) - min(xs) + 20.0, max(ys) - min(ys) + 20.0)

    def sample(image: QImage) -> list[int]:
        values = []
        for x, y in points:
            colour = image.pixelColor(round((x - region.x()) * px_per_cm),
                                      round(image.height() - (y - region.y()) * px_per_cm))
            values.append(colour.red() + colour.green() + colour.blue())
        return values

    lit = sample(_render(scene, region, px_per_cm))
    controller.set_enabled(False)
    plain = sample(_render(scene, region, px_per_cm))
    controller.set_enabled(True)
    return [off - on for off, on in zip(plain, lit, strict=True)]


def _region_path(region) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for polygon in region.polygons:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in polygon]))
        path.closeSubpath()
    return path


def _along_the_shadow(caster, region, azimuth: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Two scene points on the line from the caster's middle along its shadow: one well
    INSIDE the shadow region and clear of the item, one 1 cm OUTSIDE its far edge."""
    path = _region_path(region)
    footprint = QPainterPath()
    footprint.addPolygon(QPolygonF([QPointF(x, y) for x, y in caster.footprints[0]]))
    dx, dy = shadow_direction_scene(azimuth)
    xs = [x for x, _y in caster.footprints[0]]
    ys = [y for _x, y in caster.footprints[0]]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    step, distance, last_inside = 0.5, 0.0, None
    while distance < 2000.0:
        distance += step
        point = QPointF(cx + dx * distance, cy + dy * distance)
        if path.contains(point):
            last_inside = distance
        elif last_inside is not None:
            break
    assert last_inside is not None
    inside = last_inside - 8.0
    assert not footprint.contains(QPointF(cx + dx * (inside - 6.0), cy + dy * (inside - 6.0)))
    return ((cx + dx * inside, cy + dy * inside),
            (cx + dx * (last_inside + 1.0), cy + dy * (last_inside + 1.0)))


# ── the one caster walk ──────────────────────────────────────────────────────


@pytest.mark.parametrize("turn_deg", TURNS)
@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_walk_gives_an_open_frame_its_members_turned_as_the_item(qtbot, scene, kind, turn_deg) -> None:
    item = _open(kind, turn_deg)
    scene.addItem(item)
    caster = _caster_of(scene, item)
    frame = caster.frame
    assert frame is not None and frame.triangles, kind
    assert caster.height_cm == effective_height_cm(ObjectType[kind], None)
    # the frame is in the item's OWN coordinates: its footprint, turned by its turn and
    # moved to the item's middle, is the footprint the caster's prism stands on …
    round_item = isinstance(SIZES[kind], float)
    assert frame.rotation_deg == (0.0 if round_item else turn_deg)
    c, s = math.cos(math.radians(frame.rotation_deg)), math.sin(math.radians(frame.rotation_deg))
    posed = [(CENTRE[0] + c * x - s * y, CENTRE[1] + s * x + c * y) for x, y in frame.footprint]
    corners = caster.footprints[0]
    assert len(posed) == len(corners)
    for x, y in posed:
        assert min(math.hypot(x - cx, y - cy) for cx, cy in corners) < 0.01, (kind, turn_deg, x, y)
    # … and every member stands inside it (a few millimetres of post and chamfer aside)
    outline = QPainterPath()
    outline.addPolygon(QPolygonF([QPointF(x, y) for x, y in frame.footprint]))
    for triangle in frame.triangles:
        for x, y, z in triangle:
            assert outline.contains(QPointF(x * 0.97, y * 0.97)), (kind, turn_deg, x, y)
            assert -1e-6 <= z <= caster.height_cm + 1e-6
    # … so what it lets through is what the item TURNED IN THE SCENE lets through
    for elevation, azimuth in ((59.3, 203.7), (29.0, 224.0), (15.0, 120.0)):
        got = caster_transmittance(caster, elevation, azimuth)
        assert 0.4 < got < 0.95, (kind, got)
        assert got == pytest.approx(_by_hand(kind, turn_deg, elevation, azimuth), abs=0.02)


def test_a_frame_turned_the_other_way_would_be_noticed(qtbot, scene) -> None:
    """The control of the test above: for a trellis the direction of the turn matters."""
    item = _open("TRELLIS", 30.0)
    scene.addItem(item)
    caster = _caster_of(scene, item)
    right = _by_hand("TRELLIS", 30.0, 29.0, 224.0)
    wrong = _by_hand("TRELLIS", -30.0, 29.0, 224.0)
    assert caster_transmittance(caster, 29.0, 224.0) == pytest.approx(right, abs=0.02)
    assert abs(right - wrong) > 0.05


@pytest.mark.parametrize(("kind", "size"), [
    (ObjectType.PARASOL, 150.0), (ObjectType.GREENHOUSE, (300.0, 200.0)),
    (ObjectType.TABLE_RECTANGULAR, (160.0, 90.0)), (ObjectType.TOOL_SHED, (200.0, 150.0)),
    (ObjectType.GENERIC_RECTANGLE, (200.0, 150.0)),
])
def test_every_other_kind_stays_the_solid_prism(qtbot, scene, kind, size) -> None:
    """A solid canopy, glass, a table, a shed: recorded decisions, not open frames."""
    item = _make(kind, size, height=180.0 if kind is ObjectType.GENERIC_RECTANGLE else None)
    scene.addItem(item)
    caster = _caster_of(scene, item)
    assert caster.frame is None and caster.transmittance is None
    if kind is not ObjectType.TOOL_SHED:  # (a shed is its pitched roof's triangles, #440)
        assert caster_transmittance(caster, 35.0, 180.0) == 0.0


def test_a_hidden_frame_casts_nothing_and_a_resized_one_is_weighed_anew(qtbot, scene) -> None:
    item = _open("PERGOLA", 30.0)
    scene.addItem(item)
    first = caster_transmittance(_caster_of(scene, item), 35.0, 180.0)
    item.setRect(QRectF(item.rect().x(), item.rect().y(), 600.0, 400.0))
    wider = caster_transmittance(_caster_of(scene, item), 35.0, 180.0)
    assert wider > first + 0.03       # the same nine rafters over twice the ground
    item.metadata[METADATA_KEY] = 500.0
    assert caster_transmittance(_caster_of(scene, item), 35.0, 180.0) > wider + 0.03
    item.setVisible(False)
    assert collect_identified_casters(scene) == []


def test_a_row_of_garden_lights_is_one_frame_one_weighing_and_one_region(qtbot, scene) -> None:
    """Twenty lanterns along a path: the walk hands every one of them the SAME frame
    object, so a sun position weighs it once and the overlay paints one region — not
    twenty weighings and twenty regions a hair apart (#698's cost on a lit garden)."""
    lights = [_make(ObjectType.GARDEN_LIGHT, 20.0, centre=(100.0 + 60.0 * index, 600.0))
              for index in range(20)]
    for light in lights:
        scene.addItem(light)
    casters = collect_identified_casters(scene)
    frames = {id(caster.frame) for caster in casters}
    assert len(casters) == 20 and len(frames) == 1 and None not in {caster.frame for caster in casters}
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(JUNE_NOON_UTC)
    _open_frame_transmittance.cache_clear()
    controller.set_enabled(True)
    assert _open_frame_transmittance.cache_info().misses == 1
    (region,) = controller._alive_overlay().weighted_regions()
    assert 0.0 < region.transmittance < 1.0 and len(region.polygons) == 20
    # a second pergola of the same size and turn shares its frame too; another turn does not
    one, same, turned = _open("PERGOLA", 30.0, (400.0, 300.0)), _open("PERGOLA", 30.0, (900.0, 900.0)), \
        _open("PERGOLA", 60.0, (1200.0, 300.0))
    for item in (one, same, turned):
        scene.addItem(item)
    assert _caster_of(scene, one).frame is _caster_of(scene, same).frame
    assert _caster_of(scene, one).frame != _caster_of(scene, turned).frame


# ── the shadow overlay ───────────────────────────────────────────────────────


@pytest.mark.parametrize("turn_deg", TURNS)
@pytest.mark.parametrize("kind", OPEN_KINDS)
def test_the_overlay_paints_an_open_frame_s_shade_lighter(qtbot, scene, kind, turn_deg) -> None:
    """One region of the prism's outline, its alpha the solid's times the occlusion —
    and that is what a render shows: darker than the lawn, lighter than a solid's."""
    item = _open(kind, turn_deg)
    scene.addItem(item)
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(SEPT_AFTERNOON_UTC)
    controller.set_enabled(True)
    assert controller.state == STATE_ACTIVE
    sun = solar_position(BERLIN["latitude"], BERLIN["longitude"], SEPT_AFTERNOON_UTC)
    caster = _caster_of(scene, item, controller.clock.plan_date)
    through = caster_transmittance(caster, sun.elevation_deg, sun.azimuth_deg)

    overlay = controller._alive_overlay()
    assert overlay is not None
    (region,) = overlay.weighted_regions()
    assert region.transmittance == pytest.approx(through, abs=1e-6)
    assert controller.drape_regions() == (region,)       # the 3D drape lays the same shade
    ((_path, colour),) = overlay._region_paths
    assert colour.alpha() == round(_SHADOW_COLOR.alpha() * (1.0 - through))
    assert 12 <= colour.alpha() < 0.6 * _SHADOW_COLOR.alpha()  # it reads, and it is no slab

    inside, _outside = _along_the_shadow(caster, region, sun.azimuth_deg)
    (shade,) = _darkening(scene, controller, [inside])
    assert shade > 0

    # the same footprint and height as a solid: the slab the frame was before #698
    scene.removeItem(item)
    twin = _solid_twin(kind, turn_deg)
    scene.addItem(twin)
    controller.recompute_now()
    (solid_region,) = controller._alive_overlay().weighted_regions()
    assert solid_region.occlusion == 1.0
    (slab,) = _darkening(scene, controller, [inside])
    assert shade == pytest.approx(slab * (1.0 - through), rel=0.2, abs=6)
    assert shade < 0.6 * slab


@pytest.mark.parametrize("kind", ["PERGOLA", "SWING"])
def test_a_light_shade_has_no_dark_rim_beside_a_solid_s(qtbot, scene, kind) -> None:
    """The overlay's soft edge is as strong as the shade it edges. With a solid
    elsewhere on the plan the edge of EVERY region was stroked at the solid's
    strength: a swing's faint shade wore an outline six times darker than itself."""
    item = _open(kind, 30.0)
    scene.addItem(item)
    scene.addItem(_make(ObjectType.GENERIC_RECTANGLE, (120.0, 120.0), centre=(200.0, 200.0), height=200.0))
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(SEPT_AFTERNOON_UTC)
    controller.set_enabled(True)
    sun = solar_position(BERLIN["latitude"], BERLIN["longitude"], SEPT_AFTERNOON_UTC)
    caster = _caster_of(scene, item, controller.clock.plan_date)
    regions = controller._alive_overlay().weighted_regions()
    assert sorted(region.occlusion for region in regions)[-1] == 1.0   # the solid is there
    (light,) = [region for region in regions if region.occlusion < 1.0]
    inside, rim = _along_the_shadow(caster, light, sun.azimuth_deg)
    shade, edge = _darkening(scene, controller, [inside, rim])
    assert shade > 0 and edge > 0            # the soft edge is still painted …
    assert edge <= 1.5 * shade + 6           # … at this shade's own strength


# ── the hours-of-sun map and a plant's estimate ──────────────────────────────


def _tomato(x: float, y: float) -> CircleItem:
    species = {"common_name": "Tomato", "scientific_name": "Solanum lycopersicum",
               "max_spread_cm": 40, "max_height_cm": 40, "sun_requirement": "full_sun"}
    return CircleItem(x, y, 20.0, ObjectType.PERENNIAL, name="Tomato",
                      metadata={"plant_species": species, METADATA_KEY: 40.0})


def _map(qtbot, scene: CanvasScene, day: date = SUMMER):
    controller = SunHeatmapController(scene, lambda: BERLIN)
    try:
        with qtbot.waitSignal(controller.finished, timeout=60000) as blocker:
            assert controller.run_for_day(day)
        assert blocker.args == [True]
        result = controller.result()
        assert result is not None
        return result, dict(controller.receiver_minutes)
    finally:
        controller.shutdown()


@pytest.mark.parametrize("turn_deg", [0.0, 30.0])
@pytest.mark.parametrize("kind", ["PERGOLA", "TRELLIS", "HAMMOCK"])
def test_the_map_and_a_plant_under_a_frame_collect_part_of_the_sun(qtbot, scene, kind, turn_deg) -> None:
    """The heatmap worker on a real scene: a cell and a plant just north of the frame's
    middle get more sun than behind a solid of that footprint, and less than in the open."""
    daylight = float(SAMPLE_STEP_MINUTES * len(daylight_samples(*BERLIN.values(), SUMMER)))
    spot = (CENTRE[0] + 5.0, CENTRE[1] + (35.0 if kind == "TRELLIS" else 5.0))
    plant = _tomato(*spot)
    scene.addItem(plant)
    frame = _open(kind, turn_deg)
    scene.addItem(frame)
    opened, open_plants = _map(qtbot, scene)
    scene.removeItem(frame)
    scene.addItem(_solid_twin(kind, turn_deg))
    slab, slab_plants = _map(qtbot, scene)

    # a cell beside the plant (the plant's own solid darkens the map's cell under it,
    # and is left out of its own estimate)
    beside = (spot[0] - 60.0, spot[1])
    cell, behind_solid = opened.minutes_at(*beside), slab.minutes_at(*beside)
    assert cell is not None and behind_solid is not None
    assert behind_solid + 45.0 < cell < daylight - 20.0
    identity = str(plant.item_id)
    assert slab_plants[identity] + 45.0 < open_plants[identity] < daylight - 20.0
    assert opened.minutes_at(*spot) == slab.minutes_at(*spot) == 0.0   # under the plant itself
    assert float((opened.minutes - slab.minutes).min()) >= -1e-3     # nowhere darker than the solid
    assert float(opened.minutes.max()) == pytest.approx(daylight)


def test_placing_a_pergola_shades_the_plant_under_it_and_undo_takes_it_back(qtbot, scene) -> None:
    """The whole way: a full-sun plant in the open; a pergola is placed over it through
    the command stack; the overlay shows its lighter shade, the map and the plant's
    estimate drop to part of the day — and the plant still has its full sun, where the
    solid prism of before #698 gave it none and a "too little sun" warning. Undo
    restores overlay, map and estimate; redo brings the shade back."""
    daylight = float(SAMPLE_STEP_MINUTES * len(daylight_samples(*BERLIN.values(), SUMMER)))
    plant = _tomato(CENTRE[0] + 5.0, CENTRE[1] + 5.0)
    scene.addItem(plant)
    identity = str(plant.item_id)
    commands = CommandManager()
    shadows = SunShadowController(scene, lambda: BERLIN)
    commands.stack_changed.connect(shadows.schedule_recompute)   # application.py's own wiring
    shadows.set_sim_datetime(JUNE_NOON_UTC)
    shadows.set_enabled(True)

    def frame_regions():
        shadows.recompute_now()
        overlay = shadows._alive_overlay()
        return [region for region in (overlay.weighted_regions() if overlay else ())
                if 0.0 < region.transmittance < 1.0]

    def warning(minutes: float):
        return classify_mismatch(evaluate_sun(identity, "full_sun", minutes, SUMMER))

    assert frame_regions() == []
    _map_before, plants_before = _map(qtbot, scene)
    assert plants_before[identity] == pytest.approx(daylight)
    assert warning(plants_before[identity]) is None

    pergola = _open("PERGOLA", 30.0)
    commands.execute(CreateItemCommand(scene, pergola, "pergola"))
    (region,) = frame_regions()
    sun = solar_position(BERLIN["latitude"], BERLIN["longitude"], JUNE_NOON_UTC)
    assert region.transmittance == pytest.approx(
        caster_transmittance(_caster_of(scene, pergola, shadows.clock.plan_date),
                             sun.elevation_deg, sun.azimuth_deg), abs=1e-6)
    shaded_map, plants_shaded = _map(qtbot, scene)
    under = plants_shaded[identity]
    assert 0.45 * daylight < under < 0.85 * daylight
    # the map under the roof, a metre from the plant (its own cell lies under its own
    # solid, and its morning shadow reaches a little way west): part of the day too
    beside = shaded_map.minutes_at(CENTRE[0] - 100.0, CENTRE[1] + 5.0)
    assert beside is not None and 0.45 * daylight < beside <= under + 1e-3
    assert warning(under) is None                  # ten hours: still a full-sun place
    # what the 2D model said before #698 for the very same pergola: no sun at all
    pergola.setVisible(False)
    twin = _solid_twin("PERGOLA", 30.0)
    scene.addItem(twin)
    _slab_map, plants_slab = _map(qtbot, scene)
    assert plants_slab[identity] == 0.0
    assert warning(plants_slab[identity]).direction == "too_little"
    scene.removeItem(twin)
    pergola.setVisible(True)

    commands.undo()
    assert pergola.scene() is None
    assert frame_regions() == []
    _map_undone, plants_undone = _map(qtbot, scene)
    assert plants_undone[identity] == pytest.approx(plants_before[identity])

    commands.redo()
    assert len(frame_regions()) == 1
    _map_redone, plants_redone = _map(qtbot, scene)
    assert plants_redone[identity] == pytest.approx(under, abs=1e-3)
