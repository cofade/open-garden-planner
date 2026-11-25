"""Issue #443: bed membership is reconciled by every edit path, as ONE undo step.

``GardenItem.parent_bed_id`` (with the parent's ``child_item_ids``) is
bookkeeping, and until #443 only a few actions kept it in step with geometry:
a bed that changed, most ways of moving or copying a plant, and a bed moved by
a typed coordinate or align/distribute all left the link stale — so the
Properties panel, the soil-mismatch and companion logic and the diagnostics
could follow a link to a bed the plant no longer stands in, or miss one it
does.

These tests drive the real commands and the real scene: the rule is one — a
plant's link is the smallest plant-parent containing its standing point — and
each edit path must apply it inside the SAME undo entry as the edit.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.core.commands import (
    CreateItemCommand,
    MoveItemsCommand,
    MultiVertexMoveCommand,
    SetParentBedCommand,
    register_applied_with_membership,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.footprints import (
    bed_membership_point,
    standing_point,
)
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rotation,
    register_rotation_command,
)
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


def _bed(canvas: CanvasView, x: float = 400.0, y: float = 300.0) -> RectangleItem:
    bed = RectangleItem(
        x, y, 300.0, 200.0,
        object_type=ObjectType.RAISED_BED,
        layer_id=canvas.scene().active_layer.id,
    )
    canvas.command_manager.execute(CreateItemCommand(canvas.scene(), bed, "bed"))
    return bed


def _plant(
    canvas: CanvasView, x: float, y: float, *, radius: float = 15.0
) -> CircleItem:
    plant = CircleItem(
        x, y, radius,
        object_type=ObjectType.PERENNIAL,
        layer_id=canvas.scene().active_layer.id,
    )
    plant.metadata["object_height_cm"] = 60.0
    canvas.command_manager.execute(CreateItemCommand(canvas.scene(), plant, "plant"))
    return plant


def _base(canvas: CanvasView, plant: CircleItem) -> float:
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    return snapshot_records(canvas.scene())[str(plant.item_id)].transform.base_cm


class TestBedEditsReconcileMembership:
    """(i) a bed's create / resize / turn / vertex edit re-decides its plants."""

    def test_resizing_a_bed_away_from_a_plant_unlinks_it_in_one_step(
        self, canvas: CanvasView
    ) -> None:
        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        assert plant.parent_bed_id == bed.item_id
        assert _base(canvas, plant) == 38.0
        undo_before = canvas.command_manager.undo_depth

        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_rect_resize,
        )

        old, new = build_rect_resize(bed, 60.0, 200.0)
        from open_garden_planner.core.commands import ResizeItemCommand

        canvas.command_manager.execute(
            ResizeItemCommand(bed, old, new, apply_rect_like_geometry)
        )

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        assert _base(canvas, plant) == 0.0

        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        assert _base(canvas, plant) == 38.0

    def test_turning_a_bed_relinks_its_plants_in_one_step(
        self, canvas: CanvasView
    ) -> None:
        """A long bed turned 90° no longer contains its end plant; undo re-links."""
        bed = RectangleItem(
            400.0, 300.0, 600.0, 100.0,
            object_type=ObjectType.RAISED_BED,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), bed, "bed"))
        plant = _plant(canvas, 950.0, 350.0)  # near the east end, not the centre
        assert plant.parent_bed_id == bed.item_id
        undo_before = canvas.command_manager.undo_depth

        # The live geometry, then the handle's release path.
        apply_rotation(bed, 90.0)
        assert register_rotation_command(bed, 0.0) is True

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids

        canvas.command_manager.undo()
        assert bed.rotation() == pytest.approx(0.0)
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        canvas.command_manager.redo()
        assert plant.parent_bed_id is None

    def test_a_live_applied_bed_resize_is_one_undo_step_and_no_extra_move(
        self, canvas: CanvasView
    ) -> None:
        """The drag-release path: geometry applied live, registered once.

        `_finalize_drag_move` must recognise the resize THROUGH the membership
        compound, or it adds a second position entry for the same gesture.
        """
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_rect_resize,
        )

        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        assert plant.parent_bed_id == bed.item_id
        undo_before = canvas.command_manager.undo_depth
        start_pos = QPointF(bed.pos())
        old, new = build_rect_resize(bed, 60.0, 200.0)
        apply_rect_like_geometry(bed, new)  # what the handle does live
        register_applied_with_membership(
            canvas.scene(),
            canvas.command_manager,
            ResizeItemCommand(bed, old, new, apply_rect_like_geometry),
            bed,
        )
        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        # A resize may move the item's pos (anchored resize); the release must
        # not record that as a second move step.
        canvas._drag_start_positions = {bed: start_pos}
        canvas._finalize_drag_move()
        assert canvas.command_manager.undo_depth == undo_before + 1
        assert not canvas._drag_start_positions

    def test_a_bed_vertex_drag_relinks_in_the_same_undo_step(
        self, canvas: CanvasView
    ) -> None:
        """The canonical vertex-drag path: geometry applied live, one registered step."""
        scene = canvas.scene()
        bed = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 200.0), QPointF(0.0, 200.0)],
            object_type=ObjectType.RAISED_BED,
            layer_id=scene.active_layer.id,
        )
        bed.setPos(400.0, 300.0)
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        plant = _plant(canvas, 500.0, 400.0)
        assert plant.parent_bed_id == bed.item_id

        # Pull the east side to x = 620 so (500, 400) is outside the 0..220 width.
        old = bed._get_vertex_position(1)
        bed._move_vertex_to(1, QPointF(-180.0, 0.0))
        bed._move_vertex_to(2, QPointF(-180.0, 200.0))
        command = MultiVertexMoveCommand([
            (bed, 1, old, QPointF(-180.0, 0.0)),
            (bed, 2, QPointF(300.0, 200.0), QPointF(-180.0, 200.0)),
        ])
        undo_before = canvas.command_manager.undo_depth
        register_applied_with_membership(canvas.scene(), canvas.command_manager, command, bed)

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids


