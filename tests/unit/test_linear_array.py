"""Unit tests for LinearArrayCommand and create_linear_array (US-7.14)."""

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import LinearArrayCommand, CommandManager
from open_garden_planner.ui.canvas.items import RectangleItem


class TestLinearArrayCommand:
    """Tests for LinearArrayCommand undo/redo behavior."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        return QGraphicsScene()

    @pytest.fixture
    def manager(self, qtbot) -> CommandManager:
        return CommandManager()

    def test_execute_adds_items(self, scene, manager, qtbot) -> None:
        """Items are added to scene on execute."""
        item1 = QGraphicsRectItem(0, 0, 50, 50)
        item2 = QGraphicsRectItem(100, 0, 50, 50)
        scene.addItem(item1)

        cmd = LinearArrayCommand(scene, [item2])
        manager.execute(cmd)

        assert item2.scene() is scene
        assert len(scene.items()) == 2

    def test_undo_removes_items(self, scene, manager, qtbot) -> None:
        """Items are removed from scene on undo."""
        item1 = QGraphicsRectItem(0, 0, 50, 50)
        item2 = QGraphicsRectItem(100, 0, 50, 50)
        scene.addItem(item1)

        cmd = LinearArrayCommand(scene, [item2])
        manager.execute(cmd)
        manager.undo()

        assert item2.scene() is None
        assert len(scene.items()) == 1

    def test_redo_restores_items(self, scene, manager, qtbot) -> None:
        """Items are re-added on redo after undo."""
        item1 = QGraphicsRectItem(0, 0, 50, 50)
        item2 = QGraphicsRectItem(100, 0, 50, 50)
        scene.addItem(item1)

        cmd = LinearArrayCommand(scene, [item2])
        manager.execute(cmd)
        manager.undo()
        manager.redo()

        assert item2.scene() is scene
        assert len(scene.items()) == 2

    def test_description_includes_count(self, scene, qtbot) -> None:
        """Command description includes total item count."""
        items = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(3)]
        cmd = LinearArrayCommand(scene, items)
        # 3 new items + 1 original = 4
        assert "4" in cmd.description

    def test_single_undo_removes_all_copies(self, scene, manager, qtbot) -> None:
        """Single undo removes all copies (atomic operation)."""
        source = QGraphicsRectItem(0, 0, 50, 50)
        scene.addItem(source)
        copies = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(1, 4)]

        cmd = LinearArrayCommand(scene, copies)
        manager.execute(cmd)
        assert len(scene.items()) == 4

        manager.undo()
        assert len(scene.items()) == 1


class TestLinearArrayPositions:
    """Test that copies are placed at correct positions."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        return QGraphicsScene()

    def test_horizontal_offset(self, scene, qtbot) -> None:
        """Copies at 0° are spaced horizontally."""
        source = RectangleItem(0.0, 0.0, 50.0, 50.0)
        scene.addItem(source)

        spacing = 200.0
        angle_rad = math.radians(0.0)
        dx = spacing * math.cos(angle_rad)
        dy = spacing * math.sin(angle_rad)

        copy = RectangleItem(dx, dy, 50.0, 50.0)
        cmd = LinearArrayCommand(scene, [copy])
        cmd.execute()

        items = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert len(items) == 2

        xs = sorted(i.pos().x() + i.rect().x() for i in items)
        assert abs(xs[1] - xs[0] - spacing) < 0.1

    def test_vertical_offset(self, scene, qtbot) -> None:
        """Copies at 90° are spaced vertically (downward in screen space)."""
        source = RectangleItem(0.0, 0.0, 50.0, 50.0)
        scene.addItem(source)

        spacing = 150.0
        angle_rad = math.radians(90.0)
        dx = spacing * math.cos(angle_rad)
        dy = spacing * math.sin(angle_rad)

        copy = RectangleItem(dx, dy, 50.0, 50.0)
        cmd = LinearArrayCommand(scene, [copy])
        cmd.execute()

        items = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert len(items) == 2

        ys = sorted(i.pos().y() + i.rect().y() for i in items)
        assert abs(ys[1] - ys[0] - spacing) < 0.1
