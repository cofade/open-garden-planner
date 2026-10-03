"""Qt-free domain-intelligence functions for the Agent API.

US-D3.1 (#319) added the companion wrappers; US-D3.2 (#331) added the
succession ones. They are deliberately Qt-free and operate on plain data,
making them unit-testable without a GUI.

The actual service instances are injected by the provider callables in
``application.py``, so this module never constructs its own service.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from open_garden_planner.agent_api.schema import (
    AmendmentPlanView,
    AmendmentRecommendationView,
    CompanionSuggestion,
    CompatibleSet,
    PlacementCheck,
    SeasonSegment,
    SoilMismatchListView,
    SoilMismatchView,
    SoilReading,
    SoilStatus,
    SuccessionEntryView,
    SuccessionGap,
    SuccessionPlanView,
    SuccessionSuggestion,
    TaskCalendarBucket,
    TaskCalendarView,
    TaskListView,
    TaskView,
)
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.models.succession import (
    SEASON_SEGMENTS,
    SuccessionEntry,
    SuccessionPlan,
    date_to_segment,
    resolve_season_segments,
)
from open_garden_planner.services.companion_planting_service import (
    ANTAGONISTIC,
    BENEFICIAL,
    CompanionPlantingService,
)
from open_garden_planner.services.companion_sets import (
    find_compatible_sets,
    suggest_companions,
)
from open_garden_planner.services.task_generator import classify_urgency
from open_garden_planner.services.task_status import effective_status


def suggest_companions_for_agent(
    service: CompanionPlantingService,
    species_key: str,
    *,
    exclude_antagonists_of: list[str] | None = None,
) -> list[CompanionSuggestion]:
    """Suggest companion plants for a species, ranked by benefit.

    Args:
        service: The companion planting service.
        species_key: The species to find companions for.
        exclude_antagonists_of: Species keys whose antagonists should be
            excluded from suggestions.

    Returns:
        A list of CompanionSuggestion models, sorted by score descending.
    """
    raw = suggest_companions(
        service, species_key, exclude_antagonists_of=exclude_antagonists_of
    )
    return [CompanionSuggestion(**item) for item in raw]


def find_compatible_sets_for_agent(
    service: CompanionPlantingService,
    candidates: list[str],
    *,
    size: int = 3,
    must_include: list[str] | None = None,
) -> list[CompatibleSet]:
    """Find mutually compatible sets of plants among candidates.

    Args:
        service: The companion planting service.
        candidates: Species keys to consider.
        size: Target set size (2–5).
        must_include: Species keys that must be in every returned set.

    Returns:
        A list of CompatibleSet models, sorted by score descending.
    """
    raw = find_compatible_sets(
        service, candidates, size=size, must_include=must_include
    )
    return [CompatibleSet(**item) for item in raw]


def check_placement_for_agent(
    service: CompanionPlantingService,
    species_key: str,
    bed_id: str,
    *,
    bed_plants: list[str] | None = None,
    bed_exists: bool | None = None,
) -> PlacementCheck:
    """Check whether a species is well-placed in a bed.

    Reuses the existing companion relationship logic — never a second
    implementation.

    Args:
        service: The companion planting service.
        species_key: The species to check.
        bed_id: The bed to check against.
        bed_plants: Species keys of plants already in the bed. When omitted,
            the caller must supply ``bed_exists`` so an unknown bed is not
            silently reported as an empty one.
        bed_exists: Whether ``bed_id`` resolves to a real bed. ``None`` means
            the caller could not tell, which is reported as ``"unknown"`` —
            the honest answer, rather than ``"neutral"``, which reads as
            "I looked and there was nothing to find".

    Returns:
        A PlacementCheck model with the results.
    """
    bed_plants = bed_plants or []

    # Check for antagonists and companions in the bed
    antagonists_present: list[str] = []
    companions_present: list[str] = []

    for plant in bed_plants:
        rel = service.get_relationship(species_key, plant)
        if rel is not None:
            if rel.type == ANTAGONISTIC:
                antagonists_present.append(plant)
            elif rel.type == BENEFICIAL:
                companions_present.append(plant)

    # Spacing and soil checks are not implemented here — the full diagnostics
    # are available via get_diagnostics. None means "not checked", never a
    # misleading True.
    spacing_ok = None
    soil_ok = None

    # Determine overall status. An unresolvable bed must not be reported as a
    # clean "neutral": that is the same silent-negative failure as claiming a
    # spacing check passed (P1-5).
    if bed_exists is False:
        overall = "unknown_bed"
    elif antagonists_present:
        overall = "critical"
    elif companions_present:
        overall = "good"
    elif bed_exists is None and not bed_plants:
        overall = "unknown"
    else:
        overall = "neutral"

    return PlacementCheck(
        species_key=species_key,
        bed_id=bed_id,
        antagonists_present=antagonists_present,
        companions_present=companions_present,
        spacing_ok=spacing_ok,
        soil_ok=soil_ok,
        overall=overall,
    )


# --- US-D3.2 (issue #331): succession ---------------------------------------
#
# Determinism is a contract here, not a nicety: a later golden evaluation set
# has to be able to pin these outputs. Every ordering below has an explicit
# final tiebreak on a stable key (species_key), and no set/dict iteration order
# ever reaches the output.


def parse_iso_date(value: str) -> datetime.date | None:
    """Parse an ISO date, returning None for anything unparseable.

    Public because the GUI-side providers in ``application.py`` need the same
    tolerant parse; a private name imported across module boundaries is two
    things at once that then drift (P2 in the #331 review).
    """
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _segment_views(
    segments: dict[str, tuple[datetime.date, datetime.date]],
) -> list[SeasonSegment]:
    """Curate a segment mapping in the canonical SEASON_SEGMENTS order."""
    return [
        SeasonSegment(
            segment=key,
            start_date=segments[key][0].isoformat(),
            end_date=segments[key][1].isoformat(),
        )
        for key in SEASON_SEGMENTS
        if key in segments
    ]


def get_succession_plan_for_agent(
    plan_dict: dict | None,
    bed_id: str,
    *,
    year: int | None = None,
    today: datetime.date,
    location: dict | None = None,
) -> SuccessionPlanView:
    """Curate a bed's succession plan for an agent.

    Args:
        plan_dict: The raw ``SuccessionPlan.to_dict()`` from
            ``ProjectManager.succession_plans``, or None when the bed has none.
        bed_id: The bed the plan belongs to.
        year: Plan year; defaults to the stored plan's year, else ``today.year``.
        today: The reference date for ``current_entry``/``next_entry``. Injected
            rather than read from the clock so the answer is reproducible.
        location: The plan's ``ProjectManager.location`` dict, used to decide
            whether frost-relative segments are possible.

    Returns:
        A SuccessionPlanView. A bed with no plan returns ``has_plan=False`` and
        empty entries — never a fabricated empty plan that reads as "the bed is
        deliberately left fallow".
    """
    stored = SuccessionPlan.from_dict(plan_dict) if plan_dict else None
    resolved_year = year or (stored.year if stored is not None else today.year)

    # A bed may hold a plan for one year only. Answering a question about 2027
    # with the 2026 plan reported `has_plan: true`, 2026 dates, and
    # `season: null` on every entry - which reads as a data fault rather than a
    # year mismatch. So an explicit year that does not match the stored plan
    # gets an honest empty answer, and `plan_year` says what IS there.
    plan = stored
    plan_year: int | None = None
    if plan is not None and year is not None and plan.year != year:
        plan_year = plan.year
        plan = None

    segments, are_fallback = resolve_season_segments(resolved_year, location)

    entries = plan.entries_sorted() if plan is not None else []
    views = [
        _entry_view(entry, segments) for entry in entries
    ]
    current = plan.current_entry(today) if plan is not None else None
    nxt = plan.next_entry(today) if plan is not None else None

    return SuccessionPlanView(
        bed_id=bed_id,
        year=resolved_year,
        plan_year=plan_year,
        has_plan=plan is not None,
        entries=views,
        current_entry=_entry_view(current, segments) if current is not None else None,
        next_entry=_entry_view(nxt, segments) if nxt is not None else None,
        segments=_segment_views(segments),
        segments_are_fallback=are_fallback,
        coverage="no_frost_dates" if are_fallback else "full",
        reference_date=today.isoformat(),
    )


def _entry_view(
    entry: SuccessionEntry,
    segments: dict[str, tuple[datetime.date, datetime.date]],
) -> SuccessionEntryView:
    start = parse_iso_date(entry.start_date)
    return SuccessionEntryView(
        id=entry.id,
        species_key=entry.species_key,
        common_name=entry.common_name,
        scientific_name=entry.scientific_name,
        start_date=entry.start_date,
        end_date=entry.end_date,
        notes=entry.notes,
        season=date_to_segment(start, segments) if start is not None else None,
    )


def find_succession_gaps_for_agent(
    plan_dict: dict | None,
    *,
    year: int | None = None,
    today: datetime.date,
    location: dict | None = None,
) -> list[SuccessionGap]:
    """Return the growing-season date ranges a bed's plan leaves uncovered.

    This is the question an agent actually asks ("when is bed 3 free?"), so it is
    a tool rather than something every client computes differently. Gaps are
    computed by subtracting the plan's covered ranges from each season segment,
    then reported in ``SEASON_SEGMENTS`` order.

    A slot whose dates are unparseable contributes NO coverage: a malformed entry
    must not read as a filled bed.
    """
    plan = SuccessionPlan.from_dict(plan_dict) if plan_dict else None
    resolved_year = year or (plan.year if plan is not None else today.year)
    segments, _ = resolve_season_segments(resolved_year, location)

    covered: list[tuple[datetime.date, datetime.date]] = []
    for entry in plan.entries if plan is not None else []:
        start = parse_iso_date(entry.start_date)
        end = parse_iso_date(entry.end_date)
        if start is None or end is None or end < start:
            continue
        covered.append((start, end))

    gaps: list[SuccessionGap] = []
    for key, seg_start, seg_end in _disjoint_windows(segments):
        gaps.extend(_uncovered(key, seg_start, seg_end, covered))
    return gaps


def _disjoint_windows(
    segments: dict[str, tuple[datetime.date, datetime.date]],
) -> list[tuple[str, datetime.date, datetime.date]]:
    """Return the segments as windows that do NOT share a boundary day.

    ``compute_season_segments`` produces contiguous, inclusive ranges, so
    ``early_spring`` ends on the same day ``late_spring`` starts. That is correct
    for *labeling* a date (``date_to_segment`` resolves the overlap to the first
    match, and the plan view reports the true ranges), but subtracting coverage
    per segment against those ranges makes a shared boundary day appear as
    uncovered in BOTH neighbours: an empty plan reports 257 gap-days for a
    254-day season.

    That is not merely cosmetic. ``build_succession_plan_for_agent`` refuses
    ``start <= prev_end``, so filling the gaps this tool hands out would be
    REFUSED - the read -> write round trip the ``plan-succession`` prompt
    instructs would be impossible. Clipping each window's end to the next
    window's start minus one day makes the gaps contiguous and non-overlapping;
    the final segment keeps its true inclusive end.
    """
    keys = [key for key in SEASON_SEGMENTS if key in segments]
    windows: list[tuple[str, datetime.date, datetime.date]] = []
    for i, key in enumerate(keys):
        start, end = segments[key]
        if i + 1 < len(keys):
            next_start = segments[keys[i + 1]][0]
            if next_start - datetime.timedelta(days=1) < end:
                end = next_start - datetime.timedelta(days=1)
        windows.append((key, start, end))
    return windows


def _uncovered(
    segment: str,
    window_start: datetime.date,
    window_end: datetime.date,
    covered: list[tuple[datetime.date, datetime.date]],
) -> list[SuccessionGap]:
    """Subtract ``covered`` ranges from one window, returning the leftovers."""
    # Only overlaps matter, and clipping to the window keeps a slot that runs
    # past the segment from erasing the whole next segment.
    spans = sorted(
        (max(s, window_start), min(e, window_end))
        for s, e in covered
        if e >= window_start and s <= window_end
    )
    merged: list[list[datetime.date]] = []
    for start, end in spans:
        if end < start:
            continue
        if merged and start <= merged[-1][1] + datetime.timedelta(days=1):
            # Overlapping or adjacent ranges collapse into one covered block.
            if end > merged[-1][1]:
                merged[-1][1] = end
            continue
        merged.append([start, end])

    gaps: list[SuccessionGap] = []
    cursor = window_start
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start - datetime.timedelta(days=1)))
        cursor = max(cursor, end + datetime.timedelta(days=1))
    if cursor <= window_end:
        gaps.append((cursor, window_end))
    return [
        SuccessionGap(
            segment=segment,
            start_date=s.isoformat(),
            end_date=e.isoformat(),
            days=(e - s).days + 1,
        )
        for s, e in gaps
    ]


def suggest_succession_for_agent(
    *,
    candidates: list[dict],
    gap_start: str,
    gap_end: str,
    avoid_families: list[str] | None = None,
    within_plan_families: list[str] | None = None,
    neighbour_keys: list[str] | None = None,
    service: CompanionPlantingService | None = None,
    antagonist_species: list[str] | None = None,
) -> list[SuccessionSuggestion]:
    """Rank candidate crops for one succession gap, deterministically.

    Three filters, in this order (the antagonism filter is a no-op for a window
    this bed's own plan left uncovered, which is the normal case):

    1. **Rotation conflict** — a candidate whose botanical family appears in
       ``within_plan_families`` (families of crops the bed already plans EARLIER
       in the same plan) or ``avoid_families`` (the 3-year cross-year cooldown,
       computed by ``CropRotationService.get_recommendation``) is excluded.
       Succession is several crops in ONE season, which is why
       ``CropRotationService.check_plant_placement`` cannot do this job: it
       compares only against ``records[0]``, the single most recent planting
       record, so it cannot see "tomato after the garlic entry three slots ago".
       Both inputs come pre-computed so this function stays Qt-free and does no
       I/O.
    2. **Antagonism** — a candidate antagonistic to a ``neighbour_keys`` species
       (the crops planted concurrently elsewhere in the plan) is excluded,
       reusing the companion service rather than a second relationship lookup.
    3. **Window fit** — ranked by whether ``days_to_maturity`` fits the gap. An
       unknown maturity is reported ``fits_window=False`` rather than assumed to
       fit: an unfalsifiable "fits" is the same fabrication class as a
       fabricated spacing pass.

    Args:
        candidates: Raw species records (dicts, as stored in an item's
            ``metadata["plant_species"]``). The key is derived with the
            canonical ``models.plant_data.species_key`` (ADR-016) rather than
            read from a field, because there is no such field — deriving it a
            second way is how per-species state desyncs.
        gap_start: ISO start of the gap.
        gap_end: ISO end of the gap.
        avoid_families: Families to avoid from the cross-year cooldown.
        within_plan_families: Families already used earlier in this plan.
        neighbour_keys: Species planted concurrently in the plan.
        service: Companion service, for the antagonism check.
        antagonist_species: Pre-resolved antagonists of ``neighbour_keys``, used
            when no service is supplied.

    Returns:
        Ranked suggestions. Ties break on ``days_to_maturity`` then
        ``species_key``, so repeated calls with the same input are identical.
    """
    avoid = {f.lower() for f in (avoid_families or []) if f}
    within = {f.lower() for f in (within_plan_families or []) if f}
    neighbours = [k for k in (neighbour_keys or []) if k]
    antagonists = {k.lower() for k in (antagonist_species or []) if k}

    start = parse_iso_date(gap_start)
    end = parse_iso_date(gap_end)
    window_days = (end - start).days + 1 if start and end and end >= start else 0
    # window_days == 0 means the window itself is unusable - malformed, or
    # inverted. Saying "the gap is only 0 days" about a window that does not
    # exist is a confidently wrong statement, and set_succession_plan refuses
    # the same dates. Say the window is unusable instead.
    window_usable = window_days > 0

    scored: list[tuple[bool, int, str, SuccessionSuggestion]] = []
    seen_keys: set[str] = set()
    for record in candidates:
        if not isinstance(record, dict):
            continue
        key = species_key(record)
        # Two different names can resolve to the SAME bundled record (an alias,
        # or the common name and the scientific name). Scoring both produced two
        # rows with an identical sort key, so Python's stable sort preserved
        # INPUT order - the ranking was not actually deterministic, and the
        # answer listed a crop twice. Dedupe on the resolved key.
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # ADR-016 returns "_unknown" when every name field is blank; that is not
        # a species an agent can act on, so it is skipped rather than suggested.
        if not key or key == "_unknown":
            continue
        family = str(record.get("family", "") or "")
        if family and family.lower() in avoid | within:
            continue
        if key.lower() in antagonists:
            continue
        if service is not None and neighbours and _conflicts_with_any(
            service, key, neighbours
        ):
            continue

        maturity = _effective_maturity_days(record)
        fits = maturity is not None and 0 < maturity <= window_days
        scored.append(
            (
                fits,
                maturity if maturity is not None else 10**6,
                key,
                SuccessionSuggestion(
                    species_key=key,
                    name=str(record.get("common_name", "") or "") or key,
                    family=family,
                    days_to_maturity=maturity,
                    fits_window=fits,
                    reasons=_reasons(
                        fits,
                        maturity,
                        window_days,
                        family,
                        bool(avoid | within),
                        window_usable,
                    ),
                    source="bundled",
                ),
            )
        )

    scored.sort(key=lambda row: (not row[0], row[1], row[2]))
    return [row[3] for row in scored]


def _effective_maturity_days(record: dict) -> int | None:
    """Return the shortest known days-to-maturity, or None when unknown.

    The MINIMUM is used deliberately: the question is "can this crop finish
    before the next slot starts", and a range's optimistic end is the only value
    that answers it. Using max would reject crops that in fact fit.
    """
    values = [
        v
        for v in (
            record.get("days_to_maturity_min"),
            record.get("days_to_maturity_max"),
        )
        if isinstance(v, int) and not isinstance(v, bool) and v > 0
    ]
    return min(values) if values else None


def _conflicts_with_any(
    service: CompanionPlantingService,
    species_key: str,
    neighbours: list[str],
) -> bool:
    """True when the species is antagonistic to any of the neighbours."""
    return any(
        (rel := service.get_relationship(species_key, other)) is not None
        and rel.type == ANTAGONISTIC
        for other in neighbours
    )


def _reasons(
    fits: bool,
    maturity: int | None,
    window_days: int,
    family: str,
    rotation_checked: bool,
    window_usable: bool = True,
) -> list[str]:
    """Build the display-string reason list.

    These strings are presentation, not the machine contract (see the schema
    docstring): an agent branches on ``fits_window``/``family``, not on these.
    """
    reasons: list[str] = []
    if not window_usable:
        reasons.append(
            "The requested window is unusable (malformed or end before start), "
            "so no window fit was evaluated"
        )
        return reasons
    if fits and maturity is not None:
        reasons.append(f"Matures in ~{maturity} days, fits the {window_days}-day gap")
    elif maturity is None:
        reasons.append("Days to maturity unknown — window fit not confirmed")
    else:
        reasons.append(
            f"Needs ~{maturity} days but the gap is only {window_days} days"
        )
    # Only claim a rotation check when one was actually consulted. Appending
    # "no rotation conflict" for a family-bearing candidate on an empty
    # avoid|within set asserts a check that never ran - #319's honesty lesson
    # (c), verbatim.
    if family and rotation_checked:
        reasons.append(f"No rotation conflict ({family} unused in this bed)")
    elif not family:
        reasons.append("No family on record, so no rotation claim is made")
    return reasons


class SuccessionPlanError(ValueError):
    """A refusal from ``build_succession_plan_for_agent``.

    A ValueError subclass so the server layer can catch the refusal and turn it
    into a tool error, while every distinct message stays greppable in tests.
    """


def build_succession_plan_for_agent(
    entries: list[dict] | None,
    bed_id: str,
    year: int,
    *,
    known_species_keys: set[str] | None = None,
) -> SuccessionPlan | None:
    """Validate agent-supplied entries into a ``SuccessionPlan``.

    Returns ``None`` when the plan should be DELETED (``entries`` empty/None),
    which is what ``SetSuccessionPlanCommand`` expects for removal.

    Every refusal happens before anything is constructed, so a rejected call
    leaves the caller's plan state untouched (the caller only builds the command
    on success).

    Args:
        entries: ``[{species_key, common_name, start_date, end_date, notes}]``.
        bed_id: Target bed.
        year: Plan year.
        known_species_keys: When supplied, any ``species_key`` outside this set
            is refused. Omit to skip that check.

    Raises:
        SuccessionPlanError: On an unknown species, a malformed or non-ISO date,
            an end before its start, or two entries whose ranges overlap.
    """
    if not entries:
        return None

    parsed: list[tuple[int, datetime.date, datetime.date, str, dict]] = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise SuccessionPlanError(f"Entry {index} is not an object")

        raw_key = str(raw.get("species_key", "") or "").strip()
        if not raw_key:
            raise SuccessionPlanError(
                f"Entry {index} has no species_key; succession slots must name a "
                "species so rotation and companion checks can be made"
            )
        # Canonicalise before validating AND before storing. The roster is
        # canonical (species_key lowercases the scientific name), so an exact
        # membership test refused "Allium sativum" and "Garlic" while the
        # sibling tools `set_species` and `suggest_succession`'s `candidates`
        # both accept them - three tools disagreeing on the same string. Storing
        # the canonical form also keeps the persisted plan comparable with every
        # other per-species surface.
        species_key = raw_key.lower()
        if known_species_keys is not None and species_key not in known_species_keys:
            raise SuccessionPlanError(
                f"Unknown species_key {raw_key!r}. A species key is the canonical "
                "lowercased form (ADR-016), which for a bundled plant is its "
                "scientific name - 'allium sativum', not 'Garlic'. Read the "
                "garden://species resource for the names this plan knows about."
            )

        start = parse_iso_date(str(raw.get("start_date", "") or ""))
        if start is None:
            raise SuccessionPlanError(
                f"Entry {index} ({species_key}) has a missing or non-ISO "
                f"start_date: {raw.get('start_date')!r}. Use YYYY-MM-DD."
            )
        end = parse_iso_date(str(raw.get("end_date", "") or ""))
        if end is None:
            raise SuccessionPlanError(
                f"Entry {index} ({species_key}) has a missing or non-ISO "
                f"end_date: {raw.get('end_date')!r}. Use YYYY-MM-DD."
            )
        if end < start:
            raise SuccessionPlanError(
                f"Entry {index} ({species_key}) ends {end} before it starts "
                f"{start}."
            )
        parsed.append((index, start, end, species_key, raw))

    parsed.sort(key=lambda row: (row[1], row[2], row[0]))
    for (prev_i, _prev_start, prev_end, _pk, prev_raw), (i, start, _end, _k, _raw) in zip(
        parsed, parsed[1:], strict=False
    ):
        if start <= prev_end:
            prev_name = prev_raw.get("common_name") or prev_raw.get("species_key")
            raise SuccessionPlanError(
                f"Entries {prev_i} and {i} overlap: {prev_name!r} runs to "
                f"{prev_end} but the next entry starts {start}. One bed cannot "
                "grow two crops on the same days."
            )

    plan = SuccessionPlan(
        bed_id=bed_id,
        year=year,
        entries=[
            SuccessionEntry(
                species_key=canonical_key,
                common_name=str(raw.get("common_name", "") or "").strip(),
                scientific_name=str(raw.get("scientific_name", "") or "").strip(),
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                notes=str(raw.get("notes", "") or ""),
            )
            for _index, start, end, canonical_key, raw in parsed
        ],
    )
    return plan


# --- US-D3.3 (issue #332): calendar & task tools ------------------------------

#: The task sources the generators can emit.
#:
#: SIX values, and they are the engine's own strings — read off the
#: ``source=`` argument of all seven generators, not off the issue text, which
#: implied ``soil_amendment`` / ``soil_mismatch`` and neither of which exists.
#: Both the amendment and the mismatch generator emit ``source="soil"``, so the
#: two are told apart by ``task_type`` (``soil_amendment`` vs ``soil_mismatch``),
#: not by ``source``.
#:
#: Drift-guarded for EQUALITY in tests/unit/test_agent_task_tools.py. An earlier
#: subset-only guard passed with two values no generator can ever emit, which
#: would have made ``get_tasks(source="soil_mismatch")`` return an empty list
#: while ``get_tasks(source="soil")`` — the value that works — was refused.
TASK_SOURCES: tuple[str, ...] = (
    "calendar",
    "propagation",
    "succession",
    "soil",
    "frost",
    "manual",
)

#: Statuses `get_tasks` hides when ``include_dismissed`` is false.
#:
#: BOTH ``dismissed`` and ``archived``, because that is exactly what the Tasks
#: tab hides (`ui/views/tasks_view.py`: ``if eff in ("archived", "dismissed"):
#: continue``). Matching it is not cosmetic. An agent tool that showed rows the
#: user's own task list hides would be a third surface disagreeing with the
#: other two about the same shared store — the defect invariant 6 exists to
#: prevent, and the one #227/#228 shipped.
HIDDEN_WHEN_NOT_INCLUDE_DISMISSED: tuple[str, ...] = ("archived", "dismissed")


def _task_view(
    task: Any,
    *,
    today: datetime.date,
    task_states: dict[str, Any],
) -> TaskView:
    """Curate one ``Task`` plus its render-time urgency and stored status.

    Urgency comes from ``task_generator.classify_urgency`` and status from
    ``task_status.effective_status``. Neither is re-implemented here: the first
    has a GUI mirror that already drifted once, and the second is the shared
    store two task surfaces read (invariant 6).
    """
    state = task_states.get(task.task_id)
    status = effective_status(state, today)
    urgency = None
    if task.start_date is not None and task.end_date is not None:
        urgency = classify_urgency(task.start_date, task.end_date, today)
    return TaskView(
        task_id=task.task_id,
        source=task.source,
        task_type=task.task_type,
        title=task.title,
        notes=task.notes or "",
        start_date=task.start_date.isoformat() if task.start_date else "",
        end_date=task.end_date.isoformat() if task.end_date else "",
        bed_id=task.bed_id,
        species_key=task.species_key or "",
        item_ids=list(task.item_ids or ()),
        urgency=urgency,
        status=status,
        done_date=(state or {}).get("done_date") or None,
        snooze_until=(state or {}).get("snooze_until") or None,
        dismissible=bool(task.dismissible),
    )


def _matches_window(
    task: Any, start: datetime.date, end: datetime.date
) -> bool:
    """True when a task's window overlaps ``[start, end]``.

    An undated task is always in range. It has no dates to place, so excluding
    it would make a manual to-do silently vanish from a filtered read — the
    "empty list that reads as nothing to do" trap in its narrowest form.
    """
    if task.start_date is None or task.end_date is None:
        return True
    return task.start_date <= end and task.end_date >= start


def get_tasks_for_agent(
    tasks: list[Any],
    *,
    today: datetime.date,
    task_states: dict[str, Any] | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    source: str | None = None,
    bed_id: str | None = None,
    species_key: str | None = None,
    include_dismissed: bool = False,
    has_frost_dates: bool = True,
    window_days: int = 30,
) -> TaskListView:
    """Curate the generated task calendar into a filtered, deterministic list.

    Args:
        tasks: Whatever ``generate_all`` produced for one ``PlanState``.
        today: Reference date for urgency and status.
        task_states: The shared per-task status store, keyed by ``task_id``.
        from_date: Window start. Defaults to ``today - window_days``.
        to_date: Window end. Defaults to ``today + window_days``.
        source: Keep only this ``source``. Unknown values are refused by the
            caller, not silently treated as "no filter".
        bed_id: Keep only tasks linked to this bed.
        species_key: Keep only tasks for this canonical species key.
        include_dismissed: Show dismissed tasks, with their status.
        has_frost_dates: False when the plan has no geo-location, which sets
            ``coverage`` to ``'no_frost_dates'``. The tasks themselves are
            unaffected: the calendar generator already returned nothing.
        window_days: Half-width of the default window.

    Returns:
        A :class:`TaskListView`. Ordering is ``(start_date, task_id)`` so two
        calls with the same input return byte-identical output — a contract the
        prompts and the tests both depend on.
    """
    states = task_states or {}
    start = from_date or (today - datetime.timedelta(days=window_days))
    end = to_date or (today + datetime.timedelta(days=window_days))

    selected: list[TaskView] = []
    for task in tasks:
        if source is not None and task.source != source:
            continue
        if bed_id is not None and (task.bed_id or None) != bed_id:
            continue
        if species_key is not None and (task.species_key or "") != species_key:
            continue
        if not _matches_window(task, start, end):
            continue
        view = _task_view(task, today=today, task_states=states)
        if not include_dismissed and view.status in HIDDEN_WHEN_NOT_INCLUDE_DISMISSED:
            continue
        selected.append(view)

    selected.sort(key=lambda v: (v.start_date, v.task_id))
    return TaskListView(
        today=today.isoformat(),
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        coverage="full" if has_frost_dates else "no_frost_dates",
        total=len(selected),
        tasks=selected,
    )


def get_task_calendar_for_agent(
    tasks: list[Any],
    *,
    today: datetime.date,
    year: int | None = None,
    task_states: dict[str, Any] | None = None,
    has_frost_dates: bool = True,
) -> TaskCalendarView:
    """Bucket the task calendar by month, for an overview before drilling in.

    A task is counted in EVERY month its window touches, so a three-week task
    spanning a month boundary appears in both. That is deliberate: the question
    being answered is "how busy is each month", and a task that occupies part
    of a month occupies that month.
    """
    states = task_states or {}
    target_year = year or today.year
    buckets: dict[str, TaskCalendarBucket] = {}

    for task in tasks:
        if task.start_date is None or task.end_date is None:
            continue
        view = _task_view(task, today=today, task_states=states)
        first = _month_range(task.start_date, target_year)
        last = _month_range(task.end_date, target_year)
        for month in _months_between(first, last):
            bucket = buckets.get(month)
            if bucket is None:
                bucket = TaskCalendarBucket(month=month)
                buckets[month] = bucket
            bucket.total += 1
            bucket.by_source[view.source] = bucket.by_source.get(view.source, 0) + 1
            urgency = view.urgency or "none"
            bucket.by_urgency[urgency] = bucket.by_urgency.get(urgency, 0) + 1
            if view.urgency is not None:
                bucket.actionable += 1

    months = [buckets[key] for key in sorted(buckets)]
    return TaskCalendarView(
        year=target_year,
        today=today.isoformat(),
        coverage="full" if has_frost_dates else "no_frost_dates",
        total=sum(b.total for b in months),
        months=months,
    )


def _month_range(day: datetime.date, year: int) -> str:
    """The 'YYYY-MM' key for ``day``, or '' when it falls outside ``year``."""
    return f"{day.year:04d}-{day.month:02d}" if day.year == year else ""


def _months_between(first: str, last: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' keys from ``first`` to ``last``.

    Returns ``[]`` when either bound is outside the target year — the empty
    string sentinel from :func:`_month_range` — or when the range is inverted.
    """
    if not first or not last or last < first:
        return []
    start_year, start_month = (int(part) for part in first.split("-"))
    end_year, end_month = (int(part) for part in last.split("-"))
    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


# --- US-D3.4 (issue #333): soil amendment tools -------------------------------

#: The nutrient keys ``health_level`` and the amendment engine reason about.
#: Mirrors ``soil_service._NUTRIENT_KINDS`` and is drift-guarded against it in
#: tests/unit/test_agent_soil_tools.py — the two drifting apart would silently
#: drop a nutrient from the curated output.
NUTRIENT_KINDS: tuple[str, ...] = ("n", "p", "k", "ca", "mg", "s")

#: The subset of :data:`NUTRIENT_KINDS` that ``SoilService.health_level`` can
#: actually rate — its ``ALL_PARAMS`` is (overall, ph, n, p, k). The Ca/Mg/S
#: secondaries are read by the amendment engine but have NO health rating, so
#: asking for one returns the overall rating instead of that nutrient's. See
#: :func:`_soil_status_from`.
RATED_PARAMETERS: tuple[str, ...] = ("n", "p", "k")


def _soil_status_from(
    *,
    bed_id: str,
    bed_name: str,
    record: Any,
    record_source: str,
    history: Any,
    today: datetime.date,
    health_level: Any,
    is_test_overdue: Any,
) -> SoilStatus:
    """Curate one effective soil record into a :class:`SoilStatus`.

    Every rating comes from ``SoilService.health_level`` — including its
    documented "worst non-unknown wins" rule for ``overall`` and its
    all-unknown case. Re-deriving a rating here would be a second
    implementation, and the diagnostic badge the user sees is computed from the
    service, so two answers would mean the agent and the canvas disagree.
    """
    if record is None:
        return SoilStatus(
            bed_id=bed_id,
            bed_name=bed_name,
            record_source="none",
            coverage="no_soil_test",
            test_date="",
            ph=None,
            ph_health_level="unknown",
            overall_health_level="unknown",
            is_test_overdue=False,
            levels={},
        )

    levels = {
        kind: SoilReading(
            level=getattr(record, f"{kind}_level", None),
            health_level=(
                # `SoilService.health_level` rates ph/n/p/k and 'overall'
                # ONLY. Calling it with 'ca'/'mg'/'s' falls through to its
                # overall branch and would report the OVERALL rating as if it
                # were calcium's — a confident wrong answer, which is the trap
                # D3.1 recorded ("a component that did not check something must
                # not report a result that reads as a successful check").
                # None is therefore not a fallback: it is the engine declining
                # to rate this nutrient, and the schema says so.
                health_level(record, kind).value if kind in RATED_PARAMETERS else None
            ),
        )
        for kind in NUTRIENT_KINDS
    }
    return SoilStatus(
        bed_id=bed_id,
        bed_name=bed_name,
        record_source=record_source,
        coverage="ok",
        test_date=record.date or "",
        ph=record.ph,
        ph_health_level=health_level(record, "ph").value,
        overall_health_level=health_level(record, "overall").value,
        is_test_overdue=bool(is_test_overdue(history, today)),
        levels=levels,
    )


def recommend_amendments_for_agent(
    *,
    bed_id: str,
    record: Any,
    today: datetime.date,
    recommendations: list[Any],
) -> AmendmentPlanView:
    """Curate ``calculate_amendments`` output, adding the coverage marker.

    ``recommendations`` is the engine's own list, passed in rather than
    recomputed: this is a wrapper, exactly as ``get_diagnostics`` is. An empty
    list here carries ``coverage='no_soil_test'`` when there is no record, so it
    can never read as "the soil needs nothing".
    """
    return AmendmentPlanView(
        bed_id=bed_id,
        coverage="ok" if record is not None else "no_soil_test",
        today=today.isoformat(),
        total=len(recommendations),
        recommendations=[
            _amendment_view(rec) for rec in recommendations
        ],
    )


def _amendment_view(rec: Any) -> AmendmentRecommendationView:
    """Curate one ``AmendmentRecommendation`` without recomputing anything."""
    amendment = rec.amendment
    return AmendmentRecommendationView(
        amendment_id=amendment.id,
        # `name`/`name_de` are data-baked bilingual fields, not `tr()` output.
        # The id is the machine key; this is display text beside it.
        display_name=amendment.name,
        quantity_g=rec.quantity_g,
        target_kind=rec.target_kind,
        current_value=rec.current_value,
        target_value=rec.target_value,
        fixes=list(amendment.fixes or []),
        # credits entries are (kind, current, target) — the engine's rationale
        # reads "also raises CA 0 -> 1".
        credits=[
            f"{kind}:{current}->{target}" for kind, current, target in (rec.credits or [])
        ],
        structural_fix=rec.structural_fix or "",
        release_speed=amendment.release_speed or "",
        organic=bool(amendment.organic),
    )


def get_soil_mismatches_for_agent(
    *,
    bed_id: str | None,
    today: datetime.date,
    details: list[tuple[Any, list[tuple[str, str]]]],
    coverage: str = "ok",
) -> SoilMismatchListView:
    """Curate ``get_mismatch_details`` output into the codes-plus-text shape.

    ``details`` is the engine's own result. Each reason is already a
    ``(reason_code, display_text)`` pair from the one canonical builder, so this
    only reshapes it: codes for branching, text for a human.
    """
    views = [
        SoilMismatchView(
            species_key=species_key_of(spec),
            common_name=(spec.common_name or spec.scientific_name or ""),
            reason_codes=[code for code, _text in reasons],
            reasons=[text for _code, text in reasons],
        )
        for spec, reasons in details
    ]
    views.sort(key=lambda v: v.species_key)
    return SoilMismatchListView(
        bed_id=bed_id,
        coverage=coverage,
        today=today.isoformat(),
        total=len(views),
        mismatches=views,
    )


def species_key_of(spec: Any) -> str:
    """The canonical species key for a ``PlantSpeciesData`` (ADR-016).

    ``species_key()`` takes a DICT, but the mismatch engine yields
    ``PlantSpeciesData`` objects, so the two are bridged here rather than at the
    call site. The field PRIORITY is the shared helper's, not a second guess:
    ``source_id`` → ``scientific_name`` → ``common_name``, stripped and
    lowercased.

    An object that carries none of the three fields yields ``'_unknown'`` —
    the same sentinel ``species_key()`` itself returns — so an unidentifiable
    plant is visibly unidentifiable instead of being keyed by something else.
    """
    if isinstance(spec, dict):
        return species_key(spec)
    as_dict = {
        "source_id": getattr(spec, "source_id", "") or "",
        "scientific_name": getattr(spec, "scientific_name", "") or "",
        "common_name": getattr(spec, "common_name", "") or "",
    }
    return species_key(as_dict)


# --- US-D3.4: record_soil_test validation -------------------------------------

#: Accepted Rapitest kit level per nutrient, as ``(low, high)`` INCLUSIVE.
#:
#: These are not one shared range, and that is the whole point of the table:
#: nitrogen and phosphorus run 0–4, potassium runs 1–4 because the kit has no
#: zero for it, and the Ca/Mg/S secondaries run 0–2. A single "is it in range"
#: check would silently accept a potassium 0 that the engine then reads as
#: Deficient-but-measured rather than absent.
#:
#: Sourced from the field docstrings in ``models/soil_test.py`` and
#: drift-guarded against them in tests/unit/test_agent_soil_tools.py.
RAPITEST_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "n": (0, 4),
    "p": (0, 4),
    "k": (1, 4),
    "ca": (0, 2),
    "mg": (0, 2),
    "s": (0, 2),
}

