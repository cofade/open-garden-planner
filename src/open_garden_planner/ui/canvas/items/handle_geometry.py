"""Shared handle geometry and live-edit announcement primitives."""
import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsItem,
)

from .garden_item import note_plan_changed

if TYPE_CHECKING:
    pass



HANDLE_BORDER_COLOR = QColor(255, 255, 255)
MINIMUM_SIZE_CM = 1.0

def _announce_live_edit(parent_item: QGraphicsItem | None) -> None:
    """A handle drag changes its item's GEOMETRY on every mouse move, and Qt has no
    ``itemChange`` for a geometry: tell the scene that the plan changed
    (``CanvasScene.note_plan_changed``), so that what follows the plan — the 3D
    view — follows the drag and not only its release. (The release is a command,
    and a command announces itself.) Called at the end of every handle's
    ``mouseMoveEvent`` that edits; pinned by a census of this module."""
    if parent_item is not None:
        note_plan_changed(parent_item.scene())


def _clamp_pos_to_canvas(pos: QPointF, parent_item: QGraphicsItem) -> QPointF:
    """Clamp a scene position to the canvas boundaries.

    Args:
        pos: Position in scene coordinates
        parent_item: An item whose scene has a canvas_rect property

    Returns:
        Position clamped to canvas rect, or original if no canvas rect available
    """
    scene = parent_item.scene() if parent_item else None
    if scene is not None and hasattr(scene, 'canvas_rect'):
        canvas_rect = scene.canvas_rect
        x = max(canvas_rect.left(), min(pos.x(), canvas_rect.right()))
        y = max(canvas_rect.top(), min(pos.y(), canvas_rect.bottom()))
        return QPointF(x, y)
    return pos


