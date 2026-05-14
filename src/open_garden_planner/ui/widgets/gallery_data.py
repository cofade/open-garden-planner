"""Gallery item/category data and thumbnail rendering helpers.

Single source of truth for gallery items, used by both the toolbar
category dropdowns and the global object search. Keeps the rendering
helpers and category-building logic out of any panel/widget class so
multiple call sites can share them.
"""

from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from open_garden_planner.core.fill_patterns import _TEXTURES_DIR, FillPattern
from open_garden_planner.core.furniture_renderer import (
    _FURNITURE_DIR,
    _FURNITURE_FILES,
    _INFRASTRUCTURE_DIR,
    _INFRASTRUCTURE_FILES,
)
from open_garden_planner.core.object_types import OBJECT_STYLES, ObjectType
from open_garden_planner.core.plant_renderer import (
    _CATEGORIES_DIR,
    _CATEGORY_FILES,
    _SPECIES_DIR,
    PlantCategory,
)
from open_garden_planner.core.tools import ToolType

THUMB_SIZE = 64

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons" / "tools"


class GalleryItem:
    """A single placeable object in the gallery."""

    def __init__(
        self,
        name: str,
        tool_type: ToolType,
        object_type: ObjectType | None = None,
        thumbnail: QPixmap | None = None,
        species: str = "",
        plant_category: PlantCategory | None = None,
    ) -> None:
        self.name = name
        self.tool_type = tool_type
        self.object_type = object_type
        self.thumbnail = thumbnail
        self.species = species
        self.plant_category = plant_category


class GalleryCategory:
    """A named group of gallery items.

    `icon_name` is the basename of the SVG file in resources/icons/tools/
    used by the toolbar button. Stored alongside the (translated) name so
    that icon lookup is locale-independent.
    """

    def __init__(
        self,
        name: str,
        items: list[GalleryItem],
        icon_name: str = "",
    ) -> None:
        self.name = name
        self.items = items
        self.icon_name = icon_name


def _tr(text: str) -> str:
    return QCoreApplication.translate("GalleryData", text)


def render_svg_thumbnail(svg_path: Path, size: int = THUMB_SIZE) -> QPixmap | None:
    """Render an SVG file to a square pixmap."""
    if not svg_path.exists():
        return None
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        return None
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


def render_texture_thumbnail(
    pattern: FillPattern, color: QColor, size: int = THUMB_SIZE
) -> QPixmap | None:
    """Render a rounded textured thumbnail for surfaces."""
    from open_garden_planner.core.fill_patterns import _TEXTURE_FILES

    filename = _TEXTURE_FILES.get(pattern)
    if filename is None:
        return None
    texture_path = _TEXTURES_DIR / f"{filename}.png"
    if not texture_path.exists():
        return None
    tex_pixmap = QPixmap(str(texture_path))
    if tex_pixmap.isNull():
        return None

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    clip_path = QPainterPath()
    clip_path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), 6, 6)
    painter.setClipPath(clip_path)
    scaled = tex_pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    painter.drawPixmap(0, 0, scaled)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    tint = QColor(color.red(), color.green(), color.blue(), 50)
    painter.fillRect(0, 0, size, size, tint)
    painter.end()
    return QPixmap.fromImage(image)


def render_tool_icon_thumbnail(icon_name: str, size: int = THUMB_SIZE) -> QPixmap | None:
    """Render a tool SVG icon (from resources/icons/tools/) as a thumbnail."""
    return render_svg_thumbnail(_ICONS_DIR / f"{icon_name}.svg", size)


