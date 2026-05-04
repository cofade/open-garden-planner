"""Pest & disease log data model (US-12.7).

Records per-bed or per-plant pest sightings and disease outbreaks with date,
type (pest|disease), name, severity, treatment notes, an optional photo
(base64-encoded JPEG), and an optional ``resolved_date`` that turns the entry
inactive once filled.

Storage: serialised under top-level ``pest_disease_logs`` key in the .ogp
file as ``{target_id: PestDiseaseLog.to_dict()}`` where ``target_id`` is the
UUID of either a bed-shaped item (rectangle/ellipse/polygon with bed
``object_type``) or a plant ``CircleItem``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

PestKind = Literal["pest", "disease"]
Severity = Literal["low", "medium", "high"]

KIND_VALUES: tuple[PestKind, ...] = ("pest", "disease")
SEVERITY_VALUES: tuple[Severity, ...] = ("low", "medium", "high")


@dataclass
class PestDiseaseRecord:
    """A single pest sighting or disease outbreak entry."""

    date: str = ""                       # ISO 8601, e.g. "2026-05-04"
    kind: PestKind = "pest"
    name: str = ""                       # e.g. "Aphid", "Powdery mildew"
    severity: Severity = "low"
    treatment: str = ""
    resolved_date: str | None = None     # ISO 8601 once resolved; None = active
    photo_base64: str | None = None      # JPEG bytes, base64-encoded
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def is_active(self) -> bool:
        """True while ``resolved_date`` has not been set."""
        return self.resolved_date is None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting None / empty optionals."""
        d: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "kind": self.kind,
            "name": self.name,
            "severity": self.severity,
        }
        if self.treatment:
            d["treatment"] = self.treatment
        if self.resolved_date is not None:
            d["resolved_date"] = self.resolved_date
        if self.photo_base64:
            d["photo_base64"] = self.photo_base64
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PestDiseaseRecord:
        """Deserialise from dict (forgiving — unknown values fall back to defaults)."""
        kind = data.get("kind", "pest")
        if kind not in KIND_VALUES:
            kind = "pest"
        severity = data.get("severity", "low")
        if severity not in SEVERITY_VALUES:
            severity = "low"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            kind=kind,
            name=data.get("name", ""),
            severity=severity,
            treatment=data.get("treatment", ""),
            resolved_date=data.get("resolved_date"),
            photo_base64=data.get("photo_base64"),
            notes=data.get("notes", ""),
        )


@dataclass
class PestDiseaseLog:
    """All pest/disease records logged for one target (bed or plant UUID)."""

    target_id: str
    records: list[PestDiseaseRecord] = field(default_factory=list)

    @property
    def latest(self) -> PestDiseaseRecord | None:
        """Return the most recently dated record, or None if empty."""
        if not self.records:
            return None
        return max(self.records, key=lambda r: r.date)

    @property
    def active(self) -> list[PestDiseaseRecord]:
        """Return only active records (``resolved_date is None``), newest first."""
        return sorted(
            (r for r in self.records if r.is_active),
            key=lambda r: r.date,
            reverse=True,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict."""
        return {
            "target_id": self.target_id,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PestDiseaseLog:
        """Deserialise from dict."""
        return cls(
            target_id=data.get("target_id", ""),
            records=[PestDiseaseRecord.from_dict(r) for r in data.get("records", [])],
        )
