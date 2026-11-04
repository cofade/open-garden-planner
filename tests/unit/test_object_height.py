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
    GROUND_SURFACE_TYPE_NAMES,
    METADATA_KEY,
    SOURCE_CONTAINER,
    SOURCE_CURRENT,
    SOURCE_CUSTOM,
    SOURCE_DEFAULT,
    SOURCE_GROWN,
    SOURCE_NONE,
    SOURCE_SPECIES,
    effective_height_cm,
    explicit_height_cm,
    has_height_semantics,
    height_source,
    height_source_at,
    resolve_height,
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

        assert {t.name for t in CONTAINER_TYPES} == _CONTAINER_TYPE_NAMES

    def test_plant_names_match_plant_types(self) -> None:
        from open_garden_planner.core.object_height import _PLANT_TYPE_NAMES
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        plant_names = {t.name for t in ObjectType if is_plant_type(t)}
        assert plant_names == _PLANT_TYPE_NAMES

    def test_soil_parent_names_match_the_soil_predicate(self) -> None:
        """L1.6: a plant stands on the soil of exactly the types ``is_bed_type``
        calls soil-capable. The name set is a Qt-free mirror of the repo's ONE
        predicate — a type added to (or dropped from) ``SOIL_CONTAINER_TYPES``
        must break this test, not silently leave a plant on the ground."""
        from open_garden_planner.core.object_height import (
            _SOIL_PARENT_TYPE_NAMES,
            standing_base_cm,
        )
        from open_garden_planner.core.object_types import (
            SOIL_CONTAINER_TYPES,
            ObjectType,
            is_bed_type,
            is_plant_parent_type,
        )

        assert {t.name for t in SOIL_CONTAINER_TYPES} == _SOIL_PARENT_TYPE_NAMES
        assert {t.name for t in ObjectType if is_bed_type(t)} == _SOIL_PARENT_TYPE_NAMES
        tall = {METADATA_KEY: 50.0}
        for member in ObjectType:
            raised = standing_base_cm(member, tall) > 0.0
            assert raised is is_bed_type(member), member.name
        # the one plant parent that holds no soil: climbers root in the ground
        assert is_plant_parent_type(ObjectType.TRELLIS)
        assert standing_base_cm(ObjectType.TRELLIS, tall) == 0.0


class TestLiesOnGround:
    """Manual pass of PR #584: a garden surface with no height lies UNDER the 2D sun
    study's overlays (``canvas_scene.GROUND_Z_RANGE``)."""

    def test_the_surface_names_are_real_types_without_a_default_height(self) -> None:
        from open_garden_planner.core.object_height import GROUND_SURFACE_TYPE_NAMES
        from open_garden_planner.core.object_types import ObjectType

        enum_names = {member.name for member in ObjectType}
        assert GROUND_SURFACE_TYPE_NAMES.issubset(enum_names)
        for name in GROUND_SURFACE_TYPE_NAMES:
            assert effective_height_cm(name, {}) is None, name

    def test_a_surface_without_a_height_lies_on_the_ground(self) -> None:
        from open_garden_planner.core.object_height import GROUND_SURFACE_TYPE_NAMES, lies_on_ground

        for name in GROUND_SURFACE_TYPE_NAMES:
            assert lies_on_ground(name, {}), name
            assert lies_on_ground(name, None), name
            assert not lies_on_ground(name, {METADATA_KEY: 30.0}), f"{name} with a height is a solid"

    @pytest.mark.parametrize("name", ["TOOL_SHED", "RAISED_BED", "TREE", "PERENNIAL", "SHRUB",
                                      "COLD_FRAME", "RAIN_BARREL", "PLANTER_POT", "PARASOL",
                                      "GENERIC_TEXT", "GENERIC_CALLOUT", "GARDEN_JOURNAL_PIN", "ROOF_RIDGE"])
    def test_solids_standing_objects_shapes_and_notes_do_not(self, name: str) -> None:
        """Senior review of the manual pass: a cold frame without a height sank under
        the raised bed it stood on — standing objects stay put."""
        from open_garden_planner.core.object_height import lies_on_ground

        assert not lies_on_ground(name, {})

    def test_no_type_does_not(self) -> None:
        from open_garden_planner.core.object_height import lies_on_ground

        assert not lies_on_ground(None, None)


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


