"""Furniture SVG rendering system.

Loads illustrated top-down SVG furniture shapes and renders them
as cached QPixmaps for display on the garden canvas.
"""

import functools
import math
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap, QTransform
from PyQt6.QtSvg import QSvgRenderer

from .object_types import ObjectType
from .sprite_orientation import NATURAL_SIZE_CM, sprite_turn_deg
from .sprite_raster import paint_sprite

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
    # Package 3a roster (#308)
    ObjectType.SANDBOX: "sandbox",
    ObjectType.TRAMPOLINE: "trampoline",
    ObjectType.HOT_TUB: "hot_tub",
    ObjectType.SWING: "swing",
    ObjectType.PICNIC_TABLE: "picnic_table",
    ObjectType.HAMMOCK: "hammock",
    # Garden lights (Phase 17 L5.4, #389)
    ObjectType.GARDEN_LIGHT: "garden_light",
}

# Map ObjectType to SVG filename for infrastructure objects
_INFRASTRUCTURE_FILES: dict[ObjectType, str] = {
    ObjectType.RAISED_BED: "raised_bed",
    ObjectType.COMPOST_BIN: "compost_bin",
    ObjectType.COLD_FRAME: "cold_frame",
    ObjectType.RAIN_BARREL: "rain_barrel",
    ObjectType.WATER_TAP: "water_tap",
    ObjectType.TOOL_SHED: "tool_shed",
    # Package 3a roster (#308)
    ObjectType.WHEELBARROW: "wheelbarrow",
    ObjectType.BIRD_BATH: "bird_bath",
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
    ObjectType.WHEELBARROW: _INFRASTRUCTURE_DIR,
    ObjectType.BIRD_BATH: _INFRASTRUCTURE_DIR,
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
    ObjectType.WHEELBARROW: "wheelbarrow",
    ObjectType.BIRD_BATH: "bird_bath",
}

# Default dimensions in cm (width, height) for each furniture type, from the
# one natural-size table that also drives sprite turning (#776). Each entry must
# equal its sprite's viewBox (gate: tests/unit/test_object_sprite_conformance.py).
# A garden light is a lantern post (round); a string of lights is a line and has
# no sprite (ui/canvas/items/string_lights_paint.py).
FURNITURE_DEFAULT_DIMENSIONS: dict[ObjectType, tuple[float, float]] = {
    ObjectType[name]: size
    for name, size in NATURAL_SIZE_CM.items()
    if name in ObjectType.__members__
}

# Cache for QSvgRenderer instances (path -> renderer)
_renderer_cache: dict[str, QSvgRenderer] = {}

# Cache for rendered pixmaps (cache_key -> (QPixmap, byte_count)) in LRU order
_pixmap_cache: OrderedDict[str, tuple[QPixmap, int]] = OrderedDict()

# Maximum pixmap cache entries and byte budget before eviction (#474)
_PIXMAP_CACHE_MAX = 200
_PIXMAP_CACHE_MAX_BYTES = 64 * 1024 * 1024  # 64 MB budget
_current_cache_bytes = 0

# Maximum single dimension allowed for rendering (px) to prevent OOM
MAX_FURNITURE_DIMENSION_PX = 2048


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


def paints_picture(object_type: ObjectType | None) -> bool:
    """Whether a type's 2D canvas picture is a PICTURE, not a plain fill.

    An SVG sprite (``is_furniture_type``) or a parametric painter: a PERGOLA is
    drawn from ``core.pergola`` by ``ui.canvas.items.pergola_paint`` since #769,
    never a stretched sprite. Such an item states no pen or brush of its own, and
    a missing picture paints NOTHING — never the plain fill underneath (#308's
    "a furniture item without its sprite file has no brush on the canvas").
    """
    return is_furniture_type(object_type) or object_type is ObjectType.PERGOLA


@functools.lru_cache(maxsize=64)
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


def _draw_furniture(
    painter: QPainter, rect: QRectF, renderer: QSvgRenderer, turn: bool
) -> None:
    """THE way an object sprite is drawn into ``rect``: as it is, or — for a
    sprite whose natural long axis is opposite the rectangle's (#776) — at the
    swapped size and turned a quarter clockwise about the middle."""
    if not turn:
        renderer.render(painter, rect)
        return
    center = rect.center()
    painter.save()
    painter.translate(center)
    painter.rotate(90.0)
    renderer.render(
        painter,
        QRectF(-rect.height() / 2.0, -rect.width() / 2.0, rect.height(), rect.width()),
    )
    painter.restore()