class TestMovesReconcileMembership:
    """(iv)/(vi): plant moves re-evaluate; bed moves take their plants along."""

    def test_plant_moved_in_and_out_is_linked_in_both_directions(
        self, canvas: CanvasView
    ) -> None:
        bed = _bed(canvas)
        loner = _plant(canvas, 1000.0, 400.0)
        assert loner.parent_bed_id is None

        canvas.command_manager.execute(MoveItemsCommand([loner], QPointF(-500.0, 0.0)))
        assert loner.parent_bed_id == bed.item_id
        assert loner.item_id in bed.child_item_ids
        assert _base(canvas, loner) == 38.0
        canvas.command_manager.undo()
        assert loner.parent_bed_id is None
        assert loner.item_id not in bed.child_item_ids
        assert _base(canvas, loner) == 0.0

    def test_moving_a_group_out_of_a_bed_unlinks_its_plants_in_one_step(
        self, canvas: CanvasView
    ) -> None:
        """#1001: a group is not a plant, but its members are."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(3)]
        assert all(plant.parent_bed_id == bed.item_id for plant in plants)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), plants))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        undo_before = canvas.command_manager.undo_depth

        canvas.command_manager.execute(
            MoveItemsCommand([group], QPointF(3000.0, 0.0))
        )

        assert canvas.command_manager.undo_depth == undo_before + 1
        for plant in plants:
            assert plant.parent_bed_id is None
            assert plant.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        for plant in plants:
            assert plant.parent_bed_id == bed.item_id
            assert plant.item_id in bed.child_item_ids

    def test_moving_a_group_that_contains_its_bed_carries_each_plant_once(
        self, canvas: CanvasView
    ) -> None:
        """A bed inside the group already carries its linked plants.

        The bed-child expansion must not add a second delta to plants the
        group's Qt move already carries (#1001 review).
        """
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(3)]
        before = [plant.scenePos() for plant in plants]
        before_bed = bed.scenePos()
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, *plants]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        undo_before = canvas.command_manager.undo_depth

        canvas.command_manager.execute(
            MoveItemsCommand([group], QPointF(100.0, 50.0))
        )

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert (bed.scenePos().x(), bed.scenePos().y()) == pytest.approx(
            (before_bed.x() + 100.0, before_bed.y() + 50.0)
        )
        for plant, start in zip(plants, before, strict=True):
            assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
                (start.x() + 100.0, start.y() + 50.0)
            )
            assert plant.parent_bed_id == bed.item_id
            assert plant.item_id in bed.child_item_ids
        canvas.command_manager.undo()
        for plant, start in zip(plants, before, strict=True):
            assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
                (start.x(), start.y())
            )
            assert plant.parent_bed_id == bed.item_id

    def test_a_move_that_lists_a_group_and_its_plant_moves_it_once(
        self, canvas: CanvasView
    ) -> None:
        """A caller listing a group and its child must not add the child delta twice."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before = QPointF(plant.scenePos())

        canvas.command_manager.execute(
            MoveItemsCommand([group, plant], QPointF(50.0, 0.0))
        )

        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before.x() + 50.0, before.y())
        )
        canvas.command_manager.undo()
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before.x(), before.y())
        )

    def test_aligning_a_group_and_its_child_keeps_the_child_delta(
        self, canvas: CanvasView
    ) -> None:
        """Align has per-item deltas; a carried child keeps its distinct scene delta."""
        from open_garden_planner.core.commands import AlignItemsCommand, GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before_bed = QPointF(bed.scenePos())
        before_plant = QPointF(plant.scenePos())

        canvas.command_manager.execute(AlignItemsCommand([
            (group, QPointF(100.0, 0.0)),
            (plant, QPointF(0.0, 0.0)),
        ]))

        assert (bed.scenePos().x(), bed.scenePos().y()) == pytest.approx(
            (before_bed.x() + 100.0, before_bed.y())
        )
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x(), before_plant.y())
        )
        canvas.command_manager.undo()
        assert (bed.scenePos().x(), bed.scenePos().y()) == pytest.approx(
            (before_bed.x(), before_bed.y())
        )
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x(), before_plant.y())
        )

    def test_aligning_an_outer_group_keeps_a_grandchild_scene_delta(
        self, canvas: CanvasView
    ) -> None:
        """The nearest LISTED ancestor supplies the residual; a skipped level still moves."""
        from open_garden_planner.core.commands import AlignItemsCommand, GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        inner = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [inner]))
        outer = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem) and item is not inner)
        before_plant = QPointF(plant.scenePos())

        canvas.command_manager.execute(AlignItemsCommand([
            (outer, QPointF(100.0, 0.0)),
            (plant, QPointF(0.0, 0.0)),
        ]))

        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x(), before_plant.y())
        )

    def test_a_constraint_propagated_child_in_a_group_keeps_its_local_delta(
        self, canvas: CanvasView
    ) -> None:
        """The finalizer passes local deltas; a child's solver correction is additive."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before_group = QPointF(group.scenePos())
        before_plant = QPointF(plant.scenePos())

        canvas._drag_start_positions = {group: QPointF(group.pos())}
        group.moveBy(100.0, 0.0)
        local_start = QPointF(plant.pos())
        plant.moveBy(20.0, 0.0)
        canvas._constraint_propagated_starts = {plant: local_start}
        canvas._drag_start_undo_depth = canvas.command_manager.undo_depth
        canvas._finalize_drag_move()

        assert (group.scenePos().x(), group.scenePos().y()) == pytest.approx(
            (before_group.x() + 100.0, before_group.y())
        )
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x() + 120.0, before_plant.y())
        )
        canvas.command_manager.undo()
        assert (group.scenePos().x(), group.scenePos().y()) == pytest.approx(
            (before_group.x(), before_group.y())
        )
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x(), before_plant.y())
        )

    def test_a_zero_move_is_not_recorded(
        self, canvas: CanvasView
    ) -> None:
        """#1001 review: an empty residual move is an explicit no-op, not an undo step."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before = QPointF(plant.scenePos())
        undo_before = canvas.command_manager.undo_depth

        canvas.command_manager.execute(
            MoveItemsCommand([group, plant], QPointF(0.0, 0.0))
        )

        assert canvas.command_manager.undo_depth == undo_before
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before.x(), before.y())
        )

    def test_a_ui_nudge_of_a_group_with_its_bed_moves_plants_once(
        self, qtbot: object, canvas: CanvasView
    ) -> None:
        """The arrow-key path expands bed children too; it must skip carried ones."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(2)]
        before = [plant.scenePos() for plant in plants]
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, *plants]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        canvas.scene().clearSelection()
        group.setSelected(True)
        undo_before = canvas.command_manager.undo_depth

        qtbot.keyClick(canvas, Qt.Key.Key_Right)  # type: ignore[attr-defined]

        assert canvas.command_manager.undo_depth == undo_before + 1
        for plant, start in zip(plants, before, strict=True):
            assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
                (start.x() + 50.0, start.y())
            )
            assert plant.parent_bed_id == bed.item_id

    def test_aligning_a_rotated_group_and_its_child_keeps_the_child_scene_delta(
        self, canvas: CanvasView
    ) -> None:
        """A group's residual is a SCENE delta; a rotated parent turns it (#1021 review).

        ``AlignItemsCommand(delta_frame="scene")`` subtracts the ancestor's
        delta and hands the rest to ``moveBy``, which is parent-local. On a
        rotated group that turns the residual, so the child that asked for a
        zero scene delta would move.
        """
        from open_garden_planner.core.commands import AlignItemsCommand, GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        group.setRotation(90.0)
        before_plant = QPointF(plant.scenePos())

        canvas.command_manager.execute(AlignItemsCommand([
            (group, QPointF(100.0, 0.0)),
            (plant, QPointF(0.0, 0.0)),
        ], delta_frame="scene"))

        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before_plant.x(), before_plant.y())
        )

    def test_a_single_scene_delta_inside_a_rotated_and_scaled_group_lands_in_scene(
        self, canvas: CanvasView
    ) -> None:
        """An item with an UNLISTED Qt parent takes its scene delta in scene space (#1020).

        ``moveBy`` is parent-local. With an unrotated parent the two frames agree,
        which is why only a rotated (and scaled) group showed the defect: the
        agent lists only its target, never the group that carries it.
        """
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        plant = _plant(canvas, 450.0, 350.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, plant]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        group.setRotation(30.0)
        group.setScale(1.5)
        before = QPointF(plant.scenePos())
        dx, dy = 40.0, -25.0

        canvas.command_manager.execute(
            MoveItemsCommand([plant], QPointF(dx, dy), delta_frame="scene")
        )

        moved = plant.scenePos()
        assert (moved.x() - before.x(), moved.y() - before.y()) == pytest.approx(
            (dx, dy)
        )
        canvas.command_manager.undo()
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (before.x(), before.y())
        )

    def test_aligning_a_group_and_its_bed_carries_external_plants_by_the_beds_net_delta(
        self, canvas: CanvasView
    ) -> None:
        """A non-grouped plant follows the BED, not the group carrying it (#1021 review).

        The bed is listed with a delta that cancels the group's, so the bed
        stays put; a plant linked to it but outside the group must stay too.
        """
        from open_garden_planner.core.commands import AlignItemsCommand, GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        inside = _plant(canvas, 450.0, 350.0)
        outside = _plant(canvas, 500.0, 380.0)
        assert outside.parent_bed_id == bed.item_id
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, inside]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before_outside = QPointF(outside.scenePos())

        canvas.command_manager.execute(AlignItemsCommand([
            (group, QPointF(100.0, 0.0)),
            (bed, QPointF(0.0, 0.0)),
        ], delta_frame="scene"))

        assert (outside.scenePos().x(), outside.scenePos().y()) == pytest.approx(
            (before_outside.x(), before_outside.y())
        )

    def test_a_live_drag_of_a_group_and_its_bed_keeps_external_plants_in_step(
        self, canvas: CanvasView
    ) -> None:
        """The live propagation uses the bed's NET delta, not whichever came first.

        Both the group and the bed inside it are dragged (the stale-selection
        case). A plant linked to the bed but outside the group must follow the
        bed's total scene movement - 100 from the group plus 20 of its own -
        during the drag and in the one undo step (#1021 review).
        """
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        inside = _plant(canvas, 450.0, 350.0)
        outside = _plant(canvas, 500.0, 380.0)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, inside]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before_outside = QPointF(outside.scenePos())
        canvas._drag_start_positions = {
            group: QPointF(group.pos()), bed: QPointF(bed.pos()),
        }
        canvas._child_drag_origins.clear()

        group.moveBy(100.0, 0.0)
        canvas._propagate_bed_children_during_drag()
        bed.moveBy(20.0, 0.0)
        canvas._propagate_bed_children_during_drag()

        assert outside.scenePos().x() == pytest.approx(before_outside.x() + 120.0)
        assert outside.scenePos().y() == pytest.approx(before_outside.y())

        canvas._drag_start_undo_depth = canvas.command_manager.undo_depth
        canvas._finalize_drag_move()

        assert outside.scenePos().x() == pytest.approx(before_outside.x() + 120.0)
        canvas.command_manager.undo()
        assert outside.scenePos().x() == pytest.approx(before_outside.x())

    @pytest.mark.parametrize(
        ("frame", "group_delta", "bed_delta", "expected"),
        [("scene", 100.0, 0.0, 0.0), ("local", 100.0, 20.0, 120.0)],
    )
    def test_a_bound_reference_point_follows_its_bed_not_the_group(
        self, canvas: CanvasView, frame: str, group_delta: float,
        bed_delta: float, expected: float,
    ) -> None:
        """A point bound to a listed bed takes the bed's NET delta (#1021 review)."""
        from open_garden_planner.core.commands import AlignItemsCommand, GroupCommand
        from open_garden_planner.core.reference_points import build_metadata
        from open_garden_planner.ui.canvas.items import ReferencePointItem
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        bed = _bed(canvas)
        inside = _plant(canvas, 450.0, 350.0)
        point = ReferencePointItem(
            500.0, 400.0, 3.0, metadata=build_metadata(parent=bed.item_id),
        )
        canvas.scene().addItem(point)
        canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, inside]))
        group = next(item for item in canvas.scene().items()
                     if isinstance(item, GroupItem))
        before = QPointF(point.scenePos())

        canvas.command_manager.execute(AlignItemsCommand([
            (group, QPointF(group_delta, 0.0)),
            (bed, QPointF(bed_delta, 0.0)),
        ], delta_frame=frame))

        assert point.scenePos().x() == pytest.approx(before.x() + expected)
        assert point.scenePos().y() == pytest.approx(before.y())
        canvas.command_manager.undo()
        assert point.scenePos().x() == pytest.approx(before.x())

    def test_a_bed_moved_over_a_plant_links_it(self, canvas: CanvasView) -> None:
        bed = _bed(canvas)
        loner = _plant(canvas, 1000.0, 400.0)
        assert loner.parent_bed_id is None
        # The bed lands around the plant; the plant did not move.
        canvas.command_manager.execute(MoveItemsCommand([bed], QPointF(500.0, 0.0)))
        assert loner.parent_bed_id == bed.item_id
        assert loner.item_id in bed.child_item_ids
        canvas.command_manager.undo()
        assert loner.parent_bed_id is None
        assert loner.item_id not in bed.child_item_ids

    @pytest.mark.parametrize("fixed_child", [False, True])
    def test_moving_a_bed_carries_its_plants_and_keeps_the_link(
        self, canvas: CanvasView, fixed_child: bool
    ) -> None:
        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        before = QPointF(plant.pos())
        if fixed_child:
            from open_garden_planner.core.constraints import AnchorRef, ConstraintType
            from open_garden_planner.core.measure_snapper import AnchorType

            ref = AnchorRef(plant.item_id, AnchorType.CENTER)
            canvas._canvas_scene.constraint_graph.add_constraint(
                ref, ref, 0.0, constraint_type=ConstraintType.FIXED,
                target_x=before.x(), target_y=before.y(),
            )
        canvas.command_manager.execute(MoveItemsCommand([bed], QPointF(700.0, 100.0)))
        if fixed_child:
            assert plant.pos() == before
            assert plant.parent_bed_id is None
            canvas.command_manager.undo()
            assert plant.pos() == before
            assert plant.parent_bed_id == bed.item_id
            canvas.command_manager.redo()
            assert plant.pos() == before
            assert plant.parent_bed_id is None
            return
        assert plant.parent_bed_id == bed.item_id
        assert plant.pos().x() == pytest.approx(before.x() + 700.0)
        assert plant.pos().y() == pytest.approx(before.y() + 100.0)
        assert _base(canvas, plant) == 38.0
        canvas.command_manager.undo()
        assert plant.pos().x() == pytest.approx(before.x())
        assert plant.pos().y() == pytest.approx(before.y())
        assert plant.parent_bed_id == bed.item_id


