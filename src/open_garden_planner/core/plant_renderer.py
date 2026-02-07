"""Plant SVG rendering system.

Loads illustrated top-down SVG plant shapes and renders them
as cached QPixmaps for display on the garden canvas. Supports
category-based shapes (15 categories) and species-specific
illustrations (8+ popular species).
"""

import hashlib
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .object_types import ObjectType

# Directory containing plant SVG files
_PLANTS_DIR = Path(__file__).parent.parent / "resources" / "plants"
_CATEGORIES_DIR = _PLANTS_DIR / "categories"
_SPECIES_DIR = _PLANTS_DIR / "species"


class PlantCategory(Enum):
    """Categories of plant shapes for SVG mapping."""

    ROUND_DECIDUOUS = auto()
    COLUMNAR_TREE = auto()
    WEEPING_TREE = auto()
    CONIFER = auto()
    SPREADING_SHRUB = auto()
    COMPACT_SHRUB = auto()
    ORNAMENTAL_GRASS = auto()
    FLOWERING_PERENNIAL = auto()
    GROUND_COVER = auto()
    CLIMBING_PLANT = auto()
    HEDGE_SECTION = auto()
    VEGETABLE = auto()
    HERB = auto()
    FRUIT_TREE = auto()
    PALM = auto()


# Map PlantCategory to SVG filename (without extension)
_CATEGORY_FILES: dict[PlantCategory, str] = {
    PlantCategory.ROUND_DECIDUOUS: "round_deciduous",
    PlantCategory.COLUMNAR_TREE: "columnar_tree",
    PlantCategory.WEEPING_TREE: "weeping_tree",
    PlantCategory.CONIFER: "conifer",
    PlantCategory.SPREADING_SHRUB: "spreading_shrub",
    PlantCategory.COMPACT_SHRUB: "compact_shrub",
    PlantCategory.ORNAMENTAL_GRASS: "ornamental_grass",
    PlantCategory.FLOWERING_PERENNIAL: "flowering_perennial",
    PlantCategory.GROUND_COVER: "ground_cover",
    PlantCategory.CLIMBING_PLANT: "climbing_plant",
    PlantCategory.HEDGE_SECTION: "hedge_section",
    PlantCategory.VEGETABLE: "vegetable",
    PlantCategory.HERB: "herb",
    PlantCategory.FRUIT_TREE: "fruit_tree",
    PlantCategory.PALM: "palm",
}

# Map species names (lowercase) to SVG filename (without extension)
_SPECIES_FILES: dict[str, str] = {
    "rose": "rose",
    "rosa": "rose",
    "lavender": "lavender",
    "lavandula": "lavender",
    "apple": "apple_tree",
    "apple tree": "apple_tree",
    "malus": "apple_tree",
    "cherry": "cherry_tree",
    "cherry tree": "cherry_tree",
    "prunus": "cherry_tree",
    "sunflower": "sunflower",
    "helianthus": "sunflower",
    "tomato": "tomato",
    "solanum lycopersicum": "tomato",
    "boxwood": "boxwood",
    "buxus": "boxwood",
    "box": "boxwood",
    "rhododendron": "rhododendron",
    "azalea": "rhododendron",
}

# Default category mapping for ObjectType
_OBJECT_TYPE_DEFAULT_CATEGORY: dict[ObjectType, PlantCategory] = {
    ObjectType.TREE: PlantCategory.ROUND_DECIDUOUS,
    ObjectType.SHRUB: PlantCategory.SPREADING_SHRUB,
    ObjectType.PERENNIAL: PlantCategory.FLOWERING_PERENNIAL,
}

# Cache for QSvgRenderer instances (path -> renderer)
_renderer_cache: dict[str, QSvgRenderer] = {}

# Cache for rendered pixmaps (cache_key -> QPixmap)
_pixmap_cache: dict[str, QPixmap] = {}

# Maximum pixmap cache entries before eviction
_PIXMAP_CACHE_MAX = 300


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


