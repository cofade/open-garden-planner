"""Unit tests for garden infrastructure SVG rendering (US-6.9)."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QPixmap

from open_garden_planner.core.furniture_renderer import (
    FURNITURE_DEFAULT_DIMENSIONS,
    _INFRASTRUCTURE_DIR,
    _INFRASTRUCTURE_FILES,
    clear_furniture_cache,
    get_default_dimensions,
    get_furniture_svg_path,
    is_furniture_type,
    render_furniture_pixmap,
)
from open_garden_planner.core.object_types import ObjectType


INFRASTRUCTURE_TYPES = [
    ObjectType.RAISED_BED,
    ObjectType.COMPOST_BIN,
    ObjectType.COLD_FRAME,
    ObjectType.RAIN_BARREL,
    ObjectType.WATER_TAP,
    ObjectType.TOOL_SHED,
]


class TestIsInfrastructureType:
    """Tests for is_furniture_type detecting infrastructure objects."""

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_infrastructure_types_detected(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        assert is_furniture_type(obj_type) is True

    def test_house_is_not_infrastructure(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(ObjectType.HOUSE) is False

    def test_generic_rect_is_not_infrastructure(self, qtbot: object) -> None:  # noqa: ARG002
        assert is_furniture_type(ObjectType.GENERIC_RECTANGLE) is False


class TestInfrastructureSVGFiles:
    """Tests for infrastructure SVG file existence."""

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_svg_file_exists(self, obj_type: ObjectType) -> None:
        filename = _INFRASTRUCTURE_FILES[obj_type]
        path = _INFRASTRUCTURE_DIR / f"{filename}.svg"
        assert path.exists(), f"Infrastructure SVG missing: {filename}.svg"
        assert path.is_file()
        assert path.stat().st_size > 0

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_svg_has_valid_header(self, obj_type: ObjectType) -> None:
        filename = _INFRASTRUCTURE_FILES[obj_type]
        path = _INFRASTRUCTURE_DIR / f"{filename}.svg"
        content = path.read_text(encoding="utf-8")
        assert "<svg" in content, f"{filename}.svg is not valid SVG"
        assert "</svg>" in content

    def test_six_infrastructure_files_mapped(self, qtbot: object) -> None:  # noqa: ARG002
        assert len(_INFRASTRUCTURE_FILES) == 6


class TestGetInfrastructureSvgPath:
    """Tests for SVG path resolution."""

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_infrastructure_type_resolves(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        path = get_furniture_svg_path(obj_type)
        assert path is not None
        assert path.exists()

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_infrastructure_svg_in_infrastructure_dir(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        path = get_furniture_svg_path(obj_type)
        assert path is not None
        assert "infrastructure" in str(path)


class TestRenderInfrastructurePixmap:
    """Tests for SVG to QPixmap rendering."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        clear_furniture_cache()
        yield  # type: ignore[misc]
        clear_furniture_cache()

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_render_returns_pixmap(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        w, h = FURNITURE_DEFAULT_DIMENSIONS[obj_type]
        pixmap = render_furniture_pixmap(obj_type, width=w, height=h)
        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert not pixmap.isNull()

    def test_render_raised_bed_default_size(self, qtbot: object) -> None:  # noqa: ARG002
        pixmap = render_furniture_pixmap(ObjectType.RAISED_BED, width=120, height=80)
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_caching_returns_same_pixmap(self, qtbot: object) -> None:  # noqa: ARG002
        p1 = render_furniture_pixmap(ObjectType.RAISED_BED, width=120, height=80)
        p2 = render_furniture_pixmap(ObjectType.RAISED_BED, width=120, height=80)
        assert p1 is p2  # Same object from cache


class TestInfrastructureDefaultDimensions:
    """Tests for default infrastructure dimensions."""

    @pytest.mark.parametrize("obj_type", INFRASTRUCTURE_TYPES)
    def test_all_types_have_defaults(self, qtbot: object, obj_type: ObjectType) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(obj_type)
        assert w > 0
        assert h > 0

    def test_raised_bed_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.RAISED_BED)
        assert w == 120.0
        assert h == 80.0

    def test_tool_shed_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.TOOL_SHED)
        assert w == 200.0
        assert h == 150.0

    def test_water_tap_small(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.WATER_TAP)
        assert w == 20.0
        assert h == 20.0

    def test_rain_barrel_dimensions(self, qtbot: object) -> None:  # noqa: ARG002
        w, h = get_default_dimensions(ObjectType.RAIN_BARREL)
        assert w == 60.0
        assert h == 60.0
