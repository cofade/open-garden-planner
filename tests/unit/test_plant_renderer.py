"""Unit tests for plant SVG rendering system (US-6.2)."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QPixmap

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_renderer import (
    PlantCategory,
    _CATEGORIES_DIR,
    _SPECIES_DIR,
    _resolve_svg_path,
    _stable_random_for_item,
    clear_plant_cache,
    get_all_categories,
    get_default_category,
    get_species_names,
    is_plant_type,
    render_plant_pixmap,
)


class TestPlantCategoryEnum:
    """Tests for PlantCategory enum members."""

    def test_all_15_categories_exist(self, qtbot: object) -> None:  # noqa: ARG002
        expected = [
            "ROUND_DECIDUOUS", "COLUMNAR_TREE", "WEEPING_TREE", "CONIFER",
            "SPREADING_SHRUB", "COMPACT_SHRUB", "ORNAMENTAL_GRASS",
            "FLOWERING_PERENNIAL", "GROUND_COVER", "CLIMBING_PLANT",
            "HEDGE_SECTION", "VEGETABLE", "HERB", "FRUIT_TREE", "PALM",
        ]
        for name in expected:
            assert hasattr(PlantCategory, name), f"Missing category: {name}"

    def test_category_count(self, qtbot: object) -> None:  # noqa: ARG002
        assert len(PlantCategory) == 15


class TestPlantSVGFiles:
    """Tests for plant SVG file existence."""

    @pytest.mark.parametrize(
        "filename",
        [
            "round_deciduous", "columnar_tree", "weeping_tree", "conifer",
            "spreading_shrub", "compact_shrub", "ornamental_grass",
            "flowering_perennial", "ground_cover", "climbing_plant",
            "hedge_section", "vegetable", "herb", "fruit_tree", "palm",
        ],
    )
    def test_category_svg_exists(self, filename: str) -> None:
        path = _CATEGORIES_DIR / f"{filename}.svg"
        assert path.exists(), f"Category SVG missing: {filename}.svg"
        assert path.is_file()
        assert path.stat().st_size > 0

    @pytest.mark.parametrize(
        "filename",
        [
            "rose", "lavender", "apple_tree", "cherry_tree",
            "sunflower", "tomato", "boxwood", "rhododendron",
        ],
    )
    def test_species_svg_exists(self, filename: str) -> None:
        path = _SPECIES_DIR / f"{filename}.svg"
        assert path.exists(), f"Species SVG missing: {filename}.svg"
        assert path.is_file()
        assert path.stat().st_size > 0

    @pytest.mark.parametrize(
        "filename",
        [
            "round_deciduous", "columnar_tree", "conifer", "spreading_shrub",
            "flowering_perennial", "rose", "lavender", "sunflower",
        ],
    )
    def test_svg_has_valid_header(self, filename: str) -> None:
        # Check categories first, then species
        path = _CATEGORIES_DIR / f"{filename}.svg"
        if not path.exists():
            path = _SPECIES_DIR / f"{filename}.svg"
        content = path.read_text(encoding="utf-8")
        assert "<svg" in content, f"{filename}.svg is not valid SVG"
        assert "</svg>" in content


class TestIsPlantType:
    """Tests for is_plant_type helper."""

    def test_tree_is_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(ObjectType.TREE) is True

    def test_shrub_is_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(ObjectType.SHRUB) is True

    def test_perennial_is_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(ObjectType.PERENNIAL) is True

    def test_house_is_not_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(ObjectType.HOUSE) is False

    def test_generic_circle_is_not_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(ObjectType.GENERIC_CIRCLE) is False

    def test_none_is_not_plant(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_plant_type(None) is False


class TestDefaultCategory:
    """Tests for ObjectType to PlantCategory mapping."""

    def test_tree_default_is_round_deciduous(self, qtbot: object) -> None:  # noqa: ARG002
        assert get_default_category(ObjectType.TREE) == PlantCategory.ROUND_DECIDUOUS

    def test_shrub_default_is_spreading_shrub(self, qtbot: object) -> None:  # noqa: ARG002
        assert get_default_category(ObjectType.SHRUB) == PlantCategory.SPREADING_SHRUB

    def test_perennial_default_is_flowering_perennial(self, qtbot: object) -> None:  # noqa: ARG002
        assert get_default_category(ObjectType.PERENNIAL) == PlantCategory.FLOWERING_PERENNIAL

    def test_non_plant_returns_none(self, qtbot: object) -> None:  # noqa: ARG002
        assert get_default_category(ObjectType.HOUSE) is None


class TestResolveSvgPath:
    """Tests for SVG path resolution logic."""

    def test_tree_default_resolves(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.TREE)
        assert path is not None
        assert path.name == "round_deciduous.svg"

    def test_species_takes_priority(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.SHRUB, species="rose")
        assert path is not None
        assert path.name == "rose.svg"

    def test_category_takes_priority_over_default(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.TREE, category=PlantCategory.CONIFER)
        assert path is not None
        assert path.name == "conifer.svg"

    def test_species_partial_match(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.TREE, species="Cherry Blossom")
        assert path is not None
        assert path.name == "cherry_tree.svg"

    def test_non_plant_returns_none(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.HOUSE)
        assert path is None

    def test_unknown_species_falls_back_to_category(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(
            ObjectType.TREE, species="Unknown Plant XYZ",
            category=PlantCategory.CONIFER,
        )
        assert path is not None
        assert path.name == "conifer.svg"

    def test_unknown_species_falls_back_to_default(self, qtbot: object) -> None:  # noqa: ARG002
        path = _resolve_svg_path(ObjectType.TREE, species="Unknown Plant XYZ")
        assert path is not None
        assert path.name == "round_deciduous.svg"


class TestStableRandom:
    """Tests for stable randomization."""

    def test_same_id_gives_same_result(self, qtbot: object) -> None:  # noqa: ARG002
        r1 = _stable_random_for_item("test-id-123")
        r2 = _stable_random_for_item("test-id-123")
        assert r1 == r2

    def test_different_ids_give_different_results(self, qtbot: object) -> None:  # noqa: ARG002
        r1 = _stable_random_for_item("id-a")
        r2 = _stable_random_for_item("id-b")
        assert r1 != r2

    def test_different_offsets_give_different_results(self, qtbot: object) -> None:  # noqa: ARG002
        r1 = _stable_random_for_item("same-id", seed_offset=0)
        r2 = _stable_random_for_item("same-id", seed_offset=1)
        assert r1 != r2

    def test_result_in_range(self, qtbot: object) -> None:  # noqa: ARG002
        r = _stable_random_for_item("any-id")
        assert 0.0 <= r <= 1.0


class TestRenderPlantPixmap:
    """Tests for SVG to QPixmap rendering."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        clear_plant_cache()
        yield  # type: ignore[misc]
        clear_plant_cache()

    def test_render_tree_returns_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(ObjectType.TREE, diameter=100.0)
        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert not pixmap.isNull()
        assert pixmap.width() == 100
        assert pixmap.height() == 100

    def test_render_shrub_returns_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(ObjectType.SHRUB, diameter=80.0)
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_render_perennial_returns_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(ObjectType.PERENNIAL, diameter=60.0)
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_render_non_plant_returns_none(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(ObjectType.HOUSE, diameter=100.0)
        assert pixmap is None

    def test_render_with_species(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=100.0, species="rose",
        )
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_render_with_category(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(
            ObjectType.TREE, diameter=100.0,
            category=PlantCategory.CONIFER,
        )
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_render_with_tint(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(
            ObjectType.TREE, diameter=100.0,
            tint_color=QColor(200, 100, 50, 100),
        )
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_caching_returns_same_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        p1 = render_plant_pixmap(
            ObjectType.TREE, diameter=100.0, item_id="test-cache",
        )
        p2 = render_plant_pixmap(
            ObjectType.TREE, diameter=100.0, item_id="test-cache",
        )
        assert p1 is p2  # Same object from cache

    def test_different_sizes_different_pixmaps(self, qtbot: object) -> None:  # noqa: ARG002
        p1 = render_plant_pixmap(ObjectType.TREE, diameter=50.0, item_id="id1")
        p2 = render_plant_pixmap(ObjectType.TREE, diameter=100.0, item_id="id1")
        assert p1 is not None
        assert p2 is not None
        assert p1.width() != p2.width()

    def test_minimum_size_clamped(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_plant_pixmap(ObjectType.TREE, diameter=1.0)
        assert pixmap is not None
        assert pixmap.width() >= 4

    def test_render_all_categories(self, qtbot: object) -> None:  # noqa: ARG002
        """Verify every category SVG renders without error."""
        for cat in PlantCategory:
            pixmap = render_plant_pixmap(
                ObjectType.TREE, diameter=64.0, category=cat,
            )
            assert pixmap is not None, f"Failed to render category: {cat.name}"
            assert not pixmap.isNull()

    def test_render_all_species(self, qtbot: object) -> None:  # noqa: ARG002
        """Verify all species SVGs render without error."""
        species_list = [
            "rose", "lavender", "apple", "cherry",
            "sunflower", "tomato", "boxwood", "rhododendron",
        ]
        for species in species_list:
            pixmap = render_plant_pixmap(
                ObjectType.TREE, diameter=64.0, species=species,
            )
            assert pixmap is not None, f"Failed to render species: {species}"
            assert not pixmap.isNull()


class TestHelperFunctions:
    """Tests for utility functions."""

    def test_get_all_categories(self, qtbot: object) -> None:  # noqa: ARG002
        cats = get_all_categories()
        assert len(cats) == 15
        assert PlantCategory.ROUND_DECIDUOUS in cats

    def test_get_species_names(self, qtbot: object) -> None:  # noqa: ARG002
        names = get_species_names()
        assert len(names) > 0
        assert "rose" in names
        assert "lavender" in names

    def test_clear_plant_cache(self, qtbot: object) -> None:  # noqa: ARG002
        # Load something into cache
        render_plant_pixmap(ObjectType.TREE, diameter=64.0)
        # Clear should not raise
        clear_plant_cache()
        # Loading again should still work
        pixmap = render_plant_pixmap(ObjectType.TREE, diameter=64.0)
        assert pixmap is not None
