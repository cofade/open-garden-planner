"""Fill pattern definitions and texture loading for object styling.

Loads tileable PNG textures from resources/textures/ and applies color
tinting to create QBrush objects for rendering garden items.
"""

from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap

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
    """Apply a color tint to a texture pixmap.

    Blends the user's color onto the texture to allow customization
    while preserving the texture detail. The color's alpha channel
    controls the overall fill opacity.

    Args:
        texture: Base texture pixmap
        color: Color to tint with

    Returns:
        Tinted pixmap
    """
    result = QPixmap(texture.size())
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw the base texture at the color's alpha level
    alpha = color.alpha()
    if alpha < 255:
        painter.setOpacity(alpha / 255.0)
    painter.drawPixmap(0, 0, texture)

    # Overlay the user's color at reduced opacity for tinting
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    tint = QColor(color.red(), color.green(), color.blue(), 80)
    painter.fillRect(result.rect(), tint)

    painter.end()
    return result


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
