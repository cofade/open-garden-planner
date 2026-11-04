"""Unit tests for fill pattern texture loading system (US-6.1)."""

from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtGui import QBrush, QColor, QPixmap

from open_garden_planner.core.fill_patterns import (
    _TEXTURES_DIR,
    FillPattern,
    _load_texture,
    _tint_texture,
    clear_texture_cache,
    create_pattern_brush,
    pattern_from_name,
    tinted_pattern_pixels,
)


class TestFillPatternEnum:
    """Tests for FillPattern enum members."""

    def test_solid_pattern_exists(self, qtbot: object) -> None:
        assert FillPattern.SOLID is not None

    def test_all_material_patterns_exist(self, qtbot: object) -> None:
        expected = [
            "SOLID", "GRASS", "GRAVEL", "CONCRETE", "WOOD",
            "WATER", "SOIL", "MULCH", "ROOF_TILES", "SAND", "STONE", "GLASS", "HEDGE",
            "BRICK", "BARK", "WILDFLOWER", "TERRACOTTA", "PEBBLES",
            "SLATE", "LATTICE", "COMPOST", "FLAGSTONE", "CLAY",
            "DECKING", "CORTEN",  # US-E9 asset-forge pilots
        ]
        for name in expected:
            assert hasattr(FillPattern, name), f"Missing pattern: {name}"

    def test_pattern_count(self, qtbot: object) -> None:
        assert len(FillPattern) == 25


class TestTextureFiles:
    """Tests for texture PNG file existence and validity."""

    @pytest.fixture
    def textures_dir(self) -> Path:
        return _TEXTURES_DIR

    def test_textures_directory_exists(self, textures_dir: Path) -> None:
        assert textures_dir.exists()
        assert textures_dir.is_dir()

    @pytest.mark.parametrize(
        "filename",
        ["grass", "gravel", "concrete", "wood", "water", "soil", "mulch", "sand", "stone", "roof_tiles", "glass", "hedge", "brick", "bark", "wildflower", "terracotta", "pebbles", "slate", "lattice", "compost", "flagstone", "clay", "decking", "corten"],
    )
    def test_texture_file_exists(self, textures_dir: Path, filename: str) -> None:
        path = textures_dir / f"{filename}.png"
        assert path.exists(), f"Texture file missing: {filename}.png"
        assert path.is_file()

    @pytest.mark.parametrize(
        "filename",
        ["grass", "gravel", "concrete", "wood", "water", "soil", "mulch", "sand", "stone", "roof_tiles", "glass", "hedge", "brick", "bark", "wildflower", "terracotta", "pebbles", "slate", "lattice", "compost", "flagstone", "clay", "decking", "corten"],
    )
    def test_texture_file_is_valid_png(self, textures_dir: Path, filename: str) -> None:
        path = textures_dir / f"{filename}.png"
        assert path.stat().st_size > 0
        with open(path, "rb") as f:
            header = f.read(8)
            assert header[:4] == b"\x89PNG", f"{filename}.png is not a valid PNG"

    @pytest.mark.parametrize(
        "filename",
        ["grass", "gravel", "concrete", "wood", "water", "soil", "mulch", "sand", "stone", "roof_tiles", "glass", "hedge", "brick", "bark", "wildflower", "terracotta", "pebbles", "slate", "lattice", "compost", "flagstone", "clay", "decking", "corten"],
    )
    def test_texture_file_is_256x256(self, textures_dir: Path, filename: str, qtbot: object) -> None:
        path = textures_dir / f"{filename}.png"
        pixmap = QPixmap(str(path))
        assert not pixmap.isNull()
        assert pixmap.width() == 256, f"{filename}.png width is {pixmap.width()}, expected 256"
        assert pixmap.height() == 256, f"{filename}.png height is {pixmap.height()}, expected 256"


