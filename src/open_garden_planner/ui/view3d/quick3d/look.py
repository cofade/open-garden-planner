"""The look of a frame as plain data — and the ONE look L1.2 has (ADR-048). Engine-free.

A ``Look`` is everything about a frame that is art direction and not truth: the
colour and strength of the key light, the fill, the exposure, the sky. What is
truth — where the sun stands, how high a wall is — never lives here; it comes
from ``core/solar`` and the records.

L1.2 ships ``NEUTRAL_DAY`` only: the L0 spike's measured noon rig
(``ogp-lush-cinematic`` §3), a plain sky colour and no image-based light probe.
The moods by sun elevation, the procedural sky, fog and the night rig are L1.4,
which passes its own ``Look`` values to ``Quick3DHost.set_look``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final

_HEX: Final = re.compile(r"#[0-9a-fA-F]{6}")


def linear_to_srgb_hex(rgb: tuple[float, float, float]) -> str:
    """Linear rgb (clamped to 0..1) → ``#rrggbb`` — the inverse of
    ``core.scene3d.srgb_to_linear`` (IEC 61966-2-1), to 8 bits."""
    channels = []
    for value in rgb:
        clamped = min(max(value, 0.0), 1.0)
        encoded = 12.92 * clamped if clamped <= 0.0031308 else 1.055 * clamped ** (1 / 2.4) - 0.055
        channels.append(round(encoded * 255.0))
    return "#{:02x}{:02x}{:02x}".format(*channels)


@dataclass(frozen=True, slots=True)
class Look:
    """One mood. Colours are ``#rrggbb`` sRGB unless the name says ``_linear``."""

    #: Colour and brightness of the key light — the sun's LOOK; its direction is
    #: ``SunState`` and comes from ``core/solar``.
    sun_color: str
    sun_brightness: float
    #: Flat fill light in LINEAR rgb, added to every surface: it stands in for the
    #: sky's diffuse light until L1.4 lights the scene with the sky itself. A SEAM,
    #: not a look decision that pre-empts L1.4: L1.4 extends ``Look`` (sky, fog,
    #: probe exposure, night) and removes this field together with the
    #: brightness-0 fill light in ``Garden.qml``.
    fill_linear: tuple[float, float, float]
    #: Exposure of the tone-mapped (perspective) view.
    exposure: float
    #: The plain background colour (L1.4: the procedural sky replaces it).
    sky_color: str
    #: Albedo of the endless meadow and of plan ground no item covers — ONE value,
    #: shared with the ground bake (L1.5), or the plan reads as an island.
    meadow_albedo: str
    #: Amplitude of the foliage and grass sway, in the shaders' units. The wind
    #: only moves while an animation drives the scene's clock (L1.4).
    wind_strength: float = 2.5

    def __post_init__(self) -> None:
        for name in ("sun_color", "sky_color", "meadow_albedo"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise ValueError(f"Look.{name} must be '#rrggbb', got {value!r}")
        for name in ("sun_brightness", "wind_strength"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"Look.{name} must be a finite, non-negative number, got {value!r}")
        if not math.isfinite(self.exposure) or self.exposure <= 0.0:
            raise ValueError(f"Look.exposure must be a positive number, got {self.exposure!r}")
        fill = tuple(self.fill_linear)
        if len(fill) != 3 or not all(math.isfinite(v) and v >= 0.0 for v in fill):
            raise ValueError(
                f"Look.fill_linear must be three finite, non-negative numbers, got {self.fill_linear!r}")

    @property
    def fill_color(self) -> str:
        """``fill_linear`` as the ``#rrggbb`` the engine's light takes (it linearises
        colour properties itself)."""
        return linear_to_srgb_hex(self.fill_linear)


#: The L0 spike's noon anchor (``spike_q3d/runner.py``: ``SUN_NOON``,
#: ``LOOK_NOON``, ``MEADOW_ALBEDO``), pinned against it by a drift-guard test
#: until the spike retires (L1.10).
#:
#: ``fill_linear`` is derived, not chosen: the spike filled its shadows with the
#: sky's light probe at exposure 0.55; a flat fill of the same energy is the mean
#: of the noon sky's top (``#3f78c9``) and horizon (``#cfe2f2``) in linear light,
#: times 0.55.
NEUTRAL_DAY: Final = Look(
    sun_color="#fff1dc",
    sun_brightness=1.9,
    fill_linear=(0.1853, 0.2608, 0.4048),
    exposure=0.85,
    sky_color="#cfe2f2",
    meadow_albedo="#487f34",
)
