"""Tests for the object snapping engine."""

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.snapping import ObjectSnapper, SnapResult


class TestSnapResult:
    """Tests for SnapResult dataclass."""

    def test_default_values(self, qtbot) -> None:
        """Test SnapResult defaults."""
        result = SnapResult(snapped_pos=QPointF(0, 0))
        assert not result.snapped_x
        assert not result.snapped_y
        assert result.guides == []


class TestObjectSnapper:
    """Tests for ObjectSnapper class."""

    @pytest.fixture
    def snapper(self, qtbot) -> ObjectSnapper:
        """Create a snapper with default threshold."""
        return ObjectSnapper(threshold=10.0)

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def _make_selectable_rect(
        self, scene: QGraphicsScene, x: float, y: float, w: float, h: float
    ) -> QGraphicsRectItem:
        """Create a selectable rect item and add to scene."""
        item = QGraphicsRectItem(0, 0, w, h)
        item.setPos(x, y)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
        return item

    def test_no_snap_when_no_targets(self, snapper, scene) -> None:
        """Test that snapper returns zero offset when there are no targets."""
        dragged = QRectF(100, 100, 50, 50)
        result = snapper.snap(dragged, list(scene.items()))
        assert result.snapped_pos.x() == 0
        assert result.snapped_pos.y() == 0
        assert not result.snapped_x
        assert not result.snapped_y

    def test_snap_x_to_left_edge(self, snapper, scene) -> None:
        """Test snapping to the left edge of a target item."""
        target = self._make_selectable_rect(scene, 200, 0, 100, 100)
        # sceneBoundingRect includes pen margin (~0.5), so target left is ~199.5
        target_left = target.sceneBoundingRect().left()
        dragged = QRectF(148, 50, 50, 50)
        result = snapper.snap(dragged, list(scene.items()), exclude=set())
        assert result.snapped_x
        # Snap should move the dragged rect's right edge (198) to target's left edge
        expected_dx = target_left - 198.0
        assert abs(result.snapped_pos.x() - expected_dx) < 0.01

    def test_snap_y_to_top_edge(self, snapper, scene) -> None:
        """Test snapping to the top edge of a target item."""
        target = self._make_selectable_rect(scene, 0, 200, 100, 100)
        target_top = target.sceneBoundingRect().top()
        dragged = QRectF(50, 148, 50, 50)
        result = snapper.snap(dragged, list(scene.items()), exclude=set())
        assert result.snapped_y
        expected_dy = target_top - 198.0
        assert abs(result.snapped_pos.y() - expected_dy) < 0.01

    def test_no_snap_beyond_threshold(self, snapper, scene) -> None:
        """Test that items beyond threshold are not snapped to."""
        self._make_selectable_rect(scene, 200, 200, 100, 100)
        # Dragged rect far from target
        dragged = QRectF(0, 0, 50, 50)
        result = snapper.snap(dragged, list(scene.items()), exclude=set())
        assert not result.snapped_x
        assert not result.snapped_y

    def test_snap_to_center(self, snapper, scene) -> None:
        """Test snapping to the center of a target item."""
        self._make_selectable_rect(scene, 200, 200, 100, 100)
        # Target center is at (250, 250)
        # Dragged center at (248, 248) -> within threshold
        dragged = QRectF(223, 223, 50, 50)
        result = snapper.snap(dragged, list(scene.items()), exclude=set())
        assert result.snapped_x
        assert result.snapped_y

    def test_excludes_dragged_items(self, snapper, scene) -> None:
        """Test that excluded items are not used as snap targets."""
        target = self._make_selectable_rect(scene, 200, 200, 100, 100)
        # Dragged rect near target - but target is excluded
        dragged = QRectF(195, 195, 50, 50)
        result = snapper.snap(
            dragged, list(scene.items()), exclude={target}
        )
        assert not result.snapped_x
        assert not result.snapped_y

    def test_snap_generates_guides(self, snapper, scene) -> None:
        """Test that snapping generates visual guide lines."""
        self._make_selectable_rect(scene, 200, 200, 100, 100)
        # Dragged rect close enough to snap on both axes
        dragged = QRectF(195, 195, 50, 50)
        canvas = QRectF(0, 0, 1000, 1000)
        result = snapper.snap(
            dragged, list(scene.items()), exclude=set(), canvas_rect=canvas
        )
        assert len(result.guides) >= 1

    def test_threshold_property(self, snapper) -> None:
        """Test getting and setting the threshold."""
        assert snapper.threshold == 10.0
        snapper.threshold = 20.0
        assert snapper.threshold == 20.0

    def test_threshold_minimum(self, snapper) -> None:
        """Test that threshold cannot go below 1.0."""
        snapper.threshold = 0.5
        assert snapper.threshold == 1.0

    def test_non_selectable_items_ignored(self, snapper, scene) -> None:
        """Test that non-selectable items are not used as snap targets."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        item.setPos(200, 200)
        # NOT setting ItemIsSelectable
        scene.addItem(item)
        dragged = QRectF(195, 195, 50, 50)
        result = snapper.snap(dragged, list(scene.items()), exclude=set())
        assert not result.snapped_x
        assert not result.snapped_y

    def test_snap_to_extra_x(self, snapper, scene) -> None:
        """Test snapping to extra_x values (e.g. vertical guide lines)."""
        dragged = QRectF(198, 300, 50, 50)  # left edge at 198, close to x=200
        result = snapper.snap(
            dragged, list(scene.items()), exclude=set(), extra_x=[200.0]
        )
        assert result.snapped_x
        # Left edge (198) should snap to 200: dx = +2
        assert abs(result.snapped_pos.x() - 2.0) < 0.01

    def test_snap_to_extra_y(self, snapper, scene) -> None:
        """Test snapping to extra_y values (e.g. horizontal guide lines)."""
        dragged = QRectF(300, 198, 50, 50)  # top edge at 198, close to y=200
        result = snapper.snap(
            dragged, list(scene.items()), exclude=set(), extra_y=[200.0]
        )
        assert result.snapped_y
        assert abs(result.snapped_pos.y() - 2.0) < 0.01

    def test_extra_values_beyond_threshold_ignored(self, snapper, scene) -> None:
        """Test that extra values beyond threshold are not snapped to."""
        dragged = QRectF(0, 0, 50, 50)  # far from x=500
        result = snapper.snap(
            dragged, list(scene.items()), exclude=set(), extra_x=[500.0]
        )
        assert not result.snapped_x


class TestGuideLine:
    """Tests for GuideLine dataclass."""

    def test_guide_line_horizontal(self, qtbot) -> None:
        from open_garden_planner.ui.canvas.canvas_scene import GuideLine

        g = GuideLine(is_horizontal=True, position=100.0)
        assert g.is_horizontal is True
        assert g.position == 100.0

    def test_guide_line_vertical(self, qtbot) -> None:
        from open_garden_planner.ui.canvas.canvas_scene import GuideLine

        g = GuideLine(is_horizontal=False, position=250.5)
        assert g.is_horizontal is False
        assert g.position == 250.5

    def test_guide_line_mutable(self, qtbot) -> None:
        from open_garden_planner.ui.canvas.canvas_scene import GuideLine

        g = GuideLine(is_horizontal=True, position=0.0)
        g.position = 300.0
        assert g.position == 300.0
