"""Unit tests for the US-D3.2 succession domain logic (issue #331).

Qt-free by construction: this module is imported WITHOUT ``qtbot``, which is
itself part of the contract (architecture invariant #10).

Every assertion here pins against ``models/succession.py``'s OWN output rather
than a re-implementation of its formulas — the issue's acceptance criterion
says the labels must match the module's own segment definitions.
"""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.agent_api.domain import (
    SuccessionPlanError,
    build_succession_plan_for_agent,
    find_succession_gaps_for_agent,
    get_succession_plan_for_agent,
    suggest_succession_for_agent,
)
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.models.succession import (
    SEASON_SEGMENTS,
    compute_fallback_segments,
    compute_season_segments,
    date_to_segment,
    resolve_season_segments,
)
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.companion_planting_service import ANTAGONISTIC

# A concrete, mid-latitude frost pair so every expected date is computable by
# hand: last frost 2026-04-15, first fall frost 2026-10-15.
LAST_FROST = "04-15"
FALL_FROST = "10-15"
LOCATION = {
    "frost_dates": {
        "last_spring_frost": LAST_FROST,
        "first_fall_frost": FALL_FROST,
        "hardiness_zone": "7a",
    }
}
YEAR = 2026
TODAY = datetime.date(2026, 6, 15)


def _plan_dict(*entries: dict) -> dict:
    return {
        "bed_id": "bed-1",
        "year": YEAR,
        "entries": list(entries),
    }


def _entry(
    species_key: str,
    common_name: str,
    start: str,
    end: str,
    entry_id: str = "e1",
) -> dict:
    return {
        "id": entry_id,
        "species_key": species_key,
        "common_name": common_name,
        "scientific_name": "",
        "start_date": start,
        "end_date": end,
        "notes": "",
    }


def _species(
    key: str,
    name: str,
    family: str = "",
    maturity: int | None = None,
) -> dict:
    """A raw species record, as an item's ``metadata["plant_species"]`` holds it.

    Dicts, not PlantSpeciesData: the canonical key is the module-level
    ``species_key(species_dict)`` function (ADR-016), and there is no
    ``species_key`` attribute to read.
    """
    return {
        "scientific_name": name,
        "common_name": name,
        "family": family,
        "days_to_maturity_min": maturity,
    }


# --- the shared segment resolution (US-D3.2 §4.1) ----------------------------


class TestSegmentResolution:
    def test_frost_dates_give_frost_relative_segments(self) -> None:
        segments, is_fallback = resolve_season_segments(YEAR, LOCATION)
        assert is_fallback is False
        assert segments == compute_season_segments(LAST_FROST, FALL_FROST, YEAR)

    def test_no_location_falls_back_and_says_so(self) -> None:
        segments, is_fallback = resolve_season_segments(YEAR, None)
        assert is_fallback is True
        assert segments == compute_fallback_segments(YEAR)

    def test_missing_frost_subdict_falls_back(self) -> None:
        segments, is_fallback = resolve_season_segments(YEAR, {"latitude": 52.5})
        assert is_fallback is True
        assert segments == compute_fallback_segments(YEAR)

    def test_half_present_frost_dates_fall_back(self) -> None:
        """One frost date is not enough — a half-derived year must not be
        presented as a real one."""
        segments, is_fallback = resolve_season_segments(
            YEAR, {"frost_dates": {"last_spring_frost": LAST_FROST}}
        )
        assert is_fallback is True
        assert segments == compute_fallback_segments(YEAR)

    def test_unparseable_frost_date_falls_back_rather_than_raising(self) -> None:
        segments, is_fallback = resolve_season_segments(
            YEAR, {"frost_dates": {"last_spring_frost": "13-40", "first_fall_frost": FALL_FROST}}
        )
        assert is_fallback is True
        assert segments == compute_fallback_segments(YEAR)

    def test_fallback_covers_every_segment(self) -> None:
        assert set(compute_fallback_segments(YEAR)) == set(SEASON_SEGMENTS)


