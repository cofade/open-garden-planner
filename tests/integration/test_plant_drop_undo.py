"""A plant dragged into a bed is ONE undoable step: the move and its link (#627).

The owner's manual pass: dropping a plant into a bed linked it, and the first
Ctrl+Z undid only the link - the second the move. The drag's move and the link
commands it decides now run as one ``CompoundCommand``.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


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
    target = start + QPoint(90, 0)  # ~400 cm at this zoom: far enough to leave the old bed
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), target)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, target)

    assert bed.pos() != bed_start and plant.pos() != plant_start
    assert plant.parent_bed_id == bed.item_id, "the plant travelled with its bed"
    assert len(view.command_manager._undo_stack) == before + 1
    view.command_manager.undo()
    assert bed.pos() == bed_start and plant.pos() == plant_start
    assert plant.parent_bed_id == bed.item_id
