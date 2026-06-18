"""Integration tests for rotation-aware drag-resize (issue #218 + follow-up).

The interactive resize routes every rect-bearing item (Circle/Rectangle/Ellipse)
through one rotation-aware "resize about a scene anchor" primitive: the corner or
edge OPPOSITE the dragged handle stays fixed in the scene, the rotation origin is
re-pinned to the new rect centre, and a circle stays circular with the dragged
handle tracking the cursor.

The earlier bug (PR #221 manual test): a rotated circle resize was incoherent —
``min(width, height)`` + a scene-space fixed-edge guess that disagreed with the
rotated frame, so the diameter collapsed/refused to grow and the centre drifted.
These tests drive the real ``ResizeHandle._apply_resize(delta)`` (one call per
mouse-move) with the initial state seeded as ``mousePressEvent`` does.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    HandlePosition,
    ResizeHandle,
    resize_rect_item_keeping_anchor,
)

_ANGLES = [0.0, 45.0, 215.0]
_CORNER = HandlePosition.BOTTOM_RIGHT
_EDGE = HandlePosition.MIDDLE_LEFT  # horizontal edge (drives width)
_EDGE_V = HandlePosition.TOP_CENTER  # vertical edge (drives height)
_HANDLES = [_CORNER, _EDGE, _EDGE_V]

_LEFT = {HandlePosition.TOP_LEFT, HandlePosition.MIDDLE_LEFT, HandlePosition.BOTTOM_LEFT}
_RIGHT = {HandlePosition.TOP_RIGHT, HandlePosition.MIDDLE_RIGHT, HandlePosition.BOTTOM_RIGHT}
_TOP = {HandlePosition.TOP_LEFT, HandlePosition.TOP_CENTER, HandlePosition.TOP_RIGHT}
_BOTTOM = {HandlePosition.BOTTOM_LEFT, HandlePosition.BOTTOM_CENTER, HandlePosition.BOTTOM_RIGHT}


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=8000, height_cm=6000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _make(shape: str) -> CircleItem | RectangleItem | EllipseItem:
    if shape == "circle":
        return CircleItem(300.0, 300.0, 50.0, object_type=ObjectType.SHRUB)
    if shape == "rect":
        return RectangleItem(250.0, 260.0, 100.0, 80.0)
    return EllipseItem(250.0, 260.0, 100.0, 80.0)


def _fixed_local(rect: QRectF, pos: HandlePosition) -> QPointF:
    """The corner/edge point OPPOSITE the handle (centre on a non-driven axis)."""
    x = (
        rect.right() if pos in _LEFT
        else rect.left() if pos in _RIGHT
        else rect.center().x()
    )
    y = (
        rect.bottom() if pos in _TOP
        else rect.top() if pos in _BOTTOM
        else rect.center().y()
    )
    return QPointF(x, y)


def _outward_delta(pos: HandlePosition, angle_deg: float, mag: float) -> QPointF:
    """Scene delta that drives ``pos`` outward by ``mag`` in the item's local frame."""
    lx = -1.0 if pos in _LEFT else 1.0 if pos in _RIGHT else 0.0
    ly = -1.0 if pos in _TOP else 1.0 if pos in _BOTTOM else 0.0
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    return QPointF((lx * c - ly * s) * mag, (lx * s + ly * c) * mag)


def _seed(item: object, pos: HandlePosition) -> ResizeHandle:
    handle = ResizeHandle(pos, item)  # type: ignore[arg-type]
    handle._initial_rect = QRectF(item.rect())  # type: ignore[attr-defined]
    handle._initial_parent_pos = item.pos()  # type: ignore[attr-defined]
    handle._drag_start_pos = QPointF(0, 0)
    handle._is_dragging = True
    return handle


def _diag(item: object) -> float:
    r = item.rect()  # type: ignore[attr-defined]
    return math.hypot(r.width(), r.height())


# ---------------------------------------------------------------------------
# The fixed corner/edge stays put across a multi-step drag; invariants hold.


@pytest.mark.parametrize("shape", ["circle", "rect", "ellipse"])
@pytest.mark.parametrize("angle", _ANGLES)
@pytest.mark.parametrize("handle", _HANDLES)
def test_fixed_reference_stays_put(
    canvas: CanvasView, shape: str, angle: float, handle: HandlePosition
) -> None:
    item = _make(shape)
    canvas.scene().addItem(item)
    item._apply_rotation(angle)

    anchor0 = item.mapToScene(_fixed_local(item.rect(), handle))
    h = _seed(item, handle)

    for mag in (20.0, 55.0, 110.0):  # cumulative deltas, as mouse-move sends
        h._apply_resize(_outward_delta(handle, angle, mag))

        # The side opposite the handle has not moved on screen.
        anchor = item.mapToScene(_fixed_local(item.rect(), handle))
        assert anchor.x() == pytest.approx(anchor0.x(), abs=1e-6)
        assert anchor.y() == pytest.approx(anchor0.y(), abs=1e-6)
        # Pivot tracks the new geometric centre, and what the .ogp stores equals
        # the on-screen centre (no save/reload drift).
        assert item.transformOriginPoint() == item.rect().center()
        ser = QPointF(
            item.pos().x() + item.rect().center().x(),
            item.pos().y() + item.rect().center().y(),
        )
        vis = item.mapToScene(item.rect().center())
        assert ser.x() == pytest.approx(vis.x(), abs=1e-6)
        assert ser.y() == pytest.approx(vis.y(), abs=1e-6)
        if shape == "circle":
            assert item.rect().width() == pytest.approx(item.rect().height())


