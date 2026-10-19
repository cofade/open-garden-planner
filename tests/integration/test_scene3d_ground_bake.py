"""The ground bake against the 2D canvas (Phase 17 L1.5, #385) — gates G1, G2, G3,
G4, G5 and G8 of the story, the pins of its addendum and the §8.10 integration
test: a real scene, a real plan, an edit session through the app's own commands,
and a recording sink that receives the tiles.

Every parity number in here is the bake against the canvas's OWN render of the
same items (``ground_bake_support.canvas_render``, pattern: docs §8.10.28). The
render tier's twin is ``test_scene3d_ground_render.py``.
"""

from __future__ import annotations

import ast
import json
import math
import statistics
from collections.abc import Collection
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QCoreApplication, QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QSignalSpy

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import DeleteItemsCommand, MoveItemsCommand
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle, StrokeStyle
from open_garden_planner.core.scene3d import (
    MEADOW_RGB,
    BuilderRegistry,
    GroundSpec,
    MeshPart,
    Record,
    SceneDiff,
    changed_tiles,
    prism_mesh,
)
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.arrange import build_arrange_command
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.view3d.ground_bake import GroundBaker
from open_garden_planner.ui.view3d.snapshot import SkipReason
from tests.integration.ground_bake_support import (
    Bake,
    TimedBaker,
    canvas_render,
    canvas_rgb,
    difference,
    ncc,
)
from tests.integration.ground_bake_support import rgba as ground_rgba
from tests.integration.test_scene3d_snapshot import (
    work_done,  # noqa: F401 - the contract story's counters of what an idle tick must not do
)

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "tests" / "fixtures" / "plans"
#: The gate's bound: mean absolute difference per channel, 0..255.
PARITY = 6.0

# A plan of 1100 x 700 cm: 3 x 2 tiles at 1 px/cm, with borders at east 512 and 1024
# and at north 512. The two positions put an item of 300 x 200 across the first
# border, and across the corner where four tiles meet.
PLAN_W, PLAN_D = 1100.0, 700.0
ACROSS_A_BORDER = (380.0, 150.0)
ACROSS_A_CORNER = (400.0, 420.0)
POSITIONS = {"border": ACROSS_A_BORDER, "corner": ACROSS_A_CORNER}
TINT = QColor(200, 40, 60, 200)  # a custom colour, and translucent


def new_scene() -> CanvasScene:
    return CanvasScene(width_cm=PLAN_W, height_cm=PLAN_D)


def on_layer(scene: CanvasScene, *items: Any) -> None:
    """Add items the way a drawing tool does: on the scene's active layer."""
    for item in items:
        item.layer_id = scene.active_layer.id
        scene.addItem(item)


def style(item: Any, pattern: FillPattern, color: QColor | None) -> None:
    """Give an item a fill the way the properties panel does: the stored pattern
    and colour, and the brush made from both."""
    if color is None:
        color = QColor(item.fill_color)  # the object type's own colour: "untinted"
    item.fill_pattern = pattern
    item.fill_color = color
    item.setBrush(create_pattern_brush(pattern, color))


def compare(scene: CanvasScene, registry: BuilderRegistry | None = None, *,
            tile_px: int = 512) -> tuple[float, int, Bake]:
    """Bake ``scene`` through the pipeline and hold it against the canvas's render:
    ``(mean, max)`` difference, and the bake. ``tile_px=2048`` makes the plan ONE
    tile — the bake without a tile border in it."""
    bake = Bake(scene, registry=registry,
                baker=GroundBaker(bare_rgb=canvas_rgb(), tile_px=tile_px, budget_s=None))
    bake.step()
    assert bake.skipped == [] and bake.baker.failures == {}
    mean, worst = difference(bake.image(), canvas_render(scene, bake.grid))
    return mean, worst, bake


# ── G1: parity with the canvas, per pattern ───────────────────────────────────


class TestParityPerPattern:
    """G1 — the bake against the 2D canvas's full-detail render of the same flat
    item: for each of the 24 fill patterns (and the solid fill), tinted and
    untinted, turned and not, at two positions that straddle tiles."""

    @pytest.mark.parametrize("position", sorted(POSITIONS))
    @pytest.mark.parametrize("angle", [0.0, 33.0])
    @pytest.mark.parametrize("tinted", [False, True], ids=["untinted", "tinted"])
    @pytest.mark.parametrize("pattern", list(FillPattern), ids=lambda p: p.name)
    def test_a_rectangle_is_painted_as_the_canvas_paints_it(
            self, qtbot: Any, pattern: FillPattern, tinted: bool, angle: float,
            position: str) -> None:
        scene = new_scene()
        x, y = POSITIONS[position]
        item = RectangleItem(x, y, 300.0, 200.0, object_type=ObjectType.GENERIC_RECTANGLE)
        style(item, pattern, TINT if tinted else None)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        mean, worst, bake = compare(scene)
        assert len({tile.key for tile in changed_tiles((), bake.tiles)[0]}) == 6
        assert len(bake.baker.painted_ids()) == 1
        assert mean <= PARITY, (pattern.name, mean, worst)
        # measured (docs §8.32.5): not turned, the two renders are the same picture;
        # turned, single values differ by one step of 255 (largest mean seen: 0.0002)
        assert mean <= (0.002 if angle else 0.0), (pattern.name, mean, worst)
        assert worst <= (2 if angle else 0), (pattern.name, mean, worst)

    def test_all_24_textures_and_the_solid_fill_are_covered(self) -> None:
        assert len(FillPattern) == 25 and FillPattern.SOLID in FillPattern


# ── G1, continued: every shape, every path style, sprites, pens ───────────────


def _rectangle(position: str = "border", kind: ObjectType = ObjectType.GENERIC_RECTANGLE) -> Any:
    x, y = POSITIONS[position]
    return RectangleItem(x, y, 300.0, 200.0, object_type=kind)


def _polygon(position: str = "border") -> Any:
    x, y = POSITIONS[position]
    corners = [(0, 0), (300, 0), (300, 80), (120, 80), (120, 200), (0, 200)]  # a concave L
    return PolygonItem([QPointF(x + dx, y + dy) for dx, dy in corners],
                       object_type=ObjectType.TERRACE_PATIO)


def _ellipse(position: str = "border") -> Any:
    x, y = POSITIONS[position]
    return EllipseItem(x, y, 300.0, 180.0, object_type=ObjectType.GENERIC_ELLIPSE)


def _circle(position: str = "border") -> Any:
    x, y = POSITIONS[position]
    return CircleItem(x + 140.0, y + 100.0, 110.0, object_type=ObjectType.POND_POOL)


def _star(position: str = "border") -> Any:
    """A pentagram: its outline crosses itself, and the canvas leaves its centre
    open (the odd-even rule) where the solid path's resolved regions fill it."""
    x, y = POSITIONS[position]
    cx, cy = x + 140.0, y + 100.0
    points = [QPointF(cx + 130.0 * math.cos(math.radians(90.0 + 144.0 * k)),
                      cy + 130.0 * math.sin(math.radians(90.0 + 144.0 * k))) for k in range(5)]
    return PolygonItem(points, object_type=ObjectType.LAWN)


def _path(style: PathFenceStyle, position: str = "border", width: float | None = None) -> Any:
    x, y = POSITIONS[position]
    points = [QPointF(x - 60.5, y + 10.25), QPointF(x + 150.0, y + 60.0),
              QPointF(x + 170.3, y + 190.7), QPointF(x + 330.0, y + 150.0)]
    item = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=style)
    if width is not None:
        pen = item.pen()
        pen.setWidthF(width)
        adopt_pen(item, pen)
    return item


SHAPES_UNDER_TEST = {"rectangle": _rectangle, "polygon": _polygon, "ellipse": _ellipse,
                     "circle": _circle, "star": _star}


def _only(scene: CanvasScene, *keep: Any) -> CanvasScene:
    """``scene`` with every other item hidden — the 2D reference of "what is on the
    ground" when a test's scene also holds items that stand (a scene the TEST owns)."""
    for item in scene.items():
        if hasattr(item, "item_id") and item not in keep:
            item.setVisible(False)
    return scene


