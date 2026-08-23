"""Integration tests: per-object stacking order arrange gestures (issue #338).

Exercises the full Qt-aware seam -- `CanvasView.arrange_selected` ->
`ui.canvas.arrange.build_arrange_command` -> `core.stacking.arrange` ->
`ArrangeItemsCommand` -- rather than the pure `core.stacking` algorithm
(covered by `tests/unit/test_stacking.py`) or `CanvasScene._normalized_layer_order`
in isolation (covered by `tests/unit/test_plant_bed_zorder.py`).
"""
# ruff: noqa: ARG002

from open_garden_planner.core.commands import MoveToLayerCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.arrange import build_arrange_command
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rect(
    name: str,
    x: float,
    y: float,
    layer_id,
    object_type: ObjectType = ObjectType.GENERIC_RECTANGLE,
    width: float = 100.0,
    height: float = 100.0,
) -> RectangleItem:
    return RectangleItem(
        x, y, width, height, object_type=object_type, name=name, layer_id=layer_id
    )


def _circle(
    name: str,
    cx: float,
    cy: float,
    layer_id,
    object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
    radius: float = 20.0,
) -> CircleItem:
    return CircleItem(
        center_x=cx,
        center_y=cy,
        radius=radius,
        object_type=object_type,
        name=name,
        layer_id=layer_id,
    )


def _bottom_to_top_names(scene: CanvasScene) -> list[str]:
    """Every named item in the scene, bottom-to-top by z-value."""
    items = [i for i in scene.items() if getattr(i, "name", None)]
    return [i.name for i in sorted(items, key=lambda i: i.zValue())]


def _add_layer(scene: CanvasScene, name: str) -> Layer:
    layer = Layer(name=name, z_order=len(scene.layers))
    scene.add_layer(layer)
    return layer


def _link_plant(bed, plant) -> None:
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)


# ---------------------------------------------------------------------------
# Each of the four modes
# ---------------------------------------------------------------------------


class TestFourModes:
    def test_bring_to_front(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)
        assert _bottom_to_top_names(scene) == ["a", "b", "c"]

        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)

        assert _bottom_to_top_names(scene) == ["b", "c", "a"]

    def test_send_to_back(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)

        c.setSelected(True)
        canvas.arrange_selected(ArrangeMode.SEND_TO_BACK)

        assert _bottom_to_top_names(scene) == ["c", "a", "b"]

    def test_bring_forward(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)

        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_FORWARD)

        assert _bottom_to_top_names(scene) == ["b", "a", "c"]

    def test_send_backward(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)

        c.setSelected(True)
        canvas.arrange_selected(ArrangeMode.SEND_BACKWARD)

        assert _bottom_to_top_names(scene) == ["a", "c", "b"]


# ---------------------------------------------------------------------------
# Undo/redo round-trip restores exact previous zValue order
# ---------------------------------------------------------------------------


class TestUndoRedoRoundTrip:
    def test_undo_redo_restores_exact_zvalues(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)

        before = {item.name: item.zValue() for item in (a, b, c)}

        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
        after = {item.name: item.zValue() for item in (a, b, c)}
        assert after != before

        canvas.command_manager.undo()
        restored = {item.name: item.zValue() for item in (a, b, c)}
        assert restored == before, "Undo must restore the exact previous zValues"

        canvas.command_manager.redo()
        redone = {item.name: item.zValue() for item in (a, b, c)}
        assert redone == after, "Redo must reproduce the exact post-arrange zValues"


# ---------------------------------------------------------------------------
# Dirty flag on execute / undo / redo
# ---------------------------------------------------------------------------


