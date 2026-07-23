"""Unit tests for the Qt-free object-height resolver (US-E2, #257).

Pins the full precedence chain (explicit > container fill > measured
current height > species max_height_cm > per-type default > None), the
date-projected growth branch (US-E8), the value guards, and — because
the module deliberately matches object types by *name* to stay Qt-free —
the sync between its name sets and the real ``ObjectType`` enum.
"""

from __future__ import annotations

from datetime import date

import pytest

from open_garden_planner.core.object_height import (
    DEFAULT_HEIGHTS_CM,
    METADATA_KEY,
    SOURCE_CONTAINER,
    SOURCE_CURRENT,
    SOURCE_CUSTOM,
    SOURCE_DEFAULT,
    SOURCE_NONE,
    SOURCE_SPECIES,
    effective_height_cm,
    explicit_height_cm,
    has_height_semantics,
    height_source,
)


class TestPrecedence:
    def test_explicit_wins_over_everything(self) -> None:
        meta = {
            METADATA_KEY: 90.0,
            "container_height_cm": 30.0,
            "plant_species": {"max_height_cm": 200.0},
        }
        assert effective_height_cm("CONTAINER", meta) == 90.0
        assert height_source("CONTAINER", meta) == SOURCE_CUSTOM

    def test_container_fill_height_when_no_explicit(self) -> None:
        meta = {"container_height_cm": 45.0}
        assert effective_height_cm("CONTAINER", meta) == 45.0
        assert height_source("CONTAINER", meta) == SOURCE_CONTAINER

    def test_container_default_fill_when_no_keys(self) -> None:
        # container_model.DEFAULT_HEIGHT_CM = 30 — the soil-fill default.
        assert effective_height_cm("CONTAINER_ROUND", {}) == 30.0
        assert effective_height_cm("WALL_PLANTER", None) == 30.0

    def test_species_max_height_for_plants(self) -> None:
        meta = {"plant_species": {"max_height_cm": 180.0}}
        assert effective_height_cm("TREE", meta) == 180.0
        assert height_source("TREE", meta) == SOURCE_SPECIES

    def test_species_less_plant_has_no_height(self) -> None:
        assert effective_height_cm("TREE", {}) is None
        assert height_source("TREE", {}) == SOURCE_NONE

    def test_type_default_when_nothing_else(self) -> None:
        assert effective_height_cm("FENCE", {}) == 120.0
        assert effective_height_cm("WALL", None) == 200.0
        assert height_source("FENCE", {}) == SOURCE_DEFAULT

    def test_no_semantics_type_returns_none(self) -> None:
        assert effective_height_cm("GENERIC_RECTANGLE", {}) is None
        assert height_source("GENERIC_RECTANGLE", {}) == SOURCE_NONE

    def test_enum_members_work_like_names(self) -> None:
        from open_garden_planner.core.object_types import ObjectType

        assert effective_height_cm(ObjectType.FENCE, {}) == 120.0
        assert effective_height_cm(
            ObjectType.CONTAINER, {"container_height_cm": 45.0}
        ) == 45.0


class TestDefaultTable:
    @pytest.mark.parametrize(
        "name, expected",
        sorted(DEFAULT_HEIGHTS_CM.items()),
    )
    def test_every_default_row(self, name: str, expected: float) -> None:
        assert effective_height_cm(name, {}) == expected

    def test_default_names_exist_in_enum(self) -> None:
        """Every name in the default table must be a real ObjectType member —
        a rename in object_types.py must break this test, not silently
        orphan a default."""
        from open_garden_planner.core.object_types import ObjectType

        enum_names = {member.name for member in ObjectType}
        assert set(DEFAULT_HEIGHTS_CM) <= enum_names

    def test_container_names_match_container_types(self) -> None:
        from open_garden_planner.core.object_height import _CONTAINER_TYPE_NAMES
        from open_garden_planner.core.object_types import CONTAINER_TYPES

        assert _CONTAINER_TYPE_NAMES == {t.name for t in CONTAINER_TYPES}

    def test_plant_names_match_plant_types(self) -> None:
        from open_garden_planner.core.object_height import _PLANT_TYPE_NAMES
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        plant_names = {t.name for t in ObjectType if is_plant_type(t)}
        assert _PLANT_TYPE_NAMES == plant_names


