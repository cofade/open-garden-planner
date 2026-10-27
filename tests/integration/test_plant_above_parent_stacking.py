"""A plant renders above the bed, container, planter or trellis it stands in (#629).

The clamp that puts a plant immediately above its bed existed already — but it followed
``parent_bed_id``, and drawing a bed AROUND a standing plant makes no link (#443). So the
plant vanished behind the new parent in 2D while 3D drew it on the soil, and its sun badge
(#481/#627) vanished with it. The in-ground garden bed only looked immune because it is a
ground surface and sorts under everything.

Measured before the fix (plant added first, parent drawn around it): z(plant) 0.00001
against z(parent) 0.00002 for `RAISED_BED`, `CONTAINER`, `CONTAINER_ROUND`,
`WALL_PLANTER` and `TRELLIS` — the plant was under all five. `GARDEN_BED` sorted to
−750.0, which is the ground band, not a plant rule.

The rule now: a plant's stacking parent is its LINK, or — when it has none — the smallest
plant-parent whose outline contains its stable centre (``footprints.standing_point``, the
point the lift and the sun estimate ask). It is re-derived on add, on arrange and after
every command, so a bed resized or moved around a plant (or a plant moved into one) settles
too.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.commands import CreateItemCommand, MoveItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

PARENTS = (
    ObjectType.RAISED_BED,
    ObjectType.CONTAINER,
    ObjectType.CONTAINER_ROUND,
    ObjectType.WALL_PLANTER,
    ObjectType.TRELLIS,
    ObjectType.GARDEN_BED,
)
#: An L-shaped bed: two arms, a notch at (400..700, 300..700).
L_BED = [QPointF(100.0, 100.0), QPointF(700.0, 100.0), QPointF(700.0, 300.0),
         QPointF(400.0, 300.0), QPointF(400.0, 700.0), QPointF(100.0, 700.0)]


def _parent(scene: CanvasScene, kind: ObjectType) -> Any:
    layer = scene.active_layer.id
    if kind is ObjectType.CONTAINER_ROUND:
        return CircleItem(500.0, 500.0, 120.0, object_type=kind, layer_id=layer)
    return RectangleItem(360.0, 360.0, 280.0, 280.0, object_type=kind, layer_id=layer)


@pytest.mark.parametrize("kind", PARENTS, ids=lambda kind: kind.name)
def test_a_parent_drawn_around_a_standing_plant_keeps_it_on_top(
    qtbot: Any, kind: ObjectType
) -> None:
    """Every plant-parent type: the plant added FIRST is drawn above the parent."""
    scene = CanvasScene(1000.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    plant = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    scene.addItem(plant)
    qtbot.wait(1)
    parent = _parent(scene, kind)
    scene.addItem(parent)
    qtbot.wait(1)
    assert plant.zValue() > parent.zValue(), kind.name
    # . and it is the item a click finds, and the one the canvas draws on top
    assert scene.itemAt(QPointF(500.0, 500.0), view.transform()) is plant
    order = [item for item in scene.items() if item in (plant, parent)]
    assert order[0] is plant, f"{kind.name} covers the plant"


def test_the_bed_is_still_reachable_outside_the_plant(qtbot: Any) -> None:
    """The clamp moves the plant, not the whole bed: the bed stays clickable."""
    scene = CanvasScene(1000.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    plant = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    scene.addItem(plant)
    qtbot.wait(1)
    bed = RectangleItem(360.0, 360.0, 280.0, 280.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    scene.addItem(bed)
    qtbot.wait(1)
    assert scene.itemAt(QPointF(380.0, 380.0), view.transform()) is bed


def test_a_linked_plant_is_unchanged(qtbot: Any) -> None:
    """The shipped case — created inside an existing bed — keeps the same clamp."""
    scene = CanvasScene(1000.0, 1000.0)
    bed = RectangleItem(360.0, 360.0, 280.0, 280.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    scene.addItem(bed)
    qtbot.wait(1)
    plant = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    plant.parent_bed_id = bed.item_id
    scene.addItem(plant)
    qtbot.wait(1)
    assert plant.zValue() > bed.zValue()


def test_a_distant_bed_does_not_clamp_a_plant(qtbot: Any) -> None:
    """Containment is geometry, not "any bed in the layer"."""
    scene = CanvasScene(1600.0, 1000.0)
    plant = CircleItem(300.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    scene.addItem(plant)
    qtbot.wait(1)
    far = RectangleItem(1200.0, 300.0, 200.0, 200.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    scene.addItem(far)
    qtbot.wait(1)
    assert plant.zValue() < far.zValue(), "an unrelated bed is newer and stays above"


def test_a_plant_moved_into_a_bed_is_raised_by_the_command(qtbot: Any) -> None:
    """A command creates the condition: the per-command restack settles it (#629)."""
    scene = CanvasScene(1600.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    commands = view.command_manager
    plant = CircleItem(300.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, plant, "plant"))
    bed = RectangleItem(1000.0, 400.0, 300.0, 300.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, bed, "bed"))
    qtbot.wait(1)
    assert plant.zValue() < bed.zValue(), "the older plant is below the newer bed"
    commands.execute(MoveItemsCommand([plant], QPointF(850.0, 0.0)))  # into the bed
    qtbot.wait(1)
    assert plant.zValue() > bed.zValue(), "a plant moved into a bed must come above it"
    commands.undo()
    qtbot.wait(1)
    # Undo puts the plant back OUTSIDE the bed. It keeps the higher z it was given
    # while inside - harmless (a plant above a bed it is not in hides nothing), and the
    # clamp never has to *lower* anything, which is what keeps the per-command check a
    # one-way test (stated in ADR-043's addendum).
    assert not bed.sceneBoundingRect().contains(plant.scenePos())
    assert plant.zValue() > bed.zValue()


