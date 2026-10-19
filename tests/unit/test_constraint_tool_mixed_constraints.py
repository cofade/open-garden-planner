"""Rectangle edge-length interactions preserve existing graph contracts (#406)."""
import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QMessageBox

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import constraint_tool as tools
from tests.constraint_tool_helpers import (
    anchor,
    click,
    geometry,
    items_for,
    make_canvas,
    modal_choices,
)


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_resize_keeps_center_alignment(qtbot, monkeypatch, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    tool = tools.HorizontalConstraintTool(view)
    for item in items[:2]:
        click(tool, anchor(item, AnchorType.CENTER).point)
    graph = view.scene().constraint_graph
    existing = next(iter(graph.constraints.values()))
    before = geometry(items)
    depth = view.command_manager.undo_depth
    click(tools.EdgeLengthConstraintTool(view), anchor(items[0], AnchorType.EDGE_TOP).point)
    assert view.command_manager.undo_depth == depth + 1
    assert len(graph.constraints) == 2
    assert items[0].rect().width() == 250
    assert anchor(items[0], AnchorType.CENTER).point.y() == pytest.approx(anchor(items[1], AnchorType.CENTER).point.y(), abs=1)
    after = geometry(items)
    identity = set(graph.constraints)
    view.command_manager.undo()
    assert list(graph.constraints) == [existing.constraint_id]
    assert geometry(items) == before
    view.command_manager.redo()
    assert set(graph.constraints) == identity
    assert geometry(items) == after


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_resize_refuses_to_displace_fixed_item(qtbot, monkeypatch, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    click(tools.FixedConstraintTool(view), anchor(items[0], AnchorType.CENTER).point)
    graph = view.scene().constraint_graph
    before = geometry(items)
    existing = {key: c.to_dict() for key,c in graph.constraints.items()}
    depth = view.command_manager.undo_depth
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    click(tools.EdgeLengthConstraintTool(view), anchor(items[0], AnchorType.EDGE_TOP).point)
    assert warnings
    assert view.command_manager.undo_depth == depth
    assert {key: c.to_dict() for key,c in graph.constraints.items()} == existing
    assert geometry(items) == before
    fixed = next(iter(graph.constraints.values()))
    assert fixed.constraint_type == ConstraintType.FIXED
    assert (items[0].pos().x(), items[0].pos().y()) == (fixed.target_x, fixed.target_y)


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_incompatible_edge_length_refused_atomically(qtbot, monkeypatch, rotation):
    from open_garden_planner.ui.dialogs.constraint_conflict_dialog import ConstraintConflictDialog
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    tool = tools.EdgeLengthConstraintTool(view)
    click(tool, anchor(items[0], AnchorType.EDGE_TOP).point)
    graph = view.scene().constraint_graph
    before = geometry(items)
    existing = {key: c.to_dict() for key,c in graph.constraints.items()}
    depth = view.command_manager.undo_depth
    def different_distance(dialog):
        dialog._spin.setValue(4)
        return tools.QDialog.DialogCode.Accepted
    monkeypatch.setattr(tools.DistanceInputDialog, "exec", different_distance)
    refusals = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: refusals.append(args[2]))
    def reject_conflict(dialog):
        refusals.append(dialog.windowTitle())
        return tools.QDialog.DialogCode.Rejected
    monkeypatch.setattr(ConstraintConflictDialog, "exec", reject_conflict)
    click(tool, anchor(items[0], AnchorType.EDGE_TOP).point)
    assert refusals
    assert view.command_manager.undo_depth == depth
    assert {key: c.to_dict() for key,c in graph.constraints.items()} == existing
    assert geometry(items) == before
    assert not tool._graphics_items
    assert not tool._edge_indicators


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_feasibility_probe_exception_restores_geometry(qtbot, monkeypatch, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    before = geometry(items)
    def explode(*args):
        raise RuntimeError("injected feasibility probe error")
    monkeypatch.setattr(view, "is_constraint_feasible", explode)
    tool = tools.EdgeLengthConstraintTool(view)
    with pytest.raises(RuntimeError, match="injected feasibility"):
        click(tool, anchor(items[0], AnchorType.EDGE_TOP).point)
    assert geometry(items) == before
    assert view.command_manager.undo_depth == 0
    assert not view.scene().constraint_graph.constraints
    assert not tool._graphics_items
    assert not tool._edge_indicators


@pytest.mark.parametrize("rotation", [0, 45, 215])
@pytest.mark.parametrize("selected", [0, 1, 2])
def test_rectangle_resize_refuses_equal_chain(qtbot, monkeypatch, rotation, selected):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    equal = tools.EqualConstraintTool(view)
    for first, second in ((0, 1), (1, 2)):
        click(equal, anchor(items[first], AnchorType.EDGE_TOP).point)
        click(equal, anchor(items[second], AnchorType.EDGE_TOP).point)
    graph = view.scene().constraint_graph
    before = geometry(items)
    existing = {key: c.to_dict() for key, c in graph.constraints.items()}
    depth = view.command_manager.undo_depth
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    click(tools.EdgeLengthConstraintTool(view), anchor(items[selected], AnchorType.EDGE_TOP).point)
    assert warnings
    assert geometry(items) == before
    assert {key: c.to_dict() for key, c in graph.constraints.items()} == existing
    assert view.command_manager.undo_depth == depth
    view.command_manager.undo()
    assert len(graph.constraints) == 1
    view.command_manager.redo()
    assert geometry(items) == before
    assert {key: c.to_dict() for key, c in graph.constraints.items()} == existing


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_width_resize_preserves_equal_height(qtbot, monkeypatch, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    equal = tools.EqualConstraintTool(view)
    for item in items[:2]:
        click(equal, anchor(item, AnchorType.EDGE_LEFT).point)
    before = geometry(items)
    existing = {key: c.to_dict() for key, c in view.scene().constraint_graph.constraints.items()}
    click(tools.EdgeLengthConstraintTool(view), anchor(items[0], AnchorType.EDGE_TOP).point)
    assert items[0].rect().width() == 250
    assert items[0].rect().height() == items[1].rect().height() == 160
    after = geometry(items)
    view.command_manager.undo()
    assert geometry(items) == before
    assert {key: c.to_dict() for key, c in view.scene().constraint_graph.constraints.items()} == existing
    view.command_manager.redo()
    assert geometry(items) == after


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_refusal_modal_timer_serializes_original_geometry(qtbot, monkeypatch, rotation):
    from open_garden_planner.core.project import ProjectManager
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    click(tools.FixedConstraintTool(view), anchor(items[0], AnchorType.CENTER).point)
    before = geometry(items)
    payload = ProjectManager._serialize_item(items[0])
    observed = []
    def warning(*args):
        dialog = QDialog(view)
        def inspect():
            observed.append((geometry(items), ProjectManager._serialize_item(items[0])))
            dialog.accept()
        QTimer.singleShot(0, inspect)
        dialog.exec()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    click(tools.EdgeLengthConstraintTool(view), anchor(items[0], AnchorType.EDGE_TOP).point)
    assert observed == [(before, payload)]


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_conflicting_resize_cannot_offer_destructive_override(qtbot, monkeypatch, rotation):
    from open_garden_planner.ui.dialogs.constraint_conflict_dialog import ConstraintConflictDialog
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    tool = tools.EdgeLengthConstraintTool(view)
    click(tool, anchor(items[0], AnchorType.EDGE_TOP).point)
    graph = view.scene().constraint_graph
    existing = {key: c.to_dict() for key, c in graph.constraints.items()}
    before = geometry(items)
    def different_distance(dialog):
        dialog._spin.setValue(4)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(tools.DistanceInputDialog, "exec", different_distance)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    def override(dialog):
        dialog._on_accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ConstraintConflictDialog, "exec", override)
    click(tool, anchor(items[0], AnchorType.EDGE_TOP).point)
    assert view.command_manager.undo_depth == 1
    assert geometry(items) == before
    assert {key: c.to_dict() for key, c in graph.constraints.items()} == existing
    view.command_manager.undo()
    assert not graph.constraints
    assert items[0].rect().width() == 200
    view.command_manager.redo()
    assert geometry(items) == before
    assert {key: c.to_dict() for key, c in graph.constraints.items()} == existing