# ---------------------------------------------------------------------------
# The dragged handle tracks the cursor: outward grows, inward shrinks — for
# corner AND edge handles, at every angle. (The old bug: a circle could not grow
# at all from a middle handle, and a 45deg corner drag collapsed it.)


@pytest.mark.parametrize("shape", ["circle", "rect", "ellipse"])
@pytest.mark.parametrize("angle", _ANGLES)
@pytest.mark.parametrize("handle", _HANDLES)
def test_outward_grows_inward_shrinks(
    canvas: CanvasView, shape: str, angle: float, handle: HandlePosition
) -> None:
    grow = _make(shape)
    canvas.scene().addItem(grow)
    grow._apply_rotation(angle)
    start = _diag(grow)
    _seed(grow, handle)._apply_resize(_outward_delta(handle, angle, 60.0))
    assert _diag(grow) > start + 1.0  # genuinely larger (not capped/collapsed)

    shrink = _make(shape)
    canvas.scene().addItem(shrink)
    shrink._apply_rotation(angle)
    start2 = _diag(shrink)
    _seed(shrink, handle)._apply_resize(_outward_delta(handle, angle, -20.0))
    assert _diag(shrink) < start2 - 1.0


@pytest.mark.parametrize("shape", ["rect", "ellipse"])
@pytest.mark.parametrize("angle", _ANGLES)
@pytest.mark.parametrize(
    ("handle", "keeps"),
    [(_EDGE, "height"), (_EDGE_V, "width")],
)
def test_edge_handle_keeps_perpendicular_dimension(
    canvas: CanvasView, shape: str, angle: float, handle: HandlePosition, keeps: str
) -> None:
    """A rect/ellipse edge drag changes only the driven axis (non-square items)."""
    item = _make(shape)
    canvas.scene().addItem(item)
    item._apply_rotation(angle)
    before = item.rect()
    _seed(item, handle)._apply_resize(_outward_delta(handle, angle, 40.0))
    after = item.rect()
    if keeps == "height":
        assert after.height() == pytest.approx(before.height())
        assert after.width() > before.width()
    else:
        assert after.width() == pytest.approx(before.width())
        assert after.height() > before.height()


def test_circle_middle_handle_can_grow(canvas: CanvasView) -> None:
    """Regression: min(w,h) used to cap a circle's growth from an edge handle."""
    c = CircleItem(300.0, 300.0, 50.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(c)
    _seed(c, HandlePosition.MIDDLE_RIGHT)._apply_resize(_outward_delta(HandlePosition.MIDDLE_RIGHT, 0.0, 40.0))
    assert c.radius > 50.0


@pytest.mark.parametrize("angle", _ANGLES)
def test_small_drag_does_not_collapse(canvas: CanvasView, angle: float) -> None:
    """A small drag yields a small change — not a collapse to ~MINIMUM_SIZE_CM."""
    c = CircleItem(300.0, 300.0, 50.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(c)
    c._apply_rotation(angle)
    _seed(c, _CORNER)._apply_resize(_outward_delta(_CORNER, angle, 6.0))
    assert c.radius == pytest.approx(53.0, abs=1.0)  # ~ +3cm radius, not collapsed


# ---------------------------------------------------------------------------
# Undo of a rotated resize restores geometry, position AND pivot.


def test_undo_rotated_resize_restores_everything(canvas: CanvasView) -> None:
    circle = CircleItem(300.0, 300.0, 40.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(circle)
    circle._apply_rotation(45.0)
    init_rect = QRectF(circle.rect())
    init_pos = circle.pos()

    h = _seed(circle, _CORNER)
    h._apply_resize(_outward_delta(_CORNER, 45.0, 60.0))
    circle._on_resize_end(init_rect, init_pos)  # registers the undo command

    cmd_mgr = canvas.command_manager
    assert cmd_mgr.can_undo
    cmd_mgr.undo()

    assert circle.rect() == init_rect
    assert circle.pos() == init_pos
    assert circle.transformOriginPoint() == init_rect.center()


# ---------------------------------------------------------------------------
# The shared primitive still reproduces the centre-anchor case (#213/#219).


def test_helper_matches_set_radius_centered(canvas: CanvasView) -> None:
    a = CircleItem(300.0, 300.0, 25.0, object_type=ObjectType.SHRUB)
    b = CircleItem(300.0, 300.0, 25.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(a)
    canvas.scene().addItem(b)
    a._apply_rotation(45.0)
    b._apply_rotation(45.0)

    a.set_radius_centered(60.0)

    scene_center = b.mapToScene(b.rect().center())
    new_center = QPointF(60.0, 60.0)
    resize_rect_item_keeping_anchor(b, QRectF(0, 0, 120, 120), scene_center, new_center)

    assert a.pos().x() == pytest.approx(b.pos().x(), abs=1e-6)
    assert a.pos().y() == pytest.approx(b.pos().y(), abs=1e-6)
    assert a.transformOriginPoint() == b.transformOriginPoint()
