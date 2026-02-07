"""Tests for US-6.3: Drop shadows on all objects (toggleable)."""

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

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


class TestDropShadowsOnScene:
    """Tests for shadow management on CanvasScene."""

    def test_shadows_enabled_by_default(self, qtbot) -> None:
        scene = CanvasScene()
        assert scene.shadows_enabled is True

    def test_rectangle_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)
        effect = item.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)

    def test_circle_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        item = CircleItem(50, 50, 25)
        scene.addItem(item)
        effect = item.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)

    def test_polygon_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)]
        item = PolygonItem(points)
        scene.addItem(item)
        effect = item.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)

    def test_polyline_gets_shadow_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(200, 50)]
        item = PolylineItem(points)
        scene.addItem(item)
        effect = item.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)

    def test_shadow_effect_parameters(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)
        effect = item.graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect)
        assert effect.blurRadius() == CanvasScene.SHADOW_BLUR_RADIUS
        assert effect.xOffset() == CanvasScene.SHADOW_OFFSET_X
        assert effect.yOffset() == CanvasScene.SHADOW_OFFSET_Y
        assert effect.color() == CanvasScene.SHADOW_COLOR

    def test_disable_shadows_removes_effects(self, qtbot) -> None:
        scene = CanvasScene()
        item1 = RectangleItem(0, 0, 100, 50)
        item2 = CircleItem(200, 200, 30)
        scene.addItem(item1)
        scene.addItem(item2)

        scene.set_shadows_enabled(False)

        assert scene.shadows_enabled is False
        assert item1.graphicsEffect() is None
        assert item2.graphicsEffect() is None

    def test_reenable_shadows_applies_effects(self, qtbot) -> None:
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)

        scene.set_shadows_enabled(False)
        assert item.graphicsEffect() is None

        scene.set_shadows_enabled(True)
        assert isinstance(item.graphicsEffect(), QGraphicsDropShadowEffect)

    def test_no_shadow_when_disabled_on_add(self, qtbot) -> None:
        scene = CanvasScene()
        scene.set_shadows_enabled(False)

        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)

        assert item.graphicsEffect() is None

    def test_background_image_no_shadow(self, qtbot, tmp_path) -> None:
        """Background images should not receive drop shadows."""
        # Create a small test image
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QImage, QColor as QC

        img = QImage(QSize(10, 10), QImage.Format.Format_RGB32)
        img.fill(QC(255, 255, 255))
        img_path = str(tmp_path / "test.png")
        img.save(img_path)

        scene = CanvasScene()
        item = BackgroundImageItem(img_path)
        scene.addItem(item)
        assert item.graphicsEffect() is None

    def test_plant_circle_gets_shadow(self, qtbot) -> None:
        """Plant items (trees, shrubs, perennials) also get shadows."""
        scene = CanvasScene()
        item = CircleItem(50, 50, 30, object_type=ObjectType.TREE)
        scene.addItem(item)
        assert isinstance(item.graphicsEffect(), QGraphicsDropShadowEffect)

    def test_many_items_shadow_toggle(self, qtbot) -> None:
        """Toggling shadows with 100+ objects completes without error."""
        scene = CanvasScene()
        items = []
        for i in range(120):
            item = RectangleItem(i * 110, 0, 100, 50)
            scene.addItem(item)
            items.append(item)

        # All should have shadows
        for item in items:
            assert isinstance(item.graphicsEffect(), QGraphicsDropShadowEffect)

        # Disable
        scene.set_shadows_enabled(False)
        for item in items:
            assert item.graphicsEffect() is None

        # Re-enable
        scene.set_shadows_enabled(True)
        for item in items:
            assert isinstance(item.graphicsEffect(), QGraphicsDropShadowEffect)
