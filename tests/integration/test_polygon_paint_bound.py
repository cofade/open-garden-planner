"""Integration tests for the 2D polygon paint bound (issue #472).

A plan file may hold a polygon with any number of vertices, and a reflex-heavy
outline (a "comb", teeth across its whole height) makes one antialiased fill
quadratic — seconds to minutes — freezing the window. Issue #472 asks for "a
stated bound on what is painted at full detail, or a degraded paint beyond it".

`PolygonItem` bounds full detail at `MAX_FULL_DETAIL_VERTICES`; above it an
unselected item paints the exact outline with a **cosmetic** 1-px pen and no
fill, while exports/offscreen renders and a selected item keep the exact fill.

**These tests drive a real `CanvasView`** (and, for the export case, the real
`ExportService._disable_item_caches` convention). That matters: an earlier
version of this file called `item.paint(...)` directly, which passed while the
degrade was unreachable in the product — Qt passes `widget = 0` for every
**cached** paint, and unselected canvas items are cached, so a `widget`-based
"interactive" test never fired. A direct `paint()` call cannot see that.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import (
    MAX_FULL_DETAIL_VERTICES,
    MAX_POLYGON_VERTICES,
    PolygonItem,
)

# A colour that appears nowhere else (not the page, not a pen, not a texture),
# so counting it measures exactly "did the fill paint?".
FILL = QColor("#ff00ff")
SIDE = 600.0


def _issue_comb(vertices: int) -> list[QPointF]:
    """The bug report's shape: full-height teeth (a scanline per tooth)."""
    assert vertices % 4 == 0 and vertices >= 4
    teeth = vertices // 4
    step = SIDE / teeth
    points: list[QPointF] = []
    for i in range(teeth):
        x0 = i * step
        points += [
            QPointF(x0, 0.0),
            QPointF(x0, SIDE),
            QPointF(x0 + step * 0.5, SIDE),
            QPointF(x0 + step * 0.5, 0.0),
        ]
    return points