class TestTextureLoading:
    """Tests for texture loading and caching."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        clear_texture_cache()
        yield  # type: ignore[misc]
        clear_texture_cache()

    def test_load_grass_texture(self, qtbot: object) -> None:
        pixmap = _load_texture(FillPattern.GRASS)
        assert pixmap is not None
        assert not pixmap.isNull()
        assert pixmap.width() == 256

    def test_load_texture_returns_none_for_solid(self, qtbot: object) -> None:
        pixmap = _load_texture(FillPattern.SOLID)
        assert pixmap is None

    def test_load_texture_caching(self, qtbot: object) -> None:
        pixmap1 = _load_texture(FillPattern.GRAVEL)
        pixmap2 = _load_texture(FillPattern.GRAVEL)
        # Same object from cache
        assert pixmap1 is pixmap2

    @pytest.mark.parametrize(
        "pattern",
        [p for p in FillPattern if p != FillPattern.SOLID],
    )
    def test_all_non_solid_patterns_load(self, qtbot: object, pattern: FillPattern) -> None:
        pixmap = _load_texture(pattern)
        assert pixmap is not None, f"Failed to load texture for {pattern.name}"


class TestTintTexture:
    """Tests for texture tinting."""

    def test_tint_returns_pixmap(self, qtbot: object) -> None:
        texture = _load_texture(FillPattern.GRASS)
        assert texture is not None
        tinted = _tint_texture(texture, QColor(100, 200, 100, 150))
        assert isinstance(tinted, QPixmap)
        assert not tinted.isNull()
        assert tinted.width() == texture.width()
        assert tinted.height() == texture.height()

    def test_tint_with_full_alpha(self, qtbot: object) -> None:
        texture = _load_texture(FillPattern.WOOD)
        assert texture is not None
        tinted = _tint_texture(texture, QColor(200, 150, 100, 255))
        assert not tinted.isNull()

    def test_tint_with_low_alpha(self, qtbot: object) -> None:
        texture = _load_texture(FillPattern.WATER)
        assert texture is not None
        tinted = _tint_texture(texture, QColor(64, 164, 223, 50))
        assert not tinted.isNull()


class TestCreatePatternBrush:
    """Tests for the main create_pattern_brush function."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        clear_texture_cache()
        yield  # type: ignore[misc]
        clear_texture_cache()

    def test_solid_returns_solid_brush(self, qtbot: object) -> None:
        color = QColor(255, 0, 0)
        brush = create_pattern_brush(FillPattern.SOLID, color)
        assert isinstance(brush, QBrush)
        assert brush.color() == color

    def test_grass_returns_textured_brush(self, qtbot: object) -> None:
        brush = create_pattern_brush(FillPattern.GRASS, QColor(90, 150, 60, 120))
        assert isinstance(brush, QBrush)
        # Texture brush has a non-null texture
        assert not brush.texture().isNull()

    def test_all_patterns_return_valid_brush(self, qtbot: object) -> None:
        color = QColor(128, 128, 128, 128)
        for pattern in FillPattern:
            brush = create_pattern_brush(pattern, color)
            assert isinstance(brush, QBrush), f"Invalid brush for {pattern.name}"

    def test_cached_brush_same_color(self, qtbot: object) -> None:
        color = QColor(100, 200, 100, 120)
        brush1 = create_pattern_brush(FillPattern.GRAVEL, color)
        brush2 = create_pattern_brush(FillPattern.GRAVEL, color)
        # Both should have valid textures
        assert not brush1.texture().isNull()
        assert not brush2.texture().isNull()

    def test_different_colors_different_brushes(self, qtbot: object) -> None:
        brush1 = create_pattern_brush(FillPattern.WOOD, QColor(200, 150, 100, 120))
        brush2 = create_pattern_brush(FillPattern.WOOD, QColor(100, 50, 200, 120))
        # Different tints should produce different textures
        t1 = brush1.texture().toImage()
        t2 = brush2.texture().toImage()
        # At least one pixel should differ
        different = False
        for x in range(0, t1.width(), 32):
            for y in range(0, t1.height(), 32):
                if t1.pixelColor(x, y) != t2.pixelColor(x, y):
                    different = True
                    break
            if different:
                break
        assert different

    def test_sand_pattern(self, qtbot: object) -> None:
        brush = create_pattern_brush(FillPattern.SAND, QColor(210, 195, 160, 120))
        assert isinstance(brush, QBrush)
        assert not brush.texture().isNull()

    def test_stone_pattern(self, qtbot: object) -> None:
        brush = create_pattern_brush(FillPattern.STONE, QColor(180, 175, 165, 120))
        assert isinstance(brush, QBrush)
        assert not brush.texture().isNull()

    def test_glass_pattern(self, qtbot: object) -> None:
        brush = create_pattern_brush(FillPattern.GLASS, QColor(210, 230, 245, 140))
        assert isinstance(brush, QBrush)
        assert not brush.texture().isNull()


class TestThe3DFillPicture:
    """#628 follow-up: a raised object's own faces show the fill it had on the ground.

    The ground bake paints a lawn, path, shape or bed while it lies flat; the moment
    the user gives it a height it stops being painted there and becomes a solid, so
    ``tinted_pattern_pixels`` hands the 3D pipeline the very picture the canvas made.
    """

    def test_solid_has_no_picture(self, qtbot: object) -> None:
        assert tinted_pattern_pixels(FillPattern.SOLID, QColor(90, 150, 60)) is None

    def test_a_pattern_is_the_canvas_texture_in_rgba(self, qtbot: object) -> None:
        got = tinted_pattern_pixels(FillPattern.GRASS, QColor(90, 150, 60))
        assert got is not None
        width, height, data = got
        assert (width, height) == (256, 256)
        assert len(data) == width * height * 4
        assert data[3::4] == b"\xff" * (width * height), "a solid body is opaque"
        pixels = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
        # the mean IS the fill colour — the same rule `_tint_texture` follows in 2D
        for channel, value in enumerate((90, 150, 60)):
            assert abs(int(pixels[:, :, channel].mean()) - value) <= 4
        assert int(pixels[:, :, 1].std()) > 1, "a flat fill would carry no detail"

    def test_the_tile_ruler_and_the_textures_are_one_size(self, qtbot: object) -> None:
        """UVs are plan centimetres / 256: a texture of another size would stretch."""
        from open_garden_planner.core.scene3d import PATTERN_TILE_CM

        assert PATTERN_TILE_CM == 256.0
        for pattern in FillPattern:
            if pattern == FillPattern.SOLID:
                continue
            texture = _load_texture(pattern)
            assert texture is not None, pattern
            assert (texture.width(), texture.height()) == (256, 256), pattern

    def test_a_records_pattern_name_resolves(self, qtbot: object) -> None:
        assert pattern_from_name("GRASS") is FillPattern.GRASS
        assert pattern_from_name("SOLID") is None
        assert pattern_from_name(None) is None
        assert pattern_from_name("") is None
        assert pattern_from_name("NO_SUCH_PATTERN") is None


class TestClearTextureCache:
    """Tests for cache clearing."""

    def test_clear_cache(self, qtbot: object) -> None:
        # Load something into cache
        create_pattern_brush(FillPattern.GRASS, QColor(90, 150, 60))
        # Clear should not raise
        clear_texture_cache()
        # Loading again should still work
        brush = create_pattern_brush(FillPattern.GRASS, QColor(90, 150, 60))
        assert not brush.texture().isNull()
