"""Tests for gallery panel."""

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.panels.gallery_panel import (
    GalleryCategory,
    GalleryItem,
    GalleryPanel,
    GalleryThumbnailButton,
    _build_gallery_categories,
    _render_svg_thumbnail,
)


def test_gallery_panel_creation(qtbot):  # noqa: ARG001
    """Test that a gallery panel can be created."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    assert panel is not None


def test_gallery_panel_has_categories(qtbot):  # noqa: ARG001
    """Test that the gallery panel has multiple categories."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    assert len(panel._categories) > 0
    assert len(panel._category_widgets) > 0


def test_gallery_panel_has_search_box(qtbot):  # noqa: ARG001
    """Test that the gallery panel has a search box."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    assert panel._search_box is not None
    assert panel._search_box.placeholderText() == "Search objects..."


def test_gallery_panel_has_category_dropdown(qtbot):  # noqa: ARG001
    """Test that the gallery panel has a category dropdown."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    assert panel._category_combo is not None
    # Should have "All Categories" + one for each category
    assert panel._category_combo.count() == len(panel._categories) + 1
    assert panel._category_combo.itemText(0) == "All Categories"


def test_gallery_panel_emits_tool_selected(qtbot):  # noqa: ARG001
    """Test that clicking a gallery item emits tool_selected signal."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    # Find a button and trigger it
    assert len(panel._all_buttons) > 0
    button = panel._all_buttons[0]
    signals = []
    panel.tool_selected.connect(lambda t: signals.append(t))
    button.clicked_item.emit(button._item)

    assert len(signals) == 1
    assert isinstance(signals[0], ToolType)


def test_gallery_panel_emits_item_selected(qtbot):  # noqa: ARG001
    """Test that clicking a gallery item emits item_selected signal."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    assert len(panel._all_buttons) > 0
    button = panel._all_buttons[0]
    items = []
    panel.item_selected.connect(lambda i: items.append(i))
    button.clicked_item.emit(button._item)

    assert len(items) == 1
    assert isinstance(items[0], GalleryItem)


def test_build_gallery_categories(qtbot):  # noqa: ARG001
    """Test that gallery categories are correctly built."""
    categories = _build_gallery_categories()

    assert len(categories) > 0

    # Check expected category names exist
    names = [c.name for c in categories]
    assert "Basic Shapes" in names
    assert "Trees" in names
    assert "Shrubs" in names
    assert "Flowers & Perennials" in names
    assert "Structures" in names
    assert "Paths & Surfaces" in names
    assert "Fences & Walls" in names


def test_gallery_categories_have_items(qtbot):  # noqa: ARG001
    """Test that every category has at least one item."""
    categories = _build_gallery_categories()

    for cat in categories:
        assert len(cat.items) > 0, f"Category '{cat.name}' has no items"


def test_gallery_items_have_tool_types(qtbot):  # noqa: ARG001
    """Test that every gallery item has a valid tool type."""
    categories = _build_gallery_categories()

    for cat in categories:
        for item in cat.items:
            assert item.tool_type is not None
            assert isinstance(item.tool_type, ToolType)


def test_gallery_items_have_names(qtbot):  # noqa: ARG001
    """Test that every gallery item has a non-empty name."""
    categories = _build_gallery_categories()

    for cat in categories:
        for item in cat.items:
            assert item.name, f"Item in '{cat.name}' has no name"


def test_gallery_tree_category_has_species(qtbot):  # noqa: ARG001
    """Test that the Trees category includes species-specific items."""
    categories = _build_gallery_categories()
    tree_cat = next(c for c in categories if c.name == "Trees")

    species_items = [i for i in tree_cat.items if i.species]
    assert len(species_items) >= 2  # Apple Tree, Cherry Tree


def test_gallery_flower_category_has_species(qtbot):  # noqa: ARG001
    """Test that Flowers & Perennials has species-specific items."""
    categories = _build_gallery_categories()
    flower_cat = next(c for c in categories if c.name == "Flowers & Perennials")

    species_items = [i for i in flower_cat.items if i.species]
    assert len(species_items) >= 3  # Rose, Lavender, Sunflower


def test_gallery_filter_by_search(qtbot):  # noqa: ARG001
    """Test that searching filters items correctly."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    # Set a search term
    panel._search_box.setText("Rose")

    # At least one button should not be hidden, many should be hidden
    not_hidden = sum(1 for btn in panel._all_buttons if not btn.isHidden())
    hidden_count = sum(1 for btn in panel._all_buttons if btn.isHidden())

    assert not_hidden >= 1
    assert hidden_count > 0


def test_gallery_filter_by_category(qtbot):  # noqa: ARG001
    """Test that selecting a category filters items."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    # Select "Trees" category (index 1)
    panel._category_combo.setCurrentIndex(1)

    # The Trees header should not be hidden
    header, grid = panel._category_widgets[0]
    assert not header.isHidden()
    assert not grid.isHidden()

    # Other categories should be hidden
    for i, (h, g) in enumerate(panel._category_widgets):
        if i > 0:
            assert h.isHidden()


def test_gallery_thumbnail_button_creation(qtbot):  # noqa: ARG001
    """Test that a thumbnail button can be created."""
    item = GalleryItem(
        name="Test Item",
        tool_type=ToolType.TREE,
    )
    button = GalleryThumbnailButton(item)
    qtbot.addWidget(button)

    assert button is not None
    assert button.toolTip() == "Test Item"


def test_gallery_thumbnail_button_emits_signal(qtbot):  # noqa: ARG001
    """Test that a thumbnail button emits clicked_item on click."""
    item = GalleryItem(
        name="Test Item",
        tool_type=ToolType.TREE,
    )
    button = GalleryThumbnailButton(item)
    qtbot.addWidget(button)

    clicked_items = []
    button.clicked_item.connect(lambda i: clicked_items.append(i))
    button.click()

    assert len(clicked_items) == 1
    assert clicked_items[0] is item


def test_gallery_clear_search_shows_all(qtbot):  # noqa: ARG001
    """Test that clearing the search box shows all items."""
    panel = GalleryPanel()
    qtbot.addWidget(panel)

    total = len(panel._all_buttons)

    # Filter then clear
    panel._search_box.setText("nonexistent_xyz")
    panel._search_box.setText("")

    not_hidden = sum(1 for btn in panel._all_buttons if not btn.isHidden())
    assert not_hidden == total
