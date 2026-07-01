"""Pure (Qt-free) mapping from harvested warning flags to Agent API diagnostics.

``get_diagnostics`` reports the plan's **already-computed** warnings — the same
state the canvas paints as badges — rather than recomputing anything. The Qt
main thread harvests each garden item's current flags into plain dicts (see
``ProjectManager.diagnostics_snapshot``); this module turns those records into
:class:`~open_garden_planner.agent_api.schema.Diagnostic` entries. No PyQt6, no
mcp — unit-testable without a GUI.

One record may yield several diagnostics (a plant can be both crowded and next to
an antagonist). Positive indicators are intentionally NOT reported: spacing
``"ideal"`` and rotation ``"good"`` are good-state markers, not warnings.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.schema import Diagnostic


def _label(record: dict[str, Any]) -> str:
    return str(
        record.get("name") or record.get("object_type") or record.get("item_id") or "Object"
    )


def diagnostics_from_records(
    records: list[dict[str, Any]], *, kind: str | None = None
) -> list[Diagnostic]:
    """Expand harvested warning-flag records into diagnostics, optionally filtered."""
    out: list[Diagnostic] = []
    for record in records:
        label = _label(record)
        ids = [str(record.get("item_id", ""))]

        if record.get("antagonist_warning"):
            out.append(
                Diagnostic(
                    kind="companion_conflict",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} has an antagonistic plant within companion range.",
                )
            )
        if record.get("spacing_overlap") == "overlap":
            out.append(
                Diagnostic(
                    kind="spacing_overlap",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} is closer than its spacing radius to a neighbour.",
                )
            )
        if record.get("capacity_overrun"):
            out.append(
                Diagnostic(
                    kind="capacity_overrun",
                    severity="warning",
                    item_ids=ids,
                    message=f"{label} holds more plant footprint than its container fits.",
                )
            )
        soil = record.get("soil_mismatch_level")
        if soil in ("warning", "critical"):
            out.append(
                Diagnostic(
                    kind="soil_mismatch",
                    severity=str(soil),
                    item_ids=ids,
                    message=f"{label} is in soil/pH that does not match its requirements.",
                )
            )
        rotation = record.get("rotation_status")
        if rotation in ("suboptimal", "violation"):
            out.append(
                Diagnostic(
                    kind="crop_rotation",
                    severity="critical" if rotation == "violation" else "warning",
                    item_ids=ids,
                    message=f"{label} conflicts with crop-rotation guidance ({rotation}).",
                )
            )

    if kind is not None:
        out = [d for d in out if d.kind == kind]
    return out
