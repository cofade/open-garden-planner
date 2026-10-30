"""#649 manual regression: orientation creation preserves FIXED geometry."""

import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsLineItem, QMessageBox

from open_garden_planner.core.commands import MoveItemsCommand
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem, RectangleItem
from tests.constraint_tool_helpers import click, geometry
from tests.integration.test_constrained_rotation import window as application_window_fixture

window = application_window_fixture

EDGE_TYPES = (AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM, AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT)


def _edge(item, index=None, kind=None):
    return next(a for a in get_anchor_points(item)
                if (a.anchor_index == index if index is not None else a.anchor_type == kind)
                and a.anchor_type in EDGE_TYPES)


def _points(edge):
    """Independent scene-space endpoint measurement, not the tool's angle helper."""
    item = edge.item
    if isinstance(item, PolygonItem):
        polygon = item.polygon()
        i = edge.anchor_index
        return item.mapToScene(polygon.at(i)), item.mapToScene(polygon.at((i + 1) % polygon.count()))
    rect = item.rect()
    ends = {
        AnchorType.EDGE_TOP: (rect.topLeft(), rect.topRight()),
        AnchorType.EDGE_BOTTOM: (rect.bottomLeft(), rect.bottomRight()),
        AnchorType.EDGE_LEFT: (rect.topLeft(), rect.bottomLeft()),
        AnchorType.EDGE_RIGHT: (rect.topRight(), rect.bottomRight()),
    }[edge.anchor_type]
    return item.mapToScene(ends[0]), item.mapToScene(ends[1])


def _relation(a, b, kind):
    a0, a1 = _points(a)
    b0, b1 = _points(b)
    va, vb = a1 - a0, b1 - b0
    norm = math.hypot(va.x(), va.y()) * math.hypot(vb.x(), vb.y())
    if kind == ConstraintType.PERPENDICULAR:
        return abs(va.x() * vb.x() + va.y() * vb.y()) / norm
    return abs(va.x() * vb.y() - va.y() * vb.x()) / norm


def _assert_connector(scene, constraint, edge_a, edge_b):
    group = scene.dimension_line_manager._groups[constraint.constraint_id]
    connector = next(item for item in group.items if isinstance(item, QGraphicsLineItem)
                     and item.pen().style() == Qt.PenStyle.DashLine)
    for actual, edge in zip((connector.mapToScene(connector.line().p1()),
                             connector.mapToScene(connector.line().p2())),
                            (edge_a, edge_b), strict=True):
        p0, p1 = _points(edge)
        expected = (p0 + p1) / 2
        assert (actual.x(), actual.y()) == pytest.approx((expected.x(), expected.y()), abs=1e-9)


def _world_geometry(items):
    result = []
    for item in items:
        if isinstance(item, PolygonItem):
            points = list(item.polygon())
        else:
            rect = item.rect()
            points = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        mapped = [item.mapToScene(point) for point in points]
        result.append((item.rotation(), *(coordinate for point in mapped
                                          for coordinate in (point.x(), point.y()))))
    return result


def _items(canvas, angle=15):
    triangle = PolygonItem([QPointF(300, 400), QPointF(420, 400), QPointF(360, 490)])
    triangle._apply_rotation(angle)
    rectangle = RectangleItem(800, 400, 100, 100)
    rectangle._apply_rotation(0)
    canvas.scene().addItem(triangle)
    canvas.scene().addItem(rectangle)
    return triangle, rectangle


def _lock(canvas, item):
    ref = AnchorRef(item.item_id, AnchorType.CENTER)
    return canvas.scene().constraint_graph.add_constraint(
        ref, ref, 0, constraint_type=ConstraintType.FIXED,
        target_x=item.pos().x(), target_y=item.pos().y(),
    )


def _activate(canvas, kind):
    canvas.set_active_tool(ToolType.CONSTRAINT_PERPENDICULAR
                           if kind == ConstraintType.PERPENDICULAR else ToolType.CONSTRAINT_PARALLEL)
    return canvas.tool_manager.active_tool


