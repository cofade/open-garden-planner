"""Integration tests for US-G4 (issue #320) — Plant lists & favourites.

Covers:
  * Persistent storage of favourites and named lists across store reloads.
  * Drag-to-canvas creation reusing gallery drop orchestration:
    - Auto-parenting to underlying bed.
    - Sizing according to spread/height.
    - Planting date stamped to today.
    - Single undo/redo step.
  * JSON export and import round-trip across independent stores.
  * 'Update from plan' explicit snapshot update without silent overwrites.
  * PlantListsPanel widget interactions (list switching, entry selection).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import (
    PlantCycle,
    PlantSpeciesData,
    SunRequirement,
    WaterNeeds,
)
from open_garden_planner.models.plant_lists import PlantListStore
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.plant_lists_panel import PlantListsPanel


@pytest.fixture()
def canvas(qtbot: Any) -> CanvasView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


def _drop(view: CanvasView, mime_text: str, scene_pos: QPointF = QPointF(100, 100)) -> None:
    """Simulate a drop with the given MIME text at scene_pos."""
    mime = QMimeData()
    mime.setText(mime_text)
    view_point = view.mapFromScene(scene_pos)
    event = QDropEvent(
        QPointF(view_point),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.dropEvent(event)


class TestPlantListsIntegration:
    def test_favourites_persistence_across_reloads(self, tmp_path: Any) -> None:
        db_file = tmp_path / "plant_lists.json"
        store1 = PlantListStore(storage_path=db_file)

        tomato = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            cycle=PlantCycle.ANNUAL,
            sun_requirement=SunRequirement.FULL_SUN,
            water_needs=WaterNeeds.MEDIUM,
            max_spread_cm=60.0,
            max_height_cm=150.0,
        )
        apple = PlantSpeciesData(
            scientific_name="Malus domestica",
            common_name="Apple Tree",
            cycle=PlantCycle.PERENNIAL,
            sun_requirement=SunRequirement.FULL_SUN,
            max_spread_cm=300.0,
            max_height_cm=450.0,
            data_source="permapeople",
            source_id="12345",
        )

        assert store1.is_favorite(tomato) is False
        store1.toggle_favorite(tomato)
        store1.toggle_favorite(apple)

        assert store1.is_favorite(tomato) is True
        assert store1.is_favorite(apple) is True
        assert len(store1.get_list("favorites").entries) == 2

        # Reload in fresh store instance pointing to same file
        store2 = PlantListStore(storage_path=db_file)
        assert store2.is_favorite(tomato) is True
        assert store2.is_favorite(apple) is True
        fav_entries = store2.get_list("favorites").entries
        assert len(fav_entries) == 2
        entry_names = {e.species.common_name for e in fav_entries}
        assert entry_names == {"Tomato", "Apple Tree"}

    def test_drag_to_canvas_with_auto_parenting_and_undo(
        self, canvas: CanvasView, tmp_path: Any, monkeypatch: Any
    ) -> None:
        db_file = tmp_path / "plant_lists.json"
        store = PlantListStore(storage_path=db_file)
        monkeypatch.setattr(
            "open_garden_planner.models.plant_lists.get_plant_list_store",
            lambda: store,
        )

        # Place a bed on canvas at (50, 50, 200, 200)
        scene = canvas.scene()
        bed = RectangleItem(50, 50, 200, 200, object_type=ObjectType.RAISED_BED)
        scene.addItem(bed)

        # Create a plant in favorites
        tomato = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            cycle=PlantCycle.ANNUAL,
            max_spread_cm=60.0,
            max_height_cm=150.0,
        )
        entry = store.add_entry("favorites", tomato, note="Heirloom brandywine")
        assert entry is not None

        # Drop inside the bed at (120, 120)
        _drop(canvas, f"plant_list:{entry.id}", scene_pos=QPointF(120, 120))

        # Check created item
        plant_items = [i for i in scene.items() if isinstance(i, CircleItem)]
        assert len(plant_items) == 1
        plant = plant_items[0]

        # Verify auto-parenting to the bed
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

        # Verify species metadata
        assert plant.plant_species == "Tomato"
        assert plant.radius == pytest.approx(30.0)  # 60cm spread / 2
        assert plant.metadata.get("plant_species") is not None
        assert plant.metadata["plant_species"]["common_name"] == "Tomato"

        # Verify default planting date stamped to today (US-E8)
        assert plant.metadata.get("plant_instance", {}).get("planting_date") == date.today().isoformat()

        # Verify single undo step reverses plant addition and unparents from bed
        cmd_mgr = canvas._command_manager
        assert cmd_mgr.can_undo is True
        cmd_mgr.undo()

        plant_items_after_undo = [i for i in scene.items() if isinstance(i, CircleItem)]
        assert len(plant_items_after_undo) == 0
        assert plant.item_id not in bed.child_item_ids

        # Redo restores plant and re-parents to bed
        assert cmd_mgr.can_redo is True
        cmd_mgr.redo()

        plant_items_after_redo = [i for i in scene.items() if isinstance(i, CircleItem)]
        assert len(plant_items_after_redo) == 1
        restored = plant_items_after_redo[0]
        assert restored.parent_bed_id == bed.item_id
        assert restored.item_id in bed.child_item_ids

    def test_json_export_and_import_roundtrip(self, tmp_path: Any) -> None:
        store1 = PlantListStore(storage_path=tmp_path / "store1.json")
        orchard = store1.create_list("Orchard Plan", description="Fruit trees for south slope")

        apple = PlantSpeciesData(
            scientific_name="Malus domestica",
            common_name="Apple",
            max_spread_cm=300.0,
            max_height_cm=450.0,
        )
        pear = PlantSpeciesData(
            scientific_name="Pyrus communis",
            common_name="Pear",
            max_spread_cm=250.0,
            max_height_cm=400.0,
        )

        store1.add_entry(orchard.id, apple, note="Honeycrisp")
        store1.add_entry(orchard.id, pear, note="Conference")

        # Export to JSON
        json_str = store1.export_list_to_json(orchard.id)
        assert "open_garden_planner_plant_list" in json_str
        assert "Honeycrisp" in json_str

        # Import into an independent store
        store2 = PlantListStore(storage_path=tmp_path / "store2.json")
        imported = store2.import_list_from_json(json_str)

        assert imported.name == "Orchard Plan"
        assert imported.description == "Fruit trees for south slope"
        assert len(imported.entries) == 2
        entry_species = {e.species.scientific_name for e in imported.entries}
        assert entry_species == {"Malus domestica", "Pyrus communis"}

    def test_update_from_plan_explicit_sync(self, tmp_path: Any) -> None:
        store = PlantListStore(storage_path=tmp_path / "store.json")
        chili = PlantSpeciesData(
            scientific_name="Capsicum annuum",
            common_name="Chili Pepper",
            max_spread_cm=40.0,
            max_height_cm=60.0,
        )
        entry = store.add_entry("favorites", chili, note="Mild")
        assert entry is not None

        # Verify initial snapshot
        assert entry.species.max_height_cm == pytest.approx(60.0)

        # User updates variety/description on plan to 90cm height
        updated_data = PlantSpeciesData(
            scientific_name="Capsicum annuum",
            common_name="Chili Pepper",
            description="Habanero hot pepper",
            max_spread_cm=50.0,
            max_height_cm=90.0,
        )

        # Snapshot does NOT change without explicit update
        assert entry.species.max_height_cm == pytest.approx(60.0)

        # Trigger update
        success = store.update_entry_species("favorites", entry.id, updated_data)
        assert success is True

        # Check refreshed snapshot
        _, refreshed_entry = store.get_entry(entry.id)
        assert refreshed_entry is not None
        assert refreshed_entry.species.description == "Habanero hot pepper"
        assert refreshed_entry.species.max_height_cm == pytest.approx(90.0)

    def test_plant_lists_panel_ui(
        self, qtbot: Any, tmp_path: Any
    ) -> None:
        db_file = tmp_path / "plant_lists.json"
        store = PlantListStore(storage_path=db_file)

        custom = store.create_list("Herbs")
        basil = PlantSpeciesData(
            scientific_name="Ocimum basilicum",
            common_name="Basil",
            max_spread_cm=25.0,
            max_height_cm=30.0,
        )
        store.add_entry(custom.id, basil, note="Genovese")

        panel = PlantListsPanel(store=store)
        qtbot.addWidget(panel)

        # List combo should have 2 lists: Favorites and Herbs
        assert panel._list_combo.count() == 2
        assert "Favorites" in panel._list_combo.itemText(0)
        assert "Herbs" in panel._list_combo.itemText(1)

        # Switch to Herbs
        panel._list_combo.setCurrentIndex(1)
        assert panel._current_list_id == custom.id
        assert panel._entries_list.count() == 1
        item = panel._entries_list.item(0)
        assert "Basil" in item.text()

    def test_panel_add_selected_from_canvas_and_note_update(
        self, qtbot: Any, tmp_path: Any
    ) -> None:
        """Panel adds selected canvas plants and supports note updates and list moves."""
        db_file = tmp_path / "plant_lists.json"
        store = PlantListStore(storage_path=db_file)
        custom = store.create_list("Veggies")

        scene = CanvasScene()
        plant_item = CircleItem(100.0, 100.0, 25.0, ObjectType.PERENNIAL)
        plant_item.metadata["plant_species"] = {
            "scientific_name": "Daucus carota",
            "common_name": "Carrot",
            "max_spread_cm": 15.0,
        }
        scene.addItem(plant_item)
        plant_item.setSelected(True)

        panel = PlantListsPanel(store=store, canvas_scene=scene)
        qtbot.addWidget(panel)
        panel._current_list_id = custom.id
        panel._refresh_entries()

        # Add selected canvas plant
        panel._on_add_selected_from_canvas()
        assert len(store.get_list(custom.id).entries) == 1
        entry = store.get_list(custom.id).entries[0]
        assert entry.species.common_name == "Carrot"

        # Update note
        store.update_entry_note(custom.id, entry.id, "Sweet Nantes variety")
        updated_entry = store.get_list(custom.id).entries[0]
        assert updated_entry.note == "Sweet Nantes variety"

        # Move to favorites
        store.move_entry(custom.id, store.FAVORITES_ID, entry.id)
        assert len(store.get_list(custom.id).entries) == 0
        assert len(store.get_list(store.FAVORITES_ID).entries) == 1

        # Remove from favorites
        store.remove_entry(store.FAVORITES_ID, entry.id)
        assert len(store.get_list(store.FAVORITES_ID).entries) == 0

    def test_plant_database_panel_favorite_state_and_deselect(
        self, qtbot: Any, tmp_path: Any
    ) -> None:
        """PlantDatabasePanel favorite button toggles favorites and disables on deselect."""
        from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel

        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        sp = PlantSpeciesData(
            scientific_name="Fragaria ananassa",
            common_name="Strawberry",
        )
        panel._update_profile_header(sp)
        assert panel._favorite_btn.isEnabled()
        assert panel._favorite_btn.text() == "☆"

        # Toggle favorite
        panel._on_toggle_favorite()
        assert panel._favorite_btn.text() == "⭐"
        assert panel._list_store.is_favorite(sp)

        # Deselect: verify favorite button is disabled and reset to ☆ (P1-2 fix verification)
        panel._hide_details()
        assert not panel._favorite_btn.isEnabled()
        assert panel._favorite_btn.text() == "☆"

        # Show no metadata: also verify button is disabled
        panel._show_no_metadata()
        assert not panel._favorite_btn.isEnabled()
        assert panel._favorite_btn.text() == "☆"

        # Cleanup store
        panel._list_store.toggle_favorite(sp)

    def test_category_dropdown_favorites_tooltip_and_toggle(
        self, qtbot: Any
    ) -> None:
        """CategoryDropdown thumbnail reflects favorite status in tooltip via canonical resolution."""
        from open_garden_planner.core.tools import ToolType
        from open_garden_planner.models.plant_lists import get_plant_list_store
        from open_garden_planner.ui.widgets.category_dropdown import _ThumbnailButton
        from open_garden_planner.ui.widgets.gallery_data import GalleryItem

        store = get_plant_list_store()
        item = GalleryItem(
            name="Apple Tree",
            tool_type=ToolType.TREE,
            object_type=ObjectType.TREE,
            species="apple tree",
        )
        btn = _ThumbnailButton(item)
        qtbot.addWidget(btn)
        btn.show()

        sp_obj = btn._get_species_obj()
        if store.is_favorite(sp_obj):
            store.toggle_favorite(sp_obj)

        # Initially not favorited
        btn._update_tooltip()
        assert btn.toolTip() == "Apple Tree"
        assert not btn._star_badge.isVisible()

        # Favorite via species object
        sp_obj = btn._get_species_obj()
        store.toggle_favorite(sp_obj)
        try:
            btn._update_tooltip()
            # Must show star badge and tooltip (verifies P0-2 resolution fix and visual badge)
            assert not btn._star_badge.isHidden()
            assert btn._star_badge.isVisible()
            assert "⭐" in btn.toolTip()
            assert "Apple Tree" in btn.toolTip()
        finally:
            store.toggle_favorite(sp_obj)
            btn._update_tooltip()
            assert not btn._star_badge.isVisible()
            assert "⭐" not in btn.toolTip()