class TestParityPerShape:
    @pytest.mark.parametrize("position", sorted(POSITIONS))
    @pytest.mark.parametrize("angle", [0.0, 33.0, 215.0])
    @pytest.mark.parametrize("shape", ["rectangle", "polygon", "ellipse", "star"])
    def test_every_filled_shape_with_a_texture(self, qtbot: Any, shape: str, angle: float,
                                               position: str) -> None:
        scene = new_scene()
        item = SHAPES_UNDER_TEST[shape](position)
        style(item, FillPattern.BRICK, TINT)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        mean, worst, _bake = compare(scene)
        assert mean <= (0.002 if angle else 0.0) and worst <= (2 if angle else 0), (mean, worst)

    @pytest.mark.parametrize("position", sorted(POSITIONS))
    def test_a_circle_with_a_texture(self, qtbot: Any, position: str) -> None:
        scene = new_scene()
        item = _circle(position)  # a pond: the WATER texture, the type's own colour
        scene.addItem(item)
        mean, worst, bake = compare(scene)
        assert (mean, worst) == (0.0, 0)
        assert bake.records[str(item.item_id)].material.pattern == "WATER"

    @pytest.mark.parametrize("position", sorted(POSITIONS))
    @pytest.mark.parametrize("angle", [33.0, 215.0])
    @pytest.mark.parametrize("pattern", [FillPattern.SOLID, FillPattern.BRICK, FillPattern.WOOD],
                             ids=lambda p: p.name)
    def test_what_is_painted_in_a_turned_circle_turns_with_it(
            self, qtbot: Any, pattern: FillPattern, angle: float, position: str) -> None:
        """A circle's record does not turn (scene contract: its footprint and its
        solid are the same whatever its rotation) — what the canvas paints in its
        coordinates does. The turn travels in the PAINT (``Paint.rotation_deg``)
        and the bake poses its painter with it: a turned circle is painted like
        every other turned shape. (Before: its texture, its dash phase and its
        sprite stayed unturned — all 31 turned circles of a fuzz of 300 items
        differed from the canvas, by up to 48,822 px.)"""
        scene = new_scene()
        item = _circle(position)
        style(item, pattern, TINT)
        scene.addItem(item)
        item._apply_rotation(angle)
        mean, worst, bake = compare(scene)
        record = bake.records[str(item.item_id)]
        assert record.transform.rotation_deg == 0.0  # the contract: the circle does not turn
        assert record.material.paint is not None and record.material.paint.rotation_deg == angle
        assert mean <= 0.002 and worst <= 2, (mean, worst)

    @pytest.mark.parametrize("stroke", [StrokeStyle.DASHED, StrokeStyle.DASH_DOT], ids=lambda s: s.name)
    def test_the_dashes_of_a_turned_circle_start_where_the_canvas_starts_them(
            self, qtbot: Any, stroke: StrokeStyle) -> None:
        scene = new_scene()
        item = _circle("corner")
        style(item, FillPattern.SOLID, QColor(250, 240, 180))
        pen = item.pen()
        pen.setColor(QColor(20, 60, 160))
        pen.setWidthF(7.5)
        pen.setStyle(stroke.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)
        item._apply_rotation(33.0)
        # in ONE tile the bake is the canvas's own call: the same dashes, bit for bit
        assert compare(scene, tile_px=2048)[:2] == (0.0, 0)
        # across four tiles the outline is cut along chords, turned or not: the dashes
        # of a round outline then lie up to a pixel from Qt's (§8.32.5; measured for
        # this circle, unturned and turned alike: mean 0.018, about 980 px by more
        # than 8)
        mean, _worst, _bake = compare(scene)
        assert mean <= 0.03, mean

    def test_turning_a_circle_is_a_change_of_its_paint_and_of_nothing_else(self, qtbot: Any) -> None:
        """The diff matrix: no geometry, no transform — one material change. The
        solid of a round thing is not rebuilt and not posed anew; its ground tiles
        are re-baked when it is on the ground."""
        scene = new_scene()
        pond, barrel = _circle("border"), CircleItem(900.0, 500.0, 40.0, object_type=ObjectType.RAIN_BARREL)
        style(pond, FillPattern.BRICK, None)
        scene.addItem(pond)
        scene.addItem(barrel)
        barrel.metadata["object_height_cm"] = 90.0
        bake = Bake(scene, registry=production_registry(), bare_rgb=canvas_rgb())
        bake.step()
        assert bake.sync.solid_ids == {str(barrel.item_id)}
        builds, before = bake.sync.build_count, dict(bake.records)
        bake.sink.clear_calls()
        pond._apply_rotation(40.0)
        barrel._apply_rotation(40.0)
        result = bake.step()
        assert result == SceneDiff(material=(str(pond.item_id), str(barrel.item_id)))
        assert bake.sync.build_count == builds  # no builder ran
        assert [op for op, _ in bake.sink.ops()] == ["begin", "update_material", "update_material",
                                                    "set_ground", "commit"]
        for item in (pond, barrel):
            now, was = bake.records[str(item.item_id)], before[str(item.item_id)]
            assert now.same_geometry(was) and now.same_transform(was) and not now.same_material(was)
        assert 1 <= len(bake.baker.last_repainted) <= 2  # the pond's tiles; the barrel stands
        assert difference(bake.image(), canvas_render(_only(scene, pond), bake.grid))[0] <= 0.002

    @pytest.mark.parametrize("angle", [0.0, 33.0])
    @pytest.mark.parametrize("stroke", list(StrokeStyle), ids=lambda s: s.name)
    def test_the_outline_pen(self, qtbot: Any, stroke: StrokeStyle, angle: float) -> None:
        scene = new_scene()
        item = _rectangle("corner")
        style(item, FillPattern.SOLID, QColor(250, 240, 180))
        pen = item.pen()
        pen.setColor(QColor(20, 60, 160, 220))
        pen.setWidthF(7.5)
        pen.setStyle(stroke.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        mean, worst, bake = compare(scene)
        record = bake.records[str(item.item_id)]
        assert record.material.stroke_rgba == (20, 60, 160, 220)  # the LIVE pen's colour
        assert record.material.paint.stroke_width_cm == 7.5
        if stroke is StrokeStyle.SOLID:
            assert mean <= (0.002 if angle else 0.0) and worst <= (2 if angle else 0), (mean, worst)
        else:
            # A dashed outline that crosses a tile border is cut to the tile and stroked
            # run by run (TestHostilePlans): the dashes lie where the canvas has them, to
            # one grey level at their edges. The ONE place that is not the canvas's: the
            # corner where the outline's two ends meet — there their caps are two strokes
            # and the pen-width square they share is blended twice.
            assert mean <= 0.002 and worst <= 60, (mean, worst)
            delta = np.abs(bake.image()[..., :3].astype(int)
                           - canvas_render(scene, bake.grid)[..., :3].astype(int)).max(axis=2)
            rows, columns = np.nonzero(delta > 2)
            assert 0 < len(rows) <= 120  # of 770,000 pixels
            # ... one place: the last dash before that corner, and the corner
            assert rows.max() - rows.min() <= 40 and columns.max() - columns.min() <= 40

    def test_a_layer_at_half_opacity(self, qtbot: Any) -> None:
        scene = new_scene()
        under, over = _rectangle("border"), _rectangle("corner")
        style(under, FillPattern.GRAVEL, None)
        style(over, FillPattern.WOOD, TINT)
        scene.addItem(under)
        scene.addItem(over)
        over.setOpacity(0.5)
        mean, worst, bake = compare(scene)
        assert bake.records[str(over.item_id)].material.paint.opacity == 0.5
        assert mean <= 0.002 and worst <= 1, (mean, worst)


class TestParityOfPaths:
    @pytest.mark.parametrize("position", sorted(POSITIONS))
    @pytest.mark.parametrize("angle", [0.0, 33.0])
    @pytest.mark.parametrize("path_style", list(PathFenceStyle), ids=lambda s: s.name)
    def test_every_path_and_fence_style(self, qtbot: Any, path_style: PathFenceStyle,
                                        angle: float, position: str) -> None:
        """One implementation paints a styled path on the canvas and on the ground
        (``path_style_paint``); what could still differ is the frame it is painted
        in — two styles derive a colour from the item's own coordinates."""
        scene = new_scene()
        item = _path(path_style, position, width=30.0)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        # ONE tile: the bake IS the canvas's render, bit for bit, turned or not
        assert compare(scene, tile_px=2048)[:2] == (0.0, 0)
        # six tiles: everything wider than a pixel still is; a HAIRLINE (the 0.5 to 1 cm
        # lines of a border, a bar, a mesh) is clipped at each tile's edge by Qt's line
        # rasteriser, which then steps along it from another start — a shift of less
        # than 1/64 px that shows as single pixels (measured: mean <= 0.016, one pixel
        # up to 142 of 255)
        mean, _worst, bake = compare(scene)
        record = bake.records[str(item.item_id)]
        assert record.height_cm is None and record.material.paint.stroke_width_cm == 0.0
        assert mean <= 0.05, (path_style.name, mean)

    def test_a_moved_path_keeps_its_stones_colours(self, qtbot: Any) -> None:
        """Stepping stones are tinted from their ITEM coordinates: a move must not
        re-colour them, on the canvas or on the ground."""
        scene = new_scene()
        item = _path(PathFenceStyle.STEPPING_STONES, width=40.0)
        scene.addItem(item)
        item.moveBy(63.25, 41.5)
        assert compare(scene, tile_px=2048)[:2] == (0.0, 0)
        mean, worst, _bake = compare(scene)
        assert mean <= 0.001 and worst <= 2


class TestParityOfSprites:
    @pytest.mark.parametrize("angle", [0.0, 33.0])
    @pytest.mark.parametrize("kind", ["FIRE_PIT", "RAIN_BARREL", "PERGOLA"])
    def test_a_furniture_item_without_a_height_is_its_sprite_on_the_ground(
            self, qtbot: Any, kind: str, angle: float) -> None:
        scene = new_scene()
        x, y = ACROSS_A_CORNER
        object_type = ObjectType[kind]
        if kind == "PERGOLA":
            item: Any = RectangleItem(x + 0.4, y + 0.7, 300.0, 200.0, object_type=object_type)
        else:
            item = CircleItem(x + 110.3, y + 90.6, 75.0, object_type=object_type)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        mean, worst, bake = compare(scene, production_registry())
        assert bake.baker.painted_ids() == (str(item.item_id),)
        assert bake.image()[..., :3].std() > 5.0  # a picture, not a flat fill
        # a sprite is a pixmap drawn through a flip: at a tile's edge its smooth
        # scaling rounds a value differently now and then — a circle's sprite turns
        # with its item like a rectangle's (``Paint.rotation_deg``)
        assert mean <= (0.01 if angle else 0.002) and worst <= (16 if angle else 2), (mean, worst)


# ── what is on the ground and what is not ─────────────────────────────────────


class TestWhatIsPainted:
    def test_bare_ground_is_the_one_meadow_albedo(self, qtbot: Any) -> None:
        from open_garden_planner.ui.view3d.quick3d.look import NEUTRAL_DAY

        # the L0 spike's meadow, frozen when L1.10 deleted the spike (§8.10.31)
        spike = json.loads((REPO / "tests" / "data" / "l0_spike_reference.json")
                           .read_text(encoding="utf-8"))

        scene = new_scene()
        bake = Bake(scene)  # the product's default: no colour handed in
        bake.step()
        image = bake.image()
        assert {tuple(int(c) for c in pixel) for pixel in image.reshape(-1, 4)[::997]} == {
            (*MEADOW_RGB, 255)}
        assert GroundBaker().bare_rgb == MEADOW_RGB
        assert "#{:02x}{:02x}{:02x}".format(*MEADOW_RGB) == NEUTRAL_DAY.meadow_albedo \
            == spike["rig"]["meadow_albedo"]
        assert canvas_rgb() != MEADOW_RGB  # never the canvas's beige

    def test_a_solid_is_not_painted_and_the_lawn_runs_on_under_it(self, qtbot: Any) -> None:
        scene = new_scene()
        lawn = RectangleItem(100.0, 100.0, 800.0, 500.0, object_type=ObjectType.LAWN)
        shed = RectangleItem(450.0, 300.0, 200.0, 150.0, object_type=ObjectType.GARAGE_SHED)
        scene.addItem(lawn)
        scene.addItem(shed)
        with_shed = Bake(scene, registry=production_registry())
        with_shed.step()
        assert with_shed.sync.solid_ids == {str(shed.item_id)}
        assert with_shed.baker.painted_ids() == (str(lawn.item_id),)
        scene.removeItem(shed)
        lawn_alone = Bake(scene, registry=production_registry())
        lawn_alone.step()
        assert np.array_equal(with_shed.image(), lawn_alone.image())

    def test_a_plant_is_never_painted(self, qtbot: Any) -> None:
        """Not even one without a height under a registry that builds nothing for
        it: a plant is the plant builder's, never its 2D sprite laid on the lawn."""
        scene = new_scene()
        tree = CircleItem(550.0, 350.0, 120.0, object_type=ObjectType.TREE)
        scene.addItem(tree)
        bake = Bake(scene)  # the default registry: no plant builder
        bake.step()
        record = bake.records[str(tree.item_id)]
        assert record.height_cm is None and record.material.paint is None
        assert "paint_origin" not in record.params
        assert bake.sync.solid_ids == frozenset() and bake.baker.painted_ids() == ()

    def test_an_item_a_builder_makes_a_solid_for_leaves_the_ground(self, qtbot: Any) -> None:
        scene = new_scene()
        lawn = _rectangle("corner", ObjectType.LAWN)
        scene.addItem(lawn)
        registry = BuilderRegistry()
        bake = Bake(scene, registry=registry, bare_rgb=canvas_rgb())
        bake.step()
        assert bake.baker.painted_ids() == (str(lawn.item_id),)

        def slab(record: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(record.footprints, 4.0), "vc"),)

        registry.register("LAWN", slab)
        bake.step()
        assert bake.baker.painted_ids() == () and bake.sync.solid_ids == {str(lawn.item_id)}
        assert bake.sink.state() == bake.sync.expected_state()

    def test_an_item_beside_the_plan_is_not_on_the_ground(self, qtbot: Any) -> None:
        scene = new_scene()
        scene.addItem(RectangleItem(PLAN_W + 300.0, 100.0, 200.0, 100.0,
                                    object_type=ObjectType.LAWN))
        bake = Bake(scene)
        bake.step()
        assert bake.baker.painted_ids() == () and len(bake.tiles) == 6


# ── G8: stacking ──────────────────────────────────────────────────────────────