@pytest.mark.parametrize("kind", [ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR])
@pytest.mark.parametrize("angle", [15, 45, 215])
@pytest.mark.parametrize("edge_kind", EDGE_TYPES)
@pytest.mark.parametrize("fixed_index", [0, 1])
def test_selected_edges_align_without_rotating_a_fixed_item(
    canvas, monkeypatch, kind, angle, edge_kind, fixed_index,
):
    def unexpected(*args):
        pytest.fail(f"Unexpected refusal: {args[2]}")
    monkeypatch.setattr(QMessageBox, "warning", unexpected)
    items = _items(canvas, angle)
    locked = items[fixed_index]
    fixed = _lock(canvas, locked)
    before = geometry(items)
    graph = canvas.scene().constraint_graph
    depth = canvas.command_manager.undo_depth
    a, b = _edge(items[0], index=1), _edge(items[1], kind=edge_kind)
    tool = _activate(canvas, kind)
    click(tool, a.point)
    click(tool, b.point)
    assert geometry([locked])[0] == before[fixed_index]
    assert _relation(a, b, kind) < 1e-9
    added = next(c for c in graph.constraints.values() if c.constraint_type == kind)
    assert added.anchor_a.anchor_index == a.anchor_index
    assert added.anchor_b.anchor_type == b.anchor_type
    _assert_connector(canvas.scene(), added, a, b)
    assert canvas.command_manager.undo_depth == depth + 1
    after = geometry(items)
    canvas.command_manager.undo()
    assert graph.constraints == {fixed.constraint_id: fixed}
    assert geometry(items) == before
    canvas.command_manager.redo()
    assert geometry(items) == after
    assert added.constraint_id in graph.constraints
    assert _relation(a, b, kind) < 1e-9
    _assert_connector(canvas.scene(), added, a, b)


@pytest.mark.parametrize("kind", [ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR])
def test_both_locked_refuses_without_changing_graph_geometry_or_history(canvas, monkeypatch, kind):
    items = _items(canvas)
    for item in items:
        _lock(canvas, item)
    spare = RectangleItem(1200, 100, 10, 10)
    canvas.scene().addItem(spare)
    canvas.command_manager.execute(MoveItemsCommand([spare], QPointF(1, 0)))
    canvas.command_manager.undo()
    before = geometry(items)
    graph = canvas.scene().constraint_graph
    constraints = dict(graph.constraints)
    history = (canvas.command_manager.undo_depth, canvas.command_manager.redo_depth)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    tool = _activate(canvas, kind)
    click(tool, _edge(items[0], index=1).point)
    click(tool, _edge(items[1], kind=AnchorType.EDGE_LEFT).point)
    assert warnings
    assert geometry(items) == before
    assert graph.constraints == constraints
    assert (canvas.command_manager.undo_depth, canvas.command_manager.redo_depth) == history


@pytest.mark.parametrize("kind", [ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR])
def test_fixed_member_of_rotation_chain_pins_the_whole_chain(canvas, monkeypatch, kind):
    triangle, rectangle = _items(canvas)
    partner = RectangleItem(0, 0, 100, 100)
    partner.setPos(1100, 400)
    canvas.scene().addItem(partner)
    graph = canvas.scene().constraint_graph
    graph.add_constraint(AnchorRef(rectangle.item_id, AnchorType.EDGE_TOP),
                         AnchorRef(partner.item_id, AnchorType.EDGE_TOP), 0,
                         constraint_type=ConstraintType.PARALLEL)
    _lock(canvas, partner)
    before = geometry([rectangle, partner])
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    tool = _activate(canvas, kind)
    click(tool, a.point)
    click(tool, b.point)
    assert geometry([rectangle, partner]) == before
    assert _relation(a, b, kind) < 1e-9


def test_real_toolbar_perpendicular_gesture_keeps_the_locked_rectangle(
    window, qtbot, monkeypatch, tmp_path,
):
    canvas = window.canvas_view
    triangle, rectangle = _items(canvas)
    _lock(canvas, rectangle)
    triangle.setSelected(True)
    window.resize(2200, 1000)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(200)
    canvas.set_zoom(1)
    canvas.centerOn(650, 450)
    qtbot.wait(30)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))
    toolbar = window.constraint_toolbar
    QTest.mouseClick(toolbar._buttons[ToolType.CONSTRAINT_PERPENDICULAR], Qt.MouseButton.LeftButton)
    assert canvas.tool_manager.active_tool.tool_type == ToolType.CONSTRAINT_PERPENDICULAR
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    before = geometry([rectangle])
    for edge in (a, b):
        assert canvas.viewport().rect().contains(canvas.mapFromScene(edge.point))
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(edge.point))
    qtbot.wait(50)
    assert geometry([rectangle]) == before
    assert _relation(a, b, ConstraintType.PERPENDICULAR) < 1e-9
    added = next(c for c in canvas.scene().constraint_graph.constraints.values()
                 if c.constraint_type == ConstraintType.PERPENDICULAR)
    _assert_connector(canvas.scene(), added, a, b)
    after = geometry([triangle, rectangle])
    world_after = _world_geometry([triangle, rectangle])
    ids = triangle.item_id, rectangle.item_id
    constraint_ids = set(canvas.scene().constraint_graph.constraints)
    window.canvas_view.command_manager.undo()
    assert geometry([rectangle]) == before
    window.canvas_view.command_manager.redo()
    assert geometry([triangle, rectangle]) == after
    from open_garden_planner.core.project import ProjectManager

    canvas.set_active_tool(ToolType.SELECT)
    path = tmp_path / "fixed-perpendicular.ogp"
    manager = ProjectManager()
    manager.save(canvas.scene(), path)
    manager.load(canvas.scene(), path)
    loaded = [canvas.scene().find_item_by_id(item_id) for item_id in ids]
    for actual, expected in zip(_world_geometry(loaded), world_after, strict=True):
        assert actual == pytest.approx(expected, abs=1e-9, rel=0)
    assert set(canvas.scene().constraint_graph.constraints) == constraint_ids
    assert _relation(_edge(loaded[0], index=1), _edge(loaded[1], kind=AnchorType.EDGE_LEFT),
                     ConstraintType.PERPENDICULAR) < 1e-9


