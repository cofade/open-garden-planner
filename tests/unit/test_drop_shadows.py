"""Tests for US-6.3: Painted drop shadows on all objects (toggleable)."""

from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.canvas.items.background_image_item import (
    BackgroundImageItem,
)
from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin


class TestPaintedShadows:
    """Tests for painted-shadow management on CanvasScene."""

    def test_shadows_enabled_by_default(self, qtbot) -> None:
        scene = CanvasScene()
        assert scene.shadows_enabled is True

    def test_rectangle_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)
        assert item.shadows_enabled is True

    def test_circle_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        item = CircleItem(50, 50, 25)
        scene.addItem(item)
        assert item.shadows_enabled is True

    def test_polygon_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)]
        item = PolygonItem(points)
        scene.addItem(item)
        assert item.shadows_enabled is True

    def test_polyline_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(200, 50)]
        item = PolylineItem(points)
        scene.addItem(item)
        assert item.shadows_enabled is True

    def test_shadow_parameters_on_mixin(self, qtbot) -> None:
        """Shadow offset and color are defined on the mixin."""
        assert GardenItemMixin.SHADOW_OFFSET_X == 3.0
        assert GardenItemMixin.SHADOW_OFFSET_Y == -3.0
        assert GardenItemMixin.SHADOW_COLOR.alpha() > 0

    def test_disable_shadows_clears_flag(self, qtbot) -> None:
        scene = CanvasScene()
        item1 = RectangleItem(0, 0, 100, 50)
        item2 = CircleItem(200, 200, 30)
        scene.addItem(item1)
        scene.addItem(item2)

        scene.set_shadows_enabled(False)

        assert scene.shadows_enabled is False
        assert item1.shadows_enabled is False
        assert item2.shadows_enabled is False

    def test_reenable_shadows_sets_flag(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)

        scene.set_shadows_enabled(False)
        assert item.shadows_enabled is False

        scene.set_shadows_enabled(True)
        assert item.shadows_enabled is True

    def test_no_shadow_when_disabled_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        scene.set_shadows_enabled(False)

        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)

        assert item.shadows_enabled is False

    def test_background_image_no_shadow_flag(self, qtbot, tmp_path) -> None:
        """Background images should not have shadow flag (not GardenItemMixin)."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QImage, QColor as QC

        img = QImage(QSize(10, 10), QImage.Format.Format_RGB32)
        img.fill(QC(255, 255, 255))
        img_path = str(tmp_path / "test.png")
        img.save(img_path)

        scene = CanvasScene()
        item = BackgroundImageItem(img_path)
        scene.addItem(item)
        assert not hasattr(item, 'shadows_enabled') or not isinstance(item, GardenItemMixin)

    def test_plant_circle_gets_shadow(self, qtbot) -> None:
        """Plant items (trees, shrubs, perennials) also get shadows."""
        scene = CanvasScene()
        item = CircleItem(50, 50, 30, object_type=ObjectType.TREE)
        scene.addItem(item)
        assert item.shadows_enabled is True

    def test_many_items_shadow_toggle(self, qtbot) -> None:
        """Toggling shadows with 100+ objects completes without error."""
        scene = CanvasScene()
        items = []
        for i in range(120):
            item = RectangleItem(i * 110, 0, 100, 50)
            scene.addItem(item)
            items.append(item)

        # All should have shadows enabled
        for item in items:
            assert item.shadows_enabled is True

        # Disable
        scene.set_shadows_enabled(False)
        for item in items:
            assert item.shadows_enabled is False

        # Re-enable
        scene.set_shadows_enabled(True)
        for item in items:
            assert item.shadows_enabled is True

    def test_no_graphics_effect_applied(self, qtbot) -> None:
        """Painted shadows must NOT use QGraphicsEffect (performance)."""
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)
        assert item.graphicsEffect() is None

    def test_bounding_rect_expands_for_shadow(self, qtbot) -> None:
        """Bounding rect should be larger when shadows are enabled."""
        item = RectangleItem(0, 0, 100, 50)
        item.shadows_enabled = True
        rect_with = item.boundingRect()

        item.shadows_enabled = False
        rect_without = item.boundingRect()

        assert rect_with.width() > rect_without.width()
        assert rect_with.height() > rect_without.height()
