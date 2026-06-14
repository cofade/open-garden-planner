"""Tests for plant search panel."""

from unittest.mock import patch
from uuid import UUID

from PyQt6.QtCore import Qt

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
        assert "3 plant" in panel.results_label.text()

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

    def test_click_selects_plant(self, qtbot):
        """Test that clicking a plant in the list selects it (deferred)."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        # Initially not selected
        assert not tree.isSelected()

        # Click on the item in the list (selection is applied on the event loop)
        list_item = panel.results_list.item(0)
        panel._on_item_clicked(list_item)

        # Should become selected once the deferred QTimer fires
        qtbot.waitUntil(lambda: tree.isSelected())

    def test_click_after_item_deleted_does_not_crash(self, qtbot):
        """Clicking a row whose item was deleted must not crash and must self-heal."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)
        assert panel.results_list.count() == 1

        list_item = panel.results_list.item(0)

        # Remove the item from the scene so the row's stored id is now stale.
        scene.removeItem(tree)

        # Clicking must not raise and must rebuild the (now empty) list.
        panel._on_item_clicked(list_item)
        qtbot.waitUntil(lambda: panel.results_list.count() == 0)

    def test_rows_store_item_id_not_graphics_item(self, qtbot):  # noqa: ARG002
        """Rows must store the stable item id (a UUID), never a live item reference.

        This pins the fix for #212: caching a QGraphicsItem in the row went stale
        after scene mutations. Against the old tuple-storing code this fails.
        """
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)

        payload = panel.results_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert isinstance(payload, UUID)
        assert payload == tree.item_id

    def test_click_selects_correct_item_after_rebuild(self, qtbot):
        """Smoke test: clicking a row routes to the correct plant after a rebuild.

        (The id-vs-reference regression is pinned by
        test_rows_store_item_id_not_graphics_item above; this only checks routing.)
        """
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree_a = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree_a.name = "Apple Tree"
        scene.addItem(tree_a)

        tree_b = CircleItem(300, 100, 50, object_type=ObjectType.TREE)
        tree_b.name = "Birch Tree"
        scene.addItem(tree_b)

        panel.set_canvas_scene(scene)
        # Rebuild the list (as a scene-change refresh would).
        panel.refresh_plant_list()

        # Click the second row (Birch Tree) to prove the right id is resolved.
        panel._on_item_clicked(panel.results_list.item(1))

        qtbot.waitUntil(lambda: tree_b.isSelected())
        assert not tree_a.isSelected()

    def test_noop_refresh_does_not_rebuild(self, qtbot):  # noqa: ARG002
        """A refresh with an unchanged plant set must NOT clear/rebuild the list.

        The destructive rebuild on every chatty scene.changed reset the scroll
        position and tore down rows mid-click (#212). With the signature guard a
        no-op refresh leaves the existing rows (and scroll/selection) untouched.
        """
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)
        before = [panel.results_list.item(i) for i in range(panel.results_list.count())]

        # Same scene → same visible set → must short-circuit before clear().
        with patch.object(
            panel.results_list, "clear", wraps=panel.results_list.clear
        ) as clear_spy:
            panel.refresh_plant_list()
        clear_spy.assert_not_called()

        after = [panel.results_list.item(i) for i in range(panel.results_list.count())]
        assert after == before  # same QListWidgetItem objects, not recreated

    def test_selection_preserved_across_rebuild(self, qtbot):  # noqa: ARG002
        """When the list IS rebuilt, the previously-selected row is re-selected."""
        panel = PlantSearchPanel()
        scene = CanvasScene()

        apple = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        apple.name = "Apple Tree"
        scene.addItem(apple)

        panel.set_canvas_scene(scene)
        panel.results_list.setCurrentItem(panel.results_list.item(0))
        selected_id = panel.results_list.currentItem().data(Qt.ItemDataRole.UserRole)

        # Membership change forces a real rebuild.
        birch = CircleItem(300, 100, 50, object_type=ObjectType.TREE)
        birch.name = "Birch Tree"
        scene.addItem(birch)
        panel.refresh_plant_list()

        assert panel.results_list.count() == 2
        current = panel.results_list.currentItem()
        assert current is not None
        assert current.data(Qt.ItemDataRole.UserRole) == selected_id

    def test_row_widget_is_mouse_transparent(self, qtbot):  # noqa: ARG002
        """Row widgets must be transparent to the mouse so clicks reach the list.

        Otherwise a press on the row widget body is swallowed and itemClicked
        doesn't fire → "single-click sometimes needs a second click" (#212).
        """
        panel = PlantSearchPanel()
        scene = CanvasScene()

        tree = CircleItem(100, 100, 50, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        scene.addItem(tree)

        panel.set_canvas_scene(scene)
        widget = panel.results_list.itemWidget(panel.results_list.item(0))
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

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

        # Get names from list items - rows now store only the item id; resolve the
        # live item via the scene.
        names = []
        for i in range(panel.results_list.count()):
            item = panel.results_list.item(i)
            item_id = item.data(Qt.ItemDataRole.UserRole)
            graphics_item = scene.find_item_by_id(item_id)
            names.append(graphics_item.name)

        assert names == ["Apple Tree", "Cherry Tree", "Zebra Plant"]
