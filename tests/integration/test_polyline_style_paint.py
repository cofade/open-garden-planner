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

    Compared across the first leg's independent paint-reach band, clipped to the
    fixed image (a negative numpy slice would silently sample its far edge).
    The cache bounds are separately pinned by test_styled_line_bounds. To two steps
    of 255: a thin antialiased rail with a corner in it is not rasterised exactly
    as one without (measured: at most 2, on the rails of three styles)."""
    bent = _line(AN_L, style, width)
    straight = _line(FIRST_LEG, style, width)
    reach = _reach(bent.pen().widthF())
    rows = slice(max(0, int(FIRST_LEG[0].y() - reach) - 1),
                 min(SIZE, int(FIRST_LEG[0].y() + reach) + 2))
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
    assert len({painter.__name__ for painter in style_paint._STYLE_PAINTERS.values()}) == 11
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
    """Plain or styled, the selection is drawn after the style — outside the line.
    10 cm wide: a path preset's real width (L4, #388) puts the selection's rectangle
    outside this 420 px frame."""
    item = _line(AN_L, style, 10.0)
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


def _over(item: PolylineItem, background: QColor) -> np.ndarray:
    """``item`` painted by its own ``paint`` over ``background``."""
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0.0, 0.0, SIZE, SIZE))
    scene.addItem(item)
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(background)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        scene.render(painter, QRectF(0.0, 0.0, SIZE, SIZE), QRectF(0.0, 0.0, SIZE, SIZE))
    finally:
        painter.end()
    scene.removeItem(item)
    return _array(image)


@pytest.mark.parametrize("style", [PathFenceStyle.GRAVEL_PATH, PathFenceStyle.DIRT_PATH],
                         ids=lambda s: s.name)
def test_gravel_and_dirt_are_their_textures_and_hide_what_lies_under(style: PathFenceStyle,
                                                                       qtbot: Any) -> None:
    """Owner, L4 manual pass (#388): a gravel path in 3D was green — its stroke was the
    colour at 100 / 255 over the lawn, a dirt path's at 140 / 255 — and a few dots drawn
    for a 6 cm line did not read as gravel. Now each is its fill texture in the line's
    colour, opaque: over white and over black the path's inside is the same picture,
    with the texture's grain, and on average the line's colour."""
    from open_garden_planner.core.object_types import get_path_fence_style_info

    info = get_path_fence_style_info(style)
    item = _line(AN_L, style)
    assert item.pen().widthF() == info.stroke_width >= 70.0
    inside = _within(AN_L, info.stroke_width / 2.0 - 4.0)  # clear of the rim and the caps' edge
    white = _over(_line(AN_L, style), QColor(255, 255, 255))[inside]
    black = _over(_line(AN_L, style), QColor(0, 0, 0))[inside]
    assert np.array_equal(white, black), "the ground shows through the path"
    luma = white @ np.array([0.299, 0.587, 0.114])
    assert float(luma.std()) > 8.0, "a flat colour, not gravel or earth"
    mean = white.mean(axis=0)
    colour = info.stroke_color
    assert np.allclose(mean, (colour.red(), colour.green(), colour.blue()), atol=12.0), mean


def test_the_gravel_edging_is_the_3d_edging() -> None:
    """The rim the 2D painter draws round a gravel path is the 3D edging's width and
    shade: two copies of three numbers (the 3D package is Qt-free), held together."""
    from open_garden_planner.core.scene3d.builders import surfaces

    assert (style_paint.GRAVEL_EDGE_CM, style_paint.GRAVEL_EDGE_SHARE, style_paint.GRAVEL_EDGE_SHADE) \
        == (surfaces.GRAVEL_EDGE_CM, surfaces.GRAVEL_EDGE_SHARE, surfaces.GRAVEL_EDGE_SHADE)


def test_a_dirt_path_is_the_sprites_light_soil() -> None:
    """Owner, L4 manual pass: over the soil texture the former preset 150, 110, 60 read
    orange. The preset is the 2D sprites' own light soil (``MATERIALS["soil"]["light"]``)."""
    from open_garden_planner.core.object_types import get_path_fence_style_info
    from open_garden_planner.core.scene3d.builders import palette

    colour = get_path_fence_style_info(PathFenceStyle.DIRT_PATH).stroke_color
    assert (colour.red(), colour.green(), colour.blue()) == palette.SOIL_LIGHT.srgb


def _dense_fence_points(count: int = 16_000) -> list[QPointF]:
    """16k-point fence alternating tightly between y=100 and y=400 over 300 cm (#928)."""
    return [
        QPointF(i * 300.0 / count, 100.0 if i % 2 == 0 else 400.0)
        for i in range(count)
    ]


def test_sparse_and_dense_polylines_bounded_geometry_contract(qtbot: Any) -> None:
    """Sparse lines (<= MAX_FULL_DETAIL_VERTICES) stay exact; dense lines bound
    their stroked path without mutating ``item.points`` or ``item.path()`` (#928)."""
    from open_garden_planner.ui.canvas.items.polygon_item import MAX_FULL_DETAIL_VERTICES

    sparse_pts = [QPointF(i * 2.0, 100.0 if i % 2 == 0 else 200.0) for i in range(MAX_FULL_DETAIL_VERTICES)]
    sparse = PolylineItem(sparse_pts, object_type=ObjectType.FENCE)
    s_pts, s_path = sparse._bounded_stroke_geometry()
    assert len(s_pts) == MAX_FULL_DETAIL_VERTICES
    assert s_path == sparse.path()

    dense_pts = _dense_fence_points(16_000)
    dense = PolylineItem(dense_pts, object_type=ObjectType.FENCE)
    d_pts, d_path = dense._bounded_stroke_geometry()
    assert dense.point_count == 16_000
    assert len(dense.points) == 16_000
    assert dense.path().elementCount() == 16_000
    assert len(d_pts) <= 64
    assert d_path.elementCount() <= 64
    assert dense.shape().elementCount() < 2_000
    # Envelope preserved across [0..300] x [100..400]
    rect = d_path.boundingRect()
    assert rect.left() == pytest.approx(0.0, abs=1.0)
    assert rect.right() >= 299.0
    assert rect.top() == pytest.approx(100.0)
    assert rect.bottom() == pytest.approx(400.0)


@pytest.mark.parametrize(
    "style",
    [PathFenceStyle.NONE, PathFenceStyle.WOODEN_FENCE, PathFenceStyle.GRAVEL_PATH, PathFenceStyle.PAVED_PATH],
    ids=lambda s: s.name,
)
def test_selected_dense_polyline_bounds_shadow_stroke_and_selection(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, style: PathFenceStyle
) -> None:
    """Selected 16k-point polylines keep stored width/style, bound shadow/body/selection
    strokes, reuse the zoom-keyed raster cache across repaints, and invalidate cleanly (#928)."""
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.core.item_look import adopt_pen
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    pts = _dense_fence_points(16_000)
    item = PolylineItem(pts, object_type=ObjectType.FENCE, path_fence_style=style)
    pen = QPen(item.pen())
    pen.setWidthF(12.0)
    adopt_pen(item, pen)
    item.shadows_enabled = True

    scene = CanvasScene(600, 600)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(600, 600)
    view.show()
    view.fit_in_view()
    qtbot.waitExposed(view)
    QApplication.processEvents()

    drawn: list[tuple[int, float, bool]] = []
    real_draw_path = QPainter.drawPath

    def spy_draw_path(self_painter: QPainter, path: Any) -> None:
        p = self_painter.pen()
        drawn.append((path.elementCount(), p.widthF(), p.isCosmetic()))
        real_draw_path(self_painter, path)

    monkeypatch.setattr(QPainter, "drawPath", spy_draw_path)

    body_calls = 0
    real_body = PolylineItem._paint_dense_body

    def spy_body(self_item: PolylineItem, *args: Any, **kwargs: Any) -> None:
        nonlocal body_calls
        body_calls += 1
        real_body(self_item, *args, **kwargs)

    monkeypatch.setattr(PolylineItem, "_paint_dense_body", spy_body)

    item.setSelected(True)
    QApplication.processEvents()
    item.update()
    view.viewport().repaint()
    first_body_calls = body_calls
    assert first_body_calls >= 1
    assert item._dense_selected_cache is not None
    # Every stroked path during cold selected paint (shadow + body) is bounded
    # (including stroked texture outlines, which were 361k+ elements before #928)
    assert all(count <= 1_000 for count, _w, _cos in drawn), drawn
    # Stored non-cosmetic width is preserved (not downgraded to 1px cosmetic)
    assert any((not cos) and w >= 12.0 for _c, w, cos in drawn), drawn

    # Repeated selected repaint hits the raster cache without rebuilding
    drawn.clear()
    body_calls = 0
    item.update()
    view.viewport().repaint()
    assert body_calls == 0

    # Zoom change invalidates the zoom-keyed raster cache and rebuilds once
    body_calls = 0
    view.set_zoom(2.0)
    view.centerOn(150.0, 250.0)
    QApplication.processEvents()
    item.update()
    view.viewport().repaint()
    assert body_calls == 1
    body_calls = 0
    item.update()
    view.viewport().repaint()
    assert body_calls == 0

    # Pen edit and deselection clear the cached raster
    new_pen = QPen(item.pen())
    new_pen.setWidthF(16.0)
    adopt_pen(item, new_pen)
    assert item._dense_selected_cache is None
    item.setSelected(False)
    assert item._dense_selected_cache is None
    assert item.point_count == 16_000


@pytest.mark.parametrize("style", [PathFenceStyle.NONE, PathFenceStyle.WOODEN_FENCE], ids=lambda s: s.name)
def test_dense_polyline_exports_preserve_width_and_bound_paths(
    qtbot: Any, tmp_path: Any, style: PathFenceStyle
) -> None:
    """PNG and SVG exports of a 16k-point dense polyline preserve stored width/style
    and bound stroked path elements without mutating ``item.points`` (#928)."""
    from open_garden_planner.core.item_look import adopt_pen
    from open_garden_planner.services.export_service import ExportService
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    pts = _dense_fence_points(16_000)
    item = PolylineItem(pts, object_type=ObjectType.FENCE, path_fence_style=style)
    adopt_pen(item, QPen(QColor(255, 0, 255), 20.0))

    scene = CanvasScene(600.0, 600.0)
    scene.set_shadows_enabled(False)
    scene.addItem(item)

    png_path = tmp_path / f"dense_{style.name}.png"
    ExportService.export_to_png(scene, png_path, dpi=72)
    img = QImage(str(png_path))
    px = _array(img)
    magenta = (px[:, :, 0] > 200) & (px[:, :, 1] < 80) & (px[:, :, 2] > 200)
    assert int(magenta.sum()) > 1_000

    svg_path = tmp_path / f"dense_{style.name}.svg"
    ExportService.export_to_svg(scene, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "<path" in svg_text
    # Bounded stroke path rather than 16,000 raw line segments in SVG
    assert svg_text.count(" L ") < 500
    assert item.point_count == 16_000


def test_selected_dense_polyline_partial_exposed_rect_does_not_poison_cache(qtbot: Any) -> None:
    """Painting a selected dense polyline with a partial ``option.exposedRect``
    must cache the whole polyline, not clip segments outside the first expose (#928)."""
    from PyQt6.QtWidgets import QStyle, QStyleOptionGraphicsItem

    from open_garden_planner.core.item_look import adopt_pen

    pts = _dense_fence_points(16_000)
    item = PolylineItem(pts, object_type=ObjectType.FENCE, path_fence_style=PathFenceStyle.WOODEN_FENCE)
    adopt_pen(item, QPen(QColor(255, 0, 255), 14.0))
    item.shadows_enabled = False
    item.setSelected(True)

    opt_left = QStyleOptionGraphicsItem()
    opt_left.state = QStyle.StateFlag.State_Selected
    opt_left.exposedRect = QRectF(0.0, 90.0, 80.0, 330.0)
    img_left = QImage(420, 440, QImage.Format.Format_RGBA8888_Premultiplied)
    img_left.fill(BACKGROUND)
    p1 = QPainter(img_left)
    try:
        item._paint_dense_selected_cached(p1, opt_left, None)
    finally:
        p1.end()

    opt_full = QStyleOptionGraphicsItem()
    opt_full.state = QStyle.StateFlag.State_Selected
    opt_full.exposedRect = QRectF(0.0, 90.0, 320.0, 330.0)
    img_full = QImage(420, 440, QImage.Format.Format_RGBA8888_Premultiplied)
    img_full.fill(BACKGROUND)
    p2 = QPainter(img_full)
    try:
        item._paint_dense_selected_cached(p2, opt_full, None)
    finally:
        p2.end()

    px = _array(img_full)
    right_half = px[:, 200:310, :]
    assert np.any(right_half != 255), "partial exposedRect poisoned the whole-item selected cache"
