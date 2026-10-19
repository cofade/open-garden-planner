"""How a styled path or fence line is painted on the 2D canvas (US-6.15) — through
the real ``PolylineItem.paint``.

The ten style painters live in ``ui/canvas/items/path_style_paint.py`` (they are
shared with the 3D ground bake). What is pinned here is the 2D picture itself:

- a line with a BEND paints nothing beyond its own reach — a boardwalk and a
  stone wall used to fill the whole inside of the bend with one colour (their
  rails were drawn with the brush the last plank / stone had left behind, and Qt
  fills an open path as if it were closed);
- away from the bend, a bent line is the straight line, pixel for pixel;
- a plain line (style ``NONE``) is the base class's stroke and builds no style
  painter at all; the table of painters is built once and names every style.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.items import PolylineItem, polyline_item
from open_garden_planner.ui.canvas.items import path_style_paint as style_paint
from open_garden_planner.ui.canvas.items.path_style_paint import STYLES_PAINTED, PathStylePaint

SIZE = 420
BACKGROUND = QColor(255, 255, 255)
STYLES = [style for style in PathFenceStyle if style is not PathFenceStyle.NONE]
#: The corner of the L every test bends its line at.
CORNER = QPointF(340.0, 60.0)
FIRST_LEG = [QPointF(40.0, 60.0), CORNER]
AN_L = [*FIRST_LEG, QPointF(340.0, 360.0)]
A_U = [*AN_L, QPointF(140.0, 360.0)]


def _line(points: list[QPointF], style: PathFenceStyle, width: float | None = None) -> PolylineItem:
    kind = ObjectType.PATH if "PATH" in style.name or style in (
        PathFenceStyle.STEPPING_STONES, PathFenceStyle.WOODEN_BOARDWALK, PathFenceStyle.NONE,
    ) else ObjectType.FENCE
    item = PolylineItem([QPointF(point) for point in points], object_type=kind, path_fence_style=style)
    if width is not None:
        pen = item.pen()
        pen.setWidthF(width)
        item.setPen(pen)
    return item


def _rendered(item: PolylineItem) -> np.ndarray:
    """``item`` painted by a scene — its own ``paint`` — one pixel a centimetre."""
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0.0, 0.0, SIZE, SIZE))
    scene.addItem(item)
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        scene.render(painter, QRectF(0.0, 0.0, SIZE, SIZE), QRectF(0.0, 0.0, SIZE, SIZE))
    finally:
        painter.end()
    scene.removeItem(item)
    return _array(image)


def _array(image: QImage) -> np.ndarray:
    bits = image.constBits()
    assert bits is not None
    return np.frombuffer(bits.asstring(image.sizeInBytes()), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3].astype(np.int16)


def _within(points: list[QPointF], reach: float) -> np.ndarray:
    """True for every pixel within ``reach`` of the polyline (a wide round stroke)."""
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    pen = QPen(QColor(0, 0, 0))
    pen.setWidthF(2.0 * reach)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(*points)
    painter.end()
    return _array(image)[..., 0] < 128


def _reach(width: float) -> float:
    """The farthest any style draws from its centre line: chain-link rails at one
    width, a metal fence's bars at 1.25 widths plus the spear's 1.2 cm, a mitred
    right angle at 0.71 widths — and room for antialiasing."""
    return 1.5 * width + 4.0


@pytest.mark.parametrize("width", [None, 30.0], ids=["preset width", "30 cm wide"])
@pytest.mark.parametrize("shape", ["L", "U"])
@pytest.mark.parametrize("style", STYLES, ids=lambda s: s.name)
def test_a_bent_line_paints_nothing_beyond_its_reach(
        style: PathFenceStyle, shape: str, width: float | None, qtbot: Any) -> None:
    """Found by the 3D ground bake (Phase 17 L1.5): a bent WOODEN_BOARDWALK or
    STONE_WALL filled the inside of its bend with the colour of its last plank or
    stone — over its own elements, out to the chord between its ends."""
    points = AN_L if shape == "L" else A_U
    item = _line(points, style, width)
    painted = np.any(_rendered(item) != 255, axis=2)
    assert painted.any()
    stray = painted & ~_within(points, _reach(item.pen().widthF()))
    assert int(stray.sum()) == 0, (style.name, int(stray.sum()))


@pytest.mark.parametrize("width", [None, 30.0], ids=["preset width", "30 cm wide"])
@pytest.mark.parametrize("style", STYLES, ids=lambda s: s.name)
def test_away_from_its_bend_a_bent_line_is_the_straight_line(
        style: PathFenceStyle, width: float | None, qtbot: Any) -> None:
    """The elements of a line's first leg are where they are whatever follows it:
    left of the bend — by more than the style's reach — the picture of the L is the
    picture of its first leg alone. (With the patch, the planks and stones of the
    first leg were painted over.)

    Compared inside the first leg's own bounding rectangle, which is all the live
    canvas shows of it: the item cache cuts what a style draws beyond it — the
    bars of a 30 cm metal fence reach 37.5 cm from the line, the rectangle 17 cm;
    an export, which paints without the cache, shows them whole. And to two steps
    of 255: a thin antialiased rail with a corner in it is not rasterised exactly
    as one without (measured: at most 2, on the rails of three styles)."""
    bent = _line(AN_L, style, width)
    straight = _line(FIRST_LEG, style, width)
    reach = _reach(bent.pen().widthF())
    bounds = straight.sceneBoundingRect()
    rows = slice(int(bounds.top()) + 1, int(bounds.bottom()) - 1)
    columns = slice(0, int(CORNER.x() - reach - 1.0))
    first, second = _rendered(bent)[rows, columns], _rendered(straight)[rows, columns]
    assert np.any(second != 255)
    assert int(np.abs(first - second).max()) <= 2, style.name


def test_a_boardwalks_planks_alternate_to_the_bend(qtbot: Any) -> None:
    """Along the first leg's centre line: one sample per plank, light and dark in
    turn, to the bend."""
    item = _line(AN_L, PathFenceStyle.WOODEN_BOARDWALK, 30.0)
    image = _rendered(item)
    reds = [int(image[60, int(40.0 + k * 10.5), 0]) for k in range(1, 27)]  # spacing 0.35 x 30
    assert len(set(reds)) == 2, reds
    assert all(a != b for a, b in zip(reds, reds[1:], strict=False)), reds


class _Counted(PathStylePaint):
    built = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).built += 1
        super().__init__(*args, **kwargs)


def test_a_plain_line_builds_no_style_painter(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Style ``NONE`` is most lines of a plan, and this is the shipped 2D paint
    path: a plain line is stroked by the base class and builds nothing per paint
    (it built a ``PathStylePaint``, a copy of its points and a ten-entry table)."""
    monkeypatch.setattr(polyline_item, "PathStylePaint", _Counted)
    _Counted.built = 0
    plain = _line(AN_L, PathFenceStyle.NONE)
    assert np.any(_rendered(plain) != 255)
    assert _Counted.built == 0
    styled = _line(AN_L, PathFenceStyle.GRAVEL_PATH)
    assert np.any(_rendered(styled) != 255)
    assert _Counted.built == 1


