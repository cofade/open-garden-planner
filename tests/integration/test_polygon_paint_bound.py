"""Integration tests for the 2D polygon paint bound (issue #472).

A plan file may hold a polygon with any number of vertices, and a reflex-heavy
outline (a "comb", teeth across its whole height) makes one antialiased fill
quadratic — seconds to minutes — freezing the window. Issue #472 asks for "a
stated bound on what is painted at full detail, or a degraded paint beyond it".

The fix bounds full detail at `MAX_FULL_DETAIL_VERTICES`; above it an unselected
item paints the exact outline with a **cosmetic** 1-px pen and no fill during
interactive painting, while exports/offscreen renders (``widget is None``) and a
selected item keep the exact fill. The cosmetic pen matters: Qt strokes a wide
solid pen by building a fill, so reusing the item's own pen would leave the
degraded frame quadratic too (measured in the bug report and in ADR-057).

This pins: the degrade is chosen above the bound and is orders of magnitude
cheaper; the exact fill is kept at the bound, in exports and when selected; and
a hostile polygon is refused at the load seam without dropping the rest of a
plan.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.polygon_item import (
    MAX_FULL_DETAIL_VERTICES,
    MAX_POLYGON_VERTICES,
    PolygonItem,
)

_FILL = QColor(200, 40, 40)
_BACKGROUND = QColor(255, 255, 255)


def _issue_comb(vertices: int, side: float = 600.0) -> QPolygonF:
    """The bug report's shape: a square outline drawn as full-height teeth.

    Exactly ``vertices`` points (a multiple of 4): each tooth contributes two
    vertical edges, so a scanline crosses ~one edge per tooth.
    """
    assert vertices % 4 == 0 and vertices >= 4
    teeth = vertices // 4
    step = side / teeth
    poly = QPolygonF()
    for i in range(teeth):
        x0 = i * step
        poly.append(QPointF(x0, 0.0))
        poly.append(QPointF(x0, side))
        poly.append(QPointF(x0 + step * 0.5, side))
        poly.append(QPointF(x0 + step * 0.5, 0.0))
    assert poly.count() == vertices
    return poly


def _subdivided_square(vertices: int, side: float = 600.0) -> QPolygonF:
    """A solid square whose outline holds exactly ``vertices`` points.

    Subdividing each edge gives a polygon with a large, unambiguous interior —
    so a *fill* inks much more than a hairline *outline* — while its vertex
    count can be set freely above the paint bound. (Its fill is cheap because it
    is convex; the comb above is used for the cost assertion.)
    """
    assert vertices >= 4
    per_edge = [vertices // 4] * 4
    for i in range(vertices % 4):
        per_edge[i] += 1
    corners = [
        QPointF(0, 0),
        QPointF(side, 0),
        QPointF(side, side),
        QPointF(0, side),
    ]
    poly = QPolygonF()
    for e in range(4):
        a = corners[e]
        b = corners[(e + 1) % 4]
        n = per_edge[e]
        for i in range(n):
            t = i / n
            poly.append(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    assert poly.count() == vertices
    return poly


def _square_item(vertices: int) -> PolygonItem:
    item = PolygonItem(vertices=_subdivided_square(vertices), object_type=ObjectType.LAWN)
    item.setBrush(_FILL)
    return item


def _comb_item(vertices: int) -> PolygonItem:
    # No pen override: the item keeps its object type's pen (LAWN: 2.0 solid),
    # which is exactly the pen whose stroke Qt turns into a fill.
    item = PolygonItem(vertices=_issue_comb(vertices), object_type=ObjectType.LAWN)
    item.setBrush(_FILL)
    return item


def _paint(item: PolygonItem, widget: QWidget | None) -> tuple[QImage, float]:
    image = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(_BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        t0 = time.perf_counter()
        item.paint(painter, QStyleOptionGraphicsItem(), widget)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
    finally:
        painter.end()
    return image, elapsed_ms


def _ink(image: QImage) -> int:
    """Count pixels that are not the background — a fill inks far more than a hairline."""
    background = _BACKGROUND.rgb()
    return sum(
        1
        for y in range(0, image.height(), 4)
        for x in range(0, image.width(), 4)
        if image.pixel(x, y) != background
    )


@pytest.fixture()
def _qt(qtbot: object) -> object:  # noqa: ARG001 — ensures a QApplication exists
    return qtbot


class TestDegradedInteractivePaint:
    def test_over_budget_polygon_paints_an_outline_not_a_fill(self, _qt: object) -> None:
        item = _square_item(MAX_FULL_DETAIL_VERTICES * 2)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        # The degraded on-screen frame inks a tiny fraction of the exact fill.
        assert _ink(on_screen) * 3 < _ink(exported)

    def test_over_budget_comb_paint_is_far_cheaper_than_full_detail(self, _qt: object) -> None:
        item = _comb_item(MAX_FULL_DETAIL_VERTICES * 2)
        _, export_ms = _paint(item, None)
        _, degrade_ms = _paint(item, QWidget())
        assert degrade_ms * 4 < export_ms, (
            f"degraded paint {degrade_ms:.1f} ms is not far cheaper than "
            f"full detail {export_ms:.1f} ms"
        )

    @pytest.mark.parametrize("vertices", [8, MAX_FULL_DETAIL_VERTICES])
    def test_at_or_below_budget_paints_the_exact_fill(
        self, _qt: object, vertices: int
    ) -> None:
        item = _square_item(vertices)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        assert _ink(on_screen) == _ink(exported)


class TestFullDetailIsNeverLost:
    def test_export_paints_the_exact_fill(self, _qt: object) -> None:
        item = _square_item(MAX_FULL_DETAIL_VERTICES * 2)
        exported, _ = _paint(item, None)
        on_screen, _ = _paint(item, QWidget())
        assert _ink(exported) > _ink(on_screen) * 3

    def test_selected_polygon_paints_the_exact_fill(self, _qt: object) -> None:
        item = _square_item(MAX_FULL_DETAIL_VERTICES * 2)
        item.setSelected(True)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        assert _ink(on_screen) == _ink(exported)


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


class TestTheBoundSitsBelowThePathologicalCount:
    """Pin the threshold, not just the mechanism (round-1 review, issue #472).

    The first draft set the bound at 1,024 vertices — the very count the bug
    report calls pathological — so the report's own reproduction was never
    degraded. These use a literal count so a future change back to that bound
    fails, even though the cosmetic-pen mechanism would still be in place.
    """

    def test_a_1024_vertex_polygon_is_degraded(self, _qt: object) -> None:
        assert MAX_FULL_DETAIL_VERTICES <= 512, (
            "the full-detail bound must sit below the 1,024-vertex comb the bug "
            "report measured at 10.5 s"
        )
        item = _square_item(1024)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        assert _ink(on_screen) < _ink(exported), "a 1,024-vertex polygon must be degraded"

    def test_the_bound_itself_is_not_degraded(self, _qt: object) -> None:
        item = _square_item(MAX_FULL_DETAIL_VERTICES)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        assert _ink(on_screen) == _ink(exported)

    def test_one_vertex_above_the_bound_is_degraded(self, _qt: object) -> None:
        item = _square_item(MAX_FULL_DETAIL_VERTICES + 4)
        on_screen, _ = _paint(item, QWidget())
        exported, _ = _paint(item, None)
        assert _ink(on_screen) < _ink(exported)