class TestSegmentBoundary:
    """The issue describes THREE segments; the code has FOUR. This pins the
    real vocabulary and the inclusive-boundary behaviour."""

    def test_there_are_four_segments_not_three(self) -> None:
        assert SEASON_SEGMENTS == (
            "early_spring",
            "late_spring",
            "summer",
            "fall",
        )

    def test_shared_boundary_belongs_to_the_earlier_segment(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        boundary = segments["early_spring"][1]
        assert boundary == segments["late_spring"][0]
        assert date_to_segment(boundary, segments) == "early_spring"

    def test_date_outside_every_segment_is_none(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        assert date_to_segment(datetime.date(YEAR, 1, 5), segments) is None


# --- get_succession_plan ----------------------------------------------------


class TestGetSuccessionPlan:
    def test_entries_are_date_sorted(self) -> None:
        plan = _plan_dict(
            _entry("lettuce", "Lettuce", "2026-08-01", "2026-09-01", "c"),
            _entry("radish", "Radish", "2026-04-01", "2026-05-01", "a"),
            _entry("beans", "Beans", "2026-06-01", "2026-07-15", "b"),
        )
        view = get_succession_plan_for_agent(
            plan, "bed-1", today=TODAY, location=LOCATION
        )
        assert [e.species_key for e in view.entries] == ["radish", "beans", "lettuce"]

    def test_current_and_next_use_the_injected_date(self) -> None:
        plan = _plan_dict(
            _entry("beans", "Beans", "2026-06-01", "2026-07-15", "b"),
            _entry("lettuce", "Lettuce", "2026-08-01", "2026-09-01", "c"),
        )
        view = get_succession_plan_for_agent(
            plan, "bed-1", today=datetime.date(2026, 6, 20), location=LOCATION
        )
        assert view.current_entry is not None
        assert view.current_entry.species_key == "beans"
        assert view.next_entry is not None
        assert view.next_entry.species_key == "lettuce"
        assert view.reference_date == "2026-06-20"

    def test_current_entry_is_none_between_slots(self) -> None:
        plan = _plan_dict(_entry("beans", "Beans", "2026-06-01", "2026-07-15"))
        view = get_succession_plan_for_agent(
            plan, "bed-1", today=datetime.date(2026, 12, 1), location=LOCATION
        )
        assert view.current_entry is None
        assert view.next_entry is None

    def test_no_plan_reports_has_plan_false(self) -> None:
        view = get_succession_plan_for_agent(
            None, "bed-1", today=TODAY, location=LOCATION
        )
        assert view.has_plan is False
        assert view.entries == []

    def test_empty_plan_is_distinguishable_from_no_plan(self) -> None:
        view = get_succession_plan_for_agent(
            _plan_dict(), "bed-1", today=TODAY, location=LOCATION
        )
        assert view.has_plan is True
        assert view.entries == []

    def test_segments_are_reported_in_canonical_order(self) -> None:
        view = get_succession_plan_for_agent(
            _plan_dict(), "bed-1", today=TODAY, location=LOCATION
        )
        assert [s.segment for s in view.segments] == list(SEASON_SEGMENTS)
        assert view.segments_are_fallback is False
        assert view.coverage == "full"

    def test_no_location_reports_the_coverage_marker_not_an_empty_list(self) -> None:
        view = get_succession_plan_for_agent(
            _plan_dict(), "bed-1", today=TODAY, location=None
        )
        assert view.coverage == "no_frost_dates"
        assert view.segments_are_fallback is True
        # The marker comes WITH the fallback segments, not instead of them.
        assert [s.segment for s in view.segments] == list(SEASON_SEGMENTS)
        assert view.segments[0].start_date == compute_fallback_segments(YEAR)[
            "early_spring"
        ][0].isoformat()

    def test_entry_carries_its_season_label(self) -> None:
        plan = _plan_dict(_entry("beans", "Beans", "2026-06-20", "2026-07-15"))
        view = get_succession_plan_for_agent(
            plan, "bed-1", today=TODAY, location=LOCATION
        )
        assert view.entries[0].season == "summer"


# --- find_succession_gaps ----------------------------------------------------


class TestFindSuccessionGaps:
    def test_a_fully_covered_year_has_no_gaps(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        first = segments["early_spring"][0]
        last = segments["fall"][1]
        plan = _plan_dict(_entry("cover", "Cover", first.isoformat(), last.isoformat()))
        gaps = find_succession_gaps_for_agent(
            plan, today=TODAY, location=LOCATION
        )
        assert gaps == []

    def test_gaps_are_the_uncovered_ranges_with_season_labels(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        plan = _plan_dict(
            _entry(
                "beans",
                "Beans",
                segments["summer"][0].isoformat(),
                segments["summer"][1].isoformat(),
            )
        )
        gaps = find_succession_gaps_for_agent(plan, today=TODAY, location=LOCATION)
        labels = [g.segment for g in gaps]
        assert labels == ["early_spring", "late_spring", "fall"]

        early = gaps[0]
        assert early.start_date == segments["early_spring"][0].isoformat()
        # The window ends one day early: the shared boundary day belongs to the
        # NEXT segment's window, so the two never report the same day twice.
        expected_end = segments["early_spring"][1] - datetime.timedelta(days=1)
        assert early.end_date == expected_end.isoformat()
        assert early.days == (expected_end - segments["early_spring"][0]).days + 1

    def test_a_slot_in_the_middle_leaves_two_gaps_in_its_segment(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        seg_start, seg_end = segments["summer"]
        mid = seg_start + datetime.timedelta(days=20)
        plan = _plan_dict(
            _entry("beans", "Beans", mid.isoformat(), (mid + datetime.timedelta(days=10)).isoformat())
        )
        gaps = find_succession_gaps_for_agent(plan, today=TODAY, location=LOCATION)
        summer = [g for g in gaps if g.segment == "summer"]
        assert len(summer) == 2
        assert summer[0].start_date == seg_start.isoformat()
        assert summer[0].end_date == (mid - datetime.timedelta(days=1)).isoformat()
        assert summer[1].start_date == (mid + datetime.timedelta(days=11)).isoformat()
        # Summer is not the final segment, so its window ends one day before the
        # raw segment end (that day opens `fall`).
        assert summer[1].end_date == (seg_end - datetime.timedelta(days=1)).isoformat()

    def test_adjacent_slots_do_not_leave_a_one_day_gap(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        s = segments["summer"][0]
        plan = _plan_dict(
            _entry("a", "A", s.isoformat(), (s + datetime.timedelta(days=9)).isoformat(), "a"),
            _entry("b", "B", (s + datetime.timedelta(days=10)).isoformat(), (s + datetime.timedelta(days=19)).isoformat(), "b"),
        )
        gaps = find_succession_gaps_for_agent(plan, today=TODAY, location=LOCATION)
        # Days 11-20 of summer remain; nothing spurious in between.
        assert [g.segment for g in gaps] == ["early_spring", "late_spring", "summer", "fall"]
        summer = next(g for g in gaps if g.segment == "summer")
        assert summer.start_date == (s + datetime.timedelta(days=20)).isoformat()

    def test_overlapping_slots_are_merged_not_double_counted(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        s, e = segments["summer"]
        mid = s + datetime.timedelta(days=15)
        plan = _plan_dict(
            _entry("a", "A", s.isoformat(), mid.isoformat(), "a"),
            _entry("b", "B", mid.isoformat(), e.isoformat(), "b"),
        )
        gaps = find_succession_gaps_for_agent(plan, today=TODAY, location=LOCATION)
        assert [g.segment for g in gaps] == ["early_spring", "late_spring", "fall"]

    def test_malformed_entry_covers_nothing(self) -> None:
        """A garbage date must not read as a filled bed."""
        plan = _plan_dict(_entry("broken", "Broken", "not-a-date", "also-not"))
        gaps = find_succession_gaps_for_agent(plan, today=TODAY, location=LOCATION)
        assert len(gaps) == len(SEASON_SEGMENTS)
        assert all(g.days > 0 for g in gaps)

    def test_no_plan_reports_every_segment_as_free(self) -> None:
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=LOCATION)
        assert [g.segment for g in gaps] == list(SEASON_SEGMENTS)

    def test_no_location_uses_the_fallback_segments(self) -> None:
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=None)
        fallback = compute_fallback_segments(YEAR)
        assert gaps[0].start_date == fallback["early_spring"][0].isoformat()

    def test_gaps_do_not_share_a_boundary_day(self) -> None:
        """Segments are contiguous and inclusive, so a raw per-segment
        subtraction reports the shared boundary day TWICE. That is not cosmetic:
        filling the gaps this tool hands out would then be refused by
        ``build_succession_plan_for_agent`` (``start <= prev_end``), making the
        read -> write round trip impossible."""
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=LOCATION)
        days: list[str] = []
        for gap in gaps:
            cursor = datetime.date.fromisoformat(gap.start_date)
            end = datetime.date.fromisoformat(gap.end_date)
            while cursor <= end:
                days.append(cursor.isoformat())
                cursor += datetime.timedelta(days=1)
        assert len(days) == len(set(days)), "a day appears in two segments' gaps"
        assert sum(g.days for g in gaps) == len(days)

    def test_the_four_gaps_tile_the_season_without_a_hole(self) -> None:
        segments = compute_season_segments(LAST_FROST, FALL_FROST, YEAR)
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=LOCATION)
        assert gaps[0].start_date == segments["early_spring"][0].isoformat()
        assert gaps[-1].end_date == segments["fall"][1].isoformat()
        for first, second in zip(gaps, gaps[1:], strict=False):
            # Exactly one day between consecutive gaps: no overlap, no hole.
            delta = (
                datetime.date.fromisoformat(second.start_date)
                - datetime.date.fromisoformat(first.end_date)
            ).days
            assert delta == 1, f"{first.end_date} -> {second.start_date} leaves {delta - 1}"

    def test_filling_every_gap_is_accepted_by_the_write_validator(self) -> None:
        """The round trip the ``plan-succession`` prompt asks an agent to make."""
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=LOCATION)
        entries = [
            {
                "species_key": "allium sativum",
                "common_name": "Garlic",
                "start_date": g.start_date,
                "end_date": g.end_date,
            }
            for g in gaps
        ]
        plan = build_succession_plan_for_agent(entries, "bed-1", YEAR)
        assert plan is not None
        assert len(plan.entries) == len(gaps)

    def test_a_fallback_plan_also_tiles_without_overlap(self) -> None:
        gaps = find_succession_gaps_for_agent(None, today=TODAY, location=None)
        days = sum(g.days for g in gaps)
        distinct = set()
        for gap in gaps:
            cursor = datetime.date.fromisoformat(gap.start_date)
            end = datetime.date.fromisoformat(gap.end_date)
            while cursor <= end:
                distinct.add(cursor)
                cursor += datetime.timedelta(days=1)
        assert days == len(distinct)


# --- suggest_succession -----------------------------------------------------


class TestSuggestSuccession:
    def _suggest(self, **kwargs):
        params = {
            "candidates": [],
            "gap_start": "2026-06-01",
            "gap_end": "2026-07-15",
        }
        params.update(kwargs)
        return suggest_succession_for_agent(**params)

    def test_excludes_a_family_already_used_earlier_in_the_plan(self) -> None:
        """The regression this story exists for: succession is several crops in
        ONE season, which CropRotationService.check_plant_placement cannot see
        because it only compares against records[0]."""
        out = self._suggest(
            candidates=[
                _species("tomato", "Tomato", "Solanaceae", 80),
                _species("beans", "Beans", "Fabaceae", 55),
            ],
            within_plan_families=["Solanaceae"],
        )
        assert [s.species_key for s in out] == ["beans"]

    def test_excludes_the_cross_year_cooldown_families(self) -> None:
        out = self._suggest(
            candidates=[
                _species("cabbage", "Cabbage", "Brassicaceae", 70),
                _species("beans", "Beans", "Fabaceae", 55),
            ],
            avoid_families=["Brassicaceae"],
        )
        assert [s.species_key for s in out] == ["beans"]

    def test_familyless_species_is_not_excluded_by_family(self) -> None:
        """No family means no rotation claim can be made — but it is also not
        evidence of a conflict, so it stays."""
        out = self._suggest(
            candidates=[_species("mystery", "Mystery", "", 40)],
            within_plan_families=["Solanaceae"],
        )
        assert [s.species_key for s in out] == ["mystery"]

    def test_excludes_a_pre_resolved_antagonist(self) -> None:
        out = self._suggest(
            candidates=[
                _species("fennel", "Fennel", "Apiaceae", 65),
                _species("beans", "Beans", "Fabaceae", 55),
            ],
            neighbour_keys=["dill"],
            antagonist_species=["fennel"],
        )
        assert [s.species_key for s in out] == ["beans"]

    def test_window_fit_is_reported_not_assumed(self) -> None:
        # A 61-day gap: beans (55d) fits, pumpkin (120d) does not.
        out = self._suggest(
            candidates=[
                _species("beans", "Beans", "Fabaceae", 55),
                _species("pumpkin", "Pumpkin", "Cucurbitaceae", 120),
            ],
            gap_start="2026-06-01",
            gap_end="2026-07-31",
        )
        by_key = {s.species_key: s for s in out}
        assert by_key["beans"].fits_window is True
        assert by_key["pumpkin"].fits_window is False
        # Fits first, regardless of input order.
        assert [s.species_key for s in out][0] == "beans"

    def test_a_crop_too_slow_for_the_gap_is_still_returned_but_ranked_last(self) -> None:
        """Excluding it entirely would hide that a candidate was considered; the
        machine fields say why it is not a good fit."""
        out = self._suggest(
            candidates=[_species("pumpkin", "Pumpkin", "Cucurbitaceae", 120)],
            gap_start="2026-06-01",
            gap_end="2026-06-30",
        )
        assert out[0].species_key == "pumpkin"
        assert out[0].fits_window is False
        assert any("gap is only" in r for r in out[0].reasons)

    def test_unknown_maturity_is_not_reported_as_fitting(self) -> None:
        out = self._suggest(candidates=[_species("mystery", "Mystery", "", None)])
        assert out[0].days_to_maturity is None
        assert out[0].fits_window is False
        assert any("not confirmed" in r for r in out[0].reasons)

    def test_uses_the_shortest_known_maturity(self) -> None:
        """A range's optimistic end is what answers 'can it finish in time'."""
        record = {
            "scientific_name": "Tomato",
            "common_name": "Tomato",
            "days_to_maturity_min": 55,
            "days_to_maturity_max": 80,
        }
        out = self._suggest(candidates=[record], gap_end="2026-08-01")
        assert out[0].days_to_maturity == 55
        assert out[0].fits_window is True

    def test_the_longer_end_alone_would_not_fit(self) -> None:
        """80 days would not fit this 62-day gap; taking the max would have
        wrongly rejected a crop that in fact finishes in 55."""
        out = self._suggest(
            candidates=[{"scientific_name": "Tomato", "common_name": "Tomato",
                         "days_to_maturity_min": 55, "days_to_maturity_max": 80}],
            gap_start="2026-06-01",
            gap_end="2026-08-01",
        )
        assert out[0].fits_window is True

    def test_everything_excluded_returns_an_empty_list_not_a_fallback(self) -> None:
        out = self._suggest(
            candidates=[_species("tomato", "Tomato", "Solanaceae", 80)],
            within_plan_families=["Solanaceae"],
        )
        assert out == []

    def test_no_candidates_returns_empty(self) -> None:
        assert self._suggest() == []

    def test_species_without_a_usable_name_is_skipped(self) -> None:
        """ADR-016 yields '_unknown' for a blank record; that is not a species an
        agent can plant, so it is skipped rather than suggested."""
        assert self._suggest(candidates=[{"scientific_name": "", "common_name": ""}]) == []

    def test_a_non_dict_candidate_is_skipped_not_fatal(self) -> None:
        assert self._suggest(candidates=[None, 42]) == []  # type: ignore[list-item]

    def test_ranking_is_deterministic_across_input_order(self) -> None:
        candidates = [
            _species("c", "C", "Fabaceae", 40),
            _species("a", "A", "Poaceae", 40),
            _species("b", "B", "Asteraceae", 40),
        ]
        forward = self._suggest(candidates=candidates)
        backward = self._suggest(candidates=list(reversed(candidates)))
        assert [s.species_key for s in forward] == [s.species_key for s in backward]
        assert [s.species_key for s in forward] == ["a", "b", "c"]

    def test_same_input_twice_is_identical(self) -> None:
        candidates = [
            _species("b", "B", "Fabaceae", 40),
            _species("a", "A", "Poaceae", 60),
        ]
        assert self._suggest(candidates=candidates) == self._suggest(
            candidates=candidates
        )

    def test_inverted_gap_window_yields_no_confirmed_fit(self) -> None:
        out = self._suggest(
            candidates=[_species("beans", "Beans", "Fabaceae", 55)],
            gap_start="2026-07-15",
            gap_end="2026-06-01",
        )
        assert out[0].fits_window is False


class TestSuggestSuccessionAntagonism:
    """Pins the production antagonism path (``service=``), which the review found
    had zero tests while the alternative ``antagonist_species`` parameter was
    tested and never passed by production."""

    def _service(self):
        from open_garden_planner.services.companion_planting_service import (
            CompanionPlantingService,
        )

        return CompanionPlantingService()

    def _suggest(self, service, candidates, **kw):
        params = {
            "candidates": candidates,
            "gap_start": "2026-06-01",
            "gap_end": "2026-07-01",
            "service": service,
        }
        params.update(kw)
        return suggest_succession_for_agent(**params)

    def test_no_service_means_no_antagonism_exclusion(self) -> None:
        out = self._suggest(
            None, [_species("tomato", "Tomato", "Solanaceae", 60)]
        )
        assert [s.species_key for s in out] == ["tomato"]

    def test_a_service_that_knows_no_relationship_excludes_nothing(self) -> None:
        out = self._suggest(
            self._service(),
            [_species("tomato", "Tomato", "Solanaceae", 60)],
            neighbour_keys=["nonexistent plant"],
        )
        assert [s.species_key for s in out] == ["tomato"]

    def test_a_known_antagonistic_pair_is_excluded_through_the_service(self) -> None:
        """Measured from the bundled DB rather than hardcoded, so the test fails
        if the data changes or if the service lookup is bypassed."""
        service = self._service()
        pair = None
        for record in get_species_db().values():
            rel = service.get_relationship(
                species_key(record), species_key(record)
            )
            _ = rel
        # Find any antagonistic relationship in the bundled data.
        db = get_species_db()
        names = [species_key(r) for r in db.values()]
        for a in names:
            for b in names:
                if a >= b:
                    continue
                rel = service.get_relationship(a, b)
                if rel is not None and rel.type == ANTAGONISTIC:
                    pair = (a, b)
                    break
            if pair:
                break
        assert pair is not None, "bundled data has no antagonistic pair to test with"

        out = self._suggest(
            service, [_species(pair[0], pair[0], "Testaceae", 40)], neighbour_keys=[pair[1]]
        )
        assert out == []


# --- build_succession_plan_for_agent (the write validator) ------------------


class TestBuildSuccessionPlan:
    def test_builds_a_date_sorted_plan(self) -> None:
        plan = build_succession_plan_for_agent(
            [
                {"species_key": "lettuce", "common_name": "Lettuce", "start_date": "2026-08-01", "end_date": "2026-09-01"},
                {"species_key": "beans", "common_name": "Beans", "start_date": "2026-06-01", "end_date": "2026-07-15"},
            ],
            "bed-1",
            YEAR,
        )
        assert plan is not None
        assert [e.species_key for e in plan.entries] == ["beans", "lettuce"]
        assert plan.bed_id == "bed-1"
        assert plan.year == YEAR

    def test_empty_entries_means_delete(self) -> None:
        assert build_succession_plan_for_agent([], "bed-1", YEAR) is None
        assert build_succession_plan_for_agent(None, "bed-1", YEAR) is None

    def test_refuses_an_unknown_species(self) -> None:
        with pytest.raises(SuccessionPlanError, match="Unknown species_key"):
            build_succession_plan_for_agent(
                [{"species_key": "unicorn", "start_date": "2026-06-01", "end_date": "2026-07-01"}],
                "bed-1",
                YEAR,
                known_species_keys={"beans"},
            )

    def test_refuses_a_missing_species_key(self) -> None:
        with pytest.raises(SuccessionPlanError, match="no species_key"):
            build_succession_plan_for_agent(
                [{"start_date": "2026-06-01", "end_date": "2026-07-01"}], "bed-1", YEAR
            )

    def test_refuses_a_non_iso_date(self) -> None:
        with pytest.raises(SuccessionPlanError, match="non-ISO"):
            build_succession_plan_for_agent(
                [{"species_key": "beans", "start_date": "01/06/2026", "end_date": "2026-07-01"}],
                "bed-1",
                YEAR,
            )

    def test_refuses_an_end_before_its_start(self) -> None:
        with pytest.raises(SuccessionPlanError, match="before it starts"):
            build_succession_plan_for_agent(
                [{"species_key": "beans", "start_date": "2026-07-01", "end_date": "2026-06-01"}],
                "bed-1",
                YEAR,
            )

    def test_refuses_overlapping_entries(self) -> None:
        with pytest.raises(SuccessionPlanError, match="overlap"):
            build_succession_plan_for_agent(
                [
                    {"species_key": "beans", "common_name": "Beans", "start_date": "2026-06-01", "end_date": "2026-07-15"},
                    {"species_key": "lettuce", "common_name": "Lettuce", "start_date": "2026-07-01", "end_date": "2026-08-01"},
                ],
                "bed-1",
                YEAR,
            )

    def test_adjacent_entries_are_allowed(self) -> None:
        plan = build_succession_plan_for_agent(
            [
                {"species_key": "beans", "start_date": "2026-06-01", "end_date": "2026-07-15"},
                {"species_key": "lettuce", "start_date": "2026-07-16", "end_date": "2026-08-01"},
            ],
            "bed-1",
            YEAR,
        )
        assert plan is not None
        assert len(plan.entries) == 2

    def test_a_one_day_overlap_is_refused(self) -> None:
        """The off-by-one the review found unpinned: `start <= prev_end` means a
        slot ending the very day the next starts is an overlap, which the tool
        docstring previously said was fine."""
        with pytest.raises(SuccessionPlanError, match="overlap"):
            build_succession_plan_for_agent(
                [
                    {"species_key": "beans", "start_date": "2026-06-01", "end_date": "2026-07-15"},
                    {"species_key": "lettuce", "start_date": "2026-07-15", "end_date": "2026-08-01"},
                ],
                "bed-1",
                YEAR,
            )

    def test_the_species_key_is_stored_canonicalised(self) -> None:
        """Validated and stored forms must be the SAME string, or the persisted
        plan stops matching every other per-species surface."""
        plan = build_succession_plan_for_agent(
            [
                {"species_key": "Allium Sativum", "start_date": "2026-06-01", "end_date": "2026-07-15"}
            ],
            "bed-1",
            YEAR,
            known_species_keys={"allium sativum"},
        )
        assert plan is not None
        assert plan.entries[0].species_key == "allium sativum"

    def test_a_proper_case_key_is_accepted_against_a_lower_case_roster(self) -> None:
        plan = build_succession_plan_for_agent(
            [
                {"species_key": "Allium sativum", "start_date": "2026-06-01", "end_date": "2026-07-15"}
            ],
            "bed-1",
            YEAR,
            known_species_keys={"allium sativum"},
        )
        assert plan is not None

    def test_refuses_a_non_dict_entry(self) -> None:
        with pytest.raises(SuccessionPlanError, match="not an object"):
            build_succession_plan_for_agent(["beans"], "bed-1", YEAR)  # type: ignore[list-item]

    def test_every_refusal_names_the_offending_index(self) -> None:
        with pytest.raises(SuccessionPlanError, match="Entry 1"):
            build_succession_plan_for_agent(
                [
                    {"species_key": "beans", "start_date": "2026-06-01", "end_date": "2026-07-15"},
                    {"species_key": "bad", "start_date": "nope", "end_date": "2026-08-01"},
                ],
                "bed-1",
                YEAR,
            )

class TestHonestReasons:
    """A component that did not check something must not report a result that
    reads as a successful check (ADR-045 lesson (c)).

    An earlier version appended "No rotation conflict (<family> unused in this
    bed)" for ANY candidate carrying a family - including when no rotation data
    had been consulted at all, which asserts a check that never ran. Reverting
    the `and rotation_checked` half of the condition survived the whole suite,
    so it is pinned here.
    """

    def _suggest(self, **kw):
        params = {
            "candidates": [_species("beans", "Beans", "Fabaceae", 40)],
            "gap_start": "2026-06-01",
            "gap_end": "2026-07-15",
        }
        params.update(kw)
        return suggest_succession_for_agent(**params)

    def test_no_rotation_claim_when_no_rotation_data_was_consulted(self) -> None:
        reasons = self._suggest()[0].reasons
        assert not any("No rotation conflict" in r for r in reasons)

    def test_the_candidate_really_does_carry_a_family(self) -> None:
        """Guards the test above: without a family the clause is unreachable and
        the assertion would pass for the wrong reason."""
        assert self._suggest()[0].family == "Fabaceae"

    def test_a_rotation_claim_appears_once_families_were_consulted(self) -> None:
        reasons = self._suggest(avoid_families=["Brassicaceae"])[0].reasons
        assert any("No rotation conflict" in r for r in reasons)

    def test_a_familyless_candidate_says_so_rather_than_claiming_safety(self) -> None:
        out = suggest_succession_for_agent(
            candidates=[_species("mystery", "Mystery", "", 40)],
            gap_start="2026-06-01",
            gap_end="2026-07-15",
            avoid_families=["Brassicaceae"],
        )
        assert any("no family" in r.lower() for r in out[0].reasons)
        assert not any("No rotation conflict" in r for r in out[0].reasons)
