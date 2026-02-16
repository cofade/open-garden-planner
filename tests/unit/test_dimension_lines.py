"""Tests for dimension line visualization."""

from uuid import uuid4

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.dimension_lines import (
    DimensionLineGroup,
    _point_to_segment_distance,
)


class TestPointToSegmentDistance:
    """Tests for the point-to-segment distance helper."""

    def test_point_on_segment(self, qtbot) -> None:
        dist = _point_to_segment_distance(
            QPointF(5, 0), QPointF(0, 0), QPointF(10, 0)
        )
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_point_perpendicular(self, qtbot) -> None:
        dist = _point_to_segment_distance(
            QPointF(5, 3), QPointF(0, 0), QPointF(10, 0)
        )
        assert dist == pytest.approx(3.0, abs=1e-6)

    def test_point_beyond_endpoint_a(self, qtbot) -> None:
        dist = _point_to_segment_distance(
            QPointF(-3, 0), QPointF(0, 0), QPointF(10, 0)
        )
        assert dist == pytest.approx(3.0, abs=1e-6)

    def test_point_beyond_endpoint_b(self, qtbot) -> None:
        dist = _point_to_segment_distance(
            QPointF(13, 0), QPointF(0, 0), QPointF(10, 0)
        )
        assert dist == pytest.approx(3.0, abs=1e-6)

    def test_degenerate_segment(self, qtbot) -> None:
        dist = _point_to_segment_distance(
            QPointF(3, 4), QPointF(0, 0), QPointF(0, 0)
        )
        assert dist == pytest.approx(5.0, abs=1e-6)


class TestDimensionLineGroup:
    """Tests for DimensionLineGroup."""

    def test_creation(self, qtbot) -> None:
        cid = uuid4()
        group = DimensionLineGroup(cid)
        assert group.constraint_id == cid
        assert group.items == []

    def test_remove_from_scene(self, qtbot) -> None:
        scene = QGraphicsScene()
        cid = uuid4()
        group = DimensionLineGroup(cid)

        # Add a line item to the group
        from PyQt6.QtCore import QLineF
        from PyQt6.QtGui import QPen

        line = scene.addLine(QLineF(0, 0, 100, 100), QPen())
        group.items.append(line)
        assert len(scene.items()) == 1

        group.remove_from_scene(scene)
        assert len(scene.items()) == 0
        assert group.items == []


class TestDimensionLineManager:
    """Tests for DimensionLineManager."""

    def test_initial_state(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        mgr = scene.dimension_line_manager
        assert mgr.visible is True

    def test_set_visible(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        mgr = scene.dimension_line_manager
        mgr.set_visible(False)
        assert mgr.visible is False
        mgr.set_visible(True)
        assert mgr.visible is True

    def test_update_all_with_no_constraints(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        mgr = scene.dimension_line_manager
        # Should not raise
        mgr.update_all()
        assert len(mgr._groups) == 0

    def test_update_all_creates_groups_for_constraints(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)

        # Add two rectangle items to the scene
        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        # Add a constraint between them
        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        scene.constraint_graph.add_constraint(ref_a, ref_b, 300.0)

        mgr = scene.dimension_line_manager
        mgr.update_all()

        # Should have created a group with graphics items
        assert len(mgr._groups) == 1
        group = list(mgr._groups.values())[0]
        # Witness lines (2) + dimension line (1) + arrowheads (2) + text (1) = 6
        assert len(group.items) == 6

    def test_clear_removes_all(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)

        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        scene.constraint_graph.add_constraint(ref_a, ref_b, 300.0)

        mgr = scene.dimension_line_manager
        mgr.update_all()
        assert len(mgr._groups) == 1

        mgr.clear()
        assert len(mgr._groups) == 0

    def test_stale_constraints_removed(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)

        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        c = scene.constraint_graph.add_constraint(ref_a, ref_b, 300.0)

        mgr = scene.dimension_line_manager
        mgr.update_all()
        assert len(mgr._groups) == 1

        # Remove the constraint
        scene.constraint_graph.remove_constraint(c.constraint_id)
        mgr.update_all()
        assert len(mgr._groups) == 0

    def test_violated_constraint_uses_different_color(self, qtbot) -> None:
        """Verify that violated constraints produce visuals (color check is visual)."""
        scene = CanvasScene(1000, 1000)

        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        # Set target distance far from actual (~300cm actual, target 100cm)
        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        scene.constraint_graph.add_constraint(ref_a, ref_b, 100.0)

        mgr = scene.dimension_line_manager
        mgr.update_all()
        assert len(mgr._groups) == 1

    def test_hidden_constraints_not_drawn(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)

        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        scene.constraint_graph.add_constraint(ref_a, ref_b, 300.0, visible=False)

        mgr = scene.dimension_line_manager
        mgr.update_all()
        # Group should not be created for invisible constraints
        assert len(mgr._groups) == 0

    def test_get_constraint_at(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)

        from open_garden_planner.ui.canvas.items import RectangleItem

        item_a = RectangleItem(0, 0, 100, 100)
        item_b = RectangleItem(300, 0, 100, 100)
        scene.addItem(item_a)
        scene.addItem(item_b)

        ref_a = AnchorRef(item_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(item_b.item_id, AnchorType.CENTER)
        c = scene.constraint_graph.add_constraint(ref_a, ref_b, 300.0)

        mgr = scene.dimension_line_manager
        mgr.update_all()

        # Items at (0,0,100,100) center=(50,50), (300,0,100,100) center=(350,50)
        # Direction (1,0), perpendicular (0,1), offset +15 -> dimension line at y=65
        # Midpoint of dimension line: x=200, y=65
        found = mgr.get_constraint_at(QPointF(200, 65), threshold=20.0)
        assert found == c.constraint_id

    def test_get_constraint_at_no_match(self, qtbot) -> None:
        scene = CanvasScene(1000, 1000)
        mgr = scene.dimension_line_manager

        # No constraints, should return None
        found = mgr.get_constraint_at(QPointF(500, 500))
        assert found is None


class TestCanvasSceneConstraintIntegration:
    """Test CanvasScene constraint visibility methods."""

    def test_constraints_visible_property(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        assert scene.constraints_visible is True

    def test_set_constraints_visible(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        scene.set_constraints_visible(False)
        assert scene.constraints_visible is False
        scene.set_constraints_visible(True)
        assert scene.constraints_visible is True

    def test_update_dimension_lines(self, qtbot) -> None:
        scene = CanvasScene(500, 300)
        # Should not raise
        scene.update_dimension_lines()