class TestDirtyFlag:
    def test_execute_undo_redo_mark_project_dirty(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        scene.addItem(a)
        scene.addItem(b)

        manager = ProjectManager()
        canvas.command_manager.stack_changed.connect(manager.mark_dirty)

        manager.mark_clean()
        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
        assert manager.is_dirty, "Arrange (execute) must mark the project dirty"

        manager.mark_clean()
        canvas.command_manager.undo()
        assert manager.is_dirty, "Undo must mark the project dirty"

        manager.mark_clean()
        canvas.command_manager.redo()
        assert manager.is_dirty, "Redo must mark the project dirty"


# ---------------------------------------------------------------------------
# No-op outcomes push nothing onto the undo stack
# ---------------------------------------------------------------------------


class TestNoOpOutcomes:
    def test_nothing_selected(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        scene.addItem(_rect("a", 0, 0, layer_id))

        command, outcome = build_arrange_command(scene, [], ArrangeMode.BRING_TO_FRONT)
        assert command is None
        assert outcome is ArrangeOutcome.NOTHING_SELECTED

        can_undo_before = canvas.command_manager.can_undo
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
        assert canvas.command_manager.can_undo == can_undo_before

    def test_already_at_front(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        scene.addItem(a)
        scene.addItem(b)

        command, outcome = build_arrange_command(scene, [b], ArrangeMode.BRING_TO_FRONT)
        assert command is None
        assert outcome is ArrangeOutcome.ALREADY_AT_FRONT

        can_undo_before = canvas.command_manager.can_undo
        b.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
        assert canvas.command_manager.can_undo == can_undo_before

    def test_already_at_back(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        scene.addItem(a)
        scene.addItem(b)

        command, outcome = build_arrange_command(scene, [a], ArrangeMode.SEND_TO_BACK)
        assert command is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK

        can_undo_before = canvas.command_manager.can_undo
        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.SEND_TO_BACK)
        assert canvas.command_manager.can_undo == can_undo_before

    def test_no_overlap_above(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 1000, 1000, layer_id)  # far away, no overlap
        scene.addItem(a)
        scene.addItem(b)

        command, outcome = build_arrange_command(scene, [a], ArrangeMode.BRING_FORWARD)
        assert command is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_ABOVE

        can_undo_before = canvas.command_manager.can_undo
        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_FORWARD)
        assert canvas.command_manager.can_undo == can_undo_before

    def test_no_overlap_below(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 1000, 1000, layer_id)  # far away, no overlap
        scene.addItem(a)
        scene.addItem(b)

        command, outcome = build_arrange_command(scene, [b], ArrangeMode.SEND_BACKWARD)
        assert command is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_BELOW

        can_undo_before = canvas.command_manager.can_undo
        b.setSelected(True)
        canvas.arrange_selected(ArrangeMode.SEND_BACKWARD)
        assert canvas.command_manager.can_undo == can_undo_before


# ---------------------------------------------------------------------------
# Multi-selection keeps relative order and becomes contiguous
# ---------------------------------------------------------------------------


class TestMultiSelectionRelativeOrder:
    def test_non_contiguous_selection_becomes_contiguous_at_front(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 200, 0, layer_id)
        c = _rect("c", 400, 0, layer_id)
        d = _rect("d", 600, 0, layer_id)
        for item in (a, b, c, d):
            scene.addItem(item)
        assert _bottom_to_top_names(scene) == ["a", "b", "c", "d"]

        a.setSelected(True)
        c.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)

        assert _bottom_to_top_names(scene) == ["b", "d", "a", "c"]


# ---------------------------------------------------------------------------
# Bed block: bring bed to front carries plants above it, in order
# ---------------------------------------------------------------------------


class TestBedBlock:
    def test_bring_bed_to_front_carries_plants_in_order(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        lawn = _rect("lawn", 0, 0, layer_id, ObjectType.LAWN)
        bed = _rect("bed", 200, 0, layer_id, ObjectType.RAISED_BED)
        plant1 = _circle("plant1", 220, 20, layer_id, ObjectType.TREE)
        plant2 = _circle("plant2", 250, 20, layer_id, ObjectType.TREE)
        path = _rect("path", 500, 0, layer_id, ObjectType.PATH)
        scene.addItem(lawn)
        scene.addItem(bed)
        scene.addItem(plant1)
        scene.addItem(plant2)
        scene.addItem(path)
        _link_plant(bed, plant1)
        _link_plant(bed, plant2)

        bed.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)

        assert _bottom_to_top_names(scene) == ["lawn", "path", "bed", "plant1", "plant2"]
        assert bed.zValue() < plant1.zValue() < plant2.zValue()


# ---------------------------------------------------------------------------
# Plant clamp: a lone linked plant can't be sent below its bed
# ---------------------------------------------------------------------------


class TestPlantClamp:
    def test_send_lone_plant_to_back_stops_above_its_bed(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        lawn = _rect("lawn", 0, 0, layer_id, ObjectType.LAWN)
        bed = _rect("bed", 200, 0, layer_id, ObjectType.RAISED_BED)
        plant1 = _circle("plant1", 220, 20, layer_id, ObjectType.TREE)
        scene.addItem(lawn)
        scene.addItem(bed)
        scene.addItem(plant1)
        _link_plant(bed, plant1)

        assert bed.zValue() < plant1.zValue(), "Setup: plant already clamped above bed"

        command, outcome = build_arrange_command(scene, [plant1], ArrangeMode.SEND_TO_BACK)
        assert command is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK

        can_undo_before = canvas.command_manager.can_undo
        plant1.setSelected(True)
        canvas.arrange_selected(ArrangeMode.SEND_TO_BACK)
        assert canvas.command_manager.can_undo == can_undo_before
        assert bed.zValue() < plant1.zValue(), "Plant must still render directly above its bed"


# ---------------------------------------------------------------------------
# Cross-layer selection: one command, each item frontmost in its own layer
# ---------------------------------------------------------------------------


class TestCrossLayerSelection:
    def test_bring_to_front_across_two_layers_is_one_command(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer1_id = scene.active_layer.id
        layer2 = _add_layer(scene, "Layer 2")

        a1 = _rect("a1", 0, 0, layer1_id)  # bottom of layer 1
        a2 = _rect("a2", 20, 20, layer1_id)  # top of layer 1
        b1 = _rect("b1", 0, 0, layer2.id)  # bottom of layer 2
        b2 = _rect("b2", 20, 20, layer2.id)  # top of layer 2
        for item in (a1, a2, b1, b2):
            scene.addItem(item)
        assert a1.zValue() < a2.zValue()
        assert b1.zValue() < b2.zValue()

        undo_count_before = len(canvas.command_manager._undo_stack)
        a1.setSelected(True)
        b1.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
        undo_count_after = len(canvas.command_manager._undo_stack)

        assert undo_count_after == undo_count_before + 1, (
            "A cross-layer arrange must push exactly one undo step"
        )
        assert a1.zValue() > a2.zValue(), "a1 must now be frontmost within layer 1"
        assert b1.zValue() > b2.zValue(), "b1 must now be frontmost within layer 2"


# ---------------------------------------------------------------------------
# Bring Forward steps past the nearest OVERLAPPING item, skipping a
# non-overlapping one in between
# ---------------------------------------------------------------------------


class TestForwardStepsPastOverlap:
    def test_forward_skips_non_overlapping_item(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        # A overlaps only C's rect; B does not overlap A at all.
        a = _rect("a", 0, 0, layer_id, width=10, height=10)
        b = _rect("b", 1000, 1000, layer_id, width=10, height=10)
        c = _rect("c", 5, 5, layer_id, width=10, height=10)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)
        assert _bottom_to_top_names(scene) == ["a", "b", "c"]

        a.setSelected(True)
        canvas.arrange_selected(ArrangeMode.BRING_FORWARD)

        assert _bottom_to_top_names(scene) == ["b", "c", "a"], (
            "Forward must jump straight past the non-overlapping b to swap with c"
        )


# ---------------------------------------------------------------------------
# MoveToLayerCommand rank handling
# ---------------------------------------------------------------------------


class TestMoveToLayerRankHandling:
    def test_moved_items_land_on_top_of_target_in_relative_order(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer1_id = scene.active_layer.id
        layer2 = _add_layer(scene, "Layer 2")

        seed = _rect("seed", 0, 0, layer2.id)
        scene.addItem(seed)

        a = _rect("a", 100, 0, layer1_id)
        b = _rect("b", 200, 0, layer1_id)
        scene.addItem(a)
        scene.addItem(b)
        assert a.stack_order < b.stack_order

        cmd = MoveToLayerCommand([a, b], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)

        assert a.layer_id == layer2.id
        assert b.layer_id == layer2.id
        assert a.stack_order > seed.stack_order
        assert b.stack_order > seed.stack_order
        assert a.stack_order < b.stack_order, "Relative order of the moved items is kept"

    def test_same_layer_item_keeps_its_rank(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer1_id = scene.active_layer.id
        layer2 = _add_layer(scene, "Layer 2")

        already_there = _rect("already_there", 0, 0, layer2.id)
        moving = _rect("moving", 100, 0, layer1_id)
        scene.addItem(already_there)
        scene.addItem(moving)
        rank_before = already_there.stack_order

        cmd = MoveToLayerCommand([already_there, moving], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)

        assert already_there.stack_order == rank_before, (
            "An item already in the target layer must keep its existing rank"
        )
        assert moving.layer_id == layer2.id

    def test_undo_restores_exact_layer_and_rank(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer1_id = scene.active_layer.id
        layer2 = _add_layer(scene, "Layer 2")
        # Seed the target layer so the fresh rank the item gets there is
        # guaranteed to differ from its original rank in layer 1.
        scene.addItem(_rect("seed", 0, 0, layer2.id))

        item = _rect("item", 100, 0, layer1_id)
        scene.addItem(item)
        original_layer_id = item.layer_id
        original_rank = item.stack_order

        cmd = MoveToLayerCommand([item], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)
        assert item.layer_id == layer2.id
        assert item.stack_order != original_rank

        canvas.command_manager.undo()

        assert item.layer_id == original_layer_id
        assert item.stack_order == original_rank
