"""Strict numeric validation and atomic .ogp persistence (AUD-041).

Qt-free. Every .ogp reader/writer uses this boundary before constructing scene
objects or replacing a file. Invalid numeric data rejects the entire document.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, cast

MIN_CANVAS_CM = 50.0
MAX_CANVAS_CM = 100_000.0

# Numeric strings are accepted only at the geometric keys legacy loaders
# already consume as numbers. Text elsewhere is never interpreted as numeric.
_GEOMETRY_KEYS = frozenset({
    "x", "y", "x1", "y1", "x2", "y2", "width", "height", "center_x", "center_y",
    "radius", "semi_x", "semi_y", "rotation", "rotation_angle", "start_deg", "span_deg",
    "through_x", "through_y", "stroke_width", "font_size", "scale_factor", "opacity",
    "target_x", "target_y", "box_dx", "box_dy", "position", "scene_x", "scene_y",
    "meters_per_pixel", "object_height_cm", "spacing_radius_cm", "value", "angle",
    "label_offset_x", "label_offset_y", "font_size_cm",
})


class PlanValidationError(ValueError):
    """Machine-readable numeric failure; the UI translates the category."""

    def __init__(self, field: str, category: str = "finite") -> None:
        self.field, self.category = field, category
        super().__init__(f"Invalid plan value ({category}): {field}")


def finite_number(value: Any, field: str) -> float:
    """Convert a numeric value and refuse overflow, booleans and non-finites."""
    try:
        if isinstance(value, bool):
            raise ValueError
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlanValidationError(field) from exc
    if not math.isfinite(result):
        raise PlanValidationError(field)
    return result


def validate_canvas_size(width: Any, height: Any) -> tuple[float, float]:
    """Shared canvas limits for loaded plans and new_plan; never clamp."""
    dimensions = []
    for name, raw in (("width_cm", width), ("height_cm", height)):
        value = finite_number(raw, name)
        if not MIN_CANVAS_CM <= value <= MAX_CANVAS_CM:
            raise PlanValidationError(name, "canvas")
        dimensions.append(value)
    return dimensions[0], dimensions[1]


def _walk(value: Any, path: str, *, geometry: bool = False) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        finite_number(value, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk(child, f"{path}[{index}]", geometry=geometry)
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if geometry and key in _GEOMETRY_KEYS and isinstance(child, str):
                # Other malformed strings retain the existing skip/placeholder
                # policy; only non-finite numeric strings are a numeric violation.
                try:
                    converted = float(child)
                except ValueError:
                    pass
                else:
                    finite_number(converted, child_path)
            _walk(child, child_path, geometry=geometry or key in {"objects", "guides", "constraints", "layers", "garden_journal_notes"})
        if geometry:
            _check_extents(value, path)


def _check_extents(record: dict[str, Any], path: str) -> None:
    """Refuse overflow of bounds before handing coordinates to Qt."""
    for position, size in (("x", "width"), ("y", "height"),
                           ("center_x", "radius"), ("center_y", "radius"),
                           ("center_x", "semi_x"), ("center_y", "semi_y"),
                           ("target_x", "box_dx"), ("target_y", "box_dy")):
        if position not in record or size not in record:
            continue
        try:
            pos, extent = float(record[position]), float(record[size])
        except (ValueError, TypeError):
            continue
        finite_number(pos + extent, f"{path}.{position}+{size}")
        finite_number(pos - extent, f"{path}.{position}-{size}")
        finite_number(extent * 2, f"{path}.{size}*2")
    if "scale_factor" in record:
        scale = finite_number(record["scale_factor"], f"{path}.scale_factor")
        if scale <= 0:
            raise PlanValidationError(f"{path}.scale_factor", "positive")
        finite_number(1.0 / scale, f"{path}.scale")
    if "meters_per_pixel" in record:
        mpp = finite_number(record["meters_per_pixel"], f"{path}.meters_per_pixel")
        if mpp <= 0:
            raise PlanValidationError(f"{path}.meters_per_pixel", "positive")
        finite_number(100.0 * mpp, f"{path}.pixel_extent")
    points: list[tuple[float, float]] = []
    for key in ("points", "anchors", "handles_in", "handles_out"):
        for point in record.get(key, []) if isinstance(record.get(key), list) else []:
            if isinstance(point, dict) and "x" in point and "y" in point:
                try:
                    points.append((float(point["x"]), float(point["y"])))
                except (ValueError, TypeError):
                    continue
    if points:
        finite_number(max(p[0] for p in points) - min(p[0] for p in points), f"{path}.bounds.width")
        finite_number(max(p[1] for p in points) - min(p[1] for p in points), f"{path}.bounds.height")


def validate_plan_data(data: dict[str, Any]) -> None:
    """Validate a complete raw payload without changing it or the scene."""
    if not isinstance(data, dict):
        raise TypeError("Project must be a JSON object")
    _walk(data, "plan")
    canvas = data.get("canvas", {})
    for dimension in ("width", "height"):
        if dimension in canvas and not isinstance(canvas[dimension], (int, float)):
            raise PlanValidationError(f"canvas.{dimension}")
    validate_canvas_size(canvas.get("width", 5000.0), canvas.get("height", 3000.0))
    _check_group_offsets(data.get("objects", []))


def _check_group_offsets(records: Any, dx: float = 0.0, dy: float = 0.0) -> None:
    """Nested group translations must not overflow otherwise finite children."""
    if not isinstance(records, list):
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        for key_x, key_y in (("x", "y"), ("center_x", "center_y"), ("target_x", "target_y")):
            if key_x in record and key_y in record:
                try:
                    x, y = float(record[key_x]), float(record[key_y])
                except (TypeError, ValueError):
                    continue
                finite_number(x + dx, "group.child.x")
                finite_number(y + dy, "group.child.y")
        if record.get("type") == "group":
            x = finite_number(record.get("x", 0.0), "group.x")
            y = finite_number(record.get("y", 0.0), "group.y")
            _check_group_offsets(record.get("children", []), x + dx, y + dy)
        elif dx or dy:
            for key in ("points", "anchors", "handles_in", "handles_out"):
                _check_group_offsets(record.get(key, []), dx, dy)
            if isinstance(record.get("position"), dict):
                _check_group_offsets([record["position"]], dx, dy)


def _reject_constant(token: str) -> Any:
    raise PlanValidationError(token)


def read_plan(path: Path) -> dict[str, Any]:
    """Read and validate before any deserializer is allowed to see the data."""
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream, parse_constant=_reject_constant)
    validate_plan_data(data)
    return cast(dict[str, Any], data)


def write_plan(path: Path, data: dict[str, Any]) -> None:
    """Validate/encode first, then fsync and atomically replace the destination."""
    validate_plan_data(data)
    encoded = json.dumps(data, indent=2, allow_nan=False).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
