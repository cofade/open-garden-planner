"""``paint_shape`` draws a shape item's fill with the tile its painter needs and
otherwise exactly what the item's Qt base class draws (#785).

The ellipse is the one shape whose Qt paint has two branches: a whole ellipse
(``drawEllipse``) and an arc (``drawPie``). ``paint_shape`` may take over only
the first; these tests pin where the line between them lies.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QStyleOptionGraphicsItem

from open_garden_planner.core.fill_patterns import (
    FillPattern,
    clear_texture_cache,
    create_pattern_brush,
)
from open_garden_planner.ui.canvas.items.fill_paint import paint_shape

_ZOOM = 4.0  # above 100 %: a textured fill takes the detail tile
_FULL = 360 * 16


@pytest.fixture(autouse=True)
def _fresh_caches(qtbot):
    clear_texture_cache()
    yield
    clear_texture_cache()


def _ellipse(span: int) -> QGraphicsEllipseItem:
    item = QGraphicsEllipseItem(QRectF(4.0, 4.0, 40.0, 30.0))
    item.setBrush(create_pattern_brush(FillPattern.GRASS, QColor(70, 140, 60)))
    item.setPen(QPen(QColor(20, 60, 20), 1.0))
    item.setStartAngle(30 * 16)
    item.setSpanAngle(span)
    return item


def _render(item: QGraphicsEllipseItem, *, through_paint_shape: bool) -> tuple[np.ndarray, int]:
    """The item painted at ``_ZOOM`` and how often its Qt base paint ran."""
    image = QImage(200, 160, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(_ZOOM, _ZOOM)
    option = QStyleOptionGraphicsItem()
    calls = 0

    def base_paint(p, o, w) -> None:
        nonlocal calls
        calls += 1
        QGraphicsEllipseItem.paint(item, p, o, w)

    if through_paint_shape:
        paint_shape(item, painter, option, None, base_paint)
    else:
        QGraphicsEllipseItem.paint(item, painter, option, None)
    painter.end()
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    pixels = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return pixels[:, : image.width(), :3].astype(np.int32).copy(), calls


class TestEllipseSpan:
    @pytest.mark.parametrize("span", [_FULL, -_FULL, 2 * _FULL])
    def test_a_whole_ellipse_takes_the_detail_tile(self, span: int) -> None:
        item = _ellipse(span)
        refined, calls = _render(item, through_paint_shape=True)
        plain, _ = _render(item, through_paint_shape=False)
        assert calls == 0  # paint_shape drew it itself ...
        assert np.abs(refined - plain).max() > 0  # ... with another tile
        # ... over the same area: what is not white is the same shape
        assert np.array_equal((refined < 250).any(axis=2), (plain < 250).any(axis=2))

    @pytest.mark.parametrize("span", [0, 90 * 16, -200 * 16, _FULL + 16])
    def test_an_arc_is_left_to_qt(self, span: int) -> None:
        """Qt draws a pie for every span that is not a whole number of turns —
        and for a span of 0, which is not a whole ellipse either."""
        item = _ellipse(span)
        ours, calls = _render(item, through_paint_shape=True)
        qt, _ = _render(item, through_paint_shape=False)
        assert calls == 1
        assert np.array_equal(ours, qt)
