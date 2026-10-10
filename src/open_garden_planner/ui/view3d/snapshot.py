"""Plan snapshot for the 3D view — live items → plain data.

Runs on the GUI thread; the output contains no Qt object references (the
same snapshot-boundary discipline as the US-E4 worker). Footprints reuse
the US-E3 extraction (rotation/position are Qt's answer via ``mapToScene``)
so the 3D solids can never disagree with the 2D shadow footprints.

Two collectors live here until L1.10 removes Qt 3D:

- ``collect_scene3d_records`` (US-E6) feeds the shipped Qt 3D window with
  scene-space prisms and decals — unchanged.
- ``snapshot_records`` (Phase 17 L1.1, #385, ADR-054) produces contract v2:
  one ``core.scene3d.Record`` per item, in the item-local frame with a rigid
  transform, for ``SceneSync`` and the Qt Quick 3D sink.
"""

from __future__ import annotations

import math
from datetime import date
from functools import lru_cache
from typing import Any

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.container_model import container_material
from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.object_types import PathFenceStyle, is_container_type
from open_garden_planner.core.scene3d import (
    PARAM_CONTAINER_MATERIAL,
    PARAM_PATH_STYLE,
    PARAM_PLANT_CATEGORY,
    PARAM_RADIUS_CM,
    PARAM_RIDGE,
    PARAM_SEED,
    PARAM_SPECIES_KEY,
    PARAM_SPECIES_NAME,
    LocalFrame,
    Material,
    Params,
    ParamValue,
    Record,
    Rgba,
    Ring,
    Scene3DRecord,
    local_frame,
    quantize_cm,
    records_from_raw,
)
from open_garden_planner.core.shadow_geometry import circle_footprint, polyline_footprint
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.ui.canvas.footprints import (
    OUTLINE_CIRCLE,
    OUTLINE_POLYLINE,
    item_footprints,
    item_outline,
)
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

_FALLBACK_COLOR = (158, 158, 148, 255)


def _item_color_rgba(item: Any) -> tuple[int, int, int, int]:
    color = getattr(item, "fill_color", None)
    if isinstance(color, str):
        color = QColor(color)
    if isinstance(color, QColor) and color.isValid():
        return (color.red(), color.green(), color.blue(), 255)
    return _FALLBACK_COLOR


def collect_scene3d_records(
    scene: QGraphicsScene, at_date: date | None = None
) -> list[Scene3DRecord]:
    """Every visible item with a footprint → an engine-ready record.

    Items with an effective height become extruded prisms; the rest
    (lawns, paths, in-ground beds …) become thin ground decals, so the
    2D layout stays recognizable from above. ``at_date`` (US-E8) projects
    dated plants to their grown height and canopy spread — scrub the sim
    date and trees grow in 3D.
    """
    raw: list[dict[str, Any]] = []
    # Bottom-to-top stacking order (scene.items() is top-first) so flat decals
    # can be lifted up the 2D layer order — a higher layer renders on top.
    for item in reversed(scene.items()):
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        metadata = getattr(item, "metadata", None)
        height = effective_height_cm(object_type, metadata, at_date=at_date)
        color = _item_color_rgba(item)
        name = str(getattr(item, "name", "") or object_type.name)
        for footprint in item_footprints(item, at_date):
            if len(footprint) >= 3:
                raw.append(
                    {
                        "footprint": footprint,
                        "height_cm": height,
                        "color_rgba": color,
                        "name": name,
                    }
                )
    return records_from_raw(raw)


# ── contract v2 (Phase 17 L1.1) ──────────────────────────────────────────────


@lru_cache(maxsize=4096)
def _circle_ring(radius_cm: float) -> Ring:
    """A circle's item-local footprint: ``circle_footprint`` about the origin.

    Cached: a plan has few distinct radii, and the ring is a function of the
    radius alone (a circle's footprint does not turn with its item).
    """
    return tuple((quantize_cm(x), quantize_cm(y))
                 for x, y in circle_footprint(0.0, 0.0, radius_cm))


