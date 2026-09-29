"""Tests for the Companion panel's compatible-set action (US-D3.1, #319).

These pin the three defects the live manual pass found, none of which the
pre-existing suite could see because it never exercised the panel path:

* ``_get_current_bed_id`` / ``_get_bed_plants`` read ``parent_bed_id`` from
  ``item.metadata``, but it is a ``GardenItem`` PROPERTY — both returned None
  and the action silently did nothing.
* the action passed the whole bed as ``must_include``, which returns nothing
  unless the bed already IS a complete clique (P0-2).
* ``size=3`` returned an empty dialog for a two-plant bed.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
)
from open_garden_planner.services.companion_sets import find_sets_for_bed
from open_garden_planner.ui.panels.companion_panel import (
    CompatibleSetDialog,
    CompanionPanel,
)


@pytest.fixture()
def service() -> CompanionPlantingService:
    return CompanionPlantingService()


class _FakeItem:
    """Minimal stand-in for a canvas plant item.

    ``parent_bed_id`` is a real PROPERTY here, exactly as on ``GardenItem``.
    The original bug was reading ``metadata["parent_bed_id"]`` instead, so
    this fake deliberately keeps ``metadata`` free of that key — a plain
    attribute would have hidden the bug rather than reproduced it.
    """

    def __init__(self, bed_id: str | None, species: str) -> None:
        self._parent_bed_id = bed_id
        self.plant_species = species
        self.metadata: dict[str, Any] = {"plant_species": {"common_name": species}}

    @property
    def parent_bed_id(self) -> str | None:
        return self._parent_bed_id


class _FakeScene:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def items(self) -> list[Any]:
        return list(self._items)


def _panel(qtbot: Any, service: CompanionPlantingService, items: list[Any]) -> CompanionPanel:
    panel = CompanionPanel(service)
    qtbot.addWidget(panel)
    panel.set_canvas_scene(_FakeScene(items))
    return panel


class TestParentBedLookup:
    """The bed-membership lookups must read the property, not the metadata dict."""

    def test_get_current_bed_id_reads_property(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        item = _FakeItem("bed-1", "corn")
        panel = _panel(qtbot, service, [item])
        panel._current_item = item
        assert panel._get_current_bed_id() == "bed-1"

    def test_get_current_bed_id_none_when_unlinked(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        item = _FakeItem(None, "corn")
        panel = _panel(qtbot, service, [item])
        panel._current_item = item
        assert panel._get_current_bed_id() is None

    def test_get_bed_plants_reads_property(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        items = [
            _FakeItem("bed-1", "corn"),
            _FakeItem("bed-1", "Bean"),
            _FakeItem("bed-2", "squash"),
        ]
        panel = _panel(qtbot, service, items)
        found = panel._get_bed_plants("bed-1")
        assert sorted(found) == ["bean", "corn"]

    def test_get_bed_plants_empty_for_other_bed(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        panel = _panel(qtbot, service, [_FakeItem("bed-2", "corn")])
        assert panel._get_bed_plants("bed-1") == []


class TestFindSetsForBed:
    """``find_sets_for_bed`` must not reproduce the must_include dead end."""

    def test_returns_sets_for_two_plant_bed(self, service: CompanionPlantingService) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        assert result["sets"], "a corn+bean bed must yield at least one set"
        assert sorted(result["bed_plants"]) == ["bean", "corn"]
        assert result["conflicts"] == []

    def test_sets_cover_the_bed_plants(
        self, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        top = result["sets"][0]
        assert set(top["covers"]) == {"corn", "bean"}
        assert top["covers_all"] is True

    def test_conflicting_bed_reports_the_conflict(
        self, service: CompanionPlantingService
    ) -> None:
        # corn and tomato are antagonistic in the bundled data.
        result = find_sets_for_bed(service, ["corn", "tomato"], size=3)
        assert result["conflicts"], "an antagonistic bed pair must be reported"
        for conflict in result["conflicts"]:
            assert conflict["antagonistic_to"], "a conflict must name what it clashes with"

    def test_non_antagonistic_pair_is_not_a_conflict(
        self, service: CompanionPlantingService
    ) -> None:
        """P1-3: absent from a 3-set is NOT a clash.

        Regression: conflicts used to include any bed plant missing from every
        set, which reported "mint has no compatible set with cabbage" when the
        bundled data says the pair is beneficial — it simply has no third
        mutual partner at size 3.
        """
        result = find_sets_for_bed(service, ["cabbage", "mint"], size=3)
        assert result["conflicts"] == [], (
            "a beneficial pair with no 3-clique must not be reported as a conflict"
        )
        # The step-down finds the 2-clique, so both plants are covered and
        # there is nothing left to report as uncovered either.
        assert result["searched_size"] == 2
        assert result["uncovered"] == []

    def test_search_steps_down_when_no_set_of_requested_size(
        self, service: CompanionPlantingService
    ) -> None:
        """A real 2-clique pair must not dead-end at size 3 (P1-3)."""
        result = find_sets_for_bed(service, ["cabbage", "mint"], size=3)
        assert result["searched_size"] == 2
        assert result["sets"], "stepping down must find the 2-clique"

    def test_step_down_not_used_when_requested_size_available(
        self, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        assert result["searched_size"] == 3

    def test_conflicting_bed_still_returns_something_useful(
        self, service: CompanionPlantingService
    ) -> None:
        """A bed with a bad pair must still get options, not a dead end."""
        result = find_sets_for_bed(service, ["corn", "tomato"], size=3)
        assert result["sets"], "sets covering the compatible subset must be offered"
        assert any(s["covers"] for s in result["sets"])

    def test_empty_bed(self, service: CompanionPlantingService) -> None:
        result = find_sets_for_bed(service, [], size=3)
        assert result["bed_plants"] == []
        assert result["conflicts"] == []

    def test_rejects_out_of_range_size(
        self, service: CompanionPlantingService
    ) -> None:
        with pytest.raises(ValueError, match="size must be 2"):
            find_sets_for_bed(service, ["corn"], size=1)
        with pytest.raises(ValueError, match="size must be 2"):
            find_sets_for_bed(service, ["corn"], size=6)


class TestCompatibleSetDialog:
    """The dialog must show coverage and name conflicts, not just a list."""

    def test_shows_every_set(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        dialog = CompatibleSetDialog(result["sets"], result["bed_plants"], [], [], None)
        qtbot.addWidget(dialog)
        assert dialog._list.count() == len(result["sets"])

    def test_first_row_is_prefilled(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        dialog = CompatibleSetDialog(result["sets"], result["bed_plants"], [], [], None)
        qtbot.addWidget(dialog)
        assert dialog._list.currentRow() == 0

    def test_conflicts_are_rendered(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "tomato"], size=3)
        dialog = CompatibleSetDialog(
            result["sets"], result["bed_plants"], result["conflicts"], [], None
        )
        qtbot.addWidget(dialog)
        texts = [w.text() for w in dialog.findChildren(object) if hasattr(w, "text")]
        for conflict in result["conflicts"]:
            assert any(conflict["species_key"] in t for t in texts), (
                f"conflict {conflict['species_key']} not surfaced in the dialog"
            )

    def test_uncovered_is_not_worded_as_a_clash(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        """P1-3: an uncovered plant must not be announced as a clash.

        Uses a bed that genuinely yields ``uncovered``. The earlier version used
        cabbage+mint, which the step-down resolves to a 2-clique — so
        ``uncovered`` was EMPTY and the dialog rendered no clash labels for any
        reason, making the assertion vacuous. It also asserts the neutral
        wording is PRESENT, so this fails both when a clash reappears and when
        the neutral line is lost.
        """
        result = find_sets_for_bed(service, ["onion", "beet"], size=3)
        assert result["uncovered"], (
            "fixture no longer produces uncovered, so this test is vacuous — "
            "pick a bed that does"
        )
        assert result["conflicts"] == [], "onion/beet are not bundled antagonists"

        dialog = CompatibleSetDialog(
            result["sets"],
            result["bed_plants"],
            result["conflicts"],
            result["uncovered"],
            None,
        )
        qtbot.addWidget(dialog)
        texts = [w.text() for w in dialog.findChildren(object) if hasattr(w, "text")]

        for text in texts:
            assert "clashes with" not in text, (
                f"an uncovered plant was announced as a clash: {text}"
            )
        assert any("not part of any of these sets" in text for text in texts), (
            f"the neutral uncovered line is missing: {texts}"
        )

    def test_get_selected_set_returns_members(
        self, qtbot: Any, service: CompanionPlantingService
    ) -> None:
        result = find_sets_for_bed(service, ["corn", "bean"], size=3)
        dialog = CompatibleSetDialog(result["sets"], result["bed_plants"], [], [], None)
        qtbot.addWidget(dialog)
        dialog._on_accept()
        assert dialog.get_selected_set() == result["sets"][0]["members"]