def test_a_bed_grown_around_a_plant_raises_it(qtbot: Any) -> None:
    """A resize is the same class: the command's own slot asks the shape again (#629).

    Through the real ``ResizeItemCommand`` — not ``setRect`` plus a hand-made call —
    so the flag's wiring (command → ``stack_changed`` → the scan) is exercised.
    """
    from open_garden_planner.core.commands import ResizeItemCommand
    from open_garden_planner.ui.canvas.geometry_apply import (
        apply_rect_like_geometry,
        build_rect_resize,
    )

    scene = CanvasScene(1600.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    commands = view.command_manager
    plant = CircleItem(300.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, plant, "plant"))
    bed = RectangleItem(100.0, 300.0, 100.0, 100.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, bed, "bed"))
    qtbot.wait(1)
    assert plant.zValue() < bed.zValue(), "the older plant is below the newer bed"

    old, new = build_rect_resize(bed, 400.0, 400.0)   # now it contains the plant
    assert bed.rect().width() == 100.0
    commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    qtbot.wait(1)
    assert bed.rect().width() == 400.0
    assert plant.zValue() > bed.zValue(), "a bed grown around a plant must lift it"

    commands.undo()
    qtbot.wait(1)
    assert bed.rect().width() == 100.0


def test_only_add_and_delete_commands_are_containment_neutral() -> None:
    """The ``changes_containment`` table, re-derived from ``core.commands`` (#629).

    A wrong ``False`` is invisible to every other test here: the plant stays behind the
    bed and the driving test still passes because it asks the scan by hand. So the
    neutral set is named, every other command class must keep the safe default, and
    the classes that move, resize, rotate or re-type an item are named explicitly.
    """
    import inspect

    from open_garden_planner.core import commands as commands_module

    defined = {
        cls for _name, cls in inspect.getmembers(commands_module, inspect.isclass)
        if issubclass(cls, commands_module.Command)
        and cls is not commands_module.Command
        and cls.__module__ == commands_module.__name__
    }
    neutral = {cls for cls in defined if not cls.changes_containment}
    assert neutral == set(commands_module.CONTAINMENT_NEUTRAL_COMMANDS)
    assert neutral == {
        commands_module.CreateItemCommand,
        commands_module.CreateItemsCommand,
        commands_module.DeleteItemsCommand,
    }, "a new neutral command must be a deliberate decision"
    for cls in (
        commands_module.MoveItemsCommand,
        commands_module.ResizeItemCommand,
        commands_module.RotateItemCommand,
        commands_module.MoveVertexCommand,
        commands_module.ChangePropertyCommand,
        commands_module.SetParentBedCommand,
        commands_module.GroupCommand,
        commands_module.UngroupCommand,
        commands_module.MoveToLayerCommand,
    ):
        assert cls.changes_containment is True, cls.__name__


