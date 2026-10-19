"""Refusal and cleanup preserve graph, geometry and command history."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMessageBox

from tests.constraint_tool_helpers import (
    DIALOG_TOOLS,
    SCENARIOS,
    click,
    geometry,
    items_for,
    make_canvas,
    modal_choices,
    run_gesture,
    selected_points,
)


@pytest.mark.parametrize("name", sorted(DIALOG_TOOLS))
def test_rejected_modal_has_no_effect(qtbot, monkeypatch, name):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch, accepted=False)
    items = items_for(view)
    before = geometry(items)
    tool = SCENARIOS[name][0](view)
    tool.activate()
    for a in selected_points(name, items):
        click(tool, a.point)
    tool.cancel()
    assert not view.scene().constraint_graph.constraints
    assert view.command_manager.undo_depth == 0
    assert geometry(items) == before
    assert not getattr(tool, "_graphics_items", [])


@pytest.mark.parametrize("name", SCENARIOS)
def test_switching_tools_removes_previews(qtbot, monkeypatch, name):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view)
    manager = view._tool_manager
    manager.set_active_tool(SCENARIOS[name][0](view).tool_type)
    tool = manager.active_tool
    if name not in {"edge_length", "fixed"}:
        click(tool, selected_points(name, items)[0].point)
    tool.mouse_move(None, QPointF(1800, 1800))
    from open_garden_planner.core.tools.base_tool import ToolType
    manager.set_active_tool(ToolType.SELECT)
    assert not getattr(tool, "_graphics_items", [])
    assert not getattr(tool, "_anchor_indicators", [])
    assert not getattr(tool, "_edge_indicators", [])
    assert not view.scene().constraint_graph.constraints
    assert view.command_manager.undo_depth == 0


def test_fixed_repeated_click_is_noop(qtbot, monkeypatch):
    view = make_canvas(qtbot)
    tool, items = run_gesture(view, monkeypatch, "fixed")
    before = geometry(items)
    identity = list(view.scene().constraint_graph.constraints)
    depth = view.command_manager.undo_depth
    click(tool, selected_points("fixed", items)[0].point)
    assert list(view.scene().constraint_graph.constraints) == identity
    assert view.command_manager.undo_depth == depth
    assert geometry(items) == before
    tool.cancel()


def test_conflicting_distance_refused_without_history(qtbot, monkeypatch):
    view = make_canvas(qtbot)
    tool, items = run_gesture(view, monkeypatch, "distance")
    graph = view.scene().constraint_graph
    existing = next(iter(graph.constraints.values()))
    before = geometry(items)
    depth = view.command_manager.undo_depth
    # Same anchors, incompatible fixed distance. Preserve real feasibility check.
    import open_garden_planner.core.tools.constraint_tool as tools
    def different_distance(dialog):
        dialog._spin.setValue(4)
        return tools.QDialog.DialogCode.Accepted
    monkeypatch.setattr(tools.DistanceInputDialog, "exec", different_distance)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    for a in selected_points("distance", items):
        click(tool, a.point)
    assert warnings
    assert list(graph.constraints) == [existing.constraint_id]
    assert view.command_manager.undo_depth == depth
    assert geometry(items) == before
    tool.cancel()


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_adjacent_parallel_polygon_edges_refused(qtbot, monkeypatch, rotation):
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.core.tools.constraint_tool import ParallelConstraintTool
    from tests.constraint_tool_helpers import anchor
    from tests.unit.test_constraint_tool_shapes import edge_shape
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    item = edge_shape("polygon", 600, 600, rotation)
    view.scene().addItem(item)
    before = geometry([item])
    warnings = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: warnings.append(args[2]))
    tool = ParallelConstraintTool(view)
    tool.activate()
    click(tool, anchor(item, AnchorType.EDGE_TOP, 0).point)
    click(tool, anchor(item, AnchorType.EDGE_RIGHT, 1).point)
    assert warnings
    assert not view.scene().constraint_graph.constraints
    assert view.command_manager.undo_depth == 0
    assert geometry([item]) == before
    tool.cancel()