class TestStacking:
    def test_overlapping_items_paint_in_the_canvas_order_and_follow_an_arrange(
            self, qtbot: Any) -> None:
        """G8. Two overlapping flat items: the later one is on top; "bring to
        front" re-bakes the tiles they share, and the bake matches the canvas
        before and after."""
        from open_garden_planner.core.stacking import ArrangeMode

        scene = new_scene()
        red = RectangleItem(380.0, 150.0, 300.0, 200.0, object_type=ObjectType.GENERIC_RECTANGLE)
        blue = RectangleItem(500.0, 250.0, 300.0, 200.0, object_type=ObjectType.GENERIC_RECTANGLE)
        style(red, FillPattern.SOLID, QColor(220, 30, 30))
        style(blue, FillPattern.SOLID, QColor(30, 30, 220))
        on_layer(scene, red, blue)
        bake = Bake(scene, bare_rgb=canvas_rgb())
        bake.step()
        row, column = int(PLAN_D - 300.0), 600  # east 600, north 300: a point both cover
        assert tuple(bake.image()[row, column, :3]) == (30, 30, 220)  # blue, added last
        assert difference(bake.image(), canvas_render(scene, bake.grid)) == (0.0, 0)
        before = bake.tiles

        command, _outcome = build_arrange_command(scene, [red], ArrangeMode.BRING_TO_FRONT)
        assert command is not None
        command.execute()
        result = bake.step()
        assert result == SceneDiff(reordered=True)  # no record changed: only their order
        assert tuple(bake.image()[row, column, :3]) == (220, 30, 30)
        assert difference(bake.image(), canvas_render(scene, bake.grid)) == (0.0, 0)
        uploaded, dropped = changed_tiles(before, bake.tiles)
        # the two items share tiles (0, 0) and (1, 0), and overlap in both: those two
        # are painted anew and sent, and no other
        assert dropped == () and {tile.key for tile in uploaded} == {(0, 0), (1, 0)}
        assert set(bake.baker.last_repainted) == {(0, 0), (1, 0)}
        command.undo()
        bake.step()
        assert tuple(bake.image()[row, column, :3]) == (30, 30, 220)
        assert bake.sink.state() == bake.sync.expected_state()

    def test_a_reorder_of_items_that_do_not_share_a_tile_repaints_nothing(self, qtbot: Any) -> None:
        from open_garden_planner.core.stacking import ArrangeMode

        scene = new_scene()
        west = RectangleItem(50.0, 50.0, 200.0, 150.0, object_type=ObjectType.LAWN)
        east = RectangleItem(700.0, 50.0, 200.0, 150.0, object_type=ObjectType.LAWN)
        on_layer(scene, west, east)
        bake = Bake(scene)
        bake.step()
        command, _outcome = build_arrange_command(scene, [west], ArrangeMode.BRING_TO_FRONT)
        assert command is not None
        command.execute()
        assert bake.step().reordered
        assert bake.baker.last_repainted == ()


class TestTheOrderOfRegionsDoesNotMatter:
    def test_a_record_of_several_regions_is_one_picture_in_any_order(self, qtbot: Any) -> None:
        """The contract states the order of a record's regions (the scene contract's
        fifth round) and leaves the order of a region's holes open: the ground
        depends on neither. Two outer rings ten centimetres apart under a pen sixteen
        wide, two holes, an island in one of them, fill and pen both translucent —
        painted ring by ring that blends twice where the strokes meet, and in an
        order. It is ONE path in ONE call: one fill, one stroke."""
        from open_garden_planner.core.scene3d import Material, Paint, Params, Transform

        def outer(x0: float, y0: float, x1: float, y1: float) -> tuple[tuple[float, float], ...]:
            return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))  # counter-clockwise

        def hole(x0: float, y0: float, x1: float, y1: float) -> tuple[tuple[float, float], ...]:
            return ((x0, y0), (x0, y1), (x1, y1), (x1, y0))  # clockwise

        big, small = outer(-200.0, -150.0, 60.0, 150.0), outer(70.0, -150.0, 200.0, 150.0)
        hole_a, hole_b = hole(-180.0, -130.0, -100.0, 130.0), hole(-90.0, -130.0, 40.0, 130.0)
        island = outer(-60.0, -100.0, 10.0, 100.0)  # inside hole_b: a region of its own

        def baked(footprints: Any, holes: Any, turn: float = 0.0) -> tuple[tuple[bytes, ...], Any]:
            record = Record(
                item_id="r", kind="TERRACE_PATIO", shape="polygon", footprints=footprints,
                holes=holes, transform=Transform(550.0, 350.0, rotation_deg=turn),
                material=Material("TERRACE_PATIO", fill_rgba=(200, 60, 40, 120),
                                  stroke_rgba=(20, 30, 160, 140), paint=Paint(stroke_width_cm=16.0)),
                params=Params({"seed": "r"}))
            baker = GroundBaker(budget_s=None)
            tiles = baker.bake({"r": record}, None, (), PLAN_W, PLAN_D)
            assert baker.failures == {} and baker.painted_ids() == ("r",)
            return tuple(tile.pixels for tile in tiles), ground_rgba(baker.image())[..., :3]

        for turn in (0.0, 17.0):
            as_stated, _image = baked((big, small, island), ((hole_a, hole_b), (), ()), turn)
            assert baked((island, small, big), ((), (), (hole_b, hole_a)), turn)[0] == as_stated
            assert baked((small, big, island), ((), (hole_b, hole_a), ()), turn)[0] == as_stated
        _pixels, image = baked((big, small, island), ((hole_a, hole_b), (), ()))

        def at(x: float, y: float) -> tuple[int, ...]:
            return tuple(int(v) for v in image[int(PLAN_D - (350.0 + y)), int(550.0 + x)])

        meadow = tuple(MEADOW_RGB)
        assert at(-140.0, 0.0) == meadow and at(-75.0, 0.0) == meadow  # the holes are open
        assert at(-25.0, 0.0) not in (meadow, at(-206.0, 0.0))        # the island is filled
        # where the two outer rings' strokes overlap, the pen is blended ONCE: the
        # colour of one stroke over meadow (taken left of the big ring)
        assert at(65.0, 0.0) == at(-206.0, 0.0) != meadow


# ── G4: the live scene is never touched ───────────────────────────────────────


