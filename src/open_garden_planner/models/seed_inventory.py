"""Seed inventory data model for tracking seed packets.

Implements US-9.1: SeedPacket dataclass with viability calculation and
SeedInventoryStore for persisting the global (cross-project) inventory.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ViabilityStatus(Enum):
    """Calculated viability status for a seed packet."""

    GOOD = "good"               # Within normal shelf life
    REDUCED = "reduced"         # Past peak viability but still usable
    EXPIRED = "expired"         # Beyond expected shelf life
    UNKNOWN = "unknown"         # No shelf-life data available


@dataclass
class SeedPacket:
    """A single seed packet in the user's inventory.

    All string fields default to "" so that freshly-created packets with
    partial data are still fully serializable.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # ── Species link ──────────────────────────────────────────────────────────
    species_id: str | None = None        # scientific_name from PlantSpeciesData
    species_name: str = ""               # display name / fallback
    variety: str = ""

    # ── Provenance ────────────────────────────────────────────────────────────
    purchase_year: int = 2024
    manufacturer: str = ""
    batch_number: str = ""

    # ── Quantity ──────────────────────────────────────────────────────────────
    quantity: float = 0.0
    quantity_unit: str = "seeds"         # "seeds" | "grams"

    # ── Germination conditions ────────────────────────────────────────────────
    germination_temp_min_c: float | None = None
    germination_temp_opt_c: float | None = None
    germination_temp_max_c: float | None = None
    germination_days_min: int | None = None
    germination_days_max: int | None = None

    # True = light germinator, False = dark, None = indifferent
    light_germinator: bool | None = None

    # ── Pre-treatment ─────────────────────────────────────────────────────────
    cold_stratification: bool = False
    stratification_days: int | None = None
    pre_treatment: str = ""              # scarification, soaking, etc.

    # ── Extra ─────────────────────────────────────────────────────────────────
    notes: str = ""
    photo_path: str = ""                 # absolute or project-relative path
    created_date: str = ""              # ISO date string (YYYY-MM-DD)

    # ──────────────────────────────────────────────────────────────────────────

    def viability_status(self, current_year: int, db: SeedViabilityDB) -> ViabilityStatus:
        """Return the calculated viability status for this packet.

        Args:
            current_year: The year to calculate age against (usually today's year).
            db: Loaded SeedViabilityDB instance.

        Returns:
            ViabilityStatus enum value.
        """
        age = current_year - self.purchase_year
        if age < 0:
            return ViabilityStatus.GOOD

        entry = db.lookup(self.species_name)
        if entry is None:
            return ViabilityStatus.UNKNOWN

        shelf_life = entry.get("shelf_life_years", 0)
        reduced_after = entry.get("reduced_after_years", shelf_life)

        if age >= shelf_life:
            return ViabilityStatus.EXPIRED
        if age >= reduced_after:
            return ViabilityStatus.REDUCED
        return ViabilityStatus.GOOD

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        d: dict[str, Any] = {
            "id": self.id,
            "species_name": self.species_name,
            "purchase_year": self.purchase_year,
            "quantity": self.quantity,
            "quantity_unit": self.quantity_unit,
            "cold_stratification": self.cold_stratification,
        }
        # Omit falsy optionals to keep files compact
        if self.species_id:
            d["species_id"] = self.species_id
        if self.variety:
            d["variety"] = self.variety
        if self.manufacturer:
            d["manufacturer"] = self.manufacturer
        if self.batch_number:
            d["batch_number"] = self.batch_number
        if self.germination_temp_min_c is not None:
            d["germination_temp_min_c"] = self.germination_temp_min_c
        if self.germination_temp_opt_c is not None:
            d["germination_temp_opt_c"] = self.germination_temp_opt_c
        if self.germination_temp_max_c is not None:
            d["germination_temp_max_c"] = self.germination_temp_max_c
        if self.germination_days_min is not None:
            d["germination_days_min"] = self.germination_days_min
        if self.germination_days_max is not None:
            d["germination_days_max"] = self.germination_days_max
        if self.light_germinator is not None:
            d["light_germinator"] = self.light_germinator
        if self.stratification_days is not None:
            d["stratification_days"] = self.stratification_days
        if self.pre_treatment:
            d["pre_treatment"] = self.pre_treatment
        if self.notes:
            d["notes"] = self.notes
        if self.photo_path:
            d["photo_path"] = self.photo_path
        if self.created_date:
            d["created_date"] = self.created_date
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedPacket:
        """Deserialise from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            species_id=data.get("species_id"),
            species_name=data.get("species_name", ""),
            variety=data.get("variety", ""),
            purchase_year=data.get("purchase_year", 2024),
            manufacturer=data.get("manufacturer", ""),
            batch_number=data.get("batch_number", ""),
            quantity=data.get("quantity", 0.0),
            quantity_unit=data.get("quantity_unit", "seeds"),
            germination_temp_min_c=data.get("germination_temp_min_c"),
            germination_temp_opt_c=data.get("germination_temp_opt_c"),
            germination_temp_max_c=data.get("germination_temp_max_c"),
            germination_days_min=data.get("germination_days_min"),
            germination_days_max=data.get("germination_days_max"),
            light_germinator=data.get("light_germinator"),
            cold_stratification=data.get("cold_stratification", False),
            stratification_days=data.get("stratification_days"),
            pre_treatment=data.get("pre_treatment", ""),
            notes=data.get("notes", ""),
            photo_path=data.get("photo_path", ""),
            created_date=data.get("created_date", ""),
        )


# ── Viability database ─────────────────────────────────────────────────────────

class SeedViabilityDB:
    """Bundled database mapping species/families to seed shelf life.

    Loaded from ``resources/data/seed_viability.json``.  Lookups first try
    an exact match on common name (lowercase), then fall back to the plant
    family name, then return None.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._by_species: dict[str, dict[str, int]] = data.get("by_species", {})
        self._by_family: dict[str, dict[str, int]] = data.get("by_family", {})

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> SeedViabilityDB:
        """Load the database from a JSON file."""
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedViabilityDB:
        """Create directly from a dict (useful for tests)."""
        return cls(data)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def lookup(
        self,
        species_name: str,
        family: str | None = None,
    ) -> dict[str, int] | None:
        """Return shelf-life entry or None if not found.

        Tries (in order):
        1. ``species_name`` lowercased against ``by_species`` keys (exact)
        2. Any ``by_species`` key that appears as a substring of ``species_name``
        3. ``family`` (botanical family name) against ``by_family`` keys
        """
        key = species_name.lower().strip()

        # Exact species match
        if key in self._by_species:
            return self._by_species[key]

        # Substring match (e.g. "Cherry Tomato" → "tomato" key)
        for species_key, entry in self._by_species.items():
            if species_key in key or key in species_key:
                return entry

        # Family fallback
        if family:
            entry = self._by_family.get(family)
            if entry is not None:
                return entry

        return None

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def species_count(self) -> int:
        """Number of species entries in the database."""
        return len(self._by_species)

    @property
    def family_count(self) -> int:
        """Number of family entries in the database."""
        return len(self._by_family)


