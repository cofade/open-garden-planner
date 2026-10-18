"""Fill pattern definitions and texture loading for object styling.

Loads tileable PNG textures from resources/textures/ and recolours each one to
the item's fill colour to create QBrush objects for rendering garden items.
"""

from enum import Enum, auto
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtGui import QBrush, QColor, QImage, QPixmap

# Directory containing texture PNG files
_TEXTURES_DIR = Path(__file__).parent.parent / "resources" / "textures"

# Cache for loaded base texture pixmaps (pattern -> QPixmap)
_texture_cache: dict["FillPattern", QPixmap] = {}

# Cache for tinted texture pixmaps (pattern, color_key -> QPixmap)
_tinted_cache: dict[tuple["FillPattern", int], QPixmap] = {}

# Maximum number of tinted texture cache entries before clearing
_TINTED_CACHE_MAX = 200


class FillPattern(Enum):
    """Available fill patterns for objects."""

    SOLID = auto()  # Solid color fill
    GRASS = auto()  # Grass texture
    GRAVEL = auto()  # Gravel/stone texture
    CONCRETE = auto()  # Concrete texture
    WOOD = auto()  # Wood grain texture
    WATER = auto()  # Water texture
    SOIL = auto()  # Soil/dirt texture
    MULCH = auto()  # Mulch texture
    ROOF_TILES = auto()  # Roof tile texture
    SAND = auto()  # Sand texture
    STONE = auto()  # Stone paving texture
    GLASS = auto()  # Glass pane / greenhouse texture
    HEDGE = auto()  # Dense foliage / hedge texture
    BRICK = auto()  # Running bond brick pattern
    BARK = auto()  # Tree bark texture
    WILDFLOWER = auto()  # Wildflower meadow
    TERRACOTTA = auto()  # Terracotta tiles
    PEBBLES = auto()  # River pebbles
    SLATE = auto()  # Slate slabs
    LATTICE = auto()  # Trellis / lattice pattern
    COMPOST = auto()  # Composted soil
    FLAGSTONE = auto()  # Irregular flagstone paving
    CLAY = auto()  # Clay surface
    DECKING = auto()  # Weathered timber decking boards (US-E9 asset forge)
    CORTEN = auto()  # Corten (weathering) steel (US-E9 asset forge)


# Mapping from FillPattern to texture filename (without .png)
_TEXTURE_FILES: dict[FillPattern, str] = {
    FillPattern.GRASS: "grass",
    FillPattern.GRAVEL: "gravel",
    FillPattern.CONCRETE: "concrete",
    FillPattern.WOOD: "wood",
    FillPattern.WATER: "water",
    FillPattern.SOIL: "soil",
    FillPattern.MULCH: "mulch",
    FillPattern.ROOF_TILES: "roof_tiles",
    FillPattern.SAND: "sand",
    FillPattern.STONE: "stone",
    FillPattern.GLASS: "glass",
    FillPattern.HEDGE: "hedge",
    FillPattern.BRICK: "brick",
    FillPattern.BARK: "bark",
    FillPattern.WILDFLOWER: "wildflower",
    FillPattern.TERRACOTTA: "terracotta",
    FillPattern.PEBBLES: "pebbles",
    FillPattern.SLATE: "slate",
    FillPattern.LATTICE: "lattice",
    FillPattern.COMPOST: "compost",
    FillPattern.FLAGSTONE: "flagstone",
    FillPattern.CLAY: "clay",
    FillPattern.DECKING: "decking",
    FillPattern.CORTEN: "corten",
}


def _load_texture(pattern: FillPattern) -> QPixmap | None:
    """Load a texture PNG from disk, with caching.

    Args:
        pattern: The fill pattern to load the texture for

    Returns:
        QPixmap of the texture, or None if not found
    """
    if pattern in _texture_cache:
        return _texture_cache[pattern]

    filename = _TEXTURE_FILES.get(pattern)
    if filename is None:
        return None

    texture_path = _TEXTURES_DIR / f"{filename}.png"
    if not texture_path.exists():
        return None

    pixmap = QPixmap(str(texture_path))
    if pixmap.isNull():
        return None

    _texture_cache[pattern] = pixmap
    return pixmap