class TestTheLiveSceneIsLeftAlone:
    def _scene_with_a_selection(self) -> tuple[CanvasScene, list[Any]]:
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / "bench_small.ogp")
        flat = [item for item in scene.items()
                if getattr(getattr(item, "object_type", None), "name", "") in ("LAWN", "POND_POOL")]
        assert len(flat) == 2
        for item in flat:
            item.setSelected(True)
        QCoreApplication.processEvents()  # what loading and selecting queued is delivered
        return scene, flat

    def test_no_selection_change_no_visibility_change_no_changed_signal(self, qtbot: Any) -> None:
        """G4. Full bakes and incremental ones, with a selection active."""
        scene, flat = self._scene_with_a_selection()
        visible = {id(item): item.isVisible() for item in scene.items()}
        selection, changed = QSignalSpy(scene.selectionChanged), QSignalSpy(scene.changed)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert len(bake.baker.last_repainted) == 20 and len(bake.baker.painted_ids()) == 11
        bake.baker.clear()
        bake.step()  # a second full bake
        bake.sync.reset()
        bake.step()  # … and one after a reset
        QCoreApplication.processEvents()
        assert len(selection) == 0 and len(changed) == 0
        assert {id(item): item.isVisible() for item in scene.items()} == visible
        assert scene.selectedItems() and set(scene.selectedItems()) == set(flat)
        assert scene.labels_enabled and scene.shadows_enabled  # what a 2D render switches off

    def test_the_spies_see_what_the_old_way_did(self, qtbot: Any) -> None:
        """Positive control: baking by rendering the live scene — what the L0 spike
        did — clears the selection and makes the scene report a change."""
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QImage, QPainter

        scene, _flat = self._scene_with_a_selection()
        selection = QSignalSpy(scene.selectionChanged)
        image = QImage(240, 160, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        render_scene_region(scene, painter, QRectF(0, 0, 240, 160), QRectF(0, 0, 2400, 1600))
        painter.end()
        QCoreApplication.processEvents()
        assert len(selection) >= 1


# ── G3: one small edit ────────────────────────────────────────────────────────


def _loaded(plan: str) -> CanvasScene:
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    return scene


def _flat_item_up_to_three_metres(scene: CanvasScene, bake: Bake) -> Any:
    """The largest painted item of the plan that is no longer than 3 m."""
    painted = set(bake.baker.painted_ids())
    best: tuple[float, Any] | None = None
    for item in scene.items():
        if str(getattr(item, "item_id", "")) not in painted:
            continue
        rect = item.sceneBoundingRect()
        size = max(rect.width(), rect.height())
        if size <= 300.0 and (best is None or size > best[0]):
            best = (size, item)
    assert best is not None
    return best[1]


class TestOneSmallEdit:
    # A WALL-CLOCK gate (the median of an edit's bake, 10 ms): it runs in the quiet
    # step of ADR-058, never beside the default run's workers — under eight workers
    # it read 11.58 ms. Marked by hand: the stopwatch is an attribute of
    # ``ground_bake_support.TimedBaker``, which ``tests/unit/test_perf_marker_guard.py``
    # does not follow.
    @pytest.mark.perf
    @pytest.mark.parametrize(("plan", "tiles", "painted"), [("bench_small.ogp", 20, 11),
                                                           ("bench_large.ogp", 60, 45)])
    def test_a_move_repaints_at_most_four_tiles_in_ten_milliseconds(
            self, qtbot: Any, plan: str, tiles: int, painted: int) -> None:
        """G3 — with the time budget ON, as in the product. Move one flat item of at
        most 3 m, 31 times: every move re-paints at most four tiles, looks at ONE
        record, and leaves every other tile the very object it was; the bake of
        an edit takes at most 10 ms in the median — and is ONE pass (an edit that
        fits the gate is not spread over frames)."""
        scene = _loaded(plan)
        baker = TimedBaker()
        bake = Bake(scene, registry=production_registry(), baker=baker)
        bake.step()
        open_passes = 1 + bake.finish()  # opening the plan may take several
        assert len(bake.tiles) == tiles and len(baker.painted_ids()) == painted
        item = _flat_item_up_to_three_metres(scene, bake)
        full_ms = sum(baker.milliseconds)
        most_tiles = most_records = 0
        per_edit: list[float] = []
        passes: list[int] = []
        for index in range(31):
            before = {tile.key: tile for tile in bake.tiles}
            painted_before = baker.records_painted
            baker.milliseconds.clear()
            delta = QPointF(37.5, -22.25) if index % 2 == 0 else QPointF(-37.5, 22.25)
            MoveItemsCommand([item], delta).execute()
            result = bake.step()
            assert result == SceneDiff(transform=(str(item.item_id),))
            assert baker.last_examined == 1
            repainted = set(baker.last_repainted)
            while bake.sync.ground_pending:  # a pass the budget cut short (a loaded machine)
                bake.sync.continue_ground()
                assert baker.last_examined == 0
                repainted |= set(baker.last_repainted)
            passes.append(len(baker.milliseconds))
            per_edit.append(sum(baker.milliseconds))
            most_tiles = max(most_tiles, len(repainted))
            most_records = max(most_records, baker.records_painted - painted_before)
            assert 1 <= len(repainted) <= 4
            for tile in bake.tiles:
                if tile.key not in repainted:
                    assert tile is before[tile.key]  # untouched: the same object, the same bits
            uploaded, dropped = changed_tiles(tuple(before.values()), bake.tiles)
            assert dropped == () and {tile.key for tile in uploaded} <= repainted
        median = statistics.median(per_edit)
        print(f"\nG3 {plan}: opened in {open_passes} passes, {full_ms:.1f} ms of bake; per move: "
              f"median {median:.2f} ms, max {max(per_edit):.2f} ms, at most {most_tiles} tiles and "
              f"{most_records} record paints; passes per move: median "
              f"{statistics.median(passes)}, max {max(passes)}")
        assert median <= 10.0 and statistics.median(passes) == 1
        assert bake.sink.state().ground == bake.sync.expected_state().ground


# ── G2: north up, on a real plan ──────────────────────────────────────────────


def _hide_all_but(scene: CanvasScene, keep: Collection[str]) -> None:
    """Leave only the items with these ids visible — in a scene the TEST owns: the
    2D reference of "the flat items of the plan" (what the L0 spike did to the
    live scene, and the bake must never do)."""
    for item in scene.items():
        if getattr(item, "object_type", None) is None or item.parentItem() is not None:
            continue
        item.setVisible(str(getattr(item, "item_id", "")) in keep)


class TestNorthUpOnARealPlan:
    def test_bench_small_bakes_as_its_canvas_render_north_up(self, qtbot: Any) -> None:
        """G2 (default tier). ``bench_small.ogp`` is asymmetric: its ground baked
        through the pipeline, against the canvas's render of its flat items — the
        identity must beat every flip by a wide margin, and be the same picture."""
        scene = _loaded("bench_small.ogp")
        bake = Bake(scene, registry=production_registry(), bare_rgb=canvas_rgb())
        bake.step()
        assert bake.skipped == [] and bake.baker.failures == {}
        kinds = sorted(bake.records[item_id].kind for item_id in bake.baker.painted_ids())
        assert kinds == ["DRIVEWAY", "FIRE_PIT", "GARDEN_BED", "GARDEN_BED", "GARDEN_BED", "LAWN",
                         "PATH", "PATH", "POND_POOL", "RAIN_BARREL", "TERRACE_PATIO"]
        baked = bake.image()
        _hide_all_but(scene, bake.baker.painted_ids())
        reference = canvas_render(scene, bake.grid)
        mean, worst = difference(baked, reference)
        scores = {"identity": ncc(baked, reference), "flip_v": ncc(baked, reference[::-1]),
                  "flip_h": ncc(baked, reference[:, ::-1]),
                  "rot_180": ncc(baked, reference[::-1, ::-1])}
        print(f"\nG2 bench_small: mean {mean:.5f}, max {worst}; NCC {scores}")
        assert mean <= PARITY and mean <= 0.01
        assert scores["identity"] > 0.999
        assert max(scores["flip_v"], scores["flip_h"], scores["rot_180"]) < 0.5
        # north is up: the plan's north edge is the image's first row. The lawn (the
        # plan's largest flat item) lies where the records say it does
        lawn = next(record for record in bake.records.values() if record.kind == "LAWN")
        row = int(bake.grid.height_px - lawn.transform.north_cm)
        column = int(lawn.transform.east_cm)
        assert tuple(baked[row, column, :3]) == tuple(reference[row, column, :3])
        assert tuple(baked[row, column, :3]) != canvas_rgb()

    def test_the_two_bench_plans_and_the_edge_plan_bake_without_a_failure(self, qtbot: Any) -> None:
        for plan, painted in (("bench_small.ogp", 11), ("bench_large.ogp", 45),
                              ("scene3d_edge_cases.ogp", 1)):
            scene = _loaded(plan)
            bake = Bake(scene, registry=production_registry(), bare_rgb=canvas_rgb())
            bake.step()
            assert bake.skipped == [] and bake.baker.failures == {}, plan
            assert len(bake.baker.painted_ids()) == painted, plan
            assert bake.baker.capped_tiles == 0, plan
            baked = bake.image()
            _hide_all_but(scene, bake.baker.painted_ids())
            mean, _worst = difference(baked, canvas_render(scene, bake.grid))
            assert mean <= 0.05, (plan, mean)


# ── G5 and §8.10: an edit session, incremental == full ────────────────────────


def _item_of(scene: CanvasScene, kind: str, index: int = 0) -> Any:
    found = sorted((item for item in scene.items()
                    if getattr(getattr(item, "object_type", None), "name", "") == kind),
                   key=lambda item: str(item.item_id))
    return found[index]


class TestAnEditSession:
    def test_a_scripted_session_ends_on_the_tiles_of_a_from_scratch_bake(self, qtbot: Any) -> None:
        """G5 and the §8.10 integration test: a real plan in a real scene, edited
        through the app's own commands and setters; after EVERY step the recording
        sink holds what one from-scratch apply would give it — tiles included, bit
        for bit — and at the end a fresh baker, handed the records without any
        diff, paints the same bytes."""
        from open_garden_planner.core.stacking import ArrangeMode

        scene = _loaded("bench_small.ogp")
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert len(bake.tiles) == 20 and bake.sink.transactions == 1
        pond, lawn = _item_of(scene, "POND_POOL"), _item_of(scene, "LAWN")
        bed, house = _item_of(scene, "GARDEN_BED"), _item_of(scene, "HOUSE")
        gravel = next(item for item in scene.items()
                      if getattr(item, "path_fence_style", None) is PathFenceStyle.GRAVEL_PATH)
        steps: list[tuple[str, int]] = []

        def tick(name: str, *, ground: bool) -> None:
            before = bake.tiles
            bake.step()
            uploaded, dropped = changed_tiles(before, bake.tiles)
            assert dropped == ()
            assert bool(uploaded) is ground, (name, len(uploaded))
            assert bake.sink.state() == bake.sync.expected_state(), name
            assert bake.baker.failures == {} and bake.sync.ground_failure is None
            steps.append((name, len(uploaded)))

        MoveItemsCommand([pond], QPointF(40.0, -25.0)).execute()
        tick("move a flat item", ground=True)
        style(lawn, FillPattern.WILDFLOWER, QColor(120, 160, 60))
        tick("re-pattern the lawn", ground=True)
        delete = DeleteItemsCommand(scene, [bed])
        delete.execute()
        tick("delete a bed", ground=True)
        delete.undo()
        tick("undo the delete", ground=True)
        MoveItemsCommand([house], QPointF(15.0, 10.0)).execute()
        tick("move a solid", ground=False)  # the ground does not know the house
        # two new items on the active layer (the fixture's own items have none, and
        # an item without a layer cannot be arranged)
        mulch = RectangleItem(1000.0, 380.0, 260.0, 180.0, object_type=ObjectType.GENERIC_RECTANGLE)
        style(mulch, FillPattern.MULCH, None)
        terrace = RectangleItem(900.0, 300.0, 280.0, 190.0, object_type=ObjectType.TERRACE_PATIO)
        on_layer(scene, mulch, terrace)
        tick("draw two overlapping surfaces", ground=True)
        terrace._apply_rotation(27.0)
        tick("turn it", ground=True)
        command, _outcome = build_arrange_command(scene, [terrace], ArrangeMode.SEND_TO_BACK)
        assert command is not None
        command.execute()
        tick("send the terrace under the mulch", ground=True)
        assert bake.last_diff == SceneDiff(reordered=True)  # no record changed: two swapped places
        pen = gravel.pen()
        pen.setWidthF(pen.widthF() * 2.0)
        adopt_pen(gravel, pen)
        tick("widen a path", ground=True)
        pond.metadata["object_height_cm"] = 35.0  # a height: now a solid, no longer ground
        tick("give the pond a height", ground=True)
        assert str(pond.item_id) in bake.sync.solid_ids
        assert str(pond.item_id) not in bake.baker.painted_ids()
        del pond.metadata["object_height_cm"]
        tick("take it away again", ground=True)
        tick("nothing", ground=False)
        assert bake.sink.calls[-1].op == "commit" and bake.last_diff.is_empty

        fresh = GroundBaker(budget_s=None)
        from_scratch = fresh.bake(bake.records, None, bake.sync.solid_ids,
                                  bake.plan.width_cm, bake.plan.depth_cm)
        assert [tile.pixels for tile in from_scratch] == [tile.pixels for tile in bake.tiles]
        assert from_scratch == bake.tiles
        # … and with the diff withheld the incremental baker comes to the same tiles
        assert bake.baker.bake(bake.records, None, bake.sync.solid_ids,
                               bake.plan.width_cm, bake.plan.depth_cm) == bake.tiles
        assert bake.baker.last_repainted == ()
        assert [name for name, _n in steps][:2] == ["move a flat item", "re-pattern the lawn"]
        # a small item moved a little is at most four tiles; the lawn is the plan's
        # largest surface, and re-patterning it sends every tile it lies in
        assert dict(steps)["move a flat item"] <= 4 < dict(steps)["re-pattern the lawn"]

    def test_a_new_plan_rectangle_starts_the_ground_over(self, qtbot: Any) -> None:
        scene = new_scene()
        scene.addItem(_rectangle("border", ObjectType.LAWN))
        bake = Bake(scene)
        bake.step()
        assert len(bake.tiles) == 6
        bake.plan = GroundSpec(2000.0, 1200.0)
        bake.step()
        assert len(bake.tiles) == 12 and bake.grid.width_px == 2000
        assert bake.sink.state() == bake.sync.expected_state()


# ── the addendum: flat items the solid path refuses ───────────────────────────


def _long_path(points: int) -> Any:
    """A path traced with ``points`` points, 100 cm wide: far beyond what the
    stroke's region work may cost."""
    line = [QPointF(60.0 + 2880.0 * k / (points - 1),
                    400.0 + 150.0 * math.sin(k / (points - 1) * 9.0 * math.pi)) for k in range(points)]
    item = PolylineItem(line, object_type=ObjectType.PATH,
                        path_fence_style=PathFenceStyle.PAVED_PATH)
    pen = item.pen()
    pen.setWidthF(100.0)
    adopt_pen(item, pen)
    return item


def _traced_lawn(vertices: int, x: float = 500.0, y: float = 400.0) -> Any:
    ring = [QPointF(x + (300.0 + 40.0 * math.sin(9.0 * a)) * math.cos(a),
                    y + (300.0 + 40.0 * math.sin(9.0 * a)) * math.sin(a))
            for a in (2.0 * math.pi * k / vertices for k in range(vertices))]
    return PolygonItem(ring, object_type=ObjectType.LAWN)


class TestFlatItemsTheSolidPathRefuses:
    def test_a_3000_point_path_is_on_the_ground_as_the_canvas_paints_it(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        from open_garden_planner.ui.view3d import snapshot

        clipper_calls: list[int] = []
        real = snapshot.polyline_footprint
        monkeypatch.setattr(snapshot, "polyline_footprint",
                            lambda *args: clipper_calls.append(1) or real(*args))
        scene = CanvasScene(width_cm=3000.0, height_cm=800.0)
        item = _long_path(3000)
        scene.addItem(item)
        mean, _worst, bake = compare(scene, production_registry())
        record = bake.records[str(item.item_id)]
        # no regions — nothing could be built of it — and everything that was drawn
        assert record.footprints == () and record.regions == () and len(record.path) == 3000
        assert record.path_width_cm == 100.0 and record.height_cm is None
        assert clipper_calls == []  # refused before the clipper was asked
        assert bake.baker.painted_ids() == (str(item.item_id),)
        assert mean <= 0.05, mean
        # as ONE tile: the canvas's picture but for single values one step off — the
        # record's 3,000 points are the item's on a grid of 1e-7 cm, and 2,999 mitred
        # joins of a 100 cm stroke round one of them the other way (measured: 1 value)
        whole_mean, whole_worst, _whole = compare(scene, production_registry(), tile_px=4096)
        assert whole_mean <= 1e-5 and whole_worst <= 1
        # bounded by counts: one record, painted once into each tile it reaches
        assert bake.baker.records_painted == len(bake.baker.last_repainted) == 12
        assert 0 < bake.baker.elements_generated <= 2 * 3000 and bake.baker.capped_tiles == 0
        painted = bake.baker.records_painted
        assert bake.step().is_empty and bake.baker.records_painted == painted  # idle: no work

    def test_a_5000_vertex_lawn_is_on_the_ground_as_the_canvas_paints_it(self, qtbot: Any) -> None:
        scene = CanvasScene(width_cm=1100.0, height_cm=800.0)
        item = _traced_lawn(5000)
        scene.addItem(item)
        mean, worst, bake = compare(scene, production_registry())
        record = bake.records[str(item.item_id)]
        assert record.footprints == () and len(record.outline) == 5000
        assert "outline_resolved" not in record.params
        assert (mean, worst) == (0.0, 0)
        # bounded by counts: all six tiles painted, the lawn into the four it reaches
        assert len(bake.baker.last_repainted) == 6 and bake.baker.records_painted == 4
        MoveItemsCommand([item], QPointF(12.5, -7.0)).execute()
        assert bake.step() == SceneDiff(transform=(str(item.item_id),))  # still a move
        assert bake.baker.last_examined == 1
        assert difference(bake.image(), canvas_render(scene, bake.grid)) == (0.0, 0)

    def test_an_idle_tick_asks_nothing_again_about_a_refused_flat_item(
            self, qtbot: Any, work_done: dict[str, int]) -> None:  # noqa: F811 - the fixture
        """The contract's rule (L1.1, fix round 4), held on the flat path too: a refusal
        is remembered while the item lives. A 3,000-point path and a 5,000-vertex lawn
        — kept for the ground, refused for cutting — cost the FIRST snapshot the
        pricing of their refusal, and an idle tick nothing: no cut, no stroke
        inflated, no outline resolved, and the same records again."""
        from open_garden_planner.ui.view3d import snapshot

        scene = CanvasScene(width_cm=3000.0, height_cm=1100.0)
        path, lawn = _long_path(3000), _traced_lawn(5000)
        scene.addItem(path)
        scene.addItem(lawn)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert bake.skipped == [] and set(bake.records) == {str(path.item_id), str(lawn.item_id)}
        assert all(record.footprints == () for record in bake.records.values())
        first, first_work = dict(bake.records), dict(work_done)
        assert first_work["cuts"] == 0  # nothing was ever cut: there are no regions
        strokes, outlines = (snapshot._polyline_regions.cache_info(),
                             snapshot._polygon_regions.cache_info())
        painted = bake.baker.records_painted
        for _tick in range(3):
            work_done.update(cuts=0, strokes=0, outlines=0)
            assert bake.step().is_empty and bake.records == first
            assert work_done == {"cuts": 0, "strokes": 0, "outlines": 0}
        assert bake.baker.records_painted == painted  # … and the ground paints nothing either
        # the refusals were ASKED for on every tick (they stay live), and answered from memory
        assert snapshot._polyline_regions.cache_info().misses == strokes.misses
        assert snapshot._polygon_regions.cache_info().misses == outlines.misses
        assert snapshot._polyline_regions.cache_info().hits == strokes.hits + 3
        assert snapshot._polygon_regions.cache_info().hits == outlines.hits + 3
        print(f"\nrefused flat items: first snapshot {first_work}, three idle ticks {work_done}")

    def test_with_a_height_such_an_item_is_left_out_and_reported_as_before(self, qtbot: Any) -> None:
        scene = CanvasScene(width_cm=1100.0, height_cm=800.0)
        item = _traced_lawn(5000)
        item.metadata["object_height_cm"] = 30.0
        scene.addItem(item)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert bake.records == {} and [s.reason for s in bake.skipped] == [SkipReason.OUTLINE_TOO_LARGE]

    def test_a_star_keeps_its_open_centre(self, qtbot: Any) -> None:
        """A polygon that crosses itself: the solid path's regions fill its centre
        (the non-zero rule); the canvas leaves it open (odd-even) — and so does the
        ground, from the outline as drawn."""
        scene = new_scene()
        item = _star("corner")
        style(item, FillPattern.SOLID, QColor(30, 140, 60))
        scene.addItem(item)
        mean, worst, bake = compare(scene)
        record = bake.records[str(item.item_id)]
        assert record.params["outline_resolved"] is True and len(record.outline) == 5
        assert (mean, worst) == (0.0, 0)
        centre = record.transform
        row, column = int(PLAN_D - centre.north_cm), int(centre.east_cm)
        assert tuple(bake.image()[row, column, :3]) == canvas_rgb()  # open


# ── the loader and the pen: what the bake found in the 2D app ─────────────────


class TestWhatTheCanvasReallyPaintsWith:
    def test_a_loaded_rectangle_keeps_its_saved_fill_colour(self, qtbot: Any, tmp_path: Path) -> None:
        """The loader set a rectangle's brush and left ``fill_color`` at its type's
        default: the next save lost the colour, and the 3D view tinted and baked
        another colour than the canvas painted."""
        scene = new_scene()
        item = _rectangle("corner")
        style(item, FillPattern.BRICK, QColor(200, 30, 120))
        scene.addItem(item)
        ProjectManager().save(scene, tmp_path / "plan.ogp")
        loaded = CanvasScene()
        ProjectManager().load(loaded, tmp_path / "plan.ogp")
        again = next(i for i in loaded.items() if isinstance(i, RectangleItem))
        assert QColor(again.fill_color).getRgb() == (200, 30, 120, 255)
        mean, worst, bake = compare(loaded)
        assert bake.records[str(again.item_id)].material.fill_rgba == (200, 30, 120, 255)
        assert (mean, worst) == (0.0, 0)
        ProjectManager().save(loaded, tmp_path / "again.ogp")
        assert "#ffc81e78" in (tmp_path / "again.ogp").read_text(encoding="utf-8").lower()

    @pytest.mark.style_gaps_allowed(
        "sets a stroke attribute apart from the pen on purpose: the snapshot paints the pen")
    def test_the_stroke_is_the_live_pens_after_a_load(self, qtbot: Any, tmp_path: Path) -> None:
        """The record — and the ground — follow the PEN, whatever the attribute says.
        (No loader branch set ``stroke_color`` when the bake was built; since its
        review the loader keeps pen and attribute in step — ``core.item_look`` —
        and the snapshot still reads the pen: an attribute set apart is not painted.)"""
        scene = new_scene()
        item = _polygon("border")
        pen = item.pen()
        pen.setColor(QColor(1, 2, 3))
        pen.setWidthF(6.0)
        adopt_pen(item, pen)
        scene.addItem(item)
        ProjectManager().save(scene, tmp_path / "plan.ogp")
        loaded = CanvasScene()
        ProjectManager().load(loaded, tmp_path / "plan.ogp")
        again = next(i for i in loaded.items() if isinstance(i, PolygonItem))
        assert QColor(again.stroke_color).getRgb() == (1, 2, 3, 255)  # in step since the review
        again.stroke_color = QColor(200, 200, 0)  # … and an attribute that parts is not painted
        mean, worst, bake = compare(loaded)
        assert bake.records[str(again.item_id)].material.stroke_rgba == (1, 2, 3, 255)
        assert (mean, worst) == (0.0, 0)

    def test_a_bent_boardwalk_shows_its_planks(self, qtbot: Any) -> None:
        """2D regression: the rails were filled with the last plank's brush, so a
        boardwalk with a bend had a patch over its own planks. Along the first
        leg's centre line the planks alternate again, to its end."""
        scene = new_scene()
        item = _path(PathFenceStyle.WOODEN_BOARDWALK, "border", width=30.0)
        scene.addItem(item)
        bake = Bake(scene, bare_rgb=canvas_rgb())
        bake.step()
        reference = canvas_render(scene, bake.grid)
        first, second = item.points[0], item.points[1]
        length = math.hypot(second.x() - first.x(), second.y() - first.y())
        reds = []
        for k in range(1, 20):  # one sample per plank (spacing 0.35 x 30 cm)
            t = k * 10.5 / length
            east = first.x() + (second.x() - first.x()) * t
            north = first.y() + (second.y() - first.y()) * t
            reds.append(int(reference[int(PLAN_D - north), int(east), 0]))
        assert len(set(reds[:10])) == 2
        assert all(a != b for a, b in zip(reds, reds[1:], strict=False)), reds


# ── an item made from an item (review P1-1) ───────────────────────────────────


def _derived_cases() -> list[tuple[str, str]]:
    """The 2D suite's operations and sources — but for its plain line, which is a
    FENCE: a fence stands in 3D and is not on the ground."""
    from tests.integration.test_item_style_in_step import CASES

    return [(operation, shape) for operation, shape in CASES if shape != "polyline"]


class TestAnItemMadeFromAnItem:
    """The record's fill is read from the item's ATTRIBUTES (a textured brush
    cannot be asked for its pattern or its tint); the canvas paints the live
    BRUSH. An operation that copied the second and not the first parted the two:
    measured before the fix, the offset copy of a blue brick terrace was baked
    as default wood (mean 11.0 of 255 over the plan), the chamfered copy of a red
    lawn as default green (4.09). Every operation of the 2D suite's table
    (``test_item_style_in_step.OPERATIONS``) is held to the canvas here."""

    @pytest.mark.parametrize(("operation", "shape"), _derived_cases(),
                             ids=[f"{o} of a {s}" for o, s in _derived_cases()])
    def test_it_is_baked_as_the_canvas_paints_it(self, qtbot: Any, operation: str, shape: str) -> None:
        from tests.integration.test_item_style_in_step import OPERATIONS, SOURCES

        how, _shapes, is_copy = OPERATIONS[operation]
        original = SOURCES[shape]()
        filled = not isinstance(original, PolylineItem)
        if filled:
            style(original, FillPattern.BRICK, QColor(30, 60, 200))
        pen = original.pen()
        pen.setColor(QColor(200, 30, 30))
        pen.setWidthF(5.0)
        adopt_pen(original, pen)
        derived = how(original)
        scene = new_scene()
        scene.addItem(derived)
        mean, worst, bake = compare(scene)
        record = bake.records[str(derived.item_id)]
        assert bake.baker.painted_ids() == (str(derived.item_id),)
        if isinstance(derived, PolylineItem):
            # a styled line: single pixels of its elements' edges (§8.32.5, limits 2 and 8
            # — a chamfer's new points are not round numbers; measured: mean 0.0003)
            assert mean <= 0.05, (mean, worst)
        else:
            assert (mean, worst) == (0.0, 0)
        if is_copy and filled:
            assert (record.material.fill_rgba, record.material.pattern) == ((30, 60, 200, 255), "BRICK")
        if is_copy:
            assert record.material.stroke_rgba == (200, 30, 30, 255)

    def test_the_two_cases_of_the_review(self, qtbot: Any) -> None:
        """An offset copy of a blue brick terrace polygon, and a chamfered copy of
        a red lawn rectangle — beside their sources, in one plan."""
        from tests.integration.test_item_style_in_step import _corner, _offset

        terrace = PolygonItem([QPointF(60.0, 60.0), QPointF(360.0, 60.0), QPointF(360.0, 260.0),
                               QPointF(60.0, 260.0)], object_type=ObjectType.TERRACE_PATIO)
        style(terrace, FillPattern.BRICK, QColor(30, 60, 200))
        lawn = RectangleItem(600.0, 380.0, 300.0, 200.0, object_type=ObjectType.LAWN)
        style(lawn, lawn.fill_pattern, QColor(200, 30, 30))
        outer, chamfered = _offset(terrace), _corner(lawn)
        outer.moveBy(330.0, 300.0)   # across the corner where four tiles meet
        scene = new_scene()
        for item in (terrace, outer, chamfered):
            scene.addItem(item)
        mean, worst, bake = compare(scene)
        assert (mean, worst) == (0.0, 0)
        materials = {key: bake.records[str(item.item_id)].material
                     for key, item in (("outer", outer), ("chamfered", chamfered))}
        assert (materials["outer"].fill_rgba, materials["outer"].pattern) == ((30, 60, 200, 255), "BRICK")
        assert materials["chamfered"].fill_rgba == (200, 30, 30, 255)
        assert materials["chamfered"].pattern == lawn.fill_pattern.name


# ── the boundary ──────────────────────────────────────────────────────────────


def test_the_baker_imports_no_engine_and_touches_no_scene() -> None:
    """``ground_bake.py`` is QtGui only: no Qt Quick module, nothing of the engine
    package — and no ``QGraphicsScene`` / ``QGraphicsItem`` API: it could not
    touch the live scene if it wanted to."""
    import open_garden_planner.ui.view3d.ground_bake as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not {name for name in imported if "QtQuick" in name or "QtQml" in name}
    assert not {name for name in imported if "quick3d" in name or "spike_q3d" in name}
    assert not {name for name in imported if name.startswith("PyQt6.QtWidgets")}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"QGraphicsScene", "QGraphicsItem", "QGraphicsView", "setVisible",
                        "setSelected", "clearSelection", "selectedItems", "render_scene_region",
                        "sceneTransform", "mapToScene"}


# ── security add-on: a plan file is untrusted input ───────────────────────────


def _hostile_scene() -> CanvasScene:
    return CanvasScene(width_cm=2400.0, height_cm=1600.0)  # 5 x 4 tiles


def _whole_plan_ring(vertices: int) -> list[QPointF]:
    """A ring of ``vertices`` vertices around the whole 24 x 16 m plan."""
    return [QPointF(1200.0 + 3000.0 * math.cos(a), 800.0 + 3000.0 * math.sin(a))
            for a in (2.0 * math.pi * k / vertices for k in range(vertices))]


class TestHostilePlans:
    """Counts, not clocks: what a hostile item makes the bake DO is bounded — the
    points it reads, the elements it generates, the tiles and records it paints,
    the bytes it holds — and every count has a control that shows the instrument
    sees the thing it bounds."""

    @pytest.mark.parametrize("path_style", [s for s in PathFenceStyle if s is not PathFenceStyle.NONE],
                             ids=lambda s: s.name)
    def test_a_path_of_19_kilometres_generates_elements_for_its_tiles_only(
            self, qtbot: Any, path_style: PathFenceStyle) -> None:
        """Two points 19 km apart: a style's elements are as many as the line is
        LONG. Only those inside a tile are generated, with the pattern's phase
        kept — the five tiles the line crosses still are the canvas's picture."""
        from open_garden_planner.ui.canvas.items.path_style_paint import PathStylePaint

        scene = _hostile_scene()
        item = PolylineItem([QPointF(-950_000.0, 795.5), QPointF(950_000.0, 811.25)],
                            object_type=ObjectType.PATH, path_fence_style=path_style)
        pen = item.pen()
        pen.setWidthF(30.0)
        adopt_pen(item, pen)
        scene.addItem(item)
        mean, _worst, bake = compare(scene, production_registry())
        assert bake.baker.painted_ids() == (str(item.item_id),)
        assert len(bake.baker.last_repainted) == 20 and bake.baker.records_painted == 5
        assert mean <= 0.05, mean
        generated = bake.baker.elements_generated
        # control: the canvas's own walk over the same line, at the style's densest
        # spacing, is hundreds of thousands of elements — the tiles' share is a sliver
        whole = sum(1 for _element in PathStylePaint(item.points, item.pen())._walk_path(4.0))
        assert whole == 475_001
        assert generated <= 5 * 2 * 400 and bake.baker.capped == frozenset(), generated
        # … and the exact walk only where a tile can afford the WHOLE leg (the posts of
        # a chain-link fence, 2.4 m apart: 7,917 steps); 475,001 dots never are — that
        # leg is entered by arithmetic
        assert bake.baker.steps_walked <= 5 * 16_384
        if path_style is PathFenceStyle.GRAVEL_PATH:
            assert bake.baker.steps_walked == 0
        if path_style is not PathFenceStyle.DIRT_PATH:  # the one style without elements
            assert generated > 0

    @pytest.mark.parametrize("stroke", [StrokeStyle.DASHED, StrokeStyle.DOTTED, StrokeStyle.DASH_DOT],
                             ids=lambda s: s.name)
    def test_a_dashed_line_of_19_kilometres(self, qtbot: Any, stroke: StrokeStyle) -> None:
        """A dashed pen has no elements of ours to count: Qt's dasher makes the
        dashes, and skips what lies outside the image (measured, docs §8.32.5: 19 km
        cost what 100 m cost). Pinned by its result — the bake finishes inside the
        suite's time limit and is the canvas's picture."""
        scene = _hostile_scene()
        item = PolylineItem([QPointF(-950_000.0, 795.5), QPointF(950_000.0, 811.25)],
                            object_type=ObjectType.PATH)
        pen = item.pen()
        pen.setWidthF(0.5)
        pen.setStyle(stroke.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)
        mean, _worst, bake = compare(scene, production_registry())
        assert bake.baker.records_painted == 5 and bake.baker.elements_generated == 0
        assert bake.records[str(item.item_id)].material.paint.stroke_style == pen.style().name
        assert mean <= 0.05

    def test_an_outline_at_the_size_bound_is_painted_and_one_beyond_is_never_read(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """The SIZE bound stays in front of everything: 16,384 vertices are a flat
        item like any other (no regions; painted into every tile); 16,385 are left
        out with the size reason before one point is read, copied or painted."""
        from open_garden_planner.core.scene3d import LocalFrame
        from open_garden_planner.core.scene3d.polygon import MAX_ITEM_VERTICES
        from open_garden_planner.ui.view3d import snapshot

        assert MAX_ITEM_VERTICES == 16_384
        outlines: list[int] = []
        copies: list[int] = []
        real_outline, real_ring = snapshot.item_outline, LocalFrame.local_ring

        def counted_outline(item: Any, at_date: Any = None) -> Any:
            outline = real_outline(item, at_date)
            outlines.append(len(outline.points) if outline is not None else 0)
            return outline

        def counted_ring(self: Any, points: Any) -> Any:
            copies.append(len(points))
            return real_ring(self, points)

        monkeypatch.setattr(snapshot, "item_outline", counted_outline)
        monkeypatch.setattr(LocalFrame, "local_ring", counted_ring)

        scene = _hostile_scene()
        at_the_bound = PolygonItem(_whole_plan_ring(16_384), object_type=ObjectType.LAWN)
        scene.addItem(at_the_bound)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        record = bake.records[str(at_the_bound.item_id)]
        assert bake.skipped == [] and record.footprints == () and len(record.outline) == 16_384
        assert outlines == [16_384] and copies and max(copies) == 16_384  # control: it IS read
        assert bake.baker.records_painted == 20 and bake.baker.capped_tiles == 0
        assert not np.any(np.all(bake.image()[..., :3] == np.array(MEADOW_RGB), axis=2))

        scene.removeItem(at_the_bound)
        outlines.clear()
        copies.clear()
        beyond = PolygonItem(_whole_plan_ring(16_385), object_type=ObjectType.LAWN)
        line = PolylineItem(_whole_plan_ring(16_385), object_type=ObjectType.PATH)
        scene.addItem(beyond)
        scene.addItem(line)
        painted = bake.baker.records_painted
        bake.step()
        assert bake.records == {}
        assert [(s.reason, s.kind) for s in bake.skipped] == [
            (SkipReason.OUTLINE_TOO_LARGE, "LAWN"), (SkipReason.OUTLINE_TOO_LARGE, "PATH")]
        assert outlines == [] and copies == []  # not one point read, none copied
        assert bake.baker.painted_ids() == ()
        assert bake.baker.records_painted == painted  # … and none painted: every tile is bare
        assert np.all(bake.image()[..., :3] == np.array(MEADOW_RGB))

    def test_a_plan_of_ten_thousand_kilometres_by_one_centimetre(self, qtbot: Any) -> None:
        """A degenerate plan rectangle is refused before a tile exists; the scene
        goes on without a baked ground and the failure is on record."""
        scene = new_scene()
        lawn = _rectangle("border", ObjectType.LAWN)
        scene.addItem(lawn)
        bake = Bake(scene)
        bake.plan = GroundSpec(1e9, 1.0)
        bake.step()
        assert bake.sync.ground_failure is not None
        assert bake.sync.ground_failure[0] == "ValueError" and "beyond" in bake.sync.ground_failure[1]
        assert bake.sink.ground == GroundSpec(1e9, 1.0) and bake.baker.grid is None
        assert bake.baker.tiles_painted == 0 and set(bake.sink.item_ids()) == {str(lawn.item_id)}
        # the longest plan there is, one centimetre deep: a ground like any other —
        # within the tile bound, and four bytes a pixel
        bake.plan = GroundSpec(1e6, 1.0)
        bake.step()
        assert bake.sync.ground_failure is None
        assert len(bake.tiles) == bake.grid.tile_count == 245 <= 256
        assert sum(len(tile.pixels) for tile in bake.tiles) == 125_000 * 4

    @pytest.mark.parametrize("where", [1e15, -1e15, float("nan"), float("inf"), float("-inf")],
                             ids=["1e15", "-1e15", "nan", "inf", "-inf"])
    def test_an_item_at_a_coordinate_no_plan_holds_never_reaches_the_bake(
            self, qtbot: Any, where: float) -> None:
        scene = new_scene()
        far = _rectangle("border", ObjectType.LAWN)
        near = _rectangle("corner", ObjectType.LAWN)
        scene.addItem(far)
        scene.addItem(near)
        far.setPos(where, 0.0)
        bake = Bake(scene)
        bake.step()
        assert set(bake.records) == {str(near.item_id)}
        assert [s.reason for s in bake.skipped] in ([SkipReason.OUT_OF_RANGE],
                                                    [SkipReason.RECORD_FAILED])
        assert bake.baker.painted_ids() == (str(near.item_id),) and bake.baker.failures == {}

    def test_two_thousand_surfaces_over_the_whole_plan(self, qtbot: Any) -> None:
        """The SUM. A tile's cost is the sum over its records, so a tile paints at
        most ``TILE_RECORDS`` — the ones that overlap it most; of equals the
        topmost (these lawns are translucent: none of them ends the walk). The
        small pond on top of them is the SMALLEST member of its tile, and is what
        that tile loses."""
        from open_garden_planner.ui.view3d.ground_bake import TILE_RECORDS

        assert TILE_RECORDS == 256
        scene = _hostile_scene()
        lawns: list[Any] = []

        def add_surfaces(first: int, last: int) -> None:
            # as a plan file is loaded: the scene's stacking is settled once, at the end
            # (adding 2,000 items one by one takes the 2D scene 40 s — not the bake's)
            with scene.suspend_z_refresh(renumber=True):
                for index in range(first, last):
                    item = RectangleItem(-10.0, -10.0, 2420.0, 1620.0, object_type=ObjectType.LAWN)
                    style(item, FillPattern.SOLID, QColor(index % 256, 120, 60, 40))
                    scene.addItem(item)
                    lawns.append(item)

        add_surfaces(0, 200)
        bake = Bake(scene)
        bake.step()
        assert bake.baker.records_painted == 20 * 200 and bake.baker.capped_tiles == 0  # control
        add_surfaces(200, 2000)
        pond = CircleItem(700.0, 700.0, 90.0, object_type=ObjectType.POND_POOL)
        scene.addItem(pond)
        bake = Bake(scene)
        bake.step()
        assert len(bake.records) == 2001 and len(bake.baker.painted_ids()) == 2001
        assert bake.baker.tiles_painted == 20
        assert bake.baker.records_painted == 20 * TILE_RECORDS and bake.baker.capped_tiles == 20
        # what a workspace can show the user: WHERE the ground holds less than the plan
        assert bake.baker.capped == frozenset(bake.grid.tile_keys())
        topmost = tuple(str(item.item_id) for item in lawns[-TILE_RECORDS:])
        assert all(bake.baker._order[key] == topmost for key in bake.grid.tile_keys())  # noqa: SLF001
        # The books: ONE entry a record (not one a record and tile: 40,020) and the ids
        # a tile is painted with; the comparisons that found them: 257 a tile (256
        # members, and the one that shows the tile is capped) — and the pond in its tile.
        assert bake.baker.entries_held() == 2001 + 20 * TILE_RECORDS
        assert bake.baker.admission_checks == 20 * (TILE_RECORDS + 1) + 1 == 5_141
        # the pond is moved: ONE record looked at, its tile asked again — and nothing to
        # paint, because the pond is not among what that tile holds
        painted, checks = bake.baker.records_painted, bake.baker.admission_checks
        MoveItemsCommand([pond], QPointF(35.0, -20.0)).execute()
        assert bake.step() == SceneDiff(transform=(str(pond.item_id),))
        assert bake.baker.last_examined == 1 and bake.baker.last_repainted == ()
        assert bake.baker.records_painted == painted
        assert bake.baker.admission_checks - checks == TILE_RECORDS + 2
        # the topmost lawn is recoloured: ONE record looked at, every tile painted with its 256
        style(lawns[-1], FillPattern.SOLID, QColor(250, 10, 10, 40))
        assert bake.step() == SceneDiff(material=(str(lawns[-1].item_id),))
        assert bake.baker.last_examined == 1 and len(bake.baker.last_repainted) == 20
        assert bake.baker.records_painted - painted == 20 * TILE_RECORDS
        assert bake.baker.entries_held() == 2001 + 20 * TILE_RECORDS
        assert bake.sink.state().ground == bake.sync.expected_state().ground

    def test_a_tile_generates_no_more_than_its_share_of_elements(self, qtbot: Any) -> None:
        """A gravel path folded 1,500 times into one corner of the plan: 7.5 km of
        dots inside a single tile. The tile stops at ``TILE_ELEMENTS``."""
        from open_garden_planner.ui.view3d.ground_bake import TILE_ELEMENTS

        scene = _hostile_scene()
        points = [QPointF(20.0 + 480.0 * (k % 2), 20.0 + 470.0 * k / 1500.0) for k in range(1501)]
        item = PolylineItem(points, object_type=ObjectType.PATH,
                            path_fence_style=PathFenceStyle.GRAVEL_PATH)
        scene.addItem(item)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert bake.skipped == [] and bake.baker.painted_ids() == (str(item.item_id),)
        touched = bake.baker.records_painted
        assert 1 <= touched <= 4
        assert TILE_ELEMENTS <= bake.baker.elements_generated <= touched * TILE_ELEMENTS
        assert bake.baker.capped_tiles >= 1 and (0, 0) in bake.baker.capped

    def test_paths_that_clip_a_row_of_tiles_by_a_hair_share_the_tiles_steps(self, qtbot: Any) -> None:
        """256 gravel paths, each ONE leg of 640 m across the plan's first row of
        tiles. The steps of the exact walk are the work — a leg is walked from its
        start, 16,001 steps, to hand out the 170 dots of one tile. They are charged
        to the TILE: at most ``TILE_WALK_STEPS`` for all its paths together.
        (Measured before that: 20,481,280 steps for this plan, 4,096,256 a tile.)"""
        from open_garden_planner.ui.view3d.ground_bake import TILE_ELEMENTS, TILE_WALK_STEPS

        scene = _hostile_scene()
        for k in range(256):
            scene.addItem(PolylineItem(
                [QPointF(-30_000.0, 100.0 + k), QPointF(34_000.0, 101.0 + k)],
                object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.GRAVEL_PATH))
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert bake.skipped == [] and bake.baker.records_painted == 5 * 256
        assert bake.baker.steps_walked <= 5 * TILE_WALK_STEPS == 81_920
        assert bake.baker.steps_walked == 5 * 16_001  # one leg's exact walk a tile, and no more
        assert bake.baker.elements_generated <= 5 * TILE_ELEMENTS
        print(f"\nhostile: 256 legs x 5 tiles: {bake.baker.steps_walked} steps walked, "
              f"{bake.baker.elements_generated} elements generated")

    def test_a_spent_budget_gives_the_next_path_nothing(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zero is a budget. Two gravel paths in one tile, the tile's elements set to
        exactly what the lower one needs: the upper one gets none — not "no bound"."""
        from open_garden_planner.ui.view3d import ground_bake

        def scene_with(count: int) -> tuple[CanvasScene, list[Any]]:
            scene = _hostile_scene()
            paths = [PolylineItem([QPointF(60.0, 100.0 + 150.0 * k), QPointF(400.0, 110.0 + 150.0 * k)],
                                  object_type=ObjectType.PATH,
                                  path_fence_style=PathFenceStyle.GRAVEL_PATH) for k in range(count)]
            for path in paths:
                scene.addItem(path)
            return scene, paths

        alone, _paths = scene_with(1)
        first = Bake(alone)
        first.step()
        needed = first.baker.elements_generated
        assert needed > 50 and first.baker.capped == frozenset()

        monkeypatch.setattr(ground_bake, "TILE_ELEMENTS", needed)
        both, _paths = scene_with(2)
        second = Bake(both)
        second.step()
        assert second.baker.records_painted == 2
        assert second.baker.elements_generated == needed  # the first path's, to the last dot
        assert second.baker.capped == frozenset({(0, 0)})

    def test_what_a_painter_does_before_its_first_element_is_bounded_by_the_tiles_cost(
            self, qtbot: Any) -> None:
        """A styled path strokes its whole line, builds two offset lines and walks it
        — passes over EVERY vertex before one element is drawn. They are charged:
        a styled record costs its vertices x 8, a dashed one x 3 (its points, its
        path, its cut to the tile), and a tile paints its topmost records only
        while the sum stays within ``TILE_VERTICES``."""
        from open_garden_planner.core.scene3d import Material, Paint, Params, Transform
        from open_garden_planner.ui.view3d.ground_bake import TILE_VERTICES

        assert TILE_VERTICES == 262_144

        def line(item_id: str, points: int, **more: Any) -> Record:
            path = tuple((-200.0 + 400.0 * k / (points - 1), 0.0) for k in range(points))
            return Record(item_id=item_id, kind="PATH", shape="polyline", footprints=(),
                          transform=Transform(256.0, 256.0), path=path, path_width_cm=20.0,
                          material=Material("PATH", stroke_rgba=(120, 110, 100, 255),
                                            paint=more.pop("paint", Paint())),
                          params=Params({"seed": item_id, **more}))

        styled = {f"s{k}": line(f"s{k}", 4096, path_style="GRAVEL_PATH") for k in range(40)}
        baker = GroundBaker(budget_s=None)
        baker.bake(styled, None, (), 512.0, 512.0)
        assert baker.records_painted == 8 == TILE_VERTICES // (4096 * 8)  # of 40
        assert baker.capped == frozenset({(0, 0)})

        dashed = {f"d{k}": line(f"d{k}", 16_384, paint=Paint(stroke_style="DashLine"))
                  for k in range(8)}
        baker = GroundBaker(budget_s=None)
        baker.bake(dashed, None, (), 512.0, 512.0)
        assert baker.records_painted == 5 == TILE_VERTICES // (16_384 * 3)  # of 8
        assert baker.capped == frozenset({(0, 0)})

        dearest = {f"g{k}": line(f"g{k}", 16_384, path_style="GRAVEL_PATH") for k in range(3)}
        baker = GroundBaker(budget_s=None)
        baker.bake(dearest, None, (), 512.0, 512.0)
        assert baker.records_painted == 2 == TILE_VERTICES // (16_384 * 8)  # exactly the bound

        plain = {f"p{k}": line(f"p{k}", 1024) for k in range(200)}
        baker = GroundBaker(budget_s=None)
        baker.bake(plain, None, (), 512.0, 512.0)
        assert baker.records_painted == 200 and baker.capped == frozenset()  # control

    def test_a_dashed_line_is_cut_to_the_tile_before_it_is_stroked(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """What the dasher is handed, counted: for a dashed line of 19 km, per tile,
        one run of two points no longer than the tile and its margin — starting
        with the dash offset of the place it starts at."""
        from open_garden_planner.ui.view3d import ground_bake

        runs: list[tuple[float, float, int]] = []
        real = ground_bake._runs_inside

        def recording(points: Any, clip: Any) -> Any:
            for start, length, run in real(points, clip):
                assert length == pytest.approx(sum(
                    math.hypot(b.x() - a.x(), b.y() - a.y())
                    for a, b in zip(run, run[1:], strict=False)), rel=1e-9)
                runs.append((start, length, len(run)))
                yield start, length, run

        monkeypatch.setattr(ground_bake, "_runs_inside", recording)
        scene = _hostile_scene()
        item = PolylineItem([QPointF(-950_000.0, 795.5), QPointF(950_000.0, 811.25)],
                            object_type=ObjectType.PATH)
        pen = item.pen()
        pen.setWidthF(6.0)
        pen.setStyle(StrokeStyle.DASHED.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)
        bake = Bake(scene, registry=production_registry(), bare_rgb=canvas_rgb())
        bake.step()
        assert len(runs) == 5 and all(points == 2 for _start, _length, points in runs)
        assert max(length for _start, length, _points in runs) <= 512.0 + 2 * (2.5 * 6.0 + 8.0 + 2.0) + 1.0
        # ... and its dashes are charged to the tile: a run's length over three pen widths
        assert bake.baker.dashes_charged == sum(int(length / 18.0) + 1 for _s, length, _p in runs)
        assert 5 * 28 <= bake.baker.dashes_charged <= 5 * 33 and bake.baker.capped == frozenset()
        starts = sorted(start for start, _length, _points in runs)
        assert 949_900.0 < starts[0] < 950_000.0  # where the plan begins, along the line
        # The dashes lie where the WHOLE line's lie — judged by arithmetic, not by the
        # canvas: over 9.5 km of line outside the image Qt's own dasher loses the phase
        # (measured: it agrees with the arithmetic at 261 of 393 places; a line of 190 m
        # at all of them). A dash is 4 pen widths on, 2 off: 36 cm from the line's start.
        first, second = item.points
        length = math.hypot(second.x() - first.x(), second.y() - first.y())
        dir_x, dir_y = (second.x() - first.x()) / length, (second.y() - first.y()) / length
        baked = bake.image()
        judged = 0
        for east in range(20, 2380, 3):
            along = (east - first.x()) / dir_x
            phase = along % 36.0
            if not (6.0 <= phase <= 18.0 or 27.5 <= phase <= 32.5):
                continue  # near a dash's end: its round cap decides
            north = first.y() + dir_y * along
            drawn = tuple(int(v) for v in baked[int(1600.0 - north), east, :3]) != canvas_rgb()
            assert drawn is (phase <= 18.0), (east, phase)
            judged += 1
        assert judged > 300

    @pytest.mark.parametrize("angle", [0.0, 33.0])
    def test_a_dashed_line_across_tiles_keeps_its_dashes_in_step(self, qtbot: Any, angle: float) -> None:
        scene = new_scene()
        item = _path(PathFenceStyle.NONE, "corner", width=6.0)
        pen = item.pen()
        pen.setStyle(StrokeStyle.DASHED.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)
        if angle:
            item._apply_rotation(angle)
        assert compare(scene, tile_px=2048)[:2] == (0.0, 0)  # one tile: one run, the canvas's stroke
        mean, _worst, _bake = compare(scene)
        assert mean <= 0.05, mean

    def test_a_tile_strokes_no_more_dashes_than_its_share(self, qtbot: Any) -> None:
        """A dotted line folded into one tile: its dots are as many as it is LONG,
        whatever its vertex count. A line the tile can afford is dotted and charged;
        one it cannot is stroked solid — nothing charged, and the tile says so."""
        from open_garden_planner.ui.view3d.ground_bake import TILE_DASHES

        assert TILE_DASHES == 32_768

        def folded(folds: int) -> Bake:
            scene = _hostile_scene()
            points = [QPointF(20.0 + 480.0 * (k % 2), 20.0 + 470.0 * k / folds)
                      for k in range(folds + 1)]
            item = PolylineItem(points, object_type=ObjectType.PATH)
            pen = item.pen()
            pen.setWidthF(2.0)
            pen.setStyle(StrokeStyle.DOTTED.to_qt_pen_style())
            adopt_pen(item, pen)
            scene.addItem(item)
            bake = Bake(scene, registry=production_registry())
            bake.step()
            assert bake.skipped == [] and bake.baker.records_painted == 1
            return bake

        affordable = folded(100)  # 480 m of dots 2 cm wide: one in 6 cm
        assert affordable.baker.dashes_charged == 8_001 and affordable.baker.capped == frozenset()
        beyond = folded(1500)  # 7.2 km of them in the same tile: 120,001
        assert beyond.baker.dashes_charged == 0 and beyond.baker.capped == frozenset({(0, 0)})
        # solid is a line all the same: the tile is not left bare
        assert np.any(np.any(beyond.image()[-512:, :512, :3] != np.array(MEADOW_RGB), axis=2))

    @pytest.mark.parametrize("shape", ["rectangle", "polygon", "ellipse"])
    def test_a_dashed_outline_is_cut_to_the_tile_and_its_dashes_charged(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch, shape: str) -> None:
        """A dashed outline that lies in ONE tile is the canvas's own call, its
        dashes charged first. One that reaches beyond is cut to the tile, each run
        starting in step: the dashes lie where the canvas has them (handed the whole
        outline, Qt's dasher put them elsewhere in a tile: measured, up to 7,564
        pixels of this plan). A tile without the dashes strokes solid, and says so."""
        from open_garden_planner.ui.view3d import ground_bake

        scene = new_scene()
        if shape == "rectangle":
            item: Any = RectangleItem(40.0, 30.0, 1000.0, 620.0, object_type=ObjectType.LAWN)
        elif shape == "ellipse":
            item = EllipseItem(40.0, 30.0, 1000.0, 620.0, object_type=ObjectType.GENERIC_ELLIPSE)
        else:
            item = PolygonItem([QPointF(40.0, 30.0), QPointF(1040.0, 60.0), QPointF(900.0, 650.0),
                                QPointF(500.0, 420.0), QPointF(80.0, 640.0)],
                               object_type=ObjectType.TERRACE_PATIO)
        pen = item.pen()
        pen.setWidthF(4.0)
        pen.setStyle(StrokeStyle.DASHED.to_qt_pen_style())
        adopt_pen(item, pen)
        scene.addItem(item)

        mean, worst, one = compare(scene, tile_px=2048)
        assert (mean, worst) == (0.0, 0)  # one tile: the canvas's call, bit for bit
        whole = one.baker.dashes_charged
        assert 200 <= whole <= 280  # a perimeter of 26 to 32 m, a dash in 12 cm

        mean, worst, tiles = compare(scene)
        # an ellipse is cut along chords a fiftieth of a pixel from the true curve; Qt's
        # own is four Bezier arcs, up to an eighth of a pixel from it
        assert mean <= (0.1 if shape == "ellipse" else 0.01), mean
        assert whole <= tiles.baker.dashes_charged <= 1.4 * whole  # the runs and their margins
        assert tiles.baker.capped == frozenset() and len(tiles.baker.last_repainted) == 6

        monkeypatch.setattr(ground_bake, "TILE_DASHES", 20)  # fewer than a run across a tile
        _mean, _worst, poor = compare(scene)
        assert poor.baker.dashes_charged <= 6 * 20 and len(poor.baker.capped) >= 4
        _mean, _worst, poor_one = compare(scene, tile_px=2048)
        assert poor_one.baker.dashes_charged == 0 and poor_one.baker.capped == frozenset({(0, 0)})
        # solid is an outline all the same
        solid = canvas_render(scene, poor_one.grid)
        assert difference(poor_one.image(), solid)[0] > 0.05

    def test_the_books_hold_one_entry_a_record_whatever_it_covers(self, qtbot: Any) -> None:
        """Fifty thousand rectangles, each over the whole plan (records by hand — the
        2D scene needs minutes to hold that many). What the baker HOLDS is one entry
        a record and the ids a tile is painted with; what it COMPARES to find them
        is 257 a tile — the 256 it keeps (they all overlap it whole: of equals the
        topmost) and the record that shows it is capped — for a full bake, and for
        an edit the tiles it touches."""
        from open_garden_planner.core.scene3d import Material, Paint, Params, Transform
        from open_garden_planner.ui.view3d.ground_bake import TILE_RECORDS

        per_tile = TILE_RECORDS

        def surface(item_id: str, half: tuple[float, float], at: tuple[float, float],
                    fill: tuple[int, int, int, int] = (40, 120, 60, 40)) -> Record:
            ring = ((-half[0], -half[1]), (half[0], -half[1]), (half[0], half[1]), (-half[0], half[1]))
            return Record(item_id=item_id, kind="LAWN", shape="rectangle", footprints=(ring,),
                          transform=Transform(*at),
                          material=Material("LAWN", fill_rgba=fill, paint=Paint()),
                          params=Params({"seed": item_id}))

        count = 50_000
        records = {f"r{k}": surface(f"r{k}", (1300.0, 900.0), (1200.0, 800.0)) for k in range(count)}
        records["top"] = surface("top", (50.0, 50.0), (700.0, 700.0), (200, 30, 30, 255))
        baker = GroundBaker(budget_s=None)
        baker.bake(records, None, (), 2400.0, 1600.0)
        assert len(baker.painted_ids()) == count + 1 and baker.last_examined == count + 1
        assert baker.entries_held() == count + 1 + 20 * per_tile == 55_121  # not 20 x 50,000
        # … and one more in the tile of "top": the small square is a member too — the
        # smallest, and so the one that tile loses
        assert baker.admission_checks == 20 * (per_tile + 1) + 1 == 5_141
        assert baker.records_painted == 20 * per_tile
        assert baker.capped == frozenset(baker.grid.tile_keys())
        assert "top" not in baker._order[(1, 1)]  # noqa: SLF001

        # one small item moved: one record looked at, one tile's records found again
        checks, painted = baker.admission_checks, baker.records_painted
        moved = dict(records)
        moved["top"] = surface("top", (50.0, 50.0), (735.0, 680.0), (200, 30, 30, 255))
        baker.bake(moved, SceneDiff(transform=("top",)), (), 2400.0, 1600.0)
        # … its tile's records are found again, and are the same: nothing is painted
        assert baker.last_examined == 1 and baker.last_repainted == ()
        assert baker.admission_checks - checks == per_tile + 2
        assert baker.records_painted == painted
        assert baker.entries_held() == count + 1 + 20 * per_tile

        # a record no tile shows (the lowest of 50,000) changes: every tile's records
        # are found again - and are the same, so not one tile is painted
        checks, painted_tiles = baker.admission_checks, baker.tiles_painted
        recoloured = dict(moved)
        recoloured["r0"] = surface("r0", (1300.0, 900.0), (1200.0, 800.0), (250, 250, 0, 255))
        tiles = baker.bake(recoloured, SceneDiff(material=("r0",)), (), 2400.0, 1600.0)
        assert baker.admission_checks - checks == 5_141
        assert baker.last_repainted == () and baker.tiles_painted == painted_tiles
        assert all(mine is theirs for mine, theirs in zip(tiles, baker.tiles(), strict=True))

    def test_the_comparisons_of_a_full_bake_are_linear_in_the_records(self, qtbot: Any) -> None:
        """The dearest plan for the walk that hands the tiles their records: records
        over HALF the tiles, so that the other half stays open and every record is
        asked about. One look-up per record and tile it reaches — never more."""
        from open_garden_planner.core.scene3d import Material, Paint, Params, Transform
        from open_garden_planner.ui.view3d.ground_bake import TILE_RECORDS

        ring = ((-505.0, -900.0), (505.0, -900.0), (505.0, 900.0), (-505.0, 900.0))
        material = Material("LAWN", fill_rgba=(40, 120, 60, 40), paint=Paint())
        count = 20_000
        records = {f"w{k}": Record(item_id=f"w{k}", kind="LAWN", shape="rectangle",
                                   footprints=(ring,), transform=Transform(500.0, 800.0),
                                   material=material, params=Params({"seed": "w"}))
                   for k in range(count)}
        baker = GroundBaker(budget_s=None)
        baker.bake(records, None, (), 2400.0, 1600.0)  # 5 x 4 tiles: the west 2 columns
        assert baker.capped == frozenset((c, r) for c in range(2) for r in range(4))
        # they end at east 1009 (their paint box): the first column's tiles are overlapped
        # whole and are closed after 257 records; the second column's are not, and every
        # record is a member that is ranked — 256 kept, the rest left out, none closed
        painted = 8 * TILE_RECORDS
        assert baker.records_painted == painted == 2_048
        assert baker.admission_checks == count * 8  # each record: the 8 tiles it reaches
        assert baker.entries_held() == count + painted

    def test_a_sprite_of_nine_kilometres_is_rendered_with_a_bounded_image(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A furniture item's sprite is rendered at the item's size — the PLAN's
        number. Within the bound it is asked for exactly as the canvas asks; beyond,
        with ``SPRITE_MAX_PIXELS`` at most, and stretched over every tile."""
        from open_garden_planner.ui.view3d import ground_bake
        from open_garden_planner.ui.view3d.ground_bake import SPRITE_MAX_PIXELS

        assert SPRITE_MAX_PIXELS == 262_144
        asked: list[tuple[float, float]] = []
        real = ground_bake.render_furniture_pixmap

        def recording(*, object_type: Any, width: float, height: float) -> Any:
            asked.append((width, height))
            pixmap = real(object_type=object_type, width=width, height=height)
            assert pixmap is not None and pixmap.width() * pixmap.height() <= SPRITE_MAX_PIXELS
            return pixmap

        monkeypatch.setattr(ground_bake, "render_furniture_pixmap", recording)
        scene = _hostile_scene()
        scene.addItem(RectangleItem(100.0, 100.0, 300.0, 200.0, object_type=ObjectType.PERGOLA))
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert set(asked) == {(300.0, 200.0)}  # control: the canvas's own size
        asked.clear()

        scene.addItem(RectangleItem(-450_000.0, -450_000.0, 900_000.0, 900_000.0,
                                    object_type=ObjectType.PERGOLA))
        scene.addItem(RectangleItem(-450_000.0, 700.0, 900_000.0, 0.5, object_type=ObjectType.PERGOLA))
        painted = bake.baker.records_painted
        bake.step()
        assert bake.skipped == [] and bake.baker.failures == {}
        assert bake.baker.records_painted - painted >= 20 + 5 + 1  # every tile, a row, the first
        sizes = {(max(int(w), 4), max(int(h), 4)) for w, h in asked}
        assert len(sizes) == 3 and {(300, 200), (65_536, 4)} < sizes
        (square,) = sizes - {(300, 200), (65_536, 4)}
        assert square[0] == square[1] and 510 <= square[0] <= 512  # not 900,000 a side
        assert all(w * h <= SPRITE_MAX_PIXELS for w, h in sizes)
        assert not np.any(np.all(bake.image()[..., :3] == np.array(MEADOW_RGB), axis=2))

    def test_a_textured_surface_of_nine_kilometres_costs_its_tiles(self, qtbot: Any) -> None:
        """A fill is a brush of one small texture, whatever it fills: the painter
        clips it to the tile. Twenty tiles, one record each, and the cache of
        textures is the pattern's and the colour's — nothing of the item's size."""
        from open_garden_planner.core import fill_patterns

        scene = _hostile_scene()
        item = RectangleItem(-450_000.0, -450_000.0, 900_000.0, 900_000.0, object_type=ObjectType.LAWN)
        style(item, FillPattern.GRASS, QColor(90, 160, 70))
        scene.addItem(item)
        before = len(fill_patterns._tinted_cache)
        bake = Bake(scene, registry=production_registry())
        bake.step()
        assert bake.skipped == [] and bake.baker.failures == {} and bake.baker.capped == frozenset()
        assert bake.baker.records_painted == 20 and bake.baker.tiles_painted == 20
        assert len(fill_patterns._tinted_cache) - before <= 1
        texture = create_pattern_brush(FillPattern.GRASS, QColor(90, 160, 70)).texture()
        assert 0 < texture.width() <= 256 and 0 < texture.height() <= 256
        assert not np.any(np.all(bake.image()[..., :3] == np.array(MEADOW_RGB), axis=2))

    def test_the_bytes_a_ground_holds(self, qtbot: Any) -> None:
        """Four bytes a pixel, once: the sink's tiles ARE the baker's, and every bare
        tile of one size shares one block of meadow."""
        scene = _loaded("bench_large.ogp")
        bake = Bake(scene, registry=production_registry())
        bake.step()
        grid = bake.grid
        assert sum(len(tile.pixels) for tile in bake.tiles) == grid.width_px * grid.height_px * 4
        assert grid.width_px * grid.height_px * 4 == 60_000_000  # 50 x 30 m at 1 px/cm
        assert all(mine is theirs for mine, theirs in zip(bake.baker.tiles(), bake.tiles, strict=True))
        empty = CanvasScene(width_cm=5000.0, height_cm=3000.0)
        bare = Bake(empty)
        bare.step()
        assert len(bare.tiles) == 60
        assert len({id(tile.pixels) for tile in bare.tiles}) == 4  # full, last column, last row, corner

    @pytest.mark.parametrize("settings", [
        {"tile_px": 0}, {"tile_px": 15}, {"tile_px": 10**9}, {"tile_px": 512.0}, {"tile_px": True},
        {"max_pixels": 0}, {"max_pixels": 4096 * 4096 + 1}, {"max_pixels": 10**15},
        {"bare_rgb": (1, 2)}, {"bare_rgb": (1, 2, 256)}, {"bare_rgb": (1.0, 2.0, 3.0)},
    ])
    def test_a_setting_out_of_range_is_refused_where_it_enters(self, settings: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            GroundBaker(**settings)
