"""The plant facts the 3D info card v1 shows (Phase 17 L2.3, #386).

Each fact has ONE home that the rest of the app already answers from, and the card
asks it: the height's source at the plan date (``object_height.height_source_at``
— the same precedence as ``effective_height_cm``, with the date's growth), the
growth share (``growth_model.growth_share``) and the sowing / harvest windows
(``task_generator.calendar_windows`` — extracted from ``generate_calendar_tasks``,
which now calls it: one formula, pinned equal here).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from open_garden_planner.core.growth_model import growth_share
from open_garden_planner.core.object_height import (
    SOURCE_CONTAINER,
    SOURCE_CURRENT,
    SOURCE_CUSTOM,
    SOURCE_DEFAULT,
    SOURCE_GROWN,
    SOURCE_NONE,
    SOURCE_SPECIES,
    effective_height_cm,
    height_source,
    height_source_at,
)
from open_garden_planner.services.task_generator import (
    PlanState,
    PlantRowInput,
    calendar_windows,
    generate_calendar_tasks,
)

SPECIES = {"common_name": "Apple", "max_height_cm": 400.0, "max_spread_cm": 300.0}
PLANTED = date(2020, 4, 1)


def dated(**instance: object) -> dict:
    return {"plant_species": dict(SPECIES), "plant_instance": {"planting_date": PLANTED.isoformat(),
                                                               **instance}}


class TestHeightSourceAt:
    def test_a_grown_plant_says_grown(self) -> None:
        metadata = dated(current_height_cm=100.0)
        assert height_source_at("TREE", metadata, date(2023, 4, 1)) == SOURCE_GROWN
        # without a date it is the static source
        assert height_source_at("TREE", metadata, None) == height_source("TREE", metadata) == SOURCE_CURRENT

    def test_the_precedence_is_effective_heights(self) -> None:
        cases = [
            ("TREE", {**dated(current_height_cm=100.0), "object_height_cm": 250.0}, SOURCE_CUSTOM),
            ("CONTAINER", {"container_fill_height_cm": 30.0}, SOURCE_CONTAINER),
            ("TREE", {"plant_species": dict(SPECIES)}, SOURCE_SPECIES),
            ("HOUSE", {}, SOURCE_DEFAULT),
            ("TREE", {}, SOURCE_NONE),
        ]
        for object_type, metadata, expected in cases:
            assert height_source_at(object_type, metadata, date(2023, 4, 1)) == expected

    @pytest.mark.parametrize("years", [0, 1, 3, 10, 30])
    def test_grown_exactly_when_the_height_moves_with_the_date(self, years: int) -> None:
        """The source says ``grown`` for every date at which ``effective_height_cm``
        answers the date-projected height — parametrised over the age, the
        parameter the growth scales with."""
        metadata = dated(current_height_cm=100.0)
        day = PLANTED + timedelta(days=365 * years)
        assert height_source_at("TREE", metadata, day) == SOURCE_GROWN
        assert effective_height_cm("TREE", metadata, at_date=day) is not None


class TestGrowthShare:
    @pytest.mark.parametrize(("years", "share"), [(0, 0.0), (1, 0.1), (5, 0.5), (10, 1.0),
                                                  (25, 1.0)])
    def test_the_share_of_a_trees_ten_years(self, years: int, share: float) -> None:
        day = PLANTED + timedelta(days=365 * years)
        assert growth_share(dated(current_height_cm=100.0), day, "TREE") == pytest.approx(share)

    def test_before_planting_the_share_is_zero(self) -> None:
        assert growth_share(dated(current_height_cm=100.0), date(2019, 1, 1), "TREE") == 0.0

    def test_no_share_where_nothing_grows_on_the_timeline(self) -> None:
        day = date(2023, 4, 1)
        assert growth_share({"plant_species": dict(SPECIES)}, day, "TREE") is None   # no size, no date
        assert growth_share(dated(), day, "TREE") is None                          # no measured size
        assert growth_share({}, day, "TREE") is None                               # no species
        assert growth_share(None, day, "TREE") is None


class TestCalendarWindows:
    FROST = date(2026, 4, 15)
    OFFSETS = {"indoor_sow_start": -8, "indoor_sow_end": -6, "direct_sow_start": 2,
               "direct_sow_end": 4, "harvest_start": 12, "harvest_end": 18,
               "transplant_start": None, "transplant_end": 1}

    def test_the_windows_are_frost_plus_weeks(self) -> None:
        windows = calendar_windows(self.OFFSETS.get, self.FROST)
        assert windows == [
            ("indoor_sow", self.FROST - timedelta(weeks=8), self.FROST - timedelta(weeks=6)),
            ("direct_sow", self.FROST + timedelta(weeks=2), self.FROST + timedelta(weeks=4)),
            ("harvest", self.FROST + timedelta(weeks=12), self.FROST + timedelta(weeks=18)),
        ]  # a window with one end missing (transplant) is none

    def test_the_task_generator_draws_its_tasks_from_the_same_windows(self) -> None:
        row = PlantRowInput("Tomato", "solanum lycopersicum", **self.OFFSETS)
        state = PlanState(today=date(2026, 1, 1), year=2026, last_frost=self.FROST,
                          plant_rows=(row,), actionable_only=False)
        tasks = generate_calendar_tasks(state)
        assert [(t.task_type, t.start_date, t.end_date) for t in tasks] == calendar_windows(
            lambda field: getattr(row, field), self.FROST)