#: The soil textures ``SoilTestRecord.soil_texture`` accepts.
SOIL_TEXTURES: tuple[str, ...] = ("sandy", "loamy", "clayey", "compacted")


class SoilTestError(ValueError):
    """A refusal from ``build_soil_record_for_agent``.

    A ``ValueError`` subclass so the server layer can turn it into a tool error
    while every distinct message stays greppable in tests — the same shape as
    :class:`SuccessionPlanError`.
    """


def _check_level(name: str, value: Any) -> int:
    """Validate one kit level against its own nutrient's range."""
    low, high = RAPITEST_LEVEL_RANGES[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SoilTestError(
            f"{name}_level={value!r} must be a whole number on the Rapitest "
            f"kit scale ({low}-{high}), not a lab reading. This tool takes the "
            "categorical kit scale; the soil dialog records lab ppm values."
        )
    if not low <= value <= high:
        raise SoilTestError(
            f"{name}_level={value} is outside the Rapitest kit scale "
            f"({low}-{high}) for {name}. Pass the categorical kit reading, not "
            "a lab value in ppm — a ppm number here would be read as a kit "
            "level and would silently change every recommendation."
        )
    return value


def build_soil_record_for_agent(
    *,
    ph: float | None = None,
    n_level: int | None = None,
    p_level: int | None = None,
    k_level: int | None = None,
    ca_level: int | None = None,
    mg_level: int | None = None,
    s_level: int | None = None,
    soil_texture: str | None = None,
    test_date: str | None = None,
    notes: str | None = None,
    today: datetime.date | None = None,
) -> Any:
    """Validate agent-supplied readings into a ``SoilTestRecord``.

    The target bed is resolved by the caller, not here: ``AddSoilTestCommand``
    takes the ``target_id`` and the record separately, so a record carries no
    bed of its own.

    Every refusal raises :class:`SoilTestError` BEFORE a record is built, so a
    refused call cannot reach ``AddSoilTestCommand`` and therefore cannot touch
    ``ProjectManager.soil_tests`` or the undo stack.

    The kit scale only, deliberately. The record model also carries optional
    ``*_ppm`` lab floats, but nothing in ``services/`` reads them —
    ``health_level``, ``calculate_amendments`` and ``get_mismatched_plants`` all
    read the ``*_level`` fields — and no code converts between the two scales
    (that is US-12.10c). So a record written from ppm alone would report
    UNKNOWN health, no recommendations and no mismatches while still looking
    complete to the caller. Refusing is the honest answer; the ppm path stays
    with the dialog until the conversion exists.
    """
    from open_garden_planner.models.soil_test import SoilTestRecord

    reference = today or datetime.date.today()

    if ph is not None:
        if isinstance(ph, bool) or not isinstance(ph, (int, float)):
            raise SoilTestError(f"ph={ph!r} must be a number.")
        if not math.isfinite(float(ph)):
            raise SoilTestError(f"ph={ph!r} is not a finite number.")
        if not 0.0 <= float(ph) <= 14.0:
            raise SoilTestError(
                f"ph={ph} is outside 0.0-14.0. Pass the measured pH value."
            )

    levels: dict[str, int | None] = {}
    for name, value in (
        ("n", n_level),
        ("p", p_level),
        ("k", k_level),
        ("ca", ca_level),
        ("mg", mg_level),
        ("s", s_level),
    ):
        levels[name] = None if value is None else _check_level(name, value)

    if soil_texture is not None and soil_texture not in SOIL_TEXTURES:
        raise SoilTestError(
            f"soil_texture={soil_texture!r} is not one of "
            f"{', '.join(SOIL_TEXTURES)}."
        )

    resolved_date = reference
    if test_date:
        parsed = parse_iso_date(test_date)
        if parsed is None:
            raise SoilTestError(
                f"test_date={test_date!r} is not an ISO date. Use YYYY-MM-DD."
            )
        if parsed > reference:
            raise SoilTestError(
                f"test_date={test_date} is in the future (today is "
                f"{reference.isoformat()}). A test cannot have been taken yet."
            )
        resolved_date = parsed

    if ph is None and all(value is None for value in levels.values()):
        raise SoilTestError(
            "A soil test with no readings is noise. Pass at least one of ph, "
            "n_level, p_level, k_level, ca_level, mg_level or s_level."
        )

    return SoilTestRecord(
        date=resolved_date.isoformat(),
        ph=float(ph) if ph is not None else None,
        n_level=levels["n"],
        p_level=levels["p"],
        k_level=levels["k"],
        ca_level=levels["ca"],
        mg_level=levels["mg"],
        s_level=levels["s"],
        notes=notes or "",
        # Kit scale only — see the docstring. Persisted so the dialog reopens in
        # the mode the record was actually entered in.
        mode="kit",
        soil_texture=soil_texture,
    )
