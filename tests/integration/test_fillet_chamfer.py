"""End-to-end tests for Fillet & Chamfer tools (Phase 13 Package B — US-B3).

The two tools share picking + corner-rebuild plumbing.  Fillet samples its
tangent arc into the host item's own vertex list (one object, so the rounded
corner moves/saves with the host); chamfer replaces the corner with one straight
segment.  Neither creates a second scene item.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.cad_geometry import FILLET_ARC_TOLERANCE_CM
from open_garden_planner.core.object_types import ObjectType
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
    def test_fillet_polyline_bakes_the_arc_into_the_host(
        self, canvas: CanvasView
    ) -> None:
        """3-vertex polyline → one polyline whose corner is rounded in place."""
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polylines = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        arcs = [i for i in canvas.scene().items() if isinstance(i, ArcItem)]
        assert len(polylines) == 1
        assert len(arcs) == 0, "the arc must be part of the host, not a second item"
        # The corner is replaced by its two tangent points plus the sampled arc.
        assert len(polylines[0].points) > 4

        # The whole rounded corner travels with the host when it moves: there
        # is only one object to move (owner manual test 2026-10-31).
        tangent = polylines[0].mapToScene(polylines[0].points[1])
        polylines[0].moveBy(120.0, 80.0)
        moved = polylines[0].mapToScene(polylines[0].points[1])
        assert moved.x() == pytest.approx(tangent.x() + 120.0)
        assert moved.y() == pytest.approx(tangent.y() + 80.0)
        assert len([i for i in canvas.scene().items() if isinstance(i, ArcItem)]) == 0

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
        # Nothing changes — the polyline stays 3-vertex and no arc is created.
        assert len(polylines) == 1
        assert len(polylines[0].points) == 3
        assert len(arcs) == 0

    def test_fillet_rectangle_converts_to_polygon(
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
        # Rectangle replaced by a polygon whose corner is rounded in place.
        assert len(rects) == 0
        assert len(polygons) == 1
        assert len(arcs) == 0
        assert polygons[0].polygon().count() > 5
        assert polygons[0].object_type == ObjectType.GENERIC_POLYGON

        # Undo restores the rectangle and clears the polygon.
        canvas.command_manager.undo()
        rects_after = [
            i for i in canvas.scene().items() if isinstance(i, RectangleItem)
        ]
        polygons_after = [
            i for i in canvas.scene().items() if isinstance(i, PolygonItem)
        ]
        assert len(rects_after) == 1
        assert len(polygons_after) == 0

    def test_filleting_a_house_re_derives_its_ridge(self, canvas: CanvasView) -> None:
        """A cut corner changes the outline, so the derived ridge must follow.

        The replacement polygon keeps the house's UUID and metadata, but the
        replacement command had no ridge hook (round-5 review of #690).
        """
        from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
        from open_garden_planner.ui.canvas.roof_ridge_link import (
            build_linked_ridge,
            linked_ridge,
            outline_polygon,
        )

        rect = RectangleItem(100, 100, 300, 200, object_type=ObjectType.HOUSE)
        canvas.scene().addItem(rect)
        ridge = build_linked_ridge(rect, rect.layer_id)
        assert ridge is not None
        canvas.scene().addItem(ridge)
        canonical = [QPointF(p) for p in ridge.points]
        # Make the ridge stale on purpose: the fillet of these corners keeps
        # the same extents, so only an explicit re-derivation can repair it.
        ridge._points = [QPointF(0.0, 0.0), QPointF(1.0, 1.0)]
        ridge._rebuild_path()

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(100, 100))

        rounded = next(
            i for i in canvas.scene().items() if isinstance(i, PolygonItem)
        )
        assert linked_ridge(rounded) is ridge
        polygon = outline_polygon(rounded)
        assert polygon is not None
        p1, p2 = compute_roof_ridge_endpoints(polygon, QPointF(0.0, 0.0))
        assert ridge.points[0] == rounded.mapToScene(p1)
        assert ridge.points[-1] == rounded.mapToScene(p2)

        canvas.command_manager.undo()
        assert [QPointF(p) for p in ridge.points] == canonical
        assert linked_ridge(rect) is ridge

    def test_a_rounded_bed_round_trips(self, canvas: CanvasView, tmp_path) -> None:
        """The baked corner is part of the polygon, so a save keeps it."""
        from open_garden_planner.core.project import ProjectManager

        rect = RectangleItem(0, 0, 200, 100, object_type=ObjectType.RAISED_BED)
        canvas.scene().addItem(rect)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        rounded = next(
            i for i in canvas.scene().items() if isinstance(i, PolygonItem)
        )
        before = [(p.x(), p.y()) for p in rounded.polygon()]
        path = tmp_path / "rounded.ogp"
        ProjectManager().save(canvas.scene(), path)

        loaded_scene = CanvasScene(width_cm=8000, height_cm=6000)
        ProjectManager().load(loaded_scene, path)
        loaded = loaded_scene.find_item_by_id(rounded.item_id)
        assert loaded is not None
        assert loaded.object_type == ObjectType.GARDEN_BED
        after = [(p.x(), p.y()) for p in loaded.polygon()]
        assert len(after) == len(before)
        for (bx, by), (ax, ay) in zip(before, after, strict=True):
            assert ax == pytest.approx(bx, abs=1e-6)
            assert ay == pytest.approx(by, abs=1e-6)
        assert not [
            i for i in loaded_scene.items() if isinstance(i, ArcItem)
        ], "no free-standing arc may be saved or loaded"

    def test_fillet_arc_is_tangent_to_both_edges(
        self, canvas: CanvasView
    ) -> None:
        """Every baked vertex sits on the tangent arc, within the stated tolerance."""
        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        polyline = next(
            i for i in canvas.scene().items() if isinstance(i, PolylineItem)
        )
        # Right-angle corner with r=20 → tangent points at (20,0) and (0,20),
        # arc centre (20,20).
        first = polyline.points[1]
        last = polyline.points[-2]
        assert (round(first.x(), 4), round(first.y(), 4)) == (20.0, 0.0)
        assert (round(last.x(), 4), round(last.y(), 4)) == (0.0, 20.0)

        centre = QPointF(20.0, 20.0)
        arc_points = [first, *polyline.points[2:-2], last]
        for point in arc_points:
            assert math.hypot(
                point.x() - centre.x(), point.y() - centre.y()
            ) == pytest.approx(20.0, abs=1e-6)

        # The sampled polyline's greatest chord deviation honours the contract.
        for start, end in zip(arc_points, arc_points[1:], strict=False):
            chord = math.hypot(end.x() - start.x(), end.y() - start.y())
            sagitta = 20.0 - math.sqrt(max(0.0, 20.0**2 - (chord / 2.0) ** 2))
            assert sagitta <= FILLET_ARC_TOLERANCE_CM + 1e-9

    def test_fillet_host_keeps_its_pen(self, canvas: CanvasView) -> None:
        """The rounded corner is the host's own outline; its pen is unchanged."""
        from PyQt6.QtGui import QColor, QPen

        from open_garden_planner.core.item_look import adopt_pen

        pl = PolylineItem(
            points=[QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)],
        )
        host_pen = QPen(QColor(20, 140, 40), 3.5)
        adopt_pen(pl, host_pen)
        canvas.scene().addItem(pl)

        tool = _activate_fillet(canvas, radius_cm=20.0)
        tool.mouse_press(_left_click_event(), QPointF(0, 0))

        rounded = next(
            i for i in canvas.scene().items() if isinstance(i, PolylineItem)
        )
        assert rounded.pen().color().rgba() == host_pen.color().rgba()
        assert rounded.pen().widthF() == pytest.approx(host_pen.widthF())


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

        # Now click on the internal corner (100, 0) — should fillet in place.
        tool.mouse_press(_left_click_event(), QPointF(100, 0))
        rounded = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
        assert len(rounded) == 1
        assert len(rounded[0].points) > 3
        assert not [
            i for i in canvas.scene().items() if isinstance(i, ArcItem)
        ], "no free-standing arc may be left behind"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
