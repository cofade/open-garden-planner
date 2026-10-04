"""Regression test for the Agent API ``check_placement`` bed resolution (US-D3.1).

P1-1 of the PR #369 review: ``_do_agent_check_placement`` originally walked
``bed.childItems()``, which is ALWAYS empty in this codebase because bed
membership is the ``parent_bed_id`` PROPERTY, not Qt item parenting. The
symptom was a fabricated clean result — ``overall="neutral"`` for a bed whose
real answer was ``"critical"`` — which is strictly worse than not resolving the
bed at all, and no test existed because the integration test stubbed the
provider with a lambda that bypassed the main-thread body entirely.

These tests drive the REAL main-thread body against a real CanvasScene.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


@pytest.fixture()
def app(qtbot: Any, monkeypatch: Any) -> Any:
    get_settings().show_welcome_on_startup = False
    monkeypatch.setattr(
        GardenPlannerApp, "_confirm_discard_changes", lambda _self: True, raising=False
    )
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    yield win
    win._stop_agent_api()


def _bed_with_plants(
    scene: CanvasScene, species: list[str], bed_type: ObjectType = ObjectType.RAISED_BED
) -> RectangleItem:
    """A bed with the given species linked via the parent_bed_id PROPERTY."""
    bed = RectangleItem(0, 0, 300, 200, object_type=bed_type)
    scene.addItem(bed)
    for index, name in enumerate(species):
        plant = CircleItem(
            50 + index * 60, 100, 20, object_type=ObjectType.PERENNIAL
        )
        plant.plant_species = name
        plant.parent_bed_id = bed.item_id
        scene.addItem(plant)
    return bed


class TestCheckPlacementResolvesTheBed:
    def test_finds_plants_via_parent_bed_id_property(
        self, app: Any, qtbot: Any
    ) -> None:
        """The bed's real plants must be discovered without being supplied."""
        scene = CanvasScene()
        # bean<->potato is beneficial in the bundled data, so querying "bean"
        # against this bed must surface "potato" as a companion.
        bed = _bed_with_plants(scene, ["bean", "potato"])
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("bean", bed.item_id_str)

        assert result["companions_present"] == ["potato"]
        assert result["antagonists_present"] == []
        assert result["overall"] == "good"

    def test_reports_critical_not_neutral_for_a_real_antagonist(
        self, app: Any, qtbot: Any
    ) -> None:
        """P1-1 regression: this used to answer 'neutral' (a clean bill of health).

        corn is bundled-data-antagonistic to tomato, so a tomato going into a
        corn bed must be 'critical'. The childItems() version reported
        'neutral' because it saw an empty bed.
        """
        scene = CanvasScene()
        bed = _bed_with_plants(scene, ["corn"])
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", bed.item_id_str)

        assert result["antagonists_present"] == ["corn"]
        assert result["overall"] == "critical", (
            "an unresolved bed must not fabricate a clean result"
        )

    def test_unknown_bed_reports_unknown_bed(self, app: Any, qtbot: Any) -> None:
        scene = CanvasScene()
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement(
            "tomato", "00000000-0000-0000-0000-000000000000"
        )

        assert result["overall"] == "unknown_bed"

    def test_malformed_bed_id_reports_unknown_bed(
        self, app: Any, qtbot: Any
    ) -> None:
        scene = CanvasScene()
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", "not-a-uuid")
        assert result["overall"] == "unknown_bed"

    def test_supplying_bed_plants_does_not_bypass_existence_check(
        self, app: Any, qtbot: Any
    ) -> None:
        """P1-1 regression: bed_exists used to be resolved only when
        bed_plants was omitted, so a caller passing them got 'good' for a bed
        that does not exist."""
        scene = CanvasScene()
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement(
            "potato", "00000000-0000-0000-0000-000000000000", ["bean"]
        )
        assert result["overall"] == "unknown_bed"

    def test_explicit_empty_list_on_a_real_bed_is_neutral(
        self, app: Any, qtbot: Any
    ) -> None:
        """An explicitly-empty bed_plants on a REAL bed is 'neutral', not
        'unknown' — the caller stated the contents, we did not fail to read
        them (contradiction the review flagged against the schema docstring)."""
        scene = CanvasScene()
        bed = _bed_with_plants(scene, ["corn"])
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", bed.item_id_str, [])
        assert result["overall"] == "neutral"

    def test_metadata_only_plant_is_found(self, app: Any, qtbot: Any) -> None:
        """P2-6: pin the metadata-only branch — the state SetSpeciesCommand leaves.

        A plant assigned by species search or by the agent's set_species tool
        has ``plant_species == ""`` and its species ONLY in
        ``metadata["plant_species"]``. That branch is the whole point of the
        P1-2 fix, and neither fake modelled it, so the divergence fixed in
        P2-1 (attribute-first vs metadata-first) was masked on both sides.
        """
        scene = CanvasScene()
        bed = RectangleItem(0, 0, 300, 200, object_type=ObjectType.RAISED_BED)
        scene.addItem(bed)
        plant = CircleItem(100, 100, 20, object_type=ObjectType.PERENNIAL)
        # The real SetSpeciesCommand state: empty attribute, metadata only.
        # `metadata` is a read-only property, so mutate the dict in place —
        # which is exactly what the command does.
        plant.plant_species = ""
        plant.metadata["plant_species"] = {
            "common_name": "corn",
            "scientific_name": "Zea mays",
        }
        plant.parent_bed_id = bed.item_id
        scene.addItem(plant)
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", bed.item_id_str)
        assert result["antagonists_present"] == ["corn"], (
            "a metadata-only plant was not found in its bed"
        )
        assert result["overall"] == "critical"

    def test_non_bed_object_reports_unknown_bed(self, app: Any, qtbot: Any) -> None:
        """P1-1: a resolvable NON-bed id must not report a clean 'neutral'.

        Existence is not enough — a plant's own id also resolves. Reporting
        "neutral" says "I inspected this bed's plants and none relate" about an
        object that is not a bed, which is the fabrication ADR-045's honesty
        invariant forbids and which the published schema explicitly rules out
        ("'unknown_bed' if bed_id does not resolve to a real bed").
        """
        scene = CanvasScene()
        plant = CircleItem(100, 100, 20, object_type=ObjectType.PERENNIAL)
        plant.plant_species = "corn"
        scene.addItem(plant)
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", plant.item_id_str)
        assert result["overall"] == "unknown_bed", (
            "a plant id must not be reported as an inspected empty bed"
        )

    def test_real_empty_bed_is_neutral(self, app: Any, qtbot: Any) -> None:
        scene = CanvasScene()
        bed = RectangleItem(0, 0, 300, 200, object_type=ObjectType.RAISED_BED)
        scene.addItem(bed)
        app.canvas_scene = scene
        app.canvas_view = type("V", (), {"command_manager": None, "scene": scene})()

        result = app._do_agent_check_placement("tomato", bed.item_id_str)
        assert result["overall"] == "neutral"


class TestSuggestCompanionsLanguage:
    """Issue #410: the companion display name follows the UI language."""

    def test_name_follows_the_ui_language(self, app: Any) -> None:
        get_settings().language = "en"
        english = app._agent_suggest_companions("tomato")
        get_settings().language = "de"
        try:
            german = app._agent_suggest_companions("tomato")
        finally:
            get_settings().language = "en"

        assert english and german
        # The machine key never moves with the language.
        assert [s["species_key"] for s in english] == [
            s["species_key"] for s in german
        ]
        # The display name does.
        assert any(
            de["name"] != en["name"]
            for de, en in zip(german, english, strict=True)
        ), "the provider did not pass the active language through"
