"""Tests for the bundled species DB (issue #170).

Covers the new species-record API on top of plant_species.json. The legacy
calendar-overlay API (``get_calendar_entry``, ``merge_calendar_data``)
keeps living in ``test_plant_calendar_data.py``.
"""

import pytest

from open_garden_planner.services.bundled_species_db import (
    get_species_by_common_name,
    get_species_db,
    get_species_entry,
    lookup_species,
    populate_item_species_metadata,
)


class TestBundledSpeciesDb:
    """plant_species.json loads cleanly and meets the AC scope."""

    def test_db_has_at_least_50_species(self) -> None:
        assert len(get_species_db()) >= 50

    def test_tomato_has_full_critical_record(self) -> None:
        # ph_min/max + nutrient_demand + n/p/k_demand are the fields that
        # gate US-12.10d soil-mismatch warnings.
        entry = get_species_entry("Solanum lycopersicum")
        assert entry is not None
        assert entry["ph_min"] == pytest.approx(6.0)
        assert entry["ph_max"] == pytest.approx(6.8)
        assert entry["nutrient_demand"] == "heavy"
        assert entry["n_demand"] == "high"
        assert entry["p_demand"] == "medium"
        assert entry["k_demand"] == "high"

    def test_every_record_has_ph_and_npk(self) -> None:
        # Acceptance criteria #1: every entry must have these populated, so
        # the soil-mismatch warning fires for any bundled plant.
        missing: list[str] = []
        for sci_name, entry in get_species_db().items():
            for key in ("ph_min", "ph_max", "nutrient_demand", "n_demand",
                        "p_demand", "k_demand"):
                if entry.get(key) is None:
                    missing.append(f"{sci_name}:{key}")
        assert not missing, f"Bundled records missing critical fields: {missing[:10]}"

    def test_data_source_is_bundled(self) -> None:
        # Provenance: every record should be marked as bundled so the UI
        # can distinguish curated vs. user/api data.
        for sci_name, entry in get_species_db().items():
            assert entry.get("data_source") == "bundled", (
                f"{sci_name} not marked as bundled: {entry.get('data_source')!r}"
            )

    def test_every_gallery_species_string_resolves(self) -> None:
        """Every species the gallery can drop must hit the bundled DB.

        The gallery passes ``svg_filename.replace("_", " ")`` (lower-cased,
        space-separated) — see [gallery_panel.py](src/open_garden_planner/ui/panels/gallery_panel.py).
        Anything missing here means a user dropping that thumbnail still
        sees "Keine Artdaten" — failing the AC.
        """
        gallery_species_strings = [
            # Trees
            "apple tree", "cherry tree", "pear tree", "plum tree", "peach tree",
            "fig tree", "olive tree", "lemon tree", "orange tree", "walnut tree",
            "oak", "maple", "birch", "willow", "magnolia", "pine", "spruce",
            # Shrubs
            "boxwood", "rhododendron", "blueberry", "raspberry", "blackberry",
            "gooseberry", "currant", "holly", "juniper", "forsythia", "lilac",
            "elderberry", "privet", "viburnum", "barberry", "camellia", "spirea",
            # Flowers & Perennials
            "rose", "lavender", "sunflower", "tulip", "daffodil", "dahlia",
            "peony", "iris", "lily", "marigold", "zinnia", "cosmos", "aster",
            "chrysanthemum", "geranium", "petunia", "pansy", "hydrangea",
            "clematis", "wisteria", "jasmine", "hibiscus", "crocus",
            # Vegetables & Herbs
            "tomato", "pepper", "eggplant", "zucchini", "cucumber", "pumpkin",
            "bean", "pea", "corn", "carrot", "radish", "potato", "onion",
            "garlic", "lettuce", "spinach", "cabbage", "kale", "broccoli",
            "basil", "rosemary", "thyme", "sage", "mint", "parsley", "cilantro",
            "dill", "chives", "oregano",
        ]
        unresolved = [n for n in gallery_species_strings if lookup_species(n) is None]
        assert not unresolved, (
            f"Gallery species not resolvable from bundled DB: {unresolved}"
        )


