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
    AmendmentPlanView,
    CompatibleSet,
    Diagnostic,
    ObjectRef,
    PlanSummary,
    SoilMismatchListView,
    SoilStatus,
    SuccessionGap,
    SuccessionPlanView,
    SuccessionSuggestion,
    TaskCalendarView,
    TaskListView,
    TaskView,
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


def render_plan_succession_prompt(
    bed_id: str,
    plan: SuccessionPlanView,
    gaps: list[SuccessionGap],
    candidates: list[SuccessionSuggestion],
) -> str:
    """Compose the ``plan-succession`` brief (US-D3.2).

    The plan, its gaps and the ranked candidates are supplied by the caller so
    this stays a pure renderer; the agent-facing text is English by contract
    (ADR-033: MCP surfaces are an English API).
    """
    lines = [
        f"# Succession plan for bed {bed_id} ({plan.year})",
        "",
    ]

    if plan.segments_are_fallback:
        lines.append(
            "NOTE: this plan has no geo-location, so there are no frost dates "
            "and the season segments below are approximate calendar-month "
            "boundaries rather than computed from a climate. Say so when you "
            "propose dates, and prefer the plan's existing slots as anchors."
        )
        lines.append("")

    if plan.entries:
        lines.append("## Current slots")
        for entry in plan.entries:
            season = entry.season or "outside the growing season"
            marker = " (running now)" if (
                plan.current_entry is not None
                and plan.current_entry.id == entry.id
            ) else ""
            lines.append(
                f"- {entry.common_name or entry.species_key}: "
                f"{entry.start_date} to {entry.end_date} ({season}){marker}"
            )
        lines.append("")
    else:
        lines.append(
            "This bed has no succession plan yet, so the whole growing season "
            "is open."
        )
        lines.append("")

    if gaps:
        lines.append("## Uncovered windows")
        for gap in gaps:
            lines.append(
                f"- {gap.start_date} to {gap.end_date} "
                f"({gap.segment}, {gap.days} days)"
            )
        lines.append("")
    else:
        lines.append("Every growing-season window is already covered.")
        lines.append("")

    if candidates:
        lines.append("## Ranked candidates for the first open window")
        for i, c in enumerate(candidates[:8], 1):
            fit = "fits" if c.fits_window else "fit unconfirmed or too slow"
            maturity = (
                f"~{c.days_to_maturity} days"
                if c.days_to_maturity is not None
                else "maturity unknown"
            )
            lines.append(f"{i}. {c.name} ({maturity}, {fit})")
        lines.append("")
    else:
        lines.append(
            "No candidate survived the rotation and antagonism filters for the "
            "open window. Either widen the candidate species list, or accept "
            "that this window is best left empty."
        )
        lines.append("")

    lines.extend(
        [
            "Propose a full-season plan for this bed: a slot for each "
            "uncovered window, with species and start/end dates that do not "
            "overlap each other or the slots already there.",
            "",
            "When you write it back with set_succession_plan, send the COMPLETE "
            "slot list for the year - that call replaces the plan rather than "
            "appending to it. That is one undo step, so a single undo restores "
            "the previous plan.",
        ]
    )
    return "\n".join(lines)


def render_plan_my_week_prompt(
    task_list: TaskListView,
    calendar: TaskCalendarView,
    summary: PlanSummary,
    diagnostics: list[Diagnostic],
) -> str:
    """Compose the ``plan-my-week`` brief (US-D3.3).

    The task window, the month overview, the plan summary and the diagnostics
    are supplied by the caller so this stays a pure renderer; the agent-facing
    text is English by contract (ADR-033: MCP surfaces are an English API).

    The task TITLES inside the brief are display strings in the user's UI
    language, passed through from the generator — the brief therefore tells the
    agent to branch on ``task_type`` and ``source`` and never to match a title.
    """
    lines = [
        f"# Garden week plan (reference date {task_list.today})",
        "",
    ]

    if task_list.coverage == "no_frost_dates":
        lines.append(
            "NOTE: this plan has no geo-location, so there are no frost dates "
            "and NO calendar or propagation tasks could be generated. The tasks "
            "below are only the manual, succession, soil and frost ones. Do not "
            "tell the user the week is empty - say that the planting calendar "
            "cannot be computed until a location is set, and offer to plan from "
            "the manual tasks that do exist."
        )
        lines.append("")

    urgent = [t for t in task_list.tasks if t.urgency in ("overdue", "today")]
    soon = [t for t in task_list.tasks if t.urgency == "this_week"]
    later = [
        t
        for t in task_list.tasks
        if t.urgency == "upcoming" or t.urgency is None
    ]

    lines.append(
        f"Window {task_list.from_date} to {task_list.to_date}: "
        f"{task_list.total} tasks. {calendar.total} task-months across "
        f"{len(calendar.months)} month(s) in {calendar.year}."
    )
    lines.append("")

    def _block(heading: str, rows: list[TaskView]) -> None:
        lines.append(f"## {heading}")
        if not rows:
            lines.append("- none")
        for task in rows:
            bits = [f"{task.start_date} to {task.end_date}", f"[{task.source}]"]
            if task.bed_id:
                bits.append(f"bed {task.bed_id}")
            if task.status != "open":
                bits.append(f"status: {task.status}")
            lines.append(f"- {task.task_type} ({task.title}): " + "; ".join(bits))
        lines.append("")

    _block("Overdue and due today", urgent)
    _block("Due this week", soon)
    _block("Later in the window", later)

    lines.append("## Plan")
    lines.append(
        f"- {summary.bed_count} bed(s), {summary.plant_count} plant(s), "
        f"{len(diagnostics)} active diagnostic(s)."
    )
    lines.append("")
    if diagnostics:
        lines.append("Open diagnostics:")
        for diag in diagnostics[:10]:
            lines.append(f"- {diag.kind}: {diag.message}")
        lines.append("")

    lines.extend(
        [
            "Produce a prioritised plan for the next seven days.",
            "",
            "Order the work by what is time-critical (overdue first, then "
            "frost-sensitive, then soil preparation before sowing), and say "
            "which tasks can slip a few days without harm.",
            "",
            "Branch on `task_type` and `source`, never on `title` or `notes`: "
            "those are display strings in the user's UI language.",
            "",
            "You can file new work with add_manual_task (one undo step each). "
            "You cannot dismiss or complete an existing task: generated tasks "
            "are derived state, and completing one is not an undoable agent "
            "write, so the user does that themselves.",
        ]
    )
    return "\n".join(lines)


