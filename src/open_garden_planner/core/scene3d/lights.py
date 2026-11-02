"""The garden lights at night (Phase 17 L5.4, #389, ADR-070). Qt-free.

A garden light (``GARDEN_LIGHT``) or a string of lights (``STRING_LIGHTS``) is an
object of the plan with a 2D picture (the lantern's sprite; the string is a line,
``string_lights_paint``) and a 3D model (``builders/lights.py``). At dusk
its bulbs come on (``AtmosphereSpec.lamps``): every bulb GLOWS — a sprite of the
ambient buffer (``particles.ambient_buffers``, kind ``bulb``) — and the lamps nearest
to the camera's target LIGHT the garden — the scene's fixed pool of point lights
(``Garden.qml``: ``lampSlots``), because every light the engine draws costs every lit
pixel and changes every lit material's shader.

WHERE: the bulbs are the builder's own (``builders.lights.lantern_bulb`` /
``string_bulbs``), placed into the scene by the record's pose — the same pose the
engine gives the item's Model (``Transform``: east, north, rotation counter-clockwise
seen from above, base). A glow can never hang beside its bulb; the point light stands
just below the glass (``builders.lights.lamp_light``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from .builders.lights import (
    KINDS,
    lamp_light,
    lantern_bulb,
    light_height_cm,
    string_bulbs,
)
from .frame import pose_points
from .particles import MAX_BULBS, Emitter

if TYPE_CHECKING:
    from .record import Record

__all__ = ["LAMP_SLOTS", "LIGHT_KINDS", "MAX_BULBS", "LampSource", "lamp_sources",
           "nearest_lamps"]

#: The kinds whose bulbs light up at night.
LIGHT_KINDS: Final = KINDS
#: How many lamps LIGHT at once (``Garden.qml``'s ``lampSlots``; pinned by a test).
LAMP_SLOTS: Final = 6
#: The glow of one bulb, cm across: a lantern's larger than a string's.
_LANTERN_GLOW_CM: Final = 30.0
_STRING_GLOW_CM: Final = 12.0
#: A string's one light is weaker than a lantern's: many small bulbs, one point light.
_LANTERN_STRENGTH: Final = 1.0
_STRING_STRENGTH: Final = 0.7


@dataclass(frozen=True, slots=True)
class LampSource:
    """One light of the plan, scene frame (cm): where it lights from and its bulbs."""

    item_id: str
    kind: str
    #: (east, north, up, strength): where the point light of this lamp stands.
    light: tuple[float, float, float, float]
    #: Every bulb, (east, north, up).
    bulb_points: tuple[tuple[float, float, float], ...]
    glow_cm: float

    def bulbs(self) -> tuple[Emitter, ...]:
        """Its bulbs as glowing ``bulb`` particles of the ambient buffer."""
        return tuple(Emitter("bulb", self.item_id, east, north, up, up, self.glow_cm, 1)
                     for east, north, up in self.bulb_points)


def lamp_sources(records: Iterable[Record]) -> tuple[LampSource, ...]:
    """Every light of the plan, sorted by item id — at most ``MAX_BULBS`` bulbs over all
    of them (the strings beyond it light but do not glow)."""
    out: list[LampSource] = []
    budget = MAX_BULBS
    for record in sorted(records, key=lambda r: r.item_id):
        if record.kind not in LIGHT_KINDS:
            continue
        height = light_height_cm(record)
        if height is None or not height > 0.0:
            continue
        if record.kind == "GARDEN_LIGHT":
            bulb = lantern_bulb(record, height)
            points = None if bulb is None else np.array([bulb], dtype=np.float64)
            glow, strength = _LANTERN_GLOW_CM, _LANTERN_STRENGTH
        else:
            points = string_bulbs(record, height)
            glow, strength = _STRING_GLOW_CM, _STRING_STRENGTH
        anchor = lamp_light(record, height)
        if points is None or not len(points) or anchor is None:
            continue
        scene = pose_points(record.transform, points)   # the pose the Model gets
        at = pose_points(record.transform, np.array([anchor], dtype=np.float64))[0]
        light = (float(at[0]), float(at[1]), float(at[2]), strength)
        shown = scene[:max(0, budget)]
        budget -= len(shown)
        out.append(LampSource(record.item_id, record.kind, light,
                              tuple((float(p[0]), float(p[1]), float(p[2])) for p in shown), glow))
    return tuple(out)


def nearest_lamps(sources: Iterable[LampSource], target_scene: Iterable[float],
                  slots: int = LAMP_SLOTS) -> tuple[LampSource, ...]:
    """The ``slots`` lamps nearest to ``target_scene`` (east, north, up — the camera's
    target), nearest first; a tie by item id."""
    tx, ty, tz = (float(v) for v in target_scene)
    ranked = sorted(sources, key=lambda s: (math.dist(s.light[:3], (tx, ty, tz)), s.item_id))
    return tuple(ranked[:max(0, slots)])
