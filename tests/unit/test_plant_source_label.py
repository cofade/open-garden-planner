"""Unit tests for `plant_source_label()` and the `PlantSearchDialog`
enrichment allowlist it's paired with (issue #297, manual-test follow-up).

Both were introduced to fix two sibling bugs found only by real manual
testing: an untranslated "Custom"/"Bundled" string reaching the German UI
(`plant_source_label()`'s four branches), and a spurious "Limited Plant
Data" warning for a plant whose `data_source` is empty/legacy
(`PlantSearchDialog._ONLINE_PROVIDERS`, exercised end-to-end in
`tests/integration/test_plant_search_enrichment.py`).
"""

from __future__ import annotations

from open_garden_planner.services.plant_api import PlantAPIManager
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog
from open_garden_planner.ui.plant_species_assignment import plant_source_label


class TestPlantSourceLabel:
    def test_empty_string_is_unknown_source(self) -> None:
        assert plant_source_label("") == "Unknown source"

    def test_none_is_unknown_source(self) -> None:
        # PlantSpeciesData.from_dict()'s `data.get("data_source", "")` returns
        # None, not "", for a present-but-null JSON value (the #296 trap).
        assert plant_source_label(None) == "Unknown source"  # type: ignore[arg-type]

    def test_custom_is_translated_not_title_cased(self) -> None:
        # Would render the untranslated Python-native "Custom" if this regressed
        # to a bare `.title()` call -- the exact bug this helper exists to fix.
        assert plant_source_label("custom") == "Custom Plant"

    def test_bundled_is_translated_not_title_cased(self) -> None:
        assert plant_source_label("bundled") == "Bundled"

    def test_provider_names_are_title_cased_not_translated(self) -> None:
        assert plant_source_label("trefle") == "Trefle"
        assert plant_source_label("perenual") == "Perenual"
        assert plant_source_label("permapeople") == "Permapeople"


class TestOnlineProvidersMatchesManagerClients:
    def test_online_providers_allowlist_matches_actual_manager_clients(self) -> None:
        """Pins the coupling a senior-review round flagged: `_ONLINE_PROVIDERS`
        is a hardcoded literal duplicating `PlantAPIManager._clients`' names.
        A future provider added to the manager without updating this set
        would silently never get enriched (no error, no test failure) --
        this test is what would catch that.
        """
        manager = PlantAPIManager()  # no credentials needed -- only .name is read
        manager_providers = {client.name.lower() for client in manager._clients}
        assert manager_providers == PlantSearchDialog._ONLINE_PROVIDERS
