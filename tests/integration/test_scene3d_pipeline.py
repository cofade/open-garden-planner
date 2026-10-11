"""The 3D scene pipeline end to end (Phase 17 L1.1, #385 — §8.10 and gate G2).

live items → ``snapshot_records`` → ``SceneSync`` → ``EngineSink``

A scripted edit session on a real view, scene and undo stack — draw with the
real tools, then move, rotate, recolour, resize, select, delete, undo, redo —
and after EVERY step two things are asserted:

1. the exact calls the sink received (a move is one ``update_transform`` and no
   builder call — the builder invocations are counted);
2. the ``RecordingSink`` holds exactly what a from-scratch ``apply`` of the
   current snapshot puts into an empty sink: incremental == full rebuild, the
   invariant that makes sending diffs safe.

Nothing is rendered: the sink is the recording double. L1.2 runs the same
session against Qt Quick 3D.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
    RotateItemCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    MeshPart,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    default_builder,
)
from open_garden_planner.core.stacking import ArrangeMode
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.arrange import build_arrange_command
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_move_vertex_command,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.snapshot import snapshot_records

# the real-item rig of the snapshot matrix: one stage, one set of app-command edits
from tests.integration.test_scene3d_snapshot import (
    FACTORIES,
    RECT_BACKED,
    ROUND,
    VERTEX_BACKED,
    Stage,
)
from tests.integration.test_scene3d_snapshot import _recolour as recolour_fill
from tests.integration.test_scene3d_snapshot import _resize_command as resize_command
from tests.integration.test_scene3d_snapshot import _restroke as restroke

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
JUNE = date(2026, 6, 21)
BEGIN, COMMIT = ("begin", None), ("commit", None)


class Pipeline:
    """The wiring L1.3 will own, in miniature: snapshot → sync → sink."""

    def __init__(self, scene: Any, at: date | None = None) -> None:
        self.scene = scene
        self.at = at
        self.built: list[str] = []
        self.sink = RecordingSink()
        self.sync = SceneSync(self.sink, BuilderRegistry(default=self._build), validate=True)

    def _build(self, record: Record) -> tuple[MeshPart, ...]:
        self.built.append(record.item_id)
        return default_builder(record)

    def tick(self) -> tuple[SceneDiff, list[tuple[str, str | None]], list[str]]:
        """One pipeline pass: (diff, the sink calls it caused, the items it built)."""
        self.sink.clear_calls()
        self.built.clear()
        records = snapshot_records(self.scene, self.at)
        result = self.sync.apply(records)
        self.assert_equals_full_rebuild(records)
        return result, self.sink.ops(), list(self.built)

    def assert_equals_full_rebuild(self, records: dict[str, Record]) -> None:
        fresh = SceneSync(RecordingSink(), validate=True)
        fresh.apply(records)
        assert isinstance(fresh.sink, RecordingSink)
        assert self.sink.state() == fresh.sink.state()
        assert dict(self.sync.records) == records and list(self.sync.records) == list(records)
        assert self.sync.failures == {} and not self.sink.in_transaction


def test_scripted_edit_session_sends_minimal_calls(canvas: CanvasView, mouse_event) -> None:
    scene = canvas.scene()
    commands = canvas.command_manager
    pipeline = Pipeline(scene)
    assert pipeline.tick() == (SceneDiff(), [], [])  # an empty plan: not even a transaction

    # ── draw a raised bed with the real tool (press, drag, release) ──────────
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(400.0, 300.0))
    tool.mouse_move(mouse_event, QPointF(700.0, 500.0))
    tool.mouse_release(mouse_event, QPointF(700.0, 500.0))
    bed = next(i for i in scene.items() if isinstance(i, RectangleItem))
    bed_id = str(bed.item_id)
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(added=(bed_id,))
    assert calls == [BEGIN, ("add", bed_id), COMMIT] and built == [bed_id]
    held = pipeline.sink.item(bed_id)
    assert held.transform.east_cm == 550.0 and held.transform.north_cm == 400.0
    assert float(held.parts[0].mesh.bounds()[1][2]) == 40.0  # RAISED_BED's resolved height

    # ── draw a tree with the real tool (click the centre, click the rim) ─────
    canvas.set_active_tool(ToolType.TREE)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(1500.0, 900.0))
    tool.mouse_press(mouse_event, QPointF(1620.0, 900.0))
    tree = next(i for i in scene.items() if isinstance(i, CircleItem))
    tree_id = str(tree.item_id)
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(added=(tree_id,))
    assert calls == [BEGIN, ("add", tree_id), COMMIT] and built == [tree_id]

    # ── a perennial INSIDE the bed and a fence, through the command path ─────
    layer = scene.active_layer.id
    perennial = CircleItem(500.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
    fence = PolylineItem([QPointF(100.0, 100.0), QPointF(900.0, 100.0)],
                         object_type=ObjectType.FENCE, layer_id=layer)
    commands.execute(CreateItemCommand(scene, perennial, "plant"))
    commands.execute(CreateItemCommand(scene, fence, "fence"))
    perennial_id, fence_id = str(perennial.item_id), str(fence.item_id)
    result, calls, built = pipeline.tick()
    assert set(result.added) == {perennial_id, fence_id}
    assert calls == [BEGIN, *[("add", i) for i in result.added], COMMIT]
    assert sorted(built) == sorted([perennial_id, fence_id])
    # auto-parented by the create command: the record knows its bed …
    assert pipeline.sync.records[perennial_id].parent_id == bed_id
    assert pipeline.sink.item(perennial_id).parts == ()  # … and has no height yet: no solid
    assert len(pipeline.sink.item(fence_id).parts) == 1  # FENCE: 120 cm by default

    # ── move: ONE update_transform, no builder call ──────────────────────────
    commands.execute(MoveItemsCommand([bed], QPointF(137.25, -42.5)))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(transform=(bed_id,))
    assert calls == [BEGIN, ("update_transform", bed_id), COMMIT] and built == []
    assert pipeline.sink.item(bed_id).transform.east_cm == 687.25

    # ── rotate: ONE update_transform, no builder call ────────────────────────
    commands.execute(RotateItemCommand(bed, 0.0, 30.0, apply_rotation))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(transform=(bed_id,))
    assert calls == [BEGIN, ("update_transform", bed_id), COMMIT] and built == []
    assert pipeline.sink.item(bed_id).transform.rotation_deg == 30.0

    # ── recolour: ONE update_material, no builder call ───────────────────────
    commands.execute(recolour_fill(bed, QColor(200, 30, 30)))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(material=(bed_id,))
    assert calls == [BEGIN, ("update_material", bed_id), COMMIT] and built == []
    assert pipeline.sink.item(bed_id).material.tint_rgba == (200, 30, 30, 255)

    # ── resize about the centre: ONE replace_geometry, ONE build ─────────────
    old, new = build_rect_resize(bed, 500.0, 120.0, keep_center=True)
    commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(geometry=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id), COMMIT] and built == [bed_id]
    low, high = pipeline.sink.item(bed_id).parts[0].mesh.bounds()
    assert (float(low[0]), float(high[0]), float(low[1]), float(high[1])) == (-250.0, 250.0, -60.0, 60.0)

    # ── select, then deselect: nothing reaches the engine ────────────────────
    bed.setSelected(True)
    assert pipeline.tick() == (SceneDiff(), [], [])
    bed.setSelected(False)
    assert pipeline.tick() == (SceneDiff(), [], [])

    # ── delete: ONE remove ───────────────────────────────────────────────────
    commands.execute(DeleteItemsCommand(scene, [tree]))
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(removed=(tree_id,))
    assert calls == [BEGIN, ("remove", tree_id), COMMIT] and built == []

    # ── undo the delete: ONE add, ONE build ──────────────────────────────────
    commands.undo()
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(added=(tree_id,))
    assert calls == [BEGIN, ("add", tree_id), COMMIT] and built == [tree_id]

    # ── undo the resize, then redo it ────────────────────────────────────────
    commands.undo()
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(geometry=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id), COMMIT] and built == [bed_id]
    commands.redo()
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(geometry=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id), COMMIT] and built == [bed_id]

    # ── undo back through resize, recolour, rotation and move in one tick ────
    for _ in range(4):
        commands.undo()
    result, calls, built = pipeline.tick()
    assert result == SceneDiff(geometry=(bed_id,), transform=(bed_id,), material=(bed_id,))
    assert calls == [BEGIN, ("replace_geometry", bed_id), ("update_transform", bed_id),
                     ("update_material", bed_id), COMMIT]
    assert built == [bed_id]
    assert pipeline.sink.item(bed_id).transform == held.transform  # exactly where it was drawn
    assert pipeline.sync.build_count == 9  # 4 adds + resize + re-add + undo + redo + undo — no move, turn or recolour


# ── gate G2: the diff matrix, end to end through SceneSync + RecordingSink ────
#
# The same edits as `test_scene3d_snapshot.py::TestDiffMatrix`, over every footprint
# shape they apply to. For each: the diff, the EXACT sink calls, the builder
# invocations (a move builds nothing), and incremental == full rebuild.

ALL = set(FACTORIES)


def _move(s: Stage) -> None:
    s.commands.execute(MoveItemsCommand([s.item], QPointF(137.25, -42.5)))


def _rotate(s: Stage) -> None:
    s.commands.execute(RotateItemCommand(s.item, 0.0, 213.5, apply_rotation))


def _colour(s: Stage) -> None:
    edit = restroke if s.shape == "polyline" else recolour_fill  # a line has no fill
    s.commands.execute(edit(s.item, QColor(10, 200, 30)))


def _height(s: Stage) -> None:
    s.item.metadata[METADATA_KEY] = 321.5


def _resize_centred(s: Stage) -> None:
    s.commands.execute(resize_command(s.item, s.shape, keep_center=True))


def _resize_corner(s: Stage) -> None:
    s.commands.execute(resize_command(s.item, s.shape, keep_center=False))


def _vertex(s: Stage, index: int, dx: float, dy: float) -> None:
    old = QPointF(s.item._get_vertex_position(index))
    s.commands.execute(build_move_vertex_command(
        s.item, index, old, QPointF(old.x() + dx, old.y() + dy)))


def _vertex_inside(s: Stage) -> None:
    _vertex(s, 3 if s.shape == "polygon" else 1, 12.5, -7.25)


def _vertex_extreme(s: Stage) -> None:
    _vertex(s, 0, -60.0, -30.0)


def _later_date(s: Stage) -> None:
    s.at = date(2040, 1, 1)


def _select(s: Stage) -> None:
    s.item.setSelected(True)


def _rename(s: Stage) -> None:
    s.item.name = "Renamed"


def _delete(s: Stage) -> None:
    s.commands.execute(DeleteItemsCommand(s.scene, [s.item]))


def _hide(s: Stage) -> None:
    s.item.setVisible(False)


def _send_to_back(s: Stage) -> None:
    command, _outcome = build_arrange_command(s.scene, [s.item], ArrangeMode.SEND_TO_BACK)
    assert command is not None
    s.commands.execute(command)


def _nothing(_item_id: str) -> SceneDiff:
    return SceneDiff()


def _transform(item_id: str) -> SceneDiff:
    return SceneDiff(transform=(item_id,))


def _material(item_id: str) -> SceneDiff:
    return SceneDiff(material=(item_id,))


def _geometry(item_id: str) -> SceneDiff:
    return SceneDiff(geometry=(item_id,))


def _geometry_and_transform(item_id: str) -> SceneDiff:
    return SceneDiff(geometry=(item_id,), transform=(item_id,))


def _removed(item_id: str) -> SceneDiff:
    return SceneDiff(removed=(item_id,))


def _reordered(_item_id: str) -> SceneDiff:
    return SceneDiff(reordered=True)


Edit = tuple[str, set[str], Callable[[Stage], None], Callable[[str], SceneDiff]]
EDITS: list[Edit] = [
    ("move", ALL, _move, _transform),
    ("rotate", ALL - ROUND, _rotate, _transform),
    ("rotate a circle about its centre", ROUND, _rotate, _nothing),
    ("recolour", ALL, _colour, _material),
    ("height", ALL, _height, _geometry),
    ("centred resize", {"circle", "ellipse", "rectangle"}, _resize_centred, _geometry),
    ("resize the drawn circle of a measured plant", {"plant"}, _resize_centred, _nothing),
    ("one-sided resize", RECT_BACKED, _resize_corner, _geometry_and_transform),
    ("vertex inside the bounding box", VERTEX_BACKED, _vertex_inside, _geometry),
    ("vertex growing the bounding box", VERTEX_BACKED, _vertex_extreme, _geometry_and_transform),
    ("a later date", {"plant"}, _later_date, _geometry),
    ("a later date", ALL - {"plant"}, _later_date, _nothing),
    ("select", ALL, _select, _nothing),
    ("rename", ALL, _rename, _nothing),
    ("delete", ALL, _delete, _removed),
    ("hide", ALL, _hide, _removed),
    ("send to back", ALL, _send_to_back, _reordered),
]
CASES = [(name, shape, do, expect)
         for name, shapes, do, expect in EDITS for shape in sorted(shapes)]


def minimal_calls(change: SceneDiff) -> list[tuple[str, str | None]]:
    """The sink calls a diff may cause — nothing else, and nothing at all when the
    engine has nothing to do."""
    if not change.touches_sink:
        return []
    return [BEGIN,
            *[("remove", i) for i in change.removed],
            *[("add", i) for i in change.added],
            *[("replace_geometry", i) for i in change.geometry],
            *[("update_transform", i) for i in change.transform],
            *[("update_material", i) for i in change.material],
            COMMIT]


class Rig:
    """A ``Stage`` (real view, scene, undo stack, one item of a shape) wired to a
    counting builder, a ``SceneSync`` and a ``RecordingSink``."""

    def __init__(self, canvas: CanvasView, shape: str) -> None:
        self.stage = Stage(canvas, shape)
        self.built: list[str] = []
        self.sink = RecordingSink()
        self.sync = SceneSync(self.sink, BuilderRegistry(default=self._build), validate=True)
        self.tick()
        assert sorted(self.built) == sorted([self.stage.id, str(self.stage.bystander.item_id)])

    def _build(self, record: Record) -> tuple[MeshPart, ...]:
        self.built.append(record.item_id)
        return default_builder(record)

    def tick(self) -> tuple[SceneDiff, list[tuple[str, str | None]], list[str]]:
        self.sink.clear_calls()
        self.built.clear()
        records = self.stage.snapshot()
        result = self.sync.apply(records)
        fresh = RecordingSink()
        SceneSync(fresh, validate=True).apply(records)
        assert self.sink.state() == fresh.state()  # incremental == full rebuild
        assert self.sync.failures == {}
        return result, self.sink.ops(), list(self.built)


@pytest.mark.parametrize(("name", "shape", "do", "expect"), CASES,
                         ids=[f"{name}-{shape}" for name, shape, _do, _expect in CASES])
def test_sink_receives_exactly_the_minimal_calls(
    canvas: CanvasView, name: str, shape: str,
    do: Callable[[Stage], None], expect: Callable[[str], SceneDiff],
) -> None:
    rig = Rig(canvas, shape)
    do(rig.stage)
    result, calls, built = rig.tick()
    expected = expect(rig.stage.id)
    assert result == expected, name
    assert calls == minimal_calls(expected)
    assert built == list(expected.geometry)  # a move, a turn, a recolour build nothing
    assert rig.tick() == (SceneDiff(), [], [])  # and the next tick is silent


@pytest.mark.parametrize("shape", sorted(ALL))
def test_undo_of_a_delete_is_one_add_and_one_build(canvas: CanvasView, shape: str) -> None:
    rig = Rig(canvas, shape)
    _delete(rig.stage)
    rig.tick()
    rig.stage.commands.undo()
    result, calls, built = rig.tick()
    assert result == SceneDiff(added=(rig.stage.id,))
    assert calls == [BEGIN, ("add", rig.stage.id), COMMIT] and built == [rig.stage.id]


def test_the_matrix_names_every_edit_of_the_gate() -> None:
    """Every shape meets every kind of edit the gate lists — nothing silently left out."""
    by_shape: dict[str, set[str]] = {shape: set() for shape in ALL}
    for name, shapes, _do, _expect in EDITS:
        for shape in shapes:
            by_shape[shape].add(name)
    everywhere = {"move", "recolour", "height", "a later date", "select", "rename", "delete",
                  "hide", "send to back"}
    for shape, names in by_shape.items():
        assert everywhere <= names, shape
        assert {"rotate", "rotate a circle about its centre"} & names, shape
        assert any("resize" in n or "vertex" in n for n in names), shape
    assert len(CASES) == 70


def test_two_edits_between_ticks_arrive_in_one_transaction(canvas: CanvasView) -> None:
    """The pipeline is driven by a debounced tick (L1.3), not by every command:
    whatever happened in between is one diff and one begin/commit."""
    scene = canvas.scene()
    shed = RectangleItem(100.0, 100.0, 300.0, 200.0, object_type=ObjectType.TOOL_SHED)
    lawn = RectangleItem(600.0, 100.0, 400.0, 400.0, object_type=ObjectType.LAWN)
    for item in (shed, lawn):
        canvas.command_manager.execute(CreateItemCommand(scene, item, "rectangle"))
    pipeline = Pipeline(scene)
    pipeline.tick()
    canvas.command_manager.execute(MoveItemsCommand([shed, lawn], QPointF(10.0, 20.0)))
    canvas.command_manager.execute(recolour_fill(lawn, QColor(1, 2, 3)))
    canvas.command_manager.execute(DeleteItemsCommand(scene, [shed]))
    wall = PolylineItem([QPointF(0.0, 0.0), QPointF(300.0, 0.0)], object_type=ObjectType.WALL)
    canvas.command_manager.execute(CreateItemCommand(scene, wall, "wall"))
    result, calls, built = pipeline.tick()
    shed_id, lawn_id, wall_id = (str(i.item_id) for i in (shed, lawn, wall))
    assert result == SceneDiff(added=(wall_id,), removed=(shed_id,), transform=(lawn_id,),
                               material=(lawn_id,))
    assert calls == [BEGIN, ("remove", shed_id), ("add", wall_id), ("update_transform", lawn_id),
                     ("update_material", lawn_id), COMMIT]
    assert built == [wall_id] and pipeline.sink.transactions == 2


@pytest.mark.parametrize("plan", ["bench_small.ogp", "bench_large.ogp"])
def test_bench_plan_first_apply_then_silence(qtbot, plan: str) -> None:
    """Opening a plan adds every record once; ticking again says nothing."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    pipeline = Pipeline(scene, JUNE)
    result, calls, built = pipeline.tick()
    expected = 99 if plan == "bench_small.ogp" else 425
    assert len(result.added) == len(built) == expected
    assert calls == [BEGIN, *[("add", i) for i in result.added], COMMIT]
    for _ in range(3):
        assert pipeline.tick() == (SceneDiff(), [], [])