def render_plan_soil_amendments_prompt(
    status: SoilStatus,
    plan: AmendmentPlanView,
    mismatches: SoilMismatchListView,
    planted: list[str],
) -> str:
    """Compose the ``plan-soil-amendments`` brief (US-D3.4).

    The amendment display names and mismatch reasons inside the brief are
    display strings in the user's UI language, passed through from the engine —
    the brief therefore tells the agent to branch on ``amendment_id`` and
    ``reason_codes`` and never to match on the prose.
    """
    lines = [
        f"# Soil amendment plan for bed {status.bed_id}",
        "",
    ]

    if status.coverage == "no_soil_test":
        lines.append(
            "This bed has no soil test, and the plan has no default either, so "
            "there is nothing to base a recommendation on. Do NOT describe the "
            "soil as fine - untested is not healthy. Ask the user for a soil "
            "test, or offer to record one with record_soil_test if they have "
            "kit readings to hand."
        )
        lines.append("")
        return "\n".join(lines)

    source_note = {
        "bed": "its own most recent test",
        "global": "the PLAN-WIDE default, because this bed has no test of its "
        "own - say which readings are the default's, not the bed's",
    }.get(status.record_source, "an unknown record source")
    lines.append(
        f"Readings come from {source_note} (tested {status.test_date or 'unknown'}"
        f"{', OVERDUE - retest before relying on these' if status.is_test_overdue else ''})."
    )
    lines.append(
        f"- Overall soil health: {status.overall_health_level}"
    )
    if status.ph is not None:
        lines.append(
            f"- pH {status.ph} ({status.ph_health_level})"
        )
    for kind, reading in status.levels.items():
        if reading.level is None:
            continue
        lines.append(f"- {kind}: level {reading.level} ({reading.health_level})")
    lines.append("")

    if planted:
        lines.append("## Growing here")
        for name in planted:
            lines.append(f"- {name}")
        lines.append("")
    else:
        lines.append("Nothing is planted in this bed.")
        lines.append("")

    if mismatches.total:
        lines.append("## Plants that disagree with this soil")
        for m in mismatches.mismatches:
            lines.append(
                f"- {m.common_name or m.species_key}: "
                + ", ".join(m.reason_codes)
            )
        lines.append("")

    if plan.recommendations:
        lines.append("## Recommended amendments")
        for rec in plan.recommendations:
            lines.append(
                f"- {rec.display_name} ({rec.amendment_id}): "
                f"{rec.quantity_g:.0f} g, targets {rec.target_kind} "
                f"{rec.current_value} -> {rec.target_value}"
            )
        lines.append("")
    else:
        lines.append(
            "The engine recommends no amendment from the readings it can assess. "
            "This does not prove that the soil is healthy or every value is near "
            "target: lab ppm readings are not converted to kit levels."
        )
        lines.append("")

    lines.extend(
        [
            "Propose a prioritised amendment plan WITH TIMING: which amendment "
            "goes on first and why, how long before sowing or planting each "
            "crop, and whether the reading is too old to act on.",
            "",
            "Branch on `amendment_id` and `reason_codes`, never on "
            "`display_name` or `reasons`: those are display strings in the "
            "user's UI language.",
            "",
            "record_soil_test takes the Rapitest KIT scale (categorical "
            "integers), not lab ppm. It runs one undo step, so a single undo "
            "removes the test you recorded.",
        ]
    )
    return "\n".join(lines)