class TestCopiesAndExplicitLinks:
    """(v) one rule for copies; an explicit link is never silently overruled."""

    def test_an_array_copy_is_linked_by_where_it_lands(self, canvas: CanvasView) -> None:
        """A copy built from a serialised plant carries its SOURCE's link; the
        create path drops it and re-decides from where the copy stands."""
        bed = _bed(canvas)
        _plant(canvas, 500.0, 400.0)  # the source, linked
        scene = canvas.scene()
        layer = scene.active_layer.id

        inside = CircleItem(600.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        outside = CircleItem(1000.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        for copy in (inside, outside):
            # What serialisation + deserialisation restores: the SOURCE's link.
            copy.parent_bed_id = bed.item_id
        assert not ({inside.item_id, outside.item_id} & set(bed.child_item_ids)), (
            "the stale links were never added to the bed's child list"
        )

        from open_garden_planner.core.commands import CreateItemsCommand

        canvas.command_manager.execute(CreateItemsCommand(scene, [outside, inside], "copies"))
        assert inside.parent_bed_id == bed.item_id
        assert outside.parent_bed_id is None
        assert inside.item_id in bed.child_item_ids
        assert outside.item_id not in bed.child_item_ids

    def test_an_explicit_link_to_another_bed_is_not_overruled_by_a_bed_edit(
        self, canvas: CanvasView
    ) -> None:
        """A bed edit only re-decides the plants that bed can affect (#443 review).

        The plant is explicitly linked to a far-away bed; creating another bed
        elsewhere must leave that link alone (ADR-037 addendum decision 5).
        """
        _bed(canvas)  # the bed the plant physically stands in
        far_bed = _bed(canvas, x=1500.0, y=1200.0)
        plant = _plant(canvas, 500.0, 400.0)
        canvas.command_manager.execute(
            SetParentBedCommand(
                canvas.scene(), plant, plant.parent_bed_id, far_bed.item_id
            )
        )
        assert plant.parent_bed_id == far_bed.item_id

        _bed(canvas, x=2500.0, y=1500.0)  # unrelated, nowhere near the plant

        assert plant.parent_bed_id == far_bed.item_id
        assert plant.item_id in far_bed.child_item_ids

    def test_an_explicit_link_survives_until_the_plant_moves(
        self, canvas: CanvasView
    ) -> None:
        """The panel/agent Link action may link a plant that is not in the bed
        (``link_is_geometric: false``) — that is a user decision, not a stale link.
        It is re-evaluated by the plant's next move, like every other path."""
        bed = _bed(canvas)
        loner = _plant(canvas, 1500.0, 1200.0)
        canvas.command_manager.execute(
            SetParentBedCommand(canvas.scene(), loner, None, bed.item_id)
        )
        assert loner.parent_bed_id == bed.item_id
        assert bed_membership_point(loner) != bed.mapToScene(bed.rect().center())
        assert loner.item_id in bed.child_item_ids
        # … and the plant stands on the ground: the link alone never lifts.
        assert _base(canvas, loner) == 0.0

        canvas.command_manager.execute(MoveItemsCommand([loner], QPointF(1.0, 0.0)))
        assert loner.parent_bed_id is None
        assert loner.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        assert loner.parent_bed_id == bed.item_id

    def test_a_mirror_move_out_of_a_bed_undoes_its_child_link(
        self, canvas: CanvasView, mouse_event: object
    ) -> None:
        """Mirror-Move reuses the plant's id; undo must restore the bed's link."""
        from open_garden_planner.core.tools import ToolType

        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        plant_id = plant.item_id
        assert plant.item_id in bed.child_item_ids

        canvas.set_active_tool(ToolType.MIRROR)
        tool = canvas.tool_manager.active_tool
        tool._copy_mode = False  # a Move: the original id survives on the replacement
        plant.setSelected(True)
        tool.mouse_press(mouse_event, QPointF(350.0, 100.0))
        tool.mouse_press(mouse_event, QPointF(350.0, 700.0))

        moved = canvas.scene().find_item_by_id(plant_id)
        assert moved is not None
        point = standing_point(moved)
        assert point is not None and point.x() == pytest.approx(200.0, abs=1.0)
        assert moved.parent_bed_id is None
        assert plant_id not in bed.child_item_ids

        canvas.command_manager.undo()
        restored = canvas.scene().find_item_by_id(plant_id)
        assert restored is not None
        assert restored.parent_bed_id == bed.item_id
        assert plant_id in bed.child_item_ids

        # Redo: the replacement is outside again, and the bed must NOT still
        # claim it (the round-1 undo healed the child id; a redo that only
        # unlinks the item would leave a stale id behind).
        canvas.command_manager.redo()
        moved_again = canvas.scene().find_item_by_id(plant_id)
        assert moved_again is not None
        assert moved_again.parent_bed_id is None
        assert plant_id not in bed.child_item_ids

    def test_the_link_point_is_the_standing_point_for_every_shape(
        self, canvas: CanvasView
    ) -> None:
        """(iii) the one point, on a badged plant and a turned bed."""
        bed = _bed(canvas)
        plant = _plant(canvas, 690.0, 400.0)  # 10 cm inside the east edge
        plant.set_antagonist_warning(True)
        standing = standing_point(plant)
        link = bed_membership_point(plant)
        assert standing is not None
        assert (link.x(), link.y()) == (standing.x(), standing.y())
        assert plant.parent_bed_id == bed.item_id
        assert _base(canvas, plant) == 38.0


class TestNoDanglingChildLists:
    """(v) whatever sets a link keeps the parent's child list in step."""

    def test_undoing_a_created_bed_removes_it_from_the_child_list(
        self, canvas: CanvasView
    ) -> None:
        plant = _plant(canvas, 500.0, 400.0)
        assert plant.parent_bed_id is None
        bed = _bed(canvas)  # drawn around the plant: #443 links it
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

        canvas.command_manager.undo()  # remove the bed
        assert plant.scene() is not None
        assert plant.parent_bed_id is None
        canvas.command_manager.redo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids


class TestTheReconciledPlanRoundTrips:
    """The completed geometry saves and reloads with unchanged `.ogp` format."""

    def test_save_and_reload_keeps_the_reconciled_links(
        self, canvas: CanvasView, tmp_path
    ) -> None:
        from open_garden_planner.core import ProjectManager
        from open_garden_planner.core.project import FILE_VERSION

        bed = _bed(canvas)
        inside = _plant(canvas, 500.0, 400.0)
        outside = _plant(canvas, 1200.0, 900.0)
        assert inside.parent_bed_id == bed.item_id
        assert outside.parent_bed_id is None
        bed_id, inside_id = bed.item_id, inside.item_id

        path = tmp_path / "reconciled.ogp"
        manager = ProjectManager()
        manager.save(canvas.scene(), path)

        canvas.scene().clear()
        manager.load(canvas.scene(), path)

        loaded_bed = canvas.scene().find_item_by_id(bed_id)
        loaded_inside = canvas.scene().find_item_by_id(inside_id)
        assert loaded_bed is not None and loaded_inside is not None
        assert loaded_inside.parent_bed_id == bed_id  # type: ignore[attr-defined]
        assert inside_id in loaded_bed.child_item_ids  # type: ignore[attr-defined]
        assert FILE_VERSION == "1.4"  # additive key only: no format bump


@pytest.fixture
def window(qtbot: object, monkeypatch: object, _reset_app_settings: object) -> object:
    """The real application window: the panel's and the agent's own edit paths."""
    from PyQt6.QtWidgets import QMessageBox

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings

    get_settings().show_welcome_on_startup = False
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    win = GardenPlannerApp()
    qtbot.addWidget(win)  # type: ignore[attr-defined]
    yield win
    win._stop_agent_api()


class TestThenTheFixHoldsEverywhere:
    """Paths the review round found: copies, EQUAL partners, combined moves, solver, click."""

    def test_a_mirror_copy_does_not_inherit_a_non_geometric_link(
        self, canvas: CanvasView, mouse_event: object
    ) -> None:
        """Copying a bed and an explicitly linked plant outside it: one-sided link."""
        from open_garden_planner.core.tools import ToolType
        from open_garden_planner.ui.canvas.items import CircleItem as _Circle

        bed = _bed(canvas)
        plant = _plant(canvas, 1000.0, 900.0)  # outside the bed
        canvas.command_manager.execute(
            SetParentBedCommand(canvas.scene(), plant, None, bed.item_id)
        )
        assert plant.parent_bed_id == bed.item_id
        before_beds = {id(i) for i in canvas.scene().items() if isinstance(i, RectangleItem)}
        before_plants = {id(i) for i in canvas.scene().items() if isinstance(i, _Circle)}

        bed.setSelected(True)
        plant.setSelected(True)
        canvas.set_active_tool(ToolType.MIRROR)
        tool = canvas.tool_manager.active_tool
        tool._copy_mode = True
        tool.mouse_press(mouse_event, QPointF(350.0, 100.0))
        tool.mouse_press(mouse_event, QPointF(350.0, 700.0))

        new_beds = [
            i for i in canvas.scene().items()
            if isinstance(i, RectangleItem) and id(i) not in before_beds
        ]
        new_plants = [
            i for i in canvas.scene().items()
            if isinstance(i, _Circle) and id(i) not in before_plants
        ]
        assert len(new_beds) == 1 and len(new_plants) == 1
        copy_bed, copy_plant = new_beds[0], new_plants[0]
        assert copy_plant.parent_bed_id is None
        assert copy_plant.item_id not in copy_bed.child_item_ids

    def test_an_equal_partner_bed_resize_unlinks_its_plant(
        self, canvas: CanvasView
    ) -> None:
        """EQUAL resizes a partner bed in the SAME command — its plants follow."""
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_rect_resize,
        )

        bed_a = _bed(canvas)
        bed_b = RectangleItem(
            1000.0, 300.0, 300.0, 200.0,
            object_type=ObjectType.RAISED_BED,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), bed_b, "bed"))
        plant = _plant(canvas, 1120.0, 400.0)
        assert plant.parent_bed_id == bed_b.item_id

        def apply_size(item: object, size: float) -> None:
            _old, new = build_rect_resize(item, size, 200.0, keep_center=True)
            apply_rect_like_geometry(item, new)

        old_a, new_a = build_rect_resize(bed_a, 100.0, 100.0, keep_center=True)
        canvas.command_manager.execute(
            ResizeItemCommand(
                bed_a,
                old_a,
                new_a,
                apply_rect_like_geometry,
                partner_resizes=[(bed_b, 300.0, 40.0, apply_size)],
            )
        )

        assert bed_b.rect().width() == pytest.approx(40.0)
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed_b.child_item_ids
        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed_b.item_id
        assert plant.item_id in bed_b.child_item_ids

    def test_moving_a_plant_with_an_unrelated_bed_still_redecides_it(
        self, canvas: CanvasView
    ) -> None:
        """A moved plant is re-decided even when an unrelated bed moves too."""
        bed = _bed(canvas)
        far_bed = _bed(canvas, x=1500.0, y=1200.0)
        other_bed = _bed(canvas, x=2500.0, y=1500.0)
        plant = _plant(canvas, 500.0, 400.0)
        canvas.command_manager.execute(
            SetParentBedCommand(canvas.scene(), plant, bed.item_id, far_bed.item_id)
        )
        assert plant.parent_bed_id == far_bed.item_id

        # The plant leaves the bed it stands in; the bed it shares the move with
        # is unrelated (the far bed it is linked to does not move).
        canvas.command_manager.execute(
            MoveItemsCommand([plant, other_bed], QPointF(3000.0, 0.0))
        )

        assert plant.parent_bed_id is None
        assert plant.item_id not in far_bed.child_item_ids
        canvas.command_manager.undo()
        assert plant.parent_bed_id == far_bed.item_id

    @pytest.mark.parametrize("fixed_child", [False, True])
    def test_a_constraint_that_moves_a_bed_carries_its_plant(
        self, canvas: CanvasView, fixed_child: bool
    ) -> None:
        """The REAL constraint-tool path carries a moved bed's plants.

        `_execute_constraint_with_solve` builds the command with an empty
        payload, trial-executes, undoes, injects the solver moves and executes
        again. A tracker built in the constructor missed all of that.
        """
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef, ConstraintType
        from open_garden_planner.core.measure_snapper import AnchorType

        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        other = RectangleItem(
            1200.0, 300.0, 100.0, 100.0,
            object_type=ObjectType.GENERIC_RECTANGLE,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), other, "other"))
        plant_before = QPointF(plant.pos())
        bed_before = QPointF(bed.pos())
        undo_before = canvas.command_manager.undo_depth
        graph = canvas._canvas_scene.constraint_graph
        if fixed_child:
            ref = AnchorRef(plant.item_id, AnchorType.CENTER)
            graph.add_constraint(
                ref, ref, 0.0, constraint_type=ConstraintType.FIXED,
                target_x=plant_before.x(), target_y=plant_before.y(),
            )
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(bed.item_id, AnchorType.CORNER, 0),
                AnchorRef(other.item_id, AnchorType.CORNER, 0),
                500.0,  # 300 cm shorter than the drawn distance
                constraint_type=ConstraintType.DISTANCE,
            )
        )

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert bed.pos().x() == pytest.approx(bed_before.x() + 300.0, abs=1.0)
        expected_x = plant_before.x() if fixed_child else plant_before.x() + 300.0
        assert plant.pos().x() == pytest.approx(expected_x, abs=1.0)
        assert plant.parent_bed_id == (None if fixed_child else bed.item_id)
        assert (plant.item_id in bed.child_item_ids) is not fixed_child

        canvas.command_manager.undo()
        assert bed.pos().x() == pytest.approx(bed_before.x())
        assert plant.pos().x() == pytest.approx(plant_before.x())
        assert plant.parent_bed_id == bed.item_id

    def test_a_rotation_only_constraint_payload_redecides_membership(
        self, canvas: CanvasView
    ) -> None:
        """EQUAL/EDGE_LENGTH inject `_item_rotations` after construction."""
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef
        from open_garden_planner.core.measure_snapper import AnchorType
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation

        bed = RectangleItem(
            400.0, 300.0, 600.0, 100.0,
            object_type=ObjectType.RAISED_BED,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), bed, "bed"))
        plant = _plant(canvas, 950.0, 350.0)  # near the east end
        assert plant.parent_bed_id == bed.item_id
        other = RectangleItem(
            1200.0, 1200.0, 100.0, 100.0,
            object_type=ObjectType.GENERIC_RECTANGLE,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), other, "other"))
        graph = canvas._canvas_scene.constraint_graph

        command = AddConstraintCommand(
            graph,
            AnchorRef(bed.item_id, AnchorType.CENTER),
            AnchorRef(other.item_id, AnchorType.CENTER),
            100.0,
            item_rotations=[(bed, 0.0, 90.0, apply_rotation)],
        )
        canvas.command_manager.execute(command)

        assert bed.rotation() == pytest.approx(90.0)
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        assert bed.rotation() == pytest.approx(0.0)
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

    def test_a_vertex_only_constraint_payload_redecides_membership(
        self, canvas: CanvasView
    ) -> None:
        """EDGE_LENGTH injects `_vertex_moves` only — the bed's plants follow."""
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef
        from open_garden_planner.core.measure_snapper import AnchorType

        scene = canvas.scene()
        bed = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 200.0), QPointF(0.0, 200.0)],
            object_type=ObjectType.RAISED_BED,
            layer_id=scene.active_layer.id,
        )
        bed.setPos(400.0, 300.0)
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        plant = _plant(canvas, 690.0, 310.0)  # near the east edge
        assert plant.parent_bed_id == bed.item_id
        other = RectangleItem(
            1200.0, 1200.0, 100.0, 100.0,
            object_type=ObjectType.GENERIC_RECTANGLE,
            layer_id=scene.active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(scene, other, "other"))
        graph = scene.constraint_graph

        command = AddConstraintCommand(
            graph,
            AnchorRef(bed.item_id, AnchorType.CENTER),
            AnchorRef(other.item_id, AnchorType.CENTER),
            100.0,
        )
        command._vertex_moves = [
            (bed, 1, QPointF(300.0, 0.0), QPointF(180.0, 0.0)),
            (bed, 2, QPointF(300.0, 200.0), QPointF(180.0, 200.0)),
        ]
        canvas.command_manager.execute(command)

        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

    def test_an_edited_distance_with_a_vertex_move_redecides_membership(
        self, canvas: CanvasView
    ) -> None:
        """The panel injects `_vertex_moves` into EditConstraintDistanceCommand."""
        from open_garden_planner.core.commands import EditConstraintDistanceCommand
        from open_garden_planner.core.constraints import AnchorRef
        from open_garden_planner.core.measure_snapper import AnchorType

        scene = canvas.scene()
        bed = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 200.0), QPointF(0.0, 200.0)],
            object_type=ObjectType.RAISED_BED,
            layer_id=scene.active_layer.id,
        )
        bed.setPos(400.0, 300.0)
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        plant = _plant(canvas, 690.0, 310.0)
        assert plant.parent_bed_id == bed.item_id
        other = RectangleItem(
            1200.0, 1200.0, 100.0, 100.0,
            object_type=ObjectType.GENERIC_RECTANGLE,
            layer_id=scene.active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(scene, other, "other"))
        graph = scene.constraint_graph
        constraint = graph.add_constraint(
            AnchorRef(bed.item_id, AnchorType.CENTER),
            AnchorRef(other.item_id, AnchorType.CENTER),
            100.0,
        )

        command = EditConstraintDistanceCommand(
            graph, constraint.constraint_id, 100.0, 120.0
        )
        command._vertex_moves = [
            (bed, 1, QPointF(300.0, 0.0), QPointF(180.0, 0.0)),
            (bed, 2, QPointF(300.0, 200.0), QPointF(180.0, 200.0)),
        ]
        canvas.command_manager.execute(command)

        assert plant.parent_bed_id is None
        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id

    def test_a_child_the_solver_also_moved_is_not_moved_twice(
        self, canvas: CanvasView
    ) -> None:
        """A child in the solver's own move set must not also get the bed's delta."""
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef
        from open_garden_planner.core.measure_snapper import AnchorType

        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        other = RectangleItem(
            1200.0, 300.0, 100.0, 100.0,
            object_type=ObjectType.GENERIC_RECTANGLE,
            layer_id=canvas.scene().active_layer.id,
        )
        canvas.command_manager.execute(CreateItemCommand(canvas.scene(), other, "other"))
        bed_before = QPointF(bed.pos())
        plant_before = QPointF(plant.pos())
        graph = canvas._canvas_scene.constraint_graph
        command = AddConstraintCommand(
            graph,
            AnchorRef(bed.item_id, AnchorType.CENTER),
            AnchorRef(other.item_id, AnchorType.CENTER),
            100.0,
            item_moves=[
                (bed, bed_before, bed_before + QPointF(100.0, 0.0)),
                (plant, plant_before, plant_before + QPointF(500.0, 0.0)),
            ],
        )
        canvas.command_manager.execute(command)

        assert plant.pos().x() == pytest.approx(plant_before.x() + 500.0)
        # It also left the bed by its own move, so the link is re-decided.
        assert plant.parent_bed_id is None

    def test_a_click_does_not_overrule_an_explicit_link(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A press/release without movement is not a geometry edit (#443 review)."""
        from PyQt6.QtTest import QTest

        bed = _bed(canvas)
        far_bed = _bed(canvas, x=1500.0, y=1200.0)
        plant = _plant(canvas, 500.0, 400.0)
        canvas.command_manager.execute(
            SetParentBedCommand(canvas.scene(), plant, bed.item_id, far_bed.item_id)
        )
        assert plant.parent_bed_id == far_bed.item_id

        canvas.resize(1000, 800)
        canvas.show()
        qtbot.waitExposed(canvas)  # type: ignore[attr-defined]
        point = standing_point(plant)
        assert point is not None
        canvas.centerOn(point)
        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(point),
        )

        assert plant.parent_bed_id == far_bed.item_id
        assert plant.item_id in far_bed.child_item_ids


class TestTheRealEditSurfaces:
    """The panel and the agent apply the same rule, in one undo entry each."""

    def test_a_panel_resize_reconciles_and_redo_keeps_the_truth(
        self, window: object
    ) -> None:
        """The typed width/height path: live geometry, then the command — #443 (i).

        Before the fix it registered a resize whose undo restored links that had
        never been changed, and whose redo then unlinked the plant: undo/redo
        asymmetry in the exact path the issue names.
        """
        from PyQt6.QtWidgets import QDoubleSpinBox

        canvas = window.canvas_view  # type: ignore[attr-defined]
        bed = _bed(canvas)
        plant = _plant(canvas, 500.0, 400.0)
        assert plant.parent_bed_id == bed.item_id
        panel = window.properties_panel  # type: ignore[attr-defined]
        width = QDoubleSpinBox()
        width.setValue(60.0)
        height = QDoubleSpinBox()
        height.setValue(200.0)
        undo_before = canvas.command_manager.undo_depth

        panel._on_dimension_changed(
            bed, "rect_size", width_spin=width, height_spin=height
        )

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids

        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        canvas.command_manager.redo()
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids

    def test_an_agent_vertex_write_relinks_a_bed_in_one_step(
        self, window: object
    ) -> None:
        """Agent set_vertex reshapes a bed with no drag-release handler — #443 (i)."""
        canvas = window.canvas_view  # type: ignore[attr-defined]
        scene = window.canvas_scene  # type: ignore[attr-defined]
        bed = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 200.0), QPointF(0.0, 200.0)],
            object_type=ObjectType.RAISED_BED,
            layer_id=scene.active_layer.id,
        )
        bed.setPos(400.0, 300.0)
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        plant = _plant(canvas, 690.0, 310.0)  # 10 cm inside the east edge
        assert plant.parent_bed_id == bed.item_id
        undo_before = canvas.command_manager.undo_depth

        # Move the top-right corner down-left, leaving the plant outside the outline.
        window._do_agent_set_vertex(str(bed.item_id), 1, 600.0, 400.0)  # type: ignore[attr-defined]

        assert canvas.command_manager.undo_depth == undo_before + 1
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        canvas.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids


@pytest.mark.parametrize("path", ["nudge", "drag", "agent"])
@pytest.mark.parametrize("child_constraint", ["fixed", "distance"])
def test_implicit_bed_move_preserves_constrained_child(
    window: object, path: str, child_constraint: str,
) -> None:
    """Real entry paths must not pre-expand a constrained child as an explicit move."""
    from PyQt6.QtGui import QKeyEvent

    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType

    canvas = window.canvas_view
    bed = _bed(canvas)
    plant = _plant(canvas, 500.0, 400.0)
    plant_before = QPointF(plant.pos())
    bed_before = QPointF(bed.pos())
    ref = AnchorRef(plant.item_id, AnchorType.CENTER)
    graph = canvas._canvas_scene.constraint_graph
    if child_constraint == "fixed":
        graph.add_constraint(
            ref, ref, 0.0, constraint_type=ConstraintType.FIXED,
            target_x=plant_before.x(), target_y=plant_before.y(),
        )
    else:
        other = RectangleItem(1200.0, 350.0, 100.0, 100.0)
        canvas.scene().addItem(other)
        graph.add_constraint(
            ref, AnchorRef(other.item_id, AnchorType.CENTER), 750.0,
            constraint_type=ConstraintType.DISTANCE,
        )
    depth_before = canvas.command_manager.undo_depth
    if path == "nudge":
        bed.setSelected(True)
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        canvas._move_selected_items(event)
    elif path == "agent":
        with pytest.raises(ValueError, match="constraint"):
            window._agent_move_object(str(bed.item_id), 700.0, 0.0)
        assert plant.pos() == plant_before
        assert bed.pos() == bed_before
        assert plant.parent_bed_id == bed.item_id
        assert canvas.command_manager.undo_depth == depth_before
        assert canvas.command_manager.redo_depth == 0
        return
    else:
        canvas._drag_start_positions = {bed: QPointF(bed.pos())}
        bed.moveBy(700.0, 0.0)
        canvas._propagate_bed_children_during_drag()
        assert plant.pos() == plant_before
        canvas._finalize_drag_move()
    assert plant.pos() == plant_before
    assert bed.pos() != bed_before
    assert canvas.command_manager.undo_depth == depth_before + 1
    after = QPointF(bed.pos())
    canvas.command_manager.undo()
    assert bed.pos() == bed_before
    assert plant.pos() == plant_before
    assert plant.parent_bed_id == bed.item_id
    canvas.command_manager.redo()
    assert bed.pos() == after
    assert plant.pos() == plant_before


def test_the_arrow_constraint_path_keeps_a_group_child_s_local_delta(
    canvas: CanvasView, monkeypatch
) -> None:
    """A constrained correction is parent-local; the nudge command must say so."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items.group_item import GroupItem

    bed = _bed(canvas)
    plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(2)]
    canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, *plants]))
    group = next(item for item in canvas.scene().items()
                 if isinstance(item, GroupItem))
    before_group = QPointF(group.scenePos())
    before_plant = QPointF(plants[0].scenePos())

    # The nudge path only enters its constraint branch when the graph has a
    # constraint; the solver itself is replaced by the local correction this
    # test needs (a real solver-driven frame would be another scenario).
    ref = AnchorRef(plants[0].item_id, AnchorType.CENTER)
    canvas._canvas_scene.constraint_graph.add_constraint(
        ref, ref, 0.0, constraint_type=ConstraintType.FIXED,
        target_x=plants[0].pos().x(), target_y=plants[0].pos().y(),
    )
    monkeypatch.setattr(
        canvas, "_compute_constraint_propagation",
        lambda _items, _delta: [(plants[0], QPointF(20.0, 0.0))],
    )
    canvas.scene().clearSelection()
    group.setSelected(True)
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier
    )
    canvas._move_selected_items(event)

    assert (group.scenePos().x(), group.scenePos().y()) == pytest.approx(
        (before_group.x() + 50.0, before_group.y())
    )
    assert (plants[0].scenePos().x(), plants[0].scenePos().y()) == pytest.approx(
        (before_plant.x() + 70.0, before_plant.y())
    )


def test_a_mouse_drag_of_a_group_with_its_bed_moves_and_undoes_once(
    qtbot: object, canvas: CanvasView
) -> None:
    """The live drag expansion must not add a second delta to a carried plant."""
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.ui.canvas.items.group_item import GroupItem

    bed = _bed(canvas)
    plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(2)]
    canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, *plants]))
    group = next(item for item in canvas.scene().items()
                 if isinstance(item, GroupItem))
    canvas.scene().clearSelection()
    group.setSelected(True)
    before_bed = QPointF(bed.scenePos())
    before_plants = [QPointF(plant.scenePos()) for plant in plants]
    canvas.set_zoom(1.0)
    canvas.resize(1000, 800)
    canvas.show()
    qtbot.waitExposed(canvas)  # type: ignore[attr-defined]
    canvas.centerOn(550, 400)
    viewport = canvas.viewport()
    start = bed.mapToScene(bed.rect().center())
    finish = start + QPointF(100.0, 0.0)

    qtbot.mousePress(  # type: ignore[attr-defined]
        viewport, Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(start)
    )
    qtbot.mouseMove(viewport, canvas.mapFromScene(finish))  # type: ignore[attr-defined]
    qtbot.mouseRelease(  # type: ignore[attr-defined]
        viewport, Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(finish)
    )

    assert (bed.scenePos().x(), bed.scenePos().y()) == pytest.approx(
        (before_bed.x() + 100.0, before_bed.y())
    )
    for plant, start_pos in zip(plants, before_plants, strict=True):
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (start_pos.x() + 100.0, start_pos.y())
        )
    canvas.command_manager.undo()
    assert (bed.scenePos().x(), bed.scenePos().y()) == pytest.approx(
        (before_bed.x(), before_bed.y())
    )
    for plant, start_pos in zip(plants, before_plants, strict=True):
        assert (plant.scenePos().x(), plant.scenePos().y()) == pytest.approx(
            (start_pos.x(), start_pos.y())
        )


def test_live_bed_propagation_skips_a_plant_the_group_carries(
    canvas: CanvasView,
) -> None:
    """The live drag expansion must not setPos a plant the group already carries."""
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.ui.canvas.items.group_item import GroupItem

    bed = _bed(canvas)
    plants = [_plant(canvas, 450.0 + 50.0 * i, 350.0) for i in range(2)]
    canvas.command_manager.execute(GroupCommand(canvas.scene(), [bed, *plants]))
    group = next(item for item in canvas.scene().items()
                 if isinstance(item, GroupItem))
    before = [QPointF(plant.pos()) for plant in plants]

    canvas._drag_start_positions = {group: QPointF(group.pos())}
    canvas._drag_start_undo_depth = canvas.command_manager.undo_depth
    group.moveBy(100.0, 0.0)
    canvas._propagate_bed_children_during_drag()

    for plant, start_pos in zip(plants, before, strict=True):
        assert plant.pos() == start_pos

    canvas._finalize_drag_move()
    for plant, start_pos in zip(plants, before, strict=True):
        assert plant.pos() == start_pos
    canvas.command_manager.undo()
    for plant, start_pos in zip(plants, before, strict=True):
        assert plant.pos() == start_pos
