"""A plant dragged into a bed is ONE undoable step: the move and its link (#627).

The owner's manual pass: dropping a plant into a bed linked it, and the first
Ctrl+Z undid only the link - the second the move. The drag's move and the link
commands it decides now run as one ``CompoundCommand``.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _bed_ring(bed: RectangleItem, at: QPointF) -> list[tuple[float, float]]:
    """The bed's footprint in scene coordinates when its position was ``at``."""
    rect = bed.rect()
    return [(at.x() + rect.left(), at.y() + rect.top()),
            (at.x() + rect.right(), at.y() + rect.bottom())]


def test_dragging_a_plant_into_a_bed_undoes_as_one_step(qtbot) -> None:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    bed = RectangleItem(x=200, y=200, width=400, height=400,
                        object_type=ObjectType.GARDEN_BED)
    scene.addItem(bed)
    plant = CircleItem(center_x=900, center_y=400, radius=20, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
    scene.addItem(plant)
    view.show()
    qtbot.waitExposed(view)
    view.centerOn(bed.mapToScene(bed.rect().center()))

    start_pos = QPointF(plant.pos())
    assert plant.parent_bed_id is None
    start = view.mapFromScene(plant.mapToScene(plant.boundingRect().center()))
    target = view.mapFromScene(bed.mapToScene(bed.rect().center()))
    before = len(view.command_manager._undo_stack)

    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), target)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, target)

    assert plant.parent_bed_id == bed.item_id, "the drop linked the plant"
    assert plant.pos() != start_pos
    assert len(view.command_manager._undo_stack) == before + 1, "one step, not two"

    view.command_manager.undo()
    assert plant.parent_bed_id is None, "the undo took the link back"
    assert plant.pos() == start_pos, "... and the move with it"

    view.command_manager.redo()
    assert plant.parent_bed_id == bed.item_id and plant.pos() != start_pos


def test_a_bed_dragged_with_its_linked_plant_keeps_the_link(qtbot) -> None:
    """The link is asked where the drag LEFT everything, not where it started.

    A first version predicted the membership point as "pre-drag point + delta",
    against beds still at their pre-drag positions - so dragging a bed and its
    plant together unlinked the plant. The bed's own move is part of the gesture.
    """
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    bed = RectangleItem(x=200, y=200, width=400, height=400,
                        object_type=ObjectType.GARDEN_BED)
    scene.addItem(bed)
    plant = CircleItem(center_x=400, center_y=400, radius=20, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    view.show()
    qtbot.waitExposed(view)
    view.centerOn(bed.mapToScene(bed.rect().center()))

    bed_start, plant_start = QPointF(bed.pos()), QPointF(plant.pos())
    bed.setSelected(True)
    plant.setSelected(True)
    before = len(view.command_manager._undo_stack)
    start = view.mapFromScene(plant.mapToScene(plant.boundingRect().center()))
    # 400 px at zoom 1.0 = 400 cm: the plant (scene x 400) must leave the bed's OLD
    # footprint (x 200..600). 90 px kept it inside, and then the predictive rule the
    # fix replaced gives the right answer by coincidence - the pin has to fail there.
    target = start + QPoint(400, 0)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), target)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, target)

    assert bed.pos() != bed_start and plant.pos() != plant_start
    new_centre = plant.mapToScene(plant.boundingRect().center())
    old_left = min(x for x, _y in _bed_ring(bed, bed_start))
    assert new_centre.x() > old_left + bed.rect().width(), (
        "the plant must be past the bed's OLD right edge, or this test proves nothing")
    assert plant.parent_bed_id == bed.item_id, "the plant travelled with its bed"
    assert len(view.command_manager._undo_stack) == before + 1
    view.command_manager.undo()
    assert bed.pos() == bed_start and plant.pos() == plant_start
    assert plant.parent_bed_id == bed.item_id


def test_a_bed_dragged_alone_carries_its_plant_and_undo_restores_both(qtbot) -> None:
    """A CHILD plant follows its bed with no lag, and one undo puts both back.

    The child's origin was recorded as `child.pos() - delta` on its first sighting,
    when it had not moved yet. A two-step drag then left the plant behind by the
    first frame's movement, and undo overshot it by the same amount (measured: the
    bed at 600, the plant at 300, undo -> -300). The origin is the child's own
    position; the bed's cumulative delta is then the whole story.
    """
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    bed = RectangleItem(x=200, y=200, width=400, height=400,
                        object_type=ObjectType.GARDEN_BED)
    scene.addItem(bed)
    plant = CircleItem(center_x=450, center_y=450, radius=20, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    view.show()
    qtbot.waitExposed(view)
    view.centerOn(bed.mapToScene(bed.rect().center()))

    bed_start, plant_start = QPointF(bed.pos()), QPointF(plant.pos())
    bed.setSelected(True)   # the bed alone: the plant follows as its child
    before = len(view.command_manager._undo_stack)
    press = view.mapFromScene(bed.mapToScene(bed.rect().center() - QPointF(140.0, 140.0)))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, press)
    QTest.mouseMove(view.viewport(), press + QPoint(300, 0))
    QTest.mouseMove(view.viewport(), press + QPoint(600, 0))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, press + QPoint(600, 0))

    bed_delta = bed.pos() - bed_start
    plant_delta = plant.pos() - plant_start
    assert bed_delta.x() != 0.0, "the bed must actually have been dragged"
    assert plant_delta == bed_delta, "the plant follows the bed exactly, first frame included"
    assert len(view.command_manager._undo_stack) == before + 1

    view.command_manager.undo()
    assert bed.pos() == bed_start, "undo puts the bed back"
    assert plant.pos() == plant_start, "... and the child with it, to the centimetre"
    assert plant.parent_bed_id == bed.item_id



