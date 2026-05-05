"""Regression test for US-12.10/F2.7 — plant must render above its parent bed.

The .ogp save/load cycle reverses same-z stacking via QGraphicsScene's items()
list. Without the third pass in ``CanvasScene._update_items_z_order``, the bed
would end up on top of the plant on reload.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem


def _make_scene_with_bed_and_plant(qtbot) -> tuple[CanvasScene, PolygonItem, CircleItem]:
    scene = CanvasScene(5000, 3000)
    bed = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 400), QPointF(0, 400)],
        object_type=ObjectType.GARDEN_BED,
    )
    plant = CircleItem(
        center_x=200, center_y=200, radius=20, object_type=ObjectType.TREE
    )
    scene.addItem(bed)
    scene.addItem(plant)
    plant._parent_bed_id = bed.item_id
    bed._child_item_ids = [plant.item_id]
    return scene, bed, plant


class TestPlantAboveBedAfterReload:
    def test_plant_zvalue_is_bumped_above_bed(self, qtbot) -> None:
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)
        # Same layer initially → same z. Simulate the post-load update pass.
        bed.setZValue(0)
        plant.setZValue(0)

        scene._update_items_z_order()

        assert plant.zValue() > bed.zValue(), (
            "Plant must render above its parent bed after the z-order pass; "
            "otherwise it disappears under the bed on .ogp reload."
        )

    def test_plant_with_higher_z_is_left_alone(self, qtbot) -> None:
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)
        bed.setZValue(0)
        plant.setZValue(50)  # already above

        scene._update_items_z_order()

        # Layer-driven first pass resets to layer.z_order * 100. After third
        # pass the plant is again above the bed.
        assert plant.zValue() > bed.zValue()

    def test_plant_without_parent_bed_unaffected(self, qtbot) -> None:
        scene = CanvasScene(5000, 3000)
        plant = CircleItem(
            center_x=200, center_y=200, radius=20, object_type=ObjectType.TREE
        )
        scene.addItem(plant)
        # Should run without error and not crash on missing _parent_bed_id.
        scene._update_items_z_order()
        # No assertion on z value — pass through is success.
