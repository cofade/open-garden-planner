"""Tests for the PRODUCTION succession providers in ``application.py`` (US-D3.2, #331).

``test_agent_succession_tools.py`` boots a real MCP server but wires its OWN
provider implementations, which means it exercises the transport, the schema
and the domain logic - **not** ``application.py``. Every interesting decision in
this story lives in that layer: the ``is_bed_type`` refusal, the ``run_on_main``
hop, the species roster, the rotation cooldown and the badge refresh.

So this file drives the real ``_do_agent_*`` bodies on the main thread against a
real ``GardenPlannerApp``, following the pattern ``test_agent_api_default_on.py``
established. Each test here is chosen because a mutation of the corresponding
production line makes it fail - the reviewer's mutation run showed seven such
mutations surviving the entire suite before this file existed.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.crop_rotation import CropRotationHistory, PlantingRecord
from open_garden_planner.ui.canvas.items import RectangleItem

LOCATION: dict[str, Any] = {
    "latitude": 52.5,
    "longitude": 13.4,
    "frost_dates": {
        "last_spring_frost": "04-15",
        "first_fall_frost": "10-15",
        "hardiness_zone": "7a",
    },
}
# Real bundled species, keyed by the canonical ADR-016 form (scientific name).
GARLIC = "allium sativum"
TOMATO = "solanum lycopersicum"
BEAN = "phaseolus vulgaris"


@pytest.fixture
def app_with_beds(qtbot: Any):
    """A real GardenPlannerApp holding one raised bed and one trellis.

    Yields ``(window, bed, trellis)``. The trellis is the plant-parent that
    holds no soil: succession must refuse it, and refusing it is the single
    behavioural difference between this story and D3.1's ``check_placement``.
    """
    from open_garden_planner.app.application import GardenPlannerApp

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    # Several tests deliberately dirty the document, and qtbot's teardown calls
    # close(), which would raise the modal "discard changes?" dialog and hang the
    # run. Patch it HERE, at setup, because pytest-qt closes widgets BEFORE this
    # generator fixture's teardown runs - patching in teardown is too late.
    # Production code is untouched; this only answers the prompt.
    win._confirm_discard_changes = lambda: True  # type: ignore[method-assign]
    win._project_manager.set_location(dict(LOCATION))

    scene = win.canvas_scene
    bed = RectangleItem(0, 0, 200, 100)
    bed.object_type = ObjectType.RAISED_BED
    scene.addItem(bed)

    trellis = RectangleItem(500, 0, 200, 100)
    trellis.object_type = ObjectType.TRELLIS
    scene.addItem(trellis)

    try:
        yield win, bed, trellis
    finally:
        win._stop_agent_api()


def _slot(key: str, name: str, start: str, end: str) -> dict[str, Any]:
    return {
        "species_key": key,
        "common_name": name,
        "start_date": start,
        "end_date": end,
    }


class TestProductionBedResolution:
    """Pins the ``is_bed_type`` refusal, which no other test covered.

    Mutating ``_agent_resolve_soil_bed`` from ``is_bed_type`` to the looser
    ``is_plant_parent_type`` made every other test in the suite still pass before
    this file existed.
    """

    def test_a_raised_bed_is_accepted(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        view = win._do_agent_get_succession_plan(str(bed.item_id), None, None)
        assert view["has_plan"] is False
        assert view["coverage"] == "full"

    def test_a_trellis_is_refused_by_every_tool(self, app_with_beds: Any) -> None:
        win, _bed, trellis = app_with_beds
        tid = str(trellis.item_id)

        with pytest.raises(ValueError, match="soil-capable"):
            win._do_agent_get_succession_plan(tid, None, None)
        with pytest.raises(ValueError, match="soil-capable"):
            win._do_agent_find_succession_gaps(tid, None, None)
        with pytest.raises(ValueError, match="soil-capable"):
            win._do_agent_suggest_succession(tid, "2026-06-01", "2026-07-01", ["Garlic"])
        with pytest.raises(ValueError, match="soil-capable"):
            win._do_agent_set_succession_plan(
                tid, [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 2026
            )

    def test_a_trellis_refusal_touches_nothing(self, app_with_beds: Any) -> None:
        win, _bed, trellis = app_with_beds
        with pytest.raises(ValueError):
            win._do_agent_set_succession_plan(
                str(trellis.item_id),
                [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")],
                2026,
            )
        assert win._project_manager.succession_plans == {}

    def test_an_unknown_id_is_refused_not_reported_empty(self, app_with_beds: Any) -> None:
        win, _bed, _trellis = app_with_beds
        with pytest.raises(ValueError, match="No object with id"):
            win._do_agent_get_succession_plan("00000000-0000-0000-0000-000000000000", None, None)

    def test_a_malformed_id_is_refused(self, app_with_beds: Any) -> None:
        win, _bed, _trellis = app_with_beds
        with pytest.raises(ValueError, match="not a valid bed id"):
            win._do_agent_get_succession_plan("not-a-uuid", None, None)


class TestProductionWriteAndBadge:
    """The write, the undo step, and the signal-driven badge refresh.

    ADR-036 claimed "this is asserted by a test rather than assumed" about the
    badge. That claim was false until this test existed - so the claim and the
    test now agree.
    """

    def test_write_then_undo_is_one_step(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        cm = win.canvas_view.command_manager
        before = cm.undo_depth

        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 2026
        )
        assert cm.undo_depth == before + 1
        assert GARLIC in str(win._project_manager.succession_plans[str(bed.item_id)])

        cm.undo()
        assert str(bed.item_id) not in win._project_manager.succession_plans
        assert cm.undo_depth == before

    def test_the_write_marks_the_project_dirty(self, app_with_beds: Any) -> None:
        """`is_dirty` is the user's unsaved-changes guard, so a write that does
        not set it means closing the app silently discards the agent's plan.

        The baseline has to be established explicitly: the fixture's own
        ``set_location`` marks the document dirty, so asserting `is_dirty` after
        the write proved nothing - deleting ``mark_dirty()`` from
        ``ProjectManager.set_succession_plan`` left this test green.
        """
        win, bed, _trellis = app_with_beds
        pm = win._project_manager
        pm.mark_clean()
        assert pm.is_dirty is False

        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 2026
        )
        assert pm.is_dirty is True

    def test_the_bed_badge_updates_without_an_explicit_refresh_call(
        self, app_with_beds: Any
    ) -> None:
        """ADR-036's design decision: the badge comes from the
        ``succession_plans_changed`` signal chain, so application.py does NOT
        duplicate the dialog's explicit ``_refresh_succession_indicators()``.

        This is the test that claim was missing. It writes through the agent
        provider and asserts the badge state changed - if the signal chain were
        broken, or the write stopped emitting, this fails with no explicit refresh
        anywhere in the path under test.
        """
        win, bed, _trellis = app_with_beds
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=5)).isoformat()
        end = (today + datetime.timedelta(days=5)).isoformat()

        assert bed._succession_lines == []

        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(GARLIC, "Garlic", start, end)], 2026
        )

        # The badge was populated purely by the signal chain.
        assert bed._succession_lines, (
            "the agent write did not refresh the succession badge; the "
            "succession_plans_changed -> _refresh_succession_indicators chain "
            "is broken"
        )
        names = [name for name, _is_current in bed._succession_lines]
        assert "Garlic" in names
        assert dict(bed._succession_lines)["Garlic"] is True, (
            "a slot covering today must be marked as the current one"
        )

    def test_the_badge_clears_when_the_plan_is_deleted(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        today = datetime.date.today()
        win._do_agent_set_succession_plan(
            str(bed.item_id),
            [
                _slot(
                    GARLIC,
                    "Garlic",
                    (today - datetime.timedelta(days=5)).isoformat(),
                    (today + datetime.timedelta(days=5)).isoformat(),
                )
            ],
            2026,
        )
        assert bed._succession_lines

        win._do_agent_set_succession_plan(str(bed.item_id), [], 2026)
        assert bed._succession_lines == []

    def test_a_refused_write_leaves_the_stack_and_plans_untouched(
        self, app_with_beds: Any
    ) -> None:
        win, bed, _trellis = app_with_beds
        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 2026
        )
        stored = dict(win._project_manager.succession_plans[str(bed.item_id)])
        depth = win.canvas_view.command_manager.undo_depth

        with pytest.raises(ValueError, match="overlap"):
            win._do_agent_set_succession_plan(
                str(bed.item_id),
                [
                    _slot(GARLIC, "Garlic", "2026-06-01", "2026-07-15"),
                    _slot(TOMATO, "Tomato", "2026-07-01", "2026-08-01"),
                ],
                2026,
            )
        assert win._project_manager.succession_plans[str(bed.item_id)] == stored
        assert win.canvas_view.command_manager.undo_depth == depth

    def test_a_nonsensical_year_is_refused(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        with pytest.raises(ValueError, match="out of range"):
            win._do_agent_set_succession_plan(
                str(bed.item_id), [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 12
            )
        assert win._project_manager.succession_plans == {}
        assert win.canvas_view.command_manager.undo_depth == 0

    def test_a_malformed_today_is_refused_rather_than_ignored(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        with pytest.raises(ValueError, match="not an ISO date"):
            win._do_agent_get_succession_plan(str(bed.item_id), None, "01/06/2026")


class TestProductionSpeciesValidation:
    def test_the_canonical_key_is_stored(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(GARLIC, "Garlic", "2026-06-01", "2026-07-01")], 2026
        )
        stored = win._project_manager.succession_plans[str(bed.item_id)]
        assert stored["entries"][0]["species_key"] == GARLIC

    def test_proper_case_is_accepted_and_normalised(self, app_with_beds: Any) -> None:
        """``set_species`` and ``suggest_succession`` both accept "Allium
        sativum"; the write tool must not be the odd one out."""
        win, bed, _trellis = app_with_beds
        win._do_agent_set_succession_plan(
            str(bed.item_id),
            [_slot("Allium sativum", "Garlic", "2026-06-01", "2026-07-01")],
            2026,
        )
        stored = win._project_manager.succession_plans[str(bed.item_id)]
        assert stored["entries"][0]["species_key"] == GARLIC

    def test_an_unknown_species_is_refused(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        with pytest.raises(ValueError, match="Unknown species_key"):
            win._do_agent_set_succession_plan(
                str(bed.item_id),
                [_slot("totally made up", "Nope", "2026-06-01", "2026-07-01")],
                2026,
            )
        assert win._project_manager.succession_plans == {}


class TestProductionSuggestionFilters:
    def test_a_family_used_earlier_in_the_plan_is_excluded(
        self, app_with_beds: Any
    ) -> None:
        """Pins the precedence fix: ``species_key`` is the machine contract, so a
        display name that disagrees with it must not steer the family lookup."""
        win, bed, _trellis = app_with_beds
        win._do_agent_set_succession_plan(
            str(bed.item_id), [_slot(TOMATO, "Garlic", "2026-04-01", "2026-05-01")], 2026
        )
        # A deliberately mismatched entry: key says tomato (Solanaceae), the
        # display name says garlic. The key must win.
        assert win._agent_plan_families_before(
            win._project_manager.succession_plans[str(bed.item_id)], "2026-06-01"
        ) == ["Solanaceae"]

    def test_the_cross_year_cooldown_is_read_from_rotation_history(
        self, app_with_beds: Any
    ) -> None:
        """Pins that ``_agent_rotation_avoid_families`` actually consults the
        rotation service - mutating it to ``[]`` survived the suite before."""
        win, bed, _trellis = app_with_beds
        pm = win._project_manager
        pm.set_crop_rotation(
            CropRotationHistory(
                records=[
                    PlantingRecord(
                        year=datetime.date.today().year - 1,
                        season="summer",
                        species_name="Tomato",
                        common_name="Tomato",
                        family="Solanaceae",
                        nutrient_demand="heavy",
                        area_id=str(bed.item_id),
                    )
                ]
            ).to_dict()
        )
        assert "Solanaceae" in win._agent_rotation_avoid_families(str(bed.item_id))

    def test_with_no_history_no_family_is_avoided(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        assert win._agent_rotation_avoid_families(str(bed.item_id)) == []

    def test_one_unreadable_record_does_not_disable_the_cooldown(
        self, app_with_beds: Any
    ) -> None:
        """A comprehension plus a broad catch returned [] for the WHOLE garden
        when any single record failed to deserialize - so one bad row silently
        removed the family cooldown from every bed. Only that row may be lost."""
        win, bed, _trellis = app_with_beds
        pm = win._project_manager
        good = {
            "year": datetime.date.today().year - 1,
            "season": "summer",
            "species_name": "Tomato",
            "common_name": "Tomato",
            "family": "Solanaceae",
            "nutrient_demand": "heavy",
            "area_id": str(bed.item_id),
        }
        # Missing "year" - PlantingRecord.from_dict requires it.
        bad = dict(good)
        del bad["year"]
        pm.set_crop_rotation({"records": [bad, good]})

        assert "Solanaceae" in win._agent_rotation_avoid_families(str(bed.item_id))

    def test_a_free_text_slot_resolves_by_scientific_name(self, app_with_beds: Any) -> None:
        """``_entry_species_names`` tries scientific_name too, so an entry stored
        with only a scientific name still resolves."""
        win, bed, _trellis = app_with_beds
        plan = {
            "bed_id": str(bed.item_id),
            "year": 2026,
            "entries": [
                {
                    "id": "x",
                    "species_key": "",
                    "common_name": "",
                    "scientific_name": "Allium sativum",
                    "start_date": "2026-06-01",
                    "end_date": "2026-07-01",
                }
            ],
        }
        assert win._agent_plan_families_before(plan, "2026-08-01") == ["Amaryllidaceae"]
        assert win._agent_concurrent_species_keys(plan, "2026-06-15", "2026-06-20") == [
            "Allium sativum"
        ]

    def test_candidates_resolve_through_the_bundled_db(self, app_with_beds: Any) -> None:
        """Pins that ``_agent_species_records`` resolves a display name; returning
        ``None`` everywhere survived the suite before."""
        win, _bed, _trellis = app_with_beds
        records = win._agent_species_records(["Garlic"])
        assert len(records) == 1
        assert records[0]["family"] == "Amaryllidaceae"

        out = win._do_agent_suggest_succession(
            str(_bed.item_id), "2026-06-01", "2026-07-01", ["Garlic", "Tomato"]
        )
        keys = [s["species_key"] for s in out]
        assert GARLIC in keys and TOMATO in keys

    def test_an_unresolvable_candidate_yields_no_record(self, app_with_beds: Any) -> None:
        win, _bed, _trellis = app_with_beds
        assert win._agent_species_records(["Not A Plant"]) == []

    def test_a_free_text_slot_resolves_by_display_name(self, app_with_beds: Any) -> None:
        """``SuccessionEntryView.species_key`` explicitly permits an empty key, so
        both filters must fall back to the name rather than disagreeing."""
        win, bed, _trellis = app_with_beds
        plan = {
            "bed_id": str(bed.item_id),
            "year": 2026,
            "entries": [
                {
                    "id": "x",
                    "species_key": "",
                    "common_name": "Garlic",
                    "start_date": "2026-06-01",
                    "end_date": "2026-07-01",
                }
            ],
        }
        assert win._agent_plan_families_before(plan, "2026-08-01") == ["Amaryllidaceae"]
        assert win._agent_concurrent_species_keys(plan, "2026-06-15", "2026-06-20") == [
            "Garlic"
        ]


class TestProductionThreadHop:
    """Every provider must hop to the Qt main thread.

    Removing ``run_on_main`` from the read providers survived the whole suite
    before this file existed; the mutation is invisible to a test that calls the
    ``_do_agent_*`` body directly, so the hop itself is asserted by checking that
    the public provider is the one that hops.
    """

    def test_read_providers_wrap_their_body_in_the_bridge(self, app_with_beds: Any) -> None:
        win, bed, _trellis = app_with_beds
        calls: list[object] = []
        real = win._agent_bridge.run_on_main

        def spy(fn: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(fn)
            return real(fn, *args, **kwargs)

        win._agent_bridge.run_on_main = spy  # type: ignore[method-assign]
        try:
            win._agent_get_succession_plan(str(bed.item_id))
            win._agent_find_succession_gaps(str(bed.item_id))
            win._agent_suggest_succession(
                str(bed.item_id), "2026-06-01", "2026-07-01", ["Garlic"]
            )
        finally:
            win._agent_bridge.run_on_main = real  # type: ignore[method-assign]
        assert len(calls) == 3