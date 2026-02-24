"""Unit tests for GridArrayCommand (US-7.15)."""

import pytest
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import CommandManager, GridArrayCommand
from open_garden_planner.ui.canvas.items import RectangleItem


class TestGridArrayCommand:
    """Tests for GridArrayCommand undo/redo behavior."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        return QGraphicsScene()

    @pytest.fixture
    def manager(self, qtbot) -> CommandManager:
        return CommandManager()

    def test_execute_adds_items(self, scene, manager, qtbot) -> None:
        """Items are added to scene on execute."""
        source = QGraphicsRectItem(0, 0, 50, 50)
        scene.addItem(source)
        copies = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(1, 4)]

        cmd = GridArrayCommand(scene, copies)
        manager.execute(cmd)

        assert all(c.scene() is scene for c in copies)
        assert len(scene.items()) == 4

    def test_undo_removes_items(self, scene, manager, qtbot) -> None:
        """Items are removed from scene on undo."""
        source = QGraphicsRectItem(0, 0, 50, 50)
        scene.addItem(source)
        copies = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(1, 4)]

        cmd = GridArrayCommand(scene, copies)
        manager.execute(cmd)
        manager.undo()

        assert all(c.scene() is None for c in copies)
        assert len(scene.items()) == 1

    def test_redo_restores_items(self, scene, manager, qtbot) -> None:
        """Items are re-added on redo after undo."""
        source = QGraphicsRectItem(0, 0, 50, 50)
        scene.addItem(source)
        copies = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(1, 4)]

        cmd = GridArrayCommand(scene, copies)
        manager.execute(cmd)
        manager.undo()
        manager.redo()

        assert all(c.scene() is scene for c in copies)
        assert len(scene.items()) == 4

    def test_description_includes_count(self, scene, qtbot) -> None:
        """Command description includes total item count."""
        copies = [QGraphicsRectItem(i * 100, 0, 50, 50) for i in range(8)]
        cmd = GridArrayCommand(scene, copies)
        # 8 copies + 1 original = 9
        assert "9" in cmd.description

    def test_single_undo_removes_all_copies(self, scene, manager, qtbot) -> None:
        """Single undo removes all copies at once (atomic operation)."""
        source = QGraphicsRectItem(0, 0, 50, 50)
        scene.addItem(source)
        # 3×3 grid minus original = 8 copies
        copies = [QGraphicsRectItem((i % 3) * 100, (i // 3) * 100, 50, 50) for i in range(1, 9)]

        cmd = GridArrayCommand(scene, copies)
        manager.execute(cmd)
        assert len(scene.items()) == 9

        manager.undo()
        assert len(scene.items()) == 1


class TestGridArrayPositions:
    """Test that grid copies are placed at correct positions."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        return QGraphicsScene()

    def test_3x3_grid_item_count(self, scene, qtbot) -> None:
        """3×3 grid creates 9 items total (1 source + 8 copies)."""
        source = RectangleItem(0.0, 0.0, 50.0, 50.0)
        scene.addItem(source)

        rows, cols = 3, 3
        col_spacing, row_spacing = 200.0, 150.0

        copies = []
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue
                # col → +x; row → -y (canvas Y-flip)
                copies.append(RectangleItem(c * col_spacing, -r * row_spacing, 50.0, 50.0))

        cmd = GridArrayCommand(scene, copies)
        cmd.execute()

        items = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert len(items) == rows * cols

    def test_2x1_grid_horizontal_spacing(self, scene, qtbot) -> None:
        """2×1 grid: two items spaced horizontally by col_spacing."""
        source = RectangleItem(0.0, 0.0, 50.0, 50.0)
        scene.addItem(source)

        col_spacing = 200.0
        copy = RectangleItem(col_spacing, 0.0, 50.0, 50.0)
        cmd = GridArrayCommand(scene, [copy])
        cmd.execute()

        items = sorted(
            [i for i in scene.items() if isinstance(i, RectangleItem)],
            key=lambda i: i.pos().x() + i.rect().x(),
        )
        assert len(items) == 2
        gap = (items[1].pos().x() + items[1].rect().x()) - (items[0].pos().x() + items[0].rect().x())
        assert abs(gap - col_spacing) < 0.1

    def test_1x2_grid_vertical_spacing(self, scene, qtbot) -> None:
        """1×2 grid: two items spaced vertically (downward) by row_spacing."""
        source = RectangleItem(0.0, 0.0, 50.0, 50.0)
        scene.addItem(source)

        row_spacing = 150.0
        # rows go down in screen = negative scene Y
        copy = RectangleItem(0.0, -row_spacing, 50.0, 50.0)
        cmd = GridArrayCommand(scene, [copy])
        cmd.execute()

        items = sorted(
            [i for i in scene.items() if isinstance(i, RectangleItem)],
            key=lambda i: i.pos().y() + i.rect().y(),
        )
        assert len(items) == 2
        gap = abs(
            (items[1].pos().y() + items[1].rect().y()) - (items[0].pos().y() + items[0].rect().y())
        )
        assert abs(gap - row_spacing) < 0.1