@pytest.mark.parametrize("kind", [ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR])
def test_free_rotation_chain_follows_while_fixed_reference_stays(canvas, monkeypatch, kind):
    triangle, rectangle = _items(canvas)
    partner = RectangleItem(0, 0, 100, 100)
    partner.setPos(1100, 400)
    partner._apply_rotation(0)
    canvas.scene().addItem(partner)
    graph = canvas.scene().constraint_graph
    graph.add_constraint(AnchorRef(rectangle.item_id, AnchorType.EDGE_TOP),
                         AnchorRef(partner.item_id, AnchorType.EDGE_TOP), 0,
                         constraint_type=ConstraintType.PARALLEL)
    _lock(canvas, triangle)
    before = geometry([triangle, rectangle, partner])
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    tool = _activate(canvas, kind)
    click(tool, a.point)
    click(tool, b.point)
    assert geometry([triangle])[0] == before[0]
    assert rectangle.rotation() == pytest.approx(partner.rotation())
    assert _relation(a, b, kind) < 1e-9
    after = geometry([triangle, rectangle, partner])
    canvas.command_manager.undo()
    assert geometry([triangle, rectangle, partner]) == before
    canvas.command_manager.redo()
    assert geometry([triangle, rectangle, partner]) == after


@pytest.mark.parametrize("kind", [ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR])
def test_satisfied_relation_can_be_added_between_fixed_objects(canvas, monkeypatch, kind):
    triangle, rectangle = _items(canvas)
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    p0, p1 = _points(a)
    angle = math.degrees(math.atan2(p1.y()-p0.y(), p1.x()-p0.x()))
    rectangle._apply_rotation(angle if kind == ConstraintType.PERPENDICULAR else angle-90)
    for item in (triangle, rectangle):
        _lock(canvas, item)
    before = geometry([triangle, rectangle])
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))
    tool = _activate(canvas, kind)
    click(tool, a.point)
    click(tool, _edge(rectangle, kind=AnchorType.EDGE_LEFT).point)
    assert geometry([triangle, rectangle]) == before
    assert _relation(a, b, kind) < 1e-9
    assert canvas.command_manager.undo_depth == 1


def test_conflicting_orientation_in_same_component_is_refused(canvas, monkeypatch):
    triangle, rectangle = _items(canvas)
    graph = canvas.scene().constraint_graph
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    # Establish a parallel relation first, then request perpendicular on the same edges.
    click(_activate(canvas, ConstraintType.PARALLEL), a.point)
    click(canvas.tool_manager.active_tool, b.point)
    a, b = _edge(triangle, index=1), _edge(rectangle, kind=AnchorType.EDGE_LEFT)
    before = geometry([triangle, rectangle])
    constraints = dict(graph.constraints)
    depth = canvas.command_manager.undo_depth
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    tool = _activate(canvas, ConstraintType.PERPENDICULAR)
    click(tool, a.point)
    click(tool, b.point)
    assert warnings
    assert graph.constraints == constraints
    assert geometry([triangle, rectangle]) == before
    assert canvas.command_manager.undo_depth == depth


@pytest.mark.parametrize("item_class", [PolygonItem, PolylineItem])
def test_vertex_edge_indicator_keeps_its_index_when_classification_changes(canvas, item_class):
    item = item_class([QPointF(100, 100), QPointF(300, 100),
                       QPointF(300, 300), QPointF(100, 300)])
    canvas.scene().addItem(item)
    before = _edge(item, index=0)
    item._move_vertex_to(1, QPointF(100, 250))
    after = _edge(item, index=0)
    assert before.anchor_type != after.anchor_type
    expected = item.mapToScene(QPointF(100, 175))
    actual = canvas.scene().dimension_line_manager._resolve_anchor_position(
        item.item_id, before.anchor_type, before.anchor_index,
    )
    assert actual == expected
