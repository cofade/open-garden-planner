"""Pest and disease log data model (US-12.7).

Records pest sightings and disease outbreaks per bed and per plant, with
treatment notes and optional photo attachments. Storage: serialised under
top-level ``pest_disease_logs`` key in the .ogp file as
``{target_id: PestLogHistory.to_dict()}`` where ``target_id`` is a bed or
plant UUID.

Severity scale: ``"low" | "medium" | "high"`` — kept categorical so the
overview panel can rank entries quickly without numeric thresholds.

Carryover semantics: when a new season is created, ``resolved=False``
records are copied to the new season file (so a permanent tree pest such
as borers stays visible). Resolved records remain in the previous season
file as historical record only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PestLogRecord:
    """A single pest or disease log entry."""

    date: str = ""                       # ISO 8601, e.g. "2026-04-25"
    entry_type: str = "pest"             # "pest" | "disease"
    name: str = ""                       # e.g. "Aphids", "Powdery mildew"
    severity: str = "low"                # "low" | "medium" | "high"
    treatment: str = ""                  # e.g. "Neem oil spray, weekly"
    notes: str = ""
    # Path to the attached photo, RELATIVE to the project's directory so the
    # project file remains portable. ``None`` when no photo is attached.
    photo_path: str | None = None
    # Whether the issue has been resolved. Drives both the overview-panel
    # filter and the new-season carryover (unresolved records carry over).
    resolved: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting empty optional fields."""
        d: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "entry_type": self.entry_type,
            "name": self.name,
            "severity": self.severity,
            "resolved": self.resolved,
        }
        if self.treatment:
            d["treatment"] = self.treatment
        if self.notes:
            d["notes"] = self.notes
        if self.photo_path is not None:
            d["photo_path"] = self.photo_path
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PestLogRecord:
        """Deserialise from dict (forgiving — missing fields fall back to defaults)."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            entry_type=data.get("entry_type", "pest"),
            name=data.get("name", ""),
            severity=data.get("severity", "low"),
            treatment=data.get("treatment", ""),
            notes=data.get("notes", ""),
            photo_path=data.get("photo_path"),
            resolved=bool(data.get("resolved", False)),
        )


@dataclass
class PestLogHistory:
    """All pest/disease log entries recorded for one target (bed or plant UUID)."""

    target_id: str
    records: list[PestLogRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict."""
        return {
            "target_id": self.target_id,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PestLogHistory:
        """Deserialise from dict."""
        return cls(
            target_id=data.get("target_id", ""),
            records=[PestLogRecord.from_dict(r) for r in data.get("records", [])],
        )
