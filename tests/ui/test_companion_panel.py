"""UI tests for the CompanionPanel (US-10.3)."""

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.companion_planting_service import CompanionPlantingService
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.panels.companion_panel import CompanionPanel


@pytest.fixture()
def service() -> CompanionPlantingService:
    return CompanionPlantingService()


@pytest.fixture()
def panel(qtbot, service: CompanionPlantingService) -> CompanionPanel:  # noqa: ARG001
    p = CompanionPanel(service)
    qtbot.addWidget(p)
    return p


@pytest.fixture()
def tomato_item(qtbot) -> CircleItem:  # noqa: ARG001
    item = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
    item.plant_species = "tomato"
    return item


@pytest.fixture()
def basil_item(qtbot) -> CircleItem:  # noqa: ARG001
    item = CircleItem(150.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
    item.plant_species = "basil"
    return item


class TestCompanionPanelCreation:
    def test_creates_without_error(self, panel: CompanionPanel) -> None:
        assert panel is not None

    def test_default_state_no_selection(self, panel: CompanionPanel) -> None:
        # Lists should show placeholder when no plant selected
        assert panel._good_list.count() == 1
        assert panel._bad_list.count() == 1
        assert "(none in database)" in panel._good_list.item(0).text()

    def test_plant_label_default(self, panel: CompanionPanel) -> None:
        assert "No plant selected" in panel._plant_label.text()


class TestCompanionPanelUpdateForPlant:
    def test_update_for_none_clears_panel(self, panel: CompanionPanel) -> None:
        panel.update_for_plant(None)
        assert "No plant selected" in panel._plant_label.text()

    def test_update_for_tomato_shows_companions(
        self, panel: CompanionPanel, tomato_item: CircleItem
    ) -> None:
        panel.update_for_plant(tomato_item)
        label_text = panel._plant_label.text()
        # Label shows localized plant name — just verify the "Companions for:" prefix
        assert "companions for:" in label_text.lower()
        # Tomato has known companions in the DB — at least some entries
        total = panel._good_list.count() + panel._bad_list.count()
        assert total > 0

    def test_update_for_tomato_has_basil_as_good(
        self, panel: CompanionPanel, tomato_item: CircleItem
    ) -> None:
        panel.update_for_plant(tomato_item)
        good_names = [
            panel._good_list.item(i).data(0)  # display text
            for i in range(panel._good_list.count())
        ]
        # basil is a well-known tomato companion in the DB
        assert any("basil" in t.lower() for t in good_names)

    def test_update_for_unknown_plant_shows_placeholder(
        self, panel: CompanionPanel
    ) -> None:
        """A plant item with no species name shows placeholder lists."""
        item = CircleItem(0.0, 0.0, 10.0, object_type=ObjectType.TREE)
        item.plant_species = ""
        panel.update_for_plant(item)
        assert "Unknown plant" in panel._plant_label.text()
        assert "(none in database)" in panel._good_list.item(0).text()


class TestCompanionPanelNearbyMarking:
    def test_nearby_plant_marked_with_star(
        self,
        panel: CompanionPanel,
        tomato_item: CircleItem,
        basil_item: CircleItem,
    ) -> None:
        """Basil is 50 cm from tomato (within default 200 cm radius) — marked ★."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(width_cm=5000, height_cm=3000)
        scene.addItem(tomato_item)
        scene.addItem(basil_item)
        panel.set_canvas_scene(scene)
        panel.update_for_plant(tomato_item)

        good_texts = [
            panel._good_list.item(i).text()
            for i in range(panel._good_list.count())
        ]
        assert any("★" in t and "basil" in t.lower() for t in good_texts)

        scene.removeItem(tomato_item)
        scene.removeItem(basil_item)

    def test_distant_plant_not_marked(
        self,
        panel: CompanionPanel,
        tomato_item: CircleItem,
    ) -> None:
        """A plant beyond the radius is not marked ★."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        far_basil = CircleItem(10000.0, 10000.0, 15.0, object_type=ObjectType.SHRUB)
        far_basil.plant_species = "basil"

        scene = CanvasScene(width_cm=50000, height_cm=50000)
        scene.addItem(tomato_item)
        scene.addItem(far_basil)
        panel.set_canvas_scene(scene)
        panel.update_for_plant(tomato_item)

        good_texts = [
            panel._good_list.item(i).text()
            for i in range(panel._good_list.count())
        ]
        # basil should appear but without ★
        basil_entries = [t for t in good_texts if "basil" in t.lower()]
        assert basil_entries  # exists in list
        assert not any("★" in t for t in basil_entries)

        scene.removeItem(tomato_item)
        scene.removeItem(far_basil)


class TestCompanionPanelSignal:
    def test_clicking_nearby_item_emits_signal(
        self,
        panel: CompanionPanel,
        tomato_item: CircleItem,
        basil_item: CircleItem,
    ) -> None:
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(width_cm=5000, height_cm=3000)
        scene.addItem(tomato_item)
        scene.addItem(basil_item)
        panel.set_canvas_scene(scene)
        panel.update_for_plant(tomato_item)

        emitted: list[str] = []
        panel.highlight_species_requested.connect(emitted.append)

        # Find the basil entry and click it
        for i in range(panel._good_list.count()):
            item = panel._good_list.item(i)
            if item and "basil" in item.text().lower():
                panel._good_list.itemClicked.emit(item)
                break

        assert emitted == ["basil"]

        scene.removeItem(tomato_item)
        scene.removeItem(basil_item)
