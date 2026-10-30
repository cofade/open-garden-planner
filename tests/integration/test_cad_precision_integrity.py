"""End-to-end regressions for the CAD-precision integrity package.

These drive the pieces the user actually touches: the Lock position action, a
real viewport drag, the Properties panel's Layer combo, and save/reload through
the project manager.  Unit-level coverage for the same issues lives in
``tests/unit/test_constraint_integrity.py``,
``tests/unit/test_geometry_identity.py`` and
``tests/unit/test_incidence_consistency.py``.
"""

from __future__ import annotations

import json
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsItem, QMenu

from open_garden_planner.core.constraints import (
    AnchorRef,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=6000, height_cm=4000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(900, 700)
    view.show()
    qtbot.waitExposed(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _lock(item) -> None:
    menu = QMenu()
    action = item.build_lock_context_menu(menu)
    assert item.dispatch_lock_action(action, action) is True


def _drag_in_view(canvas: CanvasView, item, delta: QPointF) -> None:
    """Press on *item*'s centre, move by *delta* in scene units, release."""
    canvas.centerOn(item.mapToScene(item.boundingRect().center()))
    start = canvas.mapFromScene(item.mapToScene(item.boundingRect().center()))
    target = canvas.mapFromScene(
        item.mapToScene(item.boundingRect().center()) + delta
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(canvas.viewport(), (start + target) / 2)
    QTest.mouseMove(canvas.viewport(), target)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target)


# ── #655: a saved position lock is still a lock after reopening ───────────


def test_saved_lock_still_holds_after_reopen(canvas: CanvasView, tmp_path) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(rect)
    _lock(rect)
    pinned = QPointF(rect.pos())
    path = tmp_path / "locked.ogp"
    ProjectManager().save(scene, path)

    ProjectManager().load(scene, path)
    loaded = next(
        item
        for item in scene.items()
        if getattr(item, "item_id", None) == rect.item_id
    )
    assert loaded.is_position_locked()

    constraint = next(
        constraint
        for constraint in scene.constraint_graph.constraints.values()
        if constraint.constraint_type == ConstraintType.FIXED
    )
    assert constraint.target_x is not None and constraint.target_y is not None, (
        "the lock's target coordinates were dropped on load"
    )
    assert (constraint.target_x, constraint.target_y) == (
        pinned.x(),
        pinned.y(),
    )

    _drag_in_view(canvas, loaded, QPointF(180.0, 120.0))
    assert loaded.pos() == pinned, "a reopened lock must still refuse to move"

    # ...and the next save does not erase it.
    again = tmp_path / "locked-again.ogp"
    ProjectManager().save(scene, again)
    raw = json.loads(again.read_text(encoding="utf-8"))
    fixed = next(
        entry for entry in raw["constraints"] if entry["constraint_type"] == "FIXED"
    )
    assert fixed["target_x"] == pytest.approx(pinned.x())
    assert fixed["target_y"] == pytest.approx(pinned.y())


# ── #662: a locked item is inert during the drag, not restored after it ───


def test_fixed_item_has_zero_transient_positions_during_a_drag(
    canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(rect)
    _lock(rect)
    pinned = QPointF(rect.pos())

    seen: list[QPointF] = []
    original = RectangleItem.itemChange

    def spy(self, change, value):
        result = original(self, change, value)
        if (
            self is rect
            and change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        ):
            seen.append(QPointF(self.pos()))
        return result

    monkeypatch.setattr(RectangleItem, "itemChange", spy)
    rect.setSelected(True)
    _drag_in_view(canvas, rect, QPointF(200.0, 140.0))
    monkeypatch.undo()

    assert rect.pos() == pinned
    assert seen == [], (
        f"the locked item reported {len(seen)} positions it never had: {seen}"
    )
    # The drag must leave no undo step for an object that cannot move.
    assert not canvas.command_manager.can_undo or (
        canvas.command_manager._undo_stack[-1].description
        not in ("Move item", "Move items (constrained)")
    )


def test_a_mobile_partner_still_follows_the_fixed_reference(canvas: CanvasView) -> None:
    scene = canvas.scene()
    fixed = RectangleItem(600, 700, 300, 200)
    scene.addItem(fixed)
    _lock(fixed)
    mobile = RectangleItem(1200, 700, 200, 200)
    scene.addItem(mobile)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(fixed.item_id, AnchorType.CENTER),
        AnchorRef(mobile.item_id, AnchorType.CENTER),
        600.0,
    )
    fixed_before = QPointF(fixed.pos())

    mobile.setSelected(True)
    _drag_in_view(canvas, mobile, QPointF(200.0, 0.0))

    assert fixed.pos() == fixed_before, "the fixed reference moved with the drag"
    distance = math.dist(
        (
            fixed.mapToScene(fixed.boundingRect().center()).x(),
            fixed.mapToScene(fixed.boundingRect().center()).y(),
        ),
        (
            mobile.mapToScene(mobile.boundingRect().center()).x(),
            mobile.mapToScene(mobile.boundingRect().center()).y(),
        ),
    )
    assert distance == pytest.approx(600.0, abs=1.0)


def test_the_lock_flag_is_restored_after_the_gesture(canvas: CanvasView) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200)
    scene.addItem(rect)
    _lock(rect)
    rect.setSelected(True)
    _drag_in_view(canvas, rect, QPointF(150.0, 100.0))

    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert rect.flags() & movable, "the drag must not leave the item frozen"

    # Unlocking restores normal behaviour.
    menu = QMenu()
    action = rect.build_lock_context_menu(menu)
    rect.dispatch_lock_action(action, action)
    assert rect.is_position_locked() is False
    before = QPointF(rect.pos())
    _drag_in_view(canvas, rect, QPointF(150.0, 100.0))
    assert rect.pos() != before, "an unlocked item must drag again"


# ── #658: the Layer combo survives its own change signal ─────────────────


@pytest.mark.parametrize("state", ["hidden", "locked"])
def test_layer_combo_change_does_not_destroy_the_sender(
    canvas: CanvasView, qtbot: object, state: str
) -> None:
    """Moving an item to a hidden/locked layer deselects it mid-signal (#658).

    The selection change synchronously rebuilds the Properties panel; the old
    ``_clear_form`` called ``removeRow``, which destroyed the combo box while its
    own ``currentIndexChanged`` was still being delivered (a SIGSEGV on macOS,
    a silently dropped signal here).
    """
    from PyQt6 import sip
    from PyQt6.QtWidgets import QComboBox

    from open_garden_planner.models.layer import Layer

    scene = canvas.scene()
    target_layer = Layer(
        name="Target", visible=state != "hidden", locked=state == "locked"
    )
    scene.add_layer(target_layer)

    rect = RectangleItem(600, 700, 300, 200)
    scene.addItem(rect)
    rect.setSelected(True)

    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_selected_items([rect])
    # The application wires the panel to the scene's selection; do the same so
    # the re-entrant rebuild happens exactly where it happens for the user.
    scene.selectionChanged.connect(
        lambda: panel.set_selected_items(list(scene.selectedItems()))
    )

    combo = next(
        child
        for child in panel.findChildren(QComboBox)
        if child.findData(target_layer.id) >= 0
    )
    alive: list[bool] = []

    def spy(_index: int) -> None:
        alive.append(not sip.isdeleted(combo))

    combo.currentIndexChanged.connect(spy)
    combo.setCurrentIndex(combo.findData(target_layer.id))

    assert alive == [True], "the change signal was dropped or the sender died in it"
    assert rect.layer_id == target_layer.id, "the item did move to the layer"
    assert panel._current_items == [], "the panel should have cleared"
    canvas.command_manager.undo()
    assert rect.layer_id != target_layer.id
    canvas.command_manager.redo()
    assert rect.layer_id == target_layer.id
