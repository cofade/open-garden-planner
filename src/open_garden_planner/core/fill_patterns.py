"""Fill pattern definitions and texture loading for object styling.

Loads tileable PNG textures from resources/textures/ and recolours each one to
the item's fill colour to create QBrush objects for rendering garden items.

A pattern's tile exists at five LEVELS (#785, #849), in texture pixels per cm:

- **0.125 / 0.25 / 0.5** — zoomed-out anti-moire mip tiles (32, 64, 128 px)
  prefiltered periodically to Nyquist and contrast-preserved around the tile's
  mean luminance, eliminating brick/roof-tile moire at 15–30 % zoom while
  keeping texture contrast intact (#503).
- **1** — the 256-px tile every brush is made with (``create_pattern_brush``),
  and what a fill is painted with at 50–100 % zoom: unchanged, pixel for pixel.
- **2** — the detail tile ``textures/x2/<name>.png``: the generator's own 512-px
  canvas before the box downsample that makes the 256-px tile. Used above
  100 %, where the 256-px tile is an upscaled bitmap.

``brush_for_painter`` swaps a brush's tile for the level its painter shows it
at and scales the brush transform to match, so the pattern's size, phase and
``FillTransform`` are exactly what they were.
"""

import math
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, cast

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QTransform

from .raster_resolution import device_scale, raster_level
from .sprite_raster import PixmapLru

# Directory containing texture PNG files
_TEXTURES_DIR = Path(__file__).parent.parent / "resources" / "textures"

# Cache for loaded base texture pixmaps (pattern -> QPixmap)
_texture_cache: dict["FillPattern", QPixmap] = {}

# Cache for tinted texture pixmaps (pattern, color_key -> QPixmap)
_tinted_cache: dict[tuple["FillPattern", int], QPixmap] = {}

# Maximum number of tinted texture cache entries before clearing
_TINTED_CACHE_MAX = 200

# The detail tiles (#785) and zoomed-out anti-moire mip tiles (#849):
# textures/x2/<name>.png at DETAIL_LEVEL (2 px/cm), and contrast-preserving
# band-limited coarse tiles at 0.5, 0.25, and 0.125 px/cm.
DETAIL_LEVEL = 2.0
COARSE_LEVELS: tuple[float, ...] = (0.5, 0.25, 0.125)
_COARSE_FILTER_SIGMA = 0.70
_COARSE_MAX_CONTRAST_GAIN = 2.8
_DETAIL_DIR = _TEXTURES_DIR / "x2"

# Which (pattern, colour) a tinted 256-px tile is, by its pixmap cache key: how
# ``brush_for_painter`` recognises a brush it may refine. Entries are two ints.
# The table outlives the tinted cache's own eviction — an item that still holds
# an evicted tile stays recognisable — and is emptied only by
# ``clear_texture_cache()`` and when it outgrows this.
_brush_tiles: dict[int, tuple["FillPattern", int]] = {}
_BRUSH_TILES_MAX = 4096

# Untinted detail tiles (pattern -> QImage or None if the file is missing),
# untinted coarse luminance tiles ((pattern, level) -> (lum_array, base_mean_lum)),
# and the tinted level tiles ((pattern, rgba, level) -> QPixmap), least recently
# used first. A level-2 tile is 1 MB; coarse tiles are 4–64 KB.
_detail_cache: dict["FillPattern", QImage | None] = {}
_coarse_cache: dict[tuple["FillPattern", float], tuple[np.ndarray, float] | None] = {}
LEVEL_TILE_CACHE_MAX_BYTES = 48 * 1024 * 1024
_level_tiles = PixmapLru(LEVEL_TILE_CACHE_MAX_BYTES, 512)