def test_a_style_painter_reads_the_items_own_points(qtbot: Any) -> None:
    """… and a styled line's painter copies nothing: it reads the list it is given."""
    points = [QPointF(point) for point in AN_L]
    assert PathStylePaint(points, QPen())._points is points
    assert PathStylePaint(tuple(points), QPen())._points == points


def test_the_table_of_style_painters_is_built_once_and_names_every_style() -> None:
    assert frozenset(STYLES) == STYLES_PAINTED
    assert style_paint._STYLE_PAINTERS.keys() == STYLES_PAINTED
    assert len({painter.__name__ for painter in style_paint._STYLE_PAINTERS.values()}) == 10
    image = QImage(8, 8, QImage.Format.Format_RGBA8888_Premultiplied)
    painter = QPainter(image)
    try:
        table = style_paint._STYLE_PAINTERS
        assert PathStylePaint(AN_L, QPen()).paint(painter, PathFenceStyle.NONE) is False
        assert all(PathStylePaint(AN_L, QPen(QColor(9, 9, 9), 4.0)).paint(painter, style) for style in STYLES)
        assert style_paint._STYLE_PAINTERS is table
    finally:
        painter.end()


@pytest.mark.parametrize("style", [PathFenceStyle.NONE, PathFenceStyle.PAVED_PATH],
                         ids=lambda s: s.name)
def test_a_selected_line_shows_its_selection(style: PathFenceStyle, qtbot: Any) -> None:
    """Plain or styled, the selection is drawn after the style — outside the line."""
    item = _line(AN_L, style)
    alone = np.any(_rendered(item) != 255, axis=2)
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0.0, 0.0, SIZE, SIZE))
    scene.addItem(item)
    item.setSelected(True)
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    try:
        scene.render(painter, QRectF(0.0, 0.0, SIZE, SIZE), QRectF(0.0, 0.0, SIZE, SIZE))
    finally:
        painter.end()
    selected = np.any(_array(image) != 255, axis=2)
    assert int((selected & ~alone).sum()) > 100
