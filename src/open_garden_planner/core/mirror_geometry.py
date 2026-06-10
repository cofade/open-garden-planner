"""Build mirrored copies of canvas shape items (US-B4 — Mirror tool).

``build_mirrored_item(source, a, b)`` returns a *new*, un-parented item that is
the reflection of ``source`` across the axis line ``a → b`` (scene coordinates),
copying the source's style / object type / metadata / layer. It returns ``None``
for item types the Mirror tool does not support.

Design (see ADR-026): the reflection rebuilds each item from its own constructor
rather than applying a Qt negative-scale transform. That keeps geometry baked
into the persisted fields (so it round-trips through save/load and DXF) and means
SVG-rendered glyphs (furniture, plants) and any embedded content render
*un-flipped* — only their position/orientation reflect, matching LibreCAD.

Coordinate handling: point-based items (polyline, polygon, bezier) reflect every
defining point in *scene* space and are rebuilt at ``pos (0, 0)`` with those
points as local coordinates, so no residual rotation is needed. Rectangle and
ellipse keep their width/height and instead reflect the centre and flip the
rotation angle. Circles reflect the centre only. Arcs reflect their three
defining points (start / through / end) and recompute via
:func:`arc_from_three_points`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QPen

from open_garden_planner.core.cad_geometry import (
    arc_from_three_points,
    reflect_angle_deg,
    reflect_point,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem


def build_mirrored_item(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem | None:
    """Return a new item that is ``source`` reflected across the axis ``a → b``.

    The returned item is not added to any scene and keeps its own fresh
    ``item_id``; the caller (the Mirror command) owns id-stamping and scene
    insertion. Returns ``None`` if ``source`` is not a supported shape type.
    """
    # Imported here to avoid import cycles (items import core).
    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        BezierItem,
        CircleItem,
        EllipseItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )

    if isinstance(source, PolylineItem):
        return _mirror_polyline(source, a, b)
    if isinstance(source, PolygonItem):
        return _mirror_polygon(source, a, b)
    if isinstance(source, CircleItem):
        return _mirror_circle(source, a, b)
    if isinstance(source, (RectangleItem, EllipseItem)):
        return _mirror_box(source, a, b)
    if isinstance(source, ArcItem):
        return _mirror_arc(source, a, b)
    if isinstance(source, BezierItem):
        return _mirror_bezier(source, a, b)
    return None


# ---------------------------------------------------------------------------
# Per-type builders
# ---------------------------------------------------------------------------


def _mirror_polyline(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem:
    refl = [reflect_point(source.mapToScene(p), a, b) for p in source.points]
    # clone_with_points copies pen/brush/object_type/name/layer/style and
    # places the clone at pos (0, 0), so scene-space points become its geometry.
    return source.clone_with_points(refl)


def _mirror_polygon(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem:
    from open_garden_planner.ui.canvas.items import PolygonItem

    poly = source.polygon()
    refl = [
        reflect_point(source.mapToScene(poly.at(i)), a, b)
        for i in range(poly.count())
    ]
    clone = PolygonItem(
        vertices=refl,
        object_type=source.object_type,
        name=source.name,
        metadata=dict(source.metadata) if source.metadata else None,
        fill_pattern=source.fill_pattern,
        stroke_style=source.stroke_style,
        layer_id=source.layer_id,
    )
    _copy_visual_style(source, clone)
    return clone


def _mirror_circle(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem:
    from open_garden_planner.ui.canvas.items import CircleItem

    center = reflect_point(source.mapToScene(source.center), a, b)
    clone = CircleItem(
        center.x(),
        center.y(),
        source.radius,
        object_type=source.object_type,
        name=source.name,
        metadata=dict(source.metadata) if source.metadata else None,
        fill_pattern=source.fill_pattern,
        stroke_style=source.stroke_style,
        layer_id=source.layer_id,
    )
    # Plants render from category/species, not pen/brush — carry them over.
    clone.plant_category = source.plant_category
    clone.plant_species = source.plant_species
    _copy_visual_style(source, clone)
    return clone


def _mirror_box(source: QGraphicsItem, a: QPointF, b: QPointF) -> QGraphicsItem:
    """Mirror a RectangleItem or EllipseItem (centre reflect + rotation flip).

    Width/height are reflection-invariant; only the centre and orientation
    change. The rotation pivot is the bounding-rect centre, which equals the
    geometric centre, so ``mapToScene(rect.center())`` is rotation-invariant.
    """
    rect = source.rect()
    w = rect.width()
    h = rect.height()
    center = reflect_point(source.mapToScene(rect.center()), a, b)
    cls = type(source)
    clone = cls(
        center.x() - w / 2.0,
        center.y() - h / 2.0,
        w,
        h,
        object_type=source.object_type,
        name=source.name,
        metadata=dict(source.metadata) if source.metadata else None,
        fill_pattern=source.fill_pattern,
        stroke_style=source.stroke_style,
        layer_id=source.layer_id,
    )
    _copy_visual_style(source, clone)
    new_angle = reflect_angle_deg(getattr(source, "rotation_angle", 0.0), a, b)
    if abs(new_angle) > 1e-9:
        clone._apply_rotation(new_angle)
    return clone


def _mirror_arc(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem | None:
    from open_garden_planner.ui.canvas.items import ArcItem

    start = reflect_point(source.start_point(), a, b)
    through = reflect_point(source.through_point(), a, b)
    end = reflect_point(source.end_point(), a, b)
    result = arc_from_three_points(start, through, end)
    if result is None:
        return None  # Degenerate after reflection — skip rather than corrupt.
    center, radius, start_deg, span_deg = result
    clone = ArcItem(
        center=center,
        radius=radius,
        start_deg=start_deg,
        span_deg=span_deg,
        name=source.name,
        layer_id=source.layer_id,
        through=through,
    )
    clone.stroke_color = source.stroke_color
    clone.stroke_width = source.stroke_width
    return clone


def _mirror_bezier(
    source: QGraphicsItem, a: QPointF, b: QPointF
) -> QGraphicsItem:
    from open_garden_planner.ui.canvas.items import BezierItem

    def refl_all(points: list[QPointF]) -> list[QPointF]:
        return [reflect_point(source.mapToScene(p), a, b) for p in points]

    clone = BezierItem(
        anchors=refl_all(source.anchors),
        handles_in=refl_all(source.handles_in),
        handles_out=refl_all(source.handles_out),
        name=source.name,
        layer_id=source.layer_id,
    )
    clone.stroke_color = source.stroke_color
    clone.stroke_width = source.stroke_width
    return clone


# ---------------------------------------------------------------------------
# Shared appearance copy (GardenItemMixin-based items)
# ---------------------------------------------------------------------------


def _copy_visual_style(source: QGraphicsItem, dest: QGraphicsItem) -> None:
    """Copy pen/brush + custom-colour/label flags from ``source`` to ``dest``.

    object_type / name / metadata / fill_pattern / stroke_style / layer_id are
    already carried via the constructor; this fills in the remaining live
    appearance state (exact pen & brush objects, the stored ``fill_color``
    override, and area-label visibility) so a mirrored shape is visually
    identical to its source.
    """
    if hasattr(source, "fill_color") and source.fill_color is not None:
        dest.fill_color = source.fill_color
    dest.setBrush(QBrush(source.brush()))
    dest.setPen(QPen(source.pen()))
    if getattr(source, "area_label_visible", False):
        dest.area_label_visible = True
