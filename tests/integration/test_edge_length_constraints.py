"""Integration tests for direct edge-length constraints (issue #140)."""

# ruff: noqa: ARG002

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_polygon(view: CanvasView) -> PolygonItem:
    event = _left_click_event()
    view.set_active_tool(ToolType.POLYGON)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(100, 100))
    tool.mouse_press(event, QPointF(300, 100))
    tool.mouse_press(event, QPointF(300, 250))
    tool.mouse_press(event, QPointF(100, 250))
    tool.mouse_double_click(event, QPointF(100, 250))
    polygons = [i for i in view.scene().items() if isinstance(i, PolygonItem)]
    return polygons[0]


class TestEdgeLengthConstraintWorkflow:
    def test_click_edge_creates_edge_length_constraint(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        polygon = _draw_polygon(canvas)
        event = _left_click_event()
        canvas.set_active_tool(ToolType.CONSTRAINT_EDGE_LENGTH)
        tool = canvas.tool_manager.active_tool

        class _AcceptedDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

            def distance_cm(self) -> float:
                return 250.0

        with patch(
            "open_garden_planner.core.tools.constraint_tool.DistanceInputDialog",
            _AcceptedDialog,
        ):
            tool.mouse_press(event, QPointF(200, 100))

        constraints = list(canvas._canvas_scene.constraint_graph.constraints.values())
        assert len(constraints) == 1
        constraint = constraints[0]
        assert constraint.constraint_type == ConstraintType.EDGE_LENGTH
        assert constraint.anchor_a.item_id == polygon.item_id
        assert constraint.anchor_b.item_id == polygon.item_id
        assert constraint.anchor_a.anchor_index != constraint.anchor_b.anchor_index
