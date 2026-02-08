"""Unit tests for furniture SVG rendering system (US-6.8)."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QPixmap

from open_garden_planner.core.furniture_renderer import (
    FURNITURE_DEFAULT_DIMENSIONS,
    _FURNITURE_DIR,
    _FURNITURE_FILES,
    clear_furniture_cache,
    get_default_dimensions,
    get_furniture_svg_path,
    is_furniture_type,
    render_furniture_pixmap,
)
from open_garden_planner.core.object_types import ObjectType


FURNITURE_TYPES = [
    ObjectType.TABLE_RECTANGULAR,
    ObjectType.TABLE_ROUND,
    ObjectType.CHAIR,
    ObjectType.BENCH,
    ObjectType.PARASOL,
    ObjectType.LOUNGER,
    ObjectType.BBQ_GRILL,
    ObjectType.FIRE_PIT,
    ObjectType.PLANTER_POT,
]

# All SVG-rendered object types (furniture + hedge)
SVG_RENDERED_TYPES = FURNITURE_TYPES + [ObjectType.HEDGE_SECTION]


class TestIsFurnitureType:
    """Tests for is_furniture_type helper."""

    @pytest.mark.parametrize("obj_type", SVG_RENDERED_TYPES)
    def test_svg_rendered_types_detected(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        assert is_furniture_type(obj_type) is True

    def test_house_is_not_furniture(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(ObjectType.HOUSE) is False

    def test_tree_is_not_furniture(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(ObjectType.TREE) is False

    def test_generic_rect_is_not_furniture(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(ObjectType.GENERIC_RECTANGLE) is False

    def test_none_is_not_furniture(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(None) is False


class TestFurnitureSVGFiles:
    """Tests for furniture SVG file existence."""

    @pytest.mark.parametrize("obj_type", FURNITURE_TYPES)
    def test_svg_file_exists(self, obj_type: ObjectType) -> None:
        filename = _FURNITURE_FILES[obj_type]
        path = _FURNITURE_DIR / f"{filename}.svg"
        assert path.exists(), f"Furniture SVG missing: {filename}.svg"
        assert path.is_file()
        assert path.stat().st_size > 0

    @pytest.mark.parametrize("obj_type", FURNITURE_TYPES)
    def test_svg_has_valid_header(self, obj_type: ObjectType) -> None:
        filename = _FURNITURE_FILES[obj_type]
        path = _FURNITURE_DIR / f"{filename}.svg"
        content = path.read_text(encoding="utf-8")
        assert "<svg" in content, f"{filename}.svg is not valid SVG"
        assert "</svg>" in content

    def test_nine_furniture_files_mapped(self, qtbot: object) -> None:  # noqa: ARG002
        assert len(_FURNITURE_FILES) == 9


class TestGetFurnitureSvgPath:
    """Tests for SVG path resolution."""

    @pytest.mark.parametrize("obj_type", SVG_RENDERED_TYPES)
    def test_svg_rendered_type_resolves(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        path = get_furniture_svg_path(obj_type)
        assert path is not None
        assert path.exists()

    def test_hedge_svg_in_plants_dir(self, qtbot: object) -> None:  # noqa: ARG002
        path = get_furniture_svg_path(ObjectType.HEDGE_SECTION)
        assert path is not None
        assert "plants" in str(path)
        assert path.name == "hedge_section.svg"

    def test_non_furniture_returns_none(self, qtbot: object) -> None:  # noqa: ARG002
        path = get_furniture_svg_path(ObjectType.HOUSE)
        assert path is None


class TestRenderFurniturePixmap:
    """Tests for SVG to QPixmap rendering."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        clear_furniture_cache()
        yield  # type: ignore[misc]
        clear_furniture_cache()

    @pytest.mark.parametrize("obj_type", FURNITURE_TYPES)
    def test_render_returns_pixmap(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        w, h = FURNITURE_DEFAULT_DIMENSIONS[obj_type]
        pixmap = render_furniture_pixmap(obj_type, width=w, height=h)
        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert not pixmap.isNull()

    def test_render_non_furniture_returns_none(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_furniture_pixmap(ObjectType.HOUSE, width=100, height=100)
        assert pixmap is None

    def test_caching_returns_same_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        p1 = render_furniture_pixmap(ObjectType.CHAIR, width=50, height=50)
        p2 = render_furniture_pixmap(ObjectType.CHAIR, width=50, height=50)
        assert p1 is p2  # Same object from cache

    def test_different_sizes_different_pixmaps(self, qtbot: object) -> None:  # noqa: ARG002
        p1 = render_furniture_pixmap(ObjectType.CHAIR, width=50, height=50)
        p2 = render_furniture_pixmap(ObjectType.CHAIR, width=100, height=100)
        assert p1 is not None
        assert p2 is not None
        assert p1.width() != p2.width()

    def test_minimum_size_clamped(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_furniture_pixmap(ObjectType.CHAIR, width=1, height=1)
        assert pixmap is not None
        assert pixmap.width() >= 4
        assert pixmap.height() >= 4

    def test_render_hedge_section(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_furniture_pixmap(ObjectType.HEDGE_SECTION, width=200, height=80)
        assert pixmap is not None
        assert not pixmap.isNull()


class TestDefaultDimensions:
    """Tests for default furniture dimensions."""

    @pytest.mark.parametrize("obj_type", FURNITURE_TYPES)
    def test_all_types_have_defaults(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(obj_type)
        assert w > 0
        assert h > 0

    def test_table_rectangular_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.TABLE_RECTANGULAR)
        assert w == 150.0
        assert h == 100.0

    def test_chair_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.CHAIR)
        assert w == 50.0
        assert h == 50.0

    def test_parasol_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.PARASOL)
        assert w == 300.0
        assert h == 300.0

    def test_non_furniture_returns_fallback(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.HOUSE)
        assert w == 100.0
        assert h == 100.0


class TestClearCache:
    """Tests for cache clearing."""

    def test_clear_does_not_raise(self, qtbot: object) -> None:  # noqa: ARG002
        clear_furniture_cache()

    def test_render_after_clear(self, qtbot: object) -> None:  # noqa: ARG002
        render_furniture_pixmap(ObjectType.CHAIR, width=50, height=50)
        clear_furniture_cache()
        pixmap = render_furniture_pixmap(ObjectType.CHAIR, width=50, height=50)
        assert pixmap is not None
