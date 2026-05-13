"""Garden journal map-linked notes data model (US-12.9).

Free-standing canvas pins. Each note carries a date, multi-line text, an
optional photo, and the scene coordinates where its pin sits. Notes are
serialised under the top-level ``garden_journal_notes`` key in the .ogp
file as ``{note_id: JournalNote.to_dict()}`` — flat, keyed by the note's
own UUID rather than by a target bed (unlike :mod:`pest_log`).

The canvas-side ``JournalPinItem`` carries only the ``note_id`` reference;
the note body lives here so the sidebar panel and the PDF "Garden Notes"
page can iterate them without scanning the scene.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JournalNote:
    """A single garden-journal entry pinned to a canvas location."""

    date: str = ""                       # ISO 8601, e.g. "2026-05-13"
    text: str = ""                       # plain multi-line body
    # Path to the attached photo, RELATIVE to the project's directory so
    # the project file remains portable. ``None`` when no photo is attached.
    photo_path: str | None = None
    # Scene coordinates of the pin (canvas centimetres).
    scene_x: float = 0.0
    scene_y: float = 0.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serialisable dict, omitting empty optional fields."""
        d: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "text": self.text,
            "scene_x": self.scene_x,
            "scene_y": self.scene_y,
        }
        if self.photo_path is not None:
            d["photo_path"] = self.photo_path
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalNote:
        """Deserialise from dict (forgiving — missing fields fall back to defaults)."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            date=data.get("date", ""),
            text=data.get("text", ""),
            photo_path=data.get("photo_path"),
            scene_x=float(data.get("scene_x", 0.0)),
            scene_y=float(data.get("scene_y", 0.0)),
        )


__all__ = ["JournalNote"]
