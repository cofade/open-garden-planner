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

from open_garden_planner.core.frost_dates import parse_frost
from open_garden_planner.models.propagation import PropagationPlan, compute_propagation_plan
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

    ``amendment_recs`` is a tuple of ``(stable_name, display_name, rationale)``
    triples and ``mismatch_plants`` a tuple of plant display names whose soil
    preference clashes with the bed — both precomputed by the caller so the
    generators stay Qt-free and need no soil-service import. The caller flattens
    each :class:`~open_garden_planner.models.amendment.AmendmentRecommendation`
    into a small display triple.

    ``stable_name`` is the amendment's English data name and is used verbatim in
    the generated task id, so switching the UI language never changes a task's
    identity (the saved done/snooze state in ``task_states`` is keyed by
    ``task_id``). ``display_name`` is the name in the active UI language and is
    the only part rendered in the task title.
    """

    bed_id: str
    name: str
    amendment_recs: tuple[tuple[str, str, str], ...] = ()
    mismatch_plants: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanState:
    """Immutable snapshot of everything the generators need."""

    today: datetime.date
    year: int
    last_frost: datetime.date | None = None
    # The STORED frost date (``'MM-DD'``), carried separately from the resolved
    # ``last_frost`` above. #414: a ``'02-29'`` frost resolves to 1 March in a
    # non-leap year, so re-deriving the anchor years from ``last_frost`` would
    # round-trip through the substitution and make a 02-29 plan behave exactly
    # like a 03-01 one in EVERY year, leap years included. The anchor-year loop
    # must parse the value the plan actually stores.
    last_frost_mmdd: str | None = None
    plant_rows: tuple[PlantRowInput, ...] = ()
    prop_plans: dict[str, PropagationPlan] = field(default_factory=dict)
    beds: tuple[BedInput, ...] = ()
    # bed_id → raw SuccessionPlan dict (parsed via SuccessionPlan.from_dict here).
    succession_plans: dict[str, dict] = field(default_factory=dict)
    manual_tasks: tuple[ManualTask, ...] = ()
    frost_alerts: tuple[FrostAlert, ...] = ()
    # GUI reminder surfaces keep only actionable generated tasks. Annual agent
    # calendars opt into the complete dated schedule before applying their filter.
    actionable_only: bool = True
    # Inputs retained for rebuilding propagation dates in a requested calendar year.
    propagation_species: dict[str, Any] = field(default_factory=dict)
    propagation_overrides: dict[str, dict] = field(default_factory=dict)
    propagation_seed_packets: dict[str, Any] = field(default_factory=dict)


# ── Urgency classification ───────────────────────────────────────────────────

#: How far ahead/behind ``today`` :func:`classify_urgency` can ever classify. Kept
#: as constants (and mirrored in that function's arithmetic) so the GUI listing
#: span is derived rather than guessed.
_URGENCY_LOOKAHEAD_DAYS = 30
_URGENCY_LOOKBEHIND_DAYS = 14


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
    if 1 <= delta_end <= _URGENCY_LOOKBEHIND_DAYS:
        return "overdue"
    delta_start = (start - today).days
    if 1 <= delta_start <= 7:
        return "this_week"
    if 8 <= delta_start <= _URGENCY_LOOKAHEAD_DAYS:
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

    The SINGLE source of this id format. Both surfaces build the id through here
    via the shared ``build_plan_state`` → ``generate_calendar_tasks`` /
    ``generate_propagation_tasks`` engine (the planting-calendar dashboard adapts
    those tasks in ``planting_calendar_view._adapt_task``), so per-task status keys
    can never diverge across the two surfaces (the #12 desync bug; see ADR-029
    addendum + §11.4). Callers must pass the canonical ``species_key`` (ADR-016).
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
            if state.actionable_only and classify_urgency(start, end, state.today) is None:
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
    """Pricking-out / hardening-off tasks from per-species propagation plans.

    Absolute overridden steps belong to the year of their start date, independent
    of the frost anchor being evaluated. Both GUI and period reads use this id.
    """
    tasks: list[Task] = []
    for row in state.plant_rows:
        plan = state.prop_plans.get(row.species_key)
        if plan is None:
            continue
        for step_id in _PROPAGATION_STEP_IDS:
            step = plan.get_step(step_id)
            if step is None:
                continue
            if state.actionable_only and classify_urgency(step.start_date, step.end_date, state.today) is None:
                continue
            tasks.append(Task(
                task_id=make_calendar_task_id(
                    row.species_key, step_id,
                    step.start_date.year if step.overridden else state.year,
                ),
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
            if sow_date is not None and (not state.actionable_only or classify_urgency(
                sow_date, sow_date, state.today
            ) is not None):
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
            if clear_date is not None and (not state.actionable_only or classify_urgency(
                clear_date, clear_date, state.today
            ) is not None):
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
        for stable_name, display_name, rationale in bed.amendment_recs:
            # Key by amendment identity (not list position) so a done/snooze
            # marker stays pinned to the right amendment if the order changes.
            # The id uses the English data name (stable across UI languages);
            # only the title follows the active language (#408).
            tasks.append(Task(
                task_id=f"soil_amendment:{bed.bed_id}:{stable_name}",
                source="soil",
                task_type="soil_amendment",
                title=f"{display_name} — {bed.name}",
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
        if state.actionable_only and classify_urgency(alert_date, alert_date, state.today) is None:
            continue
        task_type = (
            "frost_alert_red" if alert.severity == "red" else "frost_alert_orange"
        )
        title = QCoreApplication.translate(
            "Tasks", "Frost {temp}°C"
        ).format(temp=f"{alert.min_temp:.1f}")
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
    """Parse an ``'MM-DD'`` frost date for ``year`` (None on failure).

    Thin alias for :func:`open_garden_planner.core.frost_dates.parse_frost`,
    which is the single rule every reader goes through (#414). Kept as a private
    name because the generators call it on every anchor year; the module docstring
    there documents the 29-February substitution.
    """
    return parse_frost(mmdd, year)


def build_plan_state(
    scene: Any,
    project_manager: Any,
    frost_alerts: list | None = None,
    soil_service: Any | None = None,
    prop_plans: dict[str, PropagationPlan] | None = None,
    today: datetime.date | None = None,
    year: int | None = None,
    actionable_only: bool = True,
    include_propagation: bool = False,
) -> PlanState:
    """Snapshot the live scene + project into a Qt-free :class:`PlanState`.

    The single source of the snapshot for **both** task surfaces (the Tasks tab
    and the planting-calendar dashboard). Reuses the same data sources as the
    dashboard (species week-offsets, the location's last-frost date, succession
    plans) and the soil engine (amendment recommendations + mismatch warnings).

    ``prop_plans`` can be supplied by the planting calendar, gated by its
    propagation toggle. ``include_propagation`` builds those plans through the
    same calculator for agent reads, including seed data and user overrides.
    The Tasks tab keeps the default False so its reminder list is unchanged.

    ``year`` selects the calendar/frost year independently of the reference
    date. ``actionable_only=False`` retains dated tasks outside the urgency
    window for annual calendars and explicit agent date windows; the GUI keeps
    the default True. Urgency is always classified against ``today``.

    ``today`` overrides the reference date (US-D3.3). It defaults to the wall
    clock, so both GUI callers are unaffected, but a caller that must be
    reproducible passes it explicitly: every generator and
    :func:`classify_urgency` already reads ``PlanState.today`` rather than
    calling ``date.today()`` themselves, so this one parameter is the whole
    seam. Without it an agent read of "what is due" is untestable (a suite that
    pins "today" silently rots the day after it is written) and an agent cannot
    name the date it reasoned about. This mirrors ``_parse_agent_date`` on the
    application side, which owns parsing and refusal of a malformed value.
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

    today = today or datetime.date.today()
    year = today.year if year is None else year

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
    propagation_species: dict[str, Any] = {}
    seed_links: dict[str, str] = {}
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
                    if include_propagation:
                        propagation_species.setdefault(sp_key, sp)
                        packet_id = (metadata.get("plant_instance") or {}).get("seed_packet_id")
                        if packet_id:
                            seed_links.setdefault(sp_key, packet_id)
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
    overrides: dict[str, dict] = {}
    seed_packets: dict[str, Any] = {}
    if include_propagation:
        from open_garden_planner.models.seed_inventory import get_seed_inventory  # noqa: PLC0415

        overrides = dict(project_manager.propagation_overrides)
        store = get_seed_inventory()
        seed_packets = {key: store.get(packet_id) for key, packet_id in seed_links.items()}
        prop_plans = (
            build_propagation_plans(propagation_species, last_frost, overrides, seed_packets)
            if last_frost is not None else {}
        )

    return PlanState(
        today=today,
        year=year,
        last_frost=last_frost,
        last_frost_mmdd=lsf if last_frost is not None else None,
        plant_rows=tuple(plant_rows),
        prop_plans=dict(prop_plans or {}),
        beds=tuple(beds),
        succession_plans=dict(project_manager.succession_plans),
        manual_tasks=manual_tasks,
        frost_alerts=tuple(frost_alerts or ()),
        actionable_only=actionable_only,
        propagation_species=propagation_species,
        propagation_overrides=overrides,
        propagation_seed_packets=seed_packets,
    )


def build_propagation_plans(
    species: dict[str, Any], last_frost: datetime.date,
    overrides: dict[str, dict], seed_packets: dict[str, Any],
) -> dict[str, PropagationPlan]:
    """The shared GUI/agent propagation calculator, with resolved seed data.

    Reads only its inputs. Absolute user overrides keep their dates; generated
    steps follow the requested year's frost date. No widgets or inventory I/O.
    """
    plans: dict[str, PropagationPlan] = {}
    for key, sp in species.items():
        if sp.indoor_sow_start is None or sp.transplant_start is None:
            continue
        sow_start = last_frost + datetime.timedelta(weeks=sp.indoor_sow_start)
        sow_end = (
            last_frost + datetime.timedelta(weeks=sp.indoor_sow_end)
            if sp.indoor_sow_end is not None else sow_start + datetime.timedelta(days=14)
        )
        germ_min, germ_max = sp.days_to_germination_min, sp.days_to_germination_max
        packet = seed_packets.get(key)
        if packet is not None:
            if packet.germination_days_min is not None:
                germ_min = packet.germination_days_min
            if packet.germination_days_max is not None:
                germ_max = packet.germination_days_max
        plans[key] = compute_propagation_plan(
            species_key=key, sow_start=sow_start, sow_end=sow_end,
            transplant_date=last_frost + datetime.timedelta(weeks=sp.transplant_start),
            germination_days_min=germ_min, germination_days_max=germ_max,
            prick_out_after_days=sp.prick_out_after_days, harden_off_days=sp.harden_off_days,
            overrides=overrides.get(key, {}),
        )
    return plans


def stored_frost_mmdd(state: PlanState) -> str:
    """The ``'MM-DD'`` the plan actually stores, for re-anchoring on another year.

    Prefers :attr:`PlanState.last_frost_mmdd` and falls back to formatting the
    resolved date — the fallback is lossy for a ``'02-29'`` frost in a non-leap
    year (``last_frost`` is already the substituted 1 March), which is exactly why
    the stored value is carried separately (#414, ADR-049).
    """
    if state.last_frost_mmdd:
        return state.last_frost_mmdd
    # No production caller lands here — build_plan_state always sets the field —
    # so this is the hand-built-PlanState path (tests, and any future caller that
    # forgets the field). It is lossy for '02-29', which is exactly why the field
    # exists; the caller below therefore only reaches it for an ordinary date.
    return state.last_frost.strftime("%m-%d") if state.last_frost else ""


def frost_anchor_years(
    state: PlanState, start: datetime.date, end: datetime.date,
) -> list[int]:
    """The years whose frost anchor can produce a window overlapping ``[start, end]``.

    Every frost-relative task is ``frost(anchor_year) + offset weeks``, and the
    offsets are large and negative as well as positive (asparagus harvests 104
    weeks after its frost; garlic is sown 26 weeks *before* it), so the set of
    anchor years that can touch a window is wider than the window's own years.
    Deriving it here — once — is what lets every surface agree: before #414 the
    agent's date-window read did this while the Tasks tab, the dashboard and the
    Gantt each anchored on "today's year" only, so a window anchored on another
    year's frost appeared in the agent and on no GUI surface at all.

    The range is derived from the generated windows themselves (including
    propagation steps), never from a hand-written offset constant, so it stays
    correct when the bundled data changes.
    """
    from dataclasses import replace  # noqa: PLC0415

    first_year, last_year = start.year, end.year
    if state.last_frost is None:
        return [first_year] if first_year == last_year else list(range(first_year, last_year + 1))

    template = replace(state, actionable_only=False)
    relative_tasks = generate_calendar_tasks(template)
    if state.propagation_species:
        relative_tasks += generate_propagation_tasks(replace(
            template, prop_plans=build_propagation_plans(
                state.propagation_species, state.last_frost, {},
                state.propagation_seed_packets,
            ),
        ))
    offsets = [
        (date - state.last_frost).days
        for task in relative_tasks
        for date in (task.start_date, task.end_date)
        if date is not None
    ]
    if offsets:
        first_year = min(first_year, (start - datetime.timedelta(days=max(offsets))).year)
        last_year = max(last_year, (end - datetime.timedelta(days=min(offsets))).year)
    return list(range(first_year, last_year + 1))


def generate_for_date_window(
    state: PlanState, start: datetime.date, end: datetime.date,
) -> list[Task]:
    """Run the shared generators for frost anchors that can overlap the window.

    Uses one immutable snapshot. Absolute-date tasks (manual, succession, soil,
    frost) retain their identity and are deduplicated; frost-relative calendar
    tasks use each year's frost date and canonical year-addressed task ids.
    Species offsets can span several years or precede their frost anchor, so the
    anchor range comes from :func:`frost_anchor_years` — the same derivation the
    GUI surfaces use. Absolute-date overrides do not expand it. Keep canonical
    anchor-year ids, filter by date overlap, and leave urgency relative to
    state.today.
    """
    from dataclasses import replace  # noqa: PLC0415

    if start > end:
        raise ValueError("from_date must be on or before to_date.")
    tasks: dict[str, Task] = {}
    for year in frost_anchor_years(state, start, end):
        last_frost = (
            _parse_frost(stored_frost_mmdd(state), year)
            if state.last_frost is not None else None
        )
        prop_plans = state.prop_plans
        if state.propagation_species:
            prop_plans = (
                build_propagation_plans(
                    state.propagation_species, last_frost, state.propagation_overrides,
                    state.propagation_seed_packets,
                ) if last_frost is not None else {}
            )
        for task in generate_all(replace(state, year=year, last_frost=last_frost, prop_plans=prop_plans)):
            task_start = task.start_date or task.end_date
            task_end = task.end_date or task.start_date
            if task_start is not None and task_end is not None and (task_end < start or task_start > end):
                continue
            tasks.setdefault(task.task_id, task)
    return list(tasks.values())


def generate_actionable_for_surface(
    state: PlanState,
) -> list[Task]:
    """Every task a GUI surface should list, across ALL frost anchor years (#414).

    The single canonical path for the Tasks tab and the planting-calendar
    dashboard. Before #414 both anchored on the current year's frost alone, so a
    task window anchored on another year's frost was invisible on the GUI while
    the agent's ``get_tasks`` listed it — e.g. with a 20 September frost, a
    tomato harvest running 29 November – 7 February vanished from the Tasks tab
    on 1 January.

    This wraps :func:`generate_for_date_window` rather than reimplementing it,
    then re-applies the GUI's own listing rule. That filter is NOT optional:
    ``generate_for_date_window`` internally runs with ``actionable_only=False``
    (an explicit date-window read wants the complete dated schedule), so without
    the post-filter the Tasks tab would list the next decade.

    Two things this must NOT do, both of which a naive filter gets wrong:

    * **Undated tasks stay.** ``classify_urgency`` dereferences both dates, and
      :func:`generate_manual_tasks` emits undated manual tasks (``date=None``).
      Calling it unguarded raises ``TypeError`` and takes both tabs down for a
      plan whose undated task the agent's own ``add_manual_task`` created.
    * **Manual tasks are never urgency-filtered.** That is the documented contract
      of :func:`generate_manual_tasks` — "a far-future or long-past manual
      to-do must still appear in the list" — and ``TasksView._bucket``
      re-derives a bucket for exactly those, including its ``no_date`` case.
      Filtering them here would hide a December task in June, which is the same
      class of bug #414 was opened for, pointed the other way.

    ``state.actionable_only`` is deliberately NOT consulted: this helper exists to
    apply a *specific* listing rule (urgency, plus manual tasks unfiltered), and
    inheriting a second flag from the snapshot is how the anchors got filtered out
    before this function ever ran. Callers that want the raw dated schedule use
    :func:`generate_for_date_window`.
    """
    if state.last_frost is None:
        # No frost anchor: the non-relative generators (manual, succession, soil,
        # frost alerts) are still worth listing, and they carry absolute dates.
        return generate_all(state)

    from dataclasses import replace  # noqa: PLC0415

    # ``classify_urgency`` admits nothing beyond 30 days ahead or 14 behind, so
    # this span is the widest that can ever produce a listed task. It also bounds
    # the anchor-year expansion: a +/-10 year span derived 25 anchor years and ran
    # every generator 25 times on each refresh (~50x the work of a single year).
    span_start = state.today - datetime.timedelta(days=_URGENCY_LOOKBEHIND_DAYS)
    span_end = state.today + datetime.timedelta(days=_URGENCY_LOOKAHEAD_DAYS)
    # actionable_only=False INSIDE the date-window pass: that flag is inherited
    # per anchor year by the generators, so leaving the GUI's True in place would
    # drop anchors whose windows are not currently urgent *before* this function
    # ever sees them. The urgency filter below is the single one that applies.
    tasks = generate_for_date_window(
        replace(state, actionable_only=False), span_start, span_end
    )

    # Manual tasks are added from their OWN generator, not harvested from the
    # date-window pass: they carry absolute dates, so the span above drops a
    # long-past or far-future to-do before this function can exempt it. They need
    # no anchor-year expansion, and ``generate_manual_tasks`` documents that a
    # manual task is never filtered out by urgency.
    listed = {t.task_id for t in tasks}
    tasks = [
        *tasks,
        *(t for t in generate_manual_tasks(state) if t.task_id not in listed),
    ]

    actionable: list[Task] = []
    for task in tasks:
        if task.start_date is None or task.end_date is None:
            # Undated (manual, or defensively any future undated source):
            # cannot be classified, so keep it rather than crash or drop it.
            actionable.append(task)
            continue
        if task.source == "manual":
            # Absolute-date manual task: never urgency-filtered.
            actionable.append(task)
            continue
        if classify_urgency(task.start_date, task.end_date, state.today) is not None:
            actionable.append(task)
    return actionable


def propagate_plans_by_anchor(
    state: PlanState, years: list[int] | None = None,
) -> dict[tuple[str, int], PropagationPlan]:
    """Propagation plans keyed by ``(species_key, anchor_year)`` (#414).

    A species has one plan per frost anchor, because the indoor-sowing and
    transplant steps are frost-relative. Before #414 the GUI kept a single
    ``_prop_plans`` dict built from the current year's frost, which is why the
    Gantt's propagation sub-row could not draw a window anchored on another
    year. The agent already rebuilt plans per anchor year; this is that same
    derivation exposed for the GUI.
    """
    if state.last_frost is None:
        return {}
    anchor_years = years if years is not None else [state.year]
    result: dict[tuple[str, int], PropagationPlan] = {}
    for year in anchor_years:
        last_frost = _parse_frost(stored_frost_mmdd(state), year)
        if last_frost is None:
            continue
        for key, plan in build_propagation_plans(
            state.propagation_species, last_frost, state.propagation_overrides,
            state.propagation_seed_packets,
        ).items():
            result.setdefault((key, year), plan)
    return result


def _bed_amendment_recs(
    bed_id: str, item: Any, soil_service: Any | None
) -> tuple[tuple[str, str, str], ...]:
    """Flatten a bed's amendment recommendations into display triples.

    Returns ``(stable_name, display_name, rationale)`` per recommendation. The
    stable name is the amendment's English data name and keeps the task id
    language-independent; the display name follows the active UI language
    (#408).
    """
    if soil_service is None:
        return ()
    record = soil_service.get_effective_record(bed_id)
    if record is None:
        return ()
    from open_garden_planner.app.settings import active_language  # noqa: PLC0415
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
    lang = active_language()
    recs = SoilService.calculate_amendments(record, bed_area_m2=area_m2)
    triples: list[tuple[str, str, str]] = []
    for rec in recs:
        triples.append((
            rec.amendment.name,
            rec.amendment.display_name(lang),
            f"~{rec.quantity_g:.0f} g",
        ))
    return tuple(triples)


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
