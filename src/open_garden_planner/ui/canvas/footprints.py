"""Which ground does a canvas item cover? — the ONE footprint extraction.

Public home (Phase 17 L1.1, #385, ADR-054) of the helpers that used to be
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
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from PyQt6.QtCore import QPointF

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
