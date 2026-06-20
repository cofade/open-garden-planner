"""Manual task data model (US-C2 — task management).

A :class:`ManualTask` is a free-text to-do item the user adds by hand, with an
optional due date and bed link. It complements the *generated* tasks produced by
:mod:`open_garden_planner.services.task_generator` (calendar, propagation,
succession, soil, frost), which are derived from project data and never stored
directly. Manual tasks, by contrast, are user-authored and persisted under a
top-level ``manual_tasks`` key in the .ogp file as a list of
``ManualTask.to_dict()``.

Serialisation mirrors :class:`open_garden_planner.models.pest_log.PestLogRecord`:
empty optional fields are omitted from ``to_dict()`` and ``from_dict()`` is
forgiving (missing keys fall back to defaults).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ManualTask:
    """A single user-authored to-do item."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    date: str = ""                   # ISO 8601 due date, e.g. "2026-04-25"; "" = undated
    title: str = ""
    notes: str = ""
    bed_id: str | None = None        # optional link to a bed UUID

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting empty optional fields."""
        d: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "title": self.title,
        }
        if self.notes:
            d["notes"] = self.notes
        if self.bed_id is not None:
            d["bed_id"] = self.bed_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManualTask:
        """Deserialise from dict (forgiving — missing fields fall back to defaults)."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            title=data.get("title", ""),
            notes=data.get("notes", ""),
            bed_id=data.get("bed_id"),
        )
