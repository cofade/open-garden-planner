"""The additive metadata contract of a reference point (#666, ADR-080).

A reference point is a survey stake, fence post, datum or measurement reference:
a durable point object whose exact centre is the snap/measure point. It is
stored as the existing ``GENERIC_CIRCLE`` record with these additive
``metadata`` keys, so an older version reads it as a small circle and no
``FILE_VERSION`` bump is needed. This module is Qt-free: it inspects the
metadata dict and the scene, never an item class.

Key names are stable; values are plain JSON scalars:

``reference_point``
    ``True`` marks the item as a reference point.
``reference_point_parent_id``
    UUID string of the object whose outline the point is attached to, if any.
``reference_point_on_contour``
    ``True`` keeps the point on the parent's outline while it is moved.
``reference_point_size_mode``
    ``"plan_cm"`` (default; the symbol scales with the plan) or ``"screen_px"``
    (the symbol keeps its size on screen).
``reference_point_size``
    The symbol's diameter in the mode's unit (default 6 cm / 16 px).
``reference_point_color``
    ``#aarrggbb`` stroke colour (default the survey teal).
``reference_point_stroke_width``
    Cosmetic stroke width in screen pixels (default 1.8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QGraphicsItem

MARKER = "reference_point"
PARENT_ID = "reference_point_parent_id"
ON_CONTOUR = "reference_point_on_contour"
SIZE_MODE = "reference_point_size_mode"
SIZE = "reference_point_size"
COLOR = "reference_point_color"
STROKE_WIDTH = "reference_point_stroke_width"

SIZE_MODE_PLAN = "plan_cm"
SIZE_MODE_SCREEN = "screen_px"
DEFAULT_SIZE_CM = 6.0
DEFAULT_SIZE_PX = 16.0
DEFAULT_COLOR = "#168c9e"
DEFAULT_STROKE_WIDTH = 1.8

MIN_SIZE = 2.0
MAX_SIZE_PLAN = 100.0
MAX_SIZE_SCREEN = 64.0


def is_reference_point(item_or_metadata: Any) -> bool:
    """Whether an item or a metadata dict describes a reference point."""
    metadata = getattr(item_or_metadata, "metadata", item_or_metadata)
    return isinstance(metadata, dict) and metadata.get(MARKER) is True


def is_attached_reference_point(item: QGraphicsItem | None) -> bool:
    """Whether a reference point currently has a live binding parent."""
    return is_reference_point(item) and getattr(item, "binding_parent", None) is not None


def parent_id(metadata: dict[str, Any] | Any) -> UUID | None:
    """The attached parent's id, or ``None`` for an independent point."""
    raw = metadata.get(PARENT_ID) if isinstance(metadata, dict) else None
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def on_contour(metadata: dict[str, Any] | Any) -> bool:
    """Whether the point must stay on its parent's outline."""
    return bool(isinstance(metadata, dict) and metadata.get(ON_CONTOUR) is True)


def size_mode(metadata: dict[str, Any] | Any) -> str:
    """``"plan_cm"`` or ``"screen_px"``; unknown values fall back to plan cm."""
    if isinstance(metadata, dict) and metadata.get(SIZE_MODE) == SIZE_MODE_SCREEN:
        return SIZE_MODE_SCREEN
    return SIZE_MODE_PLAN


def size_value(metadata: dict[str, Any] | Any) -> float:
    """The symbol's diameter in the mode's unit, clamped to a usable range."""
    mode = size_mode(metadata)
    default = DEFAULT_SIZE_PX if mode == SIZE_MODE_SCREEN else DEFAULT_SIZE_CM
    raw = metadata.get(SIZE) if isinstance(metadata, dict) else None
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    upper = MAX_SIZE_SCREEN if mode == SIZE_MODE_SCREEN else MAX_SIZE_PLAN
    return min(max(value, MIN_SIZE), upper)


def radius_cm(metadata: dict[str, Any] | Any) -> float:
    """The stored circle radius: half the size, in the mode's own unit.

    A screen-sized symbol stores its pixel diameter; older versions still read
    it as a circle of that radius in centimetres, which is documented and
    harmless. The exact centre is the item's position in both modes.
    """
    return size_value(metadata) / 2.0


def color(metadata: dict[str, Any] | Any) -> str:
    raw = metadata.get(COLOR) if isinstance(metadata, dict) else None
    return raw if isinstance(raw, str) and raw else DEFAULT_COLOR


def stroke_width(metadata: dict[str, Any] | Any) -> float:
    raw = metadata.get(STROKE_WIDTH) if isinstance(metadata, dict) else None
    try:
        return min(max(float(raw), 0.5), 8.0) if raw is not None else DEFAULT_STROKE_WIDTH
    except (TypeError, ValueError):
        return DEFAULT_STROKE_WIDTH


