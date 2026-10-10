"""Offline-first search, explicit online requests and stale/closed-dialog safety."""

import threading
from concurrent.futures import Future
from unittest.mock import MagicMock

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.plant_api.manager import PlantAPIManager
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog


def test_offline_first_explicit_online_and_filtered_fallback(qtbot, monkeypatch):
    main_thread = threading.get_ident()
    provider_thread = []
    manager = PlantAPIManager(trefle_api_token="fake")
    def search(query, limit):
        provider_thread.append(threading.get_ident())
        return [PlantSpeciesData("Future species", "Future", data_source="trefle", source_id="123")]
    manager.search = MagicMock(side_effect=search)
    dialog = PlantSearchDialog(manager)
    qtbot.addWidget(dialog)
    manager.search.assert_not_called()
    dialog.search_input.setText("apple")
    dialog._perform_search()
    assert dialog.results_list.count() == 1
    manager.search.assert_not_called()
    dialog._perform_search(online=True)
    qtbot.waitUntil(lambda: not dialog._requests)
    assert dialog.results_list.item(0).data(256).scientific_name == "Future species"
    assert all(identity != main_thread for identity in provider_thread)
    dialog.trait_filters.function_buttons["nitrogen_fixer"].setChecked(True)
    qtbot.waitUntil(lambda: not dialog._requests)
    assert manager.search.call_count == 2
    assert dialog.results_list.count() == 0
    dialog.reject()


def test_stale_and_closed_responses_cannot_replace_results(qtbot):
    dialog = PlantSearchDialog(PlantAPIManager())
    qtbot.addWidget(dialog)
    future = Future()
    dialog._requests.append((dialog._generation, future))
    dialog.search_input.setText("strawberry")
    dialog._perform_search()
    future.set_result([PlantSpeciesData("Obsolete", "Obsolete")])
    dialog._poll_results()
    assert dialog.results_list.count() == 1
    assert "Strawberry" in dialog.results_list.item(0).text()
    dialog.reject()
    assert not dialog._poll_timer.isActive()


def test_sparse_trait_merge_both_directions():
    from open_garden_planner.models.plant_data import PermacultureLayer, PlantFunction

    rich = PlantSpeciesData("A", "A", permaculture_layer=PermacultureLayer.SUB_CANOPY,
                            functions=[PlantFunction.ANIMAL_FEED])
    sparse = PlantSpeciesData("A", "A")
    for search, detail in ((rich, sparse), (sparse, rich)):
        result = PlantSearchDialog._merge_detail_into_search_result(search, detail)
        assert result.permaculture_layer == rich.permaculture_layer and result.functions == rich.functions