class TestValueGuards:
    @pytest.mark.parametrize("bad", [0, -5, 0.0, -0.1, True, False, "120", None])
    def test_invalid_explicit_values_ignored(self, bad) -> None:
        meta = {METADATA_KEY: bad}
        assert explicit_height_cm(meta) is None
        # Falls through to the type default instead of the bad value.
        assert effective_height_cm("FENCE", meta) == 120.0

    def test_non_dict_species_ignored(self) -> None:
        assert effective_height_cm("TREE", {"plant_species": "tomato"}) is None

    def test_species_without_height_falls_through(self) -> None:
        # TRELLIS has a type default; a species dict lacking max_height_cm
        # must not mask it.
        meta = {"plant_species": {"name": "clematis"}}
        assert effective_height_cm("TRELLIS", meta) == 180.0

    def test_empty_and_none_metadata(self) -> None:
        assert explicit_height_cm({}) is None
        assert explicit_height_cm(None) is None


class TestHasHeightSemantics:
    def test_default_table_types(self) -> None:
        assert has_height_semantics("FENCE", {})
        assert has_height_semantics("HOUSE", None)

    def test_containers_and_plants(self) -> None:
        assert has_height_semantics("CONTAINER", {})
        assert has_height_semantics("TREE", {})  # even without species

    def test_explicit_height_grants_semantics_to_any_type(self) -> None:
        assert not has_height_semantics("GENERIC_RECTANGLE", {})
        assert has_height_semantics("GENERIC_RECTANGLE", {METADATA_KEY: 50.0})


class TestCurrentHeightAnchor:
    """US-E8 redesign: the plant's MEASURED current height drives shade.

    The owner reported that shadows scaled only on the species max height
    while the Plant Details "Current height" field did nothing at all.
    """

    def test_current_height_beats_species_max(self) -> None:
        meta = {
            "plant_species": {"max_height_cm": 500.0},
            "plant_instance": {"current_height_cm": 120.0},
        }
        assert effective_height_cm("TREE", meta) == 120.0
        assert height_source("TREE", meta) == SOURCE_CURRENT

    def test_explicit_override_still_wins(self) -> None:
        meta = {
            METADATA_KEY: 90.0,
            "plant_species": {"max_height_cm": 500.0},
            "plant_instance": {"current_height_cm": 120.0},
        }
        assert effective_height_cm("TREE", meta) == 90.0
        assert height_source("TREE", meta) == SOURCE_CUSTOM

    def test_dated_plant_grows_from_current_to_max(self) -> None:
        meta = {
            "plant_species": {"max_height_cm": 500.0},
            "plant_instance": {
                "planting_date": "2026-01-01",
                "current_height_cm": 100.0,
            },
        }
        # TREE horizon is 10 y, so 2031 is the halfway point.
        assert effective_height_cm(
            "TREE", meta, at_date=date(2026, 1, 1)
        ) == pytest.approx(100.0)
        assert effective_height_cm(
            "TREE", meta, at_date=date(2031, 1, 1)
        ) == pytest.approx(300.0, abs=2.0)
        assert effective_height_cm(
            "TREE", meta, at_date=date(2050, 1, 1)
        ) == pytest.approx(500.0)

    def test_measured_plant_without_species_still_has_height(self) -> None:
        """A species lookup MISS is a supported state (the plant falls back
        to the API search button). A height the user measured by hand must
        still cast a shadow — and must agree with height_source, which
        reports SOURCE_CURRENT whether or not a species is attached.
        """
        meta = {"plant_instance": {"current_height_cm": 200.0}}
        assert effective_height_cm("TREE", meta) == 200.0
        assert effective_height_cm("TREE", meta, at_date=date(2031, 1, 1)) == 200.0
        assert height_source("TREE", meta) == SOURCE_CURRENT

    def test_species_less_unmeasured_plant_still_has_no_height(self) -> None:
        assert effective_height_cm("TREE", {"plant_instance": {}}) is None
        assert height_source("TREE", {"plant_instance": {}}) == SOURCE_NONE

    def test_unmeasured_plant_stays_mature_even_with_a_date(self) -> None:
        meta = {
            "plant_species": {"max_height_cm": 500.0},
            "plant_instance": {"planting_date": "2026-01-01"},
        }
        assert effective_height_cm("TREE", meta, at_date=date(2031, 1, 1)) == 500.0
        assert height_source("TREE", meta) == SOURCE_SPECIES