def paint_furniture(painter: QPainter, rect: QRectF, object_type: ObjectType) -> bool:
    """Paint an object's sprite into ``rect`` (item units), upright, as fine as
    ``painter`` shows it — the canvas's way to draw furniture (#785).

    The canvas (and every export) draws the scene through a ``scale(1, -1)``
    Y-flip, so a picture laid into item-local coordinates comes out upside-down
    (fire-pit flames pointing down, #308 manual test); it is flipped back about
    the rectangle's centre here, once, for every caller. The resolution is
    ``core.sprite_raster.paint_sprite``'s — the one rule of
    ``core.raster_resolution``; the quarter turn is ``sprite_turn_deg``'s.

    Returns:
        False if the type has no sprite or the rectangle is degenerate.
    """
    width, height = rect.width(), rect.height()
    if not (math.isfinite(width) and math.isfinite(height) and width > 0 and height > 0):
        return False
    svg_path = get_furniture_svg_path(object_type)
    if svg_path is None:
        return False
    renderer = _get_renderer(svg_path)
    if renderer is None:
        return False
    turn = sprite_turn_deg(object_type.name, width, height) != 0.0
    center = rect.center()
    painter.save()
    painter.translate(center)
    painter.scale(1.0, -1.0)
    painter.translate(-center)
    painted = paint_sprite(
        painter,
        rect,
        ("object", str(svg_path), turn),
        lambda p, r: _draw_furniture(p, r, renderer, turn),
    )
    painter.restore()
    return painted


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
    if math.isnan(width) or math.isnan(height) or width <= 0 or height <= 0 or math.isinf(width) or math.isinf(height):
        return None

    svg_path = get_furniture_svg_path(object_type)
    if svg_path is None:
        return None

    renderer = _get_renderer(svg_path)
    if renderer is None:
        return None

    # A sprite whose natural long axis is opposite the target's is rendered at
    # the SWAPPED size and turned a quarter clockwise below, so its long axis
    # follows the item's instead of being squashed (#776).
    turn = sprite_turn_deg(object_type.name, width, height) != 0.0
    target_width, target_height = (height, width) if turn else (width, height)

    # Calculate render size (use integer pixels, minimum 4, capped at MAX_FURNITURE_DIMENSION_PX)
    if target_width > MAX_FURNITURE_DIMENSION_PX or target_height > MAX_FURNITURE_DIMENSION_PX:
        scale = min(MAX_FURNITURE_DIMENSION_PX / target_width,
                    MAX_FURNITURE_DIMENSION_PX / target_height)
        w = max(int(target_width * scale), 4)
        h = max(int(target_height * scale), 4)
    else:
        w = max(int(target_width), 4)
        h = max(int(target_height), 4)

    # Build cache key (the turn is part of it: the same pixel size can be a
    # natural or a turned picture)
    cache_key = f"{svg_path}:{w}:{h}:{'t' if turn else 'n'}"

    if cache_key in _pixmap_cache:
        _pixmap_cache.move_to_end(cache_key)
        pixmap, _ = _pixmap_cache[cache_key]
        return pixmap

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
    if turn:
        pixmap = pixmap.transformed(
            QTransform().rotate(90.0), Qt.TransformationMode.FastTransformation
        )

    global _current_cache_bytes
    entry_bytes = pixmap.width() * pixmap.height() * 4

    # Evict least recently used entries until within entry and byte budget (#474)
    while _pixmap_cache and (
        len(_pixmap_cache) >= _PIXMAP_CACHE_MAX
        or _current_cache_bytes + entry_bytes > _PIXMAP_CACHE_MAX_BYTES
    ):
        _, (_, old_bytes) = _pixmap_cache.popitem(last=False)
        _current_cache_bytes -= old_bytes

    if entry_bytes <= _PIXMAP_CACHE_MAX_BYTES:
        if cache_key in _pixmap_cache:
            _, old_bytes = _pixmap_cache.pop(cache_key)
            _current_cache_bytes -= old_bytes
        _pixmap_cache[cache_key] = (pixmap, entry_bytes)
        _current_cache_bytes += entry_bytes

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
    global _current_cache_bytes
    _renderer_cache.clear()
    _pixmap_cache.clear()
    _current_cache_bytes = 0
