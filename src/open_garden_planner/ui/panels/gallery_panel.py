"""Visual thumbnail gallery sidebar for placing objects and plants.

Displays categorized thumbnails showing SVG illustrations and texture
previews. Supports click-to-select-and-place and search/filter.
"""

from pathlib import Path

from PyQt6.QtCore import QMimeData, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDrag,
    QImage,
    QPainter,
    QPixmap,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.fill_patterns import _TEXTURES_DIR, FillPattern
from open_garden_planner.core.object_types import OBJECT_STYLES, ObjectType
from open_garden_planner.core.plant_renderer import (
    _CATEGORIES_DIR,
    _CATEGORY_FILES,
    _SPECIES_DIR,
    PlantCategory,
)
from open_garden_planner.core.tools import ToolType

# Thumbnail size in pixels
THUMB_SIZE = 64
# Number of columns in the grid
GRID_COLS = 3

# Icons directory for tool SVGs
_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons" / "tools"


class GalleryCategory:
    """Definition of a gallery category with its items."""

    def __init__(self, name: str, items: list["GalleryItem"]) -> None:
        self.name = name
        self.items = items


class GalleryItem:
    """A single item in the gallery that can be placed on the canvas."""

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


def _render_svg_thumbnail(svg_path: Path, size: int = THUMB_SIZE) -> QPixmap | None:
    """Render an SVG file to a thumbnail pixmap.

    Args:
        svg_path: Path to the SVG file
        size: Target size in pixels

    Returns:
        QPixmap or None if the file cannot be loaded
    """
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


def _render_texture_thumbnail(
    pattern: FillPattern, color: QColor, size: int = THUMB_SIZE
) -> QPixmap | None:
    """Render a texture pattern to a rounded thumbnail pixmap.

    Args:
        pattern: The fill pattern to render
        color: Tint color
        size: Target size in pixels

    Returns:
        QPixmap or None
    """
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

    # Create a square thumbnail from the texture
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Draw rounded rect clip
    from PyQt6.QtGui import QPainterPath

    clip_path = QPainterPath()
    clip_path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), 6, 6)
    painter.setClipPath(clip_path)
    # Tile the texture into the thumbnail
    scaled = tex_pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    painter.drawPixmap(0, 0, scaled)
    # Apply a subtle color tint
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    tint = QColor(color.red(), color.green(), color.blue(), 50)
    painter.fillRect(0, 0, size, size, tint)
    painter.end()
    return QPixmap.fromImage(image)


def _render_tool_icon_thumbnail(icon_name: str, size: int = THUMB_SIZE) -> QPixmap | None:
    """Render a tool SVG icon to a thumbnail pixmap.

    Args:
        icon_name: Name of the SVG file (without extension)
        size: Target size in pixels

    Returns:
        QPixmap or None
    """
    svg_path = _ICONS_DIR / f"{icon_name}.svg"
    return _render_svg_thumbnail(svg_path, size)


def _render_color_circle_thumbnail(
    color: QColor, size: int = THUMB_SIZE
) -> QPixmap:
    """Render a colored circle as a fallback thumbnail.

    Args:
        color: Fill color
        size: Target size

    Returns:
        QPixmap with a colored circle
    """
    from PyQt6.QtGui import QPen

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


