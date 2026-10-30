"""``snapshot_records`` on REAL canvas items (Phase 17 L1.1, #385).

The gates this file owns, each on a real ``CanvasScene`` with real items driven
through the app's own commands (``MoveItemsCommand``, ``RotateItemCommand`` +
``apply_rotation``, ``ResizeItemCommand`` + ``apply_rect_like_geometry``,
``build_move_vertex_command`` — the paths the GUI and the Agent API share):

- G1 — the diff matrix over every footprint shape: move → transform only,
  rotate → transform only, recolour → material only, resize / height / vertex
  edit / a plant growing with the date → geometry, select / hover / rename →
  empty, add / remove → added / removed.
- G4 — ``transform ∘ local footprint`` reproduces ``item_footprints`` to
  ≤ 1e-6 cm for every shape x rotation x position (a polyline's stroke polygon
  only to pyclipper's 1/1000 cm grid — see ``TestTransformReproducesFootprint``).
- G7 — every mesh the default builder emits for these shapes validates, and a
  prism's top is exactly the resolved height.
- G8 — an unchanged scene snapshots identically, 100 times, on both bench plans.

Fix round 1 added what the first matrix did not contain and therefore could not
catch: a stroke that closes on itself (outer ring + hole), a polygon that crosses
itself, an item whose metadata is malformed, two items with one id, and a house
with its ridge item — plus G4, G7 and G8 over a third committed plan made of
exactly those cases (``scene3d_edge_cases.ogp``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsItemGroup

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
    RotateItemCommand,
)
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.object_height import METADATA_KEY, effective_height_cm, lies_on_ground
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.scene3d import (
    SHAPES,
    Material,
    Mesh,
    MeshPart,
    Paint,
    Params,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    Transform,
    default_builder,
    diff,
    is_buildable_region,
    is_simple_ring,
    point_in_regions,
    pose_ring,
    prism_mesh,
    regions_area,
    signed_area,
    verify_builder,
)
from open_garden_planner.core.stacking import ArrangeMode
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.ui.canvas.arrange import build_arrange_command
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.footprints import (
    OUTLINE_SHAPES,
    item_footprints,
    item_outline,
)
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_circle_resize,
    build_ellipse_resize,
    build_move_vertex_command,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d import snapshot as snapshot_module
from open_garden_planner.ui.view3d.snapshot import (
    SkippedItem,
    SkipReason,
    snapshot_records,
)

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
ROTATIONS = [0.0, 17.0, 90.0, 213.5]
POSITIONS = [(0.0, 0.0), (137.25, -42.5)]
JUNE = date(2026, 6, 21)
SPECIES = {
    "common_name": "Apple tree", "scientific_name": "Malus domestica",
    "min_height_cm": 100.0, "max_height_cm": 500.0,
    "min_spread_cm": 50.0, "max_spread_cm": 400.0,
}


def snapshot_with_report(scene: Any, at_date: date | None = None,
                         ) -> tuple[dict[str, Record], list[SkippedItem]]:
    """A snapshot and what it had to leave out — ``snapshot_records``'s optional
    ``skipped`` out-parameter, as a pair."""
    skipped: list[SkippedItem] = []
    return snapshot_records(scene, at_date, skipped=skipped), skipped


# ── the six footprint shapes of the gate ──────────────────────────────────────


def _circle() -> Any:
    return CircleItem(310.5, 220.25, 75.0, object_type=ObjectType.TRAMPOLINE)


def _ellipse() -> Any:
    return EllipseItem(120.5, 80.25, 260.0, 110.5, object_type=ObjectType.POND_POOL)


def _rectangle() -> Any:
    return RectangleItem(100.3, 50.7, 240.0, 130.5, object_type=ObjectType.TOOL_SHED)


def _polygon() -> Any:
    # concave L; vertex 3 is the reflex corner, inside the bounding box
    vertices = [QPointF(200.0, 100.0), QPointF(520.5, 100.0), QPointF(520.5, 260.25),
                QPointF(360.0, 260.25), QPointF(360.0, 410.0), QPointF(200.0, 410.0)]
    return PolygonItem(vertices, object_type=ObjectType.HEDGE_POLYGON)


def _polyline() -> Any:
    # vertex 1 lies inside the bounding box of the other three
    points = [QPointF(100.0, 100.0), QPointF(250.5, 180.25), QPointF(430.0, 380.0),
              QPointF(180.75, 300.0)]
    item = PolylineItem(points, object_type=ObjectType.WALL)
    pen = item.pen()
    pen.setWidthF(24.5)
    adopt_pen(item, pen)
    return item


def _plant() -> Any:
    item = CircleItem(640.0, 480.5, 100.0, object_type=ObjectType.TREE)
    item.metadata["plant_species"] = dict(SPECIES)
    item.metadata["plant_instance"] = {"planting_date": "2026-01-01",
                                       "current_height_cm": 100.0, "current_spread_cm": 50.0}
    return item


FACTORIES: dict[str, Callable[[], Any]] = {
    "circle": _circle, "ellipse": _ellipse, "rectangle": _rectangle,
    "polygon": _polygon, "polyline": _polyline, "plant": _plant,
}
SHAPE_NAMES = sorted(FACTORIES)
ROUND = {"circle", "plant"}
RECT_BACKED = {"ellipse", "rectangle"}
VERTEX_BACKED = {"polygon", "polyline"}


class Stage:
    """A real view + scene with one item of the shape under test and a bystander."""

    def __init__(self, view: CanvasView, shape: str) -> None:
        self.view = view
        self.scene: CanvasScene = view.scene()  # type: ignore[assignment]
        self.commands = view.command_manager
        self.shape = shape
        self.item = FACTORIES[shape]()
        # a bystander in the item's own z band: a ground surface (the pond) lies under
        # every solid whatever its rank (manual pass of PR #584, GROUND_Z_RANGE)
        ground = lies_on_ground(self.item.object_type, self.item.metadata)
        self.bystander = RectangleItem(2000.0, 1500.0, 100.0, 100.0,
                                       object_type=ObjectType.LAWN if ground
                                       else ObjectType.RAISED_BED)
        for item, label in ((self.bystander, "rectangle"), (self.item, shape)):
            item.layer_id = self.scene.active_layer.id  # what every drawing tool does
            self.commands.execute(CreateItemCommand(self.scene, item, label))
        self.id = str(self.item.item_id)
        self.at: date | None = JUNE if shape == "plant" else None
        self.last = self.snapshot()

    def snapshot(self) -> dict[str, Record]:
        return snapshot_records(self.scene, self.at)

    def step(self) -> SceneDiff:
        """Snapshot again and diff against the previous snapshot."""
        new = self.snapshot()
        result = diff(self.last, new)
        self.last = new
        return result

    @property
    def record(self) -> Record:
        return self.last[self.id]


def _stage_fixture(shapes: set[str]) -> Any:
    """A ``Stage`` fixture parametrised over the shapes an edit applies to — the
    matrix names exactly its cells, with no skipped ones."""
    @pytest.fixture(params=sorted(shapes))
    def fixture(request: pytest.FixtureRequest, canvas: CanvasView) -> Stage:
        return Stage(canvas, request.param)

    return fixture


stage = _stage_fixture(set(FACTORIES))  # every footprint shape
resizable_stage = _stage_fixture(ROUND | RECT_BACKED)  # resized through a rect
rect_stage = _stage_fixture(RECT_BACKED)  # can keep a corner fixed
vertex_stage = _stage_fixture(VERTEX_BACKED)  # edited vertex by vertex
undated_stage = _stage_fixture(set(FACTORIES) - {"plant"})  # the date does not reach them


def _recolour(item: Any, color: QColor) -> ChangePropertyCommand:
    """The properties panel's fill-colour edit (``_on_color_changed``)."""
    def apply(target: Any, value: QColor) -> None:
        target.fill_color = value
        target.setBrush(create_pattern_brush(target.fill_pattern, value))

    return ChangePropertyCommand(item, "fill color", QColor(item.fill_color), color, apply)


def _restroke(item: Any, color: QColor) -> ChangePropertyCommand:
    """The properties panel's stroke-colour edit."""
    def apply(target: Any, value: QColor) -> None:
        target.stroke_color = value
        pen = target.pen()
        pen.setColor(value)
        adopt_pen(target, pen)

    return ChangePropertyCommand(item, "stroke color", QColor(item.pen().color()), color, apply)


def _resize_command(item: Any, shape: str, *, keep_center: bool, factor: float = 1.5) -> ResizeItemCommand:
    rect = item.rect()
    if shape in ROUND:
        old, new = build_circle_resize(item, rect.width() * factor, keep_center=keep_center)
    elif shape == "ellipse":
        old, new = build_ellipse_resize(item, rect.width() * factor, rect.height() * 0.8,
                                        keep_center=keep_center)
    else:
        old, new = build_rect_resize(item, rect.width() * factor, rect.height() * 0.8,
                                     keep_center=keep_center)
    return ResizeItemCommand(item, old, new, apply_rect_like_geometry)


def _solid(parts: tuple[MeshPart, ...]) -> MeshPart:
    """A builder's parts as one part: the default solid is two Models (#627: tinted
    sides and a fill cap), and these tests ask the SOLID - its outline, its cap
    area, its height. Merging them changes neither the winding nor the bounds."""
    return MeshPart(Mesh.merge([part.mesh for part in parts]), "vc")


# ── G1: the diff matrix ───────────────────────────────────────────────────────


class TestDiffMatrix:
    def test_move_is_transform_only(self, stage: Stage) -> None:
        before = stage.record
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(137.25, -42.5)))
        assert stage.step() == SceneDiff(transform=(stage.id,))
        after = stage.record
        assert after.transform.east_cm == pytest.approx(before.transform.east_cm + 137.25, abs=1e-6)
        assert after.transform.north_cm == pytest.approx(before.transform.north_cm - 42.5, abs=1e-6)
        assert after.transform.rotation_deg == before.transform.rotation_deg
        assert after.footprints == before.footprints and after.path == before.path

    def test_undo_of_a_move_restores_the_very_same_record(self, stage: Stage) -> None:
        before = stage.record
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(137.25, -42.5)))
        stage.step()
        stage.commands.undo()
        assert stage.step() == SceneDiff(transform=(stage.id,))
        assert stage.record == before

    def test_undo_dust_near_the_origin_is_absorbed_by_the_record_grid(self, canvas: CanvasView) -> None:
        """Undo is ``moveBy(-delta)``, and ``(p + d) - d`` is not always ``p``:
        ``(0.1 + 0.7) - 0.7 == 0.09999999999999998``. Far from the origin that dust
        is below one ulp of the scene position and vanishes by itself; next to the
        origin it survives into ``sceneTransform()``. On the record grid both paths
        give ONE position, so undo returns the very record it left."""
        item = RectangleItem(-0.7, -0.8, 2.0, 2.0, object_type=ObjectType.TOOL_SHED)  # centre (0.3, 0.2)
        commands = canvas.command_manager
        commands.execute(CreateItemCommand(canvas.scene(), item, "rectangle"))
        commands.execute(MoveItemsCommand([item], QPointF(0.1, 0.3)))
        before = snapshot_records(canvas.scene())
        raw_before = item.mapToScene(item.rect().center())
        commands.execute(MoveItemsCommand([item], QPointF(0.7, 0.9)))
        commands.undo()
        raw_after = item.mapToScene(item.rect().center())
        assert (raw_after.x(), raw_after.y()) != (raw_before.x(), raw_before.y())  # the dust is real
        after = snapshot_records(canvas.scene())
        assert after == before and diff(before, after).is_empty

    @pytest.mark.parametrize("angle", [17.0, 90.0, 213.5])
    def test_rotate_is_transform_only(self, stage: Stage, angle: float) -> None:
        before = stage.record
        stage.commands.execute(RotateItemCommand(stage.item, 0.0, angle, apply_rotation))
        result = stage.step()
        assert result.geometry == ()
        assert result.added == () and result.removed == () and not result.reordered
        after = stage.record
        assert after.footprints == before.footprints and after.path == before.path
        if stage.shape == "plant":
            # A circle's footprint does not turn with its item (`item_footprints`
            # polygonises it around the mapped centre), so its record keeps rotation
            # 0 — and a turn about its own centre, which is the app's rotation
            # gesture, changes nothing at all: "transform only" with nothing in it.
            assert result == SceneDiff()
            assert after == before
        elif stage.shape == "circle":
            # … for a circle the canvas PAINTS, one thing does turn: what is painted in
            # its coordinates — a fill texture, a dash pattern, a sprite (the ground
            # bake, L1.5). That turn is a fact of its PAINT: a material change, which
            # no builder sees. Geometry and transform are what they were — the solid
            # of a circle does not turn.
            assert result == SceneDiff(material=(stage.id,))
            assert after.transform == before.transform and after.transform.rotation_deg == 0.0
            assert after.same_geometry(before) and after.params == before.params
            assert before.material.paint is not None and after.material.paint is not None
            assert before.material.paint.rotation_deg == 0.0
            assert after.material.paint.rotation_deg == angle
        else:
            assert result == SceneDiff(transform=(stage.id,))
            assert after.transform.rotation_deg == angle
            assert after.material == before.material

    def test_a_rotated_item_still_moves_as_transform_only(self, stage: Stage) -> None:
        stage.commands.execute(RotateItemCommand(stage.item, 0.0, 213.5, apply_rotation))
        stage.step()
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(-300.5, 80.0)))
        assert stage.step() == SceneDiff(transform=(stage.id,))

    def test_recolour_is_material_only(self, stage: Stage) -> None:
        before = stage.record
        if stage.shape == "polyline":  # a line has no fill: its colour is the stroke
            stage.commands.execute(_restroke(stage.item, QColor(10, 200, 30)))
        else:
            stage.commands.execute(_recolour(stage.item, QColor(10, 200, 30)))
        assert stage.step() == SceneDiff(material=(stage.id,))
        assert stage.record.material.tint_rgba == (10, 200, 30, 255)
        assert stage.record.geometry_sig == before.geometry_sig
        stage.commands.undo()
        assert stage.step() == SceneDiff(material=(stage.id,))
        assert stage.record == before

    def test_height_change_is_geometry_only(self, stage: Stage) -> None:
        stage.item.metadata[METADATA_KEY] = 321.5
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        assert stage.record.height_cm == 321.5
        del stage.item.metadata[METADATA_KEY]
        assert stage.step() == SceneDiff(geometry=(stage.id,))

    def test_centred_resize_is_geometry_only(self, resizable_stage: Stage) -> None:
        stage = resizable_stage
        before = stage.record
        stage.commands.execute(_resize_command(stage.item, stage.shape, keep_center=True))
        if stage.shape == "plant":
            # A MEASURED plant's footprint is its canopy (`plant_canopy_radius_cm`),
            # not the drawn circle — as in the 2D shadow. Resizing the circle the
            # user drew changes neither, so nothing reaches the engine.
            assert stage.step().is_empty
            assert stage.record == before
            return
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        assert stage.record.transform == before.transform
        assert stage.record.footprints != before.footprints
        stage.commands.undo()
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        assert stage.record == before

    @pytest.mark.parametrize("angle", [0.0, 213.5])
    def test_one_sided_resize_also_moves_the_centre(self, rect_stage: Stage, angle: float) -> None:
        """The record frame hangs on the item's centre. A resize that keeps a corner
        fixed moves that centre, so it is geometry AND transform — never material,
        and both are exactly what happened."""
        stage = rect_stage
        stage.commands.execute(RotateItemCommand(stage.item, 0.0, angle, apply_rotation))
        stage.step()
        stage.commands.execute(_resize_command(stage.item, stage.shape, keep_center=False))
        assert stage.step() == SceneDiff(geometry=(stage.id,), transform=(stage.id,))

    def test_stroke_width_changes_a_polyline_s_geometry(self, canvas: CanvasView) -> None:
        stage = Stage(canvas, "polyline")  # only a polyline's footprint depends on its stroke
        pen = stage.item.pen()
        pen.setWidthF(40.0)
        adopt_pen(stage.item, pen)
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        assert stage.record.path_width_cm == 40.0

    def test_interior_vertex_edit_is_geometry_only(self, vertex_stage: Stage) -> None:
        stage = vertex_stage
        index = 3 if stage.shape == "polygon" else 1
        old = QPointF(stage.item._get_vertex_position(index))
        new = QPointF(old.x() + 12.5, old.y() - 7.25)  # stays inside the bounding box
        before = stage.record
        stage.commands.execute(build_move_vertex_command(stage.item, index, old, new))
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        stage.commands.undo()
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        assert stage.record == before

    def test_extreme_vertex_edit_also_moves_the_centre(self, vertex_stage: Stage) -> None:
        stage = vertex_stage
        old = QPointF(stage.item._get_vertex_position(0))
        new = QPointF(old.x() - 60.0, old.y() - 30.0)  # grows the bounding box
        stage.commands.execute(build_move_vertex_command(stage.item, 0, old, new))
        assert stage.step() == SceneDiff(geometry=(stage.id,), transform=(stage.id,))

    def test_a_plant_growing_with_the_date_is_geometry_only(self, canvas: CanvasView) -> None:
        stage = Stage(canvas, "plant")
        young = stage.record
        stage.at = date(2040, 1, 1)
        assert stage.step() == SceneDiff(geometry=(stage.id,))
        grown = stage.record
        assert grown.height_cm == 500.0 and young.height_cm < 500.0  # type: ignore[operator]
        assert grown.params["radius_cm"] == 200.0 > young.params["radius_cm"]  # type: ignore[operator]
        assert grown.transform == young.transform

    def test_the_date_changes_nothing_but_dated_plants(self, undated_stage: Stage) -> None:
        undated_stage.at = date(2040, 1, 1)
        assert undated_stage.step().is_empty

    def test_select_deselect_hover_and_rename_give_an_empty_diff(self, stage: Stage) -> None:
        stage.item.setSelected(True)  # handles, annotations and labels appear as child items
        assert stage.step().is_empty
        # A REAL hover, through the view's event pipeline: over the item itself and
        # over one of its handles (which highlights — proof the hover arrived).
        view = stage.view
        view.resize(900, 600)
        view.show()
        QTest.qWaitForWindowExposed(view)
        stage.item.setAcceptHoverEvents(True)
        handle = next(c for c in stage.item.childItems() if c.acceptHoverEvents())
        idle = QColor(handle.brush().color())
        centre = stage.item.sceneBoundingRect().center()
        view.centerOn(centre)
        for target in (centre, handle.scenePos()):
            spot = view.mapFromScene(target)
            QTest.mouseMove(view.viewport(), spot + QPoint(30, 30))  # approach, then enter
            QTest.mouseMove(view.viewport(), spot)
            QApplication.processEvents()
            assert stage.step().is_empty
        assert handle.brush().color() != idle
        stage.item.setSelected(False)
        assert stage.step().is_empty
        named = stage.snapshot()
        stage.item.name = "Renamed"
        assert stage.step().is_empty
        assert stage.record.name == "Renamed" and stage.record != named[stage.id]

    def test_add_and_remove(self, stage: Stage) -> None:
        stage.commands.execute(DeleteItemsCommand(stage.scene, [stage.item]))
        assert stage.step() == SceneDiff(removed=(stage.id,))
        stage.commands.undo()
        assert stage.step() == SceneDiff(added=(stage.id,))
        stage.commands.redo()
        assert stage.step() == SceneDiff(removed=(stage.id,))

    def test_hiding_removes_and_showing_adds(self, stage: Stage) -> None:
        stage.item.setVisible(False)
        assert stage.step() == SceneDiff(removed=(stage.id,))
        stage.item.setVisible(True)
        assert stage.step() == SceneDiff(added=(stage.id,))

    def test_arrange_is_a_reorder_never_a_geometry_change(self, stage: Stage) -> None:
        assert list(stage.last) == [str(stage.bystander.item_id), stage.id]  # bottom to top
        command, _outcome = build_arrange_command(stage.scene, [stage.item], ArrangeMode.SEND_TO_BACK)
        assert command is not None
        stage.commands.execute(command)
        result = stage.step()
        assert result == SceneDiff(reordered=True) and not result.touches_sink
        assert list(stage.last) == [stage.id, str(stage.bystander.item_id)]

    def test_the_bystander_never_changes(self, stage: Stage) -> None:
        bystander = str(stage.bystander.item_id)
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(5.0, 5.0)))
        stage.commands.execute(RotateItemCommand(stage.item, 0.0, 33.0, apply_rotation))
        stage.item.metadata[METADATA_KEY] = 77.0
        assert bystander not in stage.step().changed


# ── G4: transform ∘ local footprint == the 2D footprint ───────────────────────


