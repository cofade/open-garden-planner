"""Pure (Qt-free) read/query helpers over a ``ProjectManager.snapshot_dict`` result.

Given the read-only ``.ogp``-shaped snapshot the Agent API marshals off the Qt
main thread, these functions enumerate, locate, and measure objects. No PyQt6,
no mcp — unit-testable without a GUI. The bed/plant ``ObjectType`` name sets are
shared with :mod:`open_garden_planner.agent_api.mapping` (drift-guarded there).

Coordinates are the plan's native scene frame: centimetres, origin top-left,
+x right and +y down (see :mod:`open_garden_planner.agent_api.schema`). Geometry
is summarised by each object's axis-aligned bounding box; the serialiser stores
a different shape per object kind (rectangle ``x/y/width/height``; circle/arc
``center_x/center_y/radius``; ellipse ``semi_x/semi_y``; polyline/polygon
``points``; bezier ``anchors``; group/journal-pin a bare ``x/y`` anchor;
background image a ``position``), so :func:`object_bbox` normalises them all.
"""

from __future__ import annotations

import math
from typing import Any

from open_garden_planner.agent_api.mapping import _BED_TYPE_NAMES, _PLANT_TYPE_NAMES
from open_garden_planner.agent_api.schema import Measurement, ObjectDetail, ObjectRef

# --- geometry normalisation -------------------------------------------------


def _anchor_point(obj: dict[str, Any]) -> tuple[float, float]:
    """Best-effort anchor for a shape with no width/height (point-like)."""
    if "center_x" in obj:
        return float(obj["center_x"]), float(obj.get("center_y", 0.0))
    if "target_x" in obj:  # callout
        return float(obj["target_x"]), float(obj.get("target_y", 0.0))
    if "x1" in obj:  # line segment (construction_line) — defensive
        return float(obj["x1"]), float(obj.get("y1", 0.0))
    if "x" in obj:  # group, journal_pin
        return float(obj["x"]), float(obj.get("y", 0.0))
    pos = obj.get("position")  # background_image
    if isinstance(pos, dict):
        return float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
    return 0.0, 0.0


