"""A surface's detail picture as the engine samples it (#801) — Qt-free numpy.

A roof's tiles and a wall's plaster, courses or boards are the canvas's own pictures
(``resources/textures``: the asset forge's tileable 256-px textures, no new asset): the
same picture the 2D plan paints, reduced to what a 3D surface needs on top of its own
colour — how much lighter or darker each texel is, and which way it slopes.

The texel (RGBA8, sampled raw by ``built_detail.frag``):

- **R = the albedo multiplier x ``ALBEDO_ENCODE``.** The canvas recolours a pattern to the
  item's colour by each texel's RELATIVE luminance (``fill_patterns._tint_texture``:
  ``colour x lum / mean(lum)``, in sRGB). In linear light that is the colour times
  ``s ** 2.2`` (``s = lum / mean(lum)``); the multiplier here is ``s ** 2.2`` divided by its
  own mean, so a surface's MEAN linear colour stays its vertex colour (a roof's mean at
  noon is what it was before #801) and the mipmaps take a far surface to that flat mean.
- **G, B = the height's slope along u and along v, + 0.5.** The height is the texel's
  luminance (bright = raised, as the ground's detail normals, ``ground.frag``); the slope
  is the central difference over one texel each way, wrapping round the picture's edges
  (the pictures tile), clamped to +-0.5. Mipmaps average a slope towards 0 — a far surface
  shades flat.
- **A = 255.**

Rows are the picture's own rows (row 0 = its top), so a texture coordinate (u, v) reads the
texel the canvas's brush reads at the same (x, y) = (u, v) x 256 — what lets a roof seen
from above show the plan's own tiles (``builders/roofs.py``).
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

#: R holds the multiplier times this (a multiplier up to 2.5 fits a byte).
ALBEDO_ENCODE: Final = 0.4
#: The power that takes an sRGB ratio to a linear one (the canvas tints in sRGB).
GAMMA: Final = 2.2
#: The largest slope a texel stores either way.
MAX_SLOPE: Final = 0.5


def luminance(rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
    """The canvas's own luminance of each texel (``fill_patterns._tint_texture``'s
    weights), 0-255."""
    pixels = np.asarray(rgb, dtype=np.float64)
    return 0.299 * pixels[..., 0] + 0.587 * pixels[..., 1] + 0.114 * pixels[..., 2]


def albedo_multiplier(rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Each texel's linear albedo multiplier — mean exactly 1 (module docstring)."""
    lum = luminance(rgb)
    relative = lum / max(float(lum.mean()), 1e-6)
    linear = relative ** GAMMA
    multiplier: NDArray[np.float64] = linear / max(float(linear.mean()), 1e-12)
    return multiplier


def height_slopes(rgb: NDArray[np.uint8]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The height's slope along u (columns) and along v (rows), per texel, wrapping
    round the edges: the luminance (0-1) difference over one texel each way, halved."""
    height = luminance(rgb) / 255.0
    along_u = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) / 2.0
    along_v = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) / 2.0
    return along_u, along_v


def detail_texels(rgb: NDArray[np.uint8]) -> bytes:
    """The picture ``rgb`` (rows, columns, 3; uint8) as the engine's detail texels:
    RGBA8, rows as given (module docstring)."""
    pixels = np.asarray(rgb)
    if pixels.ndim != 3 or pixels.shape[2] < 3 or pixels.shape[0] < 3 or pixels.shape[1] < 3:
        raise ValueError(f"a detail picture is (rows, columns, 3) of at least 3 x 3, got {pixels.shape}")
    pixels = pixels[..., :3]
    along_u, along_v = height_slopes(pixels)
    out = np.empty(pixels.shape[:2] + (4,), dtype=np.uint8)
    out[..., 0] = np.clip(np.rint(albedo_multiplier(pixels) * ALBEDO_ENCODE * 255.0), 0, 255)
    for channel, slope in ((1, along_u), (2, along_v)):
        out[..., channel] = np.clip(np.rint((0.5 + np.clip(slope, -MAX_SLOPE, MAX_SLOPE)) * 255.0),
                                    0, 255)
    out[..., 3] = 255
    return out.tobytes()
