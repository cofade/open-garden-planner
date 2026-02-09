"""Furniture SVG rendering system.

Loads illustrated top-down SVG furniture shapes and renders them
as cached QPixmaps for display on the garden canvas.
"""

from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .object_types import ObjectType

# Directories containing SVG files
_FURNITURE_DIR = Path(__file__).parent.parent / "resources" / "objects" / "furniture"
_INFRASTRUCTURE_DIR = Path(__file__).parent.parent / "resources" / "objects" / "infrastructure"
_PLANTS_CATEGORIES_DIR = Path(__file__).parent.parent / "resources" / "plants" / "categories"

# Map ObjectType to (directory, filename_without_extension)
_FURNITURE_FILES: dict[ObjectType, str] = {
    ObjectType.TABLE_RECTANGULAR: "table_rectangular",
    ObjectType.TABLE_ROUND: "table_round",
    ObjectType.CHAIR: "chair",
    ObjectType.BENCH: "bench",
    ObjectType.PARASOL: "parasol",
    ObjectType.LOUNGER: "lounger",
    ObjectType.BBQ_GRILL: "bbq_grill",
    ObjectType.FIRE_PIT: "fire_pit",
    ObjectType.PLANTER_POT: "planter_pot",
}

# Map ObjectType to SVG filename for infrastructure objects
_INFRASTRUCTURE_FILES: dict[ObjectType, str] = {
    ObjectType.RAISED_BED: "raised_bed",
    ObjectType.COMPOST_BIN: "compost_bin",
    ObjectType.COLD_FRAME: "cold_frame",
    ObjectType.RAIN_BARREL: "rain_barrel",
    ObjectType.WATER_TAP: "water_tap",
    ObjectType.TOOL_SHED: "tool_shed",
}

# SVG types whose files live outside _FURNITURE_DIR
_SVG_DIR_OVERRIDES: dict[ObjectType, Path] = {
    ObjectType.HEDGE_SECTION: _PLANTS_CATEGORIES_DIR,
    ObjectType.RAISED_BED: _INFRASTRUCTURE_DIR,
    ObjectType.COMPOST_BIN: _INFRASTRUCTURE_DIR,
    ObjectType.COLD_FRAME: _INFRASTRUCTURE_DIR,
    ObjectType.RAIN_BARREL: _INFRASTRUCTURE_DIR,
    ObjectType.WATER_TAP: _INFRASTRUCTURE_DIR,
    ObjectType.TOOL_SHED: _INFRASTRUCTURE_DIR,
}

# Map ObjectType to SVG filename for non-furniture SVG-rendered objects
_OBJECT_SVG_FILES: dict[ObjectType, str] = {
    ObjectType.HEDGE_SECTION: "hedge_section",
    ObjectType.RAISED_BED: "raised_bed",
    ObjectType.COMPOST_BIN: "compost_bin",
    ObjectType.COLD_FRAME: "cold_frame",
    ObjectType.RAIN_BARREL: "rain_barrel",
    ObjectType.WATER_TAP: "water_tap",
    ObjectType.TOOL_SHED: "tool_shed",
}

# Default dimensions in cm (width, height) for each furniture type
FURNITURE_DEFAULT_DIMENSIONS: dict[ObjectType, tuple[float, float]] = {
    ObjectType.TABLE_RECTANGULAR: (150.0, 100.0),
    ObjectType.TABLE_ROUND: (100.0, 100.0),
    ObjectType.CHAIR: (50.0, 50.0),
    ObjectType.BENCH: (180.0, 60.0),
    ObjectType.PARASOL: (300.0, 300.0),
    ObjectType.LOUNGER: (70.0, 190.0),
    ObjectType.BBQ_GRILL: (80.0, 60.0),
    ObjectType.FIRE_PIT: (100.0, 100.0),
    ObjectType.PLANTER_POT: (50.0, 50.0),
    # Infrastructure
    ObjectType.RAISED_BED: (120.0, 80.0),
    ObjectType.COMPOST_BIN: (100.0, 100.0),
    ObjectType.COLD_FRAME: (120.0, 60.0),
    ObjectType.RAIN_BARREL: (60.0, 60.0),
    ObjectType.WATER_TAP: (20.0, 20.0),
    ObjectType.TOOL_SHED: (200.0, 150.0),
}

