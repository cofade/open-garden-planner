"""Data models and storage for plant lists and favourites (US-G4, issue #320).

Provides:
  * PlantListEntry: A single species entry within a list, holding a
    PlantSpeciesData snapshot so custom/imported plants survive even if the
    source is removed or unreachable.
  * PlantList: A named collection of species entries (e.g. Favorites,
    a bed palette, or a companion grouping).
  * PlantListStore: Cross-project persistent store backed by
    <app-data>/plant_lists.json using atomic file replacement.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from open_garden_planner.models.plant_data import PlantSpeciesData, species_key


def _get_species_key(species_obj: PlantSpeciesData | dict[str, Any] | str) -> str:
    """Extract canonical lowercased species_key from a species object or string."""
    if isinstance(species_obj, str):
        return species_obj.strip().lower()
    if isinstance(species_obj, PlantSpeciesData):
        return species_key({
            "source_id": species_obj.source_id,
            "scientific_name": species_obj.scientific_name,
            "common_name": species_obj.common_name,
        })
    if isinstance(species_obj, dict):
        return species_key(species_obj)
    return "_unknown"


@dataclass
class PlantListEntry:
    """An entry in a plant list."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    species_key: str = ""
    species: PlantSpeciesData = field(
        default_factory=lambda: PlantSpeciesData(
            scientific_name="", common_name=""
        )
    )
    added_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.species_key and self.species:
            self.species_key = _get_species_key(self.species)
        if not self.added_at:
            self.added_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to dictionary."""
        return {
            "id": self.id,
            "species_key": self.species_key,
            "species": self.species.to_dict() if self.species else {},
            "added_at": self.added_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlantListEntry:
        """Deserialize entry from dictionary."""
        species_raw = data.get("species", {})
        try:
            species_obj = (
                PlantSpeciesData.from_dict(species_raw)
                if species_raw
                else PlantSpeciesData(scientific_name="", common_name="")
            )
        except Exception:  # noqa: BLE001
            species_obj = PlantSpeciesData(
                scientific_name=species_raw.get("scientific_name", ""),
                common_name=species_raw.get("common_name", ""),
            )

        entry_id = data.get("id") or str(uuid.uuid4())
        sp_key = data.get("species_key") or _get_species_key(species_obj)
        added_at = data.get("added_at") or datetime.now(UTC).isoformat()
        note = data.get("note", "")

        return cls(
            id=entry_id,
            species_key=sp_key,
            species=species_obj,
            added_at=added_at,
            note=note,
        )


@dataclass
class PlantList:
    """A named collection of plant species."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    entries: list[PlantListEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize list to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlantList:
        """Deserialize list from dictionary."""
        list_id = data.get("id") or str(uuid.uuid4())
        name = data.get("name", "")
        desc = data.get("description", "")
        raw_entries = data.get("entries", [])
        entries = [PlantListEntry.from_dict(e) for e in raw_entries]
        return cls(id=list_id, name=name, description=desc, entries=entries)


