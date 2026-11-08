"""The linked ``ROOF_RIDGE`` of a ridge-bearing building — one construction and
lookup path.

A ridge-bearing building's ridge is derived geometry: ``core.roof_ridge`` computes
its two endpoints from the outline, and the ridge and its owner name each other in
``metadata`` (``owner_polygon_id`` / ``ridge_item_id``). A HOUSE has had one since
the start; since #768 a GREENHOUSE is a first-class parametric building with the
same ridge, so every path here asks the one predicate
(``core.object_types.is_ridge_bearing_type``) instead of naming HOUSE. The polygon
tool creates the ridge on draw and a type change into a ridge-bearing type does
too, through this module, so both callers produce the identical ridge rather than
a second construction path (the "one canonical path" discipline, §8.19 / ADR-046).

A greenhouse's ridge is anodised aluminium (``GREENHOUSE_RIDGE_COLOUR``), not a
house's dark-brown timber cap; the finish is applied here when the ridge is built
and re-applied when the owner changes type. Ridge metadata is additive: a ridge
without ``ridge_finish`` is a house's brown one, so old plans load unchanged.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Final

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.greenhouse import (
    RIDGE_ALUMINIUM_HEX,
    RIDGE_ALUMINIUM_SHADOW_HEX,
)
from open_garden_planner.core.object_types import ObjectType, is_ridge_bearing_type
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints

#: ``metadata`` key saying which finish a ridge wears. Absent: a house's brown.
RIDGE_FINISH_KEY: Final = "ridge_finish"
#: A greenhouse's anodised aluminium ridge (#768): body and shadow tone.
GREENHOUSE_RIDGE_COLOUR: Final = QColor(RIDGE_ALUMINIUM_HEX)
GREENHOUSE_RIDGE_SHADOW: Final = QColor(RIDGE_ALUMINIUM_SHADOW_HEX)


def outline_polygon(item: QGraphicsItem) -> QPolygonF | None:
    """A ridge-capable item's LOCAL outline as a closed polygon.

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


def ridge_points_local(
    item: QGraphicsItem, ridge: QGraphicsItem | None
) -> tuple[QPointF, QPointF] | None:
    """A linked ridge's two ends in *item*'s LOCAL frame (for its 2D paint).

    The ridge stores its points in SCENE space (since #364), so both ends are
    mapped through the ridge's own transform and then the host's — never a second
    ``mapToScene`` on the host, which would rotate the axis twice (§11.4).
    """
    if ridge is None:
        return None
    points = getattr(ridge, "points", None)
    if not isinstance(points, list) or len(points) < 2:
        return None
    first = item.mapFromScene(ridge.mapToScene(points[0]))
    second = item.mapFromScene(ridge.mapToScene(points[-1]))
    if not (math.isfinite(first.x() + first.y() + second.x() + second.y())):
        return None
    return first, second


def apply_ridge_look(owner: QGraphicsItem, ridge: QGraphicsItem | None) -> None:
    """Give *ridge* the finish its owner's type asks for (#768).

    A greenhouse's ridge is anodised aluminium; a house's stays the brown
    ``ObjectType.ROOF_RIDGE`` style. Called when the ridge is built and when its
    owner changes type, never on load: an existing plan keeps the colour it was
    saved with and only the additive ``ridge_finish`` tells the canvas painter
    which palette to use.
    """
    if ridge is None:
        return
    greenhouse = getattr(owner, "object_type", None) is ObjectType.GREENHOUSE
    metadata = getattr(ridge, "metadata", None)
    if isinstance(metadata, dict):
        if greenhouse:
            metadata[RIDGE_FINISH_KEY] = "aluminium"
        else:
            metadata.pop(RIDGE_FINISH_KEY, None)
    ridge.stroke_color = (  # type: ignore[attr-defined]
        QColor(GREENHOUSE_RIDGE_COLOUR) if greenhouse else None
    )
    setup = getattr(ridge, "_setup_styling", None)
    if callable(setup):
        setup()
    update = getattr(ridge, "update", None)
    if callable(update):
        update()


def build_linked_ridge(
    item: QGraphicsItem, layer_id: uuid.UUID | None
) -> Any | None:
    """Build and cross-link a ridge-bearing building's ridge (not yet in a scene).

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
    apply_ridge_look(item, ridge)
    return ridge


def build_copy_ridges(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """Build a fresh linked ROOF_RIDGE for every copied ridge-bearing building
    under *items* (issue #712; #768 adds GREENHOUSE).

    Walks the selection tree of each item (so nested houses inside groups
    are included). Clears any inherited ``ridge_item_id`` on copied buildings,
    builds a fresh ridge, sets the two-sided link, and returns all newly
    built ridges.
    """
    from open_garden_planner.ui.canvas.items.group_item import selection_tree

    new_ridges: list[QGraphicsItem] = []
    for item in selection_tree(items):
        if not is_ridge_bearing_type(getattr(item, "object_type", None)):
            continue
        meta = getattr(item, "metadata", None)
        if isinstance(meta, dict):
            meta.pop("ridge_item_id", None)
        ridge = build_linked_ridge(item, getattr(item, "layer_id", None))
        if ridge is not None:
            new_ridges.append(ridge)
    return new_ridges


def linked_ridges_under(item: QGraphicsItem) -> list[QGraphicsItem]:
    """Every live linked ridge of a ridge-bearing building in *item*'s child tree.

    A group is not a building: deleting the group only names the group, so a
    deletion path that inspects the selected wrapper alone leaves a nested
    house's free-standing ridge behind. The walk is shared by the GUI delete
    (``CanvasView._delete_selected_items``) and the Agent API
    (``_do_agent_delete_object``) so the two cannot drift.
    """
    from open_garden_planner.ui.canvas.items.group_item import selection_tree

    ridges: list[QGraphicsItem] = []
    for candidate in selection_tree([item]):
        if is_ridge_bearing_type(getattr(candidate, "object_type", None)):
            ridge = linked_ridge(candidate)
            if ridge is not None and ridge not in ridges:
                ridges.append(ridge)
    return ridges


def update_house_ridges_under(item: QGraphicsItem) -> None:
    """Re-derive the ridge of every ridge-bearing building inside *item*'s child tree.

    A group move/rotate changes each child's SCENE transform without changing
    its local ``pos()``, so a HOUSE (or GREENHOUSE, #768) nested in a moved group
    would otherwise leave its free-standing ridge behind (PF-CAN-34). Called from
    ``GroupItem.itemChange`` for position/transform changes.
    """
    for child in item.childItems():
        if is_ridge_bearing_type(getattr(child, "object_type", None)):
            update_linked_ridge(child)
        update_house_ridges_under(child)


def update_linked_ridge(item: QGraphicsItem) -> None:
    """Re-derive a ridge-bearing building's linked ridge from its outline/transform.

    The ridge is *derived* geometry (ADR-046): recomputing it from the item is
    self-healing and undo-safe, and one function serves every item kind that can
    bear a ridge (a polygon and a converted rectangle) instead of one method per
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
