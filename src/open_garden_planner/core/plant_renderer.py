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
    # Vegetables
    "pepper": "pepper",
    "bell pepper": "pepper",
    "capsicum": "pepper",
    "eggplant": "eggplant",
    "aubergine": "eggplant",
    "solanum melongena": "eggplant",
    "zucchini": "zucchini",
    "courgette": "zucchini",
    "cucurbita pepo": "zucchini",
    "cucumber": "cucumber",
    "cucumis sativus": "cucumber",
    "pumpkin": "pumpkin",
    "cucurbita maxima": "pumpkin",
    "squash": "squash",
    "butternut": "squash",
    "bean": "bean",
    "green bean": "bean",
    "phaseolus": "bean",
    "pea": "pea",
    "pisum sativum": "pea",
    "corn": "corn",
    "maize": "corn",
    "zea mays": "corn",
    "carrot": "carrot",
    "daucus carota": "carrot",
    "radish": "radish",
    "raphanus": "radish",
    "beet": "beet",
    "beetroot": "beet",
    "beta vulgaris": "beet",
    "turnip": "turnip",
    "brassica rapa": "turnip",
    "potato": "potato",
    "solanum tuberosum": "potato",
    "onion": "onion",
    "allium cepa": "onion",
    "garlic": "garlic",
    "allium sativum": "garlic",
    "leek": "leek",
    "allium ampeloprasum": "leek",
    "celery": "celery",
    "apium graveolens": "celery",
    "broccoli": "broccoli",
    "brassica oleracea": "broccoli",
    "cauliflower": "cauliflower",
    "cabbage": "cabbage",
    "kale": "kale",
    "spinach": "spinach",
    "spinacia oleracea": "spinach",
    "lettuce": "lettuce",
    "lactuca sativa": "lettuce",
    "arugula": "arugula",
    "rocket": "arugula",
    "eruca vesicaria": "arugula",
    "chard": "chard",
    "swiss chard": "chard",
    "artichoke": "artichoke",
    "cynara": "artichoke",
    "asparagus": "asparagus",
    "rhubarb": "rhubarb",
    "rheum": "rhubarb",
    "okra": "okra",
    "abelmoschus": "okra",
    # Herbs
    "basil": "basil",
    "ocimum basilicum": "basil",
    "rosemary": "rosemary",
    "salvia rosmarinus": "rosemary",
    "rosmarinus": "rosemary",
    "thyme": "thyme",
    "thymus": "thyme",
    "sage": "sage",
    "salvia officinalis": "sage",
    "mint": "mint",
    "mentha": "mint",
    "peppermint": "mint",
    "spearmint": "mint",
    "parsley": "parsley",
    "petroselinum": "parsley",
    "cilantro": "cilantro",
    "coriander": "cilantro",
    "coriandrum sativum": "cilantro",
    "dill": "dill",
    "anethum graveolens": "dill",
    "chives": "chives",
    "allium schoenoprasum": "chives",
    "oregano": "oregano",
    "origanum vulgare": "oregano",
    "tarragon": "tarragon",
    "artemisia dracunculus": "tarragon",
    "lemongrass": "lemongrass",
    "cymbopogon": "lemongrass",
    "chamomile": "chamomile",
    "matricaria chamomilla": "chamomile",
    "fennel": "fennel",
    "foeniculum vulgare": "fennel",
    "marjoram": "marjoram",
    "origanum majorana": "marjoram",
    "bay laurel": "bay_laurel",
    "bay": "bay_laurel",
    "laurus nobilis": "bay_laurel",
    "stevia": "stevia",
    "stevia rebaudiana": "stevia",
    "sorrel": "sorrel",
    "rumex acetosa": "sorrel",
    "borage": "borage",
    "borago officinalis": "borage",
    "lovage": "lovage",
    "levisticum officinale": "lovage",
    # Flowers
    "tulip": "tulip",
    "tulipa": "tulip",
    "daffodil": "daffodil",
    "narcissus": "daffodil",
    "dahlia": "dahlia",
    "peony": "peony",
    "paeonia": "peony",
    "iris": "iris",
    "lily": "lily",
    "lilium": "lily",
    "marigold": "marigold",
    "tagetes": "marigold",
    "zinnia": "zinnia",
    "cosmos": "cosmos",
    "aster": "aster",
    "chrysanthemum": "chrysanthemum",
    "mum": "chrysanthemum",
    "geranium": "geranium",
    "pelargonium": "geranium",
    "petunia": "petunia",
    "pansy": "pansy",
    "viola": "pansy",
    "hydrangea": "hydrangea",
    "clematis": "clematis",
    "wisteria": "wisteria",
    "jasmine": "jasmine",
    "jasminum": "jasmine",
    "hibiscus": "hibiscus",
    "crocus": "crocus",
    # Trees
    "pear": "pear_tree",
    "pear tree": "pear_tree",
    "pyrus": "pear_tree",
    "plum": "plum_tree",
    "plum tree": "plum_tree",
    "peach": "peach_tree",
    "peach tree": "peach_tree",
    "prunus persica": "peach_tree",
    "fig": "fig_tree",
    "fig tree": "fig_tree",
    "ficus carica": "fig_tree",
    "olive": "olive_tree",
    "olive tree": "olive_tree",
    "olea europaea": "olive_tree",
    "lemon": "lemon_tree",
    "lemon tree": "lemon_tree",
    "citrus limon": "lemon_tree",
    "orange": "orange_tree",
    "orange tree": "orange_tree",
    "citrus sinensis": "orange_tree",
    "walnut": "walnut_tree",
    "walnut tree": "walnut_tree",
    "juglans": "walnut_tree",
    "oak": "oak",
    "quercus": "oak",
    "maple": "maple",
    "acer": "maple",
    "birch": "birch",
    "betula": "birch",
    "willow": "willow",
    "salix": "willow",
    "magnolia": "magnolia",
    "pine": "pine",
    "pinus": "pine",
    "spruce": "spruce",
    "picea": "spruce",
    # Shrubs
    "blueberry": "blueberry",
    "vaccinium": "blueberry",
    "raspberry": "raspberry",
    "rubus idaeus": "raspberry",
    "blackberry": "blackberry",
    "rubus fruticosus": "blackberry",
    "gooseberry": "gooseberry",
    "ribes uva-crispa": "gooseberry",
    "currant": "currant",
    "ribes": "currant",
    "redcurrant": "currant",
    "blackcurrant": "currant",
    "holly": "holly",
    "ilex": "holly",
    "privet": "privet",
    "ligustrum": "privet",
    "juniper": "juniper",
    "juniperus": "juniper",
    "forsythia": "forsythia",
    "lilac": "lilac",
    "syringa": "lilac",
    "viburnum": "viburnum",
    "barberry": "barberry",
    "berberis": "barberry",
    "camellia": "camellia",
    "spirea": "spirea",
    "spiraea": "spirea",
    "elderberry": "elderberry",
    "sambucus": "elderberry",
    "elder": "elderberry",
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
_PIXMAP_CACHE_MAX = 500


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
    h = hashlib.md5(f"{item_id}:{seed_offset}".encode(), usedforsecurity=False).hexdigest()
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
