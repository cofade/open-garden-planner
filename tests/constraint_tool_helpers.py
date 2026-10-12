"""Real constraint gesture harness shared by characterization and integration tests.

Only modal choices are controlled. Picking, graph writes, solves and history are real.
"""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QDialog, QMessageBox

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.core.tools import constraint_tool as tools
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem

SCENARIOS = {
    "distance": (tools.ConstraintTool, ConstraintType.DISTANCE),
    "horizontal": (tools.HorizontalConstraintTool, ConstraintType.HORIZONTAL),
    "vertical": (tools.VerticalConstraintTool, ConstraintType.VERTICAL),
    "horizontal_distance": (tools.HorizontalDistanceConstraintTool, ConstraintType.HORIZONTAL_DISTANCE),
    "vertical_distance": (tools.VerticalDistanceConstraintTool, ConstraintType.VERTICAL_DISTANCE),
    "coincident": (tools.CoincidentConstraintTool, ConstraintType.COINCIDENT),
    "angle": (tools.AngleConstraintTool, ConstraintType.ANGLE),
    "symmetry": (tools.SymmetryConstraintTool, ConstraintType.SYMMETRY_HORIZONTAL),
    "edge_length": (tools.EdgeLengthConstraintTool, ConstraintType.EDGE_LENGTH),
    "equal": (tools.EqualConstraintTool, ConstraintType.EQUAL),
    "parallel": (tools.ParallelConstraintTool, ConstraintType.PARALLEL),
    "perpendicular": (tools.PerpendicularConstraintTool, ConstraintType.PERPENDICULAR),
    "fixed": (tools.FixedConstraintTool, ConstraintType.FIXED),
}
EDGE_TOOLS = {"edge_length", "equal", "parallel", "perpendicular"}
DIALOG_TOOLS = {"distance", "horizontal_distance", "vertical_distance", "angle", "symmetry", "edge_length"}


def make_canvas(qtbot):
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


def modal_choices(monkeypatch, *, accepted=True, axis="H"):
    def choose(dialog):
        if hasattr(dialog, "_combo"):
            dialog._combo.setCurrentIndex(0 if axis == "H" else 1)
        elif isinstance(dialog, tools.AngleInputDialog):
            dialog._spin.setValue(60)
        else:
            dialog._spin.setValue(2.5)
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
    for cls in (tools.DistanceInputDialog, tools.HDistanceInputDialog,
                tools.VDistanceInputDialog, tools.AngleInputDialog, tools.SymmetryAxisDialog):
        monkeypatch.setattr(cls, "exec", choose)
    def unexpected_warning(*args):
        pytest.fail(f"Unexpected constraint warning: {args[2]}")
    monkeypatch.setattr(QMessageBox, "warning", unexpected_warning)
    monkeypatch.setattr(QMessageBox, "information", unexpected_warning)


def items_for(view, rotation=0):
    items = []
    for x, y, w, h, angle in ((500, 500, 200, 160, rotation),
                              (1100, 800, 300, 240, rotation + 25),
                              (1600, 600, 240, 180, 0)):
        item = RectangleItem(0, 0, w, h)
        item.setPos(x, y)
        item.setTransformOriginPoint(item.rect().center())
        item._apply_rotation(angle)
        view.scene().addItem(item)
        items.append(item)
    return items


def geometry(items):
    def shape(item):
        if hasattr(item, "rect"):
            return item.rect()
        if hasattr(item, "polygon"):
            return tuple(QPointF(p) for p in item.polygon())
        return tuple(QPointF(p) for p in item.points)
    return [(i.pos(), shape(i), i.rotation(), i.transformOriginPoint()) for i in items]


def anchor(item, kind, index=0):
    return next(a for a in get_anchor_points(item)
                if a.anchor_type == kind and a.anchor_index == index)


def click(tool, point):
    event = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton)
    assert tool.mouse_move(event, point)
    assert tool.mouse_press(event, point)
    assert tool.mouse_release(event, point) is False


def selected_points(name, items):
    kind = AnchorType.EDGE_TOP if name in EDGE_TOOLS else AnchorType.CENTER
    anchors = [anchor(i, kind) for i in items]
    count = 1 if name in {"fixed", "edge_length"} else 3 if name == "angle" else 2
    return anchors[:count]