def build_metadata(
    *,
    parent: UUID | None = None,
    on_contour_value: bool = False,
    mode: str = SIZE_MODE_PLAN,
    size: float | None = None,
    colour: str = DEFAULT_COLOR,
    stroke: float = DEFAULT_STROKE_WIDTH,
) -> dict[str, Any]:
    """Build the complete metadata dict for a new or edited point."""
    mode = SIZE_MODE_SCREEN if mode == SIZE_MODE_SCREEN else SIZE_MODE_PLAN
    metadata: dict[str, Any] = {
        MARKER: True,
        SIZE_MODE: mode,
        SIZE: size if size is not None else (
            DEFAULT_SIZE_PX if mode == SIZE_MODE_SCREEN else DEFAULT_SIZE_CM
        ),
        COLOR: colour,
        STROKE_WIDTH: stroke,
        ON_CONTOUR: bool(on_contour_value and parent is not None),
    }
    if parent is not None:
        metadata[PARENT_ID] = str(parent)
    return metadata


def attached_to(scene: Any, parent: Any) -> list[Any]:
    """Reference points attached to *parent*, in the same scene."""
    if scene is None or parent is None:
        return []
    try:
        parent_uuid = parent.item_id
    except AttributeError:
        return []
    points: list[Any] = []
    for item in scene.items():
        metadata = getattr(item, "metadata", None)
        if is_reference_point(metadata) and parent_id(metadata) == parent_uuid:
            points.append(item)
    return points


def attached_to_any(scene: Any, parents: list[Any]) -> list[Any]:
    """Reference points attached to any of *parents*, without duplicates."""
    found: list[Any] = []
    seen: set[int] = set()
    for parent in parents:
        for point in attached_to(scene, parent):
            if id(point) not in seen:
                seen.add(id(point))
                found.append(point)
    return found


def constraint_pins(items: dict[UUID, QGraphicsItem]) -> set[UUID]:
    """Keep datums stationary during a solve, along with participating carriers.

    A solver cannot change a relative distance by moving both endpoints
    together. Do not solve against a stationary datum then carry it by the
    very same move.
    """
    pinned = set()
    for item_id, item in items.items():
        if not is_reference_point(item):
            continue
        pinned.add(item_id)
        carrier = item.binding_parent  # type: ignore[attr-defined]
        while carrier is not None:
            if carrier.item_id in items:
                pinned.add(carrier.item_id)
            carrier = carrier.parentItem()
    return pinned


def carried_by_moved(
    scene: Any, moved_items: list[Any], *, exclude_moved: bool = True
) -> list[tuple[Any, Any]]:
    """``(point, carrier)`` pairs a translation must move outside Qt's own move.

    A moved group carries the points bound to its descendants, because Qt moves
    the descendants with the group but the points are top-level items. A point
    that already moves with a Qt ancestor is not moved again. ``exclude_moved`` drops points that are in ``moved_items`` (the
    expansion caller); a command asks for them so it can translate the point
    exactly instead of projecting it onto the contour.
    """
    if scene is None:
        return []
    points_by_parent = attached_by_parent(scene)
    moved = set(moved_items)
    graph = getattr(scene, "constraint_graph", None)
    fixed = graph.fixed_item_ids() if graph is not None else set()
    get_layer = getattr(scene, "get_layer_by_id", None)
    seen: set[int] = set()
    found: list[tuple[Any, Any]] = []
    for carrier in moved_items:
        stack = [carrier]
        while stack:
            item = stack.pop()
            item_id = getattr(item, "item_id", None)
            if isinstance(item_id, UUID):
                for point in points_by_parent.get(item_id, ()):
                    if exclude_moved and point in moved:
                        continue
                    layer = get_layer(point.layer_id) if callable(get_layer) and point.layer_id else None
                    if point.item_id in fixed or (layer is not None and layer.locked):
                        continue
                    ancestor = point.parentItem()
                    while ancestor is not None and ancestor not in moved:
                        ancestor = ancestor.parentItem()
                    if ancestor is not None:
                        continue
                    if id(point) in seen:
                        continue
                    seen.add(id(point))
                    found.append((point, carrier))
            stack.extend(item.childItems())
    return found


def carried_delta(item: QGraphicsItem, carrier: QGraphicsItem, delta: QPointF) -> QPointF:
    """Convert a carrier's local translation into the datum's Qt parent frame."""
    source = carrier.parentItem()
    target = item.parentItem()
    if source is target:
        return delta
    if source is not None:
        origin = carrier.pos()
        delta = source.mapToScene(origin + delta) - source.mapToScene(origin)
    if target is not None:
        origin = item.scenePos()
        delta = target.mapFromScene(origin + delta) - target.mapFromScene(origin)
    return delta


def attached_by_parent(scene: Any) -> dict[UUID, list[Any]]:
    """One scene scan: parent id -> its bound reference points.

    A move command can carry many items; rebuilding ``attached_to`` per item
    would be O(items x scene). This map is built once per command instead.
    """
    mapping: dict[UUID, list[Any]] = {}
    if scene is None:
        return mapping
    for item in scene.items():
        metadata = getattr(item, "metadata", None)
        if not is_reference_point(metadata):
            continue
        pid = parent_id(metadata)
        if pid is not None:
            mapping.setdefault(pid, []).append(item)
    return mapping


