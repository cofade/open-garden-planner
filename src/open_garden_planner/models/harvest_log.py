"""Harvest tracking / yield log data model (US-C1, epic #188).

Records harvest events per plant (or bed) — amount, unit, quality and notes —
so gardeners can review per-species yields and compare totals year over year.
Storage mirrors :mod:`pest_log`: serialised under the top-level ``harvest_logs``
key in the .ogp file as ``{target_id: HarvestHistory.to_dict()}`` where
``target_id`` is a plant or bed UUID.

The history additionally caches ``species_key`` + ``species_name`` (captured
from the target item at log time). This keeps the garden-wide aggregation
Qt-free and robust: totals resolve from the stored key even after the plant
item is deleted or carried into a new season without its objects.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HarvestRecord:
    """A single harvest event for one target (plant or bed)."""

    date: str = ""                       # ISO 8601, e.g. "2026-06-24"
    quantity: float = 0.0                # amount harvested (>= 0)
    unit: str = "kg"                     # "g" | "kg" | "pcs" | "bunch" | "L" | …
    quality: str = ""                    # free text, e.g. "excellent, sweet"
    notes: str = ""
    # Path to the attached photo, RELATIVE to the project's directory so the
    # project file stays portable. ``None`` when no photo is attached.
    photo_path: str | None = None
    # Id of the pin-less garden-journal note auto-created for this harvest
    # (US-C1 journal link). ``None`` when no linked note exists.
    journal_note_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting empty optional fields."""
        d: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "quantity": self.quantity,
            "unit": self.unit,
        }
        if self.quality:
            d["quality"] = self.quality
        if self.notes:
            d["notes"] = self.notes
        if self.photo_path is not None:
            d["photo_path"] = self.photo_path
        if self.journal_note_id is not None:
            d["journal_note_id"] = self.journal_note_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarvestRecord:
        """Deserialise from dict (forgiving — missing fields fall back to defaults)."""
        try:
            quantity = float(data.get("quantity", 0.0))
        except (TypeError, ValueError):
            quantity = 0.0
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            quantity=quantity,
            unit=data.get("unit", "kg"),
            quality=data.get("quality", ""),
            notes=data.get("notes", ""),
            photo_path=data.get("photo_path"),
            journal_note_id=data.get("journal_note_id"),
        )


@dataclass
class HarvestHistory:
    """All harvest records recorded for one target (plant or bed UUID).

    ``species_key`` / ``species_name`` cache the target's identity at log time
    so garden-wide aggregation needn't reach back into the live scene.
    """

    target_id: str
    records: list[HarvestRecord] = field(default_factory=list)
    species_key: str = ""
    species_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting empty cache fields."""
        d: dict[str, Any] = {
            "target_id": self.target_id,
            "records": [r.to_dict() for r in self.records],
        }
        if self.species_key:
            d["species_key"] = self.species_key
        if self.species_name:
            d["species_name"] = self.species_name
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarvestHistory:
        """Deserialise from dict."""
        return cls(
            target_id=data.get("target_id", ""),
            records=[HarvestRecord.from_dict(r) for r in data.get("records", [])],
            species_key=data.get("species_key", ""),
            species_name=data.get("species_name", ""),
        )


__all__ = ["HarvestRecord", "HarvestHistory"]
