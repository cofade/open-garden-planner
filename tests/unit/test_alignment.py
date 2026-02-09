"""Tests for the alignment and distribution module."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.alignment import (
    AlignMode,
    DistributeMode,
    align_items,
    distribute_items,
)


class TestAlignItems:
    """Tests for the align_items function."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene so items have valid bounding rects."""
        return QGraphicsScene()

    def _make_rect(
        self, scene: QGraphicsScene, x: float, y: float, w: float, h: float
    ) -> QGraphicsRectItem:
        """Create a rect item at the given position and add to scene."""
        item = QGraphicsRectItem(0, 0, w, h)
        item.setPos(x, y)
        scene.addItem(item)
        return item

    def test_needs_at_least_2_items(self, scene) -> None:
        """Test that align returns empty for less than 2 items."""
        item = self._make_rect(scene, 0, 0, 50, 50)
        result = align_items([item], AlignMode.LEFT)
        assert result == []

    def test_align_left(self, scene) -> None:
        """Test aligning items to the left edge."""
        item1 = self._make_rect(scene, 100, 0, 50, 50)
        item2 = self._make_rect(scene, 200, 0, 50, 50)
        item3 = self._make_rect(scene, 50, 0, 50, 50)

        result = align_items([item1, item2, item3], AlignMode.LEFT)

        # All items should align to x=50 (leftmost edge)
        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].x() - (-50)) < 0.01  # 100 -> 50
        assert abs(delta_map[id(item2)].x() - (-150)) < 0.01  # 200 -> 50
        assert abs(delta_map[id(item3)].x()) < 0.01  # Already at 50

    def test_align_right(self, scene) -> None:
        """Test aligning items to the right edge."""
        item1 = self._make_rect(scene, 100, 0, 50, 50)  # Right edge at 150
        item2 = self._make_rect(scene, 200, 0, 50, 50)  # Right edge at 250
        item3 = self._make_rect(scene, 50, 0, 50, 50)   # Right edge at 100

        result = align_items([item1, item2, item3], AlignMode.RIGHT)

        # All items should align to right edge at 250
        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].x() - 100) < 0.01  # 150 -> 250
        assert abs(delta_map[id(item2)].x()) < 0.01  # Already at 250
        assert abs(delta_map[id(item3)].x() - 150) < 0.01  # 100 -> 250

    def test_align_top(self, scene) -> None:
        """Test aligning items to the top edge."""
        item1 = self._make_rect(scene, 0, 100, 50, 50)
        item2 = self._make_rect(scene, 0, 200, 50, 50)
        item3 = self._make_rect(scene, 0, 50, 50, 50)

        result = align_items([item1, item2, item3], AlignMode.TOP)

        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].y() - (-50)) < 0.01
        assert abs(delta_map[id(item2)].y() - (-150)) < 0.01
        assert abs(delta_map[id(item3)].y()) < 0.01

    def test_align_bottom(self, scene) -> None:
        """Test aligning items to the bottom edge."""
        item1 = self._make_rect(scene, 0, 100, 50, 50)  # Bottom at 150
        item2 = self._make_rect(scene, 0, 200, 50, 50)  # Bottom at 250
        item3 = self._make_rect(scene, 0, 50, 50, 50)   # Bottom at 100

        result = align_items([item1, item2, item3], AlignMode.BOTTOM)

        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].y() - 100) < 0.01
        assert abs(delta_map[id(item2)].y()) < 0.01
        assert abs(delta_map[id(item3)].y() - 150) < 0.01

    def test_align_center_horizontal(self, scene) -> None:
        """Test aligning items to horizontal center."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 200, 0, 50, 50)   # Center at 225
        # Bounding box: left=0, right=250. Center at 125.

        result = align_items([item1, item2], AlignMode.CENTER_H)

        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].x() - 100) < 0.01  # 25 -> 125
        assert abs(delta_map[id(item2)].x() - (-100)) < 0.01  # 225 -> 125

    def test_align_center_vertical(self, scene) -> None:
        """Test aligning items to vertical center."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 0, 200, 50, 50)   # Center at 225
        # Bounding box: top=0, bottom=250. Center at 125.

        result = align_items([item1, item2], AlignMode.CENTER_V)

        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].y() - 100) < 0.01  # 25 -> 125
        assert abs(delta_map[id(item2)].y() - (-100)) < 0.01  # 225 -> 125

    def test_align_no_movement_needed(self, scene) -> None:
        """Test align when items are already aligned."""
        item1 = self._make_rect(scene, 100, 0, 50, 50)
        item2 = self._make_rect(scene, 100, 100, 50, 50)

        result = align_items([item1, item2], AlignMode.LEFT)

        # Both already have left edge at 100
        for _, delta in result:
            assert abs(delta.x()) < 0.01
            assert abs(delta.y()) < 0.01


