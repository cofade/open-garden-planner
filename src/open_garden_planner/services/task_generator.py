"""Pure, Qt-free task generation engine (US-C2 — task management).

This module turns an immutable snapshot of the project (:class:`PlanState`) into
a flat list of :class:`Task` value objects, gathered from six independent
sources:

* **calendar**     — planting-calendar windows (indoor/direct sow, transplant,
  harvest) derived from species week-offsets + the last-frost date.
* **propagation**  — pricking-out and hardening-off steps from per-species
  :class:`~open_garden_planner.models.propagation.PropagationPlan` instances.
* **succession**   — sow/clear events for each
  :class:`~open_garden_planner.models.succession.SuccessionPlan` entry.
* **soil**         — one task per precomputed amendment recommendation per bed.
* **frost**        — frost-alert reminders from the weather service.
* **manual**       — user-authored :class:`~open_garden_planner.models.task.ManualTask`.

Each generator is a pure function ``(PlanState) -> list[Task]``. They take no
Qt *widgets*, perform no I/O, and never reach back into services — the soil
recommendations, frost alerts and propagation plans are all handed in via the
snapshot. (The module does import ``QCoreApplication`` purely to translate
synthesized labels; ``.translate()`` is safe with no running ``QApplication``.)
This keeps the engine trivially unit-testable and importable without a GUI.

Urgency is *not* stored on a :class:`Task`; it is recomputed at render time via
:func:`classify_urgency`, mirroring the planting-calendar view's logic.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.models.propagation import PropagationPlan
from open_garden_planner.models.succession import SuccessionPlan
from open_garden_planner.models.task import ManualTask
from open_garden_planner.services.weather_service import FrostAlert

# ── Output value object ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Task:
    """An actionable item surfaced to the user.

    Urgency is deliberately omitted — it is a function of the dates and "today",
    and is computed at render time by :func:`classify_urgency`.
    """

    task_id: str
    source: str                              # "calendar" | "propagation" | …
    task_type: str
    title: str
    notes: str = ""
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    bed_id: str | None = None
    species_key: str = ""
    item_ids: tuple[str, ...] = ()
    dismissible: bool = True


# ── Snapshot input value objects ─────────────────────────────────────────────

@dataclass(frozen=True)
class PlantRowInput:
    """One placed plant's species calendar data, frozen for the snapshot.

    The eight calendar fields are week offsets relative to the last frost date
    (negative = before frost), mirroring
    :class:`~open_garden_planner.models.plant_data.PlantSpeciesData`.
    """

    display_name: str
    species_key: str
    indoor_sow_start: int | None = None
    indoor_sow_end: int | None = None
    direct_sow_start: int | None = None
    direct_sow_end: int | None = None
    transplant_start: int | None = None
    transplant_end: int | None = None
    harvest_start: int | None = None
    harvest_end: int | None = None


@dataclass(frozen=True)
class BedInput:
    """A bed plus its precomputed soil tasks.

    ``amendment_recs`` is a tuple of ``(amendment_name, rationale)`` pairs and
    ``mismatch_plants`` a tuple of plant display names whose soil preference
    clashes with the bed — both precomputed by the caller so the generators stay
    Qt-free and need no soil-service import. The caller flattens each
    :class:`~open_garden_planner.models.amendment.AmendmentRecommendation` into a
    small display pair.
    """

    bed_id: str
    name: str
    amendment_recs: tuple[tuple[str, str], ...] = ()
    mismatch_plants: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanState:
    """Immutable snapshot of everything the generators need."""

    today: datetime.date
    year: int
    last_frost: datetime.date | None = None
    plant_rows: tuple[PlantRowInput, ...] = ()
    prop_plans: dict[str, PropagationPlan] = field(default_factory=dict)
    beds: tuple[BedInput, ...] = ()
    # bed_id → raw SuccessionPlan dict (parsed via SuccessionPlan.from_dict here).
    succession_plans: dict[str, dict] = field(default_factory=dict)
    manual_tasks: tuple[ManualTask, ...] = ()
    frost_alerts: tuple[FrostAlert, ...] = ()


# ── Urgency classification ───────────────────────────────────────────────────

def classify_urgency(
    start: datetime.date, end: datetime.date, today: datetime.date
) -> str | None:
    """Return the urgency bucket for a task window, or None if not actionable.

    Mirrors ``planting_calendar_view._classify_urgency`` (the calendar's
    ``coming_up`` bucket is renamed ``upcoming`` here):

    * ``"today"``     — window is open (``start <= today <= end``).
    * ``"overdue"``   — window ended 1–14 days ago.
    * ``"this_week"`` — window starts 1–7 days ahead.
    * ``"upcoming"``  — window starts 8–30 days ahead.
    * ``None``        — outside all of the above.
    """
    if start <= today <= end:
        return "today"
    delta_end = (today - end).days
    if 1 <= delta_end <= 14:
        return "overdue"
    delta_start = (start - today).days
    if 1 <= delta_start <= 7:
        return "this_week"
    if 8 <= delta_start <= 30:
        return "upcoming"
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_iso(value: str) -> datetime.date | None:
    """Parse an ISO date string, returning None on empty/invalid input."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


