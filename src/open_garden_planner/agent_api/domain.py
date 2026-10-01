"""Qt-free domain-intelligence functions for the Agent API.

US-D3.1 (#319) added the companion wrappers; US-D3.2 (#331) added the
succession ones. They are deliberately Qt-free and operate on plain data,
making them unit-testable without a GUI.

The actual service instances are injected by the provider callables in
``application.py``, so this module never constructs its own service.
"""

from __future__ import annotations

import datetime

from open_garden_planner.agent_api.schema import (
    CompanionSuggestion,
    CompatibleSet,
    PlacementCheck,
    SeasonSegment,
    SuccessionEntryView,
    SuccessionGap,
    SuccessionPlanView,
    SuccessionSuggestion,
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
