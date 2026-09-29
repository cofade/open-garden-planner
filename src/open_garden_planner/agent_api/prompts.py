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

from typing import Any

from open_garden_planner.agent_api.schema import (
    CompatibleSet,
    Diagnostic,
    ObjectRef,
    PlanSummary,
)

# describe-garden inlines the full object list; cap it so a very large garden
# can't balloon the prompt — the text itself points agents at list_objects/
# get_object for anything beyond this.
_MAX_DESCRIBED_OBJECTS = 50


def _file_status_line(summary: PlanSummary) -> str:
    if summary.file_name is None:
        return "- File: (unsaved)"
    suffix = " (unsaved changes)" if summary.is_dirty else ""
    return f"- File: {summary.file_name}{suffix}"


def render_audit_plan_prompt(summary: PlanSummary, diagnostics: list[Diagnostic]) -> str:
    """Compose an audit request: current layout + warnings, ask for improvements."""
    lines = [
        "Audit the garden plan currently open in Open Garden Planner.",
        "",
        "## Plan summary",
        _file_status_line(summary),
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
        _file_status_line(summary),
        f"- Canvas: {summary.canvas_width_cm:.0f} x {summary.canvas_height_cm:.0f} cm",
        f"- Beds/containers: {summary.bed_count}",
        f"- Plants: {summary.plant_count}",
        f"- Other shapes: {summary.shape_count}",
        "",
        "## Objects",
    ]
    if objects:
        for obj in objects[:_MAX_DESCRIBED_OBJECTS]:
            label = obj.name or obj.object_type or obj.type
            lines.append(
                f"- {label} ({obj.type}) at ({obj.center_x_cm:.0f}, "
                f"{obj.center_y_cm:.0f}) cm, {obj.width_cm:.0f}x{obj.height_cm:.0f} cm"
                + (f", layer '{obj.layer_name}'" if obj.layer_name else "")
            )
        if len(objects) > _MAX_DESCRIBED_OBJECTS:
            remaining = len(objects) - _MAX_DESCRIBED_OBJECTS
            lines.append(f"- ...and {remaining} more — use list_objects for the full list.")
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


def render_plan_polyculture_bed_prompt(
    bed_id: str,
    compatible_sets: list[CompatibleSet],
    existing_plants: list[str],
    conflicts: list[dict[str, Any]] | None = None,
    uncovered: list[str] | None = None,
    searched_size: int | None = None,
) -> str:
    """Compose a polyculture bed planning request (US-D3.1).

    Args:
        bed_id: The bed to plan for.
        compatible_sets: Compatible sets, already ranked by how many of the
            bed's current plants each one satisfies (``find_sets_for_bed``).
        existing_plants: Species keys already in the bed.
        conflicts: Bed plants genuinely antagonistic to another bed plant.
            Naming them is what keeps an empty result from reading as "add more
            plants", which cannot help.
        uncovered: Bed plants in no returned set. Deliberately NOT called a
            conflict — absent from a 3-set is not a clash.
        searched_size: The set size actually searched, when it differs from the
            requested one.

    Returns:
        Prompt text asking the agent to plan a polyculture bed.
    """
    conflicts = conflicts or []
    uncovered = uncovered or []
    lines = [
        f"Plan a polyculture bed for bed '{bed_id}'.",
        "",
    ]
    if existing_plants:
        lines.append(f"Already planted: {', '.join(existing_plants)}")
        lines.append("")

    if conflicts:
        lines.append("## Conflicts among the plants already in this bed")
        for conflict in conflicts:
            clashes = conflict.get("antagonistic_to", [])
            lines.append(
                f"- {conflict['species_key']} is antagonistic to "
                f"{', '.join(clashes)} (also in this bed)"
            )
        lines.append("")

    if uncovered and not conflicts:
        lines.append("## Plants not included in any set below")
        lines.append(
            "- " + ", ".join(uncovered) + " — no clash on record; simply not a"
            " member of the sets found, which is not a conflict"
        )
        lines.append("")

    if compatible_sets:
        header = "## Compatible sets (ranked by how much of the bed they keep)"
        if searched_size:
            header = (
                f"## Compatible sets of {searched_size} plants "
                "(ranked by how much of the bed they keep)"
            )
        lines.append(header)
        for i, s in enumerate(compatible_sets[:5], 1):
            keeps = ", ".join(s.covers) if s.covers else "none of the current plants"
            all_current = " — keeps everything" if s.covers_all else ""
            lines.append(
                f"{i}. {', '.join(s.members)} (score: {s.score:.1f}, "
                f"coverage: {s.coverage}, keeps: {keeps}{all_current})"
            )
        lines.append("")
        lines.append(
            "Choose the set that agrees with the most of what is already "
            "planted. If the conflicts above rule out keeping everything, say "
            "which plant should move, and explain your reasoning."
        )
    else:
        lines.append(
            "No compatible set was found among the plants already in this bed "
            "and their companions."
        )
        if conflicts:
            lines[-1] += (
                " The plants listed under conflicts above are why: adding more "
                "species cannot fix a pair that is already antagonistic."
            )
        else:
            lines[-1] += " Try a different bed, or different species."
    lines.append("")
    lines.append(
        "Use the suggest_companions and find_sets_for_bed tools if you need "
        "more options. find_compatible_sets searches a candidate palette you "
        "name and does not know what is already planted, so it is the right "
        "tool only when you are not asking about a specific bed."
    )
    return "\n".join(lines)