def test_an_add_skips_the_scan_and_a_move_asks_it(qtbot, monkeypatch: Any) -> None:
    """The flag reaches the scene: an add is derived by ``addItem``, a move is not."""
    scene = CanvasScene(1600.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    calls: list[int] = []
    original = scene._restack_plant_containment

    def counted() -> None:
        calls.append(1)
        original()

    monkeypatch.setattr(scene, "_restack_plant_containment", counted)
    plant = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    view.command_manager.execute(CreateItemCommand(scene, plant, "plant"))
    assert calls == [], "an add cannot hide a plant: it must not scan"
    view.command_manager.execute(MoveItemsCommand([plant], QPointF(20.0, 0.0)))
    assert calls == [1], "a move can carry a plant into/out of a bed: it must scan"


def test_a_healthy_layer_asks_no_shape_question(qtbot: Any) -> None:
    """The restack's cost: when plants already draw above their beds, no shape test."""
    from open_garden_planner.ui.canvas import footprints

    scene = CanvasScene(1600.0, 1000.0)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    bed = RectangleItem(360.0, 360.0, 280.0, 280.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    view.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
    plant = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    view.command_manager.execute(CreateItemCommand(scene, plant, "plant"))
    qtbot.wait(1)
    assert plant.zValue() > bed.zValue()

    calls = {"shape_contains": 0}
    original = footprints.shape_contains

    def counted(*args: Any, **kwargs: Any) -> bool:
        calls["shape_contains"] += 1
        return original(*args, **kwargs)

    footprints.shape_contains = counted
    try:
        scene._restack_plant_containment()
    finally:
        footprints.shape_contains = original
    assert calls["shape_contains"] == 0, "a healthy layer must do no shape work"


def test_a_polygon_bed_around_a_plant_raises_it(qtbot: Any) -> None:
    """An L-shaped (polygon) bed is the same rule, not a rectangle special case."""
    scene = CanvasScene(1000.0, 1000.0)
    plant = CircleItem(300.0, 300.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)
    scene.addItem(plant)
    qtbot.wait(1)
    bed = PolygonItem(list(L_BED), object_type=ObjectType.RAISED_BED,
                      layer_id=scene.active_layer.id)
    scene.addItem(bed)
    qtbot.wait(1)
    assert plant.zValue() > bed.zValue()


def test_a_plant_in_the_notch_of_a_concave_bed_is_not_clamped(qtbot: Any) -> None:
    """The bbox prefilter is not the test: the notch of an L is outside the bed."""
    scene = CanvasScene(1000.0, 1000.0)
    plant = CircleItem(600.0, 600.0, 30.0, object_type=ObjectType.PERENNIAL,
                       layer_id=scene.active_layer.id)   # in the L's notch
    scene.addItem(plant)
    qtbot.wait(1)
    bed = PolygonItem(list(L_BED), object_type=ObjectType.RAISED_BED,
                      layer_id=scene.active_layer.id)
    scene.addItem(bed)
    qtbot.wait(1)
    assert plant.zValue() < bed.zValue(), "the notch is not the bed"
