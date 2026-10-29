"""#485: a rotation gesture must keep distance constraints satisfied (one undo step).

The owner reported (2026-10-12) that rotating an object that shares a
corner-to-corner DISTANCE constraint with a partner leaves the dimension red:
the partner does not follow, the relation stays violated after release and
deselection, and only a later 1 cm nudge makes the partner jump into place —
with the nudge and the rotation each holding their own undo entry, so undoing
the nudge resurrects the broken relation.

These tests drive the REAL viewport gesture: QTest mouse events on the green
rotation handle, the real ``CanvasView``/``CanvasScene``/constraint graph and
the real command stack. Only geometry setup is direct.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.commands import AddConstraintCommand
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import RotationHandle


def _anchor(item: object, anchor_type: AnchorType, index: int = 0) -> QPointF:
    for anchor in get_anchor_points(item):  # type: ignore[arg-type]
        if anchor.anchor_type is anchor_type and anchor.anchor_index == index:
            return QPointF(anchor.point)
    raise AssertionError(f"{type(item).__name__} has no {anchor_type.name}[{index}] anchor")


def _distance(a: object, ai: int, b: object, bi: int) -> float:
    pa = _anchor(a, AnchorType.CORNER, ai)
    pb = _anchor(b, AnchorType.CORNER, bi)
    return math.hypot(pb.x() - pa.x(), pb.y() - pa.y())


def _rotation_handle(item: object) -> RotationHandle:
    handle = next(
        child
        for child in item.childItems()  # type: ignore[attr-defined]
        if isinstance(child, RotationHandle)
    )
    return handle


def _rotate(
    canvas: CanvasView,
    item: object,
    degrees: float,
    qtbot: object,
    *,
    release: bool = True,
) -> QPointF:
    """Drag ``item``'s rotation handle by ``degrees``; return the release point."""
    handle = _rotation_handle(item)
    centre_local = (
        item.rect().center()  # type: ignore[attr-defined]
        if hasattr(item, "rect")
        else item.boundingRect().center()  # type: ignore[attr-defined]
    )
    centre = item.mapToScene(centre_local)  # type: ignore[attr-defined]
    start_scene = handle.scenePos()
    start = canvas.mapFromScene(start_scene)
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    vector = start_scene - centre
    radians = math.radians(degrees)
    target_scene = centre + QPointF(
        vector.x() * math.cos(radians) - vector.y() * math.sin(radians),
        vector.x() * math.sin(radians) + vector.y() * math.cos(radians),
    )
    target = canvas.mapFromScene(target_scene)
    QTest.mouseMove(canvas.viewport(), target)
    if release:
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            target,
        )
    return target


def _show(canvas: CanvasView, qtbot: object) -> None:
    canvas.resize(1000, 800)
    canvas.show()
    qtbot.waitExposed(canvas)  # type: ignore[attr-defined]


