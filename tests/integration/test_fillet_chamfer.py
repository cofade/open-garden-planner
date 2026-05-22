"""End-to-end tests for Fillet & Chamfer tools (Phase 13 Package B — US-B3).

The two tools share picking + corner-rebuild plumbing but produce different
results: fillet emits an extra ``ArcItem``; chamfer only mutates the host
shape. Each test exercises one tool on one host kind so the cases are easy
to read.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _activate_fillet(canvas: CanvasView, radius_cm: float) -> object:
    """Activate the fillet tool and set its radius without firing QInputDialog."""
    canvas.tool_manager.set_active_tool(ToolType.FILLET)
    tool = canvas.tool_manager.active_tool
    tool._radius = radius_cm  # bypass activation dialog
    return tool


def _activate_chamfer(canvas: CanvasView, distance_cm: float) -> object:
    canvas.tool_manager.set_active_tool(ToolType.CHAMFER)
    tool = canvas.tool_manager.active_tool
    tool._distance = distance_cm
    return tool


# ─────────────────────────────────────────────────────────────────────────
# Fillet
# ─────────────────────────────────────────────────────────────────────────


class TestFilletWorkflow:
    def test_fillet_polyline_replaces_corner_and_adds_arc(
        self, canvas: CanvasView
    ) -> None:
        """3-vertex polyline (right angle) → 4-vertex polyline + 1 arc."""
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        assert len(polylines) == 1
        assert len(arcs) == 1
        # Original 3-vertex polyline is gone; the new one has 4 vertices
        # (corner split into tangent_in/tangent_out).
        assert len(polylines[0].points) == 4

    def test_fillet_polyline_undo_restores_original(
        self, canvas: CanvasView
    ) -> None:
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)
        original_id = id(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))
        canvas.command_manager.undo()

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        assert len(polylines) == 1
        assert id(polylines[0]) == original_id
        assert len(arcs) == 0

    def test_fillet_too_large_radius_is_rejected(
        self, canvas: CanvasView
    ) -> None:
        """Edge length is 10 cm; radius 50 cm needs offset 50 cm — invalid."""
        pl = PolylineItem(
            points=[QPointF(10, 0), QPointF(0, 0), QPointF(0, 10)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=50.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        # Nothing changes — the polyline stays 3-vertex and no arc spawns.
        assert len(polylines) == 1
        assert len(polylines[0].points) == 3
        assert len(arcs) == 0

    def test_fillet_rectangle_converts_to_polygon_with_arc(
        self, canvas: CanvasView
    ) -> None:
        """Rectangles can't store per-corner geometry — fillet converts them."""
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        # Top-left corner sits at (0, 0) in scene coords.
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        rects = [i for i in canvas.scene().items() if isinstance(i, RectangleItem)]
        polygons = [i for i in canvas.scene().items() if isinstance(i, PolygonItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        # Rectangle replaced by a 5-vertex polygon + the fillet arc.
        assert len(rects) == 0
        assert len(polygons) == 1
        assert len(arcs) == 1

        # Undo restores the rectangle and clears the polygon + arc.
        canvas.command_manager.undo()
        rects_after = [
            i for i in canvas.scene().items() if isinstance(i, RectangleItem)
        ]
        polygons_after = [
            i for i in canvas.scene().items() if isinstance(i, PolygonItem)
        ]
        arcs_after = [
            i for i in canvas.scene().items() if isinstance(i, ArcItem)
        ]
        assert len(rects_after) == 1
        assert len(polygons_after) == 0
        assert len(arcs_after) == 0

    def test_fillet_arc_is_tangent_to_both_edges(
        self, canvas: CanvasView
    ) -> None:
        """The generated arc's tangent endpoints sit exactly on the original edges."""
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        arc = arcs[0]
        # Right-angle corner with r=20 → tangent points at (20,0) and (0,20).
        sp = arc.start_point()
        ep = arc.end_point()
        # Either order is fine (depending on winding) — verify the set.
        coord_set = {(round(sp.x(), 4), round(sp.y(), 4)),
                     (round(ep.x(), 4), round(ep.y(), 4))}
        assert (20.0, 0.0) in coord_set
        assert (0.0, 20.0) in coord_set

    def test_fillet_arc_inherits_host_pen(self, canvas: CanvasView) -> None:
        """Manual-test feedback: a fillet arc rendered in default gray over a
        coloured polyline reads as 'chamfer cut + faint gray arc' rather than
        a true rounded corner. The arc must adopt the host's pen colour
        and width."""
        from PyQt6.QtGui import QColor, QPen

        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        host_pen = QPen(QColor(20, 140, 40), 3.5)
        pl.setPen(host_pen)
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        arc = next(
            i for i in canvas.scene().items() if isinstance(i, ArcItem)
        )
        assert arc.stroke_color.rgba() == host_pen.color().rgba()
        assert arc.stroke_width == pytest.approx(host_pen.widthF())


# ─────────────────────────────────────────────────────────────────────────
# Chamfer
# ─────────────────────────────────────────────────────────────────────────


class TestChamferWorkflow:
    def test_chamfer_polyline_replaces_corner(
        self, canvas: CanvasView
    ) -> None:
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_chamfer(canvas, distance_cm=15.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        assert len(polylines) == 1
        assert len(polylines[0].points) == 4
        # Chamfer never adds an arc.
        assert len(arcs) == 0

        # Verify the two new vertices are at the expected positions.
        pts = polylines[0].points
        coords = {(round(p.x(), 4), round(p.y(), 4)) for p in pts}
        assert (15.0, 0.0) in coords
        assert (0.0, 15.0) in coords

    def test_chamfer_undo_restores_original(self, canvas: CanvasView) -> None:
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)
        original_id = id(pl)

        tool = _activate_chamfer(canvas, distance_cm=15.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))
        canvas.command_manager.undo()

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        assert len(polylines) == 1
        assert id(polylines[0]) == original_id

    def test_chamfer_rectangle_converts_to_polygon(
        self, canvas: CanvasView
    ) -> None:
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)

        tool = _activate_chamfer(canvas, distance_cm=15.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        rects = [i for i in canvas.scene().items() if isinstance(i, RectangleItem)]
        polygons = [i for i in canvas.scene().items() if isinstance(i, PolygonItem)]
        assert len(rects) == 0
        assert len(polygons) == 1
        # 4 corners → one becomes two → 5 vertices.
        assert polygons[0].polygon().count() == 5

    def test_chamfer_too_large_distance_is_rejected(
        self, canvas: CanvasView
    ) -> None:
        pl = PolylineItem(
            points=[QPointF(10, 0), QPointF(0, 0), QPointF(0, 10)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_chamfer(canvas, distance_cm=50.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        assert len(polylines) == 1
        assert len(polylines[0].points) == 3


# ─────────────────────────────────────────────────────────────────────────
# Corner picking
# ─────────────────────────────────────────────────────────────────────────


class TestCornerPicking:
    def test_picks_only_internal_polyline_vertices(
        self, canvas: CanvasView
    ) -> None:
        """Polyline endpoints can't be filleted — only internal corners."""
        pl = PolylineItem(
            points=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        # Click on the endpoint (0, 0) — should not find a corner.
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        # No arc, the polyline is unchanged.
        assert len(arcs) == 0
        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        assert len(polylines[0].points) == 3

        # Now click on the internal corner (100, 0) — should fillet.
        tool.mouse_press(_left_click_event(), QPointF(100, 0))
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        assert len(arcs) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