def _is_finite(value: float) -> bool:
    """``math.isfinite`` that treats an unrepresentable value as non-finite."""
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class FillTransform:
    """A per-object transform of the fill texture (issue #665).

    The texture normally tiles in the item's own frame at its authored size.
    These four values move, turn and resize the *pattern* only — geometry,
    area, snapping and export coordinates are untouched:

    * ``angle_deg`` — clockwise on screen, 0 = as authored. (The canvas frame
      is Y-flipped, so a clockwise turn is Qt's positive ``QTransform.rotate``.)
    * ``scale`` — tile-size multiplier, 1.0 = the authored tile.
    * ``offset_x_cm`` / ``offset_y_cm`` — shift the pattern in the item's own
      centimetre frame; +X is right and +Y is up, i.e. CAD axes.

    A plain ``FillTransform()`` is the identity and is never serialized, so old
    plans keep loading with no visible change and the stored file grows only
    when the user actually edits the pattern.
    """

    angle_deg: float = 0.0
    scale: float = 1.0
    offset_x_cm: float = 0.0
    offset_y_cm: float = 0.0

    @property
    def is_identity(self) -> bool:
        return (
            self.angle_deg == 0.0
            and self.scale == 1.0
            and self.offset_x_cm == 0.0
            and self.offset_y_cm == 0.0
        )

    def brush_transform(self) -> QTransform:
        """The ``QBrush`` transform these values describe.

        Order is translate(offset) · rotate(angle) · scale(scale), so the
        offset is applied in centimetres in the item frame and is independent
        of the scale and the angle (acceptance criterion of #665).
        """
        transform = QTransform()
        transform.translate(self.offset_x_cm, self.offset_y_cm)
        transform.rotate(self.angle_deg)
        transform.scale(self.scale, self.scale)
        return transform

    def to_dict(self) -> dict[str, float] | None:
        """The additive ``fill_transform`` block, or None for the identity."""
        if self.is_identity:
            return None
        values = (self.angle_deg, self.scale, self.offset_x_cm, self.offset_y_cm)
        if not all(_is_finite(value) for value in values):
            # json.dump writes NaN happily; a JSON NaN would reopen as an
            # invalid number. Dropping the whole block is the safe fallback.
            return None
        return {
            "angle_deg": self.angle_deg,
            "scale": self.scale,
            "offset_x_cm": self.offset_x_cm,
            "offset_y_cm": self.offset_y_cm,
        }

    @classmethod
    def from_dict(cls, value: object) -> "FillTransform":
        """Read a stored block leniently — it arrives from an untrusted file.

        A missing or malformed field keeps its default, a non-finite number is
        ignored, and a scale that is zero or negative falls back to 1.0 (a
        mirrored/degenerate tile is never what a plan means). Never raises.
        """
        if not isinstance(value, dict):
            return cls()

        def number(key: str, default: float) -> float:
            raw = value.get(key, default)
            if isinstance(raw, bool) or not isinstance(raw, int | float):
                return default
            try:
                result = float(raw)
            except (OverflowError, TypeError, ValueError):
                # A huge JSON integer (``10**400``) is a valid ``int`` but not
                # representable as a float; it is malformed for this field.
                return default
            return result if math.isfinite(result) else default

        scale = number("scale", 1.0)
        if scale <= 0.0:
            scale = 1.0
        return cls(
            angle_deg=number("angle_deg", 0.0),
            scale=scale,
            offset_x_cm=number("offset_x_cm", 0.0),
            offset_y_cm=number("offset_y_cm", 0.0),
        )


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
    MOSS = auto()  # Tight moss cushion for a moss lawn (#960)


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
    # #960: moss has no texture of its own; the hedge texture is a dense leaf mass at
    # the cushion's scale, tinted by the plan's own moss colour.
    FillPattern.MOSS: "hedge",
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
    image = texture.toImage()
    if image.width() == 0 or image.height() == 0:
        return QPixmap(texture.size())
    return _tint_image(image, color, _mean_luminance(image))


def _luminance(image: QImage) -> np.ndarray:
    """Per-pixel luminance of ``image`` (float32, rows x columns)."""
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height = image.width(), image.height()
    # Qt's stub types the raw pointer as voidptr; Any here is the typing gap,
    # not a semantic choice. The copy is trivial: one tile, once per
    # pattern+colour, then cached.
    buffer: Any = image.bits()
    buffer.setsize(image.sizeInBytes())
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    pixels = rows[:, :width, :]
    luminance: np.ndarray = (
        0.114 * pixels[:, :, 0].astype(np.float32)
        + 0.587 * pixels[:, :, 1].astype(np.float32)
        + 0.299 * pixels[:, :, 2].astype(np.float32)
    )
    return luminance


def _mean_luminance(image: QImage) -> float:
    """The mean a texture's tint is normalised with (never below 1)."""
    return max(float(_luminance(image).mean()), 1.0)