class TestConstrainedRotationFollows:
    """The partner follows the rotated corner and the relation stays satisfied."""

    def test_distance_partner_follows_the_rotated_corner(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Rect-to-rect corner distance: satisfied during and after the gesture."""
        rect_a = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_a.setPos(300.0, 300.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(800.0, 300.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)

        # A's top-right corner to B's top-left corner.
        target = _distance(rect_a, 1, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(rect_a.item_id, AnchorType.CORNER, 1),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        partner_before = QPointF(rect_b.pos())
        undo_before = len(canvas.command_manager._undo_stack)

        _rotate(canvas, rect_a, 45.0, qtbot)

        assert rect_a.rotation() == pytest.approx(45.0, abs=2.0)
        assert rect_b.pos() != partner_before, (
            "the constrained partner must move with the rotated corner"
        )
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0), (
            "the distance relation must be satisfied on release"
        )
        assert len(canvas.command_manager._undo_stack) == undo_before + 1, (
            "one completed rotation is exactly one undo entry"
        )

        # Undo restores the angle AND the partner - one atomic step.
        canvas.command_manager.undo()
        assert rect_a.rotation() == pytest.approx(0.0, abs=0.01)
        assert rect_b.pos().x() == pytest.approx(partner_before.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(partner_before.y(), abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

        # Redo restores the completed geometry.
        canvas.command_manager.redo()
        assert rect_a.rotation() == pytest.approx(45.0, abs=2.0)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

    def test_partner_follows_DURING_the_gesture_not_only_on_release(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The relation is satisfied while the handle is still held (#485)."""
        rect_a = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_a.setPos(300.0, 300.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(800.0, 300.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)

        target = _distance(rect_a, 1, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(rect_a.item_id, AnchorType.CORNER, 1),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        release_point = _rotate(canvas, rect_a, 50.0, qtbot, release=False)
        try:
            assert rect_a.rotation() == pytest.approx(50.0, abs=2.0)
            assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0), (
                "the partner must follow during the gesture, not after a later move"
            )
        finally:
            QTest.mouseRelease(
                canvas.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                release_point,
            )

    def test_triangle_to_rectangle_corner_distance(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The owner's shape: rotating a triangle moves its corner anchor."""
        triangle = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(120.0, 0.0), QPointF(60.0, 90.0)]
        )
        triangle.setPos(300.0, 400.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(900.0, 400.0)
        canvas.scene().addItem(triangle)
        canvas.scene().addItem(rect_b)

        target = _distance(triangle, 0, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(triangle.item_id, AnchorType.CORNER, 0),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        _show(canvas, qtbot)
        canvas.centerOn(triangle.mapToScene(triangle.boundingRect().center()))
        triangle.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        undo_before = len(canvas.command_manager._undo_stack)
        _rotate(canvas, triangle, 74.0, qtbot)

        assert _distance(triangle, 0, rect_b, 0) == pytest.approx(target, abs=1.0)
        assert len(canvas.command_manager._undo_stack) == undo_before + 1
        canvas.command_manager.undo()
        assert triangle.rotation() == pytest.approx(0.0, abs=0.01)
        assert _distance(triangle, 0, rect_b, 0) == pytest.approx(target, abs=1.0)

    @pytest.mark.parametrize("degrees", [215.0, -75.5])
    def test_wrap_around_rotation_keeps_the_relation(
        self, canvas: CanvasView, qtbot: object, degrees: float
    ) -> None:
        """The owner's 284.5 degree report is a wrap-around case, not a special one."""
        rect_a = RectangleItem(0.0, 0.0, 120.0, 80.0)
        rect_a.setPos(400.0, 500.0)
        rect_b = RectangleItem(0.0, 0.0, 60.0, 90.0)
        rect_b.setPos(900.0, 700.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)

        target = _distance(rect_a, 1, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(rect_a.item_id, AnchorType.CORNER, 1),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        _rotate(canvas, rect_a, degrees, qtbot)

        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

    def test_rotation_then_nudge_then_successive_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Owner's full sequence: rotation -> tiny move -> undo, undo, redo, redo.

        Each undo must restore a COHERENT configuration; undoing the nudge must
        not resurrect a relation the rotation itself left broken.
        """
        rect_a = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_a.setPos(300.0, 300.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(800.0, 400.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)

        target = _distance(rect_a, 1, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(rect_a.item_id, AnchorType.CORNER, 1),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        start_a = QPointF(rect_a.pos())
        start_b = QPointF(rect_b.pos())
        undo_before = len(canvas.command_manager._undo_stack)

        _rotate(canvas, rect_a, 60.0, qtbot)
        rotated_a = rect_a.rotation()
        rotated_b = QPointF(rect_b.pos())
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

        # A tiny 1 cm move through the real arrow-key path (Shift = 1 cm).
        QTest.keyClick(
            canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
        )
        post_move_b = QPointF(rect_b.pos())
        assert len(canvas.command_manager._undo_stack) == undo_before + 2
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

        # 1st undo: the move only - relation still satisfied, rotation intact.
        canvas.command_manager.undo()
        assert rect_a.rotation() == pytest.approx(rotated_a, abs=0.01)
        assert rect_b.pos().x() == pytest.approx(rotated_b.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(rotated_b.y(), abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

        # 2nd undo: the rotation plus its partner correction.
        canvas.command_manager.undo()
        assert rect_a.rotation() == pytest.approx(0.0, abs=0.01)
        assert rect_a.pos().x() == pytest.approx(start_a.x(), abs=0.01)
        assert rect_a.pos().y() == pytest.approx(start_a.y(), abs=0.01)
        assert rect_b.pos().x() == pytest.approx(start_b.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(start_b.y(), abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)

        # 3rd undo: the constraint itself (owner's reported ordering).
        assert len(graph.constraints) == 1
        canvas.command_manager.undo()
        assert len(graph.constraints) == 0

        # Redo everything back.
        canvas.command_manager.redo()
        assert len(graph.constraints) == 1
        canvas.command_manager.redo()
        assert rect_a.rotation() == pytest.approx(rotated_a, abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)
        canvas.command_manager.redo()
        assert rect_b.pos().x() == pytest.approx(post_move_b.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(post_move_b.y(), abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)


class TestRotationUndoDiscipline:
    """A rotation is exactly one undo entry - even when the release path is lost."""

    def test_no_op_rotation_registers_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        rect = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect.setPos(300.0, 300.0)
        canvas.scene().addItem(rect)
        _show(canvas, qtbot)
        canvas.centerOn(rect.mapToScene(rect.rect().center()))
        rect.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        undo_before = canvas.command_manager.undo_depth
        handle = _rotation_handle(rect)
        point = canvas.mapFromScene(handle.scenePos())
        QTest.mousePress(
            canvas.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, point,
        )
        QTest.mouseRelease(
            canvas.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, point,
        )

        assert rect.rotation() == pytest.approx(0.0)
        assert canvas.command_manager.undo_depth == undo_before

    def test_lost_release_still_yields_one_undo_entry(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The view's safety net registers the rotation the handle never saw."""
        rect = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect.setPos(300.0, 300.0)
        canvas.scene().addItem(rect)
        _show(canvas, qtbot)
        rect.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        undo_before = canvas.command_manager.undo_depth
        rect.rotation_angle = 42.0
        rect.setRotation(42.0)
        canvas._ensure_rotation_undo(rect, 0.0, undo_before)

        assert canvas.command_manager.undo_depth == undo_before + 1
        canvas.command_manager.undo()
        assert rect.rotation() == pytest.approx(0.0)


class TestRotationPoliciesPreserved:
    """The fix must not reverse established constraint policy."""

    def test_interobject_parallel_refuses_the_rotation(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        rect_a = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_a.setPos(300.0, 300.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(800.0, 300.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            AnchorRef(rect_a.item_id, AnchorType.EDGE_TOP),
            AnchorRef(rect_b.item_id, AnchorType.EDGE_TOP),
            0.0,
            constraint_type=ConstraintType.PARALLEL,
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        partner_before = QPointF(rect_b.pos())
        undo_before = canvas.command_manager.undo_depth
        _rotate(canvas, rect_a, 40.0, qtbot)

        assert rect_a.rotation() == pytest.approx(0.0), (
            "an inter-object PARALLEL constraint keeps rotation blocked"
        )
        assert rect_b.pos().x() == pytest.approx(partner_before.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(partner_before.y(), abs=0.01)
        assert canvas.command_manager.undo_depth == undo_before
        assert len(graph.constraints) == 1

    def test_fixed_partner_stays_pinned_and_the_failure_is_real(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """FIXED keeps its meaning: the relation reads violated, not 'corrected'."""
        rect_a = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_a.setPos(300.0, 300.0)
        rect_b = RectangleItem(0.0, 0.0, 100.0, 100.0)
        rect_b.setPos(800.0, 300.0)
        canvas.scene().addItem(rect_a)
        canvas.scene().addItem(rect_b)

        target = _distance(rect_a, 1, rect_b, 0)
        graph = canvas._canvas_scene.constraint_graph
        canvas._execute_constraint_with_solve(
            AddConstraintCommand(
                graph,
                AnchorRef(rect_a.item_id, AnchorType.CORNER, 1),
                AnchorRef(rect_b.item_id, AnchorType.CORNER, 0),
                target,
                constraint_type=ConstraintType.DISTANCE,
            )
        )
        fixed_ref = AnchorRef(rect_b.item_id, AnchorType.CENTER)
        graph.add_constraint(
            fixed_ref,
            fixed_ref,
            0.0,
            constraint_type=ConstraintType.FIXED,
            target_x=rect_b.pos().x(),
            target_y=rect_b.pos().y(),
        )
        _show(canvas, qtbot)
        canvas.centerOn(rect_a.mapToScene(rect_a.rect().center()))
        rect_a.setSelected(True)
        qtbot.wait(20)  # type: ignore[attr-defined]

        partner_before = QPointF(rect_b.pos())
        undo_before = canvas.command_manager.undo_depth
        _rotate(canvas, rect_a, 35.0, qtbot)

        assert rect_b.pos().x() == pytest.approx(partner_before.x(), abs=0.01)
        assert rect_b.pos().y() == pytest.approx(partner_before.y(), abs=0.01)
        assert _distance(rect_a, 1, rect_b, 0) != pytest.approx(target, abs=1.0), (
            "a FIXED partner cannot follow, so the relation is genuinely violated"
        )
        assert canvas.command_manager.undo_depth == undo_before + 1
        canvas.command_manager.undo()
        assert rect_a.rotation() == pytest.approx(0.0)
        assert _distance(rect_a, 1, rect_b, 0) == pytest.approx(target, abs=1.0)