def _boundary_distance(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Largest distance from a vertex of ``a`` to the boundary of polygon ``b``."""
    def to_segment(p: tuple[float, float], s: tuple[float, float], e: tuple[float, float]) -> float:
        dx, dy = e[0] - s[0], e[1] - s[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - s[0]) * dx + (p[1] - s[1]) * dy) / length2))
        return math.hypot(p[0] - (s[0] + t * dx), p[1] - (s[1] + t * dy))

    return max(min(to_segment(p, b[i], b[(i + 1) % len(b)]) for i in range(len(b))) for p in a)


def _rings_of(record: Record) -> list[tuple[tuple[float, float], ...]]:
    """Every ring of a record — outers, then the holes of each — in the scene."""
    rings = list(record.footprints) + [hole for group in record.holes for hole in group]
    return [pose_ring(record.transform, ring) for ring in rings]


def _ring_deviation(posed: Any, expected: Any) -> float:
    """Largest vertex-to-vertex distance between two rings with the same vertices.
    A record's outer ring is counter-clockwise; ``item_footprints`` hands a ring
    out as Qt mapped it, so a mirrored item's comes the other way round — the
    same ring, read backwards."""
    assert len(posed) == len(expected)

    def worst(other: Any) -> float:
        return max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(posed, other, strict=True))

    return min(worst(list(expected)), worst(list(expected)[::-1]))


def _strip_deviation(posed: list[Any], expected: list[Any]) -> float:
    """Largest boundary-to-boundary distance between two sets of stroke rings,
    each ring of one matched with the nearest ring of the other."""
    assert len(posed) == len(expected) >= 1
    return max(
        min(max(_boundary_distance(list(p), list(e)), _boundary_distance(list(e), list(p)))
            for p in posed)
        for e in expected
    )


def _signed_area_sum(rings: Any) -> float:
    """The area a set of pyclipper rings encloses: outers count positive, holes
    negative — the even-odd reading of ``item_footprints`` for a stroke."""
    return sum(signed_area(tuple(ring)) for ring in rings)


def _cap_area(mesh: Any) -> float:
    """Signed plan area of a prism's cap (its horizontal triangles)."""
    p = mesh.positions.astype(np.float64)
    a, b, c = (p[mesh.indices[:, k]] for k in range(3))
    flat = (a[:, 2] == b[:, 2]) & (a[:, 2] == c[:, 2])
    twice = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    return float(twice[flat].sum() / 2.0)


def _assert_walls_face_away_from_the_solid(mesh: Any, record: Record) -> None:
    """Step 0.1 mm along each wall triangle's normal from its centroid: that point
    is OUTSIDE the footprint (in the open, or in a hole), and the same step back
    is inside it. The inside-out wall of a hole extruded as a solid fails here.
    (0.1 mm: far above float32 at these coordinates, far below any slit a stroke
    leaves — a 1 cm step jumps the 5 mm gap of a nearly closed 3 cm fence.)"""
    p = mesh.positions.astype(np.float64)
    walls = 0
    for i0, i1, i2 in mesh.indices:
        normal = mesh.normals[i0].astype(np.float64) * 0.01
        if abs(normal[2]) > 0.005:
            continue
        centre = (p[i0] + p[i1] + p[i2]) / 3.0
        assert not point_in_regions(centre[0] + normal[0], centre[1] + normal[1], record.regions)
        assert point_in_regions(centre[0] - normal[0], centre[1] - normal[1], record.regions)
        walls += 1
    assert walls > 0


def _place(item: Any, shape: str, rotation: float, position: tuple[float, float], how: str) -> None:
    if how == "app":  # the rotation gesture's own pivot rule
        apply_rotation(item, rotation)
    else:  # a pivot that is NOT the item's centre: the transform must still be Qt's answer
        item.setTransformOriginPoint(QPointF(33.0, -71.5))
        item.setRotation(rotation)
    item.setPos(position[0], position[1])


class TestTransformReproducesFootprint:
    """Decision 2 of the story, proven against Qt instead of assumed:
    ``scene = T + R(θ)·local`` with θ counter-clockwise seen from above.

    The measured worst deviation over the whole matrix is ~1.5e-7 cm (the record
    grid). ONE thing cannot meet 1e-6: a polyline's stroke POLYGON. The 2D code
    inflates the centre line in scene space on pyclipper's 1/1000 cm integer
    grid; the record inflates it in the item-local frame (or a move would change
    the polygon, and "move → transform only" would be false). The two differ by
    that grid — under 0.003 cm, 30 µm — while the polyline's centre line, which
    is what fences and walls are built from, agrees to 1e-6 like everything else.
    """

    @staticmethod
    def _measure(canvas: CanvasView, shape: str, rotation: float,
                 position: tuple[float, float], how: str) -> tuple[Record, float, float]:
        """(record, exact deviation in cm, polyline strip deviation in cm or 0.0).

        The exact deviation compares vertex by vertex: every ring of a
        non-polyline, the centre line of a polyline. The strip deviation is the
        largest boundary-to-boundary distance between the two stroke polygons —
        over every ring, holes included.
        """
        item = FACTORIES[shape]()
        canvas.scene().addItem(item)
        _place(item, shape, rotation, position, how)
        at = JUNE if shape == "plant" else None
        record = snapshot_records(canvas.scene(), at)[str(item.item_id)]
        expected = item_footprints(item, at)
        posed = _rings_of(record)
        assert len(posed) == len(expected) >= 1
        strip = 0.0
        if shape == "polyline":
            centre_line = [(p.x(), p.y()) for p in (item.mapToScene(q) for q in item.points)]
            exact = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in
                        zip(pose_ring(record.transform, record.path), centre_line, strict=True))
            strip = _strip_deviation(posed, expected)
        else:
            exact = max(_ring_deviation(ring, scene_ring)
                        for ring, scene_ring in zip(posed, expected, strict=True))
        canvas.scene().removeItem(item)
        return record, exact, strip

    @pytest.mark.parametrize("how", ["app", "off-centre pivot"])
    @pytest.mark.parametrize("position", POSITIONS)
    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("shape", SHAPE_NAMES)
    def test_matrix(self, canvas: CanvasView, shape: str, rotation: float,
                    position: tuple[float, float], how: str) -> None:
        record, exact, strip = self._measure(canvas, shape, rotation, position, how)
        assert exact <= 1e-6, exact
        assert strip <= 3e-3, strip
        if shape in ROUND:
            assert record.transform.rotation_deg == 0.0
        elif how == "app":
            assert record.transform.rotation_deg == rotation

    def test_measured_worst_case_is_the_record_grid(self, canvas: CanvasView) -> None:
        """The numbers the report quotes, over the whole matrix: everything compared
        vertex by vertex sits at the 1e-7 cm record grid — a fifth of the 1e-6 gate;
        only the polyline's stroke polygon is at pyclipper's grid. Upper bounds
        only: an error that turns out smaller is not a failure."""
        worst_exact, worst_strip = 0.0, 0.0
        for shape in SHAPE_NAMES:
            for rotation in ROTATIONS:
                for position in POSITIONS:
                    for how in ("app", "off-centre pivot"):
                        _record, exact, strip = self._measure(canvas, shape, rotation, position, how)
                        worst_exact, worst_strip = max(worst_exact, exact), max(worst_strip, strip)
        assert worst_exact <= 2.5e-7, worst_exact
        assert worst_strip <= 3e-3, worst_strip

    def test_rotation_sense_is_counter_clockwise_seen_from_above(self, canvas: CanvasView) -> None:
        """A rectangle turned by +90° (Qt, on the Y-up canvas): its local +x edge
        midpoint — east of the centre — ends up NORTH of the centre in the scene."""
        item = RectangleItem(0.0, 0.0, 200.0, 100.0, object_type=ObjectType.TOOL_SHED)
        canvas.scene().addItem(item)
        apply_rotation(item, 90.0)
        record = snapshot_records(canvas.scene())[str(item.item_id)]
        assert record.transform == Transform(100.0, 50.0, 90.0)
        east_edge = item.mapToScene(QPointF(200.0, 50.0))
        assert (east_edge.x(), east_edge.y()) == pytest.approx((100.0, 150.0), abs=1e-9)
        assert pose_ring(record.transform, [(100.0, 0.0)])[0] == pytest.approx((100.0, 150.0), abs=1e-9)


# ── the non-rigid rule ────────────────────────────────────────────────────────


class TestNonRigidTransform:
    @pytest.mark.parametrize(
        ("label", "matrix"),
        [("scale", QTransform().scale(2.0, 0.5)),
         ("mirror", QTransform().scale(-1.0, 1.0)),
         ("turn + stretch", QTransform().rotate(30.0).scale(1.5, 1.0)),
         ("shear", QTransform().shear(0.4, 0.0))],
    )
    @pytest.mark.parametrize("shape", ["ellipse", "rectangle", "polygon", "polyline"])
    def test_scale_mirror_and_shear_are_baked_into_the_local_footprint(
        self, canvas: CanvasView, shape: str, label: str, matrix: QTransform
    ) -> None:
        item = FACTORIES[shape]()
        canvas.scene().addItem(item)
        item.setTransform(matrix)
        item.setPos(40.0, 60.0)
        record = snapshot_records(canvas.scene())[str(item.item_id)]
        assert record.transform.rotation_deg == 0.0, label  # the transform stays rigid
        expected = item_footprints(item)
        posed = _rings_of(record)
        assert all(signed_area(ring) > 0.0 for ring in record.footprints)  # outer rings, always
        if shape == "polyline":
            centre_line = [(p.x(), p.y()) for p in (item.mapToScene(q) for q in item.points)]
            for a, b in zip(pose_ring(record.transform, record.path), centre_line, strict=True):
                assert a == pytest.approx(b, abs=1e-6)
            assert _strip_deviation(posed, expected) <= 3e-3
        else:
            assert _ring_deviation(posed[0], expected[0]) <= 1e-6
            mirrored = matrix.determinant() < 0.0
            # a mirror hands the 2D ring out clockwise; the record turns it round
            assert (list(posed[0]) != [pytest.approx(q, abs=1e-6) for q in expected[0]]) is mirrored

    def test_an_item_in_a_scaled_group_moves_as_transform_only(self, canvas: CanvasView) -> None:
        item = _rectangle()
        group = QGraphicsItemGroup()
        canvas.scene().addItem(group)
        group.addToGroup(item)
        group.setScale(2.0)
        before = snapshot_records(canvas.scene())
        group.moveBy(50.0, -20.0)
        after = snapshot_records(canvas.scene())
        assert diff(before, after) == SceneDiff(transform=(str(item.item_id),))

    def test_a_scaled_circle_keeps_the_2d_footprint(self, canvas: CanvasView) -> None:
        """``item_footprints`` polygonises a circle around its mapped centre with its
        OWN radius — a scale does not reach it. The record says the same."""
        item = _circle()
        canvas.scene().addItem(item)
        item.setTransform(QTransform().scale(2.0, 0.5))
        record = snapshot_records(canvas.scene())[str(item.item_id)]
        for a, b in zip(pose_ring(record.transform, record.footprints[0]), item_footprints(item)[0],
                        strict=True):
            assert a == pytest.approx(b, abs=1e-6)


# ── what a record carries ─────────────────────────────────────────────────────


def _plain(value: Any) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, tuple):
        return all(_plain(v) for v in value)
    if isinstance(value, Params):
        return all(_plain(v) for v in value.values())
    if isinstance(value, Transform | Material | Paint):  # Paint: the material's own part (L1.5)
        return all(_plain(getattr(value, f)) for f in value.__dataclass_fields__)
    return False