def _subdivided_square(vertices: int) -> list[QPointF]:
    """A solid square with exactly ``vertices`` outline points and a big interior."""
    assert vertices >= 4
    per_edge = [vertices // 4] * 4
    for i in range(vertices % 4):
        per_edge[i] += 1
    corners = [
        QPointF(0, 0),
        QPointF(SIDE, 0),
        QPointF(SIDE, SIDE),
        QPointF(0, SIDE),
    ]
    points: list[QPointF] = []
    for e in range(4):
        a, b, n = corners[e], corners[(e + 1) % 4], per_edge[e]
        for i in range(n):
            t = i / n
            points.append(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    assert len(points) == vertices
    return points


def _item(points: list[QPointF]) -> PolygonItem:
    # No pen override: the item keeps its object type's pen (LAWN: 2.0 solid),
    # which is exactly the pen whose stroke Qt turns into a fill.
    item = PolygonItem(vertices=points, object_type=ObjectType.LAWN)
    item.setBrush(FILL)
    return item


def _count_fill(image: QImage) -> int:
    """Sampled pixels close to :data:`FILL` — how much of the fill painted."""
    found = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            colour = QColor(image.pixel(x, y))
            if (
                abs(colour.red() - FILL.red()) < 40
                and abs(colour.green() - FILL.green()) < 40
                and abs(colour.blue() - FILL.blue()) < 40
            ):
                found += 1
    return found


def interactive_render(item: PolygonItem, *, selected: bool = False) -> QImage:
    """What the canvas shows: a real CanvasView, caches ON, cache forced fresh.

    Rendered at 100 % zoom on purpose. Below 0.4 the canvas's own LOD flat fill
    (#409, corrected in #503) replaces a patterned item's texture with its flat
    ``fill_color`` — correct product behaviour, but it would stop the below-budget
    assertions from pinning the *exact* fill they exist for. Full detail is the
    product contract at this zoom, so that is what this harness measures.
    """
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    if selected:
        item.setSelected(True)
    view = CanvasView(scene)
    view.resize(700, 700)
    view.show()
    QApplication.processEvents()
    view.set_zoom(1.0)
    view.centerOn(QPointF(SIDE / 2, SIDE / 2))
    QApplication.processEvents()
    view.resetCachedContent()  # force every device cache to rebuild → paint() runs
    QApplication.processEvents()
    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        view.viewport().render(painter)
    finally:
        painter.end()
    return image


def export_render(item: PolygonItem) -> QImage:
    """What an export shows: the project's own cache-disabling convention."""
    scene = QGraphicsScene()
    scene.addItem(item)
    cached = ExportService._disable_item_caches(scene)
    source = item.sceneBoundingRect()
    image = QImage(
        max(1, int(source.width())), max(1, int(source.height())),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        scene.render(painter, QRectF(0, 0, image.width(), image.height()), source)
    finally:
        painter.end()
    ExportService._restore_item_caches(cached)
    scene.removeItem(item)
    return image


@pytest.fixture()
def _qt(qtbot: object) -> object:  # noqa: ARG001 — ensures a QApplication exists
    return qtbot


# The polygon is a 600-unit square in a 2000-unit scene rendered at 100 % zoom
# in a 700x700 viewport, so a FILLED canvas render measures ~89,400 sampled
# magenta pixels and a DEGRADED one only the outline the item's own (green) pen
# draws — zero of them. The export render is 1:1 and measures ~89,000. Explicit
# thresholds, so a change in either harness shows up as a failure rather than a
# silent slide.
CANVAS_FILLED = 3_000
CANVAS_DEGRADED = 50
EXPORT_FILLED = 3_000


class TestTheInteractiveCanvasDegrades:
    def test_over_budget_polygon_paints_no_fill_on_the_canvas(self, _qt: object) -> None:
        item = _item(_subdivided_square(MAX_FULL_DETAIL_VERTICES * 4))
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert _count_fill(interactive_render(item)) < CANVAS_DEGRADED, (
            "the canvas did not degrade: the fill is still painted"
        )
        assert _count_fill(export_render(item)) > EXPORT_FILLED

    @pytest.mark.parametrize("vertices", [8, MAX_FULL_DETAIL_VERTICES])
    def test_at_or_below_budget_paints_the_exact_fill(
        self, _qt: object, vertices: int
    ) -> None:
        item = _item(_subdivided_square(vertices))
        assert _count_fill(interactive_render(item)) > CANVAS_FILLED, (
            "the fill is missing at or below the bound"
        )


class TestFullDetailIsNeverLost:
    def test_export_paints_the_exact_fill(self, _qt: object) -> None:
        item = _item(_subdivided_square(MAX_FULL_DETAIL_VERTICES * 4))
        assert _count_fill(export_render(item)) > EXPORT_FILLED

    def test_selected_polygon_paints_the_exact_fill(self, _qt: object) -> None:
        item = _item(_subdivided_square(MAX_FULL_DETAIL_VERTICES * 4))
        assert _count_fill(interactive_render(item, selected=True)) > CANVAS_FILLED, (
            "a selected item must paint the exact fill"
        )


class TestTheBoundSitsBelowThePathologicalCount:
    """Pin the threshold, not just the mechanism (round-1 review, issue #472)."""

    def test_a_1024_vertex_polygon_is_degraded(self, _qt: object) -> None:
        assert MAX_FULL_DETAIL_VERTICES <= 512, (
            "the full-detail bound must sit below the 1,024-vertex comb the bug "
            "report measured at 10.5 s"
        )
        item = _item(_subdivided_square(1024))
        assert _count_fill(interactive_render(item)) < CANVAS_DEGRADED

    def test_the_bound_itself_is_not_degraded(self, _qt: object) -> None:
        item = _item(_subdivided_square(MAX_FULL_DETAIL_VERTICES))
        assert _count_fill(interactive_render(item)) > CANVAS_FILLED

    def test_one_vertex_above_the_bound_is_degraded(self, _qt: object) -> None:
        item = _item(_subdivided_square(MAX_FULL_DETAIL_VERTICES + 4))
        assert _count_fill(interactive_render(item)) < CANVAS_DEGRADED


class TestHostilePolygonIsRefusedAtLoad:
    def test_refuses_a_polygon_above_the_load_ceiling(
        self, _qt: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "open_garden_planner.ui.canvas.items.polygon_item.MAX_POLYGON_VERTICES",
            8,
        )
        hostile = {
            "type": "polygon",
            "object_type": "LAWN",
            "points": [{"x": float(i), "y": 0.0} for i in range(9)],
        }
        assert ProjectManager._deserialize_item_core(hostile) is None

    def test_accepts_a_polygon_at_the_load_ceiling(
        self, _qt: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "open_garden_planner.ui.canvas.items.polygon_item.MAX_POLYGON_VERTICES",
            8,
        )
        ok = {
            "type": "polygon",
            "object_type": "LAWN",
            "points": [{"x": float(i), "y": float(i % 2)} for i in range(8)],
        }
        item = ProjectManager._deserialize_item_core(ok)
        assert isinstance(item, PolygonItem)

    def test_one_hostile_polygon_does_not_drop_the_rest_of_a_plan(
        self, _qt: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "open_garden_planner.ui.canvas.items.polygon_item.MAX_POLYGON_VERTICES",
            8,
        )
        plan = {
            "version": "1.4",
            "canvas": {"width": 1000.0, "height": 1000.0},
            "layers": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Layer 1",
                    "visible": True,
                    "locked": False,
                    "opacity": 1.0,
                    "z_order": 0,
                }
            ],
            "objects": [
                {
                    "type": "rectangle",
                    "item_id": "22222222-2222-2222-2222-222222222222",
                    "x": 10.0,
                    "y": 10.0,
                    "width": 100.0,
                    "height": 100.0,
                    "object_type": "GARDEN_BED",
                },
                {
                    "type": "polygon",
                    "item_id": "33333333-3333-3333-3333-333333333333",
                    "object_type": "LAWN",
                    "points": [{"x": float(i), "y": 0.0} for i in range(9)],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hostile.ogp"
            path.write_text(json.dumps(plan), encoding="utf-8")
            scene = CanvasScene()
            ProjectManager().load(scene, path)

        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        assert [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert [i for i in scene.items() if isinstance(i, PolygonItem)] == []


def test_the_two_bounds_are_consistent() -> None:
    """The load ceiling must leave room for the degraded outline (issue #472)."""
    assert MAX_POLYGON_VERTICES >= 10_000
    assert MAX_FULL_DETAIL_VERTICES < MAX_POLYGON_VERTICES
