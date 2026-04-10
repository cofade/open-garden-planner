"""Unit tests for array along path (US-11.13)."""

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import ArrayAlongPathCommand, CommandManager
from open_garden_planner.core.path_sampling import sample_points_along_path


class TestSamplePointsAlongPath:
    """Tests for path sampling logic."""

    @staticmethod
    def _straight_path(x1: float, y1: float, x2: float, y2: float) -> QPainterPath:
        """Create a simple straight-line path."""
        p = QPainterPath()
        p.moveTo(QPointF(x1, y1))
        p.lineTo(QPointF(x2, y2))
        return p

    def test_straight_line_even_spacing(self, qtbot) -> None:  # noqa: ARG002
        path = self._straight_path(0, 0, 200, 0)
        points = sample_points_along_path(path, 5)
        assert len(points) == 5
        # First and last should be at path endpoints
        assert abs(points[0][0].x() - 0.0) < 1.0
        assert abs(points[-1][0].x() - 200.0) < 1.0
        # Spacing should be ~50 cm
        for i in range(1, len(points)):
            dx = points[i][0].x() - points[i - 1][0].x()
            assert abs(dx - 50.0) < 1.0

    def test_start_end_offsets(self, qtbot) -> None:  # noqa: ARG002
        path = self._straight_path(0, 0, 100, 0)
        points = sample_points_along_path(path, 3, start_pct=0.2, end_pct=0.8)
        assert len(points) == 3
        # First point at 20%, last at 80%
        assert abs(points[0][0].x() - 20.0) < 1.0
        assert abs(points[-1][0].x() - 80.0) < 1.0

    def test_tangent_angles_horizontal(self, qtbot) -> None:  # noqa: ARG002
        path = self._straight_path(0, 0, 100, 0)
        points = sample_points_along_path(path, 3, follow_tangent=True)
        # Horizontal line: Qt reports angle as 0 degrees
        for _, angle in points:
            assert abs(angle) < 1.0 or abs(angle - 360.0) < 1.0

    def test_no_tangent_returns_zero(self, qtbot) -> None:  # noqa: ARG002
        path = self._straight_path(0, 0, 100, 0)
        points = sample_points_along_path(path, 3, follow_tangent=False)
        for _, angle in points:
            assert angle == 0.0

    def test_single_count(self, qtbot) -> None:  # noqa: ARG002
        path = self._straight_path(0, 0, 100, 0)
        points = sample_points_along_path(path, 1)
        assert len(points) == 1
        # Single point should be at midpoint
        assert abs(points[0][0].x() - 50.0) < 1.0

    def test_empty_path(self, qtbot) -> None:  # noqa: ARG002
        path = QPainterPath()
        points = sample_points_along_path(path, 5)
        assert len(points) == 0

    def test_right_angle_path(self, qtbot) -> None:  # noqa: ARG002
        path = QPainterPath()
        path.moveTo(QPointF(0, 0))
        path.lineTo(QPointF(100, 0))
        path.lineTo(QPointF(100, 100))
        points = sample_points_along_path(path, 3)
        assert len(points) == 3
        # First at start, last at end
        assert abs(points[0][0].x() - 0.0) < 1.0
        assert abs(points[0][0].y() - 0.0) < 1.0
        assert abs(points[-1][0].x() - 100.0) < 1.0
        assert abs(points[-1][0].y() - 100.0) < 1.0


class TestArrayAlongPathCommand:
    """Tests for ArrayAlongPathCommand undo/redo."""

    @pytest.fixture()
    def scene(self, qtbot) -> QGraphicsScene:  # noqa: ARG002
        return QGraphicsScene()

    @pytest.fixture()
    def manager(self, qtbot) -> CommandManager:  # noqa: ARG002
        return CommandManager()

    def test_execute_adds_items(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        items = [QGraphicsRectItem(i * 50, 0, 30, 30) for i in range(3)]
        cmd = ArrayAlongPathCommand(scene, items)
        manager.execute(cmd)
        for item in items:
            assert item.scene() is scene

    def test_undo_removes_items(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        items = [QGraphicsRectItem(i * 50, 0, 30, 30) for i in range(3)]
        cmd = ArrayAlongPathCommand(scene, items)
        manager.execute(cmd)
        manager.undo()
        for item in items:
            assert item.scene() is None

    def test_redo_restores_items(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        items = [QGraphicsRectItem(i * 50, 0, 30, 30) for i in range(3)]
        cmd = ArrayAlongPathCommand(scene, items)
        manager.execute(cmd)
        manager.undo()
        manager.redo()
        for item in items:
            assert item.scene() is scene

    def test_description(self, qtbot) -> None:  # noqa: ARG002
        items = [QGraphicsRectItem(0, 0, 10, 10) for _ in range(5)]
        cmd = ArrayAlongPathCommand(QGraphicsScene(), items)
        assert "5" in cmd.description
