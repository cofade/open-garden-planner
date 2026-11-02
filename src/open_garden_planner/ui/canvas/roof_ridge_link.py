"""The linked ``ROOF_RIDGE`` of a HOUSE — one construction and lookup path.

A HOUSE's ridge is derived geometry: ``core.roof_ridge`` computes its two
endpoints from the outline, and the ridge and its owner name each other in
``metadata`` (``owner_polygon_id`` / ``ridge_item_id``). The polygon tool has
always created it; since #690 a type change into HOUSE does too, through this
module, so both callers produce the identical ridge rather than a second
construction path (the "one canonical path" discipline, §8.19 / ADR-046).
"""

from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints


def outline_polygon(item: QGraphicsItem) -> QPolygonF | None:
    """A HOUSE-capable item's LOCAL outline as a closed polygon.

    ``PolygonItem`` states one directly; a rectangular shape is converted from
    its ``rect()`` (the four corners in the item's own frame). Anything else has
    no outline a ridge can be derived from and returns ``None``.
    """
    polygon = getattr(item, "polygon", None)
    if callable(polygon):
        poly = polygon()
        return QPolygonF(poly) if poly is not None and poly.count() >= 3 else None
    rect = getattr(item, "rect", None)
    if callable(rect):
        box = rect()
        if box.width() <= 0.0 or box.height() <= 0.0:
            return None
        return QPolygonF(
            [box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()]
        )
    return None


def linked_ridge(item: QGraphicsItem) -> QGraphicsItem | None:
    """The live ``ROOF_RIDGE`` this item names, if it still exists and is one."""
    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    ridge_id = metadata.get("ridge_item_id")
    if not ridge_id:
        return None
    scene = item.scene()
    finder = getattr(scene, "find_item_by_id", None)
    if not callable(finder):
        return None
    try:
        ridge = finder(uuid.UUID(str(ridge_id)))
    except (TypeError, ValueError):
        return None
    from open_garden_planner.ui.canvas.items import PolylineItem

    if (
        isinstance(ridge, PolylineItem)
        and getattr(ridge, "object_type", None) == ObjectType.ROOF_RIDGE
    ):
        return ridge
    return None


def build_linked_ridge(
    item: QGraphicsItem, layer_id: uuid.UUID | None
) -> Any | None:
    """Build and cross-link a HOUSE's ridge (not yet added to a scene).

    Endpoints are computed in the item's local frame and mapped through its
    full transform, so a rotated shape gets the ridge along its rotated long
    axis — the same rule ``PolygonItem._update_ridge_on_boundary`` applies.
    """
    polygon = outline_polygon(item)
    owner_id = getattr(item, "item_id", None)
    if polygon is None or owner_id is None or not hasattr(item, "set_metadata"):
        return None
    from open_garden_planner.ui.canvas.items import PolylineItem

    local_1, local_2 = compute_roof_ridge_endpoints(polygon, QPointF(0.0, 0.0))
    p1 = item.mapToScene(local_1)
    p2 = item.mapToScene(local_2)
    ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE, layer_id=layer_id)
    ridge.set_metadata("owner_polygon_id", str(owner_id))
    item.set_metadata("ridge_item_id", str(ridge.item_id))
    return ridge


def remove_linked_ridge(scene: QGraphicsScene, ridge: QGraphicsItem) -> None:
    """Take *ridge* out of the scene without forgetting its metadata links."""
    if ridge.scene() is scene:
        scene.removeItem(ridge)