def _resolve_svg_path(
    object_type: ObjectType,
    species: str = "",
    category: PlantCategory | None = None,
) -> Path | None:
    """Resolve the SVG file path for a plant.

    Priority:
    1. Species-specific SVG (if species name matches)
    2. Category SVG (if category specified)
    3. Default category based on ObjectType

    Args:
        object_type: The plant's ObjectType (TREE, SHRUB, PERENNIAL)
        species: Species name (optional)
        category: Plant category (optional)

    Returns:
        Path to SVG file, or None if not a plant type
    """
    if object_type not in _OBJECT_TYPE_DEFAULT_CATEGORY:
        return None

    # 1. Try species-specific SVG
    if species:
        species_lower = species.lower().strip()
        # Check direct match first
        if species_lower in _SPECIES_FILES:
            path = _SPECIES_DIR / f"{_SPECIES_FILES[species_lower]}.svg"
            if path.exists():
                return path
        # Check partial match (species name contains a known key)
        for key, filename in _SPECIES_FILES.items():
            if key in species_lower or species_lower in key:
                path = _SPECIES_DIR / f"{filename}.svg"
                if path.exists():
                    return path

    # 2. Try category SVG
    if category is not None:
        filename = _CATEGORY_FILES.get(category)
        if filename:
            path = _CATEGORIES_DIR / f"{filename}.svg"
            if path.exists():
                return path

    # 3. Fall back to default category based on ObjectType
    default_category = _OBJECT_TYPE_DEFAULT_CATEGORY.get(object_type)
    if default_category:
        filename = _CATEGORY_FILES.get(default_category)
        if filename:
            path = _CATEGORIES_DIR / f"{filename}.svg"
            if path.exists():
                return path

    return None


def _stable_random_for_item(item_id: str, seed_offset: int = 0) -> float:
    """Generate a stable pseudo-random value from an item ID.

    This ensures the same item always gets the same random variation,
    so plants don't change appearance on re-render.

    Args:
        item_id: Unique item identifier string
        seed_offset: Offset to generate different random values for the same item

    Returns:
        Float between 0.0 and 1.0
    """
    h = hashlib.md5(f"{item_id}:{seed_offset}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def render_plant_pixmap(
    object_type: ObjectType,
    diameter: float,
    item_id: str = "",
    species: str = "",
    category: PlantCategory | None = None,
    tint_color: QColor | None = None,
) -> QPixmap | None:
    """Render a plant SVG to a QPixmap at the specified size.

    Uses caching for performance. Applies slight random rotation
    based on item_id for natural variation.

    Args:
        object_type: The plant's ObjectType
        diameter: Target diameter in pixels
        item_id: Unique item ID for stable randomization
        species: Species name for SVG lookup
        category: Plant category for SVG lookup
        tint_color: Optional color tint to apply

    Returns:
        QPixmap with rendered plant, or None if no SVG available
    """
    svg_path = _resolve_svg_path(object_type, species, category)
    if svg_path is None:
        return None

    renderer = _get_renderer(svg_path)
    if renderer is None:
        return None

    # Calculate render size (use integer pixels)
    size = max(int(diameter), 4)

    # Generate stable random rotation for this specific item
    rotation = 0.0
    if item_id:
        rotation = _stable_random_for_item(item_id, seed_offset=0) * 360.0

    # Build cache key
    tint_key = tint_color.rgba() if tint_color else 0
    cache_key = f"{svg_path}:{size}:{int(rotation)}:{tint_key}"

    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    # Evict cache if too large
    if len(_pixmap_cache) >= _PIXMAP_CACHE_MAX:
        _pixmap_cache.clear()

    # Render SVG to QImage (for compositing)
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Apply rotation around center
    if abs(rotation) > 0.5:
        center = size / 2.0
        painter.translate(center, center)
        painter.rotate(rotation)
        painter.translate(-center, -center)

    # Render SVG into the full area
    renderer.render(painter, QRectF(0, 0, size, size))

    # Apply color tint if specified
    if tint_color is not None and tint_color.alpha() > 0:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        tint = QColor(tint_color.red(), tint_color.green(), tint_color.blue(), 60)
        painter.fillRect(0, 0, size, size, tint)

    painter.end()

    pixmap = QPixmap.fromImage(image)
    _pixmap_cache[cache_key] = pixmap
    return pixmap


def is_plant_type(object_type: ObjectType | None) -> bool:
    """Check if an ObjectType is a plant type.

    Args:
        object_type: The object type to check

    Returns:
        True if this is a plant type (TREE, SHRUB, PERENNIAL)
    """
    if object_type is None:
        return False
    return object_type in _OBJECT_TYPE_DEFAULT_CATEGORY


def get_default_category(object_type: ObjectType) -> PlantCategory | None:
    """Get the default plant category for an ObjectType.

    Args:
        object_type: The object type

    Returns:
        Default PlantCategory, or None if not a plant type
    """
    return _OBJECT_TYPE_DEFAULT_CATEGORY.get(object_type)


def get_all_categories() -> list[PlantCategory]:
    """Get all available plant categories.

    Returns:
        List of all PlantCategory values
    """
    return list(PlantCategory)


def get_species_names() -> list[str]:
    """Get all recognized species names with unique SVGs.

    Returns:
        Sorted list of species names
    """
    return sorted(set(_SPECIES_FILES.keys()))


def clear_plant_cache() -> None:
    """Clear all cached renderers and pixmaps."""
    _renderer_cache.clear()
    _pixmap_cache.clear()
