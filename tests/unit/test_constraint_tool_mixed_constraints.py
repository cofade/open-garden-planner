"""Rectangle edge-length interactions preserve existing graph contracts (#406)."""
import pytest
from PyQt6.QtWidgets import QMessageBox

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