def render_color_circle_thumbnail(color: QColor, size: int = THUMB_SIZE) -> QPixmap:
    """Fallback colored circle when no SVG/texture is available."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    pen_color = QColor(color.red() // 2, color.green() // 2, color.blue() // 2)
    painter.setPen(QPen(pen_color, 2))
    margin = 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()
    return QPixmap.fromImage(image)


def _shape_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    for name, tool, obj, icon in [
        (_tr("Rectangle"), ToolType.RECTANGLE, ObjectType.GENERIC_RECTANGLE, "rectangle"),
        (_tr("Polygon"), ToolType.POLYGON, ObjectType.GENERIC_POLYGON, "polygon"),
        (_tr("Circle"), ToolType.CIRCLE, ObjectType.GENERIC_CIRCLE, "circle"),
        (_tr("Ellipse"), ToolType.ELLIPSE, ObjectType.GENERIC_ELLIPSE, "ellipse"),
    ]:
        thumb = render_tool_icon_thumbnail(icon) or render_color_circle_thumbnail(
            OBJECT_STYLES[obj].fill_color
        )
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def _tree_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    for name, cat in [
        (_tr("Round Deciduous"), PlantCategory.ROUND_DECIDUOUS),
        (_tr("Columnar Tree"), PlantCategory.COLUMNAR_TREE),
        (_tr("Weeping Tree"), PlantCategory.WEEPING_TREE),
        (_tr("Conifer"), PlantCategory.CONIFER),
        (_tr("Fruit Tree"), PlantCategory.FRUIT_TREE),
        (_tr("Palm"), PlantCategory.PALM),
    ]:
        thumb = render_svg_thumbnail(_CATEGORIES_DIR / f"{_CATEGORY_FILES.get(cat, '')}.svg")
        items.append(GalleryItem(
            name=name, tool_type=ToolType.TREE, object_type=ObjectType.TREE,
            thumbnail=thumb, plant_category=cat,
        ))
    species = [
        ("Apple Tree", "apple_tree"), ("Cherry Tree", "cherry_tree"),
        ("Pear Tree", "pear_tree"), ("Plum Tree", "plum_tree"),
        ("Peach Tree", "peach_tree"), ("Fig Tree", "fig_tree"),
        ("Olive Tree", "olive_tree"), ("Lemon Tree", "lemon_tree"),
        ("Orange Tree", "orange_tree"), ("Walnut Tree", "walnut_tree"),
        ("Oak", "oak"), ("Maple", "maple"), ("Birch", "birch"),
        ("Willow", "willow"), ("Magnolia", "magnolia"),
        ("Pine", "pine"), ("Spruce", "spruce"),
    ]
    for species_name, svg_file in species:
        thumb = render_svg_thumbnail(_SPECIES_DIR / f"{svg_file}.svg")
        items.append(GalleryItem(
            name=_tr(species_name), tool_type=ToolType.TREE, object_type=ObjectType.TREE,
            thumbnail=thumb, species=svg_file.replace("_", " "),
        ))
    return items


def _shrub_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    for name, cat in [
        (_tr("Spreading Shrub"), PlantCategory.SPREADING_SHRUB),
        (_tr("Compact Shrub"), PlantCategory.COMPACT_SHRUB),
    ]:
        thumb = render_svg_thumbnail(_CATEGORIES_DIR / f"{_CATEGORY_FILES.get(cat, '')}.svg")
        items.append(GalleryItem(
            name=name, tool_type=ToolType.SHRUB, object_type=ObjectType.SHRUB,
            thumbnail=thumb, plant_category=cat,
        ))
    species = [
        ("Boxwood", "boxwood"), ("Rhododendron", "rhododendron"),
        ("Blueberry", "blueberry"), ("Raspberry", "raspberry"),
        ("Blackberry", "blackberry"), ("Gooseberry", "gooseberry"),
        ("Currant", "currant"), ("Holly", "holly"),
        ("Juniper", "juniper"), ("Forsythia", "forsythia"),
        ("Lilac", "lilac"), ("Elderberry", "elderberry"),
        ("Privet", "privet"), ("Viburnum", "viburnum"),
        ("Barberry", "barberry"), ("Camellia", "camellia"),
        ("Spirea", "spirea"),
    ]
    for species_name, svg_file in species:
        thumb = render_svg_thumbnail(_SPECIES_DIR / f"{svg_file}.svg")
        items.append(GalleryItem(
            name=_tr(species_name), tool_type=ToolType.SHRUB, object_type=ObjectType.SHRUB,
            thumbnail=thumb, species=svg_file.replace("_", " "),
        ))
    hedge_style = OBJECT_STYLES[ObjectType.HEDGE_POLYGON]
    items.append(GalleryItem(
        name=_tr("Hedge"), tool_type=ToolType.HEDGE_POLYGON, object_type=ObjectType.HEDGE_POLYGON,
        thumbnail=render_texture_thumbnail(FillPattern.HEDGE, hedge_style.fill_color),
    ))
    return items


def _flower_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    for name, cat in [
        (_tr("Flowering Perennial"), PlantCategory.FLOWERING_PERENNIAL),
        (_tr("Ornamental Grass"), PlantCategory.ORNAMENTAL_GRASS),
        (_tr("Ground Cover"), PlantCategory.GROUND_COVER),
        (_tr("Climbing Plant"), PlantCategory.CLIMBING_PLANT),
    ]:
        thumb = render_svg_thumbnail(_CATEGORIES_DIR / f"{_CATEGORY_FILES.get(cat, '')}.svg")
        items.append(GalleryItem(
            name=name, tool_type=ToolType.PERENNIAL, object_type=ObjectType.PERENNIAL,
            thumbnail=thumb, plant_category=cat,
        ))
    species = [
        ("Rose", "rose"), ("Lavender", "lavender"), ("Sunflower", "sunflower"),
        ("Tulip", "tulip"), ("Daffodil", "daffodil"), ("Dahlia", "dahlia"),
        ("Peony", "peony"), ("Iris", "iris"), ("Lily", "lily"),
        ("Marigold", "marigold"), ("Zinnia", "zinnia"), ("Cosmos", "cosmos"),
        ("Aster", "aster"), ("Chrysanthemum", "chrysanthemum"),
        ("Geranium", "geranium"), ("Petunia", "petunia"), ("Pansy", "pansy"),
        ("Hydrangea", "hydrangea"), ("Clematis", "clematis"),
        ("Wisteria", "wisteria"), ("Jasmine", "jasmine"),
        ("Hibiscus", "hibiscus"), ("Crocus", "crocus"),
    ]
    for species_name, svg_file in species:
        thumb = render_svg_thumbnail(_SPECIES_DIR / f"{svg_file}.svg")
        items.append(GalleryItem(
            name=_tr(species_name), tool_type=ToolType.PERENNIAL, object_type=ObjectType.PERENNIAL,
            thumbnail=thumb, species=svg_file.replace("_", " "),
        ))
    return items


def _veggie_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    for name, cat in [
        (_tr("Vegetable"), PlantCategory.VEGETABLE),
        (_tr("Herb"), PlantCategory.HERB),
    ]:
        thumb = render_svg_thumbnail(_CATEGORIES_DIR / f"{_CATEGORY_FILES.get(cat, '')}.svg")
        items.append(GalleryItem(
            name=name, tool_type=ToolType.PERENNIAL, object_type=ObjectType.PERENNIAL,
            thumbnail=thumb, plant_category=cat,
        ))
    species = [
        ("Tomato", "tomato"), ("Pepper", "pepper"), ("Eggplant", "eggplant"),
        ("Zucchini", "zucchini"), ("Cucumber", "cucumber"), ("Pumpkin", "pumpkin"),
        ("Bean", "bean"), ("Pea", "pea"), ("Corn", "corn"),
        ("Carrot", "carrot"), ("Radish", "radish"), ("Potato", "potato"),
        ("Onion", "onion"), ("Garlic", "garlic"), ("Lettuce", "lettuce"),
        ("Spinach", "spinach"), ("Cabbage", "cabbage"), ("Kale", "kale"),
        ("Broccoli", "broccoli"), ("Basil", "basil"), ("Rosemary", "rosemary"),
        ("Thyme", "thyme"), ("Sage", "sage"), ("Mint", "mint"),
        ("Parsley", "parsley"), ("Cilantro", "cilantro"), ("Dill", "dill"),
        ("Chives", "chives"), ("Oregano", "oregano"),
    ]
    for species_name, svg_file in species:
        thumb = render_svg_thumbnail(_SPECIES_DIR / f"{svg_file}.svg")
        items.append(GalleryItem(
            name=_tr(species_name), tool_type=ToolType.PERENNIAL, object_type=ObjectType.PERENNIAL,
            thumbnail=thumb, species=svg_file.replace("_", " "),
        ))
    return items


def _structure_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    structures = [
        (_tr("House"), ToolType.HOUSE, ObjectType.HOUSE, "house", FillPattern.ROOF_TILES),
        (_tr("Garage/Shed"), ToolType.GARAGE_SHED, ObjectType.GARAGE_SHED, "shed", FillPattern.CONCRETE),
        (_tr("Greenhouse"), ToolType.GREENHOUSE, ObjectType.GREENHOUSE, "greenhouse", FillPattern.GLASS),
    ]
    for name, tool, obj, icon, pattern in structures:
        style = OBJECT_STYLES[obj]
        thumb = render_tool_icon_thumbnail(icon) or render_texture_thumbnail(pattern, style.fill_color)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def _furniture_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    furniture = [
        (_tr("Table (Rect.)"), ToolType.TABLE_RECTANGULAR, ObjectType.TABLE_RECTANGULAR),
        (_tr("Table (Round)"), ToolType.TABLE_ROUND, ObjectType.TABLE_ROUND),
        (_tr("Chair"), ToolType.CHAIR, ObjectType.CHAIR),
        (_tr("Bench"), ToolType.BENCH, ObjectType.BENCH),
        (_tr("Parasol"), ToolType.PARASOL, ObjectType.PARASOL),
        (_tr("Lounger"), ToolType.LOUNGER, ObjectType.LOUNGER),
        (_tr("BBQ/Grill"), ToolType.BBQ_GRILL, ObjectType.BBQ_GRILL),
        (_tr("Fire Pit"), ToolType.FIRE_PIT, ObjectType.FIRE_PIT),
    ]
    for name, tool, obj in furniture:
        svg_filename = _FURNITURE_FILES.get(obj, "")
        thumb = render_svg_thumbnail(_FURNITURE_DIR / f"{svg_filename}.svg")
        if thumb is None:
            thumb = render_color_circle_thumbnail(OBJECT_STYLES[obj].fill_color)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def _bed_and_surface_items() -> list[GalleryItem]:
    """Combined beds/surfaces: Paths&Surfaces plus the bed-shaped infrastructure items."""
    items: list[GalleryItem] = []
    surfaces = [
        (_tr("Garden Bed"), ToolType.GARDEN_BED, ObjectType.GARDEN_BED, "garden_bed", FillPattern.SOIL),
        (_tr("Lawn"), ToolType.LAWN, ObjectType.LAWN, "lawn", FillPattern.GRASS),
        (_tr("Terrace/Patio"), ToolType.TERRACE_PATIO, ObjectType.TERRACE_PATIO, "terrace", FillPattern.WOOD),
        (_tr("Driveway"), ToolType.DRIVEWAY, ObjectType.DRIVEWAY, "driveway", FillPattern.GRAVEL),
        (_tr("Pond/Pool"), ToolType.POND_POOL, ObjectType.POND_POOL, "pond", FillPattern.WATER),
    ]
    for name, tool, obj, icon, pattern in surfaces:
        style = OBJECT_STYLES[obj]
        thumb = render_texture_thumbnail(pattern, style.fill_color) or render_tool_icon_thumbnail(icon)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    bed_infra = [
        (_tr("Raised Bed"), ToolType.RAISED_BED, ObjectType.RAISED_BED),
        (_tr("Cold Frame"), ToolType.COLD_FRAME, ObjectType.COLD_FRAME),
    ]
    for name, tool, obj in bed_infra:
        svg_filename = _INFRASTRUCTURE_FILES.get(obj, "")
        thumb = render_svg_thumbnail(_INFRASTRUCTURE_DIR / f"{svg_filename}.svg")
        if thumb is None:
            thumb = render_color_circle_thumbnail(OBJECT_STYLES[obj].fill_color)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def _fence_items() -> list[GalleryItem]:
    items: list[GalleryItem] = []
    fences = [
        (_tr("Fence"), ToolType.FENCE, ObjectType.FENCE, "fence"),
        (_tr("Wall"), ToolType.WALL, ObjectType.WALL, "wall"),
        (_tr("Path"), ToolType.PATH, ObjectType.PATH, "path"),
    ]
    for name, tool, obj, icon in fences:
        thumb = render_tool_icon_thumbnail(icon)
        if thumb is None:
            thumb = render_color_circle_thumbnail(OBJECT_STYLES[obj].stroke_color)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def _infrastructure_items() -> list[GalleryItem]:
    """Garden infrastructure minus the bed-shaped items (which moved to Beds & Surfaces)."""
    items: list[GalleryItem] = []
    objects = [
        (_tr("Planter/Pot"), ToolType.PLANTER_POT, ObjectType.PLANTER_POT, _FURNITURE_DIR, _FURNITURE_FILES),
        (_tr("Compost Bin"), ToolType.COMPOST_BIN, ObjectType.COMPOST_BIN, _INFRASTRUCTURE_DIR, _INFRASTRUCTURE_FILES),
        (_tr("Rain Barrel"), ToolType.RAIN_BARREL, ObjectType.RAIN_BARREL, _INFRASTRUCTURE_DIR, _INFRASTRUCTURE_FILES),
        (_tr("Water Tap"), ToolType.WATER_TAP, ObjectType.WATER_TAP, _INFRASTRUCTURE_DIR, _INFRASTRUCTURE_FILES),
        (_tr("Tool Shed"), ToolType.TOOL_SHED, ObjectType.TOOL_SHED, _INFRASTRUCTURE_DIR, _INFRASTRUCTURE_FILES),
    ]
    for name, tool, obj, svg_dir, files_map in objects:
        svg_filename = files_map.get(obj, "")
        thumb = render_svg_thumbnail(svg_dir / f"{svg_filename}.svg")
        if thumb is None:
            thumb = render_color_circle_thumbnail(OBJECT_STYLES[obj].fill_color)
        items.append(GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb))
    return items


def build_toolbar_categories() -> list[GalleryCategory]:
    """Build the 10 toolbar categories that drive the category dropdowns.

    Order is by expected frequency of use. Each category maps 1:1 to a
    toolbar button and a Sims-style dropdown palette. The icon_name is the
    basename of an SVG in resources/icons/tools/.
    """
    return [
        GalleryCategory(_tr("Beds & Surfaces"), _bed_and_surface_items(), "garden_bed"),
        GalleryCategory(_tr("Basic Shapes"), _shape_items(), "rectangle"),
        GalleryCategory(_tr("Trees"), _tree_items(), "tree"),
        GalleryCategory(_tr("Shrubs & Hedges"), _shrub_items(), "shrub"),
        GalleryCategory(_tr("Flowers & Perennials"), _flower_items(), "flower"),
        GalleryCategory(_tr("Vegetables & Herbs"), _veggie_items(), "vegetable"),
        GalleryCategory(_tr("Structures"), _structure_items(), "house"),
        GalleryCategory(_tr("Furniture"), _furniture_items(), "furniture"),
        GalleryCategory(_tr("Fences & Walls"), _fence_items(), "fence"),
        GalleryCategory(_tr("Infrastructure"), _infrastructure_items(), "infrastructure"),
    ]


def all_items(categories: list[GalleryCategory]) -> list[GalleryItem]:
    """Flatten all items from all categories. Used for global search."""
    return [item for cat in categories for item in cat.items]
