"""``core.sprite_raster``: a sprite is rasterised at the level its painter shows
it at, the cache is bounded, and an oversized sprite is never rasterised whole
(#785)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap

from open_garden_planner.core import sprite_raster
from open_garden_planner.core.sprite_raster import (
    MAX_CACHED_SIDE_PX,
    MAX_LAYER_PIXELS,
    SPRITE_CACHE_MAX_BYTES,
    PixmapLru,
    paint_sprite,
    sprite_pixel_size,
)


def _draw_star(painter: QPainter, rect: QRectF) -> None:
    """A vector picture with hard edges and no symmetry: a dark wedge in a
    light disc, plus a bar near the top-left (so a flip or a turn shows)."""
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 100.0, rect.height() / 100.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(240, 230, 120))
    painter.drawEllipse(QRectF(2, 2, 96, 96))
    path = QPainterPath()
    path.moveTo(50, 50)
    path.lineTo(95, 40)
    path.lineTo(80, 75)
    path.closeSubpath()
    painter.setBrush(QColor(30, 60, 30))
    painter.drawPath(path)
    painter.setBrush(QColor(160, 30, 30))
    painter.drawRect(QRectF(20, 22, 30, 6))
    painter.restore()


def _canvas(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :].astype(np.int16).copy()


@pytest.fixture
def cache():
    return PixmapLru(8 * 1024 * 1024, 64)


class TestPixmapLru:
    def test_bytes_never_exceed_the_budget(self, qtbot) -> None:
        lru = PixmapLru(max_bytes=1_000_000, max_entries=1000)
        for index in range(200):
            lru.put(index, QPixmap(100, 100 + index % 7))  # ~40 kB each
            assert lru.bytes_used <= lru.max_bytes
        assert 0 < len(lru) <= 25

    def test_entries_never_exceed_the_count(self, qtbot) -> None:
        lru = PixmapLru(max_bytes=10**9, max_entries=10)
        for index in range(50):
            lru.put(index, QPixmap(4, 4))
        assert len(lru) == 10

    def test_the_least_recently_used_goes_first(self, qtbot) -> None:
        lru = PixmapLru(max_bytes=10**9, max_entries=3)
        for key in "abc":
            lru.put(key, QPixmap(4, 4))
        assert lru.get("a") is not None  # touched: now the newest
        lru.put("d", QPixmap(4, 4))
        assert "b" not in lru
        assert all(key in lru for key in "acd")

    def test_a_pixmap_larger_than_the_budget_is_not_stored(self, qtbot) -> None:
        lru = PixmapLru(max_bytes=10_000, max_entries=10)
        lru.put("small", QPixmap(10, 10))
        lru.put("huge", QPixmap(200, 200))
        assert "huge" not in lru
        assert "small" in lru  # and it did not evict what was there

    def test_replacing_a_key_keeps_the_books(self, qtbot) -> None:
        lru = PixmapLru(max_bytes=10**6, max_entries=10)
        lru.put("k", QPixmap(10, 10))
        lru.put("k", QPixmap(20, 20))
        assert lru.bytes_used == 20 * 20 * 4
        lru.clear()
        assert lru.bytes_used == 0 and len(lru) == 0

    def test_the_canvas_cache_states_its_bound(self) -> None:
        """The stated bound of the sprite cache (#785): 64 MB, and no entry
        larger than 1024 x 1024 = 4 MB."""
        assert sprite_raster.SPRITE_CACHE.max_bytes == SPRITE_CACHE_MAX_BYTES == 64 * 1024 * 1024
        assert MAX_CACHED_SIDE_PX**2 * 4 == 4 * 1024 * 1024


class TestLevelIsTheCacheKey:
    def test_two_zooms_inside_one_level_share_a_pixmap(self, qtbot, cache) -> None:
        rect = QRectF(0, 0, 50, 30)
        for zoom in (2.2, 3.0, 4.0):  # all level 4
            image = _canvas(256, 256)
            painter = QPainter(image)
            painter.scale(zoom, zoom)
            assert paint_sprite(painter, rect, "star", _draw_star, cache=cache)
            painter.end()
        assert len(cache) == 1
        (key,) = cache._entries
        assert key[1:3] == sprite_pixel_size(50, 30, 4.0) == (200, 120)

    def test_a_new_level_is_a_new_pixmap(self, qtbot, cache) -> None:
        rect = QRectF(0, 0, 50, 30)
        for zoom in (0.4, 1.0, 1.7, 4.0, 9.0):  # levels 1, 1, 2, 4, 16
            image = _canvas(64, 64)
            painter = QPainter(image)
            painter.scale(zoom, zoom)
            paint_sprite(painter, rect, "star", _draw_star, cache=cache)
            painter.end()
        sizes = sorted(key[1] for key in cache._entries)
        assert sizes == [50, 100, 200, 800]

    def test_the_tint_is_part_of_the_key(self, qtbot, cache) -> None:
        rect = QRectF(0, 0, 40, 40)
        image = _canvas(64, 64)
        painter = QPainter(image)
        for tint in (None, QColor(200, 0, 0), QColor(0, 0, 200)):
            paint_sprite(painter, rect, "star", _draw_star, tint=tint, cache=cache)
        painter.end()
        assert len(cache) == 3

    def test_a_degenerate_rectangle_paints_nothing(self, qtbot, cache) -> None:
        image = _canvas(16, 16)
        painter = QPainter(image)
        assert not paint_sprite(painter, QRectF(0, 0, 0, 10), "star", _draw_star, cache=cache)
        assert not paint_sprite(painter, QRectF(0, 0, float("nan"), 10), "star", _draw_star,
                                cache=cache)
        painter.end()
        assert len(cache) == 0


class TestOversizedSprite:
    """A sprite that would need more than ``MAX_CACHED_SIDE_PX`` on a side is
    drawn from the vector for the part the device shows — never rasterised
    whole, never cached."""

    def test_nothing_is_cached_and_no_huge_pixmap_is_made(self, qtbot, cache, monkeypatch) -> None:
        made: list[tuple[int, int]] = []
        real = sprite_raster.rasterise

        def spy(width, height, draw, tint=None):
            made.append((width, height))
            return real(width, height, draw, tint)

        monkeypatch.setattr(sprite_raster, "rasterise", spy)
        image = _canvas(600, 400)
        painter = QPainter(image)
        painter.scale(10.0, 10.0)  # a 500 cm sprite at 1000 %: 5000 px (level 16: 8000)
        assert paint_sprite(painter, QRectF(-200, -150, 500, 500), "star", _draw_star, cache=cache)
        painter.end()
        assert made == [] and len(cache) == 0
        assert _pixels(image)[..., 3].max() == 255  # and it painted

    @pytest.mark.parametrize("rotation", [0.0, 30.0, 180.0])
    @pytest.mark.parametrize("flip", [1.0, -1.0])
    @pytest.mark.parametrize("ratio", [1.0, 2.0])
    def test_the_exposed_part_is_the_vector_itself(
        self, qtbot, cache, rotation: float, flip: float, ratio: float
    ) -> None:
        """Sharp but wrong is a failure: the layer route must put every pixel
        where painting the vector directly puts it — rotated, mirrored, on a
        high-density device."""
        rect = QRectF(-150, -120, 400, 400)

        def scene(draw_sprite) -> QImage:
            image = _canvas(500, 360)
            image.setDevicePixelRatio(ratio)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(120, 90)
            painter.scale(6.0 / ratio * 2.0, 6.0 / ratio * 2.0 * flip)
            painter.rotate(rotation)
            draw_sprite(painter)
            painter.end()
            return image

        direct = scene(lambda p: _draw_star(p, rect))
        layered = scene(lambda p: paint_sprite(p, rect, "star", _draw_star, cache=cache))
        assert len(cache) == 0  # it took the exposed route
        difference = np.abs(_pixels(direct) - _pixels(layered))
        # the same rasteriser on the same geometry: rounding of the composite only
        assert difference.max() <= 2, difference.max()

    def test_the_layer_is_bounded(self, qtbot, cache, monkeypatch) -> None:
        """A sprite covering a device larger than the layer budget is drawn
        coarser, not into a larger layer."""
        monkeypatch.setattr(sprite_raster, "MAX_LAYER_PIXELS", 100 * 100)
        sizes: list[int] = []
        real_image = sprite_raster._transparent_image

        def spy(width, height):
            sizes.append(width * height)
            return real_image(width, height)

        monkeypatch.setattr(sprite_raster, "_transparent_image", spy)
        image = _canvas(800, 600)
        painter = QPainter(image)
        painter.scale(10.0, 10.0)
        assert paint_sprite(painter, QRectF(0, 0, 400, 400), "star", _draw_star, cache=cache)
        painter.end()
        assert sizes and max(sizes) <= 100 * 100 + 300
        assert MAX_LAYER_PIXELS == 16 * 1024 * 1024

    def test_a_clip_bounds_the_exposed_part(self, qtbot, cache, monkeypatch) -> None:
        sizes: list[tuple[int, int]] = []
        real_image = sprite_raster._transparent_image

        def spy(width, height):
            sizes.append((width, height))
            return real_image(width, height)

        monkeypatch.setattr(sprite_raster, "_transparent_image", spy)
        image = _canvas(800, 600)
        painter = QPainter(image)
        painter.setClipRect(QRectF(100, 100, 50, 40))
        painter.scale(10.0, 10.0)
        assert paint_sprite(painter, QRectF(0, 0, 400, 400), "star", _draw_star, cache=cache)
        painter.end()
        assert sizes == [(50, 40)]

    def test_off_device_is_painted_in_full_without_a_layer(self, qtbot, cache) -> None:
        image = _canvas(100, 100)
        painter = QPainter(image)
        painter.scale(10.0, 10.0)
        painter.translate(QPointF(1000, 1000))
        assert paint_sprite(painter, QRectF(0, 0, 400, 400), "star", _draw_star, cache=cache)
        painter.end()
        assert _pixels(image)[..., 3].max() == 0


class TestCachedAndExposedAgree:
    def test_one_picture_on_both_sides_of_the_threshold(self, qtbot, cache, monkeypatch) -> None:
        """The same sprite through the pixmap route and through the layer route
        lands in the same place (a half-pixel shift between them would pop when
        a zoom crosses the threshold)."""
        rect = QRectF(10, 20, 80, 60)

        def scene() -> QImage:
            image = _canvas(400, 320)
            painter = QPainter(image)
            painter.scale(4.0, 4.0)
            paint_sprite(painter, rect, "star", _draw_star, cache=cache)
            painter.end()
            return image

        cached = scene()
        assert len(cache) == 1
        monkeypatch.setattr(sprite_raster, "MAX_CACHED_SIDE_PX", 16)
        exposed = scene()
        difference = np.abs(_pixels(cached) - _pixels(exposed))
        assert difference.max() <= 2, difference.max()
