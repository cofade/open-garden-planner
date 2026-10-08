"""Unit tests for PlantList and PlantListStore (US-G4, issue #320)."""

import json
from pathlib import Path

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.plant_lists import (
    PlantListEntry,
    PlantListStore,
    _get_species_key,
)


def test_species_key_extraction() -> None:
    """_get_species_key extracts lowercased key with fallback hierarchy."""
    sp = PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        source_id="bundled-tomato",
    )
    assert _get_species_key(sp) == "bundled-tomato"

    sp2 = PlantSpeciesData(
        scientific_name="Malus domestica",
        common_name="Apple",
    )
    assert _get_species_key(sp2) == "malus domestica"

    d = {"common_name": "Pear"}
    assert _get_species_key(d) == "pear"
    d_apple = {"common_name": "Apple Tree"}
    assert _get_species_key(d_apple) == "malus domestica"
    assert _get_species_key("apple tree") == "malus domestica"
    assert _get_species_key("Carrot") == "daucus carota"
    assert _get_species_key("Custom Unknown 123") == "custom unknown 123"


def test_plant_list_entry_serialization_roundtrip() -> None:
    """PlantListEntry round-trips through dict preserving snapshot."""
    sp = PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        max_spread_cm=60.0,
        max_height_cm=150.0,
    )
    entry = PlantListEntry(species=sp, note="Cherry tomato variety")
    entry_dict = entry.to_dict()

    restored = PlantListEntry.from_dict(entry_dict)
    assert restored.id == entry.id
    assert restored.species_key == entry.species_key
    assert restored.species.scientific_name == "Solanum lycopersicum"
    assert restored.species.max_spread_cm == 60.0
    assert restored.note == "Cherry tomato variety"


def test_plant_list_entry_corrupt_species_dict_fallback() -> None:
    """PlantListEntry handles unresolvable or corrupted species data without crashing."""
    raw = {
        "id": "abc-123",
        "species_key": "mystery-plant",
        "species": {"scientific_name": "Mystery sp.", "cycle": "invalid_enum_value"},
        "note": "A note",
    }
    entry = PlantListEntry.from_dict(raw)
    assert entry.id == "abc-123"
    assert entry.species_key == "mystery-plant"
    assert entry.species.scientific_name == "Mystery sp."


def test_store_creates_default_favorites(tmp_path: Path) -> None:
    """A fresh store creates a reserved favorites list."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    lists = store.all_lists()
    assert len(lists) == 1
    assert lists[0].id == PlantListStore.FAVORITES_ID
    assert lists[0].name == "Favorites"


def test_store_atomic_persistence(tmp_path: Path) -> None:
    """Adding entries and lists persists atomically to JSON."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    tomato = PlantSpeciesData(
        scientific_name="Solanum lycopersicum", common_name="Tomato"
    )
    store.add_entry(PlantListStore.FAVORITES_ID, tomato, note="My favorite red tomato")

    assert storage_file.exists()
    with open(storage_file, encoding="utf-8") as f:
        data = json.load(f)
    assert "lists" in data
    assert any(pl["id"] == "favorites" for pl in data["lists"])

    # Reload store from same file
    store2 = PlantListStore(storage_file)
    assert store2.is_favorite(tomato)
    fav = store2.get_list(PlantListStore.FAVORITES_ID)
    assert fav is not None
    assert len(fav.entries) == 1
    assert fav.entries[0].note == "My favorite red tomato"


def test_store_cannot_rename_or_delete_favorites(tmp_path: Path) -> None:
    """The reserved favorites list cannot be deleted or renamed."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    assert not store.rename_list(PlantListStore.FAVORITES_ID, "Hacked")
    assert not store.delete_list(PlantListStore.FAVORITES_ID)

    fav = store.get_list(PlantListStore.FAVORITES_ID)
    assert fav is not None
    assert fav.name == "Favorites"


def test_store_crud_custom_lists(tmp_path: Path) -> None:
    """Custom lists can be created, renamed, populated, and deleted."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    orchard = store.create_list("Orchard Trees", "Fruit tree varieties")
    assert orchard.id != PlantListStore.FAVORITES_ID
    assert orchard.name == "Orchard Trees"

    apple = PlantSpeciesData(scientific_name="Malus domestica", common_name="Apple")
    entry = store.add_entry(orchard.id, apple, note="Honeycrisp")
    assert entry is not None
    assert entry.species_key == "malus domestica"

    # Search entry
    found_list, found_entry = store.get_entry(entry.id)
    assert found_list is not None and found_list.id == orchard.id
    assert found_entry is not None and found_entry.id == entry.id

    # Update note
    assert store.update_entry_note(orchard.id, entry.id, "Honeycrisp updated note")
    assert found_entry.note == "Honeycrisp updated note"

    # Rename list
    assert store.rename_list(orchard.id, "Fruit Orchard")
    assert store.get_list(orchard.id).name == "Fruit Orchard"

    # Move entry to favorites
    assert store.move_entry(orchard.id, PlantListStore.FAVORITES_ID, entry.id)
    assert len(store.get_list(orchard.id).entries) == 0
    assert len(store.get_list(PlantListStore.FAVORITES_ID).entries) == 1

    # Delete custom list
    assert store.delete_list(orchard.id)
    assert store.get_list(orchard.id) is None


def test_store_toggle_favorite(tmp_path: Path) -> None:
    """toggle_favorite toggles status and persists."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    carrot = PlantSpeciesData(scientific_name="Daucus carota", common_name="Carrot")
    assert not store.is_favorite(carrot)

    # First toggle: adds to favorites
    result1 = store.toggle_favorite(carrot)
    assert result1 is True
    assert store.is_favorite(carrot)

    # Second toggle: removes from favorites
    result2 = store.toggle_favorite(carrot)
    assert result2 is False
    assert not store.is_favorite(carrot)


def test_store_update_from_plan(tmp_path: Path) -> None:
    """update_entry_species updates the stored snapshot explicitly."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    plant_orig = PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        max_height_cm=100.0,
    )
    entry = store.add_entry(PlantListStore.FAVORITES_ID, plant_orig)
    assert entry is not None

    plant_modified = PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        max_height_cm=180.0,
    )
    assert store.update_entry_species(
        PlantListStore.FAVORITES_ID, entry.id, plant_modified
    )

    fav = store.get_list(PlantListStore.FAVORITES_ID)
    assert fav.entries[0].species.max_height_cm == 180.0


def test_export_import_json(tmp_path: Path) -> None:
    """Lists can be exported and imported as JSON round-trip."""
    storage_file = tmp_path / "plant_lists.json"
    store = PlantListStore(storage_file)

    herbs = store.create_list("Kitchen Herbs", "Cooking herbs")
    basil = PlantSpeciesData(scientific_name="Ocimum basilicum", common_name="Basil")
    store.add_entry(herbs.id, basil, note="Sweet basil")

    exported_json = store.export_list_to_json(herbs.id)
    assert "Kitchen Herbs" in exported_json
    assert "Ocimum basilicum" in exported_json

    # Import into a second store
    storage_file2 = tmp_path / "plant_lists_profile2.json"
    store2 = PlantListStore(storage_file2)
    imported = store2.import_list_from_json(exported_json)

    assert imported.name == "Kitchen Herbs"
    assert len(imported.entries) == 1
    assert imported.entries[0].species.scientific_name == "Ocimum basilicum"
    assert imported.entries[0].note == "Sweet basil"