def _tint_luminance(lum: np.ndarray, color: QColor, mean_lum: float) -> QPixmap:
    """Recolour a ``lum`` array to ``color`` relative to ``mean_lum``."""
    height, width = lum.shape
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


def _tint_image(image: QImage, color: QColor, mean_lum: float) -> QPixmap:
    """``image`` recoloured to ``color`` by its luminance relative to
    ``mean_lum`` (``_tint_texture``'s map). A detail tile is tinted with the
    256-px tile's mean, so the two levels are the same picture."""
    return _tint_luminance(_luminance(image), color, mean_lum)


def _periodic_gaussian_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Zero-phase periodic Gaussian prefilter via 2D FFT (exact wrap-around)."""
    height, width = arr.shape
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :]
    kernel = np.exp(-2.0 * (math.pi**2) * (sigma**2) * (fx**2 + fy**2))
    blurred: np.ndarray = np.fft.ifft2(np.fft.fft2(arr) * kernel).real
    return blurred


def _coarse_luminance(lum_256: np.ndarray, factor: int) -> np.ndarray | None:
    """Band-limited, contrast-preserved downsample of ``lum_256`` by ``factor`` (#849).

    Box-averaging alone washes out thin mortar/ridge lines and fails the #503
    contrast floor. Filtering periodically in frequency space removes aliases
    above the coarse Nyquist limit, and rescaling AC deviations around the tile
    mean preserves texture contrast without shifting average brightness.
    """
    height, width = lum_256.shape
    if height % factor != 0 or width % factor != 0:
        return None
    blurred = _periodic_gaussian_blur(lum_256, sigma=_COARSE_FILTER_SIGMA * factor)
    new_h, new_w = height // factor, width // factor
    coarse = blurred.reshape(new_h, factor, new_w, factor).mean(axis=(1, 3))
    mu = float(lum_256.mean())
    sigma_base = float(lum_256.std())
    sigma_coarse = float(coarse.std())
    if sigma_coarse > 1e-3:
        gain = min(sigma_base / sigma_coarse, _COARSE_MAX_CONTRAST_GAIN)
        coarse = np.clip(mu + (coarse - mu) * gain, 1.0, 255.0)
    return cast(np.ndarray, coarse.astype(np.float32))


def create_pattern_brush(
    pattern: FillPattern,
    color: QColor,
    transform: FillTransform | None = None,
) -> QBrush:
    """Create a QBrush with the specified pattern and base color.

    For non-SOLID patterns, loads a tileable PNG texture from
    resources/textures/ and applies the color as a tint. Results
    are cached for performance; ``transform`` (issue #665) is applied to the
    brush on top of the cached texture and costs no extra pixmap work.

    Args:
        pattern: The fill pattern to use
        color: The base color for the pattern
        transform: Optional per-object pattern angle/scale/offset

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

    brush = QBrush(_tinted_tile(pattern, texture, color))
    if transform is not None and not transform.is_identity:
        brush.setTransform(transform.brush_transform())
    return brush


def _tinted_tile(pattern: FillPattern, texture: QPixmap, color: QColor) -> QPixmap:
    """The 256-px tile of ``pattern`` in ``color`` — cached, and registered so
    ``brush_for_painter`` knows a brush made of it."""
    key = (pattern, _color_key(color))
    tinted = _tinted_cache.get(key)
    if tinted is None:
        # Evict cache if too large
        if len(_tinted_cache) >= _TINTED_CACHE_MAX:
            _tinted_cache.clear()
        # Create tinted texture
        tinted = _tint_texture(texture, color)
        _tinted_cache[key] = tinted
    if len(_brush_tiles) >= _BRUSH_TILES_MAX:
        _brush_tiles.clear()
    _brush_tiles[tinted.cacheKey()] = key
    return tinted


def _load_detail(pattern: FillPattern) -> QImage | None:
    """The untinted detail tile of ``pattern`` (``DETAIL_LEVEL`` px per cm), or
    None when the file is missing — the fill then keeps its 256-px tile."""
    if pattern in _detail_cache:
        return _detail_cache[pattern]
    image: QImage | None = None
    filename = _TEXTURE_FILES.get(pattern)
    if filename is not None:
        path = _DETAIL_DIR / f"{filename}.png"
        if path.exists():
            loaded = QImage(str(path))
            if not loaded.isNull():
                image = loaded
    _detail_cache[pattern] = image
    return image


def _load_coarse(pattern: FillPattern, level: float) -> tuple[np.ndarray, float] | None:
    """Cached untinted coarse luminance array + base mean luminance for ``level``."""
    cache_key = (pattern, level)
    if cache_key in _coarse_cache:
        return _coarse_cache[cache_key]
    texture = _load_texture(pattern)
    if texture is None:
        _coarse_cache[cache_key] = None
        return None
    base_img = texture.toImage()
    lum_256 = _luminance(base_img)
    mean_lum = max(float(lum_256.mean()), 1.0)
    factor = round(1.0 / level)
    coarse = _coarse_luminance(lum_256, factor)
    result = (coarse, mean_lum) if coarse is not None else None
    _coarse_cache[cache_key] = result
    return result


def tile_level(scale: float) -> float:
    """The tile level for a fill shown at ``scale`` device pixels per texture cm.

    - Above 100 % (``scale > 1.01``): ``DETAIL_LEVEL`` (2.0, 512 px).
    - 50–100 % (``0.49 < scale <= 1.01``): 1.0 (256 px, unchanged).
    - Below 50 % (``scale <= 0.49``): nearest power-of-two coarse mip level in
      ``(0.5, 0.25, 0.125)`` so Qt's bilinear sampler never minifies more than
      ~1.4x and cannot produce moire (#849).
    """
    if not _is_finite(scale) or scale <= 0.0:
        return 1.0
    if scale > 1.0:
        return min(raster_level(scale), DETAIL_LEVEL)
    if scale >= 0.49:
        return 1.0
    if scale > 0.25 * math.sqrt(2.0):
        return 0.5
    if scale > 0.125 * math.sqrt(2.0):
        return 0.25
    return 0.125


def level_tile(pattern: FillPattern, color: QColor, level: float) -> QPixmap | None:
    """The tinted tile of ``pattern`` at ``level`` texture px per cm, or None
    when that level does not exist (SOLID, a missing file, level 1 — which is
    ``create_pattern_brush``'s own tile)."""
    if pattern == FillPattern.SOLID or level == 1.0:
        return None
    key = (pattern, _color_key(color), level)
    cached = _level_tiles.get(key)
    if cached is not None:
        return cached
    if level == DETAIL_LEVEL:
        texture = _load_texture(pattern)
        detail = _load_detail(pattern)
        if texture is None or detail is None:
            return None
        # normalised with the 256-px tile's mean: the same picture, finer
        tile = _tint_image(detail, color, _mean_luminance(texture.toImage()))
    elif level in COARSE_LEVELS:
        loaded = _load_coarse(pattern, level)
        if loaded is None:
            return None
        coarse_lum, mean_lum = loaded
        tile = _tint_luminance(coarse_lum, color, mean_lum)
    else:
        return None
    _level_tiles.put(key, tile)
    return tile


def brush_for_painter(brush: QBrush, painter: QPainter) -> QBrush | None:
    """``brush`` with its tile at the level ``painter`` shows it at, or None when
    the brush is right as it is (#785).

    A pattern brush's tile has 1 texture px per cm. Above 100 % zoom (or on a
    high-density display, or in a 300-dpi export) that is an upscaled bitmap.
    The answer is the same tile at another level (module docstring) under a
    brush transform scaled by ``1 / level``, so the pattern keeps its size, its
    phase and the item's ``FillTransform``. The level follows
    ``core.raster_resolution`` — the device pixels one texture cm covers, the
    brush's own transform included — rounded up to a power of two.

    None for a solid brush, a tile this module did not make, and level 1: at
    50–100 % zoom a fill is painted with exactly the brush it has.
    """
    if brush.style() != Qt.BrushStyle.TexturePattern:
        return None
    entry = _brush_tiles.get(brush.texture().cacheKey())
    if entry is None:
        return None
    pattern, rgba = entry
    own = brush.transform()
    stretch = max(math.hypot(own.m11(), own.m12()), math.hypot(own.m21(), own.m22()))
    if not _is_finite(stretch) or stretch <= 0.0:
        stretch = 1.0
    level = tile_level(device_scale(painter) * stretch)
    tile = level_tile(pattern, QColor.fromRgba(rgba), level)
    if tile is None:
        return None
    refined = QBrush(tile)
    refined.setTransform(QTransform.fromScale(1.0 / level, 1.0 / level) * own)
    return refined


def clear_texture_cache() -> None:
    """Clear all cached textures. Useful for testing or theme changes."""
    _texture_cache.clear()
    _tinted_cache.clear()
    _brush_tiles.clear()
    _detail_cache.clear()
    _coarse_cache.clear()
    _level_tiles.clear()


def pattern_from_name(name: str | None) -> FillPattern | None:
    """``"GRASS"`` -> ``FillPattern.GRASS``; ``None`` for SOLID or an unknown name.

    The record carries a fill pattern's NAME (``Material.pattern``), never a Qt
    enum: the 3D path is Qt-free above ``ui/view3d``.
    """
    if not name:
        return None
    pattern = FillPattern.__members__.get(name)
    if pattern is None or pattern == FillPattern.SOLID:
        return None
    return pattern


def pattern_pixels(pattern: FillPattern) -> tuple[int, int, bytes] | None:
    """A fill pattern's own texture, UNTINTED — RGBA8, top-down, opaque, rows as the
    image's (row 0 its top); one tile is 256 cm wide in the plan's coordinates.

    What the 3D meadow's grass is made of (#798: ``core.scene3d.meadow.grass_detail``):
    the canvas's GRASS picture as the asset forge drew it, not a recolouring of it.
    Read with ``QImage`` (no ``QPixmap``), so it needs no running application. ``None``
    for SOLID or a missing texture."""
    filename = _TEXTURE_FILES.get(pattern)
    if filename is None:
        return None
    image = QImage(str(_TEXTURES_DIR / f"{filename}.png"))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    buffer: Any = image.constBits()
    buffer.setsize(image.sizeInBytes())
    if image.bytesPerLine() != width * 4:  # RGBA8888 is packed; a padded row would shear it
        raise ValueError(f"the {pattern.name} texture has {image.bytesPerLine()} bytes a row "
                         f"for {width} pixels")
    data = bytearray(buffer)
    data[3::4] = b"\xff" * (width * height)
    return width, height, bytes(data)


def pattern_rgb(pattern: FillPattern) -> np.ndarray | None:
    """A fill pattern's own picture, untinted: (rows, columns, 3) uint8, row 0 the
    image's top — or None for SOLID or a missing texture. What a 3D surface's detail
    picture is made from (#801, ``core.scene3d.surface_detail``). The same read as
    ``pattern_pixels`` (the meadow's grass, #798), without its alpha channel."""
    pixels = pattern_pixels(pattern)
    if pixels is None:
        return None
    width, height, data = pixels
    rgba = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
    return np.array(rgba[:, :, :3])


def tinted_pattern_pixels(pattern: FillPattern, color: QColor) -> tuple[int, int, bytes] | None:
    """A fill pattern exactly as the canvas paints it — RGBA8, top-down, opaque.

    This is the picture a 3D solid's own faces carry when the plan gives it a
    height (#628 follow-up): the ground bake paints the fill while the item lies
    on the ground, and a raised item is no longer painted there, so its top (and
    sides) show this instead. ``None`` for SOLID or a missing texture: the caller
    shows the fill colour alone, which is what the canvas does for SOLID too.

    Rows are the texture's own rows (row 0 is the image's top) and one tile is
    256 cm wide in the plan's coordinates (``core.scene3d.PATTERN_TILE_CM``); the
    mesh's UVs use that same ruler. Alpha is forced opaque: a 3D solid body does not show the 2D
    fill's transparency (``Material.tint_rgba`` forces it too).
    """
    if pattern == FillPattern.SOLID:
        return None
    texture = _load_texture(pattern)
    if texture is None:
        return None
    tinted = _tinted_tile(pattern, texture, color)
    image = tinted.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    buffer: Any = image.bits()
    buffer.setsize(image.sizeInBytes())
    if image.bytesPerLine() != width * 4:  # RGBA8888 is packed; a padded row would shear it
        raise ValueError(f"the {pattern.name} texture has {image.bytesPerLine()} bytes a row "
                         f"for {width} pixels")
    data = bytearray(buffer)
    data[3::4] = b"\xff" * (width * height)   # one slice assignment, not a Python loop over pixels
    return width, height, bytes(data)
