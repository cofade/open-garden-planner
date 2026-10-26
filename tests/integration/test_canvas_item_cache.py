"""Integration tests for canvas item caching, export fidelity, and texture loss.

Tests:
1. DeviceCoordinateCache toggling on selection/deselection across item types
   to prevent selection handle ghosting and rotation lag.
2. Export fidelity: export paths temporarily disable item caches and produce
   100% bit-exact output without cache degradation.
3. ``TestTexturesAreNeverDropped``: a real ``CanvasView`` renders a textured,
   tinted item at five zoom levels and the export path at export scale, and
   asserts the texture survives each one.

Issue #503: the #409 canvas carried a low-zoom "level-of-detail" flat fill that
replaced every texture below 40 % zoom. It never ran (its guard tested
``widget is not None``, but Qt passes ``widget = 0`` for every **cached** paint
and every unselected canvas item is ``DeviceCoordinateCache``), and when
measured on the 990-item reference plan it bought nothing — fit-in-view read
10.61 / 11.50 ms median without it against 10.87 ms with it - the arms' ranges
overlap - because ``DeviceCoordinateCache``
already amortises the textured paint into a one-off cost. The owner's manual
pass confirmed the cost was real: they work at 20-25 % zoom, well under the
threshold, where the branch would have hidden every texture. The branch and its
threshold were removed; what replaced it is the negative pin in (3), so the
detail cannot be silently subtracted again.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CalloutItem,
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
    TextItem,
)
from open_garden_planner.ui.canvas.items.garden_item import (
    disable_cache,
    is_interactive_paint,
)


class TestItemCacheToggling:
    """Verify items enable DeviceCoordinateCache when unselected and NoCache when selected."""

    def test_circle_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_rectangle_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50, object_type=ObjectType.RAISED_BED)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_polygon_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)]
        item = PolygonItem(QPolygonF(points), object_type=ObjectType.GARDEN_BED)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_ellipse_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = EllipseItem(0, 0, 80, 40, object_type=ObjectType.CONTAINER_ROUND)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_polyline_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
        item = PolylineItem(points, object_type=ObjectType.FENCE)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_callout_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = CalloutItem(target=QPointF(0, 0), box_offset=QPointF(20, 20), content="Test Callout")
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_text_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = TextItem(0, 0, content="Sample Text")
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_arc_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        item = ArcItem(center=QPointF(0, 0), radius=50, start_deg=0, span_deg=90)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_bezier_item_cache_toggles(self, qtbot) -> None:
        scene = CanvasScene()
        anchors = [QPointF(0, 0), QPointF(100, 100)]
        handles_in = [QPointF(0, 0), QPointF(50, 100)]
        handles_out = [QPointF(50, 0), QPointF(100, 100)]
        item = BezierItem(anchors=anchors, handles_in=handles_in, handles_out=handles_out)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache


class TestExportCacheFidelity:
    """Verify exports disable item caches and preserve exact visual output."""

    def test_export_service_disables_and_restores_caches(self, qtbot) -> None:
        scene = QGraphicsScene()
        c1 = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        r1 = RectangleItem(0, 0, 100, 50, object_type=ObjectType.RAISED_BED)
        r2 = RectangleItem(100, 100, 100, 50, object_type=ObjectType.LAWN)
        scene.addItem(c1)
        scene.addItem(r1)
        scene.addItem(r2)

        # r2 is selected before export -> its cache mode is NoCache
        r2.setSelected(True)
        assert r2.cacheMode() == QGraphicsItem.CacheMode.NoCache
        assert c1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
        assert r2 in prior_selection
        cached = ExportService._disable_item_caches(scene)
        assert c1.cacheMode() == QGraphicsItem.CacheMode.NoCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.NoCache

        ExportService._restore_overlay_items(hidden_overlay, prior_selection)
        ExportService._restore_item_caches(cached)

        # Unselected items restore to DeviceCoordinateCache
        assert c1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        # Selected item remains selected and MUST remain NoCache to prevent handle ghosting
        assert r2.isSelected() is True
        assert r2.cacheMode() == QGraphicsItem.CacheMode.NoCache

    def test_render_scene_region_preserves_bit_exact_export(self, qtbot) -> None:
        scene = CanvasScene()
        c1 = CircleItem(10, 10, 30, object_type=ObjectType.TREE)
        r1 = RectangleItem(50, 50, 80, 40, object_type=ObjectType.RAISED_BED)
        scene.addItem(c1)
        scene.addItem(r1)

        target_rect = QRectF(0, 0, 200, 200)
        source_rect = QRectF(0, 0, 200, 200)

        # Render 1: via render_scene_region (which uses _uncached_items)
        img1 = QImage(200, 200, QImage.Format.Format_ARGB32)
        img1.fill(QColor("white"))
        p1 = QPainter(img1)
        try:
            render_scene_region(scene, p1, target_rect, source_rect, y_flip=False)
        finally:
            p1.end()

        # Render 2: baseline with caches explicitly disabled
        c1.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        r1.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        img2 = QImage(200, 200, QImage.Format.Format_ARGB32)
        img2.fill(QColor("white"))
        p2 = QPainter(img2)
        try:
            scene.render(p2, target_rect, source_rect)
        finally:
            p2.end()

        assert img1 == img2, "render_scene_region export pixels differ from uncached baseline"


# ── Issue #503: the LOD flat fill must fire on a real canvas ──────────────
#
# Deep blue — not any object type's default, distant in intensity from the
# white page and any pen in play — so a flat fill and its tinted texture land
# in distinct, measurable intensity ranges.
FLAT_FILL = QColor("#ff1f4fd8")
TEXTURE = FillPattern.ROOF_TILES
# What an export render shrinks a plan to: a PDF/SVG export maps a whole plan
# to the page width, which for a 50 m plan on an A4-width page is scale ~0.1
# (72-96 dpi); the load-bearing cases are large canvases on small pages, while
# a plan small enough to be enlarged onto the page sits above 0.4 where the
# LOD branch cannot fire at all. 1:1 renders cannot see the branch either.
EXPORT_SCALE = 0.25


def _style_textured(item: QGraphicsItem) -> QGraphicsItem:
    """Give *item* a texture plus a deep-blue tint, the state a LOD branch saw.

    Only the four **generic** fixtures go through this. The three sprite
    entries in ``_SHAPE_FACTORIES`` deliberately do not: their ``paint()``
    renders an SVG pixmap and ignores the brush, so the thing that must survive
    there is the sprite art, not a texture. The render helpers apply whatever
    brush the fixture sets, so a sprite fixture simply arrives unstyled.

    Why any of this is parametrised at all: the removed branch had seven call
    sites and they were not seven instances of one thing — two behind
    ``is_plant``, two behind ``is_furniture_type``. See
    ``TestTexturesAreNeverDropped`` and ``scripts/verify_lod_removal_mutations.py``.
    """
    item.fill_pattern = TEXTURE
    item.fill_color = QColor(FLAT_FILL)
    item.setBrush(create_pattern_brush(TEXTURE, QColor(FLAT_FILL)))
    return item


# id -> factory, for every class AND branch the deleted #409 branch touched.
#
# Seven call sites, and they were not seven instances of one thing: two sat
# inside ``if is_plant`` and two inside ``if is_furniture_type``, behind type
# predicates that a ``GENERIC_*`` fixture never satisfies. A table of the four
# generic shapes therefore watched four of seven — and the three unwatched ones
# are exactly the sprite paths the owner's manual pass objected to. Verified by
# mutation: a ``< 0.4`` flat fill in a plant or furniture branch renders a
# TREE circle from interior std 43.09 to 0.00 — a flat brown disc — while every
# test in the repo stayed green. Hence plant and furniture entries below, with
# the sprite art itself as the thing that must survive.
_SHAPE_FACTORIES: dict[str, Callable[[], QGraphicsItem]] = {
    "rectangle": lambda: _style_textured(
        RectangleItem(200, 200, 600, 400, object_type=ObjectType.GENERIC_RECTANGLE)
    ),
    "circle": lambda: _style_textured(
        CircleItem(500, 400, 400, object_type=ObjectType.GENERIC_CIRCLE)
    ),
    "ellipse": lambda: _style_textured(
        EllipseItem(200, 200, 600, 400, object_type=ObjectType.GENERIC_ELLIPSE)
    ),
    "polygon": lambda: _style_textured(
        PolygonItem(
            [
                QPointF(300, 250),
                QPointF(700, 250),
                QPointF(700, 550),
                QPointF(300, 550),
            ],
            object_type=ObjectType.GENERIC_POLYGON,
        )
    ),
    # Sprite paths: paint() draws an SVG pixmap and ignores the brush, so what
    # is under test is the sprite art, not the texture brush.
    "plant-circle": lambda: CircleItem(500, 400, 400, object_type=ObjectType.TREE),
    "furniture-rectangle": lambda: RectangleItem(
        200, 200, 600, 400, object_type=ObjectType.BENCH
    ),
    "furniture-circle": lambda: CircleItem(
        500, 400, 400, object_type=ObjectType.TABLE_ROUND
    ),
}
_SHAPE_IDS = list(_SHAPE_FACTORIES)


MASK_COLOR = QColor("#ff00ff")  # appears nowhere else: a mask, not a colour


def _qimage_array(image: QImage) -> np.ndarray:
    w, h = image.width(), image.height()
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    buf = np.frombuffer(ptr, dtype=np.uint8).reshape(h, image.bytesPerLine())
    return buf[:, : w * 4].reshape(h, w, 4).astype(np.int16)


def _erode(mask: np.ndarray, radius: int = 3) -> np.ndarray:
    """Drop ``radius`` px of boundary: antialiasing and the outline are not texture."""
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    h, w = mask.shape
    out = mask.copy()  # the ORIGINAL shape; padded is only the lookback window
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            out &= padded[dy : dy + h, dx : dx + w]
    return out


def _mask_from(
    path: QPainterPath,
    image: QImage,
    *,
    erode: int = 3,
    scale: float = 1.0,
    translate: QPointF | None = None,
) -> np.ndarray:
    """Fill *path* in :data:`MASK_COLOR` into a copy of *image* and read it back.

    The path comes from ``QGraphicsItem.shape()``, i.e. the item's GEOMETRY.
    That matters: a mask produced by painting the item a second time is not a
    mask at all, because any flat-fill branch overrides the brush on that pass
    too — so a faithful re-introduction of the deleted code empties the mask
    instead of showing up as a texture failure, and the pin then fails for the
    wrong reason. Geometry cannot be overridden by ``paint()``.

    ``scale`` and ``translate`` must reproduce the transform the image was
    rendered under, **both of them**: ``QGraphicsScene.render(painter, target,
    source)`` maps ``source`` onto ``target``, so it composes the painter's own
    scale with a translation by ``-source.topLeft()``. Supplying the scale alone
    leaves the mask displaced — which is not merely imprecise, it is
    *silently wrong*: the displaced mask lands partly on page background, and
    background-versus-fill contrast reads as a healthy luminance spread. That is
    how the circle's export case came to pass with a flat fill live (45.97) and
    fail once aligned (1.67).
    """
    canvas = QImage(image.size(), image.format())
    canvas.fill(QColor("white"))
    painter = QPainter(canvas)
    try:
        painter.scale(scale, scale)
        if translate is not None:
            painter.translate(translate.x(), translate.y())
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(MASK_COLOR))
        painter.drawPath(path)
    finally:
        painter.end()
    px = _qimage_array(canvas)
    mask = (
        (np.abs(px[:, :, 0] - MASK_COLOR.red()) <= 8)
        & (np.abs(px[:, :, 1] - MASK_COLOR.green()) <= 8)
        & (np.abs(px[:, :, 2] - MASK_COLOR.blue()) <= 8)
    )
    return _erode(mask, radius=erode)


def _canvas_render(
    qtbot: object, factory: Callable[[], QGraphicsItem], *, zoom: float
) -> tuple[np.ndarray, np.ndarray]:
    """(intensity array, interior mask) for ``factory()``'s item at ``zoom``.

    The mask is the item's own shape, mapped through the view, so it is correct
    for a circle, an ellipse and a polygon and not just a rectangle. This is
    the second trap this harness fell into: sampling the item's bounding box was
    right for a rectangle and vacuous for the other three, because the box
    corners are page background — a solid blue circle measured as high-contrast
    and passed (verified: the branch fires, the test does not notice).
    """
    item = factory()
    item.setBrush(create_pattern_brush(TEXTURE, QColor(FLAT_FILL)))

    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(700, 700)
    view.show()
    QApplication.processEvents()
    view.set_zoom(zoom)
    view.centerOn(item.sceneBoundingRect().center())
    QApplication.processEvents()
    view.resetCachedContent()  # force every device cache to rebuild -> paint() runs
    QApplication.processEvents()

    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        view.viewport().render(painter)
    finally:
        painter.end()

    mask = _mask_from(view.mapFromScene(item.mapToScene(item.shape())), image)
    return _qimage_array(image)[:, :, :3].mean(axis=2), mask


def _export_render(factory: Callable[[], QGraphicsItem]) -> tuple[np.ndarray, np.ndarray]:
    """The same pair, through the project's export cache-disabling convention.

    ``source`` comes from the item **after** it is in the scene. An earlier
    version took it from a throwaway ``probe`` that was never added to anything,
    relying on an orphan item's ``sceneBoundingRect()`` matching the scene-bound
    one. All seven fixtures do agree today (measured: 0 differences), but that is
    an implicit Qt assumption of exactly the kind that produced the round-2
    export defect, and it is only read inside the ``try`` below — so one line
    moves and the probe disappears.
    """
    item = factory()
    item.setBrush(create_pattern_brush(TEXTURE, QColor(FLAT_FILL)))
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    source = QRectF(item.sceneBoundingRect())
    assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
    cached = ExportService._disable_item_caches(scene)
    try:
        image = QImage(
            max(1, int(source.width() * EXPORT_SCALE)),
            max(1, int(source.height() * EXPORT_SCALE)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            painter.scale(EXPORT_SCALE, EXPORT_SCALE)
            scene.render(
                painter,
                QRectF(0, 0, source.width(), source.height()),
                source,
            )
        finally:
            painter.end()
        mask = _mask_from(
            item.mapToScene(item.shape()),
            image,
            erode=1,
            scale=EXPORT_SCALE,
            # scene.render maps source.topLeft() to the target's origin; without
            # this translate the mask is displaced (see TestTheMaskIsTheItem).
            translate=QPointF(-source.left(), -source.top()),
        )
        return _qimage_array(image)[:, :, :3].mean(axis=2), mask
    finally:
        ExportService._restore_item_caches(cached)


def _interior_stats(intensity: np.ndarray, mask: np.ndarray) -> tuple[int, float]:
    """(sample count, intensity std) over the eroded interior of the shape."""
    values = intensity[mask]
    return int(values.size), float(values.std()) if values.size else 0.0


# Calibrated on the dev box with THIS sampler, per shape and zoom level (interior
# pixels after a 3 px erosion on the canvas, 1 px in the export; intensity std of
# the mean RGB). The floor is 8.0 and a solid fill reads 0.00:
#
#   shape                  0.1     0.25    0.4     0.75    1.0     export
#   rectangle            18.06   14.04   19.06   19.40   20.19     15.95
#   circle               18.08   14.01   18.95   19.31   28.39     16.02
#   ellipse              18.19   14.03   18.99   19.33   20.16     16.00
#   polygon              17.89   13.86   18.82   19.33   20.18     15.47
#   plant-circle         37.98   37.55   37.59   37.89   43.17     37.95
#   furniture-rectangle  29.66   32.32   35.80   38.59   39.57     38.16
#   furniture-circle     29.69   30.21   31.21   34.24   38.17     34.07
#
# Worst case 13.86, i.e. 1.73x the floor; the sprite paths sit far above it
# because their interior is drawn art rather than a texture brush.
#
# The four textured shapes' export column converging on 15.47-16.02 is itself a
# calibration check: while the export mask was displaced by a forgotten
# -source.topLeft(), those four read 15.83 / 37.27 / 49.85 / 16.37 — the circle
# and ellipse were sampling page background. Four similar shapes rendering
# similar textures must agree; four scattered numbers meant the instrument was
# wrong, not the paint.
#
# Interior pixel counts run 816 (polygon at 0.1) to 429 986 (circle at 1.0),
# which is why there is no absolute sample floor anywhere in this class.
#
# The bound is one-sided on purpose: it says the texture IS there, with no
# ceiling on its contrast. A future change may legitimately soften a texture,
# and it must not be able to do so by deleting it.
# The samples come from the item's own SHAPE (QGraphicsItem.shape()), never from
# its bounding box: the box corners are page background for a circle, an ellipse
# or a polygon, and the first version of this harness measured a solid blue
# circle as high-contrast because of them — so the pin was vacuous on three of
# the four classes. Nor from a colour filter: that version matched "blue-ish"
# pixels image-wide, and on the Linux/offscreen CI the scene's faint background
# passed the filter (spread 62.59 there against 0.00 on Windows, one red CI job,
# no reproduction locally). Nor from a second paint of the item, which any
# flat-fill branch would override on its way through.
# ``TestTheMaskIsTheItem`` holds all of that to account.
TEXTURE_SPREAD_MIN = 8.0


class TestTexturesAreNeverDropped:
    """The canvas keeps every texture at every zoom level, in every shape and
    sprite path the deleted branch touched (#503).

    A texture has luminance spread (tiles, grout); a flat fill is one colour,
    so the intensity std of a fill's interior tells the two apart. This class
    asserts the *absence* of the regression rather than the presence of a
    feature: the #409 low-zoom flat fill was removed in #503 because it was
    measured to buy nothing (PF-CAN-20), and removing dead code leaves
    no test behind to catch it creeping back.

    **It is parametrised over rectangle, circle, ellipse and polygon *and* over the
    plant and furniture sprite paths**, because the seven deleted call sites were
    never seven instances of one thing: two sat inside ``if is_plant`` and two
    inside ``if is_furniture_type``, behind type predicates a ``GENERIC_*``
    fixture never satisfies. A four-shape table watched four of seven, and the
    three unwatched ones are exactly the sprite paths the owner's manual pass
    objected to — verified by mutation: a ``< 0.4`` flat fill in a plant branch
    renders a TREE circle from interior std 43.09 to 0.00, a flat brown disc,
    while 212 tests stayed green.

    **Three sampling traps, all paid for here.** The first version sampled the
    item's bounding box inset 10 %, which is right for a rectangle and vacuous
    for the other three: the box corners are page background, so a solid fill
    inside a circle still measured a high spread and passed (verified — the
    branch fires, the test does not notice). The mask is now the item's own
    ``QGraphicsItem.shape()``: not a second paint, because any flat-fill branch
    overrides the brush on that pass too, and not alpha, because the scene paints
    an opaque background. Second, an absolute sample floor fails the 0.1 zoom
    case for being small rather than wrong, so there is none.

    Third, and the reason ``test_the_mask_covers_the_painted_item`` exists: a
    mask in the wrong coordinate frame does not fail, it *reads background* —
    background-versus-fill contrast looks like a healthy luminance spread. The
    export mask had exactly this bug (scale applied, ``-source.topLeft()``
    forgotten) and the circle's export case passed at 45.97 with a flat fill live.
    Every defect this review surfaced reduces to one unasserted invariant, "the
    mask must be the item's interior", so that is now a test rather than a
    comment in a docstring.

    Measured on the 990-item reference plan, the removed branch changed nothing:
    ``fit_in_view`` at zoom 0.316 read 10.61 / 11.50 ms median with it disabled and
    10.87 ms with it live, ``zoom_step`` at 0.348 read 7.97 / 7.98 ms against
    8.20 ms - the two arms' ranges overlap and no reversed-order run was taken, so
    no claim about which is faster survives, and every NFR-PERF-01 budget test
    passes either way. ``DeviceCoordinateCache``
    already amortises the textured paint into a one-off cost, so the LOD could
    only ever subtract detail. The owner works at 20-25 % zoom, where the
    removed threshold (0.4) would have hidden every texture.
    """

    @pytest.mark.parametrize("shape", _SHAPE_IDS)
    @pytest.mark.parametrize("zoom", [0.1, 0.25, 0.4, 0.75, 1.0])
    def test_the_canvas_keeps_the_texture_at_every_zoom(
        self, qtbot: object, shape: str, zoom: float
    ) -> None:
        intensity, mask = _canvas_render(qtbot, _SHAPE_FACTORIES[shape], zoom=zoom)
        count, spread = _interior_stats(intensity, mask)
        # No absolute sample floor: the interior area depends on the shape class
        # and the zoom, so any constant is a calibration trap that fires on the
        # smallest case for being small. An empty mask reads 0.0 spread by
        # construction (_interior_stats), so the assertion below already
        # catches "nothing rendered" — this is the explicit version of that.
        assert count > 0, f"the {shape}'s interior mask was empty at zoom {zoom}"
        assert spread > TEXTURE_SPREAD_MIN, (
            f"the {shape}'s texture was replaced by a flat fill at zoom {zoom} "
            f"(interior spread {spread:.2f} over {count} px); #503 removed the "
            "low-zoom flat fill because it cost detail and bought no measurable "
            "time"
        )

    @pytest.mark.parametrize("shape", _SHAPE_IDS)
    def test_the_export_keeps_the_texture(
        self, qtbot: object, shape: str
    ) -> None:
        intensity, mask = _export_render(_SHAPE_FACTORIES[shape])
        count, spread = _interior_stats(intensity, mask)
        assert count > 0, f"the {shape}'s interior mask was empty in the export"
        assert spread > TEXTURE_SPREAD_MIN, (
            f"the export lost the {shape}'s texture; cache-disabled render "
            "paths must keep full detail"
        )


class TestTheMaskIsTheItem:
    """The invariant every other test here silently depends on (#503, review).

    "The mask is the item's interior" was asserted nowhere, and a mask in the
    wrong coordinate frame **passes**: it lands partly on page background, and
    background-versus-fill contrast is exactly what a luminance-spread statistic
    reads as texture. Three separate defects in this harness reduced to this one
    omission — the bounding-box sampler, the second-paint sampler, and the export
    mask that applied ``scale`` but forgot ``-source.topLeft()`` (the circle's
    export case read spread 45.97 with a flat fill live, and 1.67 once aligned).

    Two honest limits on what a mean comparison can see, both measured rather than
    assumed:

    - **Gross frame errors, not small displacements.** Shifting the *canvas* mask
      40 px in both axes still passes all 71 tests; 80 px is the first shift that
      fails. The items are 400-600 px across at zoom 1.0, so a mean over a large
      interior cannot resolve a 10 % displacement. The export half is far sharper
      — dropping the translate fires four of seven, because there the mask is only
      a few pixels of displacement away from being page.
    - **Dark-on-light by construction.** Every fixture is darker than the page
      behind it, and a flat fill therefore collapses toward the failure direction.
      A *lighter* fixture added later — a white raised bed, say — would false-fail
      here with a message about the mask being displaced. The asymmetry is the safe
      direction; it is stated so nobody has to rediscover it.
    """

    @pytest.mark.parametrize("shape", _SHAPE_IDS)
    def test_the_canvas_mask_matches_the_painted_item(
        self, qtbot: object, shape: str
    ) -> None:
        intensity, mask = _canvas_render(qtbot, _SHAPE_FACTORIES[shape], zoom=1.0)
        inside = intensity[mask]
        outside = intensity[~mask]
        assert inside.size > 500, f"{shape}: mask covers only {inside.size} px"
        assert outside.size > 100, f"{shape}: nothing outside the mask to compare"
        # The page behind a CanvasScene is a light beige/grey; a sampled interior
        # that is indistinguishable from it is reading background, not the item.
        assert inside.mean() < outside.mean() - 10.0, (
            f"{shape}: the masked interior averages {inside.mean():.1f}, the "
            f"page averages {outside.mean():.1f} — the mask is not on the item"
        )

    @pytest.mark.parametrize("shape", _SHAPE_IDS)
    def test_the_export_mask_matches_the_painted_item(self, shape: str) -> None:
        intensity, mask = _export_render(_SHAPE_FACTORIES[shape])
        inside = intensity[mask]
        outside = intensity[~mask]
        assert inside.size > 200, f"{shape}: export mask covers only {inside.size} px"
        assert outside.size > 100, f"{shape}: nothing outside the export mask"
        assert inside.mean() < outside.mean() - 10.0, (
            f"{shape}: the export mask averages {inside.mean():.1f} against the "
            f"page's {outside.mean():.1f} — the mask is displaced"
        )


class TestIsInteractivePaint:
    """The predicate's own halves, called directly (#503).

    ``is_interactive_paint`` is now a three-line expression used by exactly one
    caller (``PolygonItem``'s over-budget bound), so its docstring's claim that
    "the direct-call tests exercise it" had no test behind it. These are those
    tests: the cache-mode half (the one the #503 story is about) and the
    ``widget is not None`` half, which the docstring keeps as robustness for a
    cache-disabled item painted by a real widget.

    Deliberately direct calls, not a rendered scenario: this pins the predicate,
    where the #503 defect was a predicate whose condition never held on the
    path it guarded.
    """

    def test_a_cached_item_is_interactive_without_a_widget(self) -> None:
        """The #503 case: Qt hands ``widget = 0`` to every cached paint."""
        item = RectangleItem(0, 0, 10, 10, object_type=ObjectType.GENERIC_RECTANGLE)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert is_interactive_paint(item, None) is True

    def test_a_cache_disabled_item_is_not_interactive_without_a_widget(
        self,
    ) -> None:
        """The export / print / agent render convention disables caches first."""
        item = RectangleItem(0, 0, 10, 10, object_type=ObjectType.GENERIC_RECTANGLE)
        disable_cache(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache
        assert is_interactive_paint(item, None) is False

    def test_a_real_widget_wins_even_with_the_cache_disabled(
        self, qtbot
    ) -> None:
        """The robustness half the docstring keeps, pinned so it stays true."""
        item = RectangleItem(0, 0, 10, 10, object_type=ObjectType.GENERIC_RECTANGLE)
        disable_cache(item)
        widget = QWidget()
        qtbot.addWidget(widget)
        assert is_interactive_paint(item, widget) is True

    def test_a_non_item_object_is_not_interactive(self) -> None:
        """The ``isinstance`` guard. The parameter is typed ``object``, so this is
        reachable by a caller, and the predicate returns ``False`` rather than
        raising; the sole production caller passes a ``QGraphicsItem``."""
        assert is_interactive_paint(object(), None) is False