def test_real_app_edit_and_sim_date(qtbot, monkeypatch) -> None:
    """The same pipeline on the real application: its scene, its undo stack and
    its ONE sim clock (ADR-053) — the plan date the 3D view grows plants for."""
    from open_garden_planner.app.application import GardenPlannerApp

    # the edits below dirty the document; closing must not ask "discard changes?"
    monkeypatch.setattr(GardenPlannerApp, "_confirm_discard_changes", lambda _self: True)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._project_manager.load(win.canvas_scene, PLANS / "bench_small.ogp")
    win._sim_clock.set_datetime(datetime(2026, 6, 21, 12, 0))
    pipeline = Pipeline(win.canvas_scene, win._sim_clock.plan_date)
    result, _calls, built = pipeline.tick()
    assert len(result.added) == len(built) == 99

    # an edit through the app's own undo stack
    house = next(i for i in win.canvas_scene.items()
                 if getattr(i, "object_type", None) == ObjectType.HOUSE)
    house_id = str(house.item_id)
    ridge_id = str(house.metadata["ridge_item_id"])
    win.canvas_view.command_manager.execute(MoveItemsCommand([house], QPointF(50.0, -25.0)))
    result, calls, built = pipeline.tick()
    # the house and its ridge item move together; the ridge END POINTS in the
    # house's own frame did not change, so the house is NOT rebuilt
    assert set(result.transform) == {house_id, ridge_id}
    assert result.geometry == () and result.material == () and built == []
    assert sorted(calls[1:-1]) == sorted([("update_transform", house_id), ("update_transform", ridge_id)])
    win.canvas_view.command_manager.undo()
    result, calls, built = pipeline.tick()
    assert set(result.transform) == {house_id, ridge_id} and result.geometry == () and built == []

    # the sim clock moves ten years on: only the dated plants grow
    win._sim_clock.set_date(date(2036, 6, 21))
    pipeline.at = win._sim_clock.plan_date
    result, calls, built = pipeline.tick()
    grown = set(result.geometry)
    assert grown and result.transform == () and result.material == ()
    assert result.added == () and result.removed == ()
    kinds = {pipeline.sync.records[i].kind for i in grown}
    assert kinds <= {"TREE", "SHRUB", "PERENNIAL"}
    assert sorted(built) == sorted(grown)
    assert [op for op, _ in calls[1:-1]] == ["replace_geometry"] * len(grown)