@lru_cache(maxsize=2048)
def _polyline_strips(path: Ring, width_cm: float) -> tuple[Ring, ...]:
    """A polyline's item-local stroke polygon(s): the centre line inflated by
    half its width (``polyline_footprint`` — pyclipper, a 1/1000 cm grid)."""
    return tuple(tuple(ring) for ring in polyline_footprint(list(path), width_cm))


@lru_cache(maxsize=1024)
def _material(key: str, fill: Rgba | None, stroke: Rgba | None, pattern: str | None) -> Material:
    return Material(key, fill, stroke, pattern)


def _rgba(color: Any) -> Rgba | None:
    if isinstance(color, str):
        color = QColor(color)
    if isinstance(color, QColor) and color.isValid():
        red, green, blue, alpha = color.getRgb()
        return (red, green, blue, alpha)
    return None


def _finite_ring(ring: Ring) -> bool:
    return math.isfinite(sum(x + y for x, y in ring))


def _frame_of(item: Any, anchor: tuple[float, float], *, rotatable: bool) -> LocalFrame:
    """The item's scene transform — Qt's ``sceneTransform()``, never a
    re-derivation from pos / rotation / transformOriginPoint — split about ``anchor``."""
    matrix = item.sceneTransform()
    return local_frame(matrix.m11(), matrix.m12(), matrix.m21(), matrix.m22(),
                       matrix.dx(), matrix.dy(), anchor[0], anchor[1], rotatable=rotatable)


def _ridge_param(house_frame: LocalFrame, ridge: Any) -> ParamValue | None:
    """A HOUSE's ridge ends in the HOUSE's local frame, from the LIVE ridge item
    (ADR-046: an edited ridge is the ridge), or None when there is no usable one.

    The ridge is ANOTHER item's geometry, and the app re-writes its points by
    ``+ delta`` on every move of the house, so its float error grows with each
    move. Measured: 1.1e-10 cm after 20,000 random moves — three orders of
    magnitude below the record grid, so it never reaches the HOUSE's geometry
    signature (0 changes in those 20,000 moves; pinned over 1,000 by
    ``test_scene3d_snapshot.py::TestHouseRidge``).
    """
    if not isinstance(ridge, PolylineItem):
        return None
    points = ridge.points
    if len(points) < 2:
        return None
    ends: list[tuple[float, float]] = []
    for point in (points[0], points[-1]):
        scene_point = ridge.mapToScene(point)
        end = house_frame.local_from_scene(scene_point.x(), scene_point.y())  # on the record grid
        if not (math.isfinite(end[0]) and math.isfinite(end[1])):
            return None
        ends.append(end)
    return (ends[0], ends[1])


