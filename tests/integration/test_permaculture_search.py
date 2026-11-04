"""Offline-first search, explicit online requests and stale/closed-dialog safety."""

import threading
from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.plant_api.manager import PlantAPIManager
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog


@pytest.fixture(autouse=True)
def _isolate_custom_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """These bundled-catalog scenarios must not inherit another test's custom plants."""
    library = MagicMock()
    library.get_all_plants.return_value = []
    library.search_plants.return_value = []
    monkeypatch.setattr(
        "open_garden_planner.services.plant_library.get_plant_library", lambda: library)


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


def test_selection_change_invalidates_pending_confirmation(qtbot):
    dialog = PlantSearchDialog(PlantAPIManager())
    qtbot.addWidget(dialog)
    a = PlantSpeciesData("A", "A", data_source="trefle", source_id="a")
    b = PlantSpeciesData("B", "B", data_source="trefle", source_id="b")
    dialog._show_results([a, b])
    dialog.results_list.setCurrentRow(0)
    future = Future()
    future.set_running_or_notify_cancel()
    dialog._detail_request = (dialog._generation, a, future)
    dialog.results_list.setCurrentRow(1)
    future.set_result(a)
    dialog._poll_results()
    assert dialog._selected_plant is b and dialog.result() != dialog.DialogCode.Accepted
    dialog.reject()


def test_global_trait_only_results_and_empty_filter_controls(qtbot):
    from open_garden_planner.core.object_types import is_plant_type
    from open_garden_planner.ui.widgets.gallery_data import build_toolbar_categories
    from open_garden_planner.ui.widgets.global_search import GlobalSearchField

    field = GlobalSearchField(build_toolbar_categories())
    qtbot.addWidget(field)
    filters = field._popup.trait_filters
    filters.function_buttons["nitrogen_fixer"].setChecked(True)
    rows = field._popup._list
    assert rows.count() > 0
    assert all(is_plant_type(rows.item(index).data(256).object_type) for index in range(rows.count()))
    filters.function_buttons["dye"].setChecked(True)
    assert rows.count() == 0 and field._popup.isVisible()
    field._popup.hide()
