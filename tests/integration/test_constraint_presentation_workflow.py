"""Constraint gestures, panel actions and history through real app wiring (#457)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType
from tests.constraint_tool_helpers import geometry, run_gesture


def test_real_gesture_panel_selection_deletion_and_history(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    view = window.canvas_view
    view.set_snap_enabled(False)
    run_gesture(view, monkeypatch, "distance", integration=True, rotation=45)
    graph = window.canvas_scene.constraint_graph
    pair = next(iter(graph.constraints.values()))
    payload = pair.to_dict()
    items = [item for item in window.canvas_scene.items() if hasattr(item, "item_id")
             and item.item_id in {pair.anchor_a.item_id, pair.anchor_b.item_id}]
    solved = geometry(items)
    panel = window.constraints_panel
    assert panel._list.count() == 1
    row = panel._list.itemWidget(panel._list.item(0))
    text = next(label for label in row.findChildren(QLabel) if label.text())
    assert text.text().endswith("2.50 m")
    assert text.toolTip().endswith("2.50 m")
    assert row._type_icon_name == "constraint_distance"
    panel._list.setCurrentRow(0)
    assert set(window.canvas_scene.selectedItems()) == set(items)
    depth = view.command_manager.undo_depth
    qtbot.mouseClick(row._delete_btn, Qt.MouseButton.LeftButton)
    assert not graph.constraints
    assert panel._list.count() == 0
    assert view.command_manager.undo_depth == depth + 1
    view.command_manager.undo()
    assert graph.constraints[pair.constraint_id].to_dict() == payload
    assert panel._list.count() == 1
    assert geometry(items) == solved
    view.command_manager.redo()
    assert not graph.constraints
    assert panel._list.count() == 0
    assert geometry(items) == solved


def test_fixed_items_make_incompatible_trial_infeasible(canvas, qtbot):
    # The real CanvasView feasibility preflight builds anchor offsets and respects
    # FIXED graph pins. It must not accept an impossible new relation (#457).
    from tests.constraint_tool_helpers import items_for

    a, b, _ = items_for(canvas)
    graph = canvas.scene().constraint_graph
    for item in (a, b):
        ref = AnchorRef(item.item_id, AnchorType.CENTER)
        graph.add_constraint(ref, ref, 0, constraint_type=ConstraintType.FIXED,
                             target_x=item.pos().x(), target_y=item.pos().y())
    before = geometry([a, b])
    history = canvas.command_manager.undo_depth
    serialized = {uid: c.to_dict() for uid, c in graph.constraints.items()}
    assert not canvas.is_constraint_feasible(
        AnchorRef(a.item_id, AnchorType.CENTER), AnchorRef(b.item_id, AnchorType.CENTER),
        200, ConstraintType.DISTANCE,
    )
    assert geometry([a, b]) == before
    assert canvas.command_manager.undo_depth == history
    assert {uid: c.to_dict() for uid, c in graph.constraints.items()} == serialized