def _build_gallery_categories() -> list[GalleryCategory]:
    """Build all gallery categories with items and thumbnails.

    Returns:
        List of GalleryCategory instances
    """
    categories: list[GalleryCategory] = []

    # --- Basic Shapes ---
    shape_items: list[GalleryItem] = []
    shapes = [
        ("Rectangle", ToolType.RECTANGLE, ObjectType.GENERIC_RECTANGLE, "rectangle"),
        ("Polygon", ToolType.POLYGON, ObjectType.GENERIC_POLYGON, "polygon"),
        ("Circle", ToolType.CIRCLE, ObjectType.GENERIC_CIRCLE, "circle"),
    ]
    for name, tool, obj, icon in shapes:
        style = OBJECT_STYLES[obj]
        thumb = _render_tool_icon_thumbnail(icon)
        if thumb is None:
            thumb = _render_color_circle_thumbnail(style.fill_color)
        shape_items.append(
            GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb)
        )
    categories.append(GalleryCategory("Basic Shapes", shape_items))

    # --- Trees ---
    tree_items: list[GalleryItem] = []
    tree_categories = [
        ("Round Deciduous", PlantCategory.ROUND_DECIDUOUS),
        ("Columnar Tree", PlantCategory.COLUMNAR_TREE),
        ("Weeping Tree", PlantCategory.WEEPING_TREE),
        ("Conifer", PlantCategory.CONIFER),
        ("Fruit Tree", PlantCategory.FRUIT_TREE),
        ("Palm", PlantCategory.PALM),
    ]
    for name, cat in tree_categories:
        filename = _CATEGORY_FILES.get(cat, "")
        svg_path = _CATEGORIES_DIR / f"{filename}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        tree_items.append(
            GalleryItem(
                name=name,
                tool_type=ToolType.TREE,
                object_type=ObjectType.TREE,
                thumbnail=thumb,
                plant_category=cat,
            )
        )
    # Species-specific trees
    for species_name, svg_file in [
        ("Apple Tree", "apple_tree"),
        ("Cherry Tree", "cherry_tree"),
    ]:
        svg_path = _SPECIES_DIR / f"{svg_file}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        tree_items.append(
            GalleryItem(
                name=species_name,
                tool_type=ToolType.TREE,
                object_type=ObjectType.TREE,
                thumbnail=thumb,
                species=species_name.lower(),
            )
        )
    categories.append(GalleryCategory("Trees", tree_items))

    # --- Shrubs ---
    shrub_items: list[GalleryItem] = []
    shrub_categories = [
        ("Spreading Shrub", PlantCategory.SPREADING_SHRUB),
        ("Compact Shrub", PlantCategory.COMPACT_SHRUB),
        ("Hedge Section", PlantCategory.HEDGE_SECTION),
    ]
    for name, cat in shrub_categories:
        filename = _CATEGORY_FILES.get(cat, "")
        svg_path = _CATEGORIES_DIR / f"{filename}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        shrub_items.append(
            GalleryItem(
                name=name,
                tool_type=ToolType.SHRUB,
                object_type=ObjectType.SHRUB,
                thumbnail=thumb,
                plant_category=cat,
            )
        )
    for species_name, svg_file in [
        ("Boxwood", "boxwood"),
        ("Rhododendron", "rhododendron"),
    ]:
        svg_path = _SPECIES_DIR / f"{svg_file}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        shrub_items.append(
            GalleryItem(
                name=species_name,
                tool_type=ToolType.SHRUB,
                object_type=ObjectType.SHRUB,
                thumbnail=thumb,
                species=species_name.lower(),
            )
        )
    categories.append(GalleryCategory("Shrubs", shrub_items))

    # --- Flowers & Perennials ---
    flower_items: list[GalleryItem] = []
    flower_categories = [
        ("Flowering Perennial", PlantCategory.FLOWERING_PERENNIAL),
        ("Ornamental Grass", PlantCategory.ORNAMENTAL_GRASS),
        ("Ground Cover", PlantCategory.GROUND_COVER),
        ("Climbing Plant", PlantCategory.CLIMBING_PLANT),
    ]
    for name, cat in flower_categories:
        filename = _CATEGORY_FILES.get(cat, "")
        svg_path = _CATEGORIES_DIR / f"{filename}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        flower_items.append(
            GalleryItem(
                name=name,
                tool_type=ToolType.PERENNIAL,
                object_type=ObjectType.PERENNIAL,
                thumbnail=thumb,
                plant_category=cat,
            )
        )
    for species_name, svg_file in [
        ("Rose", "rose"),
        ("Lavender", "lavender"),
        ("Sunflower", "sunflower"),
    ]:
        svg_path = _SPECIES_DIR / f"{svg_file}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        flower_items.append(
            GalleryItem(
                name=species_name,
                tool_type=ToolType.PERENNIAL,
                object_type=ObjectType.PERENNIAL,
                thumbnail=thumb,
                species=species_name.lower(),
            )
        )
    categories.append(GalleryCategory("Flowers & Perennials", flower_items))

    # --- Vegetables & Herbs ---
    veg_items: list[GalleryItem] = []
    veg_categories = [
        ("Vegetable", PlantCategory.VEGETABLE),
        ("Herb", PlantCategory.HERB),
    ]
    for name, cat in veg_categories:
        filename = _CATEGORY_FILES.get(cat, "")
        svg_path = _CATEGORIES_DIR / f"{filename}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        veg_items.append(
            GalleryItem(
                name=name,
                tool_type=ToolType.PERENNIAL,
                object_type=ObjectType.PERENNIAL,
                thumbnail=thumb,
                plant_category=cat,
            )
        )
    for species_name, svg_file in [("Tomato", "tomato")]:
        svg_path = _SPECIES_DIR / f"{svg_file}.svg"
        thumb = _render_svg_thumbnail(svg_path)
        veg_items.append(
            GalleryItem(
                name=species_name,
                tool_type=ToolType.PERENNIAL,
                object_type=ObjectType.PERENNIAL,
                thumbnail=thumb,
                species=species_name.lower(),
            )
        )
    categories.append(GalleryCategory("Vegetables & Herbs", veg_items))

    # --- Structures ---
    structure_items: list[GalleryItem] = []
    structures = [
        ("House", ToolType.HOUSE, ObjectType.HOUSE, "house", FillPattern.ROOF_TILES),
        ("Garage/Shed", ToolType.GARAGE_SHED, ObjectType.GARAGE_SHED, "shed", FillPattern.CONCRETE),
        ("Greenhouse", ToolType.GREENHOUSE, ObjectType.GREENHOUSE, "greenhouse", FillPattern.GLASS),
    ]
    for name, tool, obj, icon, pattern in structures:
        style = OBJECT_STYLES[obj]
        thumb = _render_tool_icon_thumbnail(icon)
        if thumb is None:
            thumb = _render_texture_thumbnail(pattern, style.fill_color)
        structure_items.append(
            GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb)
        )
    categories.append(GalleryCategory("Structures", structure_items))

    # --- Paths & Surfaces ---
    surface_items: list[GalleryItem] = []
    surfaces = [
        ("Terrace/Patio", ToolType.TERRACE_PATIO, ObjectType.TERRACE_PATIO, "terrace", FillPattern.WOOD),
        ("Driveway", ToolType.DRIVEWAY, ObjectType.DRIVEWAY, "driveway", FillPattern.GRAVEL),
        ("Garden Bed", ToolType.GARDEN_BED, ObjectType.GARDEN_BED, "garden_bed", FillPattern.SOIL),
        ("Pond/Pool", ToolType.POND_POOL, ObjectType.POND_POOL, "pond", FillPattern.WATER),
    ]
    for name, tool, obj, icon, pattern in surfaces:
        style = OBJECT_STYLES[obj]
        thumb = _render_texture_thumbnail(pattern, style.fill_color)
        if thumb is None:
            thumb = _render_tool_icon_thumbnail(icon)
        surface_items.append(
            GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb)
        )
    categories.append(GalleryCategory("Paths & Surfaces", surface_items))

    # --- Fences & Walls ---
    fence_items: list[GalleryItem] = []
    fences = [
        ("Fence", ToolType.FENCE, ObjectType.FENCE, "fence"),
        ("Wall", ToolType.WALL, ObjectType.WALL, "wall"),
        ("Path", ToolType.PATH, ObjectType.PATH, "path"),
    ]
    for name, tool, obj, icon in fences:
        thumb = _render_tool_icon_thumbnail(icon)
        if thumb is None:
            style = OBJECT_STYLES[obj]
            thumb = _render_color_circle_thumbnail(style.stroke_color)
        fence_items.append(
            GalleryItem(name=name, tool_type=tool, object_type=obj, thumbnail=thumb)
        )
    categories.append(GalleryCategory("Fences & Walls", fence_items))

    return categories


