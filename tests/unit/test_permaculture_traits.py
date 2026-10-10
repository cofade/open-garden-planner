"""Species-trait contract, provider fixture and catalog evidence."""

from dataclasses import fields

import pytest

from open_garden_planner.models.plant_data import PermacultureLayer, PlantFunction, PlantSpeciesData
from open_garden_planner.services.bundled_species_db import get_species_db, lookup_species
from open_garden_planner.services.permaculture import (
    PERMAPEOPLE_LAYERS,
    matches_traits,
    permapeople_traits,
)


def test_roundtrip_unknowns_and_deduplication():
    species = PlantSpeciesData.from_dict({"scientific_name": "X", "common_name": "X",
        "permaculture_layer": "future", "functions": ["ground_cover", "future", "nitrogen_fixer", "ground_cover"]})
    assert species.permaculture_layer is PermacultureLayer.UNKNOWN
    assert species.functions == [PlantFunction.NITROGEN_FIXER, PlantFunction.GROUND_COVER]
    assert species.raw_data["unrecognized_permaculture_layer"] == "future"
    assert species.raw_data["unrecognized_functions"] == ["future"]
    assert PlantSpeciesData.from_dict(species.to_dict()) == species
    assert {f.name for f in fields(species)} == set(species.to_dict())
    a, b = PlantSpeciesData("A", "A"), PlantSpeciesData("B", "B")
    a.functions.append(PlantFunction.DYE)
    assert b.functions == []


def test_all_bundled_traits_curated():
    records = get_species_db()
    assert len(records) == 118
    for record in records.values():
        assert PermacultureLayer(record["permaculture_layer"]) != PermacultureLayer.UNKNOWN
        assert all(PlantFunction(f) for f in record["functions"])


@pytest.mark.parametrize("token,layer", PERMAPEOPLE_LAYERS.items())
def test_provider_layers(token, layer):
    assert permapeople_traits({"data": [{"key": "Layer", "value": f"  {token.upper()} "}]}) == (layer, [])


def test_apple_recorded_acceptance_fixture():
    response = {"scientific_name": "Malus domestica", "name": "Apple", "data": [
        {"key": "Layer", "value": "Trees"},
        {"key": "Uses", "value": "Utility, Animal feed, Attracts insects, Hedgerow"},
        {"key": "Life cycle", "value": "Perennial"}]}
    from open_garden_planner.services.plant_api.permapeople_client import PermapeopleClient

    species = PermapeopleClient()._parse_species(response)
    assert species.permaculture_layer is PermacultureLayer.SUB_CANOPY
    assert set(species.functions) == {PlantFunction.ANIMAL_FEED, PlantFunction.POLLINATOR_ATTRACTOR, PlantFunction.HEDGEROW}
    assert species.raw_data == response
    assert permapeople_traits({"data": [{"key": "Uses", "value": [None, "not animal feed", "Utility"]}]})[1] == []


def test_filter_combination_and_alias():
    strawberry = lookup_species("strawberry")
    assert matches_traits(strawberry, "Fragaria", layers={"root", "ground_cover"},
                          functions={"pollinator_attractor", "ground_cover"})
    assert not matches_traits(strawberry, functions={"nitrogen_fixer"})
    assert matches_traits({}, layers={"unknown"})
    assert not matches_traits({}, layers={"vine"})
