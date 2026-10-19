"""Supported edge/curve picks and nonzero rotations use real geometry."""
import math

import pytest
from PyQt6.QtCore import QLineF, QPointF

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import constraint_tool as tools
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, PolylineItem
from tests.constraint_tool_helpers import (
    anchor,
    click,
    geometry,
    items_for,
    make_canvas,
    modal_choices,
    run_gesture,
)


def round_trip(view, items, before):
    graph = view.scene().constraint_graph
    assert len(graph.constraints) == 1
    assert view.command_manager.undo_depth == 1
    constraint = next(iter(graph.constraints.values()))
    payload = constraint.to_dict()
    after = geometry(items)
    view.command_manager.undo()
    assert not graph.constraints
    assert geometry(items) == before
    view.command_manager.redo()
    assert graph.constraints[constraint.constraint_id].to_dict() == payload
    assert geometry(items) == after
    return constraint


@pytest.mark.parametrize("rotation", [0, 45, 215])
@pytest.mark.parametrize("shape", ["edge", "circle"])
def test_coincidence_on_geometry(qtbot, monkeypatch, shape, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    source = items[0]
    if shape == "circle":
        target = CircleItem(2100, 1300, 120)
        target._apply_rotation(rotation)
        view.scene().addItem(target)
        items.append(target)
        center = target.rect().center()
        point = target.mapToScene(center + QPointF(120 * math.cos(.63), 120 * math.sin(.63)))
        expected = ConstraintType.POINT_ON_CIRCLE
    else:
        target = items[1]
        point = target.mapToScene(QPointF(75, 0))
        expected = ConstraintType.POINT_ON_EDGE
    before = geometry(items)
    tool = tools.CoincidentConstraintTool(view)
    tool.activate()
    click(tool, anchor(source, AnchorType.CENTER).point)
    tool.mouse_move(None, point)
    tool.mouse_move(None, point)  # replace edge/circle hover overlay
    click(tool, point)
    constraint = round_trip(view, items, before)
    assert constraint.constraint_type == expected
    assert constraint.anchor_a.item_id == source.item_id
    assert constraint.anchor_a.anchor_type == AnchorType.CENTER
    assert constraint.anchor_a.anchor_index == 0
    assert constraint.anchor_b.item_id == target.item_id
    moved = anchor(source, AnchorType.CENTER).point
    if shape == "circle":
        assert constraint.anchor_b.anchor_type == AnchorType.CENTER
        assert constraint.anchor_b.anchor_index == 0
        assert constraint.anchor_c is None
        assert constraint.target_distance == 120
        center_scene = target.mapToScene(target.rect().center())
        assert QLineF(moved, center_scene).length() == pytest.approx(120, abs=1)
    else:
        assert constraint.anchor_b.anchor_type == AnchorType.CORNER
        assert constraint.anchor_c.anchor_type == AnchorType.CORNER
        assert (constraint.anchor_b.anchor_index, constraint.anchor_c.anchor_index) == (0, 1)
        assert constraint.anchor_c.item_id == target.item_id
        assert constraint.target_distance == 0
        assert abs(target.mapFromScene(moved).y()) <= 1
    tool.cancel()
    assert not tool._graphics_items


@pytest.mark.parametrize("axis", ["H", "V"])
@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_symmetry_axis(qtbot, monkeypatch, axis, rotation):
    run_gesture(make_canvas(qtbot), monkeypatch, "symmetry", axis=axis, rotation=rotation)


def edge_shape(kind, x, y, rotation):
    points = [QPointF(0, 0), QPointF(300, 0), QPointF(320, 240), QPointF(0, 220)]
    item = PolygonItem(points) if kind == "polygon" else PolylineItem(points)
    item.setPos(x, y)
    item._apply_rotation(rotation)
    return item


@pytest.mark.parametrize("kind", ["polygon", "polyline"])
@pytest.mark.parametrize("name", ["edge_length", "parallel", "perpendicular"])
@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_vertex_backed_edge_gestures(qtbot, monkeypatch, kind, name, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = [edge_shape(kind, 600, 600, rotation), edge_shape(kind, 1600, 1100, rotation + 25)]
    for item in items:
        view.scene().addItem(item)
    before = geometry(items)
    cls = {"edge_length": tools.EdgeLengthConstraintTool, "parallel": tools.ParallelConstraintTool,
           "perpendicular": tools.PerpendicularConstraintTool}[name]
    tool = cls(view)
    tool.activate()
    picks = [anchor(item, AnchorType.EDGE_TOP, 0) for item in items]
    for a in picks[:1 if name == "edge_length" else 2]:
        click(tool, a.point)
    constraint = round_trip(view, items, before)
    assert constraint.constraint_type == getattr(ConstraintType, name.upper())
    assert constraint.anchor_a.item_id == items[0].item_id
    assert constraint.anchor_a.anchor_index == 0
    if name == "edge_length":
        expected = AnchorType.CORNER if kind == "polygon" else AnchorType.ENDPOINT
        assert constraint.anchor_a.anchor_type == expected
        assert constraint.anchor_b.anchor_type == expected
        assert constraint.anchor_b.item_id == items[0].item_id
        assert constraint.anchor_b.anchor_index == 1
        vertices = [QPointF(p) for p in items[0].polygon()] if kind == "polygon" else items[0].points
        assert QLineF(vertices[0], vertices[1]).length() == pytest.approx(250, abs=1)
    else:
        assert constraint.anchor_a.anchor_type == AnchorType.EDGE_TOP
        assert constraint.anchor_b.anchor_type == AnchorType.EDGE_TOP
        assert constraint.anchor_b.item_id == items[1].item_id
        assert constraint.anchor_b.anchor_index == 0
        difference = (items[1].rotation() - items[0].rotation()) % 180
        assert min(difference, 180 - difference) == pytest.approx(0 if name == "parallel" else 90, abs=.01)
    tool.cancel()


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_equal_circle_radii(qtbot, monkeypatch, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = [CircleItem(700, 700, 120), CircleItem(1600, 1100, 80)]
    for item in items:
        item._apply_rotation(rotation)
        view.scene().addItem(item)
    before = geometry(items)
    tool = tools.EqualConstraintTool(view)
    tool.activate()
    for item in items:
        click(tool, anchor(item, AnchorType.EDGE_TOP).point)
    constraint = round_trip(view, items, before)
    assert constraint.constraint_type == ConstraintType.EQUAL
    assert constraint.target_distance == 120
    assert constraint.anchor_a.item_id == items[0].item_id
    assert constraint.anchor_b.item_id == items[1].item_id
    assert constraint.anchor_a.anchor_type == constraint.anchor_b.anchor_type == AnchorType.EDGE_TOP
    assert constraint.anchor_a.anchor_index == constraint.anchor_b.anchor_index == 0
    assert items[0].rect().width() == items[1].rect().width() == 240
    tool.cancel()


@pytest.mark.parametrize("kind", [AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM, AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT])
@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_rectangle_edge_length_all_edges(qtbot, monkeypatch, kind, rotation):
    view = make_canvas(qtbot)
    modal_choices(monkeypatch)
    items = items_for(view, rotation)
    before = geometry(items)
    center = items[0].mapToScene(items[0].rect().center())
    tool = tools.EdgeLengthConstraintTool(view)
    tool.activate()
    click(tool, anchor(items[0], kind).point)
    constraint = round_trip(view, items, before)
    assert constraint.constraint_type == ConstraintType.EDGE_LENGTH
    indexes = {AnchorType.EDGE_TOP: (0, 1), AnchorType.EDGE_BOTTOM: (2, 3),
               AnchorType.EDGE_LEFT: (0, 2), AnchorType.EDGE_RIGHT: (1, 3)}
    assert (constraint.anchor_a.anchor_index, constraint.anchor_b.anchor_index) == indexes[kind]
    rect = items[0].rect()
    length = rect.width() if kind in {AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM} else rect.height()
    assert length == pytest.approx(250)
    assert QLineF(center, items[0].mapToScene(rect.center())).length() < 1e-9
    assert items[0].transformOriginPoint() == rect.center()
    tool.cancel()
