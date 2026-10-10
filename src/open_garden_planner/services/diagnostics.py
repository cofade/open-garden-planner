"""Pure (Qt-free) mapping from harvested warning flags to Agent API diagnostics.

``get_diagnostics`` reports the plan's **already-computed** warnings — the same
state the canvas paints as badges — rather than recomputing anything. The Qt
main thread harvests each garden item's current flags into plain dicts (see
``ProjectManager.diagnostics_snapshot``); this module turns those records into
:class:`~open_garden_planner.agent_api.schema.DiagnosticRecord` entries. No PyQt6, no
mcp — unit-testable without a GUI.

One record may yield several diagnostics (a plant can be both crowded and next to
an antagonist). Positive indicators are intentionally NOT reported: spacing
``"ideal"`` and rotation ``"good"`` are good-state markers, not warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiagnosticRecord:
    kind: str
    severity: str
    item_ids: list[str]
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _label(record: dict[str, Any]) -> str:
    return str(
        record.get("name") or record.get("object_type") or record.get("item_id") or "Object"
    )


def diagnostics_from_records(
    records: list[dict[str, Any]], *, kind: str | None = None
) -> list[DiagnosticRecord]:
    """Expand harvested warning-flag records into diagnostics, optionally filtered."""
    out: list[DiagnosticRecord] = []
    for record in records:
        offset = len(out)
        label = _label(record)
        ids = [str(record.get("item_id", ""))]

        if record.get("antagonist_warning"):
            out.append(
                DiagnosticRecord(
                    kind="companion_conflict",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} has an antagonistic plant within companion range.",
                )
            )
        if record.get("spacing_overlap") == "overlap":
            out.append(
                DiagnosticRecord(
                    kind="spacing_overlap",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} is closer than its spacing radius to a neighbour.",
                )
            )
        if record.get("capacity_overrun"):
            out.append(
                DiagnosticRecord(
                    kind="capacity_overrun",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} holds more plant footprint than its container fits.",
                )
            )
        soil = record.get("soil_mismatch_level")
        if soil in ("warning", "critical"):
            out.append(
                DiagnosticRecord(
                    kind="soil_mismatch",
                    severity=str(soil),
                    item_ids=ids,
                    message=f"{label} is in soil/pH that does not match its requirements.",
                )
            )
        rotation = record.get("rotation_status")
        if rotation in ("suboptimal", "violation"):
            out.append(
                DiagnosticRecord(
                    kind="crop_rotation",
                    severity="critical" if rotation == "violation" else "warning",
                    item_ids=ids,
                    message=f"{label} conflicts with crop-rotation guidance ({rotation}).",
                )
            )
        if record.get("outside_canvas"):
            out.append(
                DiagnosticRecord(
                    kind="outside_canvas",
                    severity="warning",
                    item_ids=ids,
                    message=(
                        f"{label} is entirely outside the plan canvas — it is "
                        "invisible in the app. Move it back on-plan with "
                        "move_object or set_object_position."
                    ),
                )
            )

        for diagnostic in record.get("diagnostics", []):
            out.append(DiagnosticRecord(**diagnostic))
        for diagnostic in out[offset:]:
            diagnostic.details.setdefault("label", label)
            if diagnostic.kind == "crop_rotation":
                diagnostic.details.setdefault("rotation_status", rotation)

    if kind is not None:
        out = [d for d in out if d.kind == kind]
    return out
