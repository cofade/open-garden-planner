"""Read-analysis prompt text builders for the Agent API (US-D1.5).

Pure (Qt-free, mcp-free) functions that compose already-fetched schema objects
(:class:`~open_garden_planner.agent_api.schema.PlanSummary`,
:class:`~open_garden_planner.agent_api.schema.Diagnostic`,
:class:`~open_garden_planner.agent_api.schema.ObjectRef`) into English prompt
text. Read-only, v1 (no write/guided-edit prompts — that is D3). Kept separate
from ``server.py`` so the text composition is unit-testable without mcp/Qt,
mirroring ``mapping.py``/``diagnostics.py``.
"""

from __future__ import annotations

from open_garden_planner.agent_api.schema import Diagnostic, ObjectRef, PlanSummary


def render_audit_plan_prompt(summary: PlanSummary, diagnostics: list[Diagnostic]) -> str:
    """Compose an audit request: current layout + warnings, ask for improvements."""
    lines = [
        "Audit the garden plan currently open in Open Garden Planner.",
        "",
        "## Plan summary",
        f"- File: {summary.file_name or '(unsaved)'}"
        + (" (unsaved changes)" if summary.is_dirty else ""),
        f"- Canvas: {summary.canvas_width_cm:.0f} x {summary.canvas_height_cm:.0f} cm",
        f"- Beds/containers: {summary.bed_count}",
        f"- Plants: {summary.plant_count}",
        f"- Other shapes: {summary.shape_count}",
        f"- Layers: {', '.join(summary.layer_names) or '(none)'}",
        "",
        "## Current warnings",
    ]
    if diagnostics:
        for d in diagnostics:
            lines.append(f"- [{d.severity}] {d.kind}: {d.message}")
    else:
        lines.append("- (none — no active warnings)")
    lines += [
        "",
        "Review the layout and warnings above. Identify the most impactful "
        "issues (spacing, companion conflicts, soil mismatches, crop rotation, "
        "or container capacity) and suggest concrete improvements, in priority "
        "order. Use the list_objects/get_object/get_diagnostics tools if you "
        "need more detail on a specific object.",
    ]
    return "\n".join(lines)


def render_describe_garden_prompt(summary: PlanSummary, objects: list[ObjectRef]) -> str:
    """Compose a narrative-description request from the plan summary + object list."""
    lines = [
        "Describe the garden plan currently open in Open Garden Planner in "
        "plain, narrative language for a human reader.",
        "",
        "## Plan summary",
        f"- File: {summary.file_name or '(unsaved)'}",
        f"- Canvas: {summary.canvas_width_cm:.0f} x {summary.canvas_height_cm:.0f} cm",
        f"- Beds/containers: {summary.bed_count}",
        f"- Plants: {summary.plant_count}",
        f"- Other shapes: {summary.shape_count}",
        "",
        "## Objects",
    ]
    if objects:
        for obj in objects:
            label = obj.name or obj.object_type or obj.type
            lines.append(
                f"- {label} ({obj.type}) at ({obj.center_x_cm:.0f}, "
                f"{obj.center_y_cm:.0f}) cm, {obj.width_cm:.0f}x{obj.height_cm:.0f} cm"
                + (f", layer '{obj.layer_name}'" if obj.layer_name else "")
            )
    else:
        lines.append("- (the plan is empty)")
    lines += [
        "",
        "Write a short, friendly narrative description of this garden: its "
        "overall layout, what's planted where, and anything notable about its "
        "size or organization. Use the list_objects/get_object tools if you "
        "need more detail on a specific object.",
    ]
    return "\n".join(lines)
