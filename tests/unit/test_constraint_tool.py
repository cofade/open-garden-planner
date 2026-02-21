"""Tests for the constraint tool and constraint commands."""

from uuid import uuid4

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.core.commands import (
    AddConstraintCommand,
    EditConstraintDistanceCommand,
    RemoveConstraintCommand,
)
from open_garden_planner.core.constraints import AnchorRef, ConstraintGraph
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import ConstraintTool, ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


# --- Command tests ---


class TestAddConstraintCommand:
    """Tests for AddConstraintCommand."""

    def test_execute_adds_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        cmd = AddConstraintCommand(graph, ref_a, ref_b, 150.0)

        cmd.execute()

        assert len(graph.constraints) == 1
        c = list(graph.constraints.values())[0]
        assert c.target_distance == 150.0

    def test_undo_removes_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        cmd = AddConstraintCommand(graph, ref_a, ref_b, 150.0)

        cmd.execute()
        assert len(graph.constraints) == 1

        cmd.undo()
        assert len(graph.constraints) == 0

    def test_redo_restores_same_constraint_id(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        cmd = AddConstraintCommand(graph, ref_a, ref_b, 100.0)

        cmd.execute()
        cid = list(graph.constraints.keys())[0]

        cmd.undo()
        cmd.execute()

        assert len(graph.constraints) == 1
        assert cid in graph.constraints

    def test_description(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        cmd = AddConstraintCommand(graph, ref_a, ref_b, 100.0)
        assert cmd.description == "Add constraint"


class TestRemoveConstraintCommand:
    """Tests for RemoveConstraintCommand."""

    def test_execute_removes_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        constraint = graph.add_constraint(ref_a, ref_b, 200.0)

        cmd = RemoveConstraintCommand(graph, constraint)
        cmd.execute()

        assert len(graph.constraints) == 0

    def test_undo_restores_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        constraint = graph.add_constraint(ref_a, ref_b, 200.0)
        cid = constraint.constraint_id

        cmd = RemoveConstraintCommand(graph, constraint)
        cmd.execute()
        assert len(graph.constraints) == 0

        cmd.undo()
        assert len(graph.constraints) == 1
        assert cid in graph.constraints

    def test_description(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        constraint = graph.add_constraint(ref_a, ref_b, 100.0)
        cmd = RemoveConstraintCommand(graph, constraint)
        assert cmd.description == "Remove constraint"


class TestEditConstraintDistanceCommand:
    """Tests for EditConstraintDistanceCommand."""

    def test_execute_changes_distance(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        constraint = graph.add_constraint(ref_a, ref_b, 100.0)

        cmd = EditConstraintDistanceCommand(
            graph, constraint.constraint_id, 100.0, 250.0
        )
        cmd.execute()

        assert constraint.target_distance == 250.0

    def test_undo_restores_distance(self, qtbot) -> None:
        graph = ConstraintGraph()
        ref_a = AnchorRef(uuid4(), AnchorType.CENTER)
        ref_b = AnchorRef(uuid4(), AnchorType.CENTER)
        constraint = graph.add_constraint(ref_a, ref_b, 100.0)

        cmd = EditConstraintDistanceCommand(
            graph, constraint.constraint_id, 100.0, 250.0
        )
        cmd.execute()
        assert constraint.target_distance == 250.0

        cmd.undo()
        assert constraint.target_distance == 100.0

    def test_missing_constraint_no_crash(self, qtbot) -> None:
        graph = ConstraintGraph()
        cmd = EditConstraintDistanceCommand(graph, uuid4(), 100.0, 200.0)
        cmd.execute()  # Should not crash
        cmd.undo()  # Should not crash

    def test_description(self, qtbot) -> None:
        graph = ConstraintGraph()
        cmd = EditConstraintDistanceCommand(graph, uuid4(), 100.0, 200.0)
        assert cmd.description == "Edit constraint distance"


# --- Constraint tool tests ---


@pytest.fixture
def constraint_tool(qtbot):
    """Create a constraint tool with scene and view."""
    scene = CanvasScene(1000, 1000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    tool = ConstraintTool(view)
    return tool, view, scene


class TestConstraintTool:
    """Tests for ConstraintTool class."""

    def test_tool_type(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        assert tool.tool_type == ToolType.CONSTRAINT

    def test_display_name(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        assert tool.display_name == "Distance Constraint"

    def test_shortcut(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        assert tool.shortcut == "K"

    def test_cursor(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        assert tool.cursor.shape() == Qt.CursorShape.CrossCursor

    def test_initial_state(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        assert tool._anchor_a is None
        assert tool._current_hover is None
        assert tool._graphics_items == []

    def test_activate_resets_state(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        tool.activate()
        assert tool._anchor_a is None
        assert tool._graphics_items == []

    def test_deactivate_resets_state(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        tool.activate()
        tool.deactivate()
        assert tool._anchor_a is None
        assert tool._graphics_items == []

    def test_escape_cancels(self, qtbot, constraint_tool) -> None:
        """Pressing Escape should reset the tool state."""
        from PyQt6.QtGui import QKeyEvent

        tool, view, scene = constraint_tool
        tool.activate()

        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        result = tool.key_press(event)
        assert result is True
        assert tool._anchor_a is None

    def test_cancel_resets(self, qtbot, constraint_tool) -> None:
        tool, view, scene = constraint_tool
        tool.cancel()
        assert tool._anchor_a is None

    def test_mouse_release_not_handled(self, qtbot, constraint_tool) -> None:
        from PyQt6.QtGui import QMouseEvent

        tool, view, scene = constraint_tool
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert tool.mouse_release(event, QPointF(0, 0)) is False
