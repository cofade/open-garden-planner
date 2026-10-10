"""Which ground does a canvas item cover? — the ONE footprint extraction.

Public home (Phase 17 L1.1, #385, ADR-054) of the two helpers that used to be
private to ``sun_shadow_controller``: the shadow overlay (US-E3), the
hours-of-sun heatmap (US-E4), the Qt 3D view (US-E6) and the Qt Quick 3D
pipeline all ask this module, so a 3D solid can never disagree with its 2D
shadow. ``tests/integration/test_footprints_golden.py`` pins every number it
returns against a fixture generated before the move.

Frame: SCENE centimetres, +x = East, +y = North (ADR-002) — there is no Y-flip
here (§8.20). Rotation and position are Qt's answer (``mapToScene``), never a
re-derivation from ``pos()`` / ``rotation()`` / ``transformOriginPoint()`` (the
#218/#219 lessons).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from PyQt6.QtCore import QPointF

from open_garden_planner.core.shadow_geometry import (
    Polygon,
    circle_footprint,
    polyline_footprint,
)

#: Vertices of a polygonalised ellipse (a circle uses ``circle_footprint``'s
#: default, the same number).
ELLIPSE_SEGMENTS = 24


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


def item_footprints(item: Any, at_date: date | None = None) -> list[Polygon]:
    """Scene-space footprint polygon(s) of one canvas item.

    Vertices are mapped through the item's own transform (``mapToScene``),
    so rotation/position are Qt's answer, not a re-derivation — the
    #218/#219 geometry lessons. ``at_date`` (US-E8) resizes a measured
    plant's canopy circle to its projected spread — display/shadow only.
    """
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if isinstance(item, CircleItem):
        center = item.mapToScene(item.center)
        radius = plant_canopy_radius_cm(item, at_date)
        if radius is None:
            radius = item.radius
        return [circle_footprint(center.x(), center.y(), radius)]
    if isinstance(item, EllipseItem):
        rect = item.rect()
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2.0, rect.height() / 2.0
        if rx <= 0 or ry <= 0:
            return []
        step = 2.0 * math.pi / ELLIPSE_SEGMENTS
        points = [
            item.mapToScene(
                QPointF(cx + rx * math.cos(i * step), cy + ry * math.sin(i * step))
            )
            for i in range(ELLIPSE_SEGMENTS)
        ]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, RectangleItem):
        rect = item.rect()
        corners = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        points = [item.mapToScene(c) for c in corners]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, PolygonItem):
        polygon = item.polygon()
        points = [item.mapToScene(polygon.at(i)) for i in range(polygon.count())]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, PolylineItem):
        points = [item.mapToScene(p) for p in item.points]
        width = item.pen().widthF()
        if width <= 0:
            width = 1.0
        return polyline_footprint([(p.x(), p.y()) for p in points], width)
    return []