class TestDistributeItems:
    """Tests for the distribute_items function."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene so items have valid bounding rects."""
        return QGraphicsScene()

    def _make_rect(
        self, scene: QGraphicsScene, x: float, y: float, w: float, h: float
    ) -> QGraphicsRectItem:
        """Create a rect item at the given position and add to scene."""
        item = QGraphicsRectItem(0, 0, w, h)
        item.setPos(x, y)
        scene.addItem(item)
        return item

    def test_needs_at_least_3_items(self, scene) -> None:
        """Test that distribute returns empty for less than 3 items."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)
        item2 = self._make_rect(scene, 100, 0, 50, 50)
        result = distribute_items([item1, item2], DistributeMode.HORIZONTAL)
        assert result == []

    def test_distribute_horizontal(self, scene) -> None:
        """Test horizontal distribution of 3 items."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 50, 0, 50, 50)    # Center at 75
        item3 = self._make_rect(scene, 200, 0, 50, 50)   # Center at 225

        result = distribute_items([item1, item2, item3], DistributeMode.HORIZONTAL)

        # After sorting by center: item1(25), item2(75), item3(225)
        # Equal spacing: first=25, last=225, step=100
        # item2 target center = 125, delta = 125 - 75 = 50
        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].x()) < 0.01  # First stays
        assert abs(delta_map[id(item2)].x() - 50) < 0.01  # 75 -> 125
        assert abs(delta_map[id(item3)].x()) < 0.01  # Last stays

    def test_distribute_vertical(self, scene) -> None:
        """Test vertical distribution of 3 items."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 0, 50, 50, 50)    # Center at 75
        item3 = self._make_rect(scene, 0, 200, 50, 50)   # Center at 225

        result = distribute_items([item1, item2, item3], DistributeMode.VERTICAL)

        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].y()) < 0.01  # First stays
        assert abs(delta_map[id(item2)].y() - 50) < 0.01  # 75 -> 125
        assert abs(delta_map[id(item3)].y()) < 0.01  # Last stays

    def test_distribute_already_even(self, scene) -> None:
        """Test distribute when items are already evenly spaced."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 100, 0, 50, 50)   # Center at 125
        item3 = self._make_rect(scene, 200, 0, 50, 50)   # Center at 225

        result = distribute_items([item1, item2, item3], DistributeMode.HORIZONTAL)

        # Already equally spaced (step=100), no movement needed
        for _, delta in result:
            assert abs(delta.x()) < 0.01
            assert abs(delta.y()) < 0.01

    def test_distribute_4_items(self, scene) -> None:
        """Test distribution of 4 items."""
        item1 = self._make_rect(scene, 0, 0, 50, 50)     # Center at 25
        item2 = self._make_rect(scene, 50, 0, 50, 50)    # Center at 75
        item3 = self._make_rect(scene, 100, 0, 50, 50)   # Center at 125
        item4 = self._make_rect(scene, 300, 0, 50, 50)   # Center at 325

        result = distribute_items(
            [item1, item2, item3, item4], DistributeMode.HORIZONTAL
        )

        # Sorted: item1(25), item2(75), item3(125), item4(325)
        # Step = (325 - 25) / 3 = 100
        # Targets: 25, 125, 225, 325
        delta_map = {id(item): delta for item, delta in result}
        assert abs(delta_map[id(item1)].x()) < 0.01      # 25 -> 25 (stays)
        assert abs(delta_map[id(item2)].x() - 50) < 0.01  # 75 -> 125
        assert abs(delta_map[id(item3)].x() - 100) < 0.01  # 125 -> 225
        assert abs(delta_map[id(item4)].x()) < 0.01      # 325 -> 325 (stays)


class TestAlignItemsCommand:
    """Tests for the AlignItemsCommand class."""

    def test_execute_moves_items(self, qtbot) -> None:
        """Test that execute moves each item by its delta."""
        from open_garden_planner.core.commands import AlignItemsCommand

        item1 = QGraphicsRectItem(0, 0, 50, 50)
        item1.setPos(0, 0)
        item2 = QGraphicsRectItem(0, 0, 50, 50)
        item2.setPos(100, 100)

        deltas = [(item1, QPointF(10, 0)), (item2, QPointF(-20, 0))]
        command = AlignItemsCommand(deltas, "Align left")
        command.execute()

        assert abs(item1.pos().x() - 10) < 0.01
        assert abs(item2.pos().x() - 80) < 0.01

    def test_undo_reverses_movement(self, qtbot) -> None:
        """Test that undo reverses each item's movement."""
        from open_garden_planner.core.commands import AlignItemsCommand

        item1 = QGraphicsRectItem(0, 0, 50, 50)
        item1.setPos(0, 0)
        item2 = QGraphicsRectItem(0, 0, 50, 50)
        item2.setPos(100, 100)

        deltas = [(item1, QPointF(10, 0)), (item2, QPointF(-20, 0))]
        command = AlignItemsCommand(deltas, "Align left")
        command.execute()
        command.undo()

        assert abs(item1.pos().x()) < 0.01
        assert abs(item2.pos().x() - 100) < 0.01

    def test_description(self, qtbot) -> None:
        """Test the description property."""
        from open_garden_planner.core.commands import AlignItemsCommand

        item = QGraphicsRectItem(0, 0, 50, 50)
        command = AlignItemsCommand([(item, QPointF(0, 0))], "Align left")
        assert command.description == "Align left"