class GalleryThumbnailButton(QToolButton):
    """A single thumbnail button in the gallery grid.

    Shows an SVG/texture preview and name label. Supports click and drag.
    """

    clicked_item = pyqtSignal(object)  # Emits the GalleryItem

    def __init__(self, item: GalleryItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item
        self._drag_start_pos: QPoint | None = None

        self.setFixedSize(THUMB_SIZE + 16, THUMB_SIZE + 24)
        self.setToolTip(item.name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(False)

        # Build layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Thumbnail image
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        if item.thumbnail and not item.thumbnail.isNull():
            scaled = item.thumbnail.scaled(
                THUMB_SIZE - 4,
                THUMB_SIZE - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet("color: palette(mid); font-size: 20px;")
        layout.addWidget(thumb_label)

        # Name label
        name_label = QLabel(item.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 9px;")
        name_label.setMaximumHeight(20)
        layout.addWidget(name_label)

        # Style
        self.setStyleSheet("""
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                background: transparent;
                padding: 2px;
            }
            QToolButton:hover {
                border: 1px solid palette(highlight);
                background: palette(midlight);
            }
            QToolButton:pressed {
                background: palette(mid);
            }
        """)

        # Connect the standard clicked signal to emit our custom signal
        self.clicked.connect(lambda: self.clicked_item.emit(self._item))

    def mousePressEvent(self, event) -> None:
        """Handle mouse press for drag initiation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move for drag-to-canvas."""
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_start_pos is None:
            return
        # Check if drag threshold exceeded
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        # Encode item info for the canvas to interpret
        drag_data = f"gallery:{self._item.tool_type.name}"
        if self._item.species:
            drag_data += f":species={self._item.species}"
        if self._item.plant_category:
            drag_data += f":category={self._item.plant_category.name}"
        mime_data.setText(drag_data)
        drag.setMimeData(mime_data)

        # Set drag pixmap
        if self._item.thumbnail and not self._item.thumbnail.isNull():
            drag_pixmap = self._item.thumbnail.scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(drag_pixmap)
            drag.setHotSpot(QPoint(24, 24))

        drag.exec(Qt.DropAction.CopyAction)


class GalleryPanel(QWidget):
    """Visual thumbnail gallery sidebar panel.

    Shows categorized thumbnails of plants, structures, and surfaces.
    Supports search/filter and click-to-place or drag-to-canvas.
    """

    tool_selected = pyqtSignal(ToolType)
    item_selected = pyqtSignal(object)  # Emits the GalleryItem

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._categories = _build_gallery_categories()
        self._all_buttons: list[GalleryThumbnailButton] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search/filter box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search objects...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._search_box)

        # Category dropdown
        self._category_combo = QComboBox()
        self._category_combo.addItem("All Categories")
        for cat in self._categories:
            self._category_combo.addItem(cat.name)
        self._category_combo.currentIndexChanged.connect(self._on_category_changed)
        layout.addWidget(self._category_combo)

        # Scrollable area for thumbnails
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(8)

        self._build_gallery_grid()

        self._scroll_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll)

    def _build_gallery_grid(self) -> None:
        """Build the full gallery grid with all categories."""
        self._category_widgets: list[tuple[QLabel, QWidget]] = []
        self._all_buttons.clear()

        for cat in self._categories:
            # Category header
            header = QLabel(cat.name)
            header.setStyleSheet("font-weight: bold; font-size: 11px; padding: 2px 0;")
            self._scroll_layout.addWidget(header)

            # Grid container
            grid_widget = QWidget()
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(4)

            for i, item in enumerate(cat.items):
                row = i // GRID_COLS
                col = i % GRID_COLS
                btn = GalleryThumbnailButton(item)
                btn.clicked_item.connect(self._on_item_clicked)
                grid_layout.addWidget(btn, row, col)
                self._all_buttons.append(btn)

            self._scroll_layout.addWidget(grid_widget)
            self._category_widgets.append((header, grid_widget))

    def _on_item_clicked(self, item: GalleryItem) -> None:
        """Handle gallery item click - activate the corresponding tool.

        Args:
            item: The clicked gallery item
        """
        self.tool_selected.emit(item.tool_type)
        self.item_selected.emit(item)

    def _on_category_changed(self) -> None:
        """Handle category dropdown change."""
        self._apply_filters()

    def _on_filter_changed(self) -> None:
        """Handle search box text change."""
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply category and search filters to show/hide items."""
        selected_cat_index = self._category_combo.currentIndex()
        search_text = self._search_box.text().strip().lower()

        for cat_index, (header, grid_widget) in enumerate(self._category_widgets):
            # Check category filter (index 0 = All)
            cat_visible = selected_cat_index == 0 or selected_cat_index == cat_index + 1

            if not cat_visible:
                header.setVisible(False)
                grid_widget.setVisible(False)
                continue

            # Check search filter on individual items within the category
            grid_layout = grid_widget.layout()
            any_visible = False

            for i in range(grid_layout.count()):
                widget = grid_layout.itemAt(i).widget()
                if isinstance(widget, GalleryThumbnailButton):
                    visible = search_text in widget._item.name.lower() if search_text else True
                    widget.setVisible(visible)
                    if visible:
                        any_visible = True

            header.setVisible(any_visible)
            grid_widget.setVisible(any_visible)
