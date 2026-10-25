"""A command refreshes only what it can change (#592).

The measured defect: an agent creating objects one call at a time paid
O(items) per command even after #450 made the z derivation one-per-layer. Two
``stack_changed`` listeners walked every scene item: ``update_dimension_lines``
refreshed every lock badge (each a full constraint-graph scan) and
``_restack_ground_changes`` classified every item. 600 single-item commands
produced 360 600 badge refreshes on a 600-item plan.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.commands import (
    AddConstraintCommand,
    ChangePropertyCommand,
    CreateItemCommand,
    MoveItemsCommand,
    RemoveConstraintCommand,
)
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import GROUND_Z_RANGE, CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.garden_item import PositionLockMixin


def _rectangle(x: float, *, object_type: ObjectType = ObjectType.HOUSE) -> RectangleItem:
    item = RectangleItem(x, 100, 40, 40)
    item.object_type = object_type
    return item


def _spy_on_classification(scene: CanvasScene) -> list[object]:
    """Count the per-item ground-band checks the scene actually performs."""
    checked: list[object] = []
    original = scene._ground_band_is_stale

    def spy(item):
        checked.append(item)
        return original(item)

    scene._ground_band_is_stale = spy  # type: ignore[method-assign]
    return checked


def test_single_item_commands_do_not_scan_the_scene(
    qtbot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)

    badges: list[object] = []
    original_badge = PositionLockMixin.refresh_lock_badge

    def badge_spy(self) -> None:
        badges.append(self)
        original_badge(self)

    monkeypatch.setattr(PositionLockMixin, "refresh_lock_badge", badge_spy)

    for index in range(100):
        view.command_manager.execute(CreateItemCommand(scene, _rectangle(index * 50)))

    # No lock badge can appear or disappear (no item has a FIXED constraint), and
    # adding a solid cannot reclassify an existing item's ground band.
    assert badges == []
    assert CreateItemCommand.changes_ground_band is False
    checked = _spy_on_classification(scene)

    # A ground surface added one command at a time still gets its band: addItem's
    # own synchronous derivation handles the new item, not the scene-wide scan.
    lawn = _rectangle(50, object_type=ObjectType.LAWN)
    view.command_manager.execute(CreateItemCommand(scene, lawn))
    assert GROUND_Z_RANGE[0] < lawn.zValue() < GROUND_Z_RANGE[1]
    assert checked == []


def test_a_fixed_constraint_still_refreshes_only_its_item(qtbot, monkeypatch) -> None:
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    rect = _rectangle(100)
    view.command_manager.execute(CreateItemCommand(scene, rect))
    other = _rectangle(300)
    view.command_manager.execute(CreateItemCommand(scene, other))

    badges: list[object] = []
    original_badge = PositionLockMixin.refresh_lock_badge

    def badge_spy(self) -> None:
        badges.append(self)
        original_badge(self)

    monkeypatch.setattr(PositionLockMixin, "refresh_lock_badge", badge_spy)

    anchor = AnchorRef(rect.item_id, AnchorType.CENTER, 0)
    view.command_manager.execute(
        AddConstraintCommand(
            scene.constraint_graph, anchor, anchor, 0,
            ConstraintType.FIXED, target_x=100, target_y=100,
        )
    )
    assert getattr(rect, "_lock_badge_item", None) is not None
    assert other not in badges
    assert rect in badges

    badges.clear()
    constraint = next(iter(scene.constraint_graph.constraints.values()))
    view.command_manager.execute(RemoveConstraintCommand(scene.constraint_graph, constraint))
    assert getattr(rect, "_lock_badge_item", None) is None
    # The item that HAD a badge is refreshed so the badge clears; the unrelated
    # item is still skipped.
    assert rect in badges and other not in badges


def test_a_reclassifying_command_still_restacks_the_band(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    rect = _rectangle(100, object_type=ObjectType.HOUSE)
    view.command_manager.execute(CreateItemCommand(scene, rect))
    assert not (GROUND_Z_RANGE[0] < rect.zValue() < GROUND_Z_RANGE[1])

    def set_type(item, value) -> None:
        item.object_type = value
        item.update()

    command = ChangePropertyCommand(
        rect, "object_type", ObjectType.HOUSE, ObjectType.LAWN, apply_func=set_type,
    )
    assert command.changes_ground_band is True
    checked = _spy_on_classification(scene)
    view.command_manager.execute(command)
    assert GROUND_Z_RANGE[0] < rect.zValue() < GROUND_Z_RANGE[1]
    assert rect in checked

    checked.clear()
    view.command_manager.undo()
    assert not (GROUND_Z_RANGE[0] < rect.zValue() < GROUND_Z_RANGE[1])
    assert rect in checked


def test_moving_an_item_is_ground_band_neutral(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    rect = _rectangle(100)
    view.command_manager.execute(CreateItemCommand(scene, rect))
    assert MoveItemsCommand.changes_ground_band is False
    view.command_manager.execute(MoveItemsCommand([rect], QPointF(30, 0)))
    assert rect.pos().x() == pytest.approx(30)