def _color_key(color: QColor) -> int:
    """Create an integer key from a QColor for cache lookup."""
    return color.rgba()


def _tint_texture(texture: QPixmap, color: QColor) -> QPixmap:
    """Recolour a texture to the user's colour, keeping its detail (issues #502).

    Maps every pixel to the user's colour scaled by the texture's **relative**
    luminance (``pixel_luminance / mean_luminance``). That gives:

    * **hue = the user's colour** everywhere — a light-green fill over the brown
      roof-tile texture is green tiles, not brown ones;
    * **detail and relative contrast preserved exactly** — the result's
      coefficient of variation equals the texture's, so the tint never flattens
      it;
    * **brightness preserved on average** — the mean maps onto the colour.

    It replaces an overlay of the colour at 80/255 (31 %) over the texture. That
    wash could not recolour a strongly coloured texture at all: the owner's
    light-green fill over the roof tiles measured ``#ca6846`` -> ``#b8925d``,
    i.e. the "standard roof tile colour" the owner reported, and raising the
    wash enough to read (160/255) flattened the low-contrast textures (SAND
    luminance std 1.62 against a 2.0 floor). The colour's alpha still sets the
    overall fill opacity.

    Args:
        texture: Base texture pixmap (RGB; the asset forge ships no alpha)
        color: Colour to recolour the texture with

    Returns:
        Recoloured pixmap
    """
    image = texture.toImage().convertToFormat(QImage.Format.Format_RGB32)
    width, height = image.width(), image.height()
    if width == 0 or height == 0:
        return QPixmap(texture.size())

    # Qt's stub types the raw pointer as voidptr; Any here is the typing gap,
    # not a semantic choice. The copy is trivial: 256x256, once per
    # pattern+colour, then cached.
    buffer: Any = image.bits()
    buffer.setsize(image.sizeInBytes())
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    pixels = rows[:, :width, :]
    lum = (
        0.114 * pixels[:, :, 0].astype(np.float32)
        + 0.587 * pixels[:, :, 1].astype(np.float32)
        + 0.299 * pixels[:, :, 2].astype(np.float32)
    )
    mean_lum = max(float(lum.mean()), 1.0)
    scale = lum / mean_lum

    out = np.empty((height, width, 4), dtype=np.uint8)
    out[:, :, 0] = np.clip(color.blue() * scale, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(color.green() * scale, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(color.red() * scale, 0, 255).astype(np.uint8)
    out[:, :, 3] = color.alpha()
    # An opaque fill stays RGB32: a per-pixel alpha channel would make every
    # textured item blend on every repaint (measured ~2x on the NFR-PERF-01
    # fit-in-view scenario). Only a translucent colour needs ARGB32.
    if color.alpha() == 255:
        return QPixmap.fromImage(
            QImage(out.tobytes(), width, height, width * 4, QImage.Format.Format_RGB32).copy()
        )
    return QPixmap.fromImage(
        QImage(out.tobytes(), width, height, width * 4, QImage.Format.Format_ARGB32).copy()
    )


def create_pattern_brush(pattern: FillPattern, color: QColor) -> QBrush:
    """Create a QBrush with the specified pattern and base color.

    For non-SOLID patterns, loads a tileable PNG texture from
    resources/textures/ and applies the color as a tint. Results
    are cached for performance.

    Args:
        pattern: The fill pattern to use
        color: The base color for the pattern

    Returns:
        A QBrush configured with the pattern
    """
    if pattern == FillPattern.SOLID:
        return QBrush(color)

    # Try to load the texture
    texture = _load_texture(pattern)
    if texture is None:
        # Fallback to solid color if texture not found
        return QBrush(color)

    # Check tinted cache
    key = (pattern, _color_key(color))
    if key in _tinted_cache:
        return QBrush(_tinted_cache[key])

    # Evict cache if too large
    if len(_tinted_cache) >= _TINTED_CACHE_MAX:
        _tinted_cache.clear()

    # Create tinted texture
    tinted = _tint_texture(texture, color)
    _tinted_cache[key] = tinted
    return QBrush(tinted)


def clear_texture_cache() -> None:
    """Clear all cached textures. Useful for testing or theme changes."""
    _texture_cache.clear()
    _tinted_cache.clear()
