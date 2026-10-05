"""Regressions found by the final pre-merge review of US-D3.2 (#331).

Each test here corresponds to a finding that was FIXED but not PINNED, which
is the same defect class the review itself was counting. They fail against the
pre-fix code.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from open_garden_planner.agent_api.domain import (
    get_succession_plan_for_agent,
    suggest_succession_for_agent,
)
from open_garden_planner.core.object_types import ObjectType
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
GARLIC = "allium sativum"


def _record(year: Any = 2025, family: str = "Solanaceae") -> dict[str, Any]:
    return {
        "year": year,
        "season": "summer",
        "species_name": "Cucumis sativus",
        "common_name": "Cucumber",
        "family": family,
        "nutrient_demand": "heavy",
        "area_id": "bed",
    }


# --------------------------------------------------------------------------- #
# P1-1: a malformed `year` must be dropped, not carried into the sort
# --------------------------------------------------------------------------- #


class TestCropRotationRecordReader:
    def _reader(self):
        from open_garden_planner.app.application import _read_crop_rotation_record

        return _read_crop_rotation_record

    def test_a_real_int_year_survives(self) -> None:
        assert self._reader()(_record()) is not None

    def test_a_string_year_is_dropped(self) -> None:
        """`PlantingRecord.from_dict` does `data["year"]` and never type-checks,
        so a string year used to survive deserialization and then raise
        `TypeError` inside the sort - outside the loop meant to guard it, and
        inside a Qt signal handler that only catches `RuntimeError`."""
        assert self._reader()(_record(year="2025")) is None

    def test_a_none_year_is_dropped(self) -> None:
        assert self._reader()(_record(year=None)) is None

    def test_a_list_year_is_dropped(self) -> None:
        assert self._reader()(_record(year=[2025])) is None

    def test_a_bool_year_is_dropped(self) -> None:
        assert self._reader()(_record(year=True)) is None

    def test_a_missing_year_is_dropped(self) -> None:
        row = _record()
        del row["year"]
        assert self._reader()(row) is None

    def test_a_non_dict_row_is_dropped(self) -> None:
        assert self._reader()("garbage") is None

    def test_one_bad_row_does_not_disable_the_cooldown(self) -> None:
        reader = self._reader()
        rows = [_record(year="2025"), _record(year=2024)]
        kept = [r for r in (reader(r) for r in rows) if r is not None]
        assert len(kept) == 1
        assert kept[0].year == 2024
        # And the survivors must sort without raising.
        from open_garden_planner.models.crop_rotation import CropRotationHistory

        CropRotationHistory(records=kept).get_records_for_area("bed")


# --------------------------------------------------------------------------- #
# P1-2: a placed custom species must be writable
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_custom_species(qtbot: Any):
    """A bed holding a plant whose species is NOT in the bundled database."""
    from open_garden_planner.app.application import GardenPlannerApp

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._confirm_discard_changes = lambda: True  # type: ignore[method-assign]
    win._project_manager.set_location(dict(LOCATION))

    scene = win.canvas_scene
    bed = RectangleItem(0, 0, 200, 100)
    bed.object_type = ObjectType.RAISED_BED
    scene.addItem(bed)

    from open_garden_planner.ui.canvas.items import CircleItem

    plant = CircleItem(0, 0, 30)
    plant.object_type = ObjectType.TREE
    # A Permapeople/custom record: `source_id` is its canonical key (ADR-016)
    # and its name resolves to nothing in the bundled DB.
    # `metadata` is a read-only property returning the live dict, so mutate it
    # in place rather than assigning.
    plant.metadata["plant_species"] = {
        "source_id": "pfa:1234",
        "scientific_name": "Testus customus",
        "common_name": "Custom Berry",
        "family": "Rosaceae",
    }
    plant.parent_bed_id = bed.item_id
    scene.addItem(plant)

    try:
        yield win, bed
    finally:
        win._stop_agent_api()


class TestCustomSpeciesIsWritable:
    def test_the_bundled_lookup_alone_would_miss_it(self, app_with_custom_species) -> None:
        """Guards the test below: proves the species really is unresolvable
        through the bundled DB, which is why the roster had to change."""
        from open_garden_planner.services.bundled_species_db import lookup_species

        _win, bed = app_with_custom_species
        assert lookup_species("pfa:1234") is None
        assert lookup_species("Custom Berry") is None

    def test_a_placed_custom_species_can_be_planned(self, app_with_custom_species) -> None:
        _win, bed = app_with_custom_species
        result = _win._do_agent_set_succession_plan(
            str(bed.item_id),
            [
                {
                    "species_key": "pfa:1234",
                    "common_name": "Custom Berry",
                    "start_date": "2026-06-01",
                    "end_date": "2026-07-15",
                }
            ],
            2026,
        )
        assert result["action"] == "set_succession_plan"
        stored = _win._project_manager.succession_plans[str(bed.item_id)]
        assert stored["entries"][0]["species_key"] == "pfa:1234"

    def test_a_genuinely_unknown_species_is_still_refused(self, app_with_custom_species) -> None:
        _win, bed = app_with_custom_species
        with pytest.raises(ValueError, match="Unknown species_key"):
            _win._do_agent_set_succession_plan(
                str(bed.item_id),
                [
                    {
                        "species_key": "totally made up",
                        "common_name": "Nope",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
                2026,
            )


# --------------------------------------------------------------------------- #
# P1-3: a year mismatch must not answer with another year's plan
# --------------------------------------------------------------------------- #


def _plan(year: int = 2026) -> dict[str, Any]:
    return {
        "bed_id": "bed",
        "year": year,
        "entries": [
            {
                "id": "a",
                "species_key": GARLIC,
                "common_name": "Garlic",
                "start_date": f"{year}-06-01",
                "end_date": f"{year}-07-15",
            }
        ],
    }


class TestYearMismatch:
    def _view(self, asked: int | None):
        return get_succession_plan_for_agent(
            _plan(2026),
            "bed",
            year=asked,
            today=datetime.date(2026, 6, 20),
            location=LOCATION,
        )

    def test_asking_the_stored_year_returns_the_plan(self) -> None:
        v = self._view(2026)
        assert v.has_plan is True
        assert v.entries[0].species_key == GARLIC
        assert v.plan_year is None

    def test_omitting_the_year_returns_the_stored_plan(self) -> None:
        v = self._view(None)
        assert v.has_plan is True
        assert v.year == 2026

    def test_asking_another_year_reports_no_plan_for_that_year(self) -> None:
        """Pre-fix this returned `has_plan: true` with 2026 dates and
        `season: null` on every entry, which reads as a data fault rather than a
        year mismatch."""
        v = self._view(2027)
        assert v.has_plan is False
        assert v.entries == []
        assert v.current_entry is None
        assert v.year == 2027

    def test_and_says_which_year_the_bed_actually_has(self) -> None:
        assert self._view(2027).plan_year == 2026
        assert self._view(2026).plan_year is None

    def test_the_segments_still_describe_the_year_asked_about(self) -> None:
        assert self._view(2027).segments[0].start_date.startswith("2027")


# --------------------------------------------------------------------------- #
# P2-1 / P2-2: ranking determinism and honest reasons
# --------------------------------------------------------------------------- #


def _species(name: str, family: str = "Fabaceae", maturity: int = 50) -> dict[str, Any]:
    return {
        "scientific_name": name,
        "common_name": name,
        "family": family,
        "days_to_maturity_min": maturity,
    }


class TestRankingAndReasons:
    def test_two_names_for_one_species_produce_one_row(self) -> None:
        """An alias and the scientific name resolve to the SAME bundled record,
        which used to yield two rows with an identical sort key - so the order
        followed the input and the answer listed a crop twice."""
        from open_garden_planner.services.bundled_species_db import lookup_species

        record = lookup_species("allium sativum")
        assert record is not None
        out = suggest_succession_for_agent(
            candidates=[record, dict(record)],
            gap_start="2026-06-01",
            gap_end="2026-07-15",
        )
        assert len(out) == 1

    def test_order_is_identical_when_the_input_is_reversed(self) -> None:
        from open_garden_planner.services.bundled_species_db import lookup_species

        a = dict(lookup_species("allium sativum") or {})
        b = dict(lookup_species("lactuca sativa") or {})
        fwd = [
            s.species_key
            for s in suggest_succession_for_agent(
                candidates=[a, b], gap_start="2026-06-01", gap_end="2026-07-15"
            )
        ]
        bwd = [
            s.species_key
            for s in suggest_succession_for_agent(
                candidates=[b, a], gap_start="2026-06-01", gap_end="2026-07-15"
            )
        ]
        assert fwd == bwd

    def test_a_malformed_window_is_reported_as_unusable_not_as_zero_days(self) -> None:
        """Saying "the gap is only 0 days" about a window that does not exist is
        a confidently wrong statement, and the write tool refuses the same
        dates."""
        for start, end in (("not-a-date", "2026-07-15"), ("2026-06-01", ""),
                           ("2026-07-15", "2026-06-01")):
            out = suggest_succession_for_agent(
                candidates=[_species("Beans")], gap_start=start, gap_end=end
            )
            assert out, "a candidate must still be returned"
            assert any("unusable" in r for r in out[0].reasons), out[0].reasons
            assert not any("0 days" in r for r in out[0].reasons), out[0].reasons

    def test_a_real_window_still_reports_the_day_count(self) -> None:
        out = suggest_succession_for_agent(
            candidates=[_species("Beans", maturity=30)],
            gap_start="2026-06-01",
            gap_end="2026-07-15",
        )
        # 2026-06-01..2026-07-15 inclusive is 45 days.
        assert any("45" in r for r in out[0].reasons), out[0].reasons
        assert not any("unusable" in r for r in out[0].reasons), out[0].reasons


# --------------------------------------------------------------------------- #
# P2-4: the selftest stub must stay mypy-clean
# --------------------------------------------------------------------------- #


class TestSelftestProviderStub:
    def test_the_stub_is_built_from_the_dataclass_fields(self) -> None:
        """Deriving the fields is what stopped the list drifting; the cast keeps
        the static check working, which the explicit list gave for free.

        Read as source rather than imported: `main` imports QtWebEngineWidgets
        at module scope, which must happen BEFORE any QApplication exists, so
        importing it from a running test suite always fails.
        """
        from pathlib import Path

        from open_garden_planner.app import settings as _settings

        main_py = (
            Path(_settings.__file__).resolve().parent.parent / "main.py"
        )
        assert main_py.exists(), main_py
        src = main_py.read_text(encoding="utf-8")
        assert "dict.fromkeys(AgentProviders.__dataclass_fields__" in src
        assert 'cast("dict[str, Any]"' in src
