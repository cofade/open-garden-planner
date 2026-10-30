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
