"""sRGB → linear light, the one conversion of the 3D pipeline (Phase 17 L1.1).

Vertex colours and material tints reach the engine in LINEAR light (the engine
does not sRGB-decode vertex colours — ``ogp-3d-renderer`` §3), while every
colour in the plan and in the 2D palettes is 8-bit sRGB. Ported from the L0
spike's ``meshes.srgb_to_linear``; a drift-guard test compares the two until the
spike retires (L1.10).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Rgba = tuple[int, int, int, int]


def srgb_channel_to_linear(value: float) -> float:
    """One sRGB channel in 0..1 → linear light (IEC 61966-2-1)."""
    if value <= 0.04045:
        return value / 12.92
    return float(((value + 0.055) / 1.055) ** 2.4)


def srgb8_to_linear(rgba: Rgba) -> tuple[float, float, float, float]:
    """8-bit sRGB ``(r, g, b, a)`` → linear ``(r, g, b)`` with a plain 0..1 alpha."""
    r, g, b, a = rgba
    return (
        srgb_channel_to_linear(r / 255.0),
        srgb_channel_to_linear(g / 255.0),
        srgb_channel_to_linear(b / 255.0),
        a / 255.0,
    )


def srgb_to_linear(hex_color: str) -> NDArray[np.float32]:
    """``#rrggbb`` → linear RGB float32, shape (3,) — the builders' palette entry point."""
    if len(hex_color) != 7 or hex_color[0] != "#":
        raise ValueError(f"expected '#rrggbb', got {hex_color!r}")
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    return np.array([srgb_channel_to_linear(c) for c in channels], dtype=np.float32)
