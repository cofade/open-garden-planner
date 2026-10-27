"""A building's roof as additive item metadata (Phase 17 L4.1, #388, ADR-065).

Three optional keys on a ``HOUSE``, ``GARAGE_SHED`` or ``TOOL_SHED`` item's
``metadata``, set from the Properties panel (one ``ChangePropertyCommand`` each)
and read by the 3D snapshot:

- ``roof_style`` — ``"gable"``, ``"hip"``, ``"shed"`` (a mono-pitch roof) or
  ``"flat"``. Absent: AUTOMATIC — a gable along the plan's ridge where there is
  one (a HOUSE's ``ROOF_RIDGE``, a shed's long axis or its sprite's ridge), a flat
  roof on a house without one;
- ``roof_pitch_deg`` — the slope in degrees (``MIN_PITCH_DEG`` … ``MAX_PITCH_DEG``).
  Absent: the style's own (a house 38°, a shed 25°);
- ``roof_overhang_cm`` — how far the eaves reach past the walls (0 …
  ``MAX_OVERHANG_CM``). Absent: the style's own (a house 30 cm, a shed 20 cm).

Additive, like ``object_height_cm`` (ADR-037): old app versions ignore the keys,
old plans load without them (automatic), and the ``.ogp`` ``FILE_VERSION`` stays.
The 2D canvas does not read them: the plan's ridge line and its 2D sun study are
unchanged (issue #440 owns a roof-aware 2D caster).

The roof's TOP is the building's height in every style — the 2D resolver's
answer, as before (ADR-037: a building's height is its ridge height): the pitch
sets the eaves under it, never the top above them.

Qt-free and standard library only: the snapshot, the builders' tests and the
Properties panel read the same rules. A value that is not usable — a style this
module does not know, a pitch or an overhang that is not a finite number — is
treated as absent, and a pitch or an overhang out of range is clamped into it: a
hand-edited plan never fails to show.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Final

__all__ = [
    "BUILDING_KINDS", "MAX_OVERHANG_CM", "MAX_PITCH_DEG", "MIN_PITCH_DEG", "OVERHANG_KEY",
    "PITCH_KEY", "ROOF_STYLES", "STYLE_KEY", "roof_overhang_cm", "roof_pitch_deg", "roof_style",
]

STYLE_KEY: Final = "roof_style"
PITCH_KEY: Final = "roof_pitch_deg"
OVERHANG_KEY: Final = "roof_overhang_cm"

#: The roof styles, in the order the Properties panel offers them.
GABLE: Final = "gable"
HIP: Final = "hip"
SHED: Final = "shed"
FLAT: Final = "flat"
ROOF_STYLES: Final[tuple[str, ...]] = (GABLE, HIP, SHED, FLAT)

#: The ObjectType names that carry a roof.
BUILDING_KINDS: Final[frozenset[str]] = frozenset({"HOUSE", "GARAGE_SHED", "TOOL_SHED"})

#: The pitch a user can set, in degrees. Below 5° a pitched roof is a flat one;
#: above 60° the eaves of any building would sink under a door.
MIN_PITCH_DEG: Final = 5.0
MAX_PITCH_DEG: Final = 60.0
#: The longest overhang a user can set, in cm.
MAX_OVERHANG_CM: Final = 150.0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def roof_style(metadata: Mapping[str, object] | None) -> str | None:
    """The stored style, or None for automatic (absent, or a value not in
    ``ROOF_STYLES``)."""
    value = (metadata or {}).get(STYLE_KEY)
    return value if isinstance(value, str) and value in ROOF_STYLES else None


def roof_pitch_deg(metadata: Mapping[str, object] | None) -> float | None:
    """The stored pitch clamped to ``MIN_PITCH_DEG`` … ``MAX_PITCH_DEG``, or None for
    the style's own (absent, not a finite number, or not positive)."""
    value = _number((metadata or {}).get(PITCH_KEY))
    if value is None or value <= 0.0:
        return None
    return min(MAX_PITCH_DEG, max(MIN_PITCH_DEG, value))


def roof_overhang_cm(metadata: Mapping[str, object] | None) -> float | None:
    """The stored overhang clamped to 0 … ``MAX_OVERHANG_CM``, or None for the
    style's own (absent, or not a finite number)."""
    value = _number((metadata or {}).get(OVERHANG_KEY))
    if value is None:
        return None
    return min(MAX_OVERHANG_CM, max(0.0, value))