def object_bbox(obj: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return ``(x, y, width, height)`` in scene cm for any serialised object.

    Indeterminate shapes collapse to a zero-size box at their anchor point.
    """
    if "width" in obj and "x" in obj:  # rectangle (group has x but no width)
        return (
            float(obj["x"]),
            float(obj["y"]),
            float(obj.get("width", 0.0)),
            float(obj.get("height", 0.0)),
        )
    if "radius" in obj and "center_x" in obj:  # circle, arc
        cx, cy, r = float(obj["center_x"]), float(obj["center_y"]), float(obj["radius"])
        return (cx - r, cy - r, 2 * r, 2 * r)
    if "semi_x" in obj and "center_x" in obj:  # ellipse
        cx, cy = float(obj["center_x"]), float(obj["center_y"])
        sx, sy = float(obj["semi_x"]), float(obj["semi_y"])
        return (cx - sx, cy - sy, 2 * sx, 2 * sy)
    if "x1" in obj and "x2" in obj:  # construction_line segment
        x1, y1 = float(obj["x1"]), float(obj.get("y1", 0.0))
        x2, y2 = float(obj["x2"]), float(obj.get("y2", 0.0))
        return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    points = obj.get("points") or obj.get("anchors")  # polyline/polygon, bezier
    if points:
        xs = [float(p["x"]) for p in points]
        ys = [float(p["y"]) for p in points]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    ax, ay = _anchor_point(obj)
    return (ax, ay, 0.0, 0.0)


def object_center(obj: dict[str, Any]) -> tuple[float, float]:
    """Return the bounding-box centre ``(cx, cy)`` in scene cm."""
    x, y, w, h = object_bbox(obj)
    return (x + w / 2.0, y + h / 2.0)


def _shoelace_area(points: list[dict[str, Any]]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = float(points[i]["x"]), float(points[i]["y"])
        x2, y2 = float(points[(i + 1) % n]["x"]), float(points[(i + 1) % n]["y"])
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def object_area_cm2(obj: dict[str, Any]) -> float:
    """Area in cm²: exact for circle/ellipse/polygon/rectangle, bbox otherwise."""
    obj_type = obj.get("type")
    if obj_type == "circle" and "radius" in obj:
        r = float(obj["radius"])
        return math.pi * r * r
    if obj_type == "ellipse" and "semi_x" in obj:
        return math.pi * float(obj["semi_x"]) * float(obj["semi_y"])
    if obj_type == "polygon" and obj.get("points"):
        return _shoelace_area(obj["points"])
    _, _, w, h = object_bbox(obj)
    return w * h


# --- classification / filtering ---------------------------------------------


def _type_matches(obj: dict[str, Any], type_filter: str) -> bool:
    """Match a ``type`` filter against object_type, a category, or geometry kind.

    Accepts an ``ObjectType`` name ('TREE', 'RAISED_BED'), a category ('bed',
    'plant', 'shape'), or a geometry kind ('circle', 'polygon'). Case-insensitive.
    """
    wanted = type_filter.strip().upper()
    obj_type = obj.get("object_type") or ""
    if wanted == obj_type.upper():
        return True
    if wanted == (obj.get("type") or "").upper():
        return True
    if wanted == "BED":
        return obj_type in _BED_TYPE_NAMES
    if wanted == "PLANT":
        return obj_type in _PLANT_TYPE_NAMES
    if wanted == "SHAPE":
        return obj_type not in _BED_TYPE_NAMES and obj_type not in _PLANT_TYPE_NAMES
    return False


def _layer_names_by_id(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        str(layer.get("id")): str(layer.get("name", ""))
        for layer in (snapshot.get("layers") or [])
    }


def _layer_matches(obj: dict[str, Any], layer_filter: str, names: dict[str, str]) -> bool:
    lid = str(obj.get("layer_id") or "")
    if not lid:
        return False
    if layer_filter == lid:
        return True
    return names.get(lid, "") == layer_filter  # match by layer name


def _species_key(obj: dict[str, Any]) -> str | None:
    key = obj.get("plant_species")
    return key if isinstance(key, str) and key else None


def _species_name(obj: dict[str, Any]) -> str | None:
    """Common/scientific name from metadata, falling back to the gallery key.

    Mirrors ``application._companion_species_name``: search-assigned plants store
    a dict under ``metadata['plant_species']``; gallery plants only have the key.
    """
    meta = obj.get("metadata")
    species = meta.get("plant_species") if isinstance(meta, dict) else None
    if isinstance(species, dict):
        name = species.get("common_name") or species.get("scientific_name")
        if name:
            return str(name)
    return _species_key(obj)


# --- object -> schema -------------------------------------------------------


def _object_ref(obj: dict[str, Any], layer_names: dict[str, str]) -> ObjectRef:
    cx, cy = object_center(obj)
    _, _, w, h = object_bbox(obj)
    lid = str(obj.get("layer_id") or "")
    return ObjectRef(
        item_id=str(obj.get("item_id", "")),
        type=str(obj.get("type", "")),
        object_type=obj.get("object_type"),
        name=obj.get("name"),
        layer_name=layer_names.get(lid) if lid else None,
        center_x_cm=cx,
        center_y_cm=cy,
        width_cm=w,
        height_cm=h,
    )


def _object_detail(obj: dict[str, Any], layer_names: dict[str, str]) -> ObjectDetail:
    ref = _object_ref(obj, layer_names)
    return ObjectDetail(
        **ref.model_dump(),
        rotation_deg=float(obj.get("rotation_angle", obj.get("rotation", 0.0)) or 0.0),
        area_cm2=object_area_cm2(obj),
        fill_color=obj.get("fill_color"),
        stroke_color=obj.get("stroke_color"),
        parent_bed_id=obj.get("parent_bed_id"),
        child_item_ids=list(obj.get("child_item_ids") or []),
        species_key=_species_key(obj),
        species_name=_species_name(obj),
        metadata=dict(obj.get("metadata") or {}),
    )


def _find(snapshot: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    target = str(item_id)
    if not target:
        # Some shapes (callout, background image) serialise without an item_id and
        # would all match ""; an empty id addresses nothing.
        return None
    objects: list[dict[str, Any]] = snapshot.get("objects") or []
    for obj in objects:
        if str(obj.get("item_id")) == target:
            return obj
    return None


# --- public query functions (consumed by the MCP tools) ---------------------


def list_objects(
    snapshot: dict[str, Any],
    *,
    type: str | None = None,
    layer: str | None = None,
    parent: str | None = None,
    raw: bool = False,
) -> list[dict[str, Any]] | list[ObjectRef]:
    """Enumerate top-level objects, optionally filtered by type/layer/parent."""
    layer_names = _layer_names_by_id(snapshot)
    out: list[Any] = []
    for obj in snapshot.get("objects") or []:
        if type is not None and not _type_matches(obj, type):
            continue
        if layer is not None and not _layer_matches(obj, layer, layer_names):
            continue
        if parent is not None and str(obj.get("parent_bed_id") or "") != str(parent):
            continue
        out.append(obj if raw else _object_ref(obj, layer_names))
    return out


def get_object(
    snapshot: dict[str, Any], item_id: str, *, raw: bool = False
) -> dict[str, Any] | ObjectDetail | None:
    """Return full detail for a single object, or ``None`` if the id is unknown."""
    obj = _find(snapshot, item_id)
    if obj is None:
        return None
    return obj if raw else _object_detail(obj, _layer_names_by_id(snapshot))


def objects_in_region(
    snapshot: dict[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    raw: bool = False,
) -> list[dict[str, Any]] | list[ObjectRef]:
    """Objects whose bounding box intersects the rectangle ``(x, y, width, height)``."""
    rx0, ry0, rx1, ry1 = x, y, x + width, y + height
    layer_names = _layer_names_by_id(snapshot)
    out: list[Any] = []
    for obj in snapshot.get("objects") or []:
        bx, by, bw, bh = object_bbox(obj)
        if bx <= rx1 and bx + bw >= rx0 and by <= ry1 and by + bh >= ry0:
            out.append(obj if raw else _object_ref(obj, layer_names))
    return out


def objects_in(
    snapshot: dict[str, Any], parent_id: str, *, raw: bool = False
) -> list[dict[str, Any]] | list[ObjectRef]:
    """Objects whose ``parent_bed_id`` is ``parent_id`` (contents of a bed/container)."""
    target = str(parent_id)
    layer_names = _layer_names_by_id(snapshot)
    out: list[Any] = [
        obj if raw else _object_ref(obj, layer_names)
        for obj in snapshot.get("objects") or []
        if str(obj.get("parent_bed_id") or "") == target
    ]
    return out


def plants_in_bed(
    snapshot: dict[str, Any], bed_id: str, *, raw: bool = False
) -> list[dict[str, Any]] | list[ObjectRef]:
    """Plant objects contained in the given bed/container."""
    target = str(bed_id)
    layer_names = _layer_names_by_id(snapshot)
    out: list[Any] = [
        obj if raw else _object_ref(obj, layer_names)
        for obj in snapshot.get("objects") or []
        if str(obj.get("parent_bed_id") or "") == target
        and obj.get("object_type") in _PLANT_TYPE_NAMES
    ]
    return out


def nearest_objects(
    snapshot: dict[str, Any],
    x: float,
    y: float,
    *,
    k: int = 5,
    type: str | None = None,
    raw: bool = False,
) -> list[dict[str, Any]] | list[ObjectRef]:
    """The ``k`` objects whose centres are closest to point ``(x, y)``."""
    layer_names = _layer_names_by_id(snapshot)
    scored: list[tuple[float, dict[str, Any]]] = []
    for obj in snapshot.get("objects") or []:
        if type is not None and not _type_matches(obj, type):
            continue
        cx, cy = object_center(obj)
        scored.append((math.hypot(cx - x, cy - y), obj))
    scored.sort(key=lambda pair: pair[0])
    chosen = scored[:k] if k > 0 else []  # k<=0 returns none (k is a hard cap)
    out: list[Any] = [obj if raw else _object_ref(obj, layer_names) for _, obj in chosen]
    return out


def measure_distance(
    snapshot: dict[str, Any], id_a: str, id_b: str
) -> Measurement | None:
    """Centre-to-centre distance between two objects, or ``None`` if either is unknown."""
    obj_a = _find(snapshot, id_a)
    obj_b = _find(snapshot, id_b)
    if obj_a is None or obj_b is None:
        return None
    ax, ay = object_center(obj_a)
    bx, by = object_center(obj_b)
    dx, dy = bx - ax, by - ay
    return Measurement(distance_cm=math.hypot(dx, dy), dx_cm=dx, dy_cm=dy)
