"""Pure (Qt-free) mapping from an ``.ogp`` snapshot dict to Agent API schema.

Kept import-light on purpose: no PyQt6, no mcp. The object-classification name
sets are inlined here rather than importing ``core.object_types`` (which pulls
in ``QColor`` and the rest of Qt); ``tests/unit/test_agent_api_mapping.py``
guards them against drift from the real ``ObjectType`` definitions.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.schema import PlanSummary

# Soil-bearing parents — mirrors ObjectType ``SOIL_CONTAINER_TYPES`` (ADR-031).
# Inlined to keep this module Qt-free; a unit drift-guard asserts equality.
_BED_TYPE_NAMES = frozenset(
    {"GARDEN_BED", "RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}
)
# Plant object types.
_PLANT_TYPE_NAMES = frozenset({"TREE", "SHRUB", "PERENNIAL"})


def plan_summary_from_snapshot(snapshot: dict[str, Any]) -> PlanSummary:
    """Build a :class:`PlanSummary` from a ``ProjectManager.snapshot_dict`` result.

    Objects are classified by their serialised ``object_type`` name. Anything
    that is neither a bed nor a plant (including objects with no ``object_type``)
    is counted as a generic shape.

    Counts cover **top-level** objects only: items nested inside a group or smart
    symbol are serialised within their parent and so are not counted individually
    (a grouped bed/plant counts toward neither ``bed_count`` nor ``plant_count``).
    """
    canvas = snapshot.get("canvas") or {}
    objects = snapshot.get("objects") or []
    layers = snapshot.get("layers") or []
    meta = snapshot.get("agent_meta") or {}

    bed_count = 0
    plant_count = 0
    shape_count = 0
    for obj in objects:
        obj_type = obj.get("object_type")
        if obj_type in _BED_TYPE_NAMES:
            bed_count += 1
        elif obj_type in _PLANT_TYPE_NAMES:
            plant_count += 1
        else:
            shape_count += 1

    return PlanSummary(
        file_name=meta.get("file_name"),
        is_dirty=bool(meta.get("is_dirty", False)),
        canvas_width_cm=float(canvas.get("width", 0.0)),
        canvas_height_cm=float(canvas.get("height", 0.0)),
        bed_count=bed_count,
        plant_count=plant_count,
        shape_count=shape_count,
        layer_names=[str(layer.get("name", "")) for layer in layers],
    )
