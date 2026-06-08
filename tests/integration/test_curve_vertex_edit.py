"""Integration tests for Bezier / Arc control-handle editing (issue #193, US-B9).

Selecting a placed curve shows draggable control handles; dragging one reshapes
the curve in place and commits a single undo step. Save/reload keeps the curve
editable.

Most tests drive the item hooks the ``CurveControlHandle`` invokes on press →
move → release (``_begin_curve_edit`` / ``_move_control`` / ``_end_curve_edit``)
directly. ``TestHandleDragViaView`` instead drives the **full Qt event path**
through ``CanvasView.mouse{Press,Move,Release}Event`` — this is the layer the
first manual-test round caught broken: the view must register
``CurveControlHandle`` as the active drag handle so it can re-establish the mouse
grab that Qt silently drops on ``ItemIgnoresTransformations`` child items.
"""

# ruff: noqa: ARG002

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.cad_geometry import arc_from_three_points
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import ArcItem, BezierItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    CURVE_KIND_CENTER,
    CurveControlHandle,
)


def _add_bezier(canvas: CanvasView) -> BezierItem:
    item = BezierItem(
        anchors=[QPointF(100, 100), QPointF(200, 200), QPointF(300, 100)],
        handles_in=[QPointF(100, 100), QPointF(150, 210), QPointF(300, 100)],
        handles_out=[QPointF(120, 100), QPointF(250, 190), QPointF(300, 100)],
    )
    canvas.scene().addItem(item)
    return item


def _add_arc(canvas: CanvasView) -> ArcItem:
    c, r, sd, sp = arc_from_three_points(
        QPointF(100, 300), QPointF(200, 260), QPointF(300, 300)
    )
    item = ArcItem(
        center=c, radius=r, start_deg=sd, span_deg=sp, through=QPointF(200, 260)
    )
    canvas.scene().addItem(item)
    return item


def _handles(item: object) -> list[CurveControlHandle]:
    return [c for c in item.childItems() if isinstance(c, CurveControlHandle)]