class PlantListStore(QObject):
    """Persistent storage for plant lists and favourites.

    Persists to ``<app-data>/plant_lists.json`` using same-directory
    atomic writes (temp file + ``os.replace``) to prevent corruption.
    The ``favorites`` list is reserved and always present.
    """

    changed = pyqtSignal()

    FILENAME = "plant_lists.json"
    FAVORITES_ID = "favorites"

    def __init__(self, storage_path: Path | None = None) -> None:
        super().__init__()
        if storage_path is None:
            from open_garden_planner.services.plant_library import get_app_data_dir

            self._path = get_app_data_dir() / self.FILENAME
        else:
            self._path = storage_path

        self._lists: dict[str, PlantList] = {}
        self._load()

    @property
    def path(self) -> Path:
        """Return the storage file path."""
        return self._path

    # ── Persistence ───────────────────────────────────────────────────────────

    def _ensure_favorites(self) -> None:
        """Ensure the reserved favorites list always exists."""
        if self.FAVORITES_ID not in self._lists:
            self._lists[self.FAVORITES_ID] = PlantList(
                id=self.FAVORITES_ID,
                name="Favorites",
                description="Starred plant species",
                entries=[],
            )

    def _load(self) -> None:
        """Load lists from disk."""
        self._lists = {}
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as fh:
                    raw_data = json.load(fh)
                if isinstance(raw_data, dict):
                    lists_raw = raw_data.get("lists", [])
                elif isinstance(raw_data, list):
                    lists_raw = raw_data
                else:
                    lists_raw = []

                for item in lists_raw:
                    pl = PlantList.from_dict(item)
                    self._lists[pl.id] = pl
            except Exception:  # noqa: BLE001
                # Corrupted or unreadable file: start clean with favorites
                self._lists = {}

        self._ensure_favorites()

    def _atomic_write(self, text: str) -> None:
        """Write text to storage path atomically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".ogp-plant-lists-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp_name, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp_name)
            raise

    def save(self) -> None:
        """Persist lists to disk and emit changed signal."""
        self._ensure_favorites()
        data = {
            "version": "1.0",
            "lists": [pl.to_dict() for pl in self.all_lists()],
        }
        self._atomic_write(json.dumps(data, indent=2))
        self.changed.emit()

    # ── List operations ───────────────────────────────────────────────────────

    def all_lists(self) -> list[PlantList]:
        """Return all lists with Favorites first, followed by custom lists sorted by name."""
        fav = self._lists.get(self.FAVORITES_ID)
        others = [
            pl for pl in self._lists.values() if pl.id != self.FAVORITES_ID
        ]
        others.sort(key=lambda pl: pl.name.lower())
        return [fav] + others if fav else others

    def get_list(self, list_id: str) -> PlantList | None:
        """Return list by ID or None."""
        return self._lists.get(list_id)

    def create_list(self, name: str, description: str = "") -> PlantList:
        """Create a new custom plant list."""
        clean_name = name.strip()
        if not clean_name:
            clean_name = "New List"
        new_list = PlantList(
            id=str(uuid.uuid4()),
            name=clean_name,
            description=description.strip(),
            entries=[],
        )
        self._lists[new_list.id] = new_list
        self.save()
        return new_list

    def rename_list(self, list_id: str, new_name: str) -> bool:
        """Rename a list. Reserved favorites cannot be renamed."""
        if list_id == self.FAVORITES_ID:
            return False
        clean_name = new_name.strip()
        if not clean_name:
            return False
        pl = self._lists.get(list_id)
        if not pl:
            return False
        pl.name = clean_name
        self.save()
        return True

    def delete_list(self, list_id: str) -> bool:
        """Delete a list. Reserved favorites cannot be deleted."""
        if list_id == self.FAVORITES_ID:
            return False
        if list_id in self._lists:
            del self._lists[list_id]
            self.save()
            return True
        return False

    # ── Entry operations ──────────────────────────────────────────────────────

    def get_entry(
        self, entry_id: str
    ) -> tuple[PlantList, PlantListEntry] | tuple[None, None]:
        """Find an entry across all lists by its ID."""
        for pl in self._lists.values():
            for entry in pl.entries:
                if entry.id == entry_id:
                    return pl, entry
        return None, None

    def add_entry(
        self,
        list_id: str,
        species: PlantSpeciesData,
        note: str = "",
    ) -> PlantListEntry | None:
        """Add a species to a list.

        If already present (matching species_key), updates its snapshot and note,
        avoiding duplicate entries.
        """
        pl = self._lists.get(list_id)
        if not pl:
            return None

        sp_key = _get_species_key(species)
        for existing in pl.entries:
            if existing.species_key == sp_key:
                existing.species = species
                if note:
                    existing.note = note.strip()
                self.save()
                return existing

        entry = PlantListEntry(
            id=str(uuid.uuid4()),
            species_key=sp_key,
            species=species,
            added_at=datetime.now(UTC).isoformat(),
            note=note.strip(),
        )
        pl.entries.append(entry)
        self.save()
        return entry

    def remove_entry(self, list_id: str, entry_id: str) -> bool:
        """Remove an entry from a list."""
        pl = self._lists.get(list_id)
        if not pl:
            return False
        initial_len = len(pl.entries)
        pl.entries = [e for e in pl.entries if e.id != entry_id]
        if len(pl.entries) < initial_len:
            self.save()
            return True
        return False

    def move_entry(self, from_list_id: str, to_list_id: str, entry_id: str) -> bool:
        """Move an entry from one list to another."""
        if from_list_id == to_list_id:
            return False
        from_list = self._lists.get(from_list_id)
        to_list = self._lists.get(to_list_id)
        if not from_list or not to_list:
            return False

        entry_to_move: PlantListEntry | None = None
        new_from_entries: list[PlantListEntry] = []
        for e in from_list.entries:
            if e.id == entry_id:
                entry_to_move = e
            else:
                new_from_entries.append(e)

        if not entry_to_move:
            return False

        from_list.entries = new_from_entries
        # Avoid duplicate in destination
        to_list.entries = [
            e for e in to_list.entries if e.species_key != entry_to_move.species_key
        ]
        to_list.entries.append(entry_to_move)
        self.save()
        return True

    def update_entry_note(self, list_id: str, entry_id: str, note: str) -> bool:
        """Update note for an entry."""
        pl = self._lists.get(list_id)
        if not pl:
            return False
        for e in pl.entries:
            if e.id == entry_id:
                e.note = note.strip()
                self.save()
                return True
        return False

    def update_entry_species(
        self, list_id: str, entry_id: str, species: PlantSpeciesData
    ) -> bool:
        """Update species snapshot for an entry ('Update from plan')."""
        pl = self._lists.get(list_id)
        if not pl:
            return False
        for e in pl.entries:
            if e.id == entry_id:
                e.species = species
                e.species_key = _get_species_key(species)
                self.save()
                return True
        return False

    # ── Favorites shortcuts ───────────────────────────────────────────────────

    def is_favorite(self, species_or_key: PlantSpeciesData | dict[str, Any] | str) -> bool:
        """Check whether a species is in the favorites list."""
        fav = self._lists.get(self.FAVORITES_ID)
        if not fav:
            return False
        target_key = _get_species_key(species_or_key)
        if not target_key or target_key == "_unknown":
            return False
        return any(e.species_key == target_key for e in fav.entries)

    def toggle_favorite(
        self, species: PlantSpeciesData, note: str = ""
    ) -> bool:
        """Toggle favorite status.

        Returns:
            True if now favorited, False if unfavorited.
        """
        fav = self._lists.get(self.FAVORITES_ID)
        if not fav:
            self._ensure_favorites()
            fav = self._lists[self.FAVORITES_ID]

        sp_key = _get_species_key(species)
        for existing in fav.entries:
            if existing.species_key == sp_key:
                self.remove_entry(self.FAVORITES_ID, existing.id)
                return False

        self.add_entry(self.FAVORITES_ID, species, note=note)
        return True

    # ── JSON Export / Import ──────────────────────────────────────────────────

    def export_list_to_json(self, list_id: str) -> str:
        """Export a list to a formatted JSON string."""
        pl = self._lists.get(list_id)
        if not pl:
            raise KeyError(f"Plant list not found: {list_id}")
        data = {
            "version": "1.0",
            "type": "open_garden_planner_plant_list",
            "list": pl.to_dict(),
        }
        return json.dumps(data, indent=2)

    def import_list_from_json(self, json_text: str) -> PlantList:
        """Import a plant list from a JSON string.

        Guarantees unique ID (never overwrites the reserved favorites id)
        and unique list name.
        """
        data = json.loads(json_text)
        if isinstance(data, dict) and "list" in data:
            list_data = data["list"]
        elif isinstance(data, dict):
            list_data = data
        else:
            raise ValueError("Invalid plant list JSON structure")

        imported = PlantList.from_dict(list_data)

        # Do not allow overwriting favorites directly via import
        if imported.id == self.FAVORITES_ID:
            imported.id = str(uuid.uuid4())
            imported.name = f"{imported.name} (Imported)"

        # Ensure unique name
        existing_names = {pl.name.lower() for pl in self._lists.values()}
        base_name = imported.name or "Imported List"
        candidate_name = base_name
        counter = 1
        while candidate_name.lower() in existing_names:
            candidate_name = f"{base_name} ({counter})"
            counter += 1
        imported.name = candidate_name

        # Ensure fresh IDs for list and its entries
        imported.id = str(uuid.uuid4())
        for entry in imported.entries:
            entry.id = str(uuid.uuid4())

        self._lists[imported.id] = imported
        self.save()
        return imported


# ── Global store accessor ─────────────────────────────────────────────────────

_STORE: PlantListStore | None = None


def get_plant_list_store(storage_path: Path | None = None) -> PlantListStore:
    """Return application-wide PlantListStore singleton."""
    global _STORE
    if _STORE is None or (storage_path is not None and _STORE.path != storage_path):
        _STORE = PlantListStore(storage_path)
    return _STORE


def reset_plant_list_store() -> None:
    """Reset the module-level singleton (useful in test teardown)."""
    global _STORE
    _STORE = None
