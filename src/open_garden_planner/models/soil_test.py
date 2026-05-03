"""Soil test data model (US-12.10a).

Records per-bed (or project-wide default) soil tests using the Rapitest
categorical scale, with optional ppm values for lab-mode entries.

NPK / secondary-nutrient scale (matches Rapitest kit):
    N: 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus
    P: 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus
    K: 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus  (no K0)
    Ca/Mg/S: 0=Low, 1=Medium, 2=High

Storage: serialised under top-level ``soil_tests`` key in the .ogp file as
``{target_id: SoilTestHistory.to_dict()}`` where ``target_id`` is a bed UUID
or the literal string ``"global"`` for the project-wide default.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SoilTestRecord:
    """A single soil test entry.

    Categorical fields (n_level/p_level/k_level/ca_level/mg_level/s_level)
    use the Rapitest kit scale; the optional ``*_ppm`` companions hold raw
    lab-report values when the test was entered in Lab mode. Conversion
    between the two is left to a later sub-story (US-12.10c).
    """

    date: str = ""                       # ISO 8601, e.g. "2026-04-25"
    ph: float | None = None
    # Rapitest categorical levels
    n_level: int | None = None           # 0–4
    p_level: int | None = None           # 0–4
    k_level: int | None = None           # 1–4
    ca_level: int | None = None          # 0–2
    mg_level: int | None = None          # 0–2
    s_level: int | None = None           # 0–2
    # Optional lab-mode parts-per-million readings
    n_ppm: float | None = None
    p_ppm: float | None = None
    k_ppm: float | None = None
    ca_ppm: float | None = None
    mg_ppm: float | None = None
    s_ppm: float | None = None
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting None / empty optionals."""
        d: dict[str, Any] = {"id": self.id, "date": self.date}
        for key in (
            "ph",
            "n_level", "p_level", "k_level",
            "ca_level", "mg_level", "s_level",
            "n_ppm", "p_ppm", "k_ppm",
            "ca_ppm", "mg_ppm", "s_ppm",
        ):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SoilTestRecord:
        """Deserialise from dict (forgiving — missing fields default to None/'')."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            ph=data.get("ph"),
            n_level=data.get("n_level"),
            p_level=data.get("p_level"),
            k_level=data.get("k_level"),
            ca_level=data.get("ca_level"),
            mg_level=data.get("mg_level"),
            s_level=data.get("s_level"),
            n_ppm=data.get("n_ppm"),
            p_ppm=data.get("p_ppm"),
            k_ppm=data.get("k_ppm"),
            ca_ppm=data.get("ca_ppm"),
            mg_ppm=data.get("mg_ppm"),
            s_ppm=data.get("s_ppm"),
            notes=data.get("notes", ""),
        )


@dataclass
class SoilTestHistory:
    """All soil tests recorded for one target (a bed UUID or ``"global"``)."""

    target_id: str
    records: list[SoilTestRecord] = field(default_factory=list)

    @property
    def latest(self) -> SoilTestRecord | None:
        """Return the most recently dated record, or None if empty."""
        if not self.records:
            return None
        return max(self.records, key=lambda r: r.date)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict."""
        return {
            "target_id": self.target_id,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SoilTestHistory:
        """Deserialise from dict."""
        return cls(
            target_id=data.get("target_id", ""),
            records=[SoilTestRecord.from_dict(r) for r in data.get("records", [])],
        )
