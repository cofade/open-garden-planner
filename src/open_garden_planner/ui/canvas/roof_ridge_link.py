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
from PyQt6.QtWidgets import QGraphicsItem

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


def is_owned_ridge(item: QGraphicsItem, candidate: QGraphicsItem | None) -> bool:
    """Whether *candidate* is a ``ROOF_RIDGE`` owned by *item*.

    The reverse ``owner_polygon_id`` is the ownership proof, so a copied or
    stale ``ridge_item_id`` never lets one house adopt another's ridge. A
    MISSING reverse link is tolerated: older and hand-authored plans predate
    it. This is the one predicate every ridge consumer uses (2D lookup, the 3D
    snapshot, the sun/shadow caster), so the rule cannot drift between them.
    """
    from open_garden_planner.ui.canvas.items import PolylineItem

    if not (
        isinstance(candidate, PolylineItem)
        and getattr(candidate, "object_type", None) == ObjectType.ROOF_RIDGE
    ):
        return False
    ridge_meta = getattr(candidate, "metadata", None)
    owner = ridge_meta.get("owner_polygon_id") if isinstance(ridge_meta, dict) else None
    return not owner or str(owner) == str(getattr(item, "item_id", ""))


def linked_ridge(item: QGraphicsItem) -> QGraphicsItem | None:
    """The live ``ROOF_RIDGE`` this item names, if it still exists and is one."""
    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    ridge_id = metadata.get("ridge_item_id")
    if not ridge_id:
        return None
    scene = item.scene()
    if scene is None:
        return None
    try:
        wanted = uuid.UUID(str(ridge_id))
    except (TypeError, ValueError):
        return None
    finder = getattr(scene, "find_item_by_id", None)
    if callable(finder):
        ridge = finder(wanted)
    else:
        # A plain QGraphicsScene (unit tests, isolated probes) has no index;
        # the canonical lookup still has to work there.
        ridge = next(
            (i for i in scene.items() if getattr(i, "item_id", None) == wanted),
            None,
        )
    return ridge if is_owned_ridge(item, ridge) else None


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


def linked_ridges_under(item: QGraphicsItem) -> list[QGraphicsItem]:
    """Every live linked ridge of a HOUSE in *item*'s own child tree.

    A group is not a HOUSE: deleting the group only names the group, so a
    deletion path that inspects the selected wrapper alone leaves a nested
    house's free-standing ridge behind. The walk is shared by the GUI delete
    (``CanvasView._delete_selected_items``) and the Agent API
    (``_do_agent_delete_object``) so the two cannot drift.
    """
    from open_garden_planner.ui.canvas.items.group_item import selection_tree

    ridges: list[QGraphicsItem] = []
    for candidate in selection_tree([item]):
        if getattr(candidate, "object_type", None) == ObjectType.HOUSE:
            ridge = linked_ridge(candidate)
            if ridge is not None and ridge not in ridges:
                ridges.append(ridge)
    return ridges


def update_house_ridges_under(item: QGraphicsItem) -> None:
    """Re-derive the ridge of every HOUSE inside *item*'s child tree.

    A group move/rotate changes each child's SCENE transform without changing
    its local ``pos()``, so a HOUSE nested in a moved group would otherwise
    leave its free-standing ridge behind (PF-CAN-34). Called from
    ``GroupItem.itemChange`` for position/transform changes.
    """
    for child in item.childItems():
        if getattr(child, "object_type", None) == ObjectType.HOUSE:
            update_linked_ridge(child)
        update_house_ridges_under(child)


def update_linked_ridge(item: QGraphicsItem) -> None:
    """Re-derive a HOUSE's linked ridge from its current outline and transform.

    The ridge is *derived* geometry (ADR-046): recomputing it from the item is
    self-healing and undo-safe, and one function serves every item kind that can
    be a HOUSE (a polygon and a converted rectangle) instead of one method per
    class. A no-op when the item has no live linked ridge.
    """
    from open_garden_planner.ui.canvas.items import PolylineItem

    ridge = linked_ridge(item)
    if not isinstance(ridge, PolylineItem):
        return
    polygon = outline_polygon(item)
    if polygon is None:
        return
    local_1, local_2 = compute_roof_ridge_endpoints(polygon, QPointF(0.0, 0.0))
    new_points = [
        ridge.mapFromScene(item.mapToScene(local_1)),
        ridge.mapFromScene(item.mapToScene(local_2)),
    ]
    ridge._points = new_points
    ridge._rebuild_path()
    if getattr(ridge, "is_vertex_edit_mode", False):
        ridge._update_vertex_handles()
    ridge._position_label()
