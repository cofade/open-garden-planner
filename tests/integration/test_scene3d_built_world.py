"""The built world end to end (Phase 17 L1.6, #385 — §8.10, gates G2 and G3).

live items → ``snapshot_records`` → ``SceneSync`` (production registry) → ``RecordingSink``

A real garden drawn with the real tools and the app's own commands: a house with
its ridge, a fence in every style, a wall, a raised bed with two plants, a round
container with a plant, a hedge and a shed. Asserted:

1. which builder each kind gets, each item's height and where each plant stands;
2. an edit session — raise the bed, move the house, change a fence's style, drag
   the ridge, undo it all — with the EXACT sink calls and builder invocations,
   and after every step incremental == full rebuild;
3. gate G2 on real items: the ridge line in the mesh, posed by the record's
   transform, is the LIVE ridge item's line in the scene, run on to the roof's
   edge — for turned houses and footprints that are not rectangles.

Nothing is rendered: the sink is the recording double (L1.2 runs the same garden
against Qt Quick 3D).
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    CreateItemCommand,
    MoveItemsCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY, effective_height_cm
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.plant_art import PLANT_KINDS
from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    default_builder,
    plan_overreach,
    pose_points,
    prism_mesh,
    verify_builder,
)
from open_garden_planner.core.scene3d.builders import (
    BUILT_WORLD_KINDS,
    OBJECT_KINDS,
    SURFACE_KINDS,
    beds,
    buildings,
    hedges,
    lines,
    palette,
    plants,
    production_registry,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.footprints import item_footprints
from open_garden_planner.ui.canvas.geometry_apply import apply_rotation, build_move_vertex_command
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_shadow_casters
from open_garden_planner.ui.view3d.snapshot import SkippedItem, snapshot_records

BEGIN, COMMIT = ("begin", None), ("commit", None)
STYLES = (PathFenceStyle.WOODEN_FENCE, PathFenceStyle.METAL_FENCE, PathFenceStyle.CHAIN_LINK,
          PathFenceStyle.HEDGE_FENCE, PathFenceStyle.STONE_WALL)


def draw_polygon(view: CanvasView, mouse_event: Any, tool: ToolType,
                 corners: list[tuple[float, float]]) -> PolygonItem:
    """Draw a polygon with the real tool: a click per corner, a double click to close."""
    before = set(view.scene().items())
    view.set_active_tool(tool)
    active = view.tool_manager.active_tool
    for x, y in corners:
        active.mouse_press(mouse_event, QPointF(x, y))
    active.mouse_double_click(mouse_event, QPointF(*corners[-1]))
    (polygon,) = [i for i in set(view.scene().items()) - before if isinstance(i, PolygonItem)]
    return polygon


def ridge_of(view: CanvasView, house: PolygonItem) -> PolylineItem:
    wanted = str(house.metadata["ridge_item_id"])
    (ridge,) = [i for i in view.scene().items() if str(getattr(i, "item_id", "")) == wanted]
    assert isinstance(ridge, PolylineItem) and ridge.object_type is ObjectType.ROOF_RIDGE
    return ridge


class Garden:
    """The story's garden, on a real view."""

    def __init__(self, view: CanvasView, mouse_event: Any) -> None:
        self.view = view
        self.scene = view.scene()
        self.commands = view.command_manager
        layer = self.scene.active_layer.id

        # a house, drawn with the HOUSE tool — which creates its ridge (core.roof_ridge)
        self.house = draw_polygon(view, mouse_event, ToolType.HOUSE,
                                  [(1000.0, 800.0), (1900.0, 800.0), (1900.0, 1340.0), (1000.0, 1340.0)])
        self.ridge = ridge_of(view, self.house)

        # a raised bed, drawn with its tool, and two plants put INTO it
        view.set_active_tool(ToolType.RAISED_BED)
        tool = view.tool_manager.active_tool
        tool.mouse_press(mouse_event, QPointF(400.0, 300.0))
        tool.mouse_move(mouse_event, QPointF(700.0, 500.0))
        tool.mouse_release(mouse_event, QPointF(700.0, 500.0))
        self.bed = next(i for i in self.scene.items() if isinstance(i, RectangleItem))
        self.bed_plants = [self._plant(480.0, 400.0, 45.0, layer), self._plant(620.0, 400.0, 70.0, layer)]

        # a round container with a plant
        self.pot = CircleItem(900.0, 400.0, 30.0, object_type=ObjectType.CONTAINER_ROUND, layer_id=layer)
        self.pot.metadata["container_material"] = "terracotta"
        self.commands.execute(CreateItemCommand(self.scene, self.pot, "pot"))
        self.pot_plant = self._plant(900.0, 400.0, 35.0, layer)

        # a fence in every style (and one with none), a wall
        self.fences: dict[str, PolylineItem] = {}
        for index, style in enumerate((PathFenceStyle.NONE, *STYLES)):
            y = 2000.0 + 150.0 * index
            fence = PolylineItem([QPointF(200.0, y), QPointF(900.0, y), QPointF(900.0, y + 90.0)],
                                 object_type=ObjectType.FENCE, layer_id=layer, path_fence_style=style)
            self.commands.execute(CreateItemCommand(self.scene, fence, "fence"))
            self.fences[style.name] = fence
        self.wall = PolylineItem([QPointF(2200.0, 300.0), QPointF(2200.0, 1100.0)],
                                 object_type=ObjectType.WALL, layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.wall, "wall"))

        # a hedge section, a hedge polygon, a tool shed
        self.hedge = RectangleItem(2600.0, 300.0, 400.0, 60.0, object_type=ObjectType.HEDGE_SECTION,
                                   layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.hedge, "hedge"))
        self.hedge_polygon = draw_polygon(view, mouse_event, ToolType.HEDGE_POLYGON, [
            (2600.0, 600.0), (3200.0, 600.0), (3200.0, 680.0), (2600.0, 680.0)])
        self.shed = RectangleItem(2600.0, 1000.0, 300.0, 200.0, object_type=ObjectType.TOOL_SHED,
                                  layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.shed, "shed"))

    def _plant(self, x: float, y: float, height: float, layer: Any) -> CircleItem:
        plant = CircleItem(x, y, 12.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        plant.metadata[METADATA_KEY] = height
        self.commands.execute(CreateItemCommand(self.scene, plant, "plant"))  # auto-parents
        return plant

    @staticmethod
    def id(item: Any) -> str:
        return str(item.item_id)


class Pipeline:
    """snapshot → sync → sink with the PRODUCTION registry, counting builder calls."""

    def __init__(self, scene: Any) -> None:
        self.scene = scene
        self.built: list[str] = []
        production = production_registry()
        self.registry = BuilderRegistry(default=self._counting(default_builder))
        for kind in production.kinds():
            self.registry.register(kind, self._counting(production.builder_for(kind)))
        self.sink = RecordingSink()
        self.sync = SceneSync(self.sink, self.registry, validate=True)

    def _counting(self, builder: Any) -> Any:
        def build(record: Record) -> tuple[MeshPart, ...]:
            self.built.append(record.item_id)
            return builder(record)  # type: ignore[no-any-return]
        return build

    def tick(self) -> tuple[SceneDiff, list[tuple[str, str | None]], list[str]]:
        self.sink.clear_calls()
        self.built.clear()
        records = snapshot_records(self.scene)
        result = self.sync.apply(records)
        fresh = SceneSync(RecordingSink(), production_registry(), validate=True)
        fresh.apply(records)
        assert isinstance(fresh.sink, RecordingSink)
        assert self.sink.state() == fresh.sink.state()  # incremental == full rebuild
        assert self.sync.failures == {} and fresh.failures == {}
        return result, self.sink.ops(), list(self.built)

    def top(self, item_id: str) -> float:
        held = self.sink.item(item_id)
        posed = [pose_points(held.transform, part.mesh.positions) for part in held.parts]
        return float(np.concatenate(posed)[:, 2].max())

    def bottom(self, item_id: str) -> float:
        held = self.sink.item(item_id)
        posed = [pose_points(held.transform, part.mesh.positions) for part in held.parts]
        return float(np.concatenate(posed)[:, 2].min())


def without(calls: list[tuple[str, str | None]], item_id: str) -> list[tuple[str, str | None]]:
    """The sink calls that do not concern ``item_id`` (the ROOF_RIDGE item: it has
    no solid of its own, and whether it has a record at all is the snapshot's
    business — the HOUSE carries the ridge)."""
    return [call for call in calls if call[1] != item_id]


@pytest.fixture
def garden(canvas: CanvasView, mouse_event: Any) -> Garden:
    return Garden(canvas, mouse_event)


def test_kinds_builders_heights_and_bases(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    result, calls, built = pipeline.tick()
    records = pipeline.sync.records
    assert set(result.added) == set(records) and calls[0] == BEGIN and calls[-1] == COMMIT
    assert sorted(built) == sorted(records)  # one builder call per item, no more

    # ── kinds → builders ─────────────────────────────────────────────────────
    production = production_registry()
    expected_builder = {
        "HOUSE": buildings.build_house, "TOOL_SHED": buildings.build_shed,
        "FENCE": lines.build_fence, "WALL": lines.build_wall,
        "RAISED_BED": beds.build_raised_bed, "CONTAINER_ROUND": beds.build_round_container,
        "HEDGE_SECTION": hedges.build_hedge, "HEDGE_POLYGON": hedges.build_hedge,
    }
    for kind, builder in expected_builder.items():
        assert production.builder_for(kind) is builder
    kinds = {record.kind for record in records.values()}
    assert kinds - BUILT_WORLD_KINDS <= {"PERENNIAL", "ROOF_RIDGE"}
    # the plants are the plant story's: its builder, wired into the same registry
    assert production.builder_for("PERENNIAL") is plants.build_plant
    assert production.kinds() == BUILT_WORLD_KINDS | OBJECT_KINDS | SURFACE_KINDS | PLANT_KINDS
    for plant in (*garden.bed_plants, garden.pot_plant):
        parts = pipeline.sink.item(Garden.id(plant)).parts
        assert parts and all(part.name in (plants.PART_FOLIAGE, plants.PART_WOOD) for part in parts)

    def names(item: Any) -> list[str]:
        return [part.name for part in pipeline.sink.item(Garden.id(item)).parts]

    assert names(garden.house) == ["walls", "roof", "facade", "floor"]  # L4.1: windows and a door
    assert names(garden.shed) == ["walls", "roof", "facade", "floor"]
    assert names(garden.bed) == ["bed"]
    assert names(garden.pot) == ["walls", "soil"]
    assert names(garden.hedge) == names(garden.hedge_polygon) == ["hedge"]
    assert names(garden.wall) == ["wall"]
    assert names(garden.fences["NONE"]) == names(garden.fences["WOODEN_FENCE"]) == ["fence"]
    assert names(garden.fences["METAL_FENCE"]) == names(garden.fences["CHAIN_LINK"]) == ["fence"]
    assert names(garden.fences["HEDGE_FENCE"]) == ["hedge"]
    assert names(garden.fences["STONE_WALL"]) == ["wall"]
    triangles = {style: sum(p.mesh.triangle_count for p in pipeline.sink.item(Garden.id(f)).parts)
                 for style, f in garden.fences.items()}
    assert triangles["NONE"] == triangles["WOODEN_FENCE"]
    assert len({triangles[s.name] for s in STYLES}) == len(STYLES)  # five different fences
    assert pipeline.sink.item(Garden.id(garden.house)).parts[1].material_kind == "roof"

    # ── heights: every solid's top is the 2D resolver's height, to the float32 ──
    for item in (garden.house, garden.shed, garden.bed, garden.pot, garden.hedge,
                 garden.hedge_polygon, garden.wall, *garden.fences.values()):
        height = effective_height_cm(item.object_type, item.metadata)
        assert height is not None
        assert pipeline.top(Garden.id(item)) == float(np.float32(height)), item.object_type.name
        assert pipeline.bottom(Garden.id(item)) == 0.0
    assert pipeline.top(Garden.id(garden.house)) == 450.0
    assert pipeline.top(Garden.id(garden.fences["CHAIN_LINK"])) == 120.0

    # ── bases: plants stand on their parent's soil (gate G3) ─────────────────
    for plant, height in zip(garden.bed_plants, (45.0, 70.0), strict=True):
        record = records[Garden.id(plant)]
        assert record.parent_id == Garden.id(garden.bed)
        assert record.transform.base_cm == 38.0  # the 40 cm bed's soil
        assert pipeline.bottom(Garden.id(plant)) == 38.0
        assert pipeline.top(Garden.id(plant)) == 38.0 + height
    pot_plant = records[Garden.id(garden.pot_plant)]
    # a pot's soil is AT its fill height (30 cm): the plan's own soil datum, no lip
    assert pot_plant.parent_id == Garden.id(garden.pot) and pot_plant.transform.base_cm == 30.0
    assert pipeline.bottom(Garden.id(garden.pot_plant)) == 30.0

    # … and that soil is where the meshes have it: nothing floats, nothing sinks
    soil = np.asarray(palette.SOIL.linear, dtype=np.float32)

    def soil_level(item: Any) -> float:
        for part in pipeline.sink.item(Garden.id(item)).parts:
            mine = np.isclose(part.mesh.colors, soil, atol=1e-6).all(axis=1)
            if mine.any():
                return float(part.mesh.positions[mine][:, 2].max())
        raise AssertionError("no soil")

    assert soil_level(garden.bed) == 38.0 and soil_level(garden.pot) == 30.0

    # ── colour: a fence is tinted with the item's own stroke, a bed is baked ──
    wooden = pipeline.sink.item(Garden.id(garden.fences["WOODEN_FENCE"]))
    assert all(part.tinted for part in wooden.parts)
    assert wooden.material.tint_rgba == (139, 90, 43, 255)  # PATH_FENCE_STYLES[WOODEN_FENCE]
    plain = pipeline.sink.item(Garden.id(garden.fences["NONE"]))
    assert plain.material.tint_rgba == (139, 69, 19, 255)  # OBJECT_STYLES[FENCE].stroke_color
    assert not pipeline.sink.item(Garden.id(garden.bed)).parts[0].tinted

    assert pipeline.tick() == (SceneDiff(), [], [])  # an untouched garden: nothing


def _drop(view: CanvasView, mime_tail: str, at: QPointF) -> CircleItem:
    """A gallery drop through the real ``dropEvent`` — how a user plants; returns the plant."""
    before = {id(item) for item in view.scene().items()}
    mime = QMimeData()
    mime.setText(f"gallery:{mime_tail}")
    view.dropEvent(QDropEvent(QPointF(view.mapFromScene(at)), Qt.DropAction.CopyAction, mime,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    (new,) = [item for item in view.scene().items()
              if isinstance(item, CircleItem) and id(item) not in before]
    return new


def test_a_raised_bed_with_two_real_plants_through_the_production_registry(
    canvas: CanvasView, mouse_event: Any
) -> None:
    """The two stories in one registry (merge of 5c44578). A raised bed drawn with its
    tool; a tomato and a lettuce dropped into it from the gallery — real plants, with
    bundled species data. Through ``SceneSync`` and ``production_registry()``:

    - the bed is this story's bed (a frame and soil at 38 cm);
    - the plants are the plant story's silhouettes — the archetype of each one's own
      sprite, not a placeholder and not the default prism — and they stand ON that soil;
    - raising the bed re-poses the plants and rebuilds none of them."""
    scene = canvas.scene()
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(400.0, 300.0))
    tool.mouse_move(mouse_event, QPointF(700.0, 500.0))
    tool.mouse_release(mouse_event, QPointF(700.0, 500.0))
    (bed,) = [item for item in scene.items() if isinstance(item, RectangleItem)]
    tomato = _drop(canvas, "PERENNIAL:species=tomato", QPointF(480.0, 400.0))
    lettuce = _drop(canvas, "PERENNIAL:species=lettuce", QPointF(620.0, 400.0))
    bed_id, tomato_id, lettuce_id = (str(item.item_id) for item in (bed, tomato, lettuce))
    assert tomato.parent_bed_id == bed.item_id == lettuce.parent_bed_id  # the drop linked them

    pipeline = Pipeline(scene)
    result, calls, built = pipeline.tick()
    records = pipeline.sync.records
    assert sorted(result.added) == sorted([bed_id, tomato_id, lettuce_id]) == sorted(built)
    production = production_registry()

    # the bed: this story's builder, its soil where the plants stand
    assert production.builder_for(records[bed_id].kind) is beds.build_raised_bed
    assert [part.name for part in pipeline.sink.item(bed_id).parts] == ["bed"]
    assert pipeline.top(bed_id) == 40.0 and pipeline.bottom(bed_id) == 0.0
    soil = np.asarray(palette.SOIL.linear, dtype=np.float32)
    (bed_part,) = pipeline.sink.item(bed_id).parts
    is_soil = np.isclose(bed_part.mesh.colors, soil, atol=1e-6).all(axis=1)
    assert float(bed_part.mesh.positions[is_soil][:, 2].max()) == 38.0

    # the plants: the plant story's builder, a silhouette each, on the soil
    for plant_id, archetype in ((tomato_id, "mound"), (lettuce_id, "rosette")):
        record = records[plant_id]
        assert record.kind == "PERENNIAL" and record.kind in PLANT_KINDS
        assert production.builder_for(record.kind) is plants.build_plant
        assert record.params.get("sprite_species")                # the plant story's input …
        assert plants.plant_archetype(record) == archetype        # … and what it builds from it
        held = pipeline.sink.item(plant_id)
        names = [part.name for part in held.parts]
        assert plants.PART_FOLIAGE in names and plants.PART_PLACEHOLDER not in names
        assert held.parts != default_builder(record)              # not the plain prism
        assert record.parent_id == bed_id and record.transform.base_cm == 38.0
        assert record.height_cm is not None
        assert pipeline.bottom(plant_id) == 38.0                  # ON the soil: no gap, nothing sunk
        assert pipeline.top(plant_id) == pytest.approx(38.0 + record.height_cm, abs=1e-3)
    plant_parts = {plant_id: pipeline.sink.item(plant_id).parts for plant_id in (tomato_id, lettuce_id)}
    shapes_built = plants.shape_cache_info().misses

    # raise the bed from 40 to 75 cm: ONE rebuild — the bed; the plants are re-posed
    canvas.command_manager.execute(_set_height(bed, 75.0))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(transform=(tomato_id, lettuce_id), geometry=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id), ("update_transform", tomato_id),
                     ("update_transform", lettuce_id), COMMIT]
    assert built == [bed_id]                                      # no plant builder call
    assert plants.shape_cache_info().misses == shapes_built      # … and no plant shape built
    for plant_id in (tomato_id, lettuce_id):
        held = pipeline.sink.item(plant_id)
        assert held.parts is plant_parts[plant_id]                # the very same meshes
        assert held.transform.base_cm == 73.0 and pipeline.bottom(plant_id) == 73.0
    assert pipeline.top(bed_id) == 75.0

    canvas.command_manager.undo()
    result, calls, built = pipeline.tick()
    assert built == [bed_id] and result.transform == (tomato_id, lettuce_id)
    assert [pipeline.bottom(plant_id) for plant_id in (tomato_id, lettuce_id)] == [38.0, 38.0]
    assert pipeline.tick() == (SceneDiff(), [], [])


def _set_height(item: Any, value: float) -> ChangePropertyCommand:
    """The properties panel's object-height edit: one undoable metadata write."""
    def apply(target: Any, new: float | None) -> None:
        if new is None:
            target.metadata.pop(METADATA_KEY, None)
        else:
            target.metadata[METADATA_KEY] = new

    return ChangePropertyCommand(item, "object height", item.metadata.get(METADATA_KEY), value, apply)


def _set_style(item: PolylineItem, style: PathFenceStyle) -> ChangePropertyCommand:
    """The properties panel's style combo (``_on_property_changed``): the style and
    its preset stroke — colour and width."""
    def apply(target: Any, new: PathFenceStyle) -> None:
        target.path_fence_style = new
        target.apply_style_preset()
        target.update()

    return ChangePropertyCommand(item, "path/fence style", item.path_fence_style, style, apply)


def test_edit_session_sends_exact_sink_calls(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    commands = garden.commands
    bed_id, house_id, ridge_id = Garden.id(garden.bed), Garden.id(garden.house), Garden.id(garden.ridge)
    plant_ids = [Garden.id(plant) for plant in garden.bed_plants]
    start_state = pipeline.sink.state()
    builds_at_start = pipeline.sync.build_count

    # ── raise the bed from 40 to 75 cm: ONE rebuild (the bed), its plants re-posed ──
    commands.execute(_set_height(garden.bed, 75.0))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(transform=tuple(plant_ids), geometry=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id),
                     *[("update_transform", plant_id) for plant_id in plant_ids], COMMIT]
    assert built == [bed_id]  # no plant mesh was rebuilt
    assert pipeline.top(bed_id) == 75.0
    assert [pipeline.bottom(plant_id) for plant_id in plant_ids] == [73.0, 73.0]
    assert pipeline.sink.item(Garden.id(garden.pot_plant)).transform.base_cm == 30.0  # untouched

    # ── move the house: ONE update_transform, no builder call ────────────────
    commands.execute(MoveItemsCommand([garden.house], QPointF(137.25, -42.5)))
    result, calls, built = pipeline.tick()
    assert house_id in result.transform and house_id not in result.geometry
    assert without(calls, ridge_id) == [BEGIN, ("update_transform", house_id), COMMIT]
    assert [b for b in built if b != ridge_id] == []  # the house and its roof were NOT rebuilt
    assert pipeline.sink.item(house_id).transform.east_cm == 1450.0 + 137.25

    # ── change a fence's style: geometry (style + stroke width) and material (stroke) ──
    fence = garden.fences["WOODEN_FENCE"]
    fence_id = Garden.id(fence)
    before_parts = pipeline.sink.item(fence_id).parts
    commands.execute(_set_style(fence, PathFenceStyle.METAL_FENCE))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(material=(fence_id,), geometry=(fence_id,))
    assert calls == [BEGIN, ("replace_geometry", fence_id), ("update_material", fence_id), COMMIT]
    assert built == [fence_id]
    held = pipeline.sink.item(fence_id)
    assert held.parts != before_parts and pipeline.top(fence_id) == 120.0
    assert held.material.tint_rgba == (60, 60, 60, 255)  # PATH_FENCE_STYLES[METAL_FENCE]
    assert pipeline.sync.records[fence_id].params["path_style"] == "METAL_FENCE"
    assert held.parts == production_registry().build(pipeline.sync.records[fence_id])

    # ── drag the ridge along the west wall: the HOUSE is rebuilt, nothing else ──
    old = garden.ridge.points[0]
    target = garden.ridge.mapFromScene(QPointF(1000.0 + 137.25, 900.0 - 42.5))  # on the moved wall
    commands.execute(build_move_vertex_command(garden.ridge, 0, old, target))
    result, calls, built = pipeline.tick()
    assert house_id in result.geometry and house_id not in result.transform
    assert without(calls, ridge_id) == [BEGIN, ("replace_geometry", house_id), COMMIT]
    assert [b for b in built if b != ridge_id] == [house_id]
    line = _ridge_in_scene(pipeline.sink.item(house_id), 450.0)
    assert float(np.linalg.norm(line - np.array([1137.25, 857.5]), axis=1).min()) < 35.0

    # ── undo all four: back to the very first state, with the fewest calls ───
    for _ in range(4):
        commands.undo()
    result, calls, built = pipeline.tick()
    assert set(result.geometry) - {ridge_id} == {bed_id, fence_id, house_id}
    assert set(result.transform) - {ridge_id} == {*plant_ids, house_id}
    assert set(result.material) == {fence_id}
    assert sorted(b for b in built if b != ridge_id) == sorted([bed_id, fence_id, house_id])
    assert pipeline.sink.state() == start_state
    rebuilt = [bed_id, fence_id, house_id]  # once going, once coming back — and nothing else
    extra = pipeline.sync.build_count - builds_at_start
    assert extra - sum(1 for _ in range(2) for _ in rebuilt) in (0, 1, 2)  # + the ridge item, if it has a record


# ── gate G2 on real items ────────────────────────────────────────────────────


def _ridge_in_scene(held: Any, height: float) -> np.ndarray:
    """The plan points of the mesh's top line (the ridge tile's apex), posed in the scene."""
    roof = next(part for part in held.parts if part.name == "roof")
    posed = pose_points(held.transform, roof.mesh.positions)
    top = posed[roof.mesh.positions[:, 2] == np.float32(height)][:, :2]
    return np.unique(np.round(top, 3), axis=0)


def _expected_live_ridge(house: PolygonItem, ridge: PolylineItem, overhang: float) -> np.ndarray:
    """The LIVE ridge item's two ends in the scene, each run on to the roof's edge:
    ``overhang / cos θ`` along the ridge, θ between the ridge and the outward normal
    of the wall it ends on — computed here from the canvas items alone."""
    points = ridge.points
    ends = [np.array([p.x(), p.y()]) for p in (ridge.mapToScene(points[0]), ridge.mapToScene(points[-1]))]
    along = (ends[1] - ends[0]) / np.linalg.norm(ends[1] - ends[0])
    (footprint,) = item_footprints(house)
    outline = np.asarray(footprint)
    out = []
    for end, direction in ((ends[0], -along), (ends[1], along)):
        best, cos_theta = math.inf, 1.0
        for a, b in zip(outline, np.roll(outline, -1, axis=0), strict=True):
            edge = b - a
            t = float(np.clip(((end - a) @ edge) / (edge @ edge), 0.0, 1.0))
            distance = float(np.linalg.norm(end - (a + t * edge)))
            if distance < best:
                normal = np.array([edge[1], -edge[0]]) / np.linalg.norm(edge)
                best, cos_theta = distance, abs(float(normal @ direction))
        assert best < 1e-6  # the live ridge ends ON the house's outline
        out.append(end + direction * (overhang / cos_theta))
    return np.stack(out)


FOOTPRINTS = {
    "rectangle": [(1000.0, 800.0), (1900.0, 800.0), (1900.0, 1340.0), (1000.0, 1340.0)],
    "l_shape": [(1000.0, 800.0), (1900.0, 800.0), (1900.0, 1200.0), (1450.0, 1200.0),
                (1450.0, 1400.0), (1000.0, 1400.0)],
    "trapezoid": [(1000.0, 800.0), (1800.0, 800.0), (1650.0, 1200.0), (1150.0, 1200.0)],
}


class TestRidgeIsTheLiveRidge:
    @pytest.mark.parametrize("angle", [0.0, 17.0, 90.0, 213.5])
    @pytest.mark.parametrize("shape", sorted(FOOTPRINTS))
    def test_mesh_ridge_equals_the_canvas_ridge(
        self, canvas: CanvasView, mouse_event: Any, shape: str, angle: float
    ) -> None:
        house = draw_polygon(canvas, mouse_event, ToolType.HOUSE, FOOTPRINTS[shape])
        ridge = ridge_of(canvas, house)
        apply_rotation(house, angle)  # the canvas re-derives the ridge (ADR-046)
        house.moveBy(321.7, -45.3)
        pipeline = Pipeline(canvas.scene())
        pipeline.tick()
        held = pipeline.sink.item(str(house.item_id))
        record = pipeline.sync.records[str(house.item_id)]
        assert record.transform.rotation_deg == pytest.approx(angle) and "ridge" in record.params
        line = _ridge_in_scene(held, 450.0)
        expected = _expected_live_ridge(house, ridge, buildings.HOUSE_ROOF.overhang_cm)
        assert len(line) == 2
        worst = max(float(np.linalg.norm(line - point, axis=1).min()) for point in expected)
        assert worst <= 0.1  # gate G2: one millimetre
        assert worst <= 5e-3  # measured 6.1e-4: float32 vertices a few thousand cm from the origin
        if shape != "trapezoid":  # the ridge meets these walls squarely: exactly 30 cm on
            ends = [ridge.mapToScene(p) for p in (ridge.points[0], ridge.points[-1])]
            length = math.hypot(ends[1].x() - ends[0].x(), ends[1].y() - ends[0].y())
            assert float(np.linalg.norm(line[0] - line[1])) == pytest.approx(length + 60.0, abs=5e-3)

    def test_dragging_the_ridge_changes_the_house_s_geometry_and_its_mesh(
        self, canvas: CanvasView, mouse_event: Any
    ) -> None:
        house = draw_polygon(canvas, mouse_event, ToolType.HOUSE, FOOTPRINTS["rectangle"])
        ridge = ridge_of(canvas, house)
        house_id = str(house.item_id)
        apply_rotation(house, 17.0)
        pipeline = Pipeline(canvas.scene())
        pipeline.tick()
        before = pipeline.sync.records[house_id]
        roof_before = pipeline.sink.item(house_id).parts[1].mesh

        wall_point = house.mapToScene(QPointF(1000.0, 900.0))  # 170 cm along the west wall
        old = ridge.points[0]
        canvas.command_manager.execute(
            build_move_vertex_command(ridge, 0, old, ridge.mapFromScene(wall_point)))
        result, calls, built = pipeline.tick()
        after = pipeline.sync.records[house_id]
        assert house_id in result.geometry and house_id not in result.transform
        assert before.geometry_sig != after.geometry_sig and not before.same_geometry(after)
        assert before.params["ridge"] != after.params["ridge"]
        assert ("replace_geometry", house_id) in calls and house_id in built
        held = pipeline.sink.item(house_id)
        assert held.parts[1].mesh != roof_before
        line = _ridge_in_scene(held, 450.0)
        expected = _expected_live_ridge(house, ridge, buildings.HOUSE_ROOF.overhang_cm)
        assert max(float(np.linalg.norm(line - point, axis=1).min()) for point in expected) <= 0.1
        assert pipeline.top(house_id) == 450.0  # the ridge height is still the house's height

        canvas.command_manager.undo()
        pipeline.tick()
        assert pipeline.sync.records[house_id].same_geometry(before)
        assert pipeline.sink.item(house_id).parts[1].mesh == roof_before

    @pytest.mark.parametrize("angle", [0.0, 60.0, 213.5])
    def test_the_slope_that_faces_the_sun_is_lit_on_a_turned_house(
        self, canvas: CanvasView, mouse_event: Any, angle: float
    ) -> None:
        """Normals posed by the record's transform: the slope whose outward side
        looks at the sun has the larger n·l — wherever the house is turned."""
        from open_garden_planner.core.scene3d import SunState
        from open_garden_planner.core.scene3d.frame import cos_sin

        house = draw_polygon(canvas, mouse_event, ToolType.HOUSE, FOOTPRINTS["rectangle"])
        apply_rotation(house, angle)
        pipeline = Pipeline(canvas.scene())
        pipeline.tick()
        held = pipeline.sink.item(str(house.item_id))
        mesh = held.parts[1].mesh
        tile = np.isclose(mesh.colors, np.asarray(palette.ROOF_TILE.linear, np.float32),
                          atol=1e-6).all(axis=1)
        c, s = cos_sin(held.transform.rotation_deg)
        local = mesh.normals[tile].astype(np.float64)
        posed = np.stack([c * local[:, 0] - s * local[:, 1], s * local[:, 0] + c * local[:, 1],
                          local[:, 2]], axis=1)
        # the two slopes look along ±(the ridge's left normal) in the scene
        facing = np.array([-s, c])  # local +y (north of the east-west ridge), turned
        azimuth = math.degrees(math.atan2(facing[0], facing[1])) % 360.0  # the compass bearing it faces
        sun = np.asarray(SunState(30.0, azimuth).direction_scene)
        toward = posed[posed[:, :2] @ facing > 0.1]
        away = posed[posed[:, :2] @ facing < -0.1]
        assert len(toward) and len(away)
        assert float((toward @ sun).min()) > 0.9  # square on to a 30° sun
        assert float((toward @ sun).min()) > float((away @ sun).max()) + 0.5


# ── an outline the contract had to resolve: a block, whatever its ring count ──



def _assert_the_house_block(part: Any, block: Any) -> None:
    """``part`` is the default prism ``block`` of a house: its shape, in the house's
    sandstone with a top of roof tiles (``buildings._house_walls``: a house takes no fill
    on any route)."""
    assert np.array_equal(part.mesh.positions, block.positions)
    assert np.array_equal(part.mesh.indices, block.indices)
    assert not part.tinted
    wall = np.asarray(buildings.HOUSE_WALL.linear, dtype=np.float32)
    tile = np.asarray(buildings.HOUSE_ROOF.tile.linear, dtype=np.float32)
    assert np.allclose(part.mesh.colors, block.colors * np.where(block.normals[:, 2:3] > 0.99, tile, wall))

class TestAResolvedOutlineGetsNoRoof:
    """Round 1's open point, closed by the contract's flag (merge of 9944012): a HOUSE
    drawn crossing itself can resolve to ONE plain ring, and then nothing but
    ``params["outline_resolved"]`` tells it from an ordinary house."""

    #: The scene contract's own "one ring of ten" (``test_scene3d_snapshot.py``).
    ONE_RING = [(50.0, 400.0), (0.0, 300.0), (350.0, 100.0), (0.0, 400.0), (50.0, 0.0)]

    def test_a_self_crossing_house_that_resolves_to_one_ring_is_a_block(
        self, canvas: CanvasView
    ) -> None:
        scene = canvas.scene()
        house = PolygonItem([QPointF(1000.0 + x, 800.0 + y) for x, y in self.ONE_RING],
                            object_type=ObjectType.HOUSE)
        ridge = PolylineItem([QPointF(1000.0, 1000.0), QPointF(1350.0, 1000.0)],
                             object_type=ObjectType.ROOF_RIDGE)
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        scene.addItem(house)
        scene.addItem(ridge)
        skipped: list[SkippedItem] = []
        records = snapshot_records(scene, skipped=skipped)
        record = records[str(house.item_id)]
        assert skipped == [] and list(records) == [str(house.item_id)]
        # ONE ring without a hole: the count says nothing …
        assert len(record.footprints) == 1 and record.holes == () and len(record.footprints[0]) == 10
        # … the record does, and the ridge drawn for the DRAWN outline is not handed on
        assert record.params.get("outline_resolved") is True and "ridge" not in record.params

        registry = production_registry()
        builder = registry.builder_for("HOUSE")
        parts = verify_builder(builder, record, height_tolerance_cm=0.5, plan_margin_cm=0.0,
                               hole_cover_limit=0.0)
        assert [part.name for part in parts] == ["prism"]             # no walls + roof
        _assert_the_house_block(parts[0], prism_mesh(record.footprints, record.height_cm,
                                                 record.holes))  # the regions, as a block
        assert float(parts[0].mesh.positions[:, 2].max()) == float(np.float32(record.height_cm))

        # It is the FLAG that decides — not the missing ridge. Hand the builder a ridge it
        # could use (a line through the middle of the ring): still the block. Take the flag
        # away and the very same ring gets a gable roof — what round 1 built.
        usable = ((-150.0, 0.0), (150.0, 0.0))
        with_ridge = dataclasses.replace(record, params=Params({**record.params, "ridge": usable}))
        assert [part.name for part in registry.build(with_ridge)] == ["prism"]
        unflagged = dataclasses.replace(with_ridge, params=Params(
            {key: value for key, value in with_ridge.params.items() if key != "outline_resolved"}))
        assert [part.name for part in registry.build(unflagged)] == ["walls", "roof", "facade", "floor"]

        sink = RecordingSink()
        sync = SceneSync(sink, registry, validate=True)
        sync.apply(records)
        assert sync.failures == {}
        assert [part.name for part in sink.item(record.item_id).parts] == ["prism"]


# ── the committed edge-case plan (L1.1's fix) through the production builders ─


EDGE_PLAN = Path(__file__).resolve().parents[1] / "fixtures" / "plans" / "scene3d_edge_cases.ogp"


@pytest.fixture
def edge_plan(qtbot: Any) -> tuple[CanvasScene, dict[str, Record]]:  # noqa: ARG001
    scene = CanvasScene()
    ProjectManager().load(scene, EDGE_PLAN)
    skipped: list[SkippedItem] = []
    records = snapshot_records(scene, skipped=skipped)
    assert skipped == []
    return scene, records


def _named(records: dict[str, Record], name: str) -> Record:
    (record,) = [r for r in records.values() if r.name == name]
    return record


class TestTheEdgeCasePlan:
    """``scene3d_edge_cases.ogp`` holds what the bench plans lack: a turned house with
    its ridge, a closed, a nearly closed and an open fence, a turned raised bed with
    plants, a pot with a plant, a concave hedge — and, since the contract's second
    fix round (merge of 9944012), a house drawn crossing itself, a ladder of a fence
    whose stroke has four holes, and a fence that stops 6 cm short of closing; since
    its third (merge of f3ed56f), a fence whose butt ends meet corner to corner. The
    production builders and the base rule over all of it."""

    def test_every_built_world_item_passes_the_gate(self, edge_plan) -> None:
        _scene, records = edge_plan
        registry = production_registry()
        built_kinds = []
        for record in records.values():
            if record.kind not in BUILT_WORLD_KINDS:
                continue
            parts = verify_builder(registry.builder_for(record.kind), record, height_tolerance_cm=0.5)
            assert parts and record.height_cm is not None, record.name
            top = max(float(part.mesh.positions[:, 2].max()) for part in parts)
            assert top == float(np.float32(record.height_cm)), record.name
            assert min(float(part.mesh.positions[:, 2].min()) for part in parts) == 0.0
            built_kinds.append(record.kind)
        assert sorted(built_kinds) == ["CONTAINER_ROUND", *["FENCE"] * 6, "HEDGE_POLYGON",
                                       "HOUSE", "HOUSE", "RAISED_BED"]
        assert len(records) == 15  # 17 items; the two ridges have no record
        sync = SceneSync(RecordingSink(), registry, validate=True)
        sync.apply(records)
        assert sync.failures == {}

    def test_the_crossed_house_is_the_block_of_its_regions(self, edge_plan) -> None:
        """A HOUSE drawn crossing itself, with a ridge item: the contract resolves the
        outline (three rings here), says so, and hands on no ridge. The house builder
        builds the regions as ONE block — no roof on a part of it, no ring dropped."""
        scene, records = edge_plan
        crossed, house = _named(records, "Crossed house"), _named(records, "House")
        assert crossed.params.get("outline_resolved") is True and "ridge" not in crossed.params
        assert len(crossed.footprints) == 3 and crossed.holes == ()
        assert "outline_resolved" not in house.params and "ridge" in house.params
        item = next(i for i in scene.items() if str(getattr(i, "item_id", "")) == crossed.item_id)
        assert item.metadata.get("ridge_item_id")  # the plan DOES hold a ridge for it
        registry = production_registry()
        parts = verify_builder(registry.builder_for("HOUSE"), crossed, height_tolerance_cm=0.5,
                               plan_margin_cm=0.0, hole_cover_limit=0.0)
        assert [part.name for part in parts] == ["prism"]
        _assert_the_house_block(parts[0], prism_mesh(crossed.footprints, crossed.height_cm,
                                                 crossed.holes))
        assert float(parts[0].mesh.positions[:, 2].max()) == 450.0 == crossed.height_cm
        beyond_cm2, _cover = plan_overreach(parts, crossed.regions, 0.0)
        assert beyond_cm2 == 0.0
        assert [part.name for part in registry.build(house)] == ["walls", "roof", "facade", "floor"]  # the other one

    def test_the_ladder_and_the_gap(self, edge_plan) -> None:
        """Two more fences of the contract's second round: a stroke with FOUR holes
        (each cell of the ladder 140 x 140 cm of garden) and one that stops 6 cm short
        of closing at a corner — its 10 cm stroke does not bridge that, so it has no
        hole. Both are built from the centre line: posts, rails and pickets on the
        stroke, the cells open."""
        _scene, records = edge_plan
        registry = production_registry()
        ladder, gap = _named(records, "Ladder fence"), _named(records, "Fence with a gap")
        assert [len(group) for group in ladder.holes] == [4] and len(ladder.footprints) == 1
        assert gap.holes == () and len(gap.footprints) == 1
        for record in (ladder, gap):
            parts = verify_builder(registry.builder_for("FENCE"), record, height_tolerance_cm=0.5)
            assert [part.name for part in parts] == ["fence"]  # no style: the default fence
            beyond_cm2, hole_cover = plan_overreach(parts, record.regions, 50.0)
            assert beyond_cm2 == 0.0 and hole_cover <= 0.01, (record.name, hole_cover)
            assert sum(part.mesh.triangle_count for part in parts) <= lines.triangle_budget(record)

    def test_the_fences_enclose_nothing(self, edge_plan) -> None:
        """A fence drawn round 80 m² of garden is 36 m of fence in 3D: nothing over the
        hole its stroke encloses, closed or 2 cm short of closed."""
        _scene, records = edge_plan
        registry = production_registry()
        closed, nearly, open_u = (_named(records, name) for name in
                                  ("Closed fence", "Nearly closed fence", "Open U fence"))
        assert closed.holes != () and nearly.holes != () and open_u.holes == ()
        for record in (closed, nearly, open_u):
            parts = registry.build(record)
            assert [part.name for part in parts] == ["fence"]  # no style: the default fence
            beyond_cm2, hole_cover = plan_overreach(parts, record.regions, 50.0)
            assert beyond_cm2 == 0.0 and hole_cover <= 0.01, (record.name, hole_cover)
            plan = np.concatenate([part.mesh.positions[:, :2] for part in parts]).astype(np.float64)
            path = np.asarray(record.path)
            start, end = path[:-1], path[1:]
            step = end - start
            t = np.clip(((plan[:, None, :] - start[None]) * step[None]).sum(-1) / (step * step).sum(-1), 0, 1)
            away = np.linalg.norm(plan[:, None, :] - (start[None] + t[..., None] * step[None]), axis=2).min(axis=1)
            # the posts are as wide as the 10 cm stroke: no vertex beyond their half diagonal
            assert float(away.max()) <= 10.0 / 2.0 * math.sqrt(2.0) + 1e-3

    def test_plants_stand_on_the_turned_bed_and_in_the_pot(self, edge_plan) -> None:
        scene, records = edge_plan
        bed, pot = _named(records, "Turned raised bed"), _named(records, "Pot")
        assert bed.transform.rotation_deg == 30.0 and (bed.height_cm, pot.height_cm) == (40.0, 30.0)
        in_bed = [r for r in records.values() if r.parent_id == bed.item_id]
        (in_pot,) = [r for r in records.values() if r.parent_id == pot.item_id]
        assert len(in_bed) == 2
        assert [r.transform.base_cm for r in in_bed] == [38.0, 38.0]  # 2 cm under the bed's rim
        assert in_pot.transform.base_cm == 30.0                       # AT the pot's fill height
        # … where the bed's and the pot's meshes have their soil
        registry = production_registry()
        soil = np.asarray(palette.SOIL.linear, dtype=np.float32)
        for parent, level in ((bed, 38.0), (pot, 30.0)):
            for part in registry.build(parent):
                mine = np.isclose(part.mesh.colors, soil, atol=1e-6).all(axis=1)
                if mine.any():
                    assert float(part.mesh.positions[mine][:, 2].max()) == level
        # the 2D casters carry the same bases, and nothing else is raised
        casters = collect_shadow_casters(scene)
        assert sorted(c.base_cm for c in casters if c.base_cm > 0.0) == [30.0, 38.0, 38.0]
        assert sum(1 for r in records.values() if r.transform.base_cm > 0.0) == 3

    def test_the_turned_house_has_its_roof_on_the_live_ridge(self, edge_plan) -> None:
        scene, records = edge_plan
        house_record = _named(records, "House")
        assert house_record.transform.rotation_deg == 25.0 and len(house_record.footprints) == 1
        items = {str(i.item_id): i for i in scene.items() if hasattr(i, "item_id")}
        house = items[house_record.item_id]
        ridge = items[str(house.metadata["ridge_item_id"])]
        assert str(ridge.item_id) not in records  # a ridge has no record: it is the house's param
        sink = RecordingSink()
        SceneSync(sink, production_registry(), validate=True).apply(records)
        held = sink.item(house_record.item_id)
        assert [part.name for part in held.parts] == ["walls", "roof", "facade", "floor"]
        line = _ridge_in_scene(held, float(house_record.height_cm or 0.0))
        expected = _expected_live_ridge(house, ridge, buildings.HOUSE_ROOF.overhang_cm)
        worst = max(float(np.linalg.norm(line - point, axis=1).min()) for point in expected)
        assert len(line) == 2 and worst <= 0.1  # gate G2