_CALENDAR_TASK_DEFS: tuple[tuple[str, str, str], ...] = (
    ("indoor_sow", "indoor_sow_start", "indoor_sow_end"),
    ("direct_sow", "direct_sow_start", "direct_sow_end"),
    ("transplant", "transplant_start", "transplant_end"),
    ("harvest", "harvest_start", "harvest_end"),
)

_PROPAGATION_STEP_IDS: tuple[str, ...] = ("prick_out", "harden_off")


def make_calendar_task_id(species_key: str, task_type: str, year: int) -> str:
    """Canonical ``task_id`` for a calendar / propagation task.

    The SINGLE source of this id format. Both this generator and the
    planting-calendar dashboard (``planting_calendar_view._generate_dashboard_tasks``)
    must build the id through here, so per-task status keys can never diverge
    across the two surfaces (the #12 desync bug; see ADR-029 addendum + §11.4).
    Callers are responsible for passing the canonical ``species_key`` (ADR-016).
    """
    return f"{species_key}:{task_type}:{year}"


# ── Generators ───────────────────────────────────────────────────────────────

def generate_calendar_tasks(state: PlanState) -> list[Task]:
    """Calendar tasks from species week-offsets + the last-frost date."""
    if state.last_frost is None:
        return []
    last_frost = state.last_frost
    tasks: list[Task] = []
    for row in state.plant_rows:
        for task_type, start_attr, end_attr in _CALENDAR_TASK_DEFS:
            start_weeks = getattr(row, start_attr)
            end_weeks = getattr(row, end_attr)
            if start_weeks is None or end_weeks is None:
                continue
            start = last_frost + datetime.timedelta(weeks=start_weeks)
            end = last_frost + datetime.timedelta(weeks=end_weeks)
            if classify_urgency(start, end, state.today) is None:
                continue
            tasks.append(Task(
                task_id=make_calendar_task_id(row.species_key, task_type, state.year),
                source="calendar",
                task_type=task_type,
                title=row.display_name,
                start_date=start,
                end_date=end,
                species_key=row.species_key,
                dismissible=False,
            ))
    return tasks


def generate_propagation_tasks(state: PlanState) -> list[Task]:
    """Pricking-out / hardening-off tasks from per-species propagation plans."""
    tasks: list[Task] = []
    for row in state.plant_rows:
        plan = state.prop_plans.get(row.species_key)
        if plan is None:
            continue
        for step_id in _PROPAGATION_STEP_IDS:
            step = plan.get_step(step_id)
            if step is None:
                continue
            if classify_urgency(step.start_date, step.end_date, state.today) is None:
                continue
            tasks.append(Task(
                task_id=make_calendar_task_id(row.species_key, step_id, state.year),
                source="propagation",
                task_type=step_id,
                title=row.display_name,
                start_date=step.start_date,
                end_date=step.end_date,
                species_key=row.species_key,
                dismissible=False,
            ))
    return tasks