# Cache for QSvgRenderer instances (path -> renderer)
_renderer_cache: dict[str, QSvgRenderer] = {}

# Cache for rendered pixmaps (cache_key -> QPixmap)
_pixmap_cache: dict[str, QPixmap] = {}

# Maximum pixmap cache entries before eviction
_PIXMAP_CACHE_MAX = 200


def is_furniture_type(object_type: ObjectType | None) -> bool:
    """Check if an ObjectType is an SVG-rendered object (furniture, hedge, etc.).

    Args:
        object_type: The object type to check

    Returns:
        True if this type uses SVG rendering
    """
    if object_type is None:
        return False
    return object_type in _FURNITURE_FILES or object_type in _OBJECT_SVG_FILES


def get_furniture_svg_path(object_type: ObjectType) -> Path | None:
    """Get the SVG file path for an SVG-rendered object type.

    Args:
        object_type: The ObjectType

    Returns:
        Path to SVG file, or None if not an SVG-rendered type
    """
    # Check furniture files first
    filename = _FURNITURE_FILES.get(object_type)
    if filename is not None:
        path = _FURNITURE_DIR / f"{filename}.svg"
        if path.exists():
            return path
        return None

    # Check other SVG object files
    filename = _OBJECT_SVG_FILES.get(object_type)
    if filename is not None:
        svg_dir = _SVG_DIR_OVERRIDES.get(object_type, _FURNITURE_DIR)
        path = svg_dir / f"{filename}.svg"
        if path.exists():
            return path

    return None


def _get_renderer(svg_path: Path) -> QSvgRenderer | None:
    """Load or retrieve cached QSvgRenderer for an SVG file.

    Args:
        svg_path: Path to the SVG file

    Returns:
        QSvgRenderer instance, or None if file not found/invalid
    """
    key = str(svg_path)
    if key in _renderer_cache:
        return _renderer_cache[key]

    if not svg_path.exists():
        return None

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        return None

    _renderer_cache[key] = renderer
    return renderer


def render_furniture_pixmap(
    object_type: ObjectType,
    width: float,
    height: float,
) -> QPixmap | None:
    """Render a furniture SVG to a QPixmap at the specified size.

    Uses caching for performance.

    Args:
        object_type: The furniture ObjectType
        width: Target width in pixels
        height: Target height in pixels

    Returns:
        QPixmap with rendered furniture, or None if no SVG available
    """
    svg_path = get_furniture_svg_path(object_type)
    if svg_path is None:
        return None

    renderer = _get_renderer(svg_path)
    if renderer is None:
        return None

    # Calculate render size (use integer pixels, minimum 4)
    w = max(int(width), 4)
    h = max(int(height), 4)

    # Build cache key
    cache_key = f"{svg_path}:{w}:{h}"

    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    # Evict cache if too large
    if len(_pixmap_cache) >= _PIXMAP_CACHE_MAX:
        _pixmap_cache.clear()

    # Render SVG to QImage
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Render SVG into the full area
    renderer.render(painter, QRectF(0, 0, w, h))

    painter.end()

    pixmap = QPixmap.fromImage(image)
    _pixmap_cache[cache_key] = pixmap
    return pixmap


def get_default_dimensions(object_type: ObjectType) -> tuple[float, float]:
    """Get the default dimensions (width, height) for a furniture type.

    Args:
        object_type: The furniture ObjectType

    Returns:
        Tuple of (width, height) in cm
    """
    return FURNITURE_DEFAULT_DIMENSIONS.get(object_type, (100.0, 100.0))


def clear_furniture_cache() -> None:
    """Clear all cached renderers and pixmaps."""
    _renderer_cache.clear()
    _pixmap_cache.clear()