def snapshot_records(
    scene: QGraphicsScene, at_date: date | None = None
) -> dict[str, Record]:
    """Every visible item with a footprint → one contract-v2 ``Record``.

    Keyed by item id, insertion-ordered BOTTOM TO TOP (paint order). Runs on the
    GUI thread; the result is plain immutable data. Skipped: invisible items
    (as ``collect_scene3d_records`` does), items without an ``object_type``,
    items without a footprint (text, groups, arcs, a polyline shorter than two
    points …) and items whose geometry is not finite.

    What a record holds, and why (``core.scene3d.record``, §8.26.1):

    - geometry in the ITEM-LOCAL frame, centred on the outline's anchor
      (``ui.canvas.footprints.item_outline``), on the record grid; the pose
      (``transform``) from the item's ``sceneTransform()``. A circle's rotation
      is 0 by construction: its footprint does not turn. A scene transform that
      is not rigid (an item in a scaled group) is baked into the local geometry.
    - ``height_cm``: ``effective_height_cm(..., at_date)`` — the 2D shadow's
      resolver; None means decoration that casts no shadow.
    - ``transform.base_cm`` is 0.0 here; L1.6 stands a plant on its parent bed
      (``parent_id``) with it.
    - ``at_date`` (US-E8) grows dated plants: canopy radius and height.
    """
    items: list[Any] = scene.items()  # top-first; garden items are duck-typed below
    by_id: dict[str, Any] | None = None
    records: dict[str, Record] = {}
    for item in reversed(items):
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        outline = item_outline(item, at_date)
        if outline is None:
            continue
        item_uuid = getattr(item, "item_id", None)
        if item_uuid is None:
            continue
        item_id = str(item_uuid)
        kind: str = object_type.name
        shape = outline.shape
        frame = _frame_of(item, outline.anchor, rotatable=shape != OUTLINE_CIRCLE)
        if not math.isfinite(frame.east_cm + frame.north_cm):
            continue
        params: dict[str, ParamValue] = {PARAM_SEED: item_id}
        path: Ring = ()
        width: float | None = None
        if shape == OUTLINE_CIRCLE:
            radius = outline.radius_cm
            if radius is None or not math.isfinite(radius) or radius <= 0.0:
                continue
            radius = quantize_cm(radius)
            footprints: tuple[Ring, ...] = (_circle_ring(radius),)
            params[PARAM_RADIUS_CM] = radius
        elif shape == OUTLINE_POLYLINE:
            path = frame.local_ring(outline.points)
            width = outline.width_cm
            if width is None or len(path) < 2 or not _finite_ring(path):
                continue
            footprints = _polyline_strips(path, width)
            style = getattr(item, "path_fence_style", PathFenceStyle.NONE)
            if style is not PathFenceStyle.NONE:
                params[PARAM_PATH_STYLE] = style.name
        else:
            ring = frame.local_ring(outline.points)
            if len(ring) < 3 or not _finite_ring(ring):
                continue
            footprints = (ring,)
        footprints = tuple(ring for ring in footprints if len(ring) >= 3)
        if not footprints:
            continue
        metadata = getattr(item, "metadata", None) or {}
        species = metadata.get("plant_species")
        species_name = ""
        if isinstance(species, dict):
            params[PARAM_SPECIES_KEY] = species_key(species)
            species_name = str(species.get("common_name") or "")
        species_name = (species_name or str(getattr(item, "plant_species", "") or "")).strip()
        if species_name:
            params[PARAM_SPECIES_NAME] = species_name
        category = getattr(item, "plant_category", None)
        if category is not None:
            params[PARAM_PLANT_CATEGORY] = category.name
        if is_container_type(object_type):
            params[PARAM_CONTAINER_MATERIAL] = container_material(metadata)
        if kind == "HOUSE":
            ridge_id = metadata.get("ridge_item_id")
            if ridge_id:
                if by_id is None:
                    by_id = {str(other.item_id): other for other in items
                             if hasattr(other, "item_id")}
                ridge = _ridge_param(frame, by_id.get(str(ridge_id)))
                if ridge is not None:
                    params[PARAM_RIDGE] = ridge
        stroke = getattr(item, "stroke_color", None)
        if stroke is None and shape == OUTLINE_POLYLINE:
            stroke = item.pen().color()  # the line's visible colour: a preset-less polyline
        pattern = getattr(item, "fill_pattern", None)
        parent = getattr(item, "parent_bed_id", None)
        records[item_id] = Record(
            item_id=item_id,
            kind=kind,
            shape=shape,
            footprints=footprints,
            transform=frame.transform(),
            material=_material(kind, _rgba(getattr(item, "fill_color", None)), _rgba(stroke),
                               pattern.name if pattern is not None else None),
            height_cm=effective_height_cm(object_type, metadata, at_date=at_date),
            path=path,
            path_width_cm=width,
            params=Params(params),
            parent_id=str(parent) if parent is not None else None,
            name=str(getattr(item, "name", "") or ""),
        )
    return records