def generate_succession_tasks(state: PlanState) -> list[Task]:
    """Sow + clear tasks for each succession-plan entry."""
    tasks: list[Task] = []
    for bed_id, raw in state.succession_plans.items():
        plan = SuccessionPlan.from_dict(raw)
        for entry in plan.entries:
            sow_date = _parse_iso(entry.start_date)
            if sow_date is not None and classify_urgency(
                sow_date, sow_date, state.today
            ) is not None:
                tasks.append(Task(
                    task_id=f"succession:sow:{bed_id}:{entry.id}",
                    source="succession",
                    task_type="succession_sow",
                    title=entry.common_name,
                    start_date=sow_date,
                    end_date=sow_date,
                    bed_id=bed_id,
                    species_key=entry.species_key,
                ))
            clear_date = _parse_iso(entry.end_date)
            if clear_date is not None and classify_urgency(
                clear_date, clear_date, state.today
            ) is not None:
                tasks.append(Task(
                    task_id=f"succession:clear:{bed_id}:{entry.id}",
                    source="succession",
                    task_type="succession_clear",
                    title=entry.common_name,
                    start_date=clear_date,
                    end_date=clear_date,
                    bed_id=bed_id,
                    species_key=entry.species_key,
                ))
    return tasks


def generate_soil_amendment_tasks(state: PlanState) -> list[Task]:
    """One task per precomputed amendment recommendation per bed (always due today)."""
    tasks: list[Task] = []
    for bed in state.beds:
        for name, rationale in bed.amendment_recs:
            # Key by amendment identity (not list position) so a done/snooze
            # marker stays pinned to the right amendment if the order changes.
            tasks.append(Task(
                task_id=f"soil_amendment:{bed.bed_id}:{name}",
                source="soil",
                task_type="soil_amendment",
                title=f"{name} — {bed.name}",
                notes=rationale,
                bed_id=bed.bed_id,
                start_date=state.today,
                end_date=state.today,
            ))
    return tasks


def generate_soil_mismatch_tasks(state: PlanState) -> list[Task]:
    """One warning per bed whose child plants prefer different soil (US-12.10d)."""
    tasks: list[Task] = []
    for bed in state.beds:
        if not bed.mismatch_plants:
            continue
        title = QCoreApplication.translate(
            "Tasks", "Soil mismatch in {bed}: {plants}"
        ).format(bed=bed.name, plants=", ".join(bed.mismatch_plants))
        tasks.append(Task(
            task_id=f"soil_mismatch:{bed.bed_id}",
            source="soil",
            task_type="soil_mismatch",
            title=title,
            bed_id=bed.bed_id,
            start_date=state.today,
            end_date=state.today,
            dismissible=True,
        ))
    return tasks


def generate_frost_tasks(state: PlanState) -> list[Task]:
    """Frost-alert reminder tasks from the weather service's alerts."""
    tasks: list[Task] = []
    for alert in state.frost_alerts:
        alert_date = _parse_iso(alert.date)
        if alert_date is None:
            continue
        if classify_urgency(alert_date, alert_date, state.today) is None:
            continue
        task_type = (
            "frost_alert_red" if alert.severity == "red" else "frost_alert_orange"
        )
        title = QCoreApplication.translate(
            "Tasks", "Frost {temp}°C"
        ).format(temp=alert.min_temp)
        tasks.append(Task(
            task_id=f"frost:{alert.date}:{alert.severity}",
            source="frost",
            task_type=task_type,
            title=title,
            start_date=alert_date,
            end_date=alert_date,
            item_ids=tuple(alert.affected_plant_ids),
        ))
    return tasks


