"""Regression test for US-12.10/F7 — exports must not include overlay items.

Selection / resize / rotation handles and the seasonal soil reminder badge
are scene-attached items, so ``scene.render()`` would paint them into PNG /
SVG / PDF / print output. ``ExportService._hide_overlay_items`` masks them
for the duration of a render and restores afterwards.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem, SoilBadgeItem


class TestHideOverlayItems:
    def test_soil_badge_hidden_during_render(self, qtbot) -> None:
        scene = CanvasScene(5000, 3000)
        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED, name="Bed",
        )
        scene.addItem(bed)
        badge = SoilBadgeItem(bed, str(bed.item_id))
        scene.addItem(badge)
        assert badge.isVisible()

        hidden, prior = ExportService._hide_overlay_items(scene)

        assert badge in hidden
        assert badge.isVisible() is False

        ExportService._restore_overlay_items(hidden, prior)
        assert badge.isVisible() is True

    def test_selection_cleared_during_render_and_restored(self, qtbot) -> None:
        scene = CanvasScene(5000, 3000)
        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED, name="Bed",
        )
        scene.addItem(bed)
        bed.setSelected(True)
        assert bed.isSelected()

        hidden, prior_selection = ExportService._hide_overlay_items(scene)

        assert bed in prior_selection
        assert bed.isSelected() is False

        ExportService._restore_overlay_items(hidden, prior_selection)
        assert bed.isSelected() is True

    def test_already_invisible_items_not_disturbed(self, qtbot) -> None:
        scene = CanvasScene(5000, 3000)
        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED, name="Bed",
        )
        scene.addItem(bed)
        badge = SoilBadgeItem(bed, str(bed.item_id))
        scene.addItem(badge)
        badge.setVisible(False)  # Pre-hidden

        hidden, prior = ExportService._hide_overlay_items(scene)

        # Pre-hidden items are not collected — restore mustn't make them visible.
        assert badge not in hidden

        ExportService._restore_overlay_items(hidden, prior)
        assert badge.isVisible() is False
