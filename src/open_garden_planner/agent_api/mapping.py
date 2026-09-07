"""Pure (Qt-free) mapping from an ``.ogp`` snapshot dict to Agent API schema.

Kept import-light on purpose: no PyQt6, no mcp. The object-classification name
sets are inlined here rather than importing ``core.object_types`` (which pulls
in ``QColor`` and the rest of Qt); ``tests/unit/test_agent_api_mapping.py``
guards them against drift from the real ``ObjectType`` definitions.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.schema import Layer, PlanSummary

# Soil-bearing parents — mirrors ObjectType ``SOIL_CONTAINER_TYPES`` (ADR-031).
# Inlined to keep this module Qt-free; a unit drift-guard asserts equality.
_BED_TYPE_NAMES = frozenset(
    {"GARDEN_BED", "RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}
)
# Plant object types.
_PLANT_TYPE_NAMES = frozenset({"TREE", "SHRUB", "PERENNIAL"})


def layers_from_snapshot(snapshot: dict[str, Any]) -> list[Layer]:
    """Build the curated :class:`Layer` list from a snapshot (US-D2.4).

    The raw snapshot already carries the full layer records
    (``models.layer.Layer.to_dict``: id/name/visible/locked/opacity/z_order);
    this only adds what a snapshot cannot carry per-layer record: the active
    layer (session state, surfaced via ``agent_meta.active_layer_id``) and the
    per-layer TOP-LEVEL object count (same counting rule as the plan summary's
    counts — objects nested in a group count once, at the group's layer).

    Layer order is the snapshot's own (scene list order, index 0 = top of the
    stack), so ``z_order`` is reported alongside rather than re-derived.
    """
    layers = snapshot.get("layers") or []
    objects = snapshot.get("objects") or []
    meta = snapshot.get("agent_meta") or {}
    active_id = meta.get("active_layer_id")

    counts: dict[str, int] = {}
    for obj in objects:
        lid = obj.get("layer_id")
        if lid:
            counts[str(lid)] = counts.get(str(lid), 0) + 1

    out: list[Layer] = []
    for layer in layers:
        lid = str(layer.get("id", ""))
        out.append(
            Layer(
                layer_id=lid,
                name=str(layer.get("name", "")),
                visible=bool(layer.get("visible", True)),
                locked=bool(layer.get("locked", False)),
                opacity=float(layer.get("opacity", 1.0)),
                z_order=int(layer.get("z_order", 0)),
                is_active=active_id is not None and lid == str(active_id),
                object_count=counts.get(lid, 0),
            )
        )
    return out


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
        layers=layers_from_snapshot(snapshot),
    )
