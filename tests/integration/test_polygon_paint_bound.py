"""Integration tests for the 2D polygon paint bound (issue #472).

A plan file may hold a polygon with any number of vertices, and a reflex-heavy
outline (a "comb") makes one antialiased fill take from seconds to minutes,
freezing the window. Issue #472 asks for a stated bound on what is painted at
full detail — or a degraded paint beyond it.

This pins the three behaviours of the fix:

* an over-budget, unselected polygon degrades to an exact **outline only**
  during interactive (on-screen) painting, so the canvas stays responsive;
* the same polygon paints its **exact fill** in an export / offscreen render
  (``widget is None``) and when it is selected, so nothing user-visible and no
  exported artifact loses detail;
* a hostile polygon is **refused at the load seam** (the ingestion trust
  boundary) while every other item in the plan still loads.
"""

from __future__ import annotations

import json
import tempfile
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

# A red fill, opaque, far from both the white background and any pen colour.
_FILL = QColor(200, 40, 40)
_BACKGROUND = QColor(255, 255, 255)


def _subdivided_square(vertices: int, side: float = 600.0) -> QPolygonF:
    """A solid square whose outline holds exactly ``vertices`` points.

    Subdividing each edge gives a polygon with an unambiguous interior — so a
    pixel at the centre is filled iff the item actually painted its fill — while
    its vertex count can be set freely above the paint bound.
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


def _styled_polygon(vertices: int) -> PolygonItem:
    item = PolygonItem(
        vertices=_subdivided_square(vertices),
        object_type=ObjectType.LAWN,
    )
    item.setBrush(_FILL)
    return item


def _interactive_centre_pixel(item: PolygonItem) -> QColor:
    """Paint ``item`` as the on-screen viewport would and read its centre."""
    return _paint_centre_pixel(item, widget=QWidget())


def _offscreen_centre_pixel(item: PolygonItem) -> QColor:
    """Paint ``item`` as an export / offscreen render would and read its centre."""
    return _paint_centre_pixel(item, widget=None)


def _paint_centre_pixel(item: PolygonItem, widget: QWidget | None) -> QColor:
    image = QImage(600, 600, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(_BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        item.paint(painter, QStyleOptionGraphicsItem(), widget)
    finally:
        painter.end()
    return QColor(image.pixel(300, 300))


@pytest.fixture()
def _qt(qtbot: object) -> object:  # noqa: ARG001 — ensures a QApplication exists
    return qtbot


class TestDegradedInteractivePaint:
    def test_over_budget_polygon_paints_no_fill_on_screen(self, _qt: object) -> None:
        item = _styled_polygon(MAX_FULL_DETAIL_VERTICES + 1)
        assert _interactive_centre_pixel(item) == _BACKGROUND

    @pytest.mark.parametrize("vertices", [8, 128, MAX_FULL_DETAIL_VERTICES])
    def test_at_or_below_budget_polygon_paints_its_fill(
        self, _qt: object, vertices: int
    ) -> None:
        item = _styled_polygon(vertices)
        assert _interactive_centre_pixel(item) == _FILL


class TestFullDetailIsNeverLost:
    def test_export_paints_the_exact_fill(self, _qt: object) -> None:
        item = _styled_polygon(MAX_FULL_DETAIL_VERTICES + 1)
        assert _offscreen_centre_pixel(item) == _FILL

    def test_selected_polygon_paints_the_exact_fill(self, _qt: object) -> None:
        item = _styled_polygon(MAX_FULL_DETAIL_VERTICES + 1)
        item.setSelected(True)
        assert _interactive_centre_pixel(item) == _FILL


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


def test_the_load_ceiling_is_generous() -> None:
    """The ceiling must not refuse any legible garden outline (issue #472)."""
    assert MAX_POLYGON_VERTICES >= 10_000
    assert MAX_FULL_DETAIL_VERTICES < MAX_POLYGON_VERTICES