def run_gesture(view, monkeypatch, name, *, rotation=0, integration=False, axis="H"):
    modal_choices(monkeypatch, axis=axis)
    items = items_for(view, rotation)
    cls, expected_type = SCENARIOS[name]
    if integration:
        manager = view._tool_manager
        manager.set_active_tool(next(kind for kind, candidate in manager._tools.items()
                                     if type(candidate) is cls))
        tool = manager.active_tool
    else:
        tool = cls(view)
        tool.activate()
    before = geometry(items)
    depth = view.command_manager.undo_depth
    anchors = selected_points(name, items)
    for a in anchors:
        # Exercise both free and snapped preview endpoints, including preview replacement.
        tool.mouse_move(None, QPointF(2500, 2000))
        click(tool, a.point)
    graph = view.scene().constraint_graph
    assert len(graph.constraints) == 1
    constraint = next(iter(graph.constraints.values()))
    if name == "symmetry" and axis == "V":
        expected_type = ConstraintType.SYMMETRY_VERTICAL
    assert constraint.constraint_type == expected_type
    assert constraint.anchor_a.item_id == items[0].item_id
    if name == "fixed":
        assert constraint.anchor_a.anchor_type == AnchorType.CENTER
        assert constraint.anchor_b == constraint.anchor_a
        assert (constraint.target_x, constraint.target_y) == (500, 500)
    elif name == "edge_length":
        assert constraint.anchor_a.anchor_type == AnchorType.CORNER
        assert constraint.anchor_b.anchor_type == AnchorType.CORNER
        assert (constraint.anchor_a.anchor_index, constraint.anchor_b.anchor_index) == (0, 1)
        assert constraint.anchor_b.item_id == items[0].item_id
    else:
        assert constraint.anchor_b.item_id == items[1].item_id
        assert constraint.anchor_a.anchor_type == anchors[0].anchor_type
        assert constraint.anchor_b.anchor_type == anchors[1].anchor_type
        assert constraint.anchor_a.anchor_index == anchors[0].anchor_index
        assert constraint.anchor_b.anchor_index == anchors[1].anchor_index
    if name == "angle":
        assert constraint.anchor_c.item_id == items[2].item_id
        assert constraint.anchor_c.anchor_type == AnchorType.CENTER
        assert constraint.target_distance == 60
    if name in {"distance", "horizontal_distance", "vertical_distance", "edge_length"}:
        assert constraint.target_distance == 250
    if name in {"horizontal", "vertical", "coincident"}:
        assert constraint.target_distance == 0
    if name == "equal":
        assert constraint.target_distance == 200
    if name == "symmetry":
        coordinate = "y" if axis == "H" else "x"
        assert constraint.target_distance == pytest.approx(
            (getattr(anchors[0].point, coordinate)() + getattr(anchors[1].point, coordinate)()) / 2)
    assert view.command_manager.undo_depth == depth + 1
    # Verify the solve actually applies the advertised relation, not merely a graph row.
    import math
    a = anchor(items[0], AnchorType.CENTER).point
    b = anchor(items[1], AnchorType.CENTER).point
    if name == "distance":
        assert math.hypot(a.x() - b.x(), a.y() - b.y()) == pytest.approx(250, abs=0.5)
    elif name == "horizontal":
        assert a.y() == pytest.approx(b.y(), abs=0.5)
    elif name == "vertical":
        assert a.x() == pytest.approx(b.x(), abs=0.5)
    elif name == "horizontal_distance":
        assert abs(a.x() - b.x()) == pytest.approx(250, abs=0.5)
    elif name == "vertical_distance":
        assert abs(a.y() - b.y()) == pytest.approx(250, abs=0.5)
    elif name == "coincident":
        assert math.hypot(a.x() - b.x(), a.y() - b.y()) <= 0.5
    elif name == "equal":
        assert items[1].rect().width() == pytest.approx(items[0].rect().width())
    elif name == "edge_length":
        assert items[0].rect().width() == pytest.approx(250, abs=0.5), items[0].rect()
    elif name in {"parallel", "perpendicular"}:
        difference = (items[1].rotation() - items[0].rotation()) % 180
        assert min(difference, 180 - difference) == pytest.approx(0 if name == "parallel" else 90, abs=0.01)
    elif name == "angle":
        c = anchor(items[2], AnchorType.CENTER).point
        angle = math.degrees(math.atan2(a.y()-b.y(), a.x()-b.x())
                             - math.atan2(c.y()-b.y(), c.x()-b.x()))
        angle = abs((angle + 180) % 360 - 180)
        assert angle == pytest.approx(60, abs=0.5)
    elif name == "symmetry":
        mirrored = (a.y() + b.y()) / 2 if axis == "H" else (a.x() + b.x()) / 2
        assert mirrored == pytest.approx(constraint.target_distance, abs=0.5)
        assert (a.x() if axis == "H" else a.y()) == pytest.approx(
            b.x() if axis == "H" else b.y(), abs=0.5)
    identity = constraint.constraint_id
    payload = constraint.to_dict()
    after = geometry(items)
    view.command_manager.undo()
    assert not graph.constraints
    assert geometry(items) == before, (geometry(items), before)
    view.command_manager.redo()
    assert list(graph.constraints) == [identity]
    assert graph.constraints[identity].to_dict() == payload
    assert geometry(items) == after
    tool.cancel()
    assert not getattr(tool, "_graphics_items", [])
    assert not getattr(tool, "_anchor_indicators", [])
    assert not getattr(tool, "_edge_indicators", [])
    return tool, items


def assert_cancelled_gesture(qtbot, monkeypatch, name, mode):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view)
    tool = SCENARIOS[name][0](view)
    tool.activate()
    before = geometry(items)
    # Empty clicks and non-left buttons must not create a command.
    click(tool, QPointF(3500, 2500))
    assert tool.mouse_press(SimpleNamespace(button=lambda: Qt.MouseButton.RightButton), QPointF()) is False
    if name not in {"fixed", "edge_length"}:
        point = selected_points(name, items)[0].point
        click(tool, point)
        click(tool, point)  # repeated selection remains a pending gesture
        tool.mouse_move(None, QPointF(2500, 2000))
    if mode == "escape":
        assert tool.key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    elif mode == "cancel":
        tool.cancel()
    else:
        tool.deactivate()
    assert geometry(items) == before, (geometry(items), before)
    assert not view.scene().constraint_graph.constraints
    assert view.command_manager.undo_depth == 0
    assert not getattr(tool, "_graphics_items", [])
    assert not getattr(tool, "_anchor_indicators", [])
    assert not getattr(tool, "_edge_indicators", [])
