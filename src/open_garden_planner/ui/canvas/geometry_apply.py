"""The canonical geometry-apply path for rect-backed canvas items (US-D2.2).

Every resize in this app funnels through :func:`apply_rect_like_geometry` and
the builders beside it. Before US-D2.2 each caller — the three numeric-entry
branches in ``properties_panel`` and the drag-release handler on each item
class — carried its own local ``apply_func`` closure for
:class:`~open_garden_planner.core.commands.ResizeItemCommand`, and the copies
had **drifted**: the drag-release closures re-pin ``transformOriginPoint`` onto
the new rect centre (the #218 fix), while the properties-panel closures never
did. A rotated circle resized from the panel therefore jumped — measurably
73.2 cm for a 30 degrees rotation and a 50 to 100 cm radius change — and at 0
degrees the drift is exactly zero, which is why it survived so long. See
``docs/11-risks-and-technical-debt/`` section 11.4.

Adding the Agent API's ``resize_object`` (US-D2.2) would have made that a
*third* copy, so the copies were collapsed instead: this module holds the one
apply function and the one anchor policy, and the panel, the drag handles and
the agent all call it. A regression here is a regression for all three, which
is the point.

Qt-touching and **main-thread only** — the Agent API reaches it through
``MainThreadBridge``, never from the server thread.

Geometry dicts
--------------
One shape, used by every caller and stored in the undo stack::

    {"rect_x", "rect_y", "width", "height", "pos_x", "pos_y"}

plus, for :class:`~open_garden_planner.ui.canvas.items.CircleItem` only, the
bookkeeping the class keeps alongside its rect::

    {"center_x", "center_y", "radius"}

The dict is a *complete* description of the item's geometry, because
``ResizeItemCommand`` replays it in both directions: ``execute`` applies the
new dict and ``undo`` applies the old one through the same function.

Anchor policy
-------------
Two policies, both expressed through the same builder:

* **centre-preserving** (``keep_center=True``) — the object's scene centre is
  invariant. This is what the Agent API uses for every type, because
  ``create_object`` and every read tool speak in centres, so it is the only
  rule an agent can reason about without knowing an item's internal anchor.
  It is also what the panel already does for circles.
* **anchor-preserving** (``keep_center=False``) — ``pos`` and the local rect
  origin are left alone, so the item grows right/down in item coordinates.
  This is the panel's long-standing behaviour for rectangles and ellipses and
  is preserved exactly.

Both go through :func:`~open_garden_planner.ui.canvas.items.resize_handle.anchored_position`,
the single solved form of Qt's rotation transform, so neither policy can drift
from the other under rotation.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.ui.canvas.items.resize_handle import anchored_position

__all__ = [
    "apply_rect_like_geometry",
    "apply_rotation",
    "build_circle_resize",
    "build_ellipse_resize",
    "build_rect_resize",
    "capture_rect_like_geometry",
    "is_resizable_rect_like",
]


def is_resizable_rect_like(item: QGraphicsItem) -> bool:
    """Whether ``item`` is a rect-backed item this module can resize.

    Deliberately a duck-type check on ``rect()``/``setRect`` rather than an
    isinstance tuple: ``CircleItem``/``RectangleItem``/``EllipseItem`` are the
    current members, but the test is about the *capability* the apply function
    needs, so a future rect-backed item works without editing this predicate.
    Polygons and polylines fail it — they are vertex-backed and belong to
    US-D2.6's vertex tools, not here.
    """
    return (
        hasattr(item, "rect")
        and hasattr(item, "setRect")
        and callable(getattr(item, "setRect", None))
    )


def _is_circle_like(item: QGraphicsItem) -> bool:
    """Whether ``item`` keeps ``_center``/``_radius`` beside its rect."""
    return hasattr(item, "_center") and hasattr(item, "_radius")


def capture_rect_like_geometry(item: QGraphicsItem) -> dict[str, Any]:
    """Snapshot ``item``'s current geometry in the canonical dict shape.

    Used for the ``old_geometry`` half of every ``ResizeItemCommand`` built
    here, so undo restores precisely what was there — including a circle's
    ``_center``/``_radius`` bookkeeping.
    """
    rect: QRectF = item.rect()  # type: ignore[attr-defined]
    pos = item.pos()
    geometry: dict[str, Any] = {
        "rect_x": rect.x(),
        "rect_y": rect.y(),
        "width": rect.width(),
        "height": rect.height(),
        "pos_x": pos.x(),
        "pos_y": pos.y(),
    }
    if _is_circle_like(item):
        center: QPointF = item._center  # type: ignore[attr-defined]
        geometry["center_x"] = center.x()
        geometry["center_y"] = center.y()
        geometry["radius"] = item._radius  # type: ignore[attr-defined]
    return geometry


def apply_rect_like_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
    """Apply a canonical geometry dict to a rect-backed item.

    **This is the ``apply_func`` every ``ResizeItemCommand`` for a rect-backed
    item must be given** — from the properties panel, from a drag release, and
    from the Agent API. It is called with the *new* dict on execute/redo and
    the *old* dict on undo, so it never reads the item's current state.

    Order matters and is load-bearing:

    1. ``prepareGeometryChange()`` **first**, to invalidate the old (possibly
       larger) bounding region before the geometry shrinks — otherwise Qt
       leaves stale pixels, e.g. the spacing-ring "ghost" disc behind a plant
       whose footprint was made smaller (#218 follow-up).
    2. ``setRect`` — the geometry itself.
    3. ``setTransformOriginPoint(rect().center())`` — the serializer invariant
       ``transformOriginPoint == rect().center()`` (#219). Skipping this is the
       panel bug this module exists to kill: a rotated item then pivots about a
       point that is no longer its centre, so it lurches away on the next
       repaint and saves a displaced position.
    4. ``setPos`` — placement, already solved by the builder for the requested
       anchor policy.
    """
    item.prepareGeometryChange()
    item.setRect(  # type: ignore[attr-defined]
        geom["rect_x"], geom["rect_y"], geom["width"], geom["height"]
    )
    if _is_circle_like(item) and "radius" in geom:
        item._center = QPointF(geom["center_x"], geom["center_y"])  # type: ignore[attr-defined]
        item._radius = geom["radius"]  # type: ignore[attr-defined]
    item.setTransformOriginPoint(item.rect().center())  # type: ignore[attr-defined]
    item.setPos(geom["pos_x"], geom["pos_y"])
    if hasattr(item, "update_resize_handles"):
        item.update_resize_handles()  # type: ignore[attr-defined]
    if hasattr(item, "_position_label"):
        item._position_label()  # type: ignore[attr-defined]
    if hasattr(item, "_update_circle_annotations"):
        item._update_circle_annotations()  # type: ignore[attr-defined]


def apply_rotation(item: QGraphicsItem, angle: float) -> None:
    """Apply a rotation angle to ``item`` — the canonical rotate ``apply_func``.

    Thin by design: ``RotationHandleMixin._apply_rotation`` is already the one
    implementation (it pins the pivot to ``rect().center()`` per #219 and
    refreshes the handles), and ``PolygonItem`` overrides it to keep an
    attached roof ridge on the boundary. Every per-item ``apply_rotation``
    closure in the codebase was already just this call; naming it here gives
    ``RotateItemCommand`` callers — including the Agent API — one importable
    function instead of a closure each.
    """
    item._apply_rotation(angle)  # type: ignore[attr-defined]


def _resize_geometry(
    item: QGraphicsItem,
    new_rect: QRectF,
    *,
    keep_center: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build ``(old, new)`` geometry dicts for a resize of ``item``.

    ``keep_center`` selects the anchor policy documented in the module header.
    Both policies are solved with :func:`anchored_position`, so a rotated item
    lands correctly under either.

    Whether the circle bookkeeping (``center_x``/``center_y``/``radius``) is
    emitted is decided **from the item**, never from the caller. Letting a
    caller choose would allow `build_rect_resize(a_circle, …)` to produce a
    ``new`` dict without those keys while ``capture_rect_like_geometry`` put
    them in ``old`` — leaving ``_radius`` stale after the resize and silently
    restoring it on undo. Deriving it here makes that shape unrepresentable.
    """
    old_geometry = capture_rect_like_geometry(item)
    circle_bookkeeping = _is_circle_like(item)
    rotation = float(item.rotation())

    if keep_center:
        # Pin the item's CURRENT scene centre; the new rect's centre goes there.
        scene_anchor = item.mapToScene(item.rect().center())  # type: ignore[attr-defined]
        local_anchor = new_rect.center()
    else:
        # Pin the item's current top-left in scene space to the new rect's
        # top-left, which leaves pos untouched at rotation 0 and keeps the
        # rotated case coherent instead of accidentally correct.
        old_rect: QRectF = item.rect()  # type: ignore[attr-defined]
        scene_anchor = item.mapToScene(old_rect.topLeft())  # type: ignore[attr-defined]
        local_anchor = new_rect.topLeft()

    pos = anchored_position(new_rect, rotation, scene_anchor, local_anchor)

    new_geometry: dict[str, Any] = {
        "rect_x": new_rect.x(),
        "rect_y": new_rect.y(),
        "width": new_rect.width(),
        "height": new_rect.height(),
        "pos_x": pos.x(),
        "pos_y": pos.y(),
    }
    if circle_bookkeeping:
        center = new_rect.center()
        new_geometry["center_x"] = center.x()
        new_geometry["center_y"] = center.y()
        new_geometry["radius"] = new_rect.width() / 2.0
    return old_geometry, new_geometry


def build_circle_resize(
    item: QGraphicsItem, new_diameter: float, *, keep_center: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(old, new)`` geometry for resizing a circle to ``new_diameter`` cm.

    ``keep_center`` defaults to ``True`` because that is what both existing
    callers already want: the properties panel explicitly recomputes ``pos`` to
    hold the centre, and the Agent API's ``resize_object`` promises centre
    preservation for every type.
    """
    new_rect = QRectF(0.0, 0.0, new_diameter, new_diameter)
    return _resize_geometry(item, new_rect, keep_center=keep_center)


def build_rect_resize(
    item: QGraphicsItem,
    new_width: float,
    new_height: float,
    *,
    keep_center: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(old, new)`` geometry for resizing a rectangle to ``new_width`` x ``new_height``.

    ``keep_center`` defaults to ``False`` to preserve the properties panel's
    long-standing behaviour (the rectangle grows right/down from its existing
    local origin). The Agent API passes ``True``.
    """
    old_rect: QRectF = item.rect()  # type: ignore[attr-defined]
    new_rect = QRectF(old_rect.x(), old_rect.y(), new_width, new_height)
    return _resize_geometry(item, new_rect, keep_center=keep_center)


def build_ellipse_resize(
    item: QGraphicsItem,
    new_width: float,
    new_height: float,
    *,
    keep_center: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(old, new)`` geometry for resizing an ellipse to full extents in cm.

    Note the units: the properties panel's spin boxes hold **semi-axes**, so it
    passes ``rx * 2`` / ``ry * 2``. Everything stored and everything the Agent
    API exchanges is a full extent, matching ``width``/``height`` everywhere
    else.
    """
    return build_rect_resize(item, new_width, new_height, keep_center=keep_center)
