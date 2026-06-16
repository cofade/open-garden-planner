"""Integration tests for rotation-aware drag-resize (issue #218).

The interactive resize path historically kept the dragged-opposite edge fixed
with axis-aligned math and never re-pinned ``transformOriginPoint``. For a
*rotated* item that drifts: the serialized centre (``pos + rect.center()``)
stops matching the on-screen centre, so the item jumps on the next rotation and
on save/reload. #219 fixed this for the rotation gesture; #218 closes it for the
resize gesture by routing every rect-bearing resize through one rotation-aware
"resize about a scene anchor" primitive.

These tests drive ``ResizeHandle._apply_resize(delta)`` directly (what a real
handle drag calls per mouse-move), with the initial state seeded as
``mousePressEvent`` would.
"""

from __future__ import annotations

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

_ROTATION = 37.0


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _serialized_center(item: object) -> QPointF:
    """Mirror core.project: a rect-bearing item stores pos + rect.center()."""
    pos = item.pos()  # type: ignore[attr-defined]
    c = item.rect().center()  # type: ignore[attr-defined]
    return QPointF(pos.x() + c.x(), pos.y() + c.y())


def _drag_resize(item: object, handle_pos: HandlePosition, delta: QPointF) -> None:
    """Drive one handle drag of ``delta`` (scene coords), seeding initial state."""
    handle = ResizeHandle(handle_pos, item)  # type: ignore[arg-type]
    handle._initial_rect = QRectF(item.rect())  # type: ignore[attr-defined]
    handle._initial_parent_pos = item.pos()  # type: ignore[attr-defined]
    handle._apply_resize(delta)


# ---------------------------------------------------------------------------
# Drag-resizing a rotated item keeps the fixed corner put + pivot on centre.


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CircleItem(100.0, 100.0, 30.0, object_type=ObjectType.SHRUB),
        lambda: RectangleItem(80.0, 90.0, 200.0, 120.0),
        lambda: EllipseItem(80.0, 90.0, 200.0, 120.0),
    ],
)
def test_rotated_drag_resize_keeps_fixed_corner(canvas: CanvasView, factory) -> None:
    item = factory()
    canvas.scene().addItem(item)
    item._apply_rotation(_ROTATION)

    # Bottom-right drag → top-left corner is the fixed anchor.
    init_rect = QRectF(item.rect())
    anchor_before = item.mapToScene(init_rect.topLeft())

    _drag_resize(item, HandlePosition.BOTTOM_RIGHT, QPointF(40.0, 40.0))

    # Pivot tracks the new geometric centre (the serializer invariant).
    assert item.transformOriginPoint() == item.rect().center()
    # The fixed corner stayed exactly where it was on screen.
    anchor_after = item.mapToScene(item.rect().topLeft())
    assert anchor_after.x() == pytest.approx(anchor_before.x(), abs=1e-6)
    assert anchor_after.y() == pytest.approx(anchor_before.y(), abs=1e-6)
    # What the .ogp file stores matches the on-screen centre → no save/reload
    # drift when reopened (rotation re-applied about the same centre).
    serialized = _serialized_center(item)
    visual = item.mapToScene(item.rect().center())
    assert serialized.x() == pytest.approx(visual.x(), abs=1e-6)
    assert serialized.y() == pytest.approx(visual.y(), abs=1e-6)


def test_unrotated_resize_is_unchanged(canvas: CanvasView) -> None:
    """Rotation == 0 must not invoke the re-anchor (byte-for-byte old behaviour)."""
    rect = RectangleItem(0.0, 0.0, 100.0, 50.0)
    canvas.scene().addItem(rect)
    _drag_resize(rect, HandlePosition.BOTTOM_RIGHT, QPointF(50.0, 25.0))
    # Top-left fixed, no rotation → grows in place from the origin.
    assert rect.pos() == QPointF(0.0, 0.0)
    assert rect.rect().width() == pytest.approx(150.0)
    assert rect.rect().height() == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# Undo of a rotated resize restores pivot + centre, not just rect + pos.


def test_undo_rotated_resize_restores_pivot_and_centre(canvas: CanvasView) -> None:
    circle = CircleItem(150.0, 150.0, 40.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(circle)
    circle._apply_rotation(_ROTATION)

    init_rect = QRectF(circle.rect())
    init_pos = circle.pos()
    before_serialized = _serialized_center(circle)

    _drag_resize(circle, HandlePosition.BOTTOM_RIGHT, QPointF(60.0, 60.0))
    # Register the undo command exactly as mouseRelease would.
    circle._on_resize_end(init_rect, init_pos)

    cmd_mgr = canvas.command_manager
    assert cmd_mgr.can_undo

    cmd_mgr.undo()
    # Geometry, position AND pivot are all back to the pre-resize state.
    assert circle.rect() == init_rect
    assert circle.pos() == init_pos
    assert circle.transformOriginPoint() == init_rect.center()
    undone = _serialized_center(circle)
    assert undone.x() == pytest.approx(before_serialized.x(), abs=1e-6)
    assert undone.y() == pytest.approx(before_serialized.y(), abs=1e-6)


# ---------------------------------------------------------------------------
# The shared primitive reproduces the centre-anchor case (no #213/#219 regress).


def test_helper_matches_set_radius_centered(canvas: CanvasView) -> None:
    a = CircleItem(200.0, 200.0, 25.0, object_type=ObjectType.SHRUB)
    b = CircleItem(200.0, 200.0, 25.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(a)
    canvas.scene().addItem(b)
    a._apply_rotation(_ROTATION)
    b._apply_rotation(_ROTATION)

    # set_radius_centered goes through the helper; replicate it by hand on b.
    a.set_radius_centered(60.0)

    scene_center = b.mapToScene(b.rect().center())
    new_center = QPointF(60.0, 60.0)
    resize_rect_item_keeping_anchor(b, QRectF(0, 0, 120, 120), scene_center, new_center)

    assert a.pos().x() == pytest.approx(b.pos().x(), abs=1e-6)
    assert a.pos().y() == pytest.approx(b.pos().y(), abs=1e-6)
    assert a.transformOriginPoint() == b.transformOriginPoint()