def anchored_position(
    new_rect: QRectF,
    rotation_deg: float,
    scene_anchor: QPointF,
    local_anchor: QPointF,
) -> QPointF:
    """The ``pos`` that pins ``local_anchor`` of ``new_rect`` onto ``scene_anchor``.

    The solved form of Qt's transform, extracted from
    :func:`resize_rect_item_keeping_anchor` so that callers which must *compute*
    a target position without mutating anything — the geometry builders in
    ``ui.canvas.geometry_apply``, which record ``pos`` into an undoable
    ``ResizeItemCommand`` dict — use the same formula the mutating primitive
    does, rather than a second transcription of it.

    Qt maps a local point ``p`` to scene as ``pos + O + R(θ)·(p − O)`` where
    ``O = transformOriginPoint`` and ``θ = item.rotation()``. With the origin
    pinned to ``new_rect.center()`` (the #219 serializer invariant), solving the
    anchor invariant gives the unique position::

        pos = scene_anchor − O − R(θ)·(local_anchor − O)

    Pure: no Qt item is touched, so it is safe to call while building an undo
    record.
    """
    origin = new_rect.center()
    angle_rad = math.radians(rotation_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    dx = local_anchor.x() - origin.x()
    dy = local_anchor.y() - origin.y()
    rot_dx = dx * cos_a - dy * sin_a
    rot_dy = dx * sin_a + dy * cos_a
    return QPointF(
        scene_anchor.x() - origin.x() - rot_dx,
        scene_anchor.y() - origin.y() - rot_dy,
    )


def scene_point_of(
    local_point: QPointF,
    rect: QRectF,
    pos: QPointF,
    rotation_deg: float,
) -> QPointF:
    """Where ``local_point`` lands in scene space for an item with this geometry.

    The **forward** direction of :func:`anchored_position`'s transform, and its
    exact inverse: ``anchored_position`` answers "what ``pos`` puts this local
    point on that scene point"; this answers "where does this local point go".
    Named as a pair so a caller needing both — pin a corner's pre-drag position,
    then solve for the post-drag ``pos`` — cannot hand-derive one of them under a
    different origin assumption than the other. Doing exactly that is what broke
    the rotated corner drag once already (see ``_move_corner_to``).

    Pure: touches no Qt item, so it is safe to call mid-drag.
    """
    origin = rect.center()
    angle_rad = math.radians(rotation_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    dx = local_point.x() - origin.x()
    dy = local_point.y() - origin.y()
    return QPointF(
        pos.x() + origin.x() + dx * cos_a - dy * sin_a,
        pos.y() + origin.y() + dx * sin_a + dy * cos_a,
    )


def resize_rect_item_keeping_anchor(
    item: QGraphicsItem,
    new_rect: QRectF,
    scene_anchor: QPointF,
    local_anchor: QPointF,
) -> None:
    """Resize a rect-bearing item, keeping ``local_anchor`` pinned to ``scene_anchor``.

    The one rotation-correct "resize about a scene point" primitive (#218). It
    applies ``new_rect``, re-pins the rotation origin to the new rect centre
    (the serializer's invariant ``transformOriginPoint == rect().center()``,
    #219), and sets ``pos`` so that ``local_anchor`` (a point in the new local
    rect) lands exactly on ``scene_anchor`` (a scene point).

    Qt maps a local point ``p`` to scene as ``pos + O + R(θ)·(p − O)`` where
    ``O = transformOriginPoint`` and ``θ = item.rotation()``. Pinning
    ``O = new_rect.center()`` and solving the anchor invariant gives the unique
    position::

        pos = scene_anchor − O − R(θ)·(local_anchor − O)

    For the centre-anchor case (``local_anchor == O``) this collapses to
    ``pos = scene_anchor − O`` — exactly what ``CircleItem.set_radius_centered``
    needs. For an edge/corner-fixed drag, ``scene_anchor`` is the fixed corner's
    pre-resize scene position and ``local_anchor`` is that corner in the new rect.

    Bookkeeping (``_center``/``_radius``, handles, labels) stays with the caller;
    this primitive only touches geometry.
    """
    # Invalidate the OLD (possibly larger) bounding region before the geometry
    # shrinks, else Qt leaves stale pixels — e.g. the spacing-ring "ghost" disc
    # seen when a plant's footprint is dragged smaller (#218 follow-up).
    item.prepareGeometryChange()
    item.setRect(new_rect)  # type: ignore[attr-defined]
    item.setTransformOriginPoint(new_rect.center())
    item.setPos(
        anchored_position(new_rect, item.rotation(), scene_anchor, local_anchor)
    )


def _is_item_fixed(item: "QGraphicsItem") -> bool:
    """Return True if item has a FIXED constraint in the scene's constraint graph."""
    scene = item.scene() if item is not None else None
    if scene is None or not hasattr(scene, "constraint_graph"):
        return False
    item_id = getattr(item, "item_id", None)
    if item_id is None:
        return False
    from open_garden_planner.core.constraints import ConstraintType

    for c in scene.constraint_graph.constraints.values():
        if c.constraint_type == ConstraintType.FIXED and c.anchor_a.item_id == item_id:
            return True
    return False


def _emit_scale_blocked_hint(item: "QGraphicsItem") -> None:
    """Surface a user-visible hint when a scale drag is refused."""
    scene = item.scene() if item is not None else None
    if scene is None:
        return
    msg = QCoreApplication.translate(
        "ResizeHandle", "Scale blocked: item has dimensional constraints"
    )
    for view in scene.views():
        window = view.window()
        status_bar = getattr(window, "statusBar", None)
        if callable(status_bar):
            try:
                status_bar().showMessage(msg, 4000)
                return
            except Exception:
                continue


def _has_blocking_constraints(item: "QGraphicsItem") -> bool:
    """Return True if ``item`` has any constraint that a uniform scale would violate.

    Scale-invariant constraint types (HORIZONTAL, VERTICAL, PARALLEL,
    PERPENDICULAR, EQUAL) are allowed.  Any other constraint — including FIXED,
    EDGE_LENGTH, DISTANCE, ANGLE, SYMMETRY_*, COINCIDENT, POINT_ON_* — blocks
    scaling because the bounding-box resize would silently invalidate it.
    """
    scene = item.scene() if item is not None else None
    if scene is None or not hasattr(scene, "constraint_graph"):
        return False
    item_id = getattr(item, "item_id", None)
    if item_id is None:
        return False
    from open_garden_planner.core.constraints import ConstraintType

    scale_invariant = {
        ConstraintType.HORIZONTAL,
        ConstraintType.VERTICAL,
        ConstraintType.PARALLEL,
        ConstraintType.PERPENDICULAR,
        ConstraintType.EQUAL,
    }
    for c in scene.constraint_graph.constraints.values():
        touches = c.anchor_a.item_id == item_id or c.anchor_b.item_id == item_id
        if not touches:
            continue
        if c.constraint_type not in scale_invariant:
            return True
    return False