class TestRecordContent:
    def test_outline_shapes_are_the_record_shapes(self) -> None:
        assert OUTLINE_SHAPES == SHAPES

    def test_records_are_plain_data(self, stage: Stage) -> None:
        """GUI thread in, plain data out: no Qt object survives into a record."""
        record = stage.record
        for field in Record.__dataclass_fields__:
            assert _plain(getattr(record, field)), field
        assert record.item_id == stage.id and record.kind == stage.item.object_type.name
        assert record.params["seed"] == stage.id

    def test_height_is_the_2d_resolver_s(self, stage: Stage) -> None:
        expected = effective_height_cm(stage.item.object_type, stage.item.metadata, at_date=stage.at)
        assert stage.record.height_cm == expected
        assert stage.record.has_2d_caster is (expected is not None)
        assert stage.record.base_cm == 0.0  # no parent bed: on the ground (L1.6, test_scene3d_base_stacking)

    def test_shape_specific_fields(self, stage: Stage) -> None:
        record = stage.record
        if stage.shape in ROUND:
            assert record.shape == "circle" and len(record.footprints[0]) == 24
            radius = record.params["radius_cm"]
            assert record.footprints[0][0] == (radius, 0.0) and record.path == ()
        elif stage.shape == "polyline":
            assert record.shape == "polyline" and len(record.path) == 4
            assert record.path_width_cm == 24.5 and len(record.footprints) == 1
        else:
            assert record.shape == stage.shape and record.path == () and record.path_width_cm is None
            xs = [x for x, _y in record.footprints[0]]
            ys = [y for _x, y in record.footprints[0]]
            assert min(xs) == -max(xs) and min(ys) == -max(ys)  # centred on its anchor

    def test_material(self, canvas: CanvasView) -> None:
        shed, wall = _rectangle(), _polyline()
        for item in (shed, wall):
            canvas.scene().addItem(item)
        records = snapshot_records(canvas.scene())
        shed_material = records[str(shed.item_id)].material
        fill = shed.fill_color
        assert shed_material.key == "TOOL_SHED"
        assert shed_material.fill_rgba == (fill.red(), fill.green(), fill.blue(), fill.alpha())
        assert shed_material.pattern == shed.fill_pattern.name
        wall_material = records[str(wall.item_id)].material
        stroke = wall.pen().color()
        assert wall_material.fill_rgba is None and wall_material.pattern is None
        assert wall_material.tint_rgba == (stroke.red(), stroke.green(), stroke.blue(), 255)

    def test_a_colour_stored_as_a_string_is_read_too(self, canvas: CanvasView) -> None:
        """``fill_color`` is typed loosely on the mixin; the legacy collector accepts
        a colour name, so contract v2 does as well — and an invalid one is no colour."""
        item = _rectangle()
        canvas.scene().addItem(item)
        item.fill_color = "#336699"
        assert snapshot_records(canvas.scene())[str(item.item_id)].material.fill_rgba == (51, 102, 153, 255)
        item.fill_color = "not a colour"
        material = snapshot_records(canvas.scene())[str(item.item_id)].material
        assert material.fill_rgba is None and material.tint_rgba[3] == 255

    def test_plant_params(self, canvas: CanvasView) -> None:
        tree = _plant()
        bare = CircleItem(100.0, 100.0, 30.0, object_type=ObjectType.SHRUB)
        bare.plant_species = "  Mystery bush "
        for item in (tree, bare):
            canvas.scene().addItem(item)
        records = snapshot_records(canvas.scene(), JUNE)
        params = records[str(tree.item_id)].params
        assert params["species_key"] == species_key(SPECIES) == "malus domestica"
        assert params["species_name"] == "Apple tree"
        bare_params = records[str(bare.item_id)].params
        assert bare_params["species_name"] == "Mystery bush" and "species_key" not in bare_params

    def test_parent_bed_is_the_property_not_metadata(self, canvas: CanvasView) -> None:
        bed = RectangleItem(0.0, 0.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED)
        plant = CircleItem(100.0, 100.0, 20.0, object_type=ObjectType.PERENNIAL)
        for item in (bed, plant):
            canvas.scene().addItem(item)
        before = snapshot_records(canvas.scene())
        assert before[str(plant.item_id)].parent_id is None
        plant.parent_bed_id = bed.item_id
        after = snapshot_records(canvas.scene())
        assert after[str(plant.item_id)].parent_id == str(bed.item_id)
        # A link, not geometry and not material: L1.6 turns it into ``base_cm`` — the
        # plant now stands on the soil of the 40 cm bed — so it is a TRANSFORM change.
        assert diff(before, after) == SceneDiff(transform=(str(plant.item_id),))
        assert after[str(plant.item_id)].transform.base_cm == 38.0
        # onto a parent that holds no raised soil the link changes nothing at all
        lawn_bed = RectangleItem(400.0, 0.0, 300.0, 200.0, object_type=ObjectType.GARDEN_BED)
        canvas.scene().addItem(lawn_bed)
        on_raised = snapshot_records(canvas.scene())
        plant.parent_bed_id = None
        loose = snapshot_records(canvas.scene())
        plant.parent_bed_id = lawn_bed.item_id
        assert diff(loose, snapshot_records(canvas.scene())).is_empty
        assert diff(on_raised, loose) == SceneDiff(transform=(str(plant.item_id),))

    def test_path_style_and_container_material(self, canvas: CanvasView) -> None:
        fence = PolylineItem([QPointF(0.0, 0.0), QPointF(500.0, 0.0)], object_type=ObjectType.FENCE,
                             path_fence_style=PathFenceStyle.WOODEN_FENCE)
        plain = PolylineItem([QPointF(0.0, 50.0), QPointF(500.0, 50.0)], object_type=ObjectType.FENCE)
        pot = CircleItem(700.0, 100.0, 25.0, object_type=ObjectType.CONTAINER_ROUND)
        pot.metadata["container_material"] = "terracotta"
        for item in (fence, plain, pot):
            canvas.scene().addItem(item)
        records = snapshot_records(canvas.scene())
        assert records[str(fence.item_id)].params["path_style"] == "WOODEN_FENCE"
        assert "path_style" not in records[str(plain.item_id)].params
        assert records[str(pot.item_id)].params["container_material"] == "terracotta"
        before = records
        fence.path_fence_style = PathFenceStyle.STONE_WALL
        assert str(fence.item_id) in diff(before, snapshot_records(canvas.scene())).geometry

    def test_order_is_bottom_to_top_like_the_legacy_collector(self, qtbot) -> None:
        """Bottom to top, as the retired Qt 3D view's collector was (L1.10 deleted it: it
        drew the ridge LINE as a decal, 99 records for this plan)."""
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / "bench_small.ogp")
        records = snapshot_records(scene, JUNE)
        items = {str(i.item_id): i for i in scene.items() if hasattr(i, "item_id")}
        zs = [items[item_id].zValue() for item_id in records]
        assert zs == sorted(zs) and len(set(zs)) > 5
        ridges = [i for i in items.values() if i.object_type is ObjectType.ROOF_RIDGE]
        # contract v2 hands the ridge to its house as a param and gives the ridge item
        # no record
        assert len(ridges) == 1 and str(ridges[0].item_id) not in records
        assert len(records) == 98

    def test_skipped_items(self, canvas: CanvasView) -> None:
        from open_garden_planner.ui.canvas.items.text_item import TextItem

        scene = canvas.scene()
        hidden = _rectangle()
        scene.addItem(hidden)
        hidden.setVisible(False)
        scene.addItem(TextItem(10.0, 10.0, "a note"))
        degenerate = EllipseItem(0.0, 0.0, 0.0, 50.0, object_type=ObjectType.POND_POOL)
        scene.addItem(degenerate)
        stub = PolylineItem([QPointF(5.0, 5.0)], object_type=ObjectType.FENCE)
        scene.addItem(stub)
        dot = CircleItem(50.0, 50.0, 0.0, object_type=ObjectType.TRAMPOLINE)
        scene.addItem(dot)
        assert item_outline(degenerate) is None
        assert item_footprints(dot) == [[]] and item_footprints(stub) == []  # nothing in 2D either
        snapshot, skipped = snapshot_with_report(scene)
        assert snapshot == {} and type(snapshot) is dict  # the return type never changed
        assert skipped == []  # left out by design — nothing is wrong with them

    def test_a_circle_turned_about_another_pivot_moves_and_still_does_not_rotate(
        self, canvas: CanvasView
    ) -> None:
        """Only a pivot away from the centre makes a circle's rotation visible in its
        GEOMETRY — as a new position. Its record still carries rotation 0; the
        turn itself is a fact of its paint (L1.5: what is painted in a circle
        turns with it), a material change."""
        item = _circle()
        canvas.scene().addItem(item)
        before = snapshot_records(canvas.scene())
        item.setTransformOriginPoint(QPointF(0.0, 0.0))
        item.setRotation(90.0)
        after = snapshot_records(canvas.scene())
        item_id = str(item.item_id)
        assert diff(before, after) == SceneDiff(transform=(item_id,), material=(item_id,))
        assert after[item_id].transform == Transform(-220.25, 310.5, 0.0)  # (x, y) → (−y, x)
        assert after[item_id].material.paint.rotation_deg == 90.0
        assert after[item_id].same_geometry(before[item_id])

    @pytest.mark.parametrize("height", [1e300, 1.0000001e6, float("inf")],
                             ids=["1e300", "just over the bound", "infinite"])
    def test_a_height_no_plan_can_hold_gets_no_solid_and_is_reported(
        self, canvas: CanvasView, height: float
    ) -> None:
        """A plan file edited by hand can hold ``"object_height_cm": 1e300``, and
        ``effective_height_cm`` passes it on. It is positive and finite, so it
        passed every check — and became infinity in the mesh's float32, which a
        sink that does not validate hands to the engine (found at the pipeline
        level by the plant story's review). The record layer refuses it once, for
        every builder: the item gets no record and is reported with its own code.
        Driven the whole way here: snapshot → ``SceneSync`` → sink, unvalidated."""
        snapshot_module._reported.clear()
        shed, bed = _rectangle(), RectangleItem(900.0, 100.0, 200.0, 100.0,
                                                object_type=ObjectType.RAISED_BED)
        scene = canvas.scene()
        scene.addItem(shed)
        scene.addItem(bed)
        shed.metadata[METADATA_KEY] = height
        assert effective_height_cm(shed.object_type, shed.metadata) == height
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(bed.item_id)]  # the rest of the plan is untouched
        (report,) = skipped
        assert (report.item_id, report.kind, report.reason) == (
            str(shed.item_id), "TOOL_SHED", SkipReason.OUT_OF_RANGE)
        assert report.reason == "out_of_range" and report.error_type == "RecordRangeError"
        assert "a height of" in report.error_message and "1e+06 cm" in report.error_message

        sink = RecordingSink()
        sync = SceneSync(sink, validate=False)  # as production runs
        sync.apply(snapshot)
        assert sync.failures == {} and set(sink.state().items) == {str(bed.item_id)}
        for held in sink.state().items.values():
            for part in held.parts:
                for name in ("positions", "normals", "colors", "uvs"):
                    assert np.isfinite(getattr(part.mesh, name)).all()

        # the height the bound still allows — 10 km — is a solid like any other
        shed.metadata[METADATA_KEY] = 1e6
        record = snapshot_records(scene)[str(shed.item_id)]
        part = _solid(default_builder(record))
        assert record.height_cm == 1e6 and float(part.mesh.bounds()[1][2]) == 1e6
        assert np.isfinite(part.mesh.positions).all()

    @pytest.mark.parametrize("height", [1e-300, 1e-46, 9e-4],
                             ids=["1e-300", "zero in float32", "just under the floor"])
    def test_a_height_too_small_to_be_one_is_reported_too(
        self, canvas: CanvasView, height: float
    ) -> None:
        """Review round 3, P2-8 — the other end of the same rule. Such a height
        built a solid 0.0 cm high that passed ``validate``."""
        snapshot_module._reported.clear()
        shed = _rectangle()
        canvas.scene().addItem(shed)
        shed.metadata[METADATA_KEY] = height
        assert effective_height_cm(shed.object_type, shed.metadata) == height
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {}
        assert [(s.reason, s.error_type) for s in skipped] == [(SkipReason.OUT_OF_RANGE, "RecordRangeError")]
        assert "is below what a solid can have" in skipped[0].error_message
        shed.metadata[METADATA_KEY] = 1e-3  # the floor itself: a record, and a solid
        record = snapshot_records(canvas.scene())[str(shed.item_id)]
        part = _solid(default_builder(record))
        assert float(part.mesh.bounds()[1][2]) == float(np.float32(1e-3))

    def test_a_height_of_nothing_is_no_height(self, canvas: CanvasView) -> None:
        """Zero, a negative number or a string is not an explicit height at all
        (``explicit_height_cm``): the kind's default stands, nothing is reported."""
        item = _rectangle()
        canvas.scene().addItem(item)
        usual = snapshot_records(canvas.scene())[str(item.item_id)].height_cm
        for nothing in (0.0, -5.0, "tall"):
            item.metadata[METADATA_KEY] = nothing
            snapshot, skipped = snapshot_with_report(canvas.scene())
            assert snapshot[str(item.item_id)].height_cm == usual and skipped == []

    @pytest.mark.parametrize(
        ("label", "make"),
        [("a canopy radius", lambda: CircleItem(0.0, 0.0, 2.5e6, object_type=ObjectType.TREE)),
         ("a rectangle's side", lambda: RectangleItem(0.0, 0.0, 3.0e6, 100.0,
                                                      object_type=ObjectType.RAISED_BED)),
         ("a polygon's vertex", lambda: PolygonItem(
             [QPointF(0.0, 0.0), QPointF(1e300, 0.0), QPointF(0.0, 500.0)],
             object_type=ObjectType.HOUSE)),
         ("a fence's vertex", lambda: PolylineItem(
             [QPointF(0.0, 0.0), QPointF(0.0, -4.0e6)], object_type=ObjectType.FENCE)),
         ("a position", lambda: _far_away(5.0e6))],
    )
    def test_every_length_that_becomes_geometry_is_held_to_the_bound(
        self, canvas: CanvasView, label: str, make: Any
    ) -> None:
        snapshot_module._reported.clear()
        item = make()
        canvas.scene().addItem(item)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {}, label
        assert [(s.item_id, s.reason, s.error_type) for s in skipped] == [
            (str(item.item_id), SkipReason.OUT_OF_RANGE, "RecordRangeError")], label

    def test_a_stroke_width_no_plan_can_hold(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pen cannot carry one — Qt refuses a width from 32,768 on and keeps the
        old — so the outline is handed one directly: the rule must not depend on
        which layer above happens to be strict."""
        import dataclasses

        fence = PolylineItem([QPointF(0.0, 0.0), QPointF(500.0, 0.0)], object_type=ObjectType.FENCE)
        canvas.scene().addItem(fence)
        pen = fence.pen()
        pen.setWidthF(3.0e6)
        adopt_pen(fence, pen)
        assert fence.pen().widthF() < 32768.0  # Qt kept the old width
        real = snapshot_module.item_outline
        monkeypatch.setattr(snapshot_module, "item_outline", lambda item, at_date=None:
                            dataclasses.replace(real(item, at_date), width_cm=3.0e6))
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUT_OF_RANGE]
        assert "a stroke width of 3000000.0 cm" in skipped[0].error_message

    def test_an_out_of_range_item_is_logged_once_with_what_was_wrong(
        self, canvas: CanvasView, caplog: pytest.LogCaptureFixture
    ) -> None:
        snapshot_module._reported.clear()
        item = _rectangle()
        canvas.scene().addItem(item)
        item.metadata[METADATA_KEY] = 1e300
        with caplog.at_level(logging.WARNING, logger=snapshot_module.__name__):
            caplog.clear()
            for _ in range(3):
                snapshot_records(canvas.scene())
        (line,) = caplog.records
        assert line.levelno == logging.WARNING and line.exc_info is None  # the plan's data, no defect
        assert "[out_of_range]" in line.getMessage() and "a height of 1e+300 cm" in line.getMessage()

    def test_non_finite_geometry_is_skipped_not_propagated(self, canvas: CanvasView) -> None:
        """NaN != NaN: one such record would report a change on every diff, forever.
        It is left out — and said so (see ``TestContainment``)."""
        item = _rectangle()
        canvas.scene().addItem(item)
        item.setPos(float("nan"), 0.0)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {}
        assert skipped == [SkippedItem(str(item.item_id), "TOOL_SHED", SkipReason.RECORD_FAILED,
                                       "ValueError", "a position that is not finite")]


# ── P1-1: a stroke that closes on itself ──────────────────────────────────────


def _fence(points: list[tuple[float, float]], width_cm: float = 10.0) -> Any:
    item = PolylineItem([QPointF(x, y) for x, y in points], object_type=ObjectType.FENCE)
    pen = item.pen()
    pen.setWidthF(width_cm)
    adopt_pen(item, pen)
    return item


#: label → (centre line, outer rings, holes) — a 10 m x 8 m garden fence, 10 cm wide
FENCES: dict[str, tuple[list[tuple[float, float]], int, int]] = {
    "closed loop": ([(0, 0), (1000, 0), (1000, 800), (0, 800), (0, 0)], 1, 1),
    "nearly closed (2 cm gap)": ([(0, 2), (0, 800), (1000, 800), (1000, 0), (0, 0)], 1, 1),
    "open U": ([(0, 800), (0, 0), (1000, 0), (1000, 800)], 1, 0),
}


class TestClosedStrokes:
    """Review P1-1. A closed fence's stroke is an outer ring and a HOLE. The first
    contract put both into ``footprints``; the default builder extruded both; the
    result was a slab at fence height over the whole garden — 81.8 m² of ground
    where the fence stands on 3.6 m², under two caps of 160 m² together — with an
    inside-out inner wall, and G4, G7 and ``verify_builder`` all passed, because
    none of them asked how much ground the solid covers. These tests ask."""

    @pytest.mark.parametrize("rotation", [0.0, 33.0])
    @pytest.mark.parametrize("label", sorted(FENCES))
    def test_the_solid_covers_the_stroke_and_nothing_else(
        self, canvas: CanvasView, label: str, rotation: float
    ) -> None:
        centre_line, outers, holes = FENCES[label]
        item = _fence(centre_line)
        canvas.scene().addItem(item)
        apply_rotation(item, rotation)
        item.setPos(140.5, 60.25)
        item.metadata[METADATA_KEY] = 120.0
        snapshot, skipped = snapshot_with_report(canvas.scene())
        record = snapshot[str(item.item_id)]
        assert skipped == []

        # structure: outer rings counter-clockwise, their holes clockwise
        assert len(record.footprints) == outers
        assert sum(len(group) for group in record.holes) == holes
        assert all(signed_area(ring) > 0.0 and is_simple_ring(ring) for ring in record.footprints)
        assert all(signed_area(hole) < 0.0 for group in record.holes for hole in group)
        assert len(record.regions) == outers

        # G4 over EVERY ring: the record's rings are the 2D stroke's rings
        two_d = item_footprints(item)
        assert len(two_d) == outers + holes
        assert _strip_deviation(_rings_of(record), two_d) <= 3e-3

        # the area. Stated tolerances: (1) the cap IS the footprint region, to
        # float32 (1e-6); (2) the region is what the 2D stroke encloses, to
        # pyclipper's grid — the two inflate the same line in two frames (5e-4);
        # (3) both are the line's length times its width, to 0.5 % — square
        # joins and butt ends are the rest. The slab of the defect was off by 4,350 %.
        part = _solid(verify_builder(default_builder, record))
        part.validate()
        cap = _cap_area(part.mesh)
        length = sum(math.dist(centre_line[i], centre_line[i + 1]) for i in range(len(centre_line) - 1))
        assert cap == pytest.approx(record.plan_area_cm2, rel=1e-6)
        assert cap == pytest.approx(_signed_area_sum(two_d), rel=5e-4)
        assert cap == pytest.approx(length * 10.0, rel=5e-3)
        assert float(part.mesh.bounds()[1][2]) == 120.0
        _assert_walls_face_away_from_the_solid(part.mesh, record)

    def test_the_defect_reconstructed_is_caught_by_verify_builder(self, canvas: CanvasView) -> None:
        """The pre-fix default builder — every ring a solid — on the real closed
        fence. It used to pass every gate; ``verify_builder`` now refuses it."""
        from open_garden_planner.core.scene3d import BuilderContractError, MeshPart, prism_mesh

        item = _fence(FENCES["closed loop"][0])
        canvas.scene().addItem(item)
        item.metadata[METADATA_KEY] = 120.0
        record = snapshot_records(canvas.scene())[str(item.item_id)]

        def every_ring_a_solid(rec: Record) -> tuple[MeshPart, ...]:
            rings = [*rec.footprints, *(hole for group in rec.holes for hole in group)]
            assert rec.height_cm is not None
            return (MeshPart(prism_mesh(rings, rec.height_cm)),)

        (slab,) = every_ring_a_solid(record)
        assert abs(_cap_area(slab.mesh)) > 40 * record.plan_area_cm2  # 1,600,162 vs 35,962 cm²
        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(every_ring_a_solid, record)

    def test_closing_the_gap_is_a_geometry_change_only(self, canvas: CanvasView) -> None:
        """An open U dragged shut gains a hole — and the hole is part of the
        geometry signature, or the engine would keep the open fence's solid."""
        stage_item = _fence([(0, 800), (0, 0), (1000, 0), (1000, 800), (500, 800)])
        canvas.scene().addItem(stage_item)
        before = snapshot_records(canvas.scene())
        item_id = str(stage_item.item_id)
        assert before[item_id].holes == ()
        # the last vertex, moved onto the first: inside the bounding box, so no move
        stage_item._move_vertex_to(4, QPointF(0.0, 800.0))
        after = snapshot_records(canvas.scene())
        assert diff(before, after) == SceneDiff(geometry=(item_id,))
        assert len(after[item_id].holes[0]) == 1

    def test_a_stroke_that_crosses_itself(self, canvas: CanvasView) -> None:
        """A figure of eight: one outer ring with two holes (the loops)."""
        item = _fence([(0, 0), (400, 400), (800, 0), (800, 400), (400, 0), (0, 400), (0, 0)])
        canvas.scene().addItem(item)
        item.metadata[METADATA_KEY] = 100.0
        record = snapshot_records(canvas.scene())[str(item.item_id)]
        assert len(record.footprints) == 1 and len(record.holes[0]) >= 2
        part = _solid(verify_builder(default_builder, record))
        assert _cap_area(part.mesh) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        assert _cap_area(part.mesh) == pytest.approx(_signed_area_sum(item_footprints(item)), rel=5e-4)


# ── P2-6: a polygon that crosses itself ───────────────────────────────────────


class TestSelfCrossingPolygon:
    def test_a_bow_tie_house_becomes_its_two_lobes(self, canvas: CanvasView) -> None:
        """The user can draw it; ``item_footprints`` hands it to the 2D shadow as
        one self-crossing ring, whose own ground the shadow's union fills by the
        non-zero rule (60,000 cm² at a vertical sun: both lobes). The record
        carries what that rule fills — two simple triangles — so no builder ever
        receives a ring it cannot triangulate, and the first contract's mesh that
        failed ``validate()`` cannot be emitted."""
        bow = PolygonItem([QPointF(100.0, 100.0), QPointF(500.0, 400.0), QPointF(500.0, 100.0),
                           QPointF(100.0, 400.0)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(bow)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        record = snapshot[str(bow.item_id)]
        assert skipped == []
        assert len(item_footprints(bow)) == 1  # 2D: the ring as drawn
        assert record.params["outline_resolved"] is True and "ridge" not in record.params
        assert len(record.footprints) == 2 and record.holes == ()
        assert all(is_simple_ring(ring) and len(ring) == 3 for ring in record.footprints)
        assert [signed_area(ring) for ring in record.footprints] == pytest.approx([30000.0, 30000.0])
        from open_garden_planner.core.shadow_geometry import compute_scene_shadows

        vertical_sun = compute_scene_shadows([(item_footprints(bow)[0], 300.0)], 89.999, 180.0)
        assert _signed_area_sum(vertical_sun) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        part = _solid(verify_builder(default_builder, record))
        part.validate()
        assert _cap_area(part.mesh) == pytest.approx(60000.0, rel=1e-6)
        sync = SceneSync(RecordingSink(), validate=True)
        sync.apply(snapshot)
        assert sync.failures == {}

    def test_a_pentagram_keeps_its_centre(self, canvas: CanvasView) -> None:
        """The non-zero rule, the 2D shadow's: the star is one ring of ten corners,
        centre included (the canvas paints it odd-even, centre open — ADR-059)."""
        star = PolygonItem([QPointF(500.0 + 300.0 * math.sin(4.0 * math.pi * k / 5.0),
                                    500.0 + 300.0 * math.cos(4.0 * math.pi * k / 5.0))
                            for k in range(5)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(star)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        record = snapshot[str(star.item_id)]
        assert skipped == [] and len(record.footprints) == 1 and record.holes == ()
        assert len(record.footprints[0]) == 10 and is_simple_ring(record.footprints[0])
        assert point_in_regions(0.0, 0.0, record.regions)  # the centre is built on
        from open_garden_planner.core.shadow_geometry import compute_scene_shadows

        vertical_sun = compute_scene_shadows([(item_footprints(star)[0], 300.0)], 89.999, 180.0)
        # to pyclipper's grid: the crossing points are snapped in two different frames
        assert _signed_area_sum(vertical_sun) == pytest.approx(record.plan_area_cm2, rel=1e-5)
        verify_builder(default_builder, record)

    def test_a_polygon_with_no_area_left_gets_no_record(self, canvas: CanvasView) -> None:
        flat = PolygonItem([QPointF(0.0, 0.0), QPointF(100.0, 100.0), QPointF(200.0, 200.0)],
                           object_type=ObjectType.HOUSE)
        spur = PolygonItem([QPointF(400.0, 200.0), QPointF(400.0, 0.0), QPointF(400.0, 50.0),
                            QPointF(350.0, 50.0), QPointF(400.0, 50.0)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(flat)
        canvas.scene().addItem(spur)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and skipped == []  # they cover no ground: left out by design

    # ── fix round 2 (P1): "resolved" is a fact a builder can read, and every region is buildable ──

    #: The four outlines of the re-review, measured on real HOUSE polygons: at the
    #: first fix one was a single ring passing for an ordinary house, one had a
    #: pocket the default builder could not cut, one a ring that was not simple,
    #: and one got no record at all. → (footprint rings, their vertex counts).
    REVIEWED: dict[str, tuple[list[tuple[float, float]], list[int]]] = {
        "one ring of ten": ([(50, 400), (0, 300), (350, 100), (0, 400), (50, 0)], [10]),
        "a pocket": ([(100, 50), (100, 150), (350, 400), (50, 200), (150, 150), (0, 50), (200, 300)],
                     [4, 3, 13]),
        "a ring that touches itself": ([(150, 100), (0, 200), (50, 150), (350, 0), (0, 300)], [3, 3]),
        "a hole on the boundary": ([(0, 200), (50, 0), (50, 250), (150, 100), (0, 0), (250, 100)],
                                   [3, 16]),
    }

    @pytest.mark.parametrize("label", sorted(REVIEWED))
    def test_the_four_outlines_of_the_review(self, canvas: CanvasView, label: str) -> None:
        points, rings = self.REVIEWED[label]
        house = PolygonItem([QPointF(1000.0 + x, 800.0 + y) for x, y in points],
                            object_type=ObjectType.HOUSE)
        ridge = PolylineItem([QPointF(1000.0, 1000.0), QPointF(1350.0, 1000.0)],
                             object_type=ObjectType.ROOF_RIDGE)
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        canvas.scene().addItem(house)
        canvas.scene().addItem(ridge)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and list(snapshot) == [str(house.item_id)]  # a record, every time
        record = snapshot[str(house.item_id)]
        # resolved — said in the record, not guessed from a ring count …
        assert record.params["outline_resolved"] is True
        assert sorted(len(ring) for ring in record.footprints) == sorted(rings)
        # … and the ridge that was drawn for the DRAWN outline is not handed on
        assert "ridge" not in record.params
        # every region is one a builder can build: the predicate, and the builder itself
        assert all(is_buildable_region(outer, holes) for outer, holes in record.regions)
        part = _solid(verify_builder(default_builder, record))
        part.validate()
        assert _cap_area(part.mesh) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        sync = SceneSync(RecordingSink(), validate=True)
        sync.apply(snapshot)
        assert sync.failures == {}
        # the ground it covers is what the 2D shadow fills at a vertical sun, less the hair
        # by which parts that met in a point were drawn apart (0.002 cm along their edges)
        from open_garden_planner.core.shadow_geometry import compute_scene_shadows

        vertical_sun = compute_scene_shadows([(item_footprints(house)[0], 300.0)], 89.999, 180.0)
        assert record.plan_area_cm2 == pytest.approx(_signed_area_sum(vertical_sun), rel=2e-3)
        # an unchanged scene still snapshots identically, a move is still a transform only
        assert diff(snapshot, snapshot_records(canvas.scene())).is_empty
        house.moveBy(33.25, -12.5)
        assert diff(snapshot, snapshot_records(canvas.scene())) == SceneDiff(
            transform=(str(house.item_id),))

    def test_a_simple_house_keeps_its_ridge_and_says_nothing_about_resolving(
        self, canvas: CanvasView
    ) -> None:
        house = PolygonItem([QPointF(0.0, 0.0), QPointF(900.0, 0.0), QPointF(900.0, 540.0),
                             QPointF(0.0, 540.0)], object_type=ObjectType.HOUSE)
        ridge = PolylineItem([QPointF(0.0, 270.0), QPointF(900.0, 270.0)],
                             object_type=ObjectType.ROOF_RIDGE)
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        canvas.scene().addItem(house)
        canvas.scene().addItem(ridge)
        record = snapshot_records(canvas.scene())[str(house.item_id)]
        assert "outline_resolved" not in record.params and "ridge" in record.params

    @pytest.mark.parametrize(
        ("label", "points"),
        [("a closing vertex that repeats the first",
          [(0, 0), (400, 0), (400, 300), (150, 300), (150, 150), (0, 150), (0, 0)]),
         ("a vertex placed twice",
          [(0, 0), (400, 0), (400, 0), (400, 300), (150, 300), (150, 150), (0, 150)]),
         ("both, and a triple",
          [(0, 0), (0, 0), (0, 0), (400, 0), (400, 300), (150, 300), (150, 150), (0, 150), (0, 0)])],
    )
    def test_a_vertex_placed_twice_does_not_send_an_outline_through_the_resolution(
        self, canvas: CanvasView, label: str, points: list[tuple[float, float]]
    ) -> None:
        """Review round 2, P1.3. Such an outline is not self-crossing; resolving it
        put its vertices on the clipper grid, started the ring somewhere else and
        would now cost a HOUSE its ridge. It stays the drawn outline, said once."""
        plain = PolygonItem([QPointF(x + 0.123456, y + 0.654321) for x, y in dict.fromkeys(points)],
                            object_type=ObjectType.HOUSE)
        doubled = PolygonItem([QPointF(x + 0.123456, y + 0.654321) for x, y in points],
                              object_type=ObjectType.HOUSE)
        scene = canvas.scene()
        scene.addItem(plain)
        scene.addItem(doubled)
        snapshot, skipped = snapshot_with_report(scene)
        one, two = snapshot[str(plain.item_id)], snapshot[str(doubled.item_id)]
        assert skipped == [] and "outline_resolved" not in two.params, label
        assert two.footprints == one.footprints and len(two.footprints[0]) == 6  # vertex for vertex
        assert two.holes == ()
        # unchanged scene → empty diff; move → transform only; turn → transform only
        assert diff(snapshot, snapshot_records(scene)).is_empty
        doubled.moveBy(41.5, 17.25)
        moved = snapshot_records(scene)
        assert diff(snapshot, moved) == SceneDiff(transform=(str(doubled.item_id),))
        apply_rotation(doubled, 33.0)
        assert diff(moved, snapshot_records(scene)) == SceneDiff(transform=(str(doubled.item_id),))

    def test_an_outline_that_cannot_be_made_buildable_is_skipped_with_its_own_code(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The residue, should there ever be one: no record, a ``SkippedItem`` with a
        stable code, the rest of the plan untouched. Forced here — over 7,500 random
        self-crossing outlines none arose (``test_random_self_crossing_outlines``)."""
        snapshot_module._reported.clear()
        monkeypatch.setattr(snapshot_module, "_resolved_regions",
                            lambda *_args, **_kwargs: snapshot_module._NO_READING)
        snapshot_module._polygon_regions.cache_clear()
        try:
            bow = PolygonItem([QPointF(0.0, 0.0), QPointF(400.0, 300.0), QPointF(400.0, 0.0),
                               QPointF(0.0, 300.0)], object_type=ObjectType.HOUSE)
            shed = _rectangle()
            canvas.scene().addItem(bow)
            canvas.scene().addItem(shed)
            snapshot, skipped = snapshot_with_report(canvas.scene())
        finally:
            snapshot_module._polygon_regions.cache_clear()
        assert list(snapshot) == [str(shed.item_id)]
        assert skipped == [SkippedItem(str(bow.item_id), "HOUSE", SkipReason.OUTLINE_UNBUILDABLE,
                                       "_UnbuildableOutline",
                                       "the outline cannot be made into regions a builder can build")]


def _far_away(distance: float) -> Any:
    item = RectangleItem(0.0, 0.0, 100.0, 100.0, object_type=ObjectType.TOOL_SHED)
    item.setPos(distance, 0.0)
    return item


def _random_outline(rng: Any, grid: float, vertices: int, span: float = 400.0) -> tuple[Any, ...]:
    points: list[tuple[float, float]] = []
    cells = int(span / grid)
    while len(points) < vertices:
        point = (rng.randrange(cells + 1) * grid, rng.randrange(cells + 1) * grid)
        if not points or point != points[-1]:
            points.append(point)
    if points[0] == points[-1]:
        points.pop()
    return tuple((float(x), float(y)) for x, y in points)


def _winding_area(outline: Any, step: float = 2.0, span: float = 400.0) -> float:
    """The area an outline fills by the non-zero rule, from a raster of its winding
    number — computed with no clipper at all."""
    xs, ys = np.meshgrid(np.arange(step / 2.0, span, step), np.arange(step / 2.0, span, step))
    winding = np.zeros(xs.shape, dtype=np.int64)
    for i in range(len(outline)):
        (x1, y1), (x2, y2) = outline[i - 1], outline[i]
        if y1 != y2:
            crossed = ((y1 > ys) != (y2 > ys)) & (xs < (x2 - x1) * (ys - y1) / (y2 - y1) + x1)
            winding += np.where(crossed, 1 if y2 > y1 else -1, 0)
    return float((winding != 0).sum()) * step * step


@pytest.mark.parametrize(("grid", "count"), [(50.0, 2500), (10.0, 2500), (0.001, 2500)],
                         ids=["a 50 cm grid", "a 10 cm grid", "a 0.001 cm grid"])
def test_random_self_crossing_outlines(grid: float, count: int) -> None:
    """Review round 2, P1 — the promise as a number. 2,500 random outlines of 5 to
    9 vertices that cross or touch themselves, per grid (a coarse one, where
    vertices fall on each other and edges retrace; a fine one, where nothing
    does): every one gets regions, every region satisfies the predicate, the
    default builder builds every one, and the ground covered is the outline's
    non-zero area. 0 dropped, 0 unbuildable — and if that ever stops being 0,
    this test says by how many."""
    import random

    rng = random.Random(385)
    dropped = unbuilt = wrong = seen = 0
    while seen < count:
        outline = _random_outline(rng, grid, rng.randrange(5, 10))
        if len(outline) < 3 or is_simple_ring(snapshot_module._without_repeats(outline)):
            continue
        truth = _winding_area(outline)
        if truth == 0.0:
            assert snapshot_module._polygon_regions(outline) == ((), True)  # no ground: no record
            continue
        seen += 1
        regions, resolved = snapshot_module._polygon_regions(outline)
        assert resolved
        if isinstance(regions, snapshot_module._Refused) or not regions:
            dropped += 1
            continue
        if not all(is_buildable_region(outer, holes) for outer, holes in regions):
            unbuilt += 1
            continue
        mesh = prism_mesh([outer for outer, _holes in regions], 100.0,
                          [holes for _outer, holes in regions])
        mesh.validate()  # … and what it builds is a sound mesh in the engine's float32
        unbuilt += not mesh.vertex_count
        # against the raster (2 cm cells: a perimeter of ~2,000 cm is ±1.5 % of a small shape)
        wrong += abs(regions_area(regions) - truth) > 0.03 * truth + 200.0
    assert (dropped, unbuilt, wrong) == (0, 0, 0)


@pytest.mark.parametrize("grid", [50.0, 10.0, 0.5],
                         ids=["a 50 cm grid", "a 10 cm grid", "a 0.5 cm grid"])
def test_random_strokes(grid: float) -> None:
    """The same promise for the other producer of holes. 1,500 random polylines
    per grid — 3 to 11 vertices, three in ten closed, 4 / 10 / 25 cm wide; on the
    coarse grid they cross and retrace themselves at will: every one gets
    regions, every region satisfies the predicate, the default builder builds a
    mesh that is sound in float32, and the ground covered is the area of the 2D
    stroke rings (outers minus holes)."""
    import random

    from open_garden_planner.core.shadow_geometry import polyline_footprint

    rng = random.Random(386)
    dropped = unbuilt = wrong = holed = 0
    for _ in range(1500):
        path = list(_random_outline(rng, grid, rng.randrange(3, 12)))
        if rng.random() < 0.3:
            path.append(path[0])
        width = rng.choice([4.0, 10.0, 25.0])
        regions = snapshot_module._polyline_regions(tuple(path), width)
        if isinstance(regions, snapshot_module._Refused):
            dropped += 1
            continue
        if not all(is_buildable_region(outer, holes) for outer, holes in regions):
            unbuilt += 1
            continue
        mesh = prism_mesh([outer for outer, _holes in regions], 100.0,
                          [holes for _outer, holes in regions])
        mesh.validate()
        unbuilt += not mesh.vertex_count
        holed += any(holes for _outer, holes in regions)
        drawn = _signed_area_sum(polyline_footprint(path, width))
        wrong += abs(regions_area(regions) - drawn) > 2e-3 * drawn + 1.0
    assert (dropped, unbuilt, wrong) == (0, 0, 0)
    assert holed > 100  # the sample is not made of open strokes only


class TestWhatPyclipperGetsWrong:
    """Two outlines — found by the random run above — for which pyclipper's own
    answer is not the outline's non-zero area: it retraces an edge, and the
    union hands one piece out as a hole. ``_resolved_regions`` checks every
    reading against the DRAWN outline and takes one that holds."""

    CASES: dict[str, tuple[tuple[tuple[float, float], ...], float]] = {
        "a piece handed out the wrong way round": (
            ((400.0, 250.0), (150.0, 300.0), (300.0, 0.0), (200.0, 100.0), (250.0, 100.0),
             (200.0, 400.0), (200.0, 100.0), (300.0, 0.0), (100.0, 350.0)), 13603.6),
        "a hole hung under the wrong ring": (
            ((400.0, 400.0), (100.0, 250.0), (300.0, 100.0), (250.0, 200.0), (300.0, 250.0),
             (200.0, 100.0), (250.0, 200.0), (300.0, 100.0)), 36704.5),
    }

    @pytest.mark.parametrize("label", sorted(CASES))
    def test_the_regions_are_the_outline_s_not_the_clipper_s(self, label: str) -> None:
        outline, area = self.CASES[label]
        assert _winding_area(outline, step=0.5) == pytest.approx(area, rel=2e-3)  # the truth
        strict = _strict_reading([snapshot_module._to_grid(outline)])
        # pyclipper's StrictlySimple reading is not usable as it comes …
        assert not (snapshot_module._buildable(strict)
                    and snapshot_module._matches_outline(outline, strict))
        regions, resolved = snapshot_module._polygon_regions(outline)
        # … and what is handed out is the outline's area, less a hair along the edges
        assert resolved and regions and snapshot_module._matches_outline(outline, regions)
        assert regions_area(regions) == pytest.approx(area, rel=1e-3)
        assert all(is_buildable_region(outer, holes) for outer, holes in regions)

    def test_the_second_one_is_wrong_in_the_plain_union_too(self) -> None:
        """Why no reading of pyclipper's is trusted without the check: the plain
        union's signed ring areas sum to 33,133 cm² for an outline that fills 36,704."""
        import pyclipper

        outline, area = self.CASES["a hole hung under the wrong ring"]
        clipper = pyclipper.Pyclipper()
        clipper.AddPath(snapshot_module._to_grid(outline), pyclipper.PT_SUBJECT, True)
        rings = clipper.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
        assert sum(pyclipper.Area(ring) for ring in rings) / 1e6 == pytest.approx(33133.1, abs=0.1)
        assert area - 33133.1 > 3500.0

    def test_a_reading_that_is_buildable_and_wrong_is_not_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check against the drawn outline, shown to DECIDE. In the outlines
        above the clipper's wrong reading also happens not to be buildable, so
        buildability alone already turns it down (the mutation check let "the
        reading is taken on trust" survive until this test existed; a search over
        12,000 more random outlines found no natural case). The safeguard is for
        the reading that is wrong AND buildable — simulated here: the strict union
        answers with the outline's whole bounding box, a perfectly good rectangle."""
        import pyclipper

        bow = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0))  # two lobes, 60,000 cm²
        box = [(0, 0), (400_000, 0), (400_000, 300_000), (0, 300_000)]
        monkeypatch.setattr(snapshot_module, "_strict_rings", lambda _subject, _fill: [box])
        lie = _strict_reading([])
        assert snapshot_module._buildable(lie) and regions_area(lie) == 120000.0  # buildable, and wrong
        assert not snapshot_module._matches_outline(bow, lie)
        regions = snapshot_module._resolved_regions(
            [snapshot_module._to_grid(bow)], pyclipper.PFT_NONZERO, outline=bow)
        assert regions is not None and regions != lie
        assert regions_area(regions) == pytest.approx(60000.0, rel=1e-3)
        assert snapshot_module._matches_outline(bow, regions)

    def test_matches_outline_tells_a_lost_piece_and_a_filled_hole(self) -> None:
        square = ((0.0, 0.0), (300.0, 0.0), (300.0, 300.0), (0.0, 300.0))
        pocket = ((100.0, 100.0), (100.0, 200.0), (200.0, 200.0), (200.0, 100.0))  # clockwise
        assert snapshot_module._matches_outline(square, ((square, ()),))
        assert not snapshot_module._matches_outline(square, ((square, (pocket,)),))  # a hole too many
        half = ((0.0, 0.0), (150.0, 0.0), (150.0, 300.0), (0.0, 300.0))
        assert not snapshot_module._matches_outline(square, ((half, ()),))  # a piece lost
        # a hair along the edges is not judged: the separation lives there
        inset = ((0.002, 0.002), (299.998, 0.002), (299.998, 299.998), (0.002, 299.998))
        assert snapshot_module._matches_outline(square, ((inset, ()),))

    def test_it_still_moves_and_turns_as_transform_only(self, canvas: CanvasView) -> None:
        bow = PolygonItem([QPointF(100.0, 100.0), QPointF(500.0, 400.0), QPointF(500.0, 100.0),
                           QPointF(100.0, 400.0)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(bow)
        item_id = str(bow.item_id)
        before = snapshot_records(canvas.scene())
        bow.moveBy(77.25, -13.5)
        moved = snapshot_records(canvas.scene())
        assert diff(before, moved) == SceneDiff(transform=(item_id,))
        apply_rotation(bow, 41.0)
        assert diff(moved, snapshot_records(canvas.scene())) == SceneDiff(transform=(item_id,))


# ── fix round 3 (P1): a stroke that touches itself ───────────────────────────


def _meeting_fence(width: float = 10.0, half: float = 100.0, depth: float = 300.0,
                   mirror: float = 1.0, at: tuple[float, float] = (1000.0, 1000.0)) -> Any:
    """A fence drawn round three sides of a rectangle and back to a point one
    stroke WIDTH above its start: its two butt ends meet corner to corner, in a
    single point. (The re-review's fence is ``_meeting_fence()``.)"""
    points = [(0.0, width), (-half * mirror, width), (-half * mirror, -depth), (half * mirror, -depth),
              (half * mirror, 0.0), (0.0, 0.0)]
    return _fence([(at[0] + x, at[1] + y) for x, y in points], width)


@pytest.fixture
def stroke_resolutions(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How often the STROKE branch of ``_resolved_regions`` ran (no drawn outline),
    with the number of rings it was handed each time."""
    calls: list[int] = []
    real = snapshot_module._resolved_regions

    def spy(rings: Any, fill: int, outline: Any = None, budget: Any = None, crossings: int = 0) -> Any:
        if outline is None:
            calls.append(len(rings))
        return real(rings, fill, outline, budget, crossings)

    monkeypatch.setattr(snapshot_module, "_resolved_regions", spy)
    snapshot_module._polyline_regions.cache_clear()
    return calls


class TestStrokesThatTouchThemselves:
    """Review round 3, P1. The report of round 2 called the stroke branch of the
    resolution a path no real stroke takes: 0 of 4,500 random strokes took it.
    It is LIVE: two butt ends that meet corner to corner make pyclipper return
    one ring that touches itself, and every such fence takes it — 15 of 15 the
    reviewer drew. With the fallback replaced by "no regions", 694 tests and all
    93 mutants still passed. Pinned here through real items."""

    def test_the_fence_of_the_review(self, canvas: CanvasView, stroke_resolutions: list[int]) -> None:
        from open_garden_planner.core.shadow_geometry import polyline_footprint

        fence, shed = _meeting_fence(), _rectangle()
        scene = canvas.scene()
        scene.addItem(fence)
        scene.addItem(shed)
        snapshot, skipped = snapshot_with_report(scene)
        assert skipped == [] and set(snapshot) == {str(fence.item_id), str(shed.item_id)}
        record = snapshot[str(fence.item_id)]

        # the premise: as it comes from the clipper the stroke is ONE ring that is no polygon
        (drawn,) = [tuple(ring) for ring in polyline_footprint(list(record.path), 10.0)]
        assert len(drawn) == 16 and not is_simple_ring(drawn)
        assert signed_area(drawn) == pytest.approx(10082.842, abs=1e-3)
        assert stroke_resolutions == [1]  # … so the fallback ran, once

        # what it handed out: one ring, no hole, the two ends a hair apart
        assert [len(ring) for ring in record.footprints] == [20] and record.holes == ()
        assert all(is_buildable_region(outer, holes) for outer, holes in record.regions)
        (ring,) = record.footprints
        assert is_simple_ring(ring)
        assert {(0.002, 149.998), (0.002, 140.002), (-0.002, 150.002), (-0.002, 159.998)} <= set(ring)
        # … the drawn stroke, drawn in by 0.002 cm all round: 2,033 cm of outline
        assert _boundary_distance(list(ring), list(drawn)) <= 3e-3
        assert 10082.842 - 5.0 < record.plan_area_cm2 < 10082.842 - 3.0

        # a stroke is not "resolved" in the record's sense: its rings never were the drawn
        # vertices, and what builds a fence reads the centre line — which is untouched
        assert "outline_resolved" not in record.params
        assert len(record.path) == 6 and record.path_width_cm == 10.0

        part = _solid(verify_builder(default_builder, record, plan_margin_cm=0.0))
        part.validate()
        assert _cap_area(part.mesh) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        sync = SceneSync(RecordingSink(), validate=True)
        sync.apply(snapshot)
        assert sync.failures == {}

        # an unchanged scene, a move, a turn
        assert diff(snapshot, snapshot_records(scene)).is_empty
        fence.moveBy(12.5, -7.25)
        moved = snapshot_records(scene)
        assert diff(snapshot, moved) == SceneDiff(transform=(str(fence.item_id),))
        apply_rotation(fence, 33.0)
        turned = snapshot_records(scene)
        assert diff(moved, turned) == SceneDiff(transform=(str(fence.item_id),))
        assert turned[str(fence.item_id)].footprints == record.footprints
        assert stroke_resolutions == [1]  # the item-local stroke did not change: nothing ran again

    @pytest.mark.parametrize("width", [4.0, 10.0, 25.0])
    @pytest.mark.parametrize(("half", "depth"), [(100.0, 300.0), (60.0, 80.0), (250.0, 65.0)])
    @pytest.mark.parametrize("mirror", [1.0, -1.0])
    def test_the_whole_family(self, canvas: CanvasView, stroke_resolutions: list[int],
                              width: float, half: float, depth: float, mirror: float) -> None:
        from open_garden_planner.core.shadow_geometry import polyline_footprint

        fence = _meeting_fence(width, half, depth, mirror)
        canvas.scene().addItem(fence)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and stroke_resolutions == [1]  # every one of them takes the fallback
        record = snapshot[str(fence.item_id)]
        assert len(record.footprints) == 1 and record.holes == ()
        assert all(is_buildable_region(outer, holes) for outer, holes in record.regions)
        drawn = polyline_footprint(list(record.path), width)
        outline = sum(math.dist(ring[i - 1], ring[i]) for ring in drawn for i in range(len(ring)))
        full = _signed_area_sum(drawn)
        assert full - 0.006 * outline <= record.plan_area_cm2 <= full  # the band, and no more
        part = _solid(verify_builder(default_builder, record, plan_margin_cm=0.0))
        part.validate()
        assert diff(snapshot, snapshot_records(canvas.scene())).is_empty

    def test_the_fence_turned_point_by_point(self, canvas: CanvasView,
                                             stroke_resolutions: list[int]) -> None:
        """Drawn at other angles the ends meet on the clipper's grid or miss it by
        a thousandth — the reviewer counted 111 of 400 through the fallback.
        Either way there is a record, and it is the stroke."""
        from open_garden_planner.core.shadow_geometry import polyline_footprint

        base = [(0.0, 10.0), (-100.0, 10.0), (-100.0, -300.0), (100.0, -300.0), (100.0, 0.0), (0.0, 0.0)]
        scene = canvas.scene()
        for degrees in range(0, 360, 9):
            turn = math.radians(degrees)
            fence = _fence([(1000.0 + x * math.cos(turn) - y * math.sin(turn),
                             1000.0 + x * math.sin(turn) + y * math.cos(turn)) for x, y in base])
            scene.addItem(fence)
            snapshot, skipped = snapshot_with_report(scene)
            record = snapshot[str(fence.item_id)]
            assert skipped == [], degrees
            assert all(is_buildable_region(outer, holes) for outer, holes in record.regions), degrees
            full = _signed_area_sum(polyline_footprint(list(record.path), 10.0))
            assert record.plan_area_cm2 == pytest.approx(full, abs=13.0), degrees
            scene.removeItem(fence)
        assert 4 <= len(stroke_resolutions) < 40  # some angles take the fallback, the right ones at least

    def test_a_reading_of_a_stroke_with_the_wrong_area_is_not_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The stroke branch has no drawn outline to hold a reading against; it
        holds it against the AREA of the stroke's own rings, less at most the
        band. Shown to decide, with a reading that is buildable and too large."""
        snapshot_module._polyline_regions.cache_clear()
        path = ((0.0, 155.0), (-100.0, 155.0), (-100.0, -155.0), (100.0, -155.0), (100.0, 145.0), (0.0, 145.0))
        box = [(-105_000, -160_000), (105_000, -160_000), (105_000, 160_000),
               (-105_000, 160_000)]  # the stroke's bounding box, filled
        monkeypatch.setattr(snapshot_module, "_strict_rings", lambda _subject, _fill: [box])
        lie = _strict_reading([])
        assert snapshot_module._buildable(lie) and regions_area(lie) == 210.0 * 320.0
        regions = snapshot_module._polyline_regions(path, 10.0)
        snapshot_module._polyline_regions.cache_clear()
        assert not isinstance(regions, snapshot_module._Refused) and regions != lie
        assert regions_area(regions) == pytest.approx(10082.842, abs=5.0)


# ── fix round 3 (P2-1 and the security finding): what an outline may cost ─────


@pytest.fixture
def fresh_outlines():
    """Every remembered answer about an outline dropped, before and after: a test
    that moves a bound must not read — or leave behind — an answer reached under
    another one."""
    from open_garden_planner.core.scene3d import polygon as polygon_module

    caches = (polygon_module._examined, snapshot_module._polyline_regions,
              snapshot_module._polygon_regions, snapshot_module._circle_regions,
              snapshot_module._convex_region)
    for cache in caches:
        cache.cache_clear()
    snapshot_module._reported.clear()
    yield
    for cache in caches:
        cache.cache_clear()


@pytest.fixture
def small_work_bound(monkeypatch: pytest.MonkeyPatch, fresh_outlines: None) -> int:
    """The work bound at 1 M units, so that a fence of sixty points is "too large"."""
    from open_garden_planner.core.scene3d import polygon as polygon_module

    monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", 1_000_000)
    return 1_000_000


def _never(what: str) -> Callable[..., Any]:
    def called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(f"{what} — on an outline that is refused for its size")
    return called


def _strict_reading(grid: Any) -> tuple[Any, ...]:
    """The FIRST reading of an outline as the resolution takes it: the union with
    ``StrictlySimple`` as a flat list, sorted into regions by ``group_rings``."""
    import pyclipper

    from open_garden_planner.core.scene3d.polygon import WorkBudget

    return snapshot_module._grouped(snapshot_module._strict_rings(grid, pyclipper.PFT_NONZERO),
                                    WorkBudget(budget=10**12))


def _watch_clipper(monkeypatch: pytest.MonkeyPatch, kept: list[Any] | None = None) -> list[str]:
    """Every question a resolution asks the clipper, in order: "plain" (the union)
    and "strict" (the union with StrictlySimple) — flat lists, both — or "band"
    (a difference with a band: the one tree). ``kept`` collects the answers."""
    asked: list[str] = []
    plain, strict, band_tree = (snapshot_module._plain_rings, snapshot_module._strict_rings,
                                snapshot_module._band_tree)

    def watched(name: str, real: Any) -> Any:
        def ask(*args: Any) -> Any:
            asked.append(name)
            answer = real(*args)
            if kept is not None:
                kept.append(answer)
            return answer

        return ask

    monkeypatch.setattr(snapshot_module, "_plain_rings", watched("plain", plain))
    monkeypatch.setattr(snapshot_module, "_strict_rings", watched("strict", strict))
    monkeypatch.setattr(snapshot_module, "_band_tree", watched("band", band_tree))
    return asked


def _watch_pyclipper(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, bool]]:
    """Every question put to a ``pyclipper.Pyclipper`` itself — below the snapshot's
    own seams, so that no seam can hide a tree: ("list" | "tree", the clip type,
    StrictlySimple), in order."""
    import pyclipper

    asked: list[tuple[str, int, bool]] = []
    real = pyclipper.Pyclipper

    class Watched:
        def __init__(self) -> None:
            self._clipper = real()
            self.StrictlySimple = False

        def AddPaths(self, *args: Any) -> Any:  # noqa: N802 - pyclipper's name
            return self._clipper.AddPaths(*args)

        def Execute(self, *args: Any) -> Any:  # noqa: N802
            self._clipper.StrictlySimple = self.StrictlySimple
            asked.append(("list", args[0], self.StrictlySimple))
            return self._clipper.Execute(*args)

        def Execute2(self, *args: Any) -> Any:  # noqa: N802
            self._clipper.StrictlySimple = self.StrictlySimple
            asked.append(("tree", args[0], self.StrictlySimple))
            return self._clipper.Execute2(*args)

    monkeypatch.setattr(pyclipper, "Pyclipper", Watched)
    return asked


def _no_clipper(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clipper must not be asked anything: neither union, no band."""
    monkeypatch.setattr(snapshot_module, "_union_rings", _never("the clipper was asked"))
    monkeypatch.setattr(snapshot_module, "_band_tree", _never("the clipper was asked"))


def _comb(teeth: int) -> tuple[tuple[float, float], ...]:
    """The ear clipper's worst case — every tooth waits for its neighbour —
    counter-clockwise: a ring whose cut costs several times what its size promises."""
    points = [(0.0, 0.0)]
    x = 0.0
    for _ in range(teeth):
        points += [(x, 200.0), (x + 5.0, 200.0), (x + 5.0, 10.0), (x + 10.0, 10.0)]
        x += 10.0
    points += [(x, 200.0), (x + 5.0, 200.0), (x + 5.0, 0.0)]
    return tuple(points[::-1])


def _scribble(count: int) -> list[tuple[float, float]]:
    """Points all over a plan of 20 m: every segment crosses about a quarter of the others."""
    return [(k * 7919 % 2003 * 10.0, k * 104729 % 1999 * 10.0) for k in range(count)]


class TestOutlinesTooLargeToCut:
    """Review round 3, P2-1. In round 2 a stroke beyond the bound was offset,
    sorted, tested for simplicity (quadratic), refused — and then resolved three
    more times, each to be refused again: 2,700 traced points took 2.59 s to say
    no, on every edit tick, where 2,600 took 1.86 s to build."""

    @staticmethod
    def _ring_of_points(count: int, radius: float = 400.0) -> list[tuple[float, float]]:
        return [(1500.0 + radius * math.cos(2.0 * math.pi * k / count),
                 1500.0 + radius * math.sin(2.0 * math.pi * k / count)) for k in range(count)]

    def test_a_stroke_beyond_the_bound_is_skipped_and_the_plan_goes_on(
        self, canvas: CanvasView, small_work_bound: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        points = self._ring_of_points(60)
        fence, shed = _fence([*points, points[0]]), _rectangle()
        scene = canvas.scene()
        scene.addItem(fence)
        scene.addItem(shed)
        monkeypatch.setattr(snapshot_module, "_resolved_regions", _never("the outline was resolved"))
        _no_clipper(monkeypatch)
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]  # the shed's 10,200 units fit
        (report,) = skipped
        assert (report.item_id, report.kind, report.reason, report.error_type) == (
            str(fence.item_id), "FENCE", SkipReason.OUTLINE_TOO_LARGE, "_OutlineTooLarge")
        assert "too large" in report.error_message and "MAX_REGION_WORK" in report.error_message
        assert snapshot_with_report(scene)[1] == skipped  # … and the same answer the next tick

    def test_every_step_of_a_stroke_is_paid_for_before_it_runs(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """The security finding: the cap sat BEHIND the work — the clipper had
        inflated the path and every ring had been read before anything was
        refused. Now each step has a price, and with one unit less than the
        price in the budget the step does not run. Pinned without a clock: for
        every step, the budget it needs, to the unit."""
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d.polygon import (
            RegionTooLargeError,
            WorkBudget,
            region_work,
        )

        points = [(round(x - 1500.0, 3), round(y - 1500.0, 3)) for x, y in self._ring_of_points(40)]
        path = (*points, points[0])  # a closed fence: its last segment touches its first
        steps = {"the pairs are tested": (polygon_module, "_touch"),
                 "the path is inflated": (snapshot_module, "polyline_footprint"),
                 "a ring is read": (snapshot_module, "_quantized"),
                 "an outer ring is asked": (polygon_module, "_ring_holds"),
                 "a region is cut": (polygon_module, "_cut")}
        whole = WorkBudget(budget=10**12)
        reached: dict[str, int] = {}

        def watching(label: str, real: Callable[..., Any]) -> Callable[..., Any]:
            def spy(*args: Any, **kwargs: Any) -> Any:
                reached.setdefault(label, whole.spent)
                return real(*args, **kwargs)
            return spy

        with monkeypatch.context() as patch:
            for label, (module, name) in steps.items():
                patch.setattr(module, name, watching(label, getattr(module, name)))
            ((outer, holes),) = snapshot_module._stroke_regions(path, 10.0, whole)
        assert list(reached) == list(steps) and len(holes) == 1  # every step, in this order
        assert 0 < reached["the pairs are tested"] < reached["the path is inflated"] < reached["a ring is read"]
        # a region is not cut unless the LEAST its cut can cost is still in the budget
        reached["a region is cut"] += region_work(outer, holes)
        assert reached["a region is cut"] <= whole.spent

        for label, (module, name) in steps.items():
            for budget, outcome in ((reached[label] - 1, RegionTooLargeError), (reached[label], AssertionError)):
                polygon_module._examined.cache_clear()
                with monkeypatch.context() as patch:
                    patch.setattr(module, name, _never(label))
                    with pytest.raises(outcome):
                        snapshot_module._stroke_regions(path, 10.0, WorkBudget(budget=budget))
        polygon_module._examined.cache_clear()
        assert snapshot_module._stroke_regions(path, 10.0, WorkBudget(budget=whole.spent)) == ((outer, holes),)
        polygon_module._examined.cache_clear()
        with pytest.raises(RegionTooLargeError):  # the whole of it, to the unit
            snapshot_module._stroke_regions(path, 10.0, WorkBudget(budget=whole.spent - 1))

    def test_a_stroke_refused_while_it_is_cut_is_not_resolved_either(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """A region whose SIZE passes and whose cut then outgrows the bound: the
        refusal is still for size, and no other reading is tried. (The stroke is
        handed in in the clipper's place: a comb, whose cut costs several times
        what its size promises.)"""
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d.polygon import (
            RegionTooLargeError,
            WorkBudget,
            cut_work,
            region_work,
        )

        teeth = _comb(80)
        monkeypatch.setattr(snapshot_module, "polyline_footprint", lambda _path, _width: [list(teeth)])
        path = ((0.0, 0.0), (100.0, 0.0))
        whole = WorkBudget(budget=10**12)
        assert snapshot_module._stroke_regions(path, 10.0, whole) == ((teeth, ()),)
        floor, spent = region_work(teeth), cut_work(teeth)
        before_the_cut = whole.spent - spent
        assert before_the_cut > 0 and before_the_cut + floor < spent
        polygon_module._examined.cache_clear()
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", (before_the_cut + floor + spent) // 2)
        monkeypatch.setattr(snapshot_module, "_resolved_regions", _never("the outline was resolved"))
        assert snapshot_module._polyline_regions(path, 10.0) is snapshot_module._TOO_LARGE
        with pytest.raises(RegionTooLargeError):  # … whatever is left in the item's own budget
            snapshot_module._stroke_regions(path, 10.0, WorkBudget(budget=10**12))

    @pytest.mark.parametrize("crossed", [False, True], ids=["a simple outline", "one that crosses itself"])
    def test_a_polygon_is_refused_before_it_is_tested_or_resolved(
        self, canvas: CanvasView, small_work_bound: int, monkeypatch: pytest.MonkeyPatch, crossed: bool
    ) -> None:
        from open_garden_planner.core.scene3d import polygon as polygon_module

        points = self._ring_of_points(120)
        if crossed:
            points[10], points[70] = points[70], points[10]
        house = PolygonItem([QPointF(x, y) for x, y in points], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        monkeypatch.setattr(polygon_module, "_is_simple", _never("the simplicity test ran"))
        monkeypatch.setattr(polygon_module, "touching_pairs", _never("its pairs were counted"))
        monkeypatch.setattr(snapshot_module, "_resolved_regions", _never("the outline was resolved"))
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]
        assert "too large" in skipped[0].error_message

    def test_a_reading_refused_for_its_size_ends_the_resolution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Three readings of an outline are tried. One refused for its SIZE is the
        last: the others are the same outline with a band cut away — larger."""
        import pyclipper

        from open_garden_planner.core.scene3d.polygon import RegionTooLargeError, WorkBudget

        def too_large(_regions: Any, budget: Any = None) -> bool:
            WorkBudget("a reading").refuse()

        asked = _watch_clipper(monkeypatch)
        monkeypatch.setattr(snapshot_module, "_buildable", too_large)
        bow = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0))
        with pytest.raises(RegionTooLargeError):
            snapshot_module._resolved_regions([snapshot_module._to_grid(bow)], pyclipper.PFT_NONZERO, outline=bow)
        assert asked == ["plain", "strict"]  # the two unions; no band was ever cut
        monkeypatch.setattr(snapshot_module, "_buildable", lambda _regions, _budget=None: False)
        asked.clear()
        assert snapshot_module._resolved_regions([snapshot_module._to_grid(bow)], pyclipper.PFT_NONZERO,
                                                 outline=bow) is snapshot_module._NO_READING
        assert asked == ["plain", "strict", "band", "band"]  # not for size: every reading gets its turn

    def test_resolving_an_outline_is_paid_for_to_the_unit(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """An outline that crosses itself, just under and just over what resolving
        it costs: with the budget it needs it is resolved, with one unit less it
        is refused — and the clipper is asked a stated number of times."""
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d.polygon import RegionTooLargeError, WorkBudget

        ring = [(round(x - 1500.0, 7), round(y - 1500.0, 7)) for x, y in self._ring_of_points(300)]
        ring[10], ring[150] = ring[150], ring[10]
        outline = tuple(ring)
        asked = _watch_clipper(monkeypatch)
        whole = WorkBudget(budget=10**12)
        regions, resolved = snapshot_module._outline_regions(outline, whole)
        assert resolved and not isinstance(regions, snapshot_module._Refused) and len(regions) >= 2
        # two unions, then a band at most twice
        assert asked in (["plain", "strict"], ["plain", "strict", "band"], ["plain", "strict", "band", "band"])
        polygon_module._examined.cache_clear()
        assert snapshot_module._outline_regions(outline, WorkBudget(budget=whole.spent)) == (regions, True)
        polygon_module._examined.cache_clear()
        with pytest.raises(RegionTooLargeError):
            snapshot_module._outline_regions(outline, WorkBudget(budget=whole.spent - 1))
        # … and through the remembered front, with the bound itself moved by one unit
        for bound, answer in ((whole.spent - 1, (snapshot_module._TOO_LARGE, False)),
                              (whole.spent, (regions, True))):
            monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", bound)
            polygon_module._examined.cache_clear()
            snapshot_module._polygon_regions.cache_clear()
            assert snapshot_module._polygon_regions(outline) == answer
        assert whole.spent < 150_000_000  # with the real bound an outline like this is resolved

    def test_an_outline_is_not_resolved_at_any_price(self, fresh_outlines: None) -> None:
        """What the three readings may cost together is what is left of ONE budget:
        a crossed outline of 300 vertices fits, one of 4,000 does not — its size
        as a plain ring would (3,500 fit), resolving it would not."""
        from open_garden_planner.core.scene3d.polygon import exceeds_work_bound

        def crossed(count: int) -> tuple[tuple[float, float], ...]:
            ring = [(round(x - 1500.0, 7), round(y - 1500.0, 7)) for x, y in self._ring_of_points(count)]
            ring[10], ring[count // 2] = ring[count // 2], ring[10]
            return tuple(ring)

        regions, resolved = snapshot_module._polygon_regions(crossed(300))
        assert resolved and not isinstance(regions, snapshot_module._Refused)
        large = crossed(3_400)
        assert not exceeds_work_bound(large)
        assert snapshot_module._polygon_regions(large) == (snapshot_module._TOO_LARGE, False)


class TestTheInputIsBoundedBeforeTheWork:
    """The security finding of fix round 3, as the reviewer put it: the trust
    boundary is the plan file, and this code runs on the GUI thread on every edit
    tick. (1) The expensive work ran BEFORE any bound on the input. (2) The bound
    was on the largest element where the cost is a sum. Every test here asserts
    what was — or never was — called; none reads a clock."""

    def test_a_polyline_of_200_000_points_is_answered_with_one_comparison(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        line = PolylineItem([QPointF(k * 0.5, (k % 7) * 3.0) for k in range(200_000)],
                            object_type=ObjectType.FENCE)
        shed = _rectangle()
        scene = canvas.scene()
        scene.addItem(line)
        scene.addItem(shed)
        read: list[Any] = []
        real = snapshot_module.item_outline
        monkeypatch.setattr(snapshot_module, "item_outline",
                            lambda item, at_date=None: (read.append(item), real(item, at_date))[1])
        monkeypatch.setattr(snapshot_module, "polyline_footprint", _never("the path was inflated"))
        remembered = snapshot_module._polyline_regions.cache_info()
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]  # the rest of the plan has its records
        assert read == [shed]  # not ONE vertex of the line was read
        (report,) = skipped
        assert (report.item_id, report.kind, report.reason) == (
            str(line.item_id), "FENCE", SkipReason.OUTLINE_TOO_LARGE)
        assert "200,000 vertices" in report.error_message and "MAX_ITEM_VERTICES" in report.error_message
        assert snapshot_module._polyline_regions.cache_info() == remembered  # nothing looked up, nothing kept
        assert snapshot_with_report(scene)[1] == skipped

    def test_a_polygon_of_100_000_vertices_is_answered_with_one_comparison(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d import ring_area

        count = 100_000
        huge = PolygonItem([QPointF(5000.0 * math.cos(2.0 * math.pi * k / count),
                                    5000.0 * math.sin(2.0 * math.pi * k / count)) for k in range(count)],
                           object_type=ObjectType.HOUSE)
        shed = _rectangle()
        scene = canvas.scene()
        scene.addItem(huge)
        scene.addItem(shed)
        read: list[Any] = []
        real = snapshot_module.item_outline
        monkeypatch.setattr(snapshot_module, "item_outline",
                            lambda item, at_date=None: (read.append(item), real(item, at_date))[1])
        ring_area.cache_clear()
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)] and read == [shed]
        assert [(s.item_id, s.reason) for s in skipped] == [(str(huge.item_id), SkipReason.OUTLINE_TOO_LARGE)]
        # nothing about it was hashed or kept: the shed's ring is all there is (and a
        # rectangle is judged by arithmetic: nothing was cut)
        assert snapshot_module._polygon_regions.cache_info().entries == 0
        assert polygon_module._examined.cache_info().entries == 0
        assert ring_area.cache_info().vertices <= 2 * (4 + 8)

    def test_an_outline_under_the_cap_and_beyond_the_bound_is_sized_up_not_tested(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """10,000 vertices: read (it is under ``MAX_ITEM_VERTICES``), and refused
        from the LENGTH of its ring — no pair of its edges is looked at, and it
        never becomes a key of the verdicts."""
        from open_garden_planner.core.scene3d import polygon as polygon_module

        count = 10_000
        large = PolygonItem([QPointF(5000.0 * math.cos(2.0 * math.pi * k / count),
                                     5000.0 * math.sin(2.0 * math.pi * k / count)) for k in range(count)],
                            object_type=ObjectType.HOUSE)
        canvas.scene().addItem(large)
        monkeypatch.setattr(polygon_module, "_is_simple", _never("the simplicity test ran"))
        monkeypatch.setattr(polygon_module, "touching_pairs", _never("its pairs were counted"))
        _no_clipper(monkeypatch)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]
        assert polygon_module._examined.cache_info().entries == 0

    @pytest.mark.parametrize(
        ("label", "points", "blocks"),
        [("a scribble of 800 points", _scribble(800), 2),  # it crosses itself 26,000 times
         ("2,000 teeth standing side by side",  # no crossing at all — and 0.33 s in the clipper's sweep
          [(k * 30.0, 1000.0 + k * 0.37 if k % 2 else -k * 0.41) for k in range(2_000)], 0),
         ("a line of 10,000 points", [(k * 20.0, (k % 5) * 40.0) for k in range(10_000)], 0)],
    )
    def test_a_path_the_clipper_would_choke_on_is_never_handed_to_it(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None,
        label: str, points: list[tuple[float, float]], blocks: int,
    ) -> None:
        from open_garden_planner.core.scene3d import polygon as polygon_module

        fence, shed = _fence(points), _rectangle()
        scene = canvas.scene()
        scene.addItem(fence)
        scene.addItem(shed)
        tested = 0
        real = polygon_module._touch

        def counting(*args: Any) -> Any:
            nonlocal tested
            tested += 1
            return real(*args)

        monkeypatch.setattr(polygon_module, "_touch", counting)
        monkeypatch.setattr(snapshot_module, "polyline_footprint", _never("the path was inflated"))
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)], label
        assert [(s.item_id, s.reason) for s in skipped] == [(str(fence.item_id), SkipReason.OUTLINE_TOO_LARGE)]
        # what saying no took: the pairs of the path, a block of 512 segments at a time
        assert tested == blocks, label

    def test_an_outline_that_crosses_itself_too_often_is_never_handed_to_the_clipper(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """800 vertices scribbled at random across a plan cross 73,000 times. They
        passed the round-3 check, which counted vertices (1,085 allowed) — and the
        last reading alone took the clipper ten seconds. What a reading costs is
        the CROSSINGS: here 59,000 of them, and the first reading alone is beyond
        the budget."""
        house = PolygonItem([QPointF(x, y) for x, y in _scribble(1_200)], object_type=ObjectType.HOUSE)
        shed = _rectangle()
        scene = canvas.scene()
        scene.addItem(house)
        scene.addItem(shed)
        _no_clipper(monkeypatch)
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]
        assert [(s.item_id, s.reason) for s in skipped] == [(str(house.item_id), SkipReason.OUTLINE_TOO_LARGE)]

    @staticmethod
    def _discs(count: int, corners: int) -> list[list[tuple[float, float]]]:
        return [[(k % 60 * 100.0 + 40.0 * math.cos(2.0 * math.pi * j / corners),
                  k // 60 * 100.0 + 40.0 * math.sin(2.0 * math.pi * j / corners)) for j in range(corners)]
                for k in range(count)]

    def test_regions_that_each_fit_the_bound_do_not_fit_it_together(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """The bound sat on the LARGEST outer ring. A stroke that comes back as
        540 outer rings of 30 vertices — the clipper's answer is not ours to
        choose, so it is handed in here — has no large ring at all."""
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d.polygon import MAX_REGION_WORK, region_work

        made = self._discs(540, 30)
        each = region_work(snapshot_module._quantized(made[0]))
        assert 300 * each < MAX_REGION_WORK < 540 * each  # each one a 360th of the bound; all of them beyond it
        monkeypatch.setattr(snapshot_module, "polyline_footprint", lambda _path, _width: made)
        cuts = 0
        real = polygon_module._cut

        def counting(outer: Any, holes: Any, work: Any) -> Any:
            nonlocal cuts
            cuts += 1
            return real(outer, holes, work)

        monkeypatch.setattr(polygon_module, "_cut", counting)
        monkeypatch.setattr(snapshot_module, "_resolved_regions", _never("the outline was resolved"))
        fence, shed = _fence([(0.0, 0.0), (500.0, 0.0)]), _rectangle()
        scene = canvas.scene()
        scene.addItem(fence)
        scene.addItem(shed)
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]
        assert [(s.item_id, s.reason) for s in skipped] == [(str(fence.item_id), SkipReason.OUTLINE_TOO_LARGE)]
        # it stopped when the budget was gone: 300-odd of the 540 were cut (and the shed)
        assert 300 < cuts <= MAX_REGION_WORK // each + 1

    def test_what_fits_together_is_built(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """… and the bound is on the work, not on the number: 300 such rings are a
        third of it, and they are a record."""
        made = self._discs(300, 30)
        monkeypatch.setattr(snapshot_module, "polyline_footprint", lambda _path, _width: made)
        fence = _fence([(0.0, 0.0), (500.0, 0.0)])
        canvas.scene().addItem(fence)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and len(snapshot[str(fence.item_id)].footprints) == 300

    def test_more_rings_than_an_item_may_hold_are_refused_unread(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        from open_garden_planner.core.scene3d.polygon import MAX_ITEM_VERTICES

        made = self._discs(5_000, 4)  # 20,000 vertices in 5,000 squares
        assert sum(len(ring) for ring in made) > MAX_ITEM_VERTICES
        monkeypatch.setattr(snapshot_module, "polyline_footprint", lambda _path, _width: made)
        monkeypatch.setattr(snapshot_module, "_quantized", _never("a ring was read"))
        monkeypatch.setattr(snapshot_module, "group_rings", _never("the rings were sorted"))
        fence = _fence([(0.0, 0.0), (500.0, 0.0)])
        canvas.scene().addItem(fence)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]

    def test_what_the_resolution_makes_is_counted_before_it_is_read(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """A zigzag over a zigzag: 22 + 22 lines cross 484 times and resolve into
        hundreds of cells. The cells are paid for — ring by ring, vertex by vertex
        — before one of them is read, out of the outline's one budget.

        The grid is 22 x 22, not 25 x 25: after #451 re-priced a bridge block, the
        625-crossing grid's resolution needs more than ``MAX_REGION_WORK`` in the
        best case and is refused from its size (pinned by the next test). 22 x 22
        still makes 286 regions and spends 25.6 M units, so the charge order is
        what this test sees."""
        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d.polygon import RegionTooLargeError, WorkBudget

        path: list[tuple[float, float]] = []
        for row in range(22):
            path += [(-50.0, row * 50.0), (1250.0, row * 50.0)][::1 if row % 2 == 0 else -1]
        for column in range(22):
            x = column * 50.0 + 25.0
            path += [(x, -50.0), (x, 1250.0)][::1 if column % 2 == 0 else -1]
        outline = tuple(path)
        whole = WorkBudget(budget=10**12)
        reached: list[int] = []
        real = snapshot_module._quantized

        def watching(ring: Any) -> Any:
            reached.append(whole.spent)
            return real(ring)

        with monkeypatch.context() as patch:
            patch.setattr(snapshot_module, "_quantized", watching)
            regions, resolved = snapshot_module._outline_regions(outline, whole)
        assert resolved and not isinstance(regions, snapshot_module._Refused)
        assert len(regions) >= 200  # 286 measured; the grid is not a handful of cells
        assert reached and reached[0] > 484 * 3_100  # the crossings alone, before the first reading
        polygon_module._examined.cache_clear()
        monkeypatch.setattr(snapshot_module, "_quantized", _never("a reading was read"))
        with pytest.raises(RegionTooLargeError):  # one unit short of what reading it costs
            snapshot_module._outline_regions(outline, WorkBudget(budget=reached[0] - 1))
        polygon_module._examined.cache_clear()
        with pytest.raises(AssertionError, match="a reading was read"):
            snapshot_module._outline_regions(outline, WorkBudget(budget=reached[0]))

    def test_a_625_crossing_grid_is_refused_from_its_size_after_the_reprice(
        self, fresh_outlines: None
    ) -> None:
        """The stated cost of #451's higher block price: a 25 x 25 line grid (625
        crossings) resolved before the re-price and is now refused from its size —
        the least its resolution can cost is over ``MAX_REGION_WORK``. It is
        refused early (8.5 M units, not the bound), and the 2D plan is untouched."""
        from open_garden_planner.core.scene3d.polygon import (
            MAX_REGION_WORK,
            RegionTooLargeError,
            WorkBudget,
        )

        path: list[tuple[float, float]] = []
        for row in range(25):
            path += [(-50.0, row * 50.0), (1250.0, row * 50.0)][::1 if row % 2 == 0 else -1]
        for column in range(25):
            x = column * 50.0 + 25.0
            path += [(x, -50.0), (x, 1250.0)][::1 if column % 2 == 0 else -1]
        budget = WorkBudget(budget=10**12)
        with pytest.raises(RegionTooLargeError, match=f"MAX_REGION_WORK = {MAX_REGION_WORK:,}"):
            snapshot_module._outline_regions(tuple(path), budget)
        assert budget.spent < MAX_REGION_WORK // 10, "refused before the bound was burned"

    def test_sorting_what_came_back_is_paid_for_too(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """2,000 small outer rings, each with a hole: every hole asks every outer
        ring. Reading them fits the budget; sorting them is twenty times the bound
        — and is refused as a matter of SIZE, not taken for a stroke that could
        not be sorted and handed to the resolution."""
        from open_garden_planner.core.scene3d import polygon as polygon_module

        made: list[list[tuple[float, float]]] = []
        for k in range(2_000):
            x, y = (k % 100) * 100.0, (k // 100) * 100.0
            made += [[(x, y), (x + 80.0, y), (x + 80.0, y + 80.0), (x, y + 80.0)],
                     [(x + 20.0, y + 60.0), (x + 60.0, y + 60.0), (x + 60.0, y + 20.0), (x + 20.0, y + 20.0)]]
        monkeypatch.setattr(snapshot_module, "polyline_footprint", lambda _path, _width: made)
        monkeypatch.setattr(polygon_module, "_ring_holds", _never("an outer ring was asked"))
        monkeypatch.setattr(snapshot_module, "_resolved_regions", _never("the outline was resolved"))
        fence = _fence([(0.0, 0.0), (500.0, 0.0)])
        canvas.scene().addItem(fence)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]

    def test_an_outline_handed_in_from_elsewhere_meets_the_same_cap(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """The item's stored count is asked first. The two functions behind it do
        not rely on that: handed more vertices than an item may have they refuse
        before they touch one."""
        from open_garden_planner.core.scene3d.polygon import MAX_ITEM_VERTICES
        from open_garden_planner.ui.canvas.footprints import ItemOutline

        points = tuple((float(k), float(k % 3)) for k in range(MAX_ITEM_VERTICES + 1))

        class Frame:
            def local_ring(self, _points: Any) -> Any:
                raise AssertionError("the outline was moved into the frame")

        for shape in ("polyline", "polygon"):
            with pytest.raises(snapshot_module._OutlineTooLarge, match="MAX_ITEM_VERTICES"):
                snapshot_module._regions_of(ItemOutline(shape, (0.0, 0.0), points, width_cm=10.0), Frame())
        monkeypatch.setattr(snapshot_module, "_without_repeats", _never("the ring was walked"))
        assert snapshot_module._polygon_regions(points) == (snapshot_module._TOO_LARGE, False)
        assert snapshot_module._polygon_regions.cache_info().entries == 0  # … and it is no key

    def test_the_strict_union_is_not_asked_about_rings_it_would_compare_for_too_long(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """StrictlySimple compares every vertex of a ring with every other. A traced
        outline of 4,400 vertices that crosses itself ONCE can pay for the plain
        union; the 58 M units of that comparison it cannot — so the strict union
        is never asked."""
        count = 4_400
        ring = [(round(3000.0 * math.cos(2.0 * math.pi * k / count), 7),
                 round(3000.0 * math.sin(2.0 * math.pi * k / count), 7)) for k in range(count)]
        ring[2000], ring[2001] = ring[2001], ring[2000]
        asked = _watch_clipper(monkeypatch)
        assert snapshot_module._polygon_regions(tuple(ring)) == (snapshot_module._TOO_LARGE, False)
        assert asked == ["plain"]  # the plain union, and nothing after it

    def test_the_price_list_of_a_resolution_once_by_hand(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """Every call of the clipper, every ring read and every comparison is paid
        for. A bow-tie through all three readings, added up from the price list."""
        import pyclipper

        from open_garden_planner.core.scene3d.polygon import WorkBudget, region_cost, stack_height

        prices = snapshot_module
        bow = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0))
        grid = [snapshot_module._to_grid(bow)]
        answers: list[Any] = []  # the plain union's rings, the strict union's rings, then a tree per band

        def reading(rings: list[Any]) -> int:
            return prices._RING_UNITS * len(rings) + prices._RING_VERTEX_UNITS * sum(len(r) for r in rings)

        asked = _watch_clipper(monkeypatch, answers)
        stack = stack_height(grid, closed=True)
        two_unions = (2 * prices._CLIP_UNITS + (prices._UNION_VERTEX_UNITS + prices._STRICT_VERTEX_UNITS) * 4
                      + 2 * prices._UNION_STACK_UNITS * stack * 4
                      + (prices._UNION_CROSSING_UNITS + prices._STRICT_CROSSING_UNITS) * 1)

        # the first reading holds: two unions, their rings, the regions' cuts, one comparison
        whole = WorkBudget(budget=10**12)
        regions = snapshot_module._resolved_regions(grid, pyclipper.PFT_NONZERO, bow, whole, 1)
        assert len(regions) == 2 and asked == ["plain", "strict"]
        paths = answers[0]
        assert sorted(len(path) for path in paths) == [3, 3] == sorted(len(ring) for ring in answers[1])
        # (two outer rings and no hole: sorting them asks nothing, and costs nothing)
        first = (two_unions + reading(paths) + prices._STRICT_SQUARE_UNITS * 18 + reading(answers[1]))
        compared = prices._LATTICE ** 2 * (prices._OUTLINE_CHECK_UNITS * 4 + prices._REGION_CHECK_UNITS * 6)
        assert whole.spent == first + sum(region_cost(outer, holes) for outer, holes in regions) + compared
        # two calls; four vertices; their stack; one crossing; two rings of three read, twice;
        # their squares; the comparison on the lattice; two triangles cut
        assert stack == 4
        assert whole.spent == (20_000 + 6_000 + 480 + 3_100 + 10_000 + 54 + 10_000
                               + 2_304 * 110 + 2 * 7_050) == 317_174

        # no reading holds: both bands are cut and read as well (the regions are not looked at here)
        answers.clear()
        asked.clear()
        monkeypatch.setattr(snapshot_module, "_buildable", lambda _regions, _budget=None: False)
        whole = WorkBudget(budget=10**12)
        assert snapshot_module._resolved_regions(grid, pyclipper.PFT_NONZERO, bow, whole, 1) is snapshot_module._NO_READING
        assert asked == ["plain", "strict", "band", "band"]
        trees = answers
        along_the_union = (prices._CLIP_UNITS + prices._BAND_CROSSING_UNITS * 1 + 6 * (
            prices._OFFSET_POINT_UNITS + prices._BAND_STACK_UNITS * stack_height(paths, closed=True)))
        along_the_ring = (prices._CLIP_UNITS + prices._OWN_BAND_CROSSING_UNITS * 1 + 4 * (
            prices._OFFSET_POINT_UNITS + prices._BAND_STACK_UNITS * stack))
        assert whole.spent == (first + along_the_union + reading(snapshot_module._tree_rings(trees[2]))
                               + along_the_ring + reading(snapshot_module._tree_rings(trees[3])))

    def test_a_ridge_is_read_at_its_two_ends_only(self) -> None:
        """A HOUSE's ridge is another item's geometry; of its points the snapshot
        reads the first and the last, whatever lies between (and a ROOF_RIDGE
        gets no record of its own, so it is never inflated)."""
        ridge = PolylineItem([QPointF(float(k), 0.0) for k in range(50_000)], object_type=ObjectType.ROOF_RIDGE)
        frame = snapshot_module._frame_of(ridge, (0.0, 0.0), rotatable=True)
        assert snapshot_module._ridge_param(frame, ridge) == ((0.0, 0.0), (49_999.0, 0.0))
        assert "ROOF_RIDGE" in snapshot_module._NO_RECORD_KINDS


# ── fix round 3 (P2-3): every shape is asked the predicate ───────────────────


class TestEveryShapeIsAsked:
    """The docs said "every region of every record satisfies
    ``is_buildable_region``" while circles, ellipses and rectangles were taken on
    trust as convex by construction. On the record grid they are not always
    polygons at all.

    Fix round 4: they are JUDGED, and without a cut. Asking the cut predicate of
    every circle cut a 24-gon per new radius, and a date scrub gives every dated
    plant a new radius per tick (bench_large: 12 ms a snapshot became 33). A ring
    that is convex by construction is judged by arithmetic on its corners; only
    one that is not convex on the record grid is asked the cut."""

    @pytest.fixture
    def asked(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
        """What was asked: of the cut predicate, and of the arithmetic on corners."""
        seen: dict[str, list[Any]] = {"cut": [], "corners": []}
        cut, corners = snapshot_module.is_buildable_region, snapshot_module.is_convex_ring

        def spy_cut(outer: Any, holes: Any = ()) -> bool:
            seen["cut"].append((outer, tuple(holes)))
            return cut(outer, holes)

        def spy_corners(ring: Any) -> bool:
            seen["corners"].append((ring, ()))
            return corners(ring)

        monkeypatch.setattr(snapshot_module, "is_buildable_region", spy_cut)
        monkeypatch.setattr(snapshot_module, "is_convex_ring", spy_corners)
        for cache in (snapshot_module._circle_regions, snapshot_module._polygon_regions,
                      snapshot_module._polyline_regions, snapshot_module._convex_region):
            cache.cache_clear()
        return seen

    @pytest.mark.parametrize("shape", sorted(FACTORIES))
    def test_all_five_shapes(self, canvas: CanvasView, asked: dict[str, list[Any]], shape: str) -> None:
        item = FACTORIES[shape]()
        canvas.scene().addItem(item)
        record = snapshot_records(canvas.scene())[str(item.item_id)]
        assert record.regions
        if shape in VERTEX_BACKED:  # a drawn outline, a stroke: the cut
            assert all(region in asked["cut"] for region in record.regions), shape
        elif shape in RECT_BACKED:  # convex by construction: its corners, and no cut
            assert all(region in asked["corners"] for region in record.regions) and asked["cut"] == []
        else:  # a circle of a centimetre and more: its radius says it all
            assert asked == {"cut": [], "corners": []}
            assert record.params["radius_cm"] >= snapshot_module._ROUND_FROM_CM
        assert all(is_buildable_region(outer, holes) for outer, holes in record.regions)

    def test_from_the_floor_on_a_circle_is_convex_without_a_look_at_its_corners(self) -> None:
        """``_ROUND_FROM_CM`` skips the arithmetic; the arithmetic skips the cut. So
        the floor must imply the arithmetic: from 1e-3 cm to 10 km, 600 radii."""
        from open_garden_planner.core.scene3d import quantize_cm
        from open_garden_planner.core.scene3d.polygon import is_convex_ring

        floor = snapshot_module._ROUND_FROM_CM
        radii = [floor, floor * 1.0000001, 1e6] + [floor * 10.0 ** (9.0 * k / 600.0) for k in range(600)]
        for radius in radii:
            ring = snapshot_module._circle_ring(quantize_cm(radius))
            assert len(ring) == 24 and is_convex_ring(ring), radius
        assert not is_convex_ring(snapshot_module._circle_ring(2e-7))  # … and below it the corners decide

    def test_a_plan_of_circles_rectangles_and_ellipses_is_not_cut_at_all(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """The op count behind the date scrub: 300 plants of 300 radii, 40 beds, 40
        ponds — turned, so that their rings are not axis-parallel — and not one
        region is cut by the snapshot. (The builder cuts what it builds.)"""
        from open_garden_planner.core.scene3d import polygon as polygon_module

        monkeypatch.setattr(polygon_module, "_cut", _never("a convex shape was cut by the snapshot"))
        scene = canvas.scene()
        for k in range(300):
            scene.addItem(CircleItem(40.0 * (k % 30), 40.0 * (k // 30), 5.0 + 0.137 * k,
                                     object_type=ObjectType.TREE))
        for k in range(40):
            bed = RectangleItem(100.0 * k, 900.0, 80.0 + k, 30.0 + 0.5 * k, object_type=ObjectType.RAISED_BED)
            pond = EllipseItem(100.0 * k, 1100.0, 60.0 + k, 25.0 + 0.3 * k, object_type=ObjectType.POND_POOL)
            for item in (bed, pond):
                scene.addItem(item)
                apply_rotation(item, 7.0 * k + 3.0)
        snapshot, skipped = snapshot_with_report(scene)
        assert skipped == [] and len(snapshot) == 380
        assert snapshot_with_report(scene) == (snapshot, [])

    def test_the_arithmetic_and_the_cut_agree_on_what_the_canvas_can_make(
        self, canvas: CanvasView, fresh_outlines: None
    ) -> None:
        """``is_convex_ring(ring)`` must imply ``is_buildable_region(ring)`` — else a
        record would exist that the default builder cannot build. Over the rings the
        snapshot itself makes: 300 shapes from 1e-6 cm to 1e5 cm, turned and squeezed."""
        from open_garden_planner.core.scene3d.polygon import is_convex_ring

        scene = canvas.scene()
        rng = np.random.default_rng(385)
        made = []
        for k in range(300):
            a, b = (float(10.0 ** rng.uniform(-6.0, 5.0)) for _ in range(2))
            item = (CircleItem(0.0, 0.0, a, object_type=ObjectType.TRAMPOLINE) if k % 3 == 0 else
                    EllipseItem(0.0, 0.0, a, b, object_type=ObjectType.POND_POOL) if k % 3 == 1 else
                    RectangleItem(0.0, 0.0, a, b, object_type=ObjectType.TOOL_SHED))
            scene.addItem(item)
            if k % 3:
                apply_rotation(item, float(rng.uniform(0.0, 360.0)))
            made.append(item)
        snapshot, skipped = snapshot_with_report(scene)
        assert len(snapshot) + len(skipped) == 300 and len(snapshot) > 250
        by_corners = 0
        for record in snapshot.values():
            ((ring, holes),) = record.regions
            assert holes == () and is_buildable_region(ring)  # the promise, for every record
            by_corners += is_convex_ring(ring)
        assert by_corners > 200  # … and most of them without the cut (the rest are slivers)
        assert all(s.reason is SkipReason.OUTLINE_UNBUILDABLE for s in skipped)

    @pytest.mark.parametrize(
        ("label", "make", "kind"),
        [("a circle of radius 2e-7 cm",
          lambda: CircleItem(100.0, 100.0, 2e-7, object_type=ObjectType.TRAMPOLINE), "TRAMPOLINE"),
         ("an ellipse 300 cm by 2e-7 cm",
          lambda: EllipseItem(100.0, 100.0, 300.0, 2e-7, object_type=ObjectType.POND_POOL), "POND_POOL")],
    )
    def test_a_shape_that_is_no_polygon_on_the_record_grid_is_reported(
        self, canvas: CanvasView, label: str, make: Callable[[], Any], kind: str
    ) -> None:
        """Found by the re-review: such an item got a record whose ring is not
        simple, and ``prism_mesh`` raised on it. Honest, and against the promise."""
        snapshot_module._reported.clear()
        item = make()
        canvas.scene().addItem(item)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {}, label
        assert [(s.item_id, s.kind, s.reason) for s in skipped] == [
            (str(item.item_id), kind, SkipReason.OUTLINE_UNBUILDABLE)], label

    def test_an_ellipse_in_a_group_scaled_to_nothing(self, canvas: CanvasView) -> None:
        item = _ellipse()
        scene = canvas.scene()
        scene.addItem(item)
        group = QGraphicsItemGroup()
        scene.addItem(group)
        group.addToGroup(item)
        group.setTransform(QTransform.fromScale(1e-9, 1e-9))
        snapshot, skipped = snapshot_with_report(scene)
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_UNBUILDABLE]

    @pytest.mark.parametrize("size", [1e-3, 3e-6, 4e-7])
    def test_what_is_small_and_still_a_polygon_is_built(self, canvas: CanvasView, size: float) -> None:
        for item in (CircleItem(100.0, 100.0, max(size, 5e-7), object_type=ObjectType.TRAMPOLINE),
                     EllipseItem(100.0, 300.0, 300.0, size, object_type=ObjectType.POND_POOL),
                     RectangleItem(100.0, 500.0, 300.0, size, object_type=ObjectType.TOOL_SHED)):
            canvas.scene().addItem(item)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and len(snapshot) == 3
        for record in snapshot.values():
            assert all(is_buildable_region(outer, holes) for outer, holes in record.regions)
            prism_mesh(record.footprints, 100.0, record.holes).validate()


# ── P2-3: one bad item must not blank the view ────────────────────────────────


def _break_species(item: Any) -> None:
    item.metadata["plant_species"] = {"scientific_name": None}  # the reviewer's case


def _break_species_name(item: Any) -> None:
    item.metadata["plant_species"] = {"common_name": 5}


def _break_category(item: Any) -> None:
    item.plant_category = "CONIFER"  # a string where the enum belongs


def _break_pattern(item: Any) -> None:
    item.fill_pattern = "GRASS"  # a string where the enum belongs


def _break_position(item: Any) -> None:
    item.setPos(float("nan"), 0.0)


#: one malformed item per group of record fields: (what breaks, the exception)
BREAKERS: dict[str, tuple[Callable[[Any], None], type[Exception]]] = {
    "geometry: species key": (_break_species, AttributeError),
    "geometry: species name": (_break_species_name, AttributeError),
    "geometry: plant category": (_break_category, AttributeError),
    "material: fill pattern": (_break_pattern, AttributeError),
    "transform: position": (_break_position, ValueError),
}


class TestContainment:
    """Review P2-3: ``plant_species = {"scientific_name": None}`` on ONE plant
    raised ``AttributeError`` out of ``snapshot_records`` — no 3D view for the
    whole plan. Now the item is left out, reported, and everything else is there."""

    @pytest.fixture(autouse=True)
    def _forget_what_was_logged(self) -> None:
        snapshot_module._reported.clear()

    @pytest.mark.parametrize("label", sorted(BREAKERS))
    def test_a_malformed_item_is_left_out_reported_and_logged_once(
        self, canvas: CanvasView, caplog: pytest.LogCaptureFixture, label: str
    ) -> None:
        breaker, error_type = BREAKERS[label]
        scene = canvas.scene()
        good = CircleItem(100.0, 100.0, 30.0, object_type=ObjectType.TREE)
        bad = CircleItem(300.0, 100.0, 30.0, object_type=ObjectType.TREE)
        also_good = _rectangle()
        for item in (good, bad, also_good):
            scene.addItem(item)
        healthy, nothing = snapshot_with_report(scene)
        assert len(healthy) == 3 and nothing == []

        breaker(bad)
        with caplog.at_level(logging.WARNING, logger=snapshot_module.__name__):
            snapshot, report = snapshot_with_report(scene)
            _again, report_again = snapshot_with_report(scene)  # the pipeline snapshots on every edit
            assert snapshot_records(scene) == snapshot  # and without a list it still does not raise

        bad_id = str(bad.item_id)
        assert set(snapshot) == {str(good.item_id), str(also_good.item_id)}  # the rest is there
        assert diff(healthy, snapshot) == SceneDiff(removed=(bad_id,))
        (skipped,) = report
        assert isinstance(skipped, SkippedItem)
        assert (skipped.item_id, skipped.kind) == (bad_id, "TREE")
        assert skipped.reason is SkipReason.RECORD_FAILED and skipped.reason == "record_failed"
        assert skipped.error_type == error_type.__name__ and skipped.error_message
        assert report_again == report  # observable every time, and two reports are EQUAL …
        mine = [r for r in caplog.records if bad_id in r.getMessage()]
        assert len(mine) == 1  # … logged once
        assert mine[0].levelno == logging.ERROR and mine[0].exc_info is not None
        logged = mine[0].exc_info[1]  # the exception itself goes to the log, and only there
        assert type(logged).__name__ == skipped.error_type and str(logged) == skipped.error_message

    def test_a_skipped_item_is_plain_data_and_keeps_nothing_alive(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review round 2, P2-1. The report is a list a caller is told to keep. It
        used to hold the exception — whose traceback holds the frames, which hold
        the scene and the item. Now it is strings and a code, and the item can go."""
        import dataclasses
        import gc
        import weakref

        # pytest's own log capture keeps every LogRecord, traceback and all, for its
        # report; a real handler writes the line and forgets it. Out of the way here,
        # so that the REPORT is the only thing that could still hold the item.
        monkeypatch.setattr(snapshot_module._log, "disabled", True)
        scene = canvas.scene()
        tree = CircleItem(300.0, 100.0, 30.0, object_type=ObjectType.TREE)
        scene.addItem(tree)
        _break_species(tree)
        _snapshot, report = snapshot_with_report(scene)
        (skipped,) = report
        assert all(isinstance(getattr(skipped, field.name), str)
                   for field in dataclasses.fields(skipped))  # a StrEnum member is a str
        assert not hasattr(skipped, "error")
        gone = weakref.ref(tree)
        scene.removeItem(tree)
        del tree
        gc.collect()
        assert gone() is None  # the report does not pin the item
        assert [reason.value for reason in SkipReason] == [
            "record_failed", "duplicate_id", "outline_unbuildable", "outline_too_large", "out_of_range",
        ]  # the codes a UI maps to texts

    def test_a_repaired_item_comes_back(self, canvas: CanvasView) -> None:
        scene = canvas.scene()
        tree = CircleItem(300.0, 100.0, 30.0, object_type=ObjectType.TREE)
        scene.addItem(tree)
        tree.metadata["plant_species"] = {"scientific_name": None}
        assert snapshot_records(scene) == {}
        tree.metadata["plant_species"] = {"scientific_name": "Malus domestica"}
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(tree.item_id)] and skipped == []

    def test_the_log_is_keyed_by_item_and_kind_of_failure_not_by_message(
        self, canvas: CanvasView, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The pipeline snapshots on every edit, and an exception's message may
        carry a value that changes with each of them. So: the same kind of
        failure on the same item is one line however its message reads, and a
        different kind is a new line."""
        scene = canvas.scene()
        tree = CircleItem(300.0, 100.0, 30.0, object_type=ObjectType.TREE)
        scene.addItem(tree)
        with caplog.at_level(logging.WARNING, logger=snapshot_module.__name__):
            _break_species(tree)  # AttributeError: 'NoneType' object has no attribute 'strip'
            first = snapshot_with_report(scene)[1][0]
            _break_species_name(tree)  # AttributeError again, another message
            second = snapshot_with_report(scene)[1][0]
            assert first.error_message != second.error_message
            assert first.error_type == second.error_type == "AttributeError"
            assert len(caplog.records) == 1
            tree.metadata.pop("plant_species")
            _break_position(tree)  # ValueError: another kind of failure
            assert snapshot_with_report(scene)[1][0].error_type == "ValueError"
        assert len(caplog.records) == 2

    def test_the_memory_of_what_was_logged_is_bounded(
        self, canvas: CanvasView, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """"Logged once" needs a memory, and the memory needs a bound — one that
        bounds the VOLUME too (review round 2, P2-2: clearing the memory when it
        was full logged every broken item again on every snapshot — 8 items, a
        memory of 5, 10 idle snapshots: 80 lines). Now: 5 items are logged once
        each, one line says that further failures are not logged, and that is
        all — however many snapshots follow. The caller's list is never cut."""
        monkeypatch.setattr(snapshot_module, "_REPORTED_MAX", 5)
        scene = canvas.scene()
        for index in range(8):
            tree = CircleItem(100.0 + 100.0 * index, 100.0, 30.0, object_type=ObjectType.TREE)
            scene.addItem(tree)
            _break_species(tree)
        with caplog.at_level(logging.WARNING, logger=snapshot_module.__name__):
            for _ in range(10):
                assert len(snapshot_with_report(scene)[1]) == 8  # reported every time
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        notices = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(errors) == 5 and len(notices) == 1 and len(caplog.records) == 6
        assert "further ones are left out of the log" in notices[0].getMessage()
        assert len(snapshot_module._reported) == 6  # five failures and the marker: it stays put

    def test_the_report_is_an_out_parameter_and_the_return_type_is_what_it_was(
        self, canvas: CanvasView
    ) -> None:
        """The signature other stories call is unchanged — ``snapshot_records(scene)``
        and ``snapshot_records(scene, at_date)`` return a plain ``dict`` — and the
        report is opt-in: a keyword-only list the caller owns, appended to, never
        cleared (two scenes can report into one list)."""
        import inspect

        signature = inspect.signature(snapshot_records)
        assert list(signature.parameters) == ["scene", "at_date", "skipped"]
        assert signature.parameters["skipped"].kind is inspect.Parameter.KEYWORD_ONLY
        assert signature.parameters["skipped"].default is None
        scene = canvas.scene()
        shed, tree = _rectangle(), CircleItem(300.0, 100.0, 30.0, object_type=ObjectType.TREE)
        scene.addItem(shed)
        scene.addItem(tree)
        _break_species(tree)
        report: list[SkippedItem] = [SkippedItem("earlier", "X", SkipReason.DUPLICATE_ID)]
        snapshot = snapshot_records(scene, None, skipped=report)
        assert type(snapshot) is dict and list(snapshot) == [str(shed.item_id)]
        assert [s.item_id for s in report] == ["earlier", str(tree.item_id)]
        sync = SceneSync(RecordingSink())
        assert sync.apply(snapshot) == SceneDiff(added=(str(shed.item_id),))

    def test_the_fill_pattern_enum_is_what_the_healthy_path_reads(self, canvas: CanvasView) -> None:
        """The guard for the breaker above: a real ``FillPattern`` is the normal
        case and gives the pattern's name."""
        shed = _rectangle()
        canvas.scene().addItem(shed)
        shed.fill_pattern = FillPattern.GRAVEL
        assert snapshot_records(canvas.scene())[str(shed.item_id)].material.pattern == "GRAVEL"


# ── P2-5: two items, one id ───────────────────────────────────────────────────


class TestDuplicateIds:
    @pytest.fixture(autouse=True)
    def _forget_what_was_logged(self) -> None:
        snapshot_module._reported.clear()

    def test_the_lower_item_wins_and_the_other_is_reported(
        self, canvas: CanvasView, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A plan must not contain two items with one id (the loader dedupes,
        #403) — but if a scene does, the snapshot says so instead of letting the
        upper item silently overwrite the lower one's record."""
        scene = canvas.scene()
        low = RectangleItem(0.0, 0.0, 100.0, 100.0, object_type=ObjectType.TOOL_SHED)
        high = RectangleItem(300.0, 0.0, 50.0, 50.0, object_type=ObjectType.RAISED_BED)
        scene.addItem(low)
        scene.addItem(high)
        high._item_id = low.item_id
        shared = str(low.item_id)
        with caplog.at_level(logging.WARNING, logger=snapshot_module.__name__):
            snapshot, report = snapshot_with_report(scene)
            snapshot_records(scene)
        assert list(snapshot) == [shared] and snapshot[shared].kind == "TOOL_SHED"  # first wins
        assert report == [SkippedItem(shared, "RAISED_BED", SkipReason.DUPLICATE_ID)]
        assert (report[0].error_type, report[0].error_message) == ("", "")  # nothing was raised
        (logged,) = caplog.records  # once, though snapshotted twice
        assert logged.levelno == logging.WARNING and shared in logged.getMessage()
        assert "already has this id [duplicate_id]" in logged.getMessage()


# ── a HOUSE and its ridge ─────────────────────────────────────────────────────


@pytest.fixture
def house_stage(canvas: CanvasView) -> tuple[CanvasView, Any, Any]:
    house = PolygonItem(
        [QPointF(1000.0, 800.0), QPointF(1900.0, 800.0), QPointF(1900.0, 1340.0),
         QPointF(1000.0, 1340.0)], object_type=ObjectType.HOUSE)
    ridge = PolylineItem([QPointF(1000.0, 1070.0), QPointF(1900.0, 1070.0)],
                         object_type=ObjectType.ROOF_RIDGE)
    house.set_metadata("ridge_item_id", str(ridge.item_id))
    ridge.set_metadata("owner_polygon_id", str(house.item_id))
    canvas.scene().addItem(house)
    canvas.scene().addItem(ridge)
    return canvas, house, ridge


class TestHouseRidge:
    def test_ridge_ends_are_in_the_house_s_local_frame(self, house_stage) -> None:
        canvas, house, _ridge = house_stage
        record = snapshot_records(canvas.scene())[str(house.item_id)]
        assert record.transform == Transform(1450.0, 1070.0, 0.0)
        assert record.params["ridge"] == ((-450.0, 0.0), (450.0, 0.0))

    def test_a_ridge_item_gets_no_record_of_its_own(self, house_stage) -> None:
        """Review P2-4. The ridge reaches 3D as its HOUSE's ``ridge`` param. As a
        record it changed GEOMETRY whenever the house turned (the app re-derives
        its points: measured on 400 of 400 rotations) — a rebuild for a line the
        house's own builder draws."""
        canvas, house, ridge = house_stage
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert list(snapshot) == [str(house.item_id)]
        assert skipped == []  # by design, not a fault
        ridge.setVisible(False)  # … and hiding the line does not take the ridge off the roof
        assert "ridge" in snapshot_records(canvas.scene())[str(house.item_id)].params

    @pytest.mark.parametrize("angle", [17.0, 90.0, 213.5])
    def test_turning_the_house_is_exactly_one_transform_entry(self, house_stage, angle) -> None:
        """The baseline is taken BEFORE the turn (the first version of this test
        turned first and so never compared across a rotation). Through the app's
        command, as the GUI and the Agent API do it."""
        canvas, house, _ridge = house_stage
        hid = str(house.item_id)
        before = snapshot_records(canvas.scene())
        ridge_local = before[hid].params["ridge"]
        canvas.command_manager.execute(RotateItemCommand(house, 0.0, angle, apply_rotation))
        turned = snapshot_records(canvas.scene())
        assert diff(before, turned) == SceneDiff(transform=(hid,))  # one entry: the house's
        assert turned[hid].transform.rotation_deg == angle
        assert turned[hid].params["ridge"] == ridge_local  # ADR-046 re-derived it; locally it stands
        assert turned[hid].same_geometry(before[hid])
        canvas.command_manager.undo()
        assert snapshot_records(canvas.scene()) == before

    @pytest.mark.parametrize("angle", [0.0, 17.0, 90.0, 213.5])
    def test_moving_a_turned_house_is_exactly_one_transform_entry(self, house_stage, angle) -> None:
        canvas, house, _ridge = house_stage
        hid = str(house.item_id)
        apply_rotation(house, angle)  # PolygonItem re-derives the ridge (ADR-046)
        before = snapshot_records(canvas.scene())
        house.moveBy(321.7, -45.3)  # the app shifts the ridge item's points by the same delta
        after = snapshot_records(canvas.scene())
        assert diff(before, after) == SceneDiff(transform=(hid,))
        assert after[hid].params["ridge"] == before[hid].params["ridge"]

    def test_a_thousand_moves_never_leak_float_dust_into_the_geometry(self, house_stage) -> None:
        """The app re-writes the ridge points by ``+ delta`` on every move, so their
        float error grows (measured: 1.1e-10 cm after 20,000 moves). On the record
        grid of 1e-7 cm it never becomes a 'change' — without the grid, the very
        first move rebuilds the house."""
        canvas, house, _ridge = house_stage
        hid = str(house.item_id)
        apply_rotation(house, 17.0)
        first = snapshot_records(canvas.scene())[hid]
        rng = np.random.default_rng(385)
        rebuilds = 0
        last = first
        for dx, dy in rng.uniform(-37.3, 41.9, size=(1000, 2)):
            house.moveBy(float(dx), float(dy))
            now = snapshot_records(canvas.scene())[hid]
            rebuilds += not last.same_geometry(now)
            last = now
        assert rebuilds == 0
        assert last.params["ridge"] == first.params["ridge"]

    def test_an_edited_ridge_changes_the_house_s_geometry(self, house_stage) -> None:
        canvas, house, ridge = house_stage
        hid = str(house.item_id)
        before = snapshot_records(canvas.scene())
        ridge._move_vertex_to(0, QPointF(1000.0, 900.0))  # a hand drag along the wall
        after = snapshot_records(canvas.scene())
        result = diff(before, after)
        assert hid in result.geometry and hid not in result.transform
        assert after[hid].params["ridge"] != before[hid].params["ridge"]

    def test_a_house_without_a_ridge_has_no_ridge_param(self, house_stage) -> None:
        canvas, house, ridge = house_stage
        canvas.scene().removeItem(ridge)
        assert "ridge" not in snapshot_records(canvas.scene())[str(house.item_id)].params

    def test_a_ridge_link_to_something_else_is_no_ridge(self, house_stage) -> None:
        """A stale or corrupt ``ridge_item_id`` (it names a shed, or a line that
        lost a point) gives a HOUSE without a ridge param — the builder falls back,
        nothing raises."""
        canvas, house, ridge = house_stage
        shed = _rectangle()
        canvas.scene().addItem(shed)
        house.set_metadata("ridge_item_id", str(shed.item_id))
        assert "ridge" not in snapshot_records(canvas.scene())[str(house.item_id)].params
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        ridge._points = ridge._points[:1]
        assert "ridge" not in snapshot_records(canvas.scene())[str(house.item_id)].params

    def test_the_bench_house(self, qtbot) -> None:
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / "bench_small.ogp")
        houses = [r for r in snapshot_records(scene, JUNE).values() if r.kind == "HOUSE"]
        assert len(houses) == 1
        (start, end) = houses[0].params["ridge"]  # type: ignore[misc]
        assert start != end and houses[0].height_cm == 450.0


# ── G7: meshes of real items ──────────────────────────────────────────────────


class TestDefaultBuilderOnRealItems:
    @pytest.mark.parametrize("rotation", [0.0, 213.5])
    def test_every_mesh_validates_and_the_top_is_the_height(self, stage: Stage, rotation: float) -> None:
        apply_rotation(stage.item, rotation)
        stage.item.metadata[METADATA_KEY] = 187.3
        stage.step()
        parts = verify_builder(default_builder, stage.record)
        assert len(parts) == 2  # tinted sides + fill cap (#627)
        for part in parts:
            part.validate()
        top = float(_solid(parts).mesh.bounds()[1][2])
        assert top == float(np.float32(187.3))  # exact, in the float32 the engine receives

    def test_a_shape_without_a_height_has_no_solid(self, canvas: CanvasView) -> None:
        lawn = RectangleItem(0.0, 0.0, 500.0, 400.0, object_type=ObjectType.LAWN)
        canvas.scene().addItem(lawn)
        record = snapshot_records(canvas.scene())[str(lawn.item_id)]
        assert record.height_cm is None and verify_builder(default_builder, record) == ()

    @pytest.mark.parametrize("plan", ["bench_small.ogp", "bench_large.ogp"])
    def test_every_bench_record_builds_a_valid_mesh(self, qtbot, plan: str) -> None:
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / plan)
        records = snapshot_records(scene, JUNE)
        solids = 0
        for record in records.values():
            parts = verify_builder(default_builder, record)
            assert bool(parts) is (record.height_cm is not None)
            solids += bool(parts)
        assert solids == sum(1 for r in records.values() if r.height_cm is not None) > 80


# ── G8: an unchanged scene ────────────────────────────────────────────────────


@pytest.mark.parametrize("plan", ["bench_small.ogp", "bench_large.ogp"])
def test_unchanged_scene_snapshots_identically_100_times(qtbot, plan: str) -> None:
    """The float-noise guard: 100 snapshots of an untouched plan compare equal and
    diff empty. Deterministic by construction — nothing here depends on the grid."""
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    first, skipped = snapshot_with_report(scene, JUNE)
    assert len(first) == (98 if plan == "bench_small.ogp" else 424)  # every item but the roof ridge
    assert skipped == []
    for _ in range(100):
        again = snapshot_records(scene, JUNE)
        assert again == first
        assert list(again) == list(first)
        assert diff(first, again).is_empty and diff(again, first).is_empty


# ── fix round 4 ──────────────────────────────────────────────────────────────


def _traced_ring(vertices: int, seed: int, cx: float, cy: float,
                 radius: float = 400.0) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    wobble = 0.15 * 2.0 * math.pi * radius / vertices
    radii = radius + rng.uniform(-wobble, wobble, vertices)
    return [(cx + float(radii[k]) * math.cos(2.0 * math.pi * k / vertices),
             cy + float(radii[k]) * math.sin(2.0 * math.pi * k / vertices)) for k in range(vertices)]


def _two_level(vertices: int, seed: int = 1, turn_deg: float = 0.0) -> list[tuple[float, float]]:
    """The review's outline: every vertex on one of two levels, x at random — a
    closed zigzag whose teeth cross each other everywhere. Turned, it is no
    kinder."""
    rng = np.random.default_rng(seed * 100003 + vertices)
    xs = np.round(rng.uniform(0.0, 2000.0, vertices), 3)
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    points = [(float(xs[k]), 0.0 if k % 2 == 0 else 1000.0) for k in range(vertices)]
    return [(round(x * c - y * s, 3), round(x * s + y * c, 3)) for x, y in points]


@pytest.fixture
def small_memory(monkeypatch: pytest.MonkeyPatch, fresh_outlines: None) -> int:
    """Every ring memory of the pipeline at 3,000 vertices of STALE answers — a
    plan of a few polygons is "above the cap" then, as a plan of 131,000 vertices
    is above the real one."""
    from open_garden_planner.core.scene3d import polygon as polygon_module
    from open_garden_planner.core.scene3d import record as record_module

    for memory in (polygon_module._examined, polygon_module.ring_area, record_module._ring_facts,
                   snapshot_module._polygon_regions, snapshot_module._polyline_regions):
        monkeypatch.setattr(memory, "_max", 3_000)
        memory.cache_clear()
    return 3_000


@pytest.fixture
def work_done(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """How often the three things an unchanged plan must NOT do were done."""
    from open_garden_planner.core.scene3d import polygon as polygon_module

    done = {"cuts": 0, "strokes": 0, "outlines": 0}

    def counting(module: Any, name: str, key: str) -> None:
        real = getattr(module, name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            done[key] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, counted)

    counting(polygon_module, "_cut", "cuts")
    counting(snapshot_module, "_stroke_regions", "strokes")
    counting(snapshot_module, "_outline_regions", "outlines")
    return done


class TestAnUnchangedPlanIsAnsweredFromMemory:
    """Review of fix round 3, P1-A. The ring memories dropped the least recently
    asked answer when they were full, and a snapshot asks the plan in the same
    order on every tick: above the cap nearly every lookup missed, and an
    UNCHANGED plan was recomputed on every tick — 160 polygons of 1,000 vertices
    re-cut all 160 regions (4.6 to 5.3 s; 0.2 s before the cap existed), 110
    closed fences of 801 points took 14 s.

    Now a snapshot is one generation, what it asks for is LIVE and never dropped,
    and the cap bounds what no snapshot asks for any more. Every test here counts
    calls; none reads a clock."""

    def test_idle_ticks_of_a_plan_above_the_cap_do_no_work(
        self, canvas: CanvasView, small_memory: int, work_done: dict[str, int]
    ) -> None:
        """The reviewer's repro, with the cap shrunk instead of the plan grown: 16
        polygons of 400 vertices and 6 closed fences of 60 points hold five times
        what the memories may hold of stale answers."""
        scene = canvas.scene()
        for k in range(16):
            ring = _traced_ring(400, k, 1000.0 * (k % 4), 1000.0 * (k // 4))
            scene.addItem(PolygonItem([QPointF(x, y) for x, y in ring], object_type=ObjectType.HEDGE_POLYGON))
        for k in range(6):
            ring = _traced_ring(60, 100 + k, 1000.0 * k, 5000.0, radius=300.0)
            scene.addItem(_fence([*ring, ring[0]]))
        first, skipped = snapshot_with_report(scene)
        assert skipped == [] and len(first) == 22
        assert work_done == {"cuts": 22, "strokes": 6, "outlines": 16}  # the first tick: every item once
        held = snapshot_module._polygon_regions.cache_info().vertices
        assert held > 4 * small_memory  # the plan IS above the cap — and all of it is held
        for _tick in range(3):
            work_done.update(cuts=0, strokes=0, outlines=0)
            assert snapshot_records(scene) == first
            assert work_done == {"cuts": 0, "strokes": 0, "outlines": 0}
        assert snapshot_module._polygon_regions.cache_info().vertices == held

    def test_an_edit_session_holds_bounded_memory(
        self, canvas: CanvasView, small_memory: int, work_done: dict[str, int]
    ) -> None:
        """One vertex of one outline dragged through 500 positions: 500 rings that
        nothing asks for again. What is held stays what the plan asks for plus at
        most the cap — the bound the cap was introduced for."""
        scene = canvas.scene()
        ring = _traced_ring(100, 7, 2000.0, 2000.0)
        edited = PolygonItem([QPointF(x, y) for x, y in ring], object_type=ObjectType.HEDGE_POLYGON)
        still = [PolygonItem([QPointF(x, y) for x, y in _traced_ring(100, 20 + k, 1000.0 * k, 0.0)],
                             object_type=ObjectType.HEDGE_POLYGON) for k in range(16)]
        for item in (edited, *still):
            scene.addItem(item)
        snapshot_records(scene)
        live = snapshot_module._polygon_regions.cache_info().vertices  # 17 outlines: 3,536 vertices
        assert live > small_memory
        most = 0
        for step in range(500):
            polygon = edited.polygon()
            polygon[0] = QPointF(ring[0][0] + 0.01 * (step + 1), ring[0][1])
            edited.setPolygon(polygon)
            work_done.update(cuts=0, strokes=0, outlines=0)
            snapshot_records(scene)
            assert work_done == {"cuts": 1, "strokes": 0, "outlines": 1}, step  # the edited one, and only it
            most = max(most, snapshot_module._polygon_regions.cache_info().vertices)
        assert most <= live + small_memory + 208  # what is live, the cap, and the ring that tipped it
        assert most > live + small_memory // 2  # … and stale answers ARE kept, up to the cap

    def test_a_refusal_is_remembered_while_the_item_lives(
        self, canvas: CanvasView, small_memory: int, work_done: dict[str, int]
    ) -> None:
        """A refused outline is asked for on every tick like any other: its refusal
        is live. (45 refused lines of 7,000 points re-paid 6,750 M units per tick.)"""
        scene = canvas.scene()
        lines = [_fence([(k * 20.0, 300.0 * row + (k % (5 + row)) * 40.0) for k in range(4_000)])
                 for row in range(4)]  # four different lines: the same one four times would be one answer
        for line in lines:
            scene.addItem(line)
        scene.addItem(_rectangle())
        first, skipped = snapshot_with_report(scene)
        assert len(first) == 1 and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE] * 4
        assert work_done["strokes"] == 4
        assert snapshot_module._polyline_regions.cache_info().vertices > 5 * small_memory
        for _tick in range(3):
            work_done.update(cuts=0, strokes=0, outlines=0)
            assert snapshot_with_report(scene) == (first, skipped)
            assert work_done == {"cuts": 0, "strokes": 0, "outlines": 0}
        # … and when the lines are gone, so is what was remembered about them: two snapshots
        # later they are stale, and that snapshot — which asks nothing about a line — drops them
        for line in lines:
            scene.removeItem(line)
        snapshot_records(scene)
        assert snapshot_module._polyline_regions.cache_info().entries == 4  # the snapshot before asked
        snapshot_records(scene)
        assert snapshot_module._polyline_regions.cache_info().vertices <= small_memory

    def test_a_snapshot_is_one_generation_and_nothing_else_is(self) -> None:
        from open_garden_planner.core.scene3d import polygon as polygon_module

        before = polygon_module._generation
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        snapshot_records(scene)
        snapshot_records(scene)
        assert polygon_module._generation == before + 2 and not polygon_module._snapshotting
        assert snapshot_records.__name__ == "snapshot_records" and "skipped" in (snapshot_records.__doc__ or "")


class TestTheTwoLevelZigzag:
    """Review of fix round 3, P1-B. ``StrictlySimple`` together with ``Execute2``
    costs by the rings it makes and the splits it tries: one outline of 340
    vertices, every vertex on one of two levels, held the GUI thread for 3.6 s
    INSIDE the work budget (the plain union took 8 ms). The strict union is asked
    for a flat list now, and ``group_rings`` — counted, paid before it runs —
    says which hole is whose."""

    def test_no_union_is_ever_asked_for_a_tree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Neither union — strict (review of fix round 3) nor plain (review of fix
        round 4: this test pinned the plain union's tree as expected). The one
        tree left is a band reading's DIFFERENCE, never with StrictlySimple."""
        import pyclipper

        asked = _watch_pyclipper(monkeypatch)
        snapshot_module._polygon_regions.cache_clear()
        for outline in (((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0)),  # resolved at once
                        TestWhatPyclipperGetsWrong.CASES["a hole hung under the wrong ring"][0],  # by a band
                        tuple(_two_level(120)), _bridged_holes(40), _touching_holes(20)):
            snapshot_module._polygon_regions(outline)
        union, difference = pyclipper.CT_UNION, pyclipper.CT_DIFFERENCE
        assert ("list", union, False) in asked and ("list", union, True) in asked  # both unions: lists
        assert ("tree", difference, False) in asked  # the hole hung under the wrong ring: read off a band's tree
        assert {question for question in asked if question[0] == "tree"} == {("tree", difference, False)}
        snapshot_module._polygon_regions.cache_clear()

    @pytest.mark.parametrize("turn_deg", [0.0, 30.0], ids=["as the review drew it", "turned 30 degrees"])
    @pytest.mark.parametrize("vertices", [200, 340])
    def test_what_it_asks_of_the_clipper_is_bounded_and_stated(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None,
        vertices: int, turn_deg: float,
    ) -> None:
        """Through a real ``PolygonItem``: at most the two unions are asked (the
        strict one as a list: 18 ms where the tree took 3.6 s), and the item is
        refused for its size — a thousand rings, and regions with hundreds of holes
        whose bridges alone are beyond what is left. The rest of the plan has its
        records."""
        asked = _watch_clipper(monkeypatch)
        house = PolygonItem([QPointF(x, y) for x, y in _two_level(vertices, turn_deg=turn_deg)],
                            object_type=ObjectType.HOUSE)
        shed = _rectangle()
        scene = canvas.scene()
        scene.addItem(house)
        scene.addItem(shed)
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]
        assert [(s.item_id, s.reason) for s in skipped] == [(str(house.item_id), SkipReason.OUTLINE_TOO_LARGE)]
        assert asked in (["plain", "strict"], ["plain"])
        asked.clear()
        assert snapshot_with_report(scene) == (snapshot, skipped) and asked == []  # remembered

    def test_the_strict_union_s_rings_are_sorted_out_of_the_item_s_own_budget(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """Which hole is whose is ``group_rings``' to say, and it is paid like every
        other step: out of the ITEM's budget, not one of its own. An outline with a
        moat and an island in it — an outer ring with a hole, and a region inside."""
        from open_garden_planner.core.scene3d.polygon import WorkBudget

        house = ((0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0), (0.0, 0.0), (40.0, 40.0),
                 (40.0, 560.0), (560.0, 560.0), (560.0, 40.0), (40.0, 40.0), (80.0, 80.0), (520.0, 80.0),
                 (520.0, 520.0), (80.0, 520.0), (80.0, 80.0), (40.0, 40.0))
        paid_from: list[Any] = []
        real = snapshot_module.group_rings
        monkeypatch.setattr(snapshot_module, "group_rings",
                            lambda rings, work=None: (paid_from.append(work), real(rings, work))[1])
        asked = _watch_clipper(monkeypatch)
        whole = WorkBudget(budget=10**12)
        regions, resolved = snapshot_module._outline_regions(house, whole)
        assert resolved and not isinstance(regions, snapshot_module._Refused)
        assert sorted(len(holes) for _outer, holes in regions) == [0, 1]  # the island, and the ring round the moat
        assert asked[:2] == ["plain", "strict"] and paid_from and all(work is whole for work in paid_from)

    def test_three_hundred_touching_diamonds_still_build(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """An honest outline of many regions: a zigzag out and its mirror back, 300
        diamonds touching tip to tip. It built before this round and must go on
        building — the price is NOT the square of the rings that come back."""
        teeth = 300
        out = [(40.0 * k, 30.0 if k % 2 else 0.0) for k in range(2 * teeth + 1)]
        back = [(x, -y) for x, y in reversed(out[1:-1])]
        house = PolygonItem([QPointF(x, y) for x, y in out + back], object_type=ObjectType.HOUSE)
        asked = _watch_clipper(monkeypatch)
        canvas.scene().addItem(house)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == []
        record = snapshot[str(house.item_id)]
        assert len(record.footprints) == teeth and record.holes == ()
        assert record.params["outline_resolved"] is True
        assert record.plan_area_cm2 == pytest.approx(teeth * 80.0 * 60.0 / 2.0, rel=1e-3)
        assert asked[:2] == ["plain", "strict"]


class TestAFlatSegmentDoesNotStack:
    """Review of fix round 3, P2-3. A straight fence with a post every 2 m fitted
    1,416 points running east–west and 6,645 running north–south: a level segment
    was counted into the stack the clipper's sweep carries, and the sweep does not
    carry level edges (7 ms of work, charged 21 times that)."""

    @staticmethod
    def _fence_of(points: int, turn_deg: float) -> Any:
        c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
        return _fence([(round(200.0 * k * c, 7), round(200.0 * k * s, 7)) for k in range(points)])

    @pytest.mark.parametrize("turn_deg", [0.0, 90.0], ids=["east-west", "north-south"])
    def test_a_straight_fence_of_5_000_posts_is_built_either_way(
        self, canvas: CanvasView, fresh_outlines: None, turn_deg: float
    ) -> None:
        fence = self._fence_of(5_000, turn_deg)
        canvas.scene().addItem(fence)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == []
        record = snapshot[str(fence.item_id)]
        assert [len(ring) for ring in record.footprints] == [4] and record.holes == ()
        assert record.plan_area_cm2 == pytest.approx(4_999 * 200.0 * 10.0, rel=1e-9)

    def test_the_two_directions_cost_the_same(self, fresh_outlines: None) -> None:
        from open_garden_planner.core.scene3d.polygon import WorkBudget

        spent = []
        for turn_deg in (0.0, 90.0):
            path = tuple((round(200.0 * k * math.cos(math.radians(turn_deg)), 7),
                          round(200.0 * k * math.sin(math.radians(turn_deg)), 7)) for k in range(1_500))
            budget = WorkBudget(budget=10**12)
            snapshot_module._stroke_regions(path, 10.0, budget)
            spent.append(budget.spent)
        assert abs(spent[0] - spent[1]) < 0.03 * spent[1]  # two segments in the stack, or none

    def test_a_fence_that_is_not_level_still_pays_for_its_stack(self, fresh_outlines: None) -> None:
        """Only EXACTLY level segments ride free. The same posts a few centimetres
        off the line are carried by the sweep, every one — and paid for."""
        from open_garden_planner.core.scene3d.polygon import (
            RegionTooLargeError,
            WorkBudget,
            stack_height,
        )

        rng = np.random.default_rng(4)
        path = tuple((50.0 * k, float(np.round(rng.uniform(-3.0, 3.0), 3))) for k in range(1_500))
        assert stack_height((path,), closed=False, reach=7.072, flat=False) == 1_499
        with pytest.raises(RegionTooLargeError):
            snapshot_module._stroke_regions(path, 10.0, WorkBudget())


class TestTheCountIsNotACopy:
    """Review of fix round 3, P2-7: "one comparison" read ``len(item.points)``, and
    ``points`` returns a copy of the list — 200,000 points copied to be counted."""

    def test_a_polyline_says_how_many_points_it_has_without_copying_them(self) -> None:
        line = PolylineItem([QPointF(float(k), 0.0) for k in range(5)], object_type=ObjectType.FENCE)
        assert line.point_count == 5 == len(line.points)
        assert line.points is not line.points  # … which is why the count does not go through it

    def test_the_size_of_an_item_is_asked_without_reading_its_points(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        line = PolylineItem([QPointF(float(k), 0.0) for k in range(5)], object_type=ObjectType.FENCE)
        monkeypatch.setattr(PolylineItem, "points", property(_never("the points were copied")))
        assert snapshot_module._drawn_vertices(line) == 5


# ── fix round 5: no union is a tree; a stated order; one call that forgets ───


def _bridged_holes(holes: int, shear: float = 0.0) -> tuple[tuple[float, float], ...]:
    """The review's ``column_keyholes`` (and, sheared, ``slanted_keyholes``): ONE
    ring — a slab 60 cm wide with triangular holes one above the other, each
    joined to the left wall by a level bridge walked out and back. No level line
    crosses more than a handful of its edges."""
    ring = [(0.0, 0.0), (60.0, 0.0), (60.0, holes * 30.0), (0.0, holes * 30.0)]
    for k in reversed(range(holes)):
        y = k * 30.0 + 15.0
        ring += [(0.0, y), (20.0, y), (30.0, y + 6.0), (30.0, y - 6.0), (20.0, y), (0.0, y)]
    return tuple((round(x + shear * y, 3), round(y + 0.3 * shear * x, 3)) for x, y in ring)


def _touching_holes(holes: int) -> tuple[tuple[float, float], ...]:
    """The review's ``column_pinholes``: the same slab with holes that TOUCH the
    wall they hang on — a triangle out of the wall and straight back."""
    ring = [(0.0, 0.0), (60.0, 0.0), (60.0, holes * 30.0), (0.0, holes * 30.0)]
    for k in reversed(range(holes)):
        y = k * 30.0 + 15.0
        ring += [(0.0, y), (12.0, y + 6.0), (12.0, y - 6.0), (0.0, y)]
    return tuple(ring)


class TestOneRingWithManyHoles:
    """Review of fix round 4, the P1. The PLAIN union was still asked for a
    PolyTree (``Execute2``) and the tree thrown away on the next line. A tree
    costs by the rings it makes and joins; the union's price is read off
    vertices, stack and crossings. One ring — a slab with 720 triangular holes,
    each bridged to its wall, 4,324 vertices — held the GUI thread for 5.3 s
    inside the budget (sheared, so that nothing is level: 3.9 s); as a list the
    same union takes milliseconds. Both unions are lists now, and the one tree
    left is a band reading's difference. Every test here counts questions; none
    reads a clock."""

    @pytest.mark.parametrize("shear", [0.0, 0.37], ids=["level", "sheared"])
    def test_the_review_s_slab_asks_for_two_lists_and_no_tree(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None, shear: float
    ) -> None:
        import pyclipper

        questions = _watch_pyclipper(monkeypatch)
        house = PolygonItem([QPointF(x, y) for x, y in _bridged_holes(720, shear)], object_type=ObjectType.HOUSE)
        shed = _rectangle()
        scene = canvas.scene()
        scene.addItem(house)
        scene.addItem(shed)
        snapshot, skipped = snapshot_with_report(scene)
        assert list(snapshot) == [str(shed.item_id)]  # a region with 720 holes: their bridges are beyond the budget
        assert [(s.item_id, s.reason) for s in skipped] == [(str(house.item_id), SkipReason.OUTLINE_TOO_LARGE)]
        assert questions == [("list", pyclipper.CT_UNION, False), ("list", pyclipper.CT_UNION, True)]
        questions.clear()
        assert snapshot_with_report(scene) == (snapshot, skipped) and questions == []  # remembered

    @pytest.mark.parametrize("shear", [0.0, 0.37], ids=["level", "sheared"])
    def test_a_slab_of_a_hundred_bridged_holes_is_built(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None, shear: float
    ) -> None:
        """What such a ring is for — a polygon with holes exported as one ring —
        is built: one region, its hundred holes, read off the strict union."""
        asked = _watch_clipper(monkeypatch)
        house = PolygonItem([QPointF(x, y) for x, y in _bridged_holes(100, shear)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and asked == ["plain", "strict"]
        record = snapshot[str(house.item_id)]
        assert len(record.footprints) == 1 and [len(group) for group in record.holes] == [100]
        assert {len(hole) for hole in record.holes[0]} == {3}
        assert record.params["outline_resolved"] is True
        slab, holes = 60.0 * 3000.0, 100 * 0.5 * 12.0 * 10.0
        assert record.plan_area_cm2 == pytest.approx((slab - holes) * (1.0 - 0.3 * shear * shear), rel=1e-4)

    def test_holes_that_touch_the_wall_are_read_off_a_band_the_one_tree(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """The touching-holes family. A hole that touches its outer ring in a point
        cannot be bridged, so the strict reading does not hold; with a band cut
        away along the union's rings the holes open into notches of ONE ring —
        read off the only tree the resolution asks for, a difference."""
        import pyclipper

        questions = _watch_pyclipper(monkeypatch)
        asked = _watch_clipper(monkeypatch)
        house = PolygonItem([QPointF(x, y) for x, y in _touching_holes(45)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert skipped == [] and asked == ["plain", "strict", "band"]
        record = snapshot[str(house.item_id)]
        assert len(record.footprints) == 1 and record.holes == () and record.params["outline_resolved"] is True
        assert record.plan_area_cm2 == pytest.approx(60.0 * 1350.0 - 45 * 0.5 * 12.0 * 12.0, rel=1e-3)
        assert questions == [("list", pyclipper.CT_UNION, False), ("list", pyclipper.CT_UNION, True),
                             ("tree", pyclipper.CT_DIFFERENCE, False)]

    def test_more_touching_holes_than_the_budget_covers_are_refused_before_any_band(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """110 of them, 444 vertices: the bridge search for the strict reading's
        region runs the budget out. Since #451 re-priced a block of candidates
        (``polygon._BRIDGE_UNITS``) the budget stops the search after a few dozen
        holes instead of every one of them. Refused; no band, no tree."""
        asked = _watch_clipper(monkeypatch)
        house = PolygonItem([QPointF(x, y) for x, y in _touching_holes(110)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]
        assert asked == ["plain", "strict"]

    def test_the_bridge_search_is_priced_at_what_it_costs(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """#451: the touching-holes family was the one row of the work table above
        its price (3.6 to 8.1), because a block of bridge candidates was charged
        60 units per edge. At 600 a block that finds nothing — the usual one for a
        hole touching the wall — is paid for, and the budget stops the search
        early: measured 30 calls for 110 holes (110 at the old price, when the
        item held the GUI thread for up to 1.5 s). No clock is read here; the
        script measures the time."""
        import open_garden_planner.core.scene3d.polygon as polygon_module

        calls = 0
        original = polygon_module._bridge_position

        def counted(*args: object, **kwargs: object) -> int:
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(polygon_module, "_bridge_position", counted)
        house = PolygonItem([QPointF(x, y) for x, y in _touching_holes(110)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        snapshot_with_report(canvas.scene())
        assert 0 < calls <= 40  # 30 measured; one per hole for a search that runs to the end

        calls = 0
        canvas.scene().removeItem(house)
        huge = PolygonItem([QPointF(x, y) for x, y in _touching_holes(200)], object_type=ObjectType.HOUSE)
        canvas.scene().addItem(huge)
        snapshot, skipped = snapshot_with_report(canvas.scene())
        assert snapshot == {} and [s.reason for s in skipped] == [SkipReason.OUTLINE_TOO_LARGE]
        assert calls == 0  # refused from its size alone: not one bridge is searched


class TestTheOrderOfARecordsRegions:
    """Review of fix round 4. With the plain union asked for a list instead of a
    tree, seven outlines of 13,740 came back as the same regions in another
    order: a record's signature must not follow a clipper mode. The order is a
    stated property now — by the smallest vertex of the outer ring — and every
    answer of the clipper is put in it before it is judged."""

    def test_regions_stand_by_the_smallest_vertex_of_their_outer_ring(self) -> None:
        hole = ((0.4, 3.2), (0.6, 3.4), (0.6, 3.2))
        second_hole = ((0.2, 3.1), (0.3, 3.2), (0.3, 3.1))
        right = (((5.0, 0.0), (6.0, 0.0), (6.0, 1.0)), ())
        upper = (((0.0, 3.0), (1.0, 3.0), (1.0, 4.0)), (hole, second_hole))
        lower = (((1.0, 2.0), (0.0, 1.0), (1.0, 1.0)), ())  # its smallest vertex is not its first
        assert snapshot_module._in_order((right, upper, lower)) == (lower, upper, right)
        assert snapshot_module._in_order((upper, lower, right)) == (lower, upper, right)
        assert snapshot_module._in_order((upper,))[0][1] == (hole, second_hole)  # holes: as the reading gave them
        # two outer rings that share their smallest vertex: by their vertices as they come
        fan_up, fan_right = ((0.0, 0.0), (1.0, 2.0), (0.0, 2.0)), ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0))
        assert snapshot_module._in_order(((fan_right, ()), (fan_up, ()))) == ((fan_up, ()), (fan_right, ()))
        assert snapshot_module._in_order(()) == ()

    OUTLINES: dict[str, tuple[tuple[float, float], ...]] = {
        "a bow-tie (two regions, the strict reading)": ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0)),
        "twenty diamonds tip to tip": tuple(
            [(40.0 * k, 30.0 if k % 2 else 0.0) for k in range(41)]
            + [(40.0 * k, -30.0 if k % 2 else 0.0) for k in range(39, 0, -1)]),
        "a piece handed out the wrong way round (a band reading)":
            TestWhatPyclipperGetsWrong.CASES["a piece handed out the wrong way round"][0],
        "a hole hung under the wrong ring (a band reading)":
            TestWhatPyclipperGetsWrong.CASES["a hole hung under the wrong ring"][0],
    }

    @pytest.mark.parametrize("name", list(OUTLINES))
    def test_the_order_is_not_the_clipper_s(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None, name: str
    ) -> None:
        """Whatever order the clipper hands its rings out in — turned round here,
        for both unions and for what is read off a band's tree — the answer is the
        same regions in the same order."""
        outline = self.OUTLINES[name]
        expected, resolved = snapshot_module._polygon_regions(outline)
        assert resolved and len(expected) > 1
        assert [min(outer) for outer, _holes in expected] == sorted(min(outer) for outer, _holes in expected)
        union, tree_regions = snapshot_module._union_rings, snapshot_module._tree_regions
        monkeypatch.setattr(snapshot_module, "_union_rings", lambda subject, fill, *, strictly_simple:
                            union(subject, fill, strictly_simple=strictly_simple)[::-1])
        monkeypatch.setattr(snapshot_module, "_tree_regions", lambda tree: tree_regions(tree)[::-1])
        snapshot_module._polygon_regions.cache_clear()
        assert snapshot_module._polygon_regions(outline) == (expected, True)

    def test_a_stroke_s_regions_are_put_in_order_too(
        self, monkeypatch: pytest.MonkeyPatch, fresh_outlines: None
    ) -> None:
        """A stroke is one connected ring with its holes, so there is nothing to
        order — until the clipper says otherwise. Whatever ``group_rings`` returns
        is put in order before it is judged."""
        from open_garden_planner.core.scene3d.polygon import WorkBudget

        left = (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)), ())
        right = (((50.0, 0.0), (60.0, 0.0), (60.0, 10.0), (50.0, 10.0)), ())
        monkeypatch.setattr(snapshot_module, "group_rings", lambda _rings, _work=None: (right, left))
        path = ((0.0, 0.0), (100.0, 0.0))
        assert snapshot_module._stroke_regions(path, 10.0, WorkBudget(budget=10**12)) == (left, right)

    def test_a_record_carries_them_in_that_order(self, canvas: CanvasView, fresh_outlines: None) -> None:
        house = PolygonItem([QPointF(x, y) for x, y in self.OUTLINES["twenty diamonds tip to tip"]],
                            object_type=ObjectType.HOUSE)
        canvas.scene().addItem(house)
        record = snapshot_records(canvas.scene())[str(house.item_id)]
        assert len(record.footprints) == 20
        smallest = [min(ring) for ring in record.footprints]
        assert smallest == sorted(smallest) and len(set(smallest)) == 20


class TestForgettingEverything:
    """Review of fix round 4, P2-3. What a snapshot asks for is never dropped
    while snapshots go on — so a plan that is gone stayed remembered until two
    more snapshots had run (measured: 321,280 vertices, about 30 MB, after
    ``scene.clear()``), and with the 3D view closed none runs. One public call
    drops everything, live and stale."""

    def test_one_call_drops_it_all_and_the_next_snapshot_is_a_first_one(
        self, canvas: CanvasView, fresh_outlines: None, work_done: dict[str, int]
    ) -> None:
        import inspect

        from open_garden_planner.core.scene3d import polygon as polygon_module
        from open_garden_planner.core.scene3d import record as record_module
        from open_garden_planner.ui.view3d.snapshot import clear_outline_cache

        assert not inspect.signature(clear_outline_cache).parameters  # one call, nothing to say
        assert clear_outline_cache.__module__ == snapshot_records.__module__  # next to the snapshot
        scene = canvas.scene()
        for k in range(3):
            ring = _traced_ring(100, 40 + k, 1000.0 * k, 0.0)
            scene.addItem(PolygonItem([QPointF(x, y) for x, y in ring], object_type=ObjectType.HEDGE_POLYGON))
        fence_ring = _traced_ring(40, 7, 500.0, 2000.0, radius=300.0)
        for item in (_fence([*fence_ring, fence_ring[0]]), _circle(), _ellipse(),
                     PolygonItem([QPointF(0.0, 0.0), QPointF(400.0, 300.0), QPointF(400.0, 0.0), QPointF(0.0, 300.0)],
                                 object_type=ObjectType.HOUSE)):
            scene.addItem(item)
        first = snapshot_with_report(scene)
        assert len(first[0]) == 7 and first[1] == []
        first_tick = dict(work_done)
        assert first_tick["cuts"] >= 6 and first_tick["strokes"] == 1 and first_tick["outlines"] == 4
        memories = (polygon_module._examined, polygon_module.ring_area, record_module._ring_facts,
                    snapshot_module._polygon_regions, snapshot_module._polyline_regions)
        circles = (snapshot_module._circle_ring, snapshot_module._circle_regions, snapshot_module._convex_region)
        assert all(memory.cache_info().entries for memory in memories)
        assert all(cache.cache_info().currsize for cache in circles)
        work_done.update(cuts=0, strokes=0, outlines=0)
        assert snapshot_with_report(scene) == first
        assert work_done == {"cuts": 0, "strokes": 0, "outlines": 0}  # remembered, all of it LIVE

        clear_outline_cache()
        assert [(memory.cache_info().entries, memory.cache_info().vertices) for memory in memories] == [(0, 0)] * 5
        assert all(memory.cache_info().entries == 0 for memory in polygon_module._memories)  # every one there is
        assert [cache.cache_info().currsize for cache in circles] == [0, 0, 0]
        assert snapshot_with_report(scene) == first
        assert work_done == first_tick  # a first tick again: every outline judged and cut once more
        clear_outline_cache()
        clear_outline_cache()  # with nothing held: nothing happens
        assert snapshot_with_report(scene) == first