def generate_manual_tasks(state: PlanState) -> list[Task]:
    """User-authored tasks — always emitted, regardless of how far the date is.

    Unlike the generated sources, a manual task is never filtered out by
    urgency: a far-future or long-past manual to-do must still appear in the
    list. An undated manual task has ``start_date``/``end_date`` of ``None``.
    """
    tasks: list[Task] = []
    for manual in state.manual_tasks:
        due = _parse_iso(manual.date)
        tasks.append(Task(
            task_id=manual.id,
            source="manual",
            task_type="manual",
            title=manual.title,
            notes=manual.notes,
            start_date=due,
            end_date=due,
            bed_id=manual.bed_id,
        ))
    return tasks


# ── Aggregation ──────────────────────────────────────────────────────────────

GeneratorFn = Callable[[PlanState], list[Task]]

GENERATORS: list[GeneratorFn] = [
    generate_calendar_tasks,
    generate_propagation_tasks,
    generate_succession_tasks,
    generate_soil_amendment_tasks,
    generate_soil_mismatch_tasks,
    generate_frost_tasks,
    generate_manual_tasks,
]


def generate_all(state: PlanState) -> list[Task]:
    """Run every generator and return a flat, ``task_id``-deduplicated list.

    On a ``task_id`` collision the first task wins (generator order in
    :data:`GENERATORS`).
    """
    seen: set[str] = set()
    result: list[Task] = []
    for generator in GENERATORS:
        for task in generator(state):
            if task.task_id in seen:
                continue
            seen.add(task.task_id)
            result.append(task)
    return result


# ── Snapshot builder (shared by the Tasks tab and the planting-calendar) ───────

def _parse_frost(mmdd: str, year: int) -> datetime.date | None:
    """Parse an ``'MM-DD'`` frost date for ``year`` (None on failure)."""
    try:
        m, d = (int(x) for x in mmdd.split("-"))
        return datetime.date(year, m, d)
    except (ValueError, AttributeError):
        return None


def build_plan_state(
    scene: Any,
    project_manager: Any,
    frost_alerts: list | None = None,
    soil_service: Any | None = None,
    prop_plans: dict[str, PropagationPlan] | None = None,
) -> PlanState:
    """Snapshot the live scene + project into a Qt-free :class:`PlanState`.

    The single source of the snapshot for **both** task surfaces (the Tasks tab
    and the planting-calendar dashboard). Reuses the same data sources as the
    dashboard (species week-offsets, the location's last-frost date, succession
    plans) and the soil engine (amendment recommendations + mismatch warnings).

    ``prop_plans`` is supplied only by the planting calendar (its precomputed
    per-species propagation plans, gated by the calendar's propagation toggle);
    the Tasks tab passes ``None`` so pricking-out / hardening-off steps stay
    calendar-only.
    """
    from open_garden_planner.core.object_types import (  # noqa: PLC0415
        get_translated_display_name,
        is_bed_type,
    )
    from open_garden_planner.models.plant_data import (  # noqa: PLC0415
        PlantSpeciesData,
        species_key,
    )
    from open_garden_planner.models.task import ManualTask  # noqa: PLC0415

    today = datetime.date.today()
    year = today.year

    last_frost: datetime.date | None = None
    location = project_manager.location or {}
    frost_dates = location.get("frost_dates") or {}
    lsf = frost_dates.get("last_spring_frost")
    if lsf:
        last_frost = _parse_frost(lsf, year)

    all_items = list(scene.items()) if scene is not None else []
    items_by_id = {
        str(getattr(item, "item_id", "")): item for item in all_items
    }

    plant_rows: list[PlantRowInput] = []
    beds: list[BedInput] = []
    for item in all_items:
        object_type = getattr(item, "object_type", None)
        metadata = getattr(item, "metadata", None) or {}
        ps_dict = metadata.get("plant_species") if isinstance(metadata, dict) else None
        if ps_dict:
            try:
                sp = PlantSpeciesData.from_dict(ps_dict)
            except Exception:
                sp = None
            if sp is not None:
                # MUST match the planting-calendar dashboard's key derivation
                # (canonical species_key, ADR-016: source_id → scientific →
                # common, lowercased) so the generated task_ids align and
                # done/snooze status syncs across both surfaces (#188 #12).
                sp_key = species_key({
                    "source_id": sp.source_id,
                    "scientific_name": sp.scientific_name,
                    "common_name": sp.common_name,
                })
                if sp_key != "_unknown":
                    plant_rows.append(PlantRowInput(
                        display_name=(getattr(item, "name", "") or sp.common_name or sp_key),
                        species_key=sp_key,
                        indoor_sow_start=sp.indoor_sow_start,
                        indoor_sow_end=sp.indoor_sow_end,
                        direct_sow_start=sp.direct_sow_start,
                        direct_sow_end=sp.direct_sow_end,
                        transplant_start=sp.transplant_start,
                        transplant_end=sp.transplant_end,
                        harvest_start=sp.harvest_start,
                        harvest_end=sp.harvest_end,
                    ))
        if is_bed_type(object_type):
            bed_id = str(getattr(item, "item_id", ""))
            if not bed_id:
                continue
            name = getattr(item, "name", "") or get_translated_display_name(object_type)
            beds.append(BedInput(
                bed_id=bed_id,
                name=name,
                amendment_recs=_bed_amendment_recs(bed_id, item, soil_service),
                mismatch_plants=_bed_mismatch_plants(item, items_by_id, soil_service),
            ))

    manual_tasks = tuple(
        ManualTask.from_dict(d) for d in project_manager.manual_tasks.values()
    )

    return PlanState(
        today=today,
        year=year,
        last_frost=last_frost,
        plant_rows=tuple(plant_rows),
        prop_plans=dict(prop_plans or {}),
        beds=tuple(beds),
        succession_plans=dict(project_manager.succession_plans),
        manual_tasks=manual_tasks,
        frost_alerts=tuple(frost_alerts or ()),
    )


