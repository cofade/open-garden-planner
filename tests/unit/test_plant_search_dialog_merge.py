"""Unit tests for PlantSearchDialog._merge_detail_into_search_result() (#297
senior-review round 4).

Round 3 fixed a wholesale-swap data-loss bug by hand-listing six "identity"
fields (common_name/scientific_name/family/genus/image_url/thumbnail_url) to
protect. Round 4 pointed out that was the same bug class relocated to every
OTHER field: if some future provider (or a Perenual detail response, whose
search results already carry sun/water/cycle directly -- unlike Trefle) ever
returns a sparser detail record for an enrichment field the search result
had, the hand-picked list wouldn't protect it. The merge is now generic: any
field at its dataclass default in `detail` defers to `plant`'s value. These
tests exercise the classmethod directly -- pure dataclass logic, no Qt
needed -- to prove the generalization holds beyond the six fields the
integration test (`tests/integration/test_plant_search_enrichment.py`)
already covers end-to-end through the real dialog.
"""

from __future__ import annotations

from open_garden_planner.models.plant_data import PlantSpeciesData, SunRequirement
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog

_merge = PlantSearchDialog._merge_detail_into_search_result


class TestGenericFieldMerge:
    def test_non_identity_field_regression_is_still_protected(self) -> None:
        """The scenario round 3's hand-picked list couldn't have caught:
        search already had a real value for an enrichment field (plausible
        for Perenual, whose search results carry sun/water/cycle directly),
        but the detail fetch regresses to the field's default. The search
        result's value must survive.
        """
        plant = PlantSpeciesData(
            scientific_name="Helianthus annuus",
            common_name="Sunflower",
            source_id="1",
            data_source="perenual",
            sun_requirement=SunRequirement.FULL_SUN,
            ph_min=6.0,
        )
        detail = PlantSpeciesData(
            scientific_name="Helianthus annuus",
            common_name="Sunflower",
            source_id="1",
            data_source="perenual",
            # sun_requirement/ph_min left at their dataclass defaults --
            # simulating a detail response that regressed versus search.
            description="A tall annual flower.",  # detail DOES add this
        )

        merged = _merge(plant, detail)

        assert merged.sun_requirement == SunRequirement.FULL_SUN  # from plant
        assert merged.ph_min == 6.0  # from plant
        assert merged.description == "A tall annual flower."  # from detail

    def test_detail_value_wins_when_it_actually_has_data(self) -> None:
        plant = PlantSpeciesData(
            scientific_name="Daucus carota", common_name="Carrot", source_id="1"
        )
        detail = PlantSpeciesData(
            scientific_name="Daucus carota",
            common_name="Carrot",
            source_id="1",
            sun_requirement=SunRequirement.FULL_SUN,
            ph_min=6.5,
        )

        merged = _merge(plant, detail)

        assert merged.sun_requirement == SunRequirement.FULL_SUN
        assert merged.ph_min == 6.5

    def test_source_id_data_source_and_raw_data_always_come_from_detail(self) -> None:
        """These three are excluded from the emptiness comparison entirely --
        source_id/data_source describe which record this is (already
        validated equal before merge is called), and detail's raw_data is
        the richer payload even when it happens to be `{}` for some field.
        """
        plant = PlantSpeciesData(
            scientific_name="Testus",
            common_name="Test",
            source_id="1",
            data_source="trefle",
            raw_data={"from": "search"},
        )
        detail = PlantSpeciesData(
            scientific_name="Testus",
            common_name="Test",
            source_id="1",
            data_source="trefle",
            raw_data={},  # empty, but must NOT fall back to plant's raw_data
        )

        merged = _merge(plant, detail)

        assert merged.raw_data == {}
        assert merged.source_id == "1"
        assert merged.data_source == "trefle"

    def test_empty_list_field_defers_to_plants_populated_list(self) -> None:
        """default_factory fields (list/dict) need the factory called for
        comparison, not a static default -- this is the case that breaks a
        naive `field.default` check.
        """
        plant = PlantSpeciesData(
            scientific_name="Testus",
            common_name="Test",
            source_id="1",
            edible=True,
            edible_parts=["leaves", "root"],
        )
        detail = PlantSpeciesData(
            scientific_name="Testus", common_name="Test", source_id="1", edible_parts=[]
        )

        merged = _merge(plant, detail)

        assert merged.edible_parts == ["leaves", "root"]