class TestSpeciesLookup:
    """lookup_species tries scientific name first, then common name."""

    def test_scientific_lookup_case_insensitive(self) -> None:
        a = lookup_species("Solanum lycopersicum")
        b = lookup_species("solanum LYCOPERSICUM")
        c = lookup_species("SOLANUM lycopersicum")
        assert a is not None and a == b == c

    def test_common_name_fallback(self) -> None:
        # Gallery may pass either form; this exercises the second branch.
        record = lookup_species("Tomato")
        assert record is not None
        assert record["scientific_name"] == "Solanum lycopersicum"

    def test_common_name_fallback_case_insensitive(self) -> None:
        assert lookup_species("BASIL") is not None
        assert lookup_species("basil") is not None

    def test_scientific_wins_when_both_could_match(self) -> None:
        # If the user passes a scientific name, we must not silently fall
        # through to a common-name collision (e.g. someone naming a custom
        # cultivar "Solanum lycopersicum").
        record = lookup_species("Solanum lycopersicum")
        assert record is not None
        assert record["common_name"] == "Tomato"

    def test_alias_lookup(self) -> None:
        # Gallery passes "pepper" but record common_name is "Sweet Pepper".
        record = lookup_species("pepper")
        assert record is not None
        assert record["scientific_name"] == "Capsicum annuum"

    def test_alias_pumpkin_resolves_to_winter_squash(self) -> None:
        record = lookup_species("pumpkin")
        assert record is not None
        assert record["scientific_name"] == "Cucurbita maxima"

    def test_unknown_species_returns_none(self) -> None:
        assert lookup_species("Imaginus plantus") is None
        assert lookup_species("Definitely Not A Real Plant") is None

    def test_empty_name_returns_none(self) -> None:
        assert lookup_species("") is None
        assert get_species_entry("") is None
        assert get_species_by_common_name("") is None


class TestPopulateItemSpeciesMetadata:
    """Drop-flow hook used by canvas_view and circle_tool."""

    def _make_item(self) -> object:
        class _Stub:
            def __init__(self) -> None:
                self.metadata: dict = {}

        return _Stub()

    def test_writes_full_record_on_hit(self) -> None:
        item = self._make_item()
        ok = populate_item_species_metadata(item, "Solanum lycopersicum")
        assert ok is True
        species = item.metadata["plant_species"]  # type: ignore[attr-defined]
        # Soil/nutrient fields populated → US-12.10d will fire.
        assert species["ph_min"] == pytest.approx(6.0)
        assert species["nutrient_demand"] == "heavy"
        # Calendar overlay also applied → existing planting-calendar UI works.
        assert species["frost_tolerance"] == "tender"
        assert species["indoor_sow_start"] == -8

    def test_common_name_hit_writes_metadata(self) -> None:
        item = self._make_item()
        ok = populate_item_species_metadata(item, "Tomato")
        assert ok is True
        assert item.metadata["plant_species"]["scientific_name"] == "Solanum lycopersicum"  # type: ignore[attr-defined]

    def test_miss_returns_false_and_does_not_write(self) -> None:
        item = self._make_item()
        ok = populate_item_species_metadata(item, "Imaginus plantus")
        assert ok is False
        assert "plant_species" not in item.metadata  # type: ignore[attr-defined]

    def test_empty_name_returns_false(self) -> None:
        item = self._make_item()
        assert populate_item_species_metadata(item, "") is False
        assert "plant_species" not in item.metadata  # type: ignore[attr-defined]

    def test_item_without_metadata_returns_false(self) -> None:
        class _NoMeta:
            pass

        assert populate_item_species_metadata(_NoMeta(), "Tomato") is False