class TestOneResolver:
    """#581: the three public entry points are projections of one ladder."""

    @pytest.mark.parametrize(
        ("object_type", "metadata", "at_date"),
        [
            ("CONTAINER", {METADATA_KEY: 90.0, "container_height_cm": 30.0}, None),
            ("CONTAINER", {"container_height_cm": 45.0}, None),
            ("TREE", {"plant_species": {"max_height_cm": 180.0}}, None),
            ("TREE", {"plant_instance": {"current_height_cm": 200.0}}, date(2031, 1, 1)),
            (
                "TREE",
                {
                    "plant_species": {"max_height_cm": 500.0},
                    "plant_instance": {
                        "planting_date": "2026-01-01",
                        "current_height_cm": 100.0,
                    },
                },
                date(2031, 1, 1),
            ),
            ("FENCE", {}, None),
            ("GENERIC_RECTANGLE", {}, None),
        ],
    )
    def test_the_public_entry_points_are_projections(
        self, object_type: str, metadata: dict, at_date: date | None,
    ) -> None:
        height, source = resolve_height(object_type, metadata, at_date)
        assert effective_height_cm(object_type, metadata, at_date) == height
        assert height_source_at(object_type, metadata, at_date) == source
        assert height_source(object_type, metadata) == resolve_height(object_type, metadata)[1]

    def test_the_growth_branch_reports_grown(self) -> None:
        metadata = {
            "plant_species": {"max_height_cm": 500.0},
            "plant_instance": {
                "planting_date": "2026-01-01",
                "current_height_cm": 100.0,
            },
        }
        height, source = resolve_height("TREE", metadata, date(2031, 1, 1))
        assert source == SOURCE_GROWN
        assert height == pytest.approx(300.0, abs=2.0)
        # Without a date the same metadata is the static CURRENT branch.
        assert height_source("TREE", metadata) == SOURCE_CURRENT


#: The kinds with no height of their own: the ground surfaces, the roof ridge (a line of
#: its house), generic shapes, annotations, and plants (one without species data gets
#: an illustrative 3D estimate, #557). Every other kind stands up and has a default.
_NO_DEFAULT_KINDS = GROUND_SURFACE_TYPE_NAMES | {
    "ROOF_RIDGE", "GENERIC_TEXT", "GENERIC_CALLOUT", "GARDEN_JOURNAL_PIN",
    "TREE", "SHRUB", "PERENNIAL",
}

#: The kinds that had no height until L4's second owner pass (ADR-065), at the values
#: the 3D view had shown them at.
_FORMERLY_HEIGHT_LESS = {
    "PARASOL": 250.0, "FIRE_PIT": 30.0, "PLANTER_POT": 50.0, "COLD_FRAME": 45.0,
    "RAIN_BARREL": 100.0, "WATER_TAP": 80.0, "SWING": 220.0, "HAMMOCK": 110.0,
    "PERGOLA": 250.0,
}


class TestEveryStandingObjectHasAHeight:
    """L4's second owner pass (ADR-065): "Doesn't make sense for me e.g. that a parasol
    doesn't have a height, while a trampoline has it." Every object that stands up has
    a default height: the Height field shows it, and it casts in 2D and 3D."""

    def test_every_standing_object_kind_has_a_default_height(self) -> None:
        from open_garden_planner.core.object_types import ObjectType

        names = {member.name for member in ObjectType}
        assert names >= _NO_DEFAULT_KINDS
        for name in sorted(names - _NO_DEFAULT_KINDS):
            assert effective_height_cm(name, None) is not None, name
            assert has_height_semantics(name, None), name
        for name in sorted(_NO_DEFAULT_KINDS):
            assert effective_height_cm(name, None) is None, name

    @pytest.mark.parametrize(("name", "height"), sorted(_FORMERLY_HEIGHT_LESS.items()))
    def test_the_formerly_height_less_kinds_have_their_default(
            self, name: str, height: float) -> None:
        assert DEFAULT_HEIGHTS_CM[name] == height
        assert resolve_height(name, None) == (height, SOURCE_DEFAULT)
        assert effective_height_cm(name, {METADATA_KEY: 210.0}) == 210.0
