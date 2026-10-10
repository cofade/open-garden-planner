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
"""

from __future__ import annotations

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
from open_garden_planner.core.fill_patterns import create_pattern_brush
from open_garden_planner.core.object_height import METADATA_KEY, effective_height_cm
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.scene3d import (
    SHAPES,
    Material,
    Params,
    Record,
    SceneDiff,
    Transform,
    default_builder,
    diff,
    pose_ring,
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
from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records, snapshot_records

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
ROTATIONS = [0.0, 17.0, 90.0, 213.5]
POSITIONS = [(0.0, 0.0), (137.25, -42.5)]
JUNE = date(2026, 6, 21)
SPECIES = {
    "common_name": "Apple tree", "scientific_name": "Malus domestica",
    "min_height_cm": 100.0, "max_height_cm": 500.0,
    "min_spread_cm": 50.0, "max_spread_cm": 400.0,
}


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
    item.setPen(pen)
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
        self.bystander = RectangleItem(2000.0, 1500.0, 100.0, 100.0,
                                       object_type=ObjectType.RAISED_BED)
        self.item = FACTORIES[shape]()
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
        target.setPen(pen)

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
        """Undo is ``moveBy(-delta)``, and ``(p + d) - d`` is not ``p`` in floats:
        ``(0.1 + 0.7) - 0.7 == 0.09999999999999987``. On the record grid the two
        are one position, so undo gives back the very record it left."""
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(0.1, 0.3)))
        stage.step()
        before = stage.record
        stage.commands.execute(MoveItemsCommand([stage.item], QPointF(0.7, 0.9)))
        stage.step()
        stage.commands.undo()
        assert stage.item.pos().x() != 0.1  # the dust is real: 0.09999999999999987
        assert stage.step() == SceneDiff(transform=(stage.id,))
        assert stage.record == before

    @pytest.mark.parametrize("angle", [17.0, 90.0, 213.5])
    def test_rotate_is_transform_only(self, stage: Stage, angle: float) -> None:
        before = stage.record
        stage.commands.execute(RotateItemCommand(stage.item, 0.0, angle, apply_rotation))
        result = stage.step()
        assert result.geometry == () and result.material == ()
        assert result.added == () and result.removed == () and not result.reordered
        after = stage.record
        assert after.footprints == before.footprints and after.path == before.path
        if stage.shape in ROUND:
            # a circle's footprint does not turn: the record keeps rotation 0, and a
            # turn about its own centre moves nothing at all
            assert after.transform.rotation_deg == 0.0
            assert result.transform in ((), (stage.id,))
            assert after.transform.east_cm == pytest.approx(before.transform.east_cm, abs=1e-6)
        else:
            assert result == SceneDiff(transform=(stage.id,))
            assert after.transform.rotation_deg == angle

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
        stage.item.setPen(pen)
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

        The exact deviation compares vertex by vertex: every footprint ring of a
        non-polyline, the centre line of a polyline. The strip deviation is the
        largest vertex-to-boundary distance between the two stroke polygons.
        """
        item = FACTORIES[shape]()
        canvas.scene().addItem(item)
        _place(item, shape, rotation, position, how)
        at = JUNE if shape == "plant" else None
        record = snapshot_records(canvas.scene(), at)[str(item.item_id)]
        expected = item_footprints(item, at)
        posed = [pose_ring(record.transform, ring) for ring in record.footprints]
        assert len(posed) == len(expected) >= 1
        strip = 0.0
        if shape == "polyline":
            centre_line = [(p.x(), p.y()) for p in (item.mapToScene(q) for q in item.points)]
            pairs = list(zip(pose_ring(record.transform, record.path), centre_line, strict=True))
            strip = max(max(_boundary_distance(p, e), _boundary_distance(e, p))
                        for p, e in zip(posed, expected, strict=True))
        else:
            pairs = []
            for ring, scene_ring in zip(posed, expected, strict=True):
                pairs.extend(zip(ring, scene_ring, strict=True))
        exact = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in pairs)
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
        only the polyline's stroke polygon is at pyclipper's grid."""
        worst_exact, worst_strip = 0.0, 0.0
        for shape in SHAPE_NAMES:
            for rotation in ROTATIONS:
                for position in POSITIONS:
                    for how in ("app", "off-centre pivot"):
                        _record, exact, strip = self._measure(canvas, shape, rotation, position, how)
                        worst_exact, worst_strip = max(worst_exact, exact), max(worst_strip, strip)
        assert 0.0 < worst_exact <= 2.5e-7, worst_exact
        assert 1e-6 < worst_strip <= 3e-3, worst_strip  # the grid is real — and bounded

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
        posed = [pose_ring(record.transform, ring) for ring in record.footprints]
        if shape == "polyline":
            centre_line = [(p.x(), p.y()) for p in (item.mapToScene(q) for q in item.points)]
            for a, b in zip(pose_ring(record.transform, record.path), centre_line, strict=True):
                assert a == pytest.approx(b, abs=1e-6)
            assert max(_boundary_distance(p, e) for p, e in zip(posed, expected, strict=True)) <= 3e-3
        else:
            for a, b in zip(posed[0], expected[0], strict=True):
                assert a == pytest.approx(b, abs=1e-6)

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
    if isinstance(value, Transform | Material):
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
        assert stage.record.casts_shadow is (expected is not None)
        assert stage.record.base_cm == 0.0  # L1.6 fills it from the parent bed

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
        assert diff(before, after).is_empty  # a link, not geometry: L1.6 turns it into base_cm

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
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / "bench_small.ogp")
        records = snapshot_records(scene, JUNE)
        items = {str(i.item_id): i for i in scene.items() if hasattr(i, "item_id")}
        zs = [items[item_id].zValue() for item_id in records]
        assert zs == sorted(zs) and len(set(zs)) > 5
        legacy = collect_scene3d_records(scene, JUNE)
        assert len(records) == len(legacy) == 99

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
        assert item_outline(degenerate) is None
        assert snapshot_records(scene) == {}

    def test_non_finite_geometry_is_skipped_not_propagated(self, canvas: CanvasView) -> None:
        """NaN != NaN: one such record would report a change on every diff, forever."""
        item = _rectangle()
        canvas.scene().addItem(item)
        item.setPos(float("nan"), 0.0)
        assert snapshot_records(canvas.scene()) == {}


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

    @pytest.mark.parametrize("angle", [0.0, 17.0, 90.0, 213.5])
    def test_moving_or_turning_the_house_does_not_touch_its_geometry(self, house_stage, angle) -> None:
        canvas, house, _ridge = house_stage
        hid = str(house.item_id)
        apply_rotation(house, angle)  # PolygonItem re-derives the ridge (ADR-046)
        before = snapshot_records(canvas.scene())
        ridge_local = before[hid].params["ridge"]
        house.moveBy(321.7, -45.3)  # the app shifts the ridge item's points by the same delta
        after = snapshot_records(canvas.scene())
        assert hid not in diff(before, after).geometry
        assert hid in diff(before, after).transform
        assert after[hid].params["ridge"] == ridge_local

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
        assert len(parts) == 1
        parts[0].validate()
        top = float(parts[0].mesh.bounds()[1][2])
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
            solids += len(parts)
        assert solids == sum(1 for r in records.values() if r.height_cm is not None) > 80


# ── G8: an unchanged scene ────────────────────────────────────────────────────


@pytest.mark.parametrize("plan", ["bench_small.ogp", "bench_large.ogp"])
def test_unchanged_scene_snapshots_identically_100_times(qtbot, plan: str) -> None:
    """The float-noise guard: 100 snapshots of an untouched plan compare equal and
    diff empty. Deterministic by construction — nothing here depends on the grid."""
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    first = snapshot_records(scene, JUNE)
    assert len(first) == (99 if plan == "bench_small.ogp" else 425)
    for _ in range(100):
        again = snapshot_records(scene, JUNE)
        assert again == first
        assert list(again) == list(first)
        assert diff(first, again).is_empty and diff(again, first).is_empty
