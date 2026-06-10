"""End-to-end tests for the Mirror tool (Phase 13 Package B — US-B4).

The tool reflects the current selection across a two-click axis, in either
**Copy** (keep originals) or **Move** (replace originals, preserving identity)
mode. The modal Copy/Move chooser is skipped under the offscreen Qt platform
(see ``MirrorTool._choose_mode_and_apply``); tests set ``tool._copy_mode``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.cad_geometry import reflect_point
from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, TextItem

# A vertical mirror axis at x = 100.
_AXIS_A = QPointF(100, 0)
_AXIS_B = QPointF(100, 200)


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _click(shift: bool = False) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )
    return event


def _activate(canvas: CanvasView, copy: bool) -> object:
    canvas.tool_manager.set_active_tool(ToolType.MIRROR)
    tool = canvas.tool_manager.active_tool
    tool._copy_mode = copy
    return tool


def _drive_axis(
    tool: object, a: QPointF, b: QPointF, shift: bool = False
) -> None:
    tool.mouse_press(_click(), a)  # axis start
    tool.mouse_press(_click(shift=shift), b)  # axis end → applies


def _polygons(canvas: CanvasView) -> list[PolygonItem]:
    return [i for i in canvas.scene().items() if isinstance(i, PolygonItem)]


class TestMirrorCopy:
    def test_copy_adds_reflected_polygon_keeps_original(
        self, canvas: CanvasView
    ) -> None:
        # Interior geometry + axis so the reflection stays comfortably inside
        # the canvas (no edge clamp), letting us assert exact reflected coords.
        verts = [QPointF(200, 200), QPointF(240, 200), QPointF(240, 230)]
        poly = PolygonItem(vertices=list(verts))
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, QPointF(400, 0), QPointF(400, 400))  # vertical axis x=400

        polys = _polygons(canvas)
        assert len(polys) == 2  # original + reflected copy
        # Identify the copy (the one that is not the original object).
        copy = next(p for p in polys if p is not poly)
        got = {
            (round(copy.mapToScene(copy.polygon().at(i)).x(), 4),
             round(copy.mapToScene(copy.polygon().at(i)).y(), 4))
            for i in range(copy.polygon().count())
        }
        ax1, ax2 = QPointF(400, 0), QPointF(400, 400)
        expected = {
            (round(reflect_point(poly.mapToScene(v), ax1, ax2).x(), 4),
             round(reflect_point(poly.mapToScene(v), ax1, ax2).y(), 4))
            for v in [poly.polygon().at(i) for i in range(poly.polygon().count())]
        }
        assert got == expected
        # The copy has a fresh identity.
        assert copy.item_id != poly.item_id

    def test_copy_is_one_undo_step(self, canvas: CanvasView) -> None:
        poly = PolygonItem(vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)])
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, _AXIS_A, _AXIS_B)
        assert len(_polygons(canvas)) == 2
        assert len(canvas.command_manager._undo_stack) == 1

        canvas.command_manager.undo()
        remaining = _polygons(canvas)
        assert len(remaining) == 1
        assert remaining[0] is poly


class TestMirrorMove:
    def test_move_replaces_original_preserving_item_id(
        self, canvas: CanvasView
    ) -> None:
        poly = PolygonItem(vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)])
        canvas.scene().addItem(poly)
        poly.setSelected(True)
        original_id = poly.item_id

        tool = _activate(canvas, copy=False)
        _drive_axis(tool, _AXIS_A, _AXIS_B)

        polys = _polygons(canvas)
        assert len(polys) == 1  # original replaced, not duplicated
        assert polys[0] is not poly
        # Identity preserved so constraints stay bound.
        assert polys[0].item_id == original_id

    def test_move_undo_restores_original(self, canvas: CanvasView) -> None:
        poly = PolygonItem(vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)])
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=False)
        _drive_axis(tool, _AXIS_A, _AXIS_B)
        assert len(canvas.command_manager._undo_stack) == 1

        canvas.command_manager.undo()
        remaining = _polygons(canvas)
        assert len(remaining) == 1
        assert remaining[0] is poly  # exact original object restored


class TestMirrorAxisConstraint:
    def test_shift_snaps_axis_to_45(self, canvas: CanvasView) -> None:
        # Interior geometry + axis at y=300 keeps the reflection on-canvas, so
        # this test isolates the Shift snap from the separate edge-clamp.
        poly = PolygonItem(
            vertices=[QPointF(200, 200), QPointF(240, 200), QPointF(240, 230)]
        )
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=True)
        tool.mouse_press(_click(), QPointF(0, 300))
        # End near 9°; Shift snaps the axis to horizontal (0°) through y = 300.
        tool.mouse_press(_click(shift=True), QPointF(50, 308))
        assert tool._axis_end is None  # state reset after applying

        # Reflecting across y = 300 maps (x, y) -> (x, 600 - y).
        copy = next(p for p in _polygons(canvas) if p is not poly)
        got = {
            (round(copy.mapToScene(copy.polygon().at(i)).x(), 4),
             round(copy.mapToScene(copy.polygon().at(i)).y(), 4))
            for i in range(copy.polygon().count())
        }
        assert got == {(200.0, 400.0), (240.0, 400.0), (240.0, 370.0)}


class TestMirrorCanvasClamp:
    def test_reflection_off_canvas_is_pulled_back(self, canvas: CanvasView) -> None:
        # Polygon near the left edge; mirror across x = 20 sends it to negative x.
        poly = PolygonItem(vertices=[QPointF(40, 50), QPointF(80, 50), QPointF(80, 90)])
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, QPointF(20, 0), QPointF(20, 200))  # vertical axis x=20

        copy = next(p for p in _polygons(canvas) if p is not poly)
        xs = [copy.mapToScene(copy.polygon().at(i)).x() for i in range(3)]
        # Raw reflection would land at x in [-40, 0]; clamp shifts it to x >= 0.
        assert min(xs) >= -1e-6
        # Shape is undistorted: width preserved (40 cm) after the group shift.
        assert max(xs) - min(xs) == pytest.approx(40.0, abs=1e-4)


class TestMirrorUnsupported:
    def test_text_item_is_skipped(self, canvas: CanvasView) -> None:
        text = TextItem(10, 10, content="Bed A")
        canvas.scene().addItem(text)
        text.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, _AXIS_A, _AXIS_B)

        # No mirror performed → nothing on the undo stack, text untouched.
        assert len(canvas.command_manager._undo_stack) == 0
        texts = [i for i in canvas.scene().items() if isinstance(i, TextItem)]
        assert len(texts) == 1

    def test_mixed_selection_mirrors_supported_only(self, canvas: CanvasView) -> None:
        poly = PolygonItem(vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)])
        text = TextItem(10, 10, content="label")
        canvas.scene().addItem(poly)
        canvas.scene().addItem(text)
        poly.setSelected(True)
        text.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, _AXIS_A, _AXIS_B)

        # Polygon mirrored (now 2), text skipped (still 1), one undo step.
        assert len(_polygons(canvas)) == 2
        assert len([i for i in canvas.scene().items() if isinstance(i, TextItem)]) == 1
        assert len(canvas.command_manager._undo_stack) == 1


class TestMirrorConstraintsAndChildren:
    def test_move_keeps_constraint_bound(self, canvas: CanvasView) -> None:
        a = PolygonItem(vertices=[QPointF(0, 0), QPointF(20, 0), QPointF(20, 20)])
        b = PolygonItem(vertices=[QPointF(40, 0), QPointF(60, 0), QPointF(60, 20)])
        canvas.scene().addItem(a)
        canvas.scene().addItem(b)
        graph = canvas.scene().constraint_graph
        graph.add_constraint(
            AnchorRef(item_id=a.item_id, anchor_type=AnchorType.CENTER),
            AnchorRef(item_id=b.item_id, anchor_type=AnchorType.CENTER),
            50.0,
        )
        assert len(graph.constraints) == 1
        a.setSelected(True)
        b.setSelected(True)

        tool = _activate(canvas, copy=False)
        _drive_axis(tool, _AXIS_A, _AXIS_B)

        # Identity preserved → the constraint still resolves to both items.
        assert len(graph.constraints) == 1
        ids = {p.item_id for p in _polygons(canvas)}
        assert {a.item_id, b.item_id} == ids
        assert graph.get_item_constraints(a.item_id)
        assert graph.get_item_constraints(b.item_id)

    def test_copy_relinks_bed_children(self, canvas: CanvasView) -> None:
        bed = PolygonItem(
            vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 40), QPointF(0, 40)],
            object_type=ObjectType.GARDEN_BED,
        )
        plant = CircleItem(20, 20, 5)
        canvas.scene().addItem(bed)
        canvas.scene().addItem(plant)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        bed.setSelected(True)  # only the bed — the child is auto-included
        tool = _activate(canvas, copy=True)
        _drive_axis(tool, _AXIS_A, _AXIS_B)

        beds = [
            p for p in _polygons(canvas) if p.object_type == ObjectType.GARDEN_BED
        ]
        plants = [i for i in canvas.scene().items() if isinstance(i, CircleItem)]
        assert len(beds) == 2 and len(plants) == 2
        bed_copy = next(p for p in beds if p is not bed)
        plant_copy = next(p for p in plants if p is not plant)
        # The copied plant is re-parented onto the copied bed (not the original).
        assert plant_copy.parent_bed_id == bed_copy.item_id
        assert plant_copy.item_id in bed_copy.child_item_ids


class TestMirrorRedo:
    def test_redo_after_undo_restores_copy(self, canvas: CanvasView) -> None:
        poly = PolygonItem(vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)])
        canvas.scene().addItem(poly)
        poly.setSelected(True)

        tool = _activate(canvas, copy=True)
        _drive_axis(tool, _AXIS_A, _AXIS_B)
        assert len(_polygons(canvas)) == 2

        canvas.command_manager.undo()
        assert len(_polygons(canvas)) == 1
        canvas.command_manager.redo()
        assert len(_polygons(canvas)) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
