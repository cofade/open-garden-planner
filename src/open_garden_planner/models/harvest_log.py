"""Harvest log data model (US-C1, issue #188).

Records harvest amounts per crop (plant) — and per bed where plants are
children — so a gardener can review per-plant history and compare yields
year-over-year. Storage: serialised under the top-level ``harvest_logs`` key
in the .ogp file as ``{target_id: HarvestLogHistory.to_dict()}`` where
``target_id`` is a plant or bed UUID.

Mirrors the pest/disease log (US-12.7, ``models/pest_log.py``) at every layer.

Carryover semantics differ from the pest log: harvest entries are a permanent
dated record (each carries an ISO date whose year drives the year-over-year
totals), so they are **not** filtered on a new-season rollover — every entry is
kept and grouped by ``HarvestEntry.date[:4]`` for per-year totals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HarvestEntry:
    """A single harvest record for one crop."""

    date: str = ""                       # ISO 8601, e.g. "2026-06-15"
    quantity: float = 0.0                # harvest amount in ``unit``
    unit: str = "g"                      # "g" | "kg" | "pcs" | "bunches" | …
    quality: str = ""                    # free-text quality note
    notes: str = ""
    # Path to the attached photo, RELATIVE to the project's directory so the
    # project file stays portable. ``None`` when no photo is attached.
    photo_path: str | None = None
    # Id of the journal note auto-created for this harvest (US-12.9 link), so
    # the note can be removed when the harvest entry is undone/deleted.
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
    def from_dict(cls, data: dict[str, Any]) -> HarvestEntry:
        """Deserialise from dict (forgiving — missing fields fall back to defaults)."""
        try:
            quantity = float(data.get("quantity", 0.0))
        except (TypeError, ValueError):
            quantity = 0.0
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            quantity=quantity,
            unit=data.get("unit", "g"),
            quality=data.get("quality", ""),
            notes=data.get("notes", ""),
            photo_path=data.get("photo_path"),
            journal_note_id=data.get("journal_note_id"),
        )

    @property
    def year(self) -> int | None:
        """The harvest year parsed from ``date`` (``None`` when unparseable)."""
        if len(self.date) >= 4 and self.date[:4].isdigit():
            return int(self.date[:4])
        return None


@dataclass
class HarvestLogHistory:
    """All harvest entries recorded for one target (plant or bed UUID)."""

    target_id: str
    entries: list[HarvestEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict."""
        return {
            "target_id": self.target_id,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarvestLogHistory:
        """Deserialise from dict."""
        return cls(
            target_id=data.get("target_id", ""),
            entries=[HarvestEntry.from_dict(e) for e in data.get("entries", [])],
        )