class TestBezierSelectionHandles:
    def test_select_shows_handles(self, canvas: CanvasView, qtbot: object) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        assert b.is_curve_edit_mode
        # 3 anchors + out0 + in1 + out1 + in2 = 7 control handles.
        assert len(_handles(b)) == 7

    def test_deselect_hides_handles(self, canvas: CanvasView, qtbot: object) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        b.setSelected(False)
        assert not b.is_curve_edit_mode
        assert not _handles(b)

    def test_remove_from_scene_clears_handles(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        canvas.scene().removeItem(b)
        assert not b.is_curve_edit_mode


class TestBezierReshapeUndo:
    def test_anchor_drag_reshapes_with_single_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        cm = canvas.command_manager
        n0 = len(cm._undo_stack)
        before = b._capture_geometry()

        b._begin_curve_edit()
        b._move_control("anchor", 1, QPointF(220, 240), False)
        b._end_curve_edit()

        assert b._capture_geometry() != before
        assert len(cm._undo_stack) == n0 + 1
        cm.undo()
        assert b._capture_geometry() == before

    def test_handle_drag_mirrors_and_undoes(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        cm = canvas.command_manager
        n0 = len(cm._undo_stack)

        b._begin_curve_edit()
        b._move_control("handle_out", 1, QPointF(260, 150), False)
        b._end_curve_edit()
        # Smooth join: the opposite tangent mirrored across the anchor.
        assert b.handles_in[1] == b.anchors[1] * 2.0 - QPointF(260, 150)
        assert len(cm._undo_stack) == n0 + 1

    def test_noop_drag_registers_no_command(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b = _add_bezier(canvas)
        b.setSelected(True)
        cm = canvas.command_manager
        n0 = len(cm._undo_stack)
        b._begin_curve_edit()
        b._end_curve_edit()  # no move in between
        assert len(cm._undo_stack) == n0

    def test_grabbing_handle_survives_drag_frame(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A live drag must reposition handles in place, never recreate them —
        otherwise the handle that grabbed the mouse would be destroyed mid-drag
        (``CurveControlHandle.mouseMoveEvent`` → ``_move_control`` →
        ``_update_control_handles``). Asserting object identity guards the
        "never recreates the grabbing handle" invariant against a future change
        to ``_curve_control_specs`` count-stability.
        """
        b = _add_bezier(canvas)
        b.setSelected(True)
        handles_before = list(b._control_handles)
        anchor1 = next(
            h for h in handles_before if h.kind == "anchor" and h.control_index == 1
        )

        b._begin_curve_edit()
        b._move_control("anchor", 1, QPointF(230, 250), False)  # one drag frame

        # Same handle objects, in the same order — the in-place reposition path
        # ran, not the _create_control_handles rebuild branch.
        assert all(
            a is bb
            for a, bb in zip(handles_before, b._control_handles, strict=True)
        )
        # …and the dragged anchor's handle actually tracked to the new position.
        assert anchor1.pos() == QPointF(230, 250)
        b._end_curve_edit()


class TestArcEditing:
    def test_select_shows_three_handles_plus_center(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        a = _add_arc(canvas)
        a.setSelected(True)
        handles = _handles(a)
        assert len(handles) == 4
        assert sum(1 for h in handles if h.kind == CURVE_KIND_CENTER) == 1

    def test_drag_through_keeps_endpoints_single_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        a = _add_arc(canvas)
        a.setSelected(True)
        cm = canvas.command_manager
        n0 = len(cm._undo_stack)
        s0, e0 = a._start_local(), a._end_local()
        before = a._capture_geometry()

        a._begin_curve_edit()
        a._move_control("arc_through", 0, QPointF(200, 230), False)
        a._end_curve_edit()

        assert math.hypot(a._start_local().x() - s0.x(), a._start_local().y() - s0.y()) < 1e-3
        assert math.hypot(a._end_local().x() - e0.x(), a._end_local().y() - e0.y()) < 1e-3
        assert len(cm._undo_stack) == n0 + 1
        cm.undo()
        assert a._capture_geometry() == before


class TestSaveReloadStillEditable:
    def test_bezier_roundtrip_still_reshapes(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        original = _add_bezier(canvas)
        clone = BezierItem.from_dict(original.to_dict())
        canvas.scene().addItem(clone)
        clone.setSelected(True)
        assert clone.is_curve_edit_mode
        clone._begin_curve_edit()
        clone._move_control("anchor", 0, QPointF(110, 110), False)
        clone._end_curve_edit()
        assert clone.anchors[0] == QPointF(110, 110)

    def test_arc_roundtrip_preserves_through_and_handles(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        original = _add_arc(canvas)
        clone = ArcItem.from_dict(original.to_dict())
        canvas.scene().addItem(clone)
        assert math.hypot(
            clone._through.x() - original._through.x(),
            clone._through.y() - original._through.y(),
        ) < 1e-6
        clone.setSelected(True)
        assert len(_handles(clone)) == 4


class TestHandleDragViaView:
    """Drive the FULL Qt event path through the view via ``QTest`` (real event
    dispatch — a hand-built ``QMouseEvent`` is NOT delivered to an
    ``ItemIgnoresTransformations`` child, which is why the polyline tests also
    avoid it).

    Regression for the first manual-test failure (#193): handles appeared but
    were inert because ``CanvasView`` did not recognise ``CurveControlHandle``
    in its dropped-grab workaround, so the handle got the press but never the
    moves. ``_active_drag_handle is handle`` pins exactly that bug.
    """

    def _setup(
        self, canvas: CanvasView, qtbot: object
    ) -> tuple[BezierItem, CurveControlHandle]:
        canvas.resize(900, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        canvas.set_active_tool(ToolType.SELECT)
        b = _add_bezier(canvas)
        b.setSelected(True)
        handle = next(
            h for h in _handles(b) if h.kind == "anchor" and h.control_index == 1
        )
        canvas.centerOn(handle.scenePos())  # keep the handle within the viewport
        return b, handle

    def test_view_registers_curve_handle_as_active_drag(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b, handle = self._setup(canvas, qtbot)
        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(handle.scenePos()),
        )
        # The exact invariant that was broken: the view must track the curve
        # handle so it can re-grab it (Qt drops the grab on the next move).
        assert canvas.scene().mouseGrabberItem() is handle
        assert canvas._active_drag_handle is handle
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(handle.scenePos()),
        )

    def test_full_drag_through_view_reshapes_with_one_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        b, handle = self._setup(canvas, qtbot)
        cm = canvas.command_manager
        n0 = len(cm._undo_stack)
        start_scene = handle.scenePos()
        before = b._capture_geometry()

        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(start_scene),
        )
        target_scene = QPointF(start_scene.x() + 60, start_scene.y() + 40)
        QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(target_scene))
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(target_scene),
        )

        assert b._capture_geometry() != before  # the curve actually reshaped
        assert len(cm._undo_stack) == n0 + 1  # exactly one undo step
        cm.undo()
        assert b._capture_geometry() == before
