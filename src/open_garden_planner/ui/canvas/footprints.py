"""Which ground does a canvas item cover? — the ONE footprint extraction.

Public home (Phase 17 L1.1, #385, ADR-059) of the helpers that used to be
private to ``sun_shadow_controller``: the shadow overlay (US-E3), the
hours-of-sun heatmap (US-E4), the Qt 3D view (US-E6) and the Qt Quick 3D
pipeline all ask this module, so a 3D solid can never disagree with its 2D
shadow. ``tests/integration/test_footprints_golden.py`` pins every number
``item_footprints`` returns against a fixture generated before the move.

Two views of one enumeration:

- ``item_outline(item, at_date)`` — the item's outline in its OWN coordinates,
  as plain floats: which vertices, which centre, which radius or stroke width.
  The 3D snapshot builds item-local records from it.
- ``item_footprints(item, at_date)`` — the same vertices in SCENE centimetres
  (+x = East, +y = North, ADR-002; no Y-flip here, §8.20). Rotation and position
  are Qt's answer (``mapToScene``), never a re-derivation from ``pos()`` /
  ``rotation()`` / ``transformOriginPoint()`` (the #218/#219 lessons).

Both come from ``item_outline``, so there is one place that decides what an
item's footprint is.

And one place that decides how high an item STANDS (Phase 17 L1.6, ADR-037
addendum): ``item_base_cm`` — the soil of its parent bed or container, when the
item is linked to that parent AND its centre is inside the parent's shape. The
2D shadow casters (overlay and heatmap) and the 3D records both ask it, so a
plant's shadow and its 3D solid start at the same height.

And one point-in-bed PREDICATE, ``shape_contains``, asked with one of two points:

- the LINK decisions (auto-parenting on creation, bulk create and paste, the
  re-link after a drag, the agent's re-link after ``move_object`` or
  ``set_object_position``, and its ``link_is_geometric``) ask it with ``bed_membership_point`` — the centre of the
  item's ``boundingRect()``, exactly as they always did (``centre_is_inside``);
- the LIFT (``item_base_cm``) asks it with ``standing_point`` — the item's stable
  geometric centre, the origin of its footprint and of its 3D record.

The two points differ while a plant shows its antagonist badge: the badge grows
the bounding rect towards +x / +y by ``0.3 * min(0.45 * radius, cap)``, which
moves its centre by up to 1.8 cm along EACH axis — 2.55 cm in all, which is the
margin against an edge at 45°. A link decision made in that state can therefore
differ from the lift for a plant whose centre is within that margin of
its bed's edge — the link is bookkeeping and keeps its shipped point; where a
solid STANDS must not change when a warning is painted over it.

This module is collecting jobs — footprints, the base rule, the app's
point-in-bed test, with ``core/commands.py`` importing from ``ui/`` lazily for
the last one. A known smell (§8.29.6), not restructured in L1.6.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from open_garden_planner.core.object_height import is_solid_soil_parent, standing_base_cm
from open_garden_planner.core.shadow_geometry import (
    Point,
    Polygon,
    circle_footprint,
    polyline_footprint,
)

from .items.circle_item import CircleItem
from .items.ellipse_item import EllipseItem
from .items.polygon_item import PolygonItem
from .items.polyline_item import PolylineItem
from .items.rectangle_item import RectangleItem

#: Vertices of a polygonalised ellipse (a circle uses ``circle_footprint``'s
#: default, the same number).
ELLIPSE_SEGMENTS = 24

#: ``ItemOutline.shape`` values — the 3D record's ``SHAPES`` (pinned equal by a test).
OUTLINE_CIRCLE = "circle"
OUTLINE_ELLIPSE = "ellipse"
OUTLINE_RECTANGLE = "rectangle"
OUTLINE_POLYGON = "polygon"
OUTLINE_POLYLINE = "polyline"
OUTLINE_SHAPES: tuple[str, ...] = (
    OUTLINE_CIRCLE, OUTLINE_ELLIPSE, OUTLINE_RECTANGLE, OUTLINE_POLYGON, OUTLINE_POLYLINE,
)


@dataclass(frozen=True, slots=True)
class ItemOutline:
    """One item's footprint source in ITEM coordinates (centimetres, plain floats).

    ``shape``: one of ``OUTLINE_SHAPES``. ``anchor``: the item-coordinate point
    the item is centred on — the circle's centre, an ellipse's or rectangle's
    ``rect().center()`` (the geometric centre, never the decoration-expanded
    ``boundingRect()``: #219), the centre of the vertex bounding box of a
    polygon or polyline. ``points``: the outline vertices — an ellipse's
    24-gon, a rectangle's four corners, a polygon's vertices, a polyline's
    CENTRE LINE; empty for a circle, which is ``anchor`` + ``radius_cm`` (a
    plant's canopy at ``at_date``). ``width_cm``: a polyline's stroke width.
    """

    shape: str
    anchor: Point
    points: tuple[Point, ...] = ()
    radius_cm: float | None = None
    width_cm: float | None = None


def plant_canopy_radius_cm(item: Any, at_date: date | None) -> float | None:
    """The plant's measured/projected canopy RADIUS in cm, else None.

    Absolute, not a scale of the drawn circle — deliberately mirroring the
    height rule so both measured fields mean literal centimetres: type a
    100 cm spread and the shadow canopy is 100 cm wide. A proportional
    scale was wrong on two counts: the drawn circle is only the mature
    canopy when a species was applied to an EXISTING plant (#213), whereas
    the gallery drop uses a fixed 200/100/60 cm default, and clamping the
    scale to ≤1 capped canopy growth at the drawn size so a plant could
    never grow past its placeholder circle.

    None means "no measurement" — callers keep the drawn radius. Display
    only; the stored item geometry is never touched (#218/#219).
    """
    from open_garden_planner.core.growth_model import (
        current_spread_from_metadata,
        effective_current_spread_cm,
        grown_spread_cm,
    )

    metadata = getattr(item, "metadata", None)
    species = (metadata or {}).get("plant_species")
    if at_date is not None and isinstance(species, dict):
        object_type = getattr(item, "object_type", None)
        grown = grown_spread_cm(
            species, metadata, at_date, getattr(object_type, "name", "")
        )
        if grown is not None:
            return grown / 2.0
    # Works with no species attached too (an unknown/custom name is a
    # supported state) — same rule as the height resolver. With a species,
    # a measured HEIGHT alone also implies a spread, so a plant measured in
    # one dimension does not render as a pancake.
    current = (
        effective_current_spread_cm(species, metadata)
        if isinstance(species, dict)
        else current_spread_from_metadata(metadata)
    )
    if current is not None:
        return current / 2.0
    return None


class ItemLookup:
    """A scene's items by id, built on first use — and, for the walk it serves,
    each soil parent's shape.

    One per walk over ``scene.items()``: most plans have few parented items, and
    a walk that meets none never pays for the dictionary. NEVER kept between
    walks: the shapes it holds are the items' shapes at the time of the walk, and
    a lookup that outlives an edit answers from the old ones (a bed shrunk away
    from its plant still "contains" it). Construct one as a local of the walk and
    let it die there — a test reads the source and fails otherwise: in the
    application the name ``ItemLookup`` appears only as an import, as this class,
    as a parameter's annotation and as a call inside the three walks (the shadow
    casters, the sun receivers, the 3D records), and a lookup is handed to
    ``item_base_cm`` / ``standing_parent`` / ``_record_of`` and to nothing else
    (``tests/integration/test_scene3d_base_stacking.py``, which also says what
    such a reading cannot see).
    """

    __slots__ = ("_by_id", "_items", "_shapes")

    def __init__(self, items: Iterable[Any]) -> None:
        self._items = items
        self._by_id: dict[str, Any] | None = None
        self._shapes: dict[int, QPainterPath] = {}

    def get(self, item_id: Any) -> Any | None:
        """The item with that id (a ``UUID`` or its string), or None."""
        if self._by_id is None:
            self._by_id = {str(item.item_id): item for item in self._items
                           if hasattr(item, "item_id")}
        return self._by_id.get(str(item_id))

    def shape_of(self, parent: Any) -> QPainterPath:
        """``contains_path(parent)``, built once per walk.

        Qt's ``contains`` rebuilds the item's shape on every call; a bed with
        forty plants built it forty times a walk (bench_large: 240 times).
        """
        key = id(parent)  # the walk's items outlive the lookup that indexes them
        shape = self._shapes.get(key)
        if shape is None:
            shape = self._shapes[key] = contains_path(parent)
        return shape


def bed_membership_point(item: Any) -> QPointF:
    """The scene point the LINK decisions ask: which bed is an item in?

    The centre of the item's ``boundingRect()`` — the construct every link
    decision of the app uses (auto-parenting on creation, bulk create and paste,
    the re-link after a drag, the agent's re-link after ``move_object`` or
    ``set_object_position``, and its ``link_is_geometric``). Kept exactly as shipped. It is NOT the geometric
    centre: the antagonist badge grows the bounding rect towards +x / +y and so
    moves this point by up to 1.8 cm along each axis (about 2.5 cm diagonally).
    Where an item STANDS is asked of ``standing_point`` instead.
    """
    point: QPointF = item.mapToScene(item.boundingRect().center())
    return point


def standing_point(item: Any) -> QPointF | None:
    """The scene point an item STANDS on: its stable geometric centre.

    ``item_outline``'s anchor in scene coordinates — a plant circle's centre, an
    ellipse's or rectangle's ``rect().center()``, the centre of a polygon's
    vertex bounding box: the point its footprint is built around and the origin
    of its 3D record. It moves only when the item's geometry or pose does —
    never with a badge, a highlight, a selection or a spacing ring, all of which
    change ``boundingRect()``. None for an item without a footprint.
    """
    if isinstance(item, CircleItem):  # every plant; skips the canopy lookup
        centre: QPointF = item.mapToScene(item.center)
        return centre
    outline = item_outline(item)
    if outline is None:
        return None
    mapped: QPointF = item.mapToScene(QPointF(outline.anchor[0], outline.anchor[1]))
    return mapped


def contains_path(parent: Any) -> QPainterPath:
    """The path Qt's ``QGraphicsItem::contains`` tests a local point against:
    the clip path of a clipped item, else its shape."""
    path: QPainterPath = parent.clipPath() if parent.isClipped() else parent.shape()
    return path


def shape_contains(parent: Any, scene_point: QPointF,
                   shape: QPainterPath | None = None) -> bool:
    """Does the parent's own shape contain that scene point? — the app's ONE
    point-in-bed predicate (Qt's ``contains``).

    ``shape``: the parent's ``contains_path`` when the caller holds it for a
    walk (``ItemLookup.shape_of``) — the same answer without rebuilding the path
    for every plant of the bed.
    """
    local = parent.mapFromScene(scene_point)
    if shape is None:
        return bool(parent.contains(local))
    return bool(shape.contains(local))


def centre_is_inside(item: Any, parent: Any) -> bool:
    """Is the item in that parent, as the LINK decisions see it
    (``bed_membership_point``)? Not the lift: ``item_base_cm``."""
    return shape_contains(parent, bed_membership_point(item))


def item_base_cm(item: Any, lookup: ItemLookup, at_date: date | None = None) -> float:
    """How high above the garden floor the item stands, in cm.

    An item is lifted onto a parent's soil only when BOTH hold:

    1. its ``parent_bed_id`` (a ``GardenItem`` PROPERTY, never a metadata key)
       names a VISIBLE soil container with a resolved height —
       ``core.object_height.standing_base_cm``: the parent's soil surface; and
    2. the item's ``standing_point`` — its stable geometric centre — lies inside
       that parent's shape (``shape_contains``).

    The link alone never decides where a solid stands: the app keeps it as
    bookkeeping, not as geometry. It is evaluated when a plant is created (one
    by one, in bulk, or pasted), when a selected plant is dropped after a drag,
    and when the agent moves a plant — and by nothing that changes a BED, so
    shrinking a bed away from its plant leaves the link in place
    (``set_parent_bed`` even sets one on purpose without containment). A linked
    plant that is not in its bed stands on the ground, exactly as every plant
    did before bases existed.

    The point is ``standing_point``, not the link decisions'
    ``bed_membership_point``: a bounding rect grows with the antagonist badge,
    and a plant 1 cm inside its bed's edge must not drop to the ground — and
    lose 38 cm of shadow base — when a warning badge appears.

    Everything else stands on the ground too: no parent, an in-ground bed, a
    trellis, a dangling link. A parent that is not visible is not there either —
    it casts no shadow and has no 3D solid, so its plants do not float above
    nothing (the visibility rule of ``collect_shadow_casters``).

    ONE rule, asked by the 2D shadow casters and by ``snapshot_records``.
    Parents do not nest (only plants are parented), so there is nothing to sum.
    WHICH parent an item stands in is ``standing_parent`` (the sun estimate asks
    that half alone); how high its soil is, ``standing_base_cm``.
    """
    parent = standing_parent(item, lookup, at_date)
    if parent is None:
        return 0.0
    return standing_base_cm(
        getattr(parent, "object_type", None), getattr(parent, "metadata", None), at_date
    )


def holds_plants(item: Any, at_date: date | None = None) -> bool:
    """Is this item a soil container a plant can stand in — the base rule's parent
    half, without a link (``core.object_height.is_solid_soil_parent``: a bed, raised
    bed, container or wall planter with a resolved, positive, finite height).

    Asked by the one caster walk for the per-plant sun estimate (#481): the ground
    point under a plant inside such a solid is inside its footprint all day, and the
    solid is UNDER the plant, not between it and the sun, whether or not the plant
    was ever linked to it. The estimate spares exactly the casters this answers True
    for, so a kind the predicate learns about is spared without a second list
    (the gap #621 found for cold frames and pots began as such a list).

    The one home of the predicate on the item side: the drift guard in
    ``tests/integration/test_scene3d_base_stacking.py`` names every caller of
    ``is_solid_soil_parent`` and expects this module.
    """
    return is_solid_soil_parent(
        getattr(item, "object_type", None), getattr(item, "metadata", None), at_date)


def standing_parent(item: Any, lookup: ItemLookup, at_date: date | None = None) -> Any | None:
    """The soil parent whose solid the item stands in, or None — the membership
    half of the base rule (``item_base_cm`` has the whole rule and its reasons).

    The parent when ALL hold: the item's ``parent_bed_id`` names it; it is
    VISIBLE; it is a soil-capable solid (``core.object_height
    .is_solid_soil_parent``: a bed, raised bed, container or wall planter with a
    resolved height); and the item's ``standing_point`` lies inside its shape.

    Asked on its own by the per-plant sun estimate (US-F3): the ground point
    under such a plant is inside that parent's footprint all day, and the parent
    is under the plant, not between it and the sun — it must not count as shade,
    whether its soil lifts the plant by 38 cm or (a 2 cm edging) by nothing.

    The geometric test runs last and only for an item with such a parent, so a
    plan without raised soil never pays for it; the parent's shape is built once
    per walk (``ItemLookup.shape_of``).
    """
    parent_id = getattr(item, "parent_bed_id", None)
    if parent_id is None:
        return None
    parent = lookup.get(parent_id)
    if parent is None or not parent.isVisible():
        return None
    if not is_solid_soil_parent(
        getattr(parent, "object_type", None), getattr(parent, "metadata", None), at_date
    ):
        return None
    point = standing_point(item)
    if point is None or not shape_contains(parent, point, lookup.shape_of(parent)):
        return None
    return parent


def _bounding_center(points: tuple[Point, ...]) -> Point:
    if not points:
        return (0.0, 0.0)
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def item_outline(item: Any, at_date: date | None = None) -> ItemOutline | None:
    """The item's outline in its own coordinates, or None when it has no footprint.

    ``at_date`` (US-E8) sizes a measured plant's canopy circle to its projected
    spread — display/shadow only, the stored geometry is never touched. Items
    that are not one of the five footprint shapes (text, callouts, groups,
    arcs …) and an ellipse without an area have none.
    """
    if isinstance(item, CircleItem):
        center = item.center
        radius = plant_canopy_radius_cm(item, at_date)
        if radius is None:
            radius = item.radius
        return ItemOutline(OUTLINE_CIRCLE, (center.x(), center.y()), radius_cm=radius)
    if isinstance(item, EllipseItem):
        rect = item.rect()
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2.0, rect.height() / 2.0
        if rx <= 0 or ry <= 0:
            return None
        step = 2.0 * math.pi / ELLIPSE_SEGMENTS
        return ItemOutline(OUTLINE_ELLIPSE, (cx, cy), tuple(
            (cx + rx * math.cos(i * step), cy + ry * math.sin(i * step))
            for i in range(ELLIPSE_SEGMENTS)
        ))
    if isinstance(item, RectangleItem):
        rect = item.rect()
        corners = (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft())
        center = rect.center()
        return ItemOutline(OUTLINE_RECTANGLE, (center.x(), center.y()),
                           tuple((c.x(), c.y()) for c in corners))
    if isinstance(item, PolygonItem):
        polygon = item.polygon()
        vertices = tuple(
            (vertex.x(), vertex.y())
            for vertex in (polygon.at(i) for i in range(polygon.count()))
        )
        return ItemOutline(OUTLINE_POLYGON, _bounding_center(vertices), vertices)
    if isinstance(item, PolylineItem):
        line = tuple((p.x(), p.y()) for p in item.points)
        width = item.pen().widthF()
        if width <= 0:
            width = 1.0
        return ItemOutline(OUTLINE_POLYLINE, _bounding_center(line), line, width_cm=width)
    return None


def item_footprints(item: Any, at_date: date | None = None) -> list[Polygon]:
    """Scene-space footprint polygon(s) of one canvas item.

    The outline's vertices (``item_outline``) mapped through the item's own
    transform (``mapToScene``), so rotation/position are Qt's answer, not a
    re-derivation — the #218/#219 geometry lessons. A circle is polygonalised
    around its mapped centre (it does not turn with its item); a polyline's
    centre line is inflated by half its stroke width, in scene space.
    ``at_date`` (US-E8) resizes a measured plant's canopy circle to its
    projected spread — display/shadow only.
    """
    outline = item_outline(item, at_date)
    if outline is None:
        return []
    if outline.shape == OUTLINE_CIRCLE:
        center = item.mapToScene(QPointF(outline.anchor[0], outline.anchor[1]))
        return [circle_footprint(center.x(), center.y(), outline.radius_cm or 0.0)]
    points = [item.mapToScene(QPointF(x, y)) for x, y in outline.points]
    scene_points = [(p.x(), p.y()) for p in points]
    if outline.shape == OUTLINE_POLYLINE:
        return polyline_footprint(scene_points, outline.width_cm or 1.0)
    return [scene_points]


def footprints_can_self_cross(item: Any) -> bool:
    """Can this item's own outline cross itself? Only a free polygon can.

    The extractor is the reason: a circle, an ellipse and a rectangle are
    generated from a centre/radius or a rect and cannot, and a polyline's
    centre line is OFFSET by ``pyclipper``, which resolves a crossing line into
    separate rings — so a crossing polyline arrives as more than one ring, the
    case the shadow walk always repairs (``core.shadow_geometry.shadow_region``).
    A ``PolygonItem`` keeps the user's own vertex order, which may cross.

    The walk asks this so that the repair's ``SimplifyPolygons`` call is paid
    only where it can find something: 379 of bench_large's 382 casters are
    circles and rectangles, and a call each cost 4.5 ms a walk (measured: 10.5 ms
    against master's 6.1 ms, Windows, before this gate). A new footprint shape
    that can cross must answer True here — pinned by
    ``tests/unit/test_footprint_shapes.py``.
    """
    return isinstance(item, PolygonItem)