def _discard_on_close(monkeypatch: Any) -> None:
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Discard,
    )


def test_agent_move_object_reparent_into_bed_undoes_as_one_step(qtbot: Any, monkeypatch: Any) -> None:
    """Agent move_object reparenting a plant into a bed is ONE undo step (#635)."""
    from open_garden_planner.app.application import GardenPlannerApp

    _discard_on_close(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    try:
        scene = window.canvas_scene
        view = window.canvas_view

        bed = RectangleItem(x=200, y=200, width=400, height=400,
                            object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        plant = CircleItem(center_x=900, center_y=400, radius=20, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
        scene.addItem(plant)
        assert plant.parent_bed_id is None
        start_pos = QPointF(plant.pos())

        before = len(view.command_manager._undo_stack)
        # Move plant into the bed: dx = -500, dy = 0
        res = window._do_agent_move_object(str(plant.item_id), -500.0, 0.0)
        assert res["bed_membership_changed"] is True
        assert res["new_parent_bed_id"] == str(bed.item_id)
        assert plant.parent_bed_id == bed.item_id
        assert len(view.command_manager._undo_stack) == before + 1, "exactly one undo step recorded (#635)"

        view.command_manager.undo()
        assert plant.parent_bed_id is None, "one undo restores None parent"
        assert plant.pos() == start_pos, "... and restores original position"

        view.command_manager.redo()
        assert plant.parent_bed_id == bed.item_id, "one redo restores bed parent"
        assert plant.pos() != start_pos, "... and restores moved position"
    finally:
        window._project_manager.mark_clean()
        window._stop_agent_api()
        window.close()


def test_agent_move_object_reparent_out_of_bed_undoes_as_one_step(qtbot: Any, monkeypatch: Any) -> None:
    """Agent move_object reparenting a plant out of a bed is ONE undo step (#635)."""
    from open_garden_planner.app.application import GardenPlannerApp

    _discard_on_close(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    try:
        scene = window.canvas_scene
        view = window.canvas_view

        bed = RectangleItem(x=200, y=200, width=400, height=400,
                            object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        plant = CircleItem(center_x=400, center_y=400, radius=20, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
        scene.addItem(plant)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        start_pos = QPointF(plant.pos())

        before = len(view.command_manager._undo_stack)
        # Move plant out of bed: dx = 500, dy = 0
        res = window._do_agent_move_object(str(plant.item_id), 500.0, 0.0)
        assert res["bed_membership_changed"] is True
        assert res["new_parent_bed_id"] is None
        assert plant.parent_bed_id is None
        assert len(view.command_manager._undo_stack) == before + 1, "exactly one undo step recorded (#635)"

        view.command_manager.undo()
        assert plant.parent_bed_id == bed.item_id, "one undo restores bed parent"
        assert plant.pos() == start_pos, "... and restores position inside bed"

        view.command_manager.redo()
        assert plant.parent_bed_id is None, "one redo detaches from bed"
        assert plant.pos() != start_pos
    finally:
        window._project_manager.mark_clean()
        window._stop_agent_api()
        window.close()


def test_agent_set_object_position_reparent_undoes_as_one_step(qtbot: Any, monkeypatch: Any) -> None:
    """Agent set_object_position reparenting a plant is ONE undo step (#635)."""
    from open_garden_planner.app.application import GardenPlannerApp

    _discard_on_close(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    try:
        scene = window.canvas_scene
        view = window.canvas_view

        bed = RectangleItem(x=200, y=200, width=400, height=400,
                            object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        plant = CircleItem(center_x=900, center_y=400, radius=20, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {"common_name": "Apple", "scientific_name": "Malus domestica"}
        scene.addItem(plant)
        assert plant.parent_bed_id is None
        start_pos = QPointF(plant.pos())

        before = len(view.command_manager._undo_stack)
        # Set position into bed (center at 400, 400)
        res = window._do_agent_set_object_position(str(plant.item_id), 400.0, 400.0)
        assert res["bed_membership_changed"] is True
        assert res["new_parent_bed_id"] == str(bed.item_id)
        assert plant.parent_bed_id == bed.item_id
        assert len(view.command_manager._undo_stack) == before + 1, "exactly one undo step recorded (#635)"

        view.command_manager.undo()
        assert plant.parent_bed_id is None
        assert plant.pos() == start_pos

        view.command_manager.redo()
        assert plant.parent_bed_id == bed.item_id
        assert plant.pos() != start_pos
    finally:
        window._project_manager.mark_clean()
        window._stop_agent_api()
        window.close()