def _bed_amendment_recs(
    bed_id: str, item: Any, soil_service: Any | None
) -> tuple[tuple[str, str], ...]:
    """Flatten a bed's amendment recommendations into (name, rationale) pairs."""
    if soil_service is None:
        return ()
    record = soil_service.get_effective_record(bed_id)
    if record is None:
        return ()
    from open_garden_planner.core.measurements import (  # noqa: PLC0415
        calculate_area_and_perimeter,
    )
    from open_garden_planner.services.soil_service import SoilService  # noqa: PLC0415

    result = calculate_area_and_perimeter(item)
    if result is None:
        return ()
    area_m2 = result[0] / 10_000.0
    if area_m2 <= 0.0:
        return ()
    recs = SoilService.calculate_amendments(record, bed_area_m2=area_m2)
    pairs: list[tuple[str, str]] = []
    for rec in recs:
        name = rec.amendment.display_name()
        pairs.append((name, f"~{rec.quantity_g:.0f} g"))
    return tuple(pairs)


def _bed_mismatch_plants(
    item: Any, items_by_id: dict[str, Any], soil_service: Any | None
) -> tuple[str, ...]:
    """Names of a bed's child plants whose soil preference clashes (US-12.10d)."""
    if soil_service is None:
        return ()
    from open_garden_planner.models.plant_data import PlantSpeciesData  # noqa: PLC0415
    from open_garden_planner.services.soil_service import SoilService  # noqa: PLC0415

    bed_id = str(getattr(item, "item_id", ""))
    record = soil_service.get_effective_record(bed_id)
    child_ids = {str(c) for c in getattr(item, "_child_item_ids", [])}
    specs: list[PlantSpeciesData] = []
    for cid in child_ids:
        child = items_by_id.get(cid)
        if child is None:
            continue
        metadata = getattr(child, "metadata", None) or {}
        ps_dict = metadata.get("plant_species") if isinstance(metadata, dict) else None
        if ps_dict and isinstance(ps_dict, dict):
            try:
                specs.append(PlantSpeciesData.from_dict(ps_dict))
            except Exception:
                continue
    mismatches = SoilService.get_mismatched_plants(record, specs)
    return tuple(s.common_name or s.scientific_name or "?" for s, _ in mismatches)