# ── Global inventory store ─────────────────────────────────────────────────────

class SeedInventoryStore:
    """Manages the user's global seed inventory (cross-project).

    Packets are stored as a list in ``get_app_data_dir()/seed_inventory.json``.
    The store is not a singleton — callers obtain a fresh instance via
    ``get_seed_inventory()`` which caches it at module level.
    """

    FILENAME = "seed_inventory.json"

    def __init__(self, storage_path: Path) -> None:
        self._path = storage_path
        self._packets: dict[str, SeedPacket] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw: list[dict[str, Any]] = json.load(fh)
            for item in raw:
                packet = SeedPacket.from_dict(item)
                self._packets[packet.id] = packet
        except Exception:  # noqa: BLE001
            pass  # Corrupt / missing file — start empty

    def save(self) -> None:
        """Persist the inventory to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        packets_list = sorted(
            self._packets.values(), key=lambda p: (p.species_name, p.id)
        )
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump([p.to_dict() for p in packets_list], fh, indent=2)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, packet: SeedPacket) -> None:
        """Add or replace a packet (keyed by packet.id)."""
        self._packets[packet.id] = packet

    def remove(self, packet_id: str) -> bool:
        """Remove a packet by ID.  Returns True if it existed."""
        return self._packets.pop(packet_id, None) is not None

    def get(self, packet_id: str) -> SeedPacket | None:
        """Return packet by ID, or None."""
        return self._packets.get(packet_id)

    def all(self) -> list[SeedPacket]:
        """Return all packets sorted by species name then ID."""
        return sorted(self._packets.values(), key=lambda p: (p.species_name, p.id))

    def __len__(self) -> int:
        return len(self._packets)


# ── Module-level accessor ──────────────────────────────────────────────────────

_store: SeedInventoryStore | None = None


def get_seed_inventory() -> SeedInventoryStore:
    """Return the application-wide seed inventory (loaded lazily)."""
    global _store
    if _store is None:
        from open_garden_planner.services.plant_library import get_app_data_dir

        _store = SeedInventoryStore(get_app_data_dir() / SeedInventoryStore.FILENAME)
    return _store


def get_viability_db() -> SeedViabilityDB:
    """Load and return the bundled seed viability database."""
    data_path = (
        Path(__file__).parent.parent
        / "resources"
        / "data"
        / "seed_viability.json"
    )
    return SeedViabilityDB.load(data_path)
