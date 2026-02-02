"""Tests for plant search panel."""

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem
from open_garden_planner.ui.panels import PlantSearchPanel


class TestPlantSearchPanel:
    """Tests for the PlantSearchPanel class."""

    def test_creation(self, qtbot):  # noqa: ARG002
        """Test that a plant search panel can be created."""
        panel = PlantSearchPanel()
        assert panel is not None
        assert panel.search_input is not None
        assert panel.results_list is not None

    def test_filter_checkboxes_default_checked(self, qtbot):  # noqa: ARG002
        """Test that all filter checkboxes are checked by default."""
        panel = PlantSearchPanel()
        assert panel.tree_checkbox.isChecked()
        assert panel.shrub_checkbox.isChecked()
        assert panel.perennial_checkbox.isChecked()

    def test_no_plants_message(self, qtbot):  # noqa: ARG002
        """Test panel shows 'no plants' when scene is empty."""
        panel = PlantSearchPanel()
        scene = CanvasScene()
        panel.set_canvas_scene(scene)

        assert panel.results_list.count() == 0
        assert "No plants" in panel.results_label.text()

    def test_finds_tree_in_scene(self, qtbot):  # noqa: ARG002
        """Test that the panel finds a tree in the scene."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add a tree to the scene
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        assert panel.results_list.count() == 1
        assert "1 plant" in panel.results_label.text()

    def test_finds_multiple_plants(self, qtbot):  # noqa: ARG002
        """Test that the panel finds multiple plants."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add various plants
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        shrub = CircleItem(200, 100, 30, object_type=ObjectType.SHRUB)
        shrub.name = "Rose Bush"
        scene.addItem(shrub)

        perennial = CircleItem(300, 100, 20, object_type=ObjectType.PERENNIAL)
        perennial.name = "Lavender"
        scene.addItem(perennial)

        panel.set_canvas_scene(scene)

        assert panel.results_list.count() == 3
        assert "3 plants" in panel.results_label.text()

    def test_search_filters_by_name(self, qtbot):  # noqa: ARG002
        """Test that search input filters plants by name."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add plants with different names
        tree1 = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree1.name = "Apple Tree"
        scene.addItem(tree1)

        tree2 = CircleItem(200, 100, 50, object_type=ObjectType.TREE)
        tree2.name = "Cherry Tree"
        scene.addItem(tree2)

        panel.set_canvas_scene(scene)

        # Initially shows all plants
        assert panel.results_list.count() == 2

        # Search for "Apple"
        panel.search_input.setText("Apple")
        assert panel.results_list.count() == 1
        assert "Showing 1 of 2" in panel.results_label.text()

        # Clear search shows all again
        panel.search_input.clear()
        assert panel.results_list.count() == 2

    def test_type_filter_trees_only(self, qtbot):  # noqa: ARG002
        """Test filtering to show only trees."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add different plant types
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        shrub = CircleItem(200, 100, 30, object_type=ObjectType.SHRUB)
        scene.addItem(shrub)

        perennial = CircleItem(300, 100, 20, object_type=ObjectType.PERENNIAL)
        scene.addItem(perennial)

        panel.set_canvas_scene(scene)

        # Initially shows all
        assert panel.results_list.count() == 3

        # Uncheck shrubs and perennials
        panel.shrub_checkbox.setChecked(False)
        panel.perennial_checkbox.setChecked(False)

        # Should only show trees
        assert panel.results_list.count() == 1

    def test_type_filter_shrubs_only(self, qtbot):  # noqa: ARG002
        """Test filtering to show only shrubs."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        shrub = CircleItem(200, 100, 30, object_type=ObjectType.SHRUB)
        scene.addItem(shrub)

        panel.set_canvas_scene(scene)

        # Uncheck trees
        panel.tree_checkbox.setChecked(False)
        panel.perennial_checkbox.setChecked(False)

        assert panel.results_list.count() == 1

    def test_search_by_scientific_name(self, qtbot):  # noqa: ARG002
        """Test searching by scientific name in metadata."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add a tree with plant metadata
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        # Access the metadata dict directly to add plant species data
        tree.metadata["plant_species"] = {
            "common_name": "Apple",
            "scientific_name": "Malus domestica",
            "family": "Rosaceae",
        }
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        # Search by scientific name
        panel.search_input.setText("Malus")
        assert panel.results_list.count() == 1

        # Search by family
        panel.search_input.setText("Rosaceae")
        assert panel.results_list.count() == 1

    def test_click_selects_plant(self, qtbot):  # noqa: ARG002
        """Test that clicking a plant in the list selects it."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        # Initially not selected
        assert not tree.isSelected()

        # Click on the item in the list
        list_item = panel.results_list.item(0)
        panel._on_item_clicked(list_item)

        # Should now be selected
        assert tree.isSelected()

    def test_refresh_updates_list(self, qtbot):  # noqa: ARG002
        """Test that refresh_plant_list updates the list."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        panel.set_canvas_scene(scene)
        assert panel.results_list.count() == 0

        # Add a plant after initial setup
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        # Manually refresh
        panel.refresh_plant_list()
        assert panel.results_list.count() == 1

    def test_ignores_non_plant_items(self, qtbot):  # noqa: ARG002
        """Test that non-plant items are not shown."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add a tree and a generic circle
        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        circle = CircleItem(200, 100, 30, object_type=ObjectType.GENERIC_CIRCLE)
        scene.addItem(circle)

        panel.set_canvas_scene(scene)

        # Should only show the tree, not the generic circle
        assert panel.results_list.count() == 1

    def test_case_insensitive_search(self, qtbot):  # noqa: ARG002
        """Test that search is case insensitive."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        # Search with different cases
        panel.search_input.setText("apple")
        assert panel.results_list.count() == 1

        panel.search_input.setText("APPLE")
        assert panel.results_list.count() == 1

        panel.search_input.setText("ApPlE")
        assert panel.results_list.count() == 1

    def test_alphabetical_order(self, qtbot):  # noqa: ARG002
        """Test that plants are listed in alphabetical order."""
        from PyQt6.QtCore import Qt

        panel = PlantSearchPanel()
        scene = CanvasScene()

        # Add plants in non-alphabetical order
        tree3 = CircleItem(300, 100, 50, object_type=ObjectType.TREE)
        tree3.name = "Zebra Plant"
        scene.addItem(tree3)

        tree1 = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree1.name = "Apple Tree"
        scene.addItem(tree1)

        tree2 = CircleItem(200, 100, 50, object_type=ObjectType.TREE)
        tree2.name = "Cherry Tree"
        scene.addItem(tree2)

        panel.set_canvas_scene(scene)

        # Verify alphabetical order
        assert panel.results_list.count() == 3

        # Get names from list items
        names = []
        for i in range(panel.results_list.count()):
            item = panel.results_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            _, graphics_item = data
            names.append(graphics_item.name)

        assert names == ["Apple Tree", "Cherry Tree", "Zebra Plant"]
