"""Regression tests for the compare overlay (US-10.7)."""

from PyQt6.QtCore import QPointF

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

PLANT_OBJECTS = [
    {
        "type": "circle",
        "object_type": "TREE",
        "center_x": 200.0,
        "center_y": 150.0,
        "radius": 30.0,
        "fill_color": "#88cc88",
        "name": "Apfelbaum",
    },
    {
        "type": "circle",
        "object_type": "SHRUB",
        "center_x": 400.0,
        "center_y": 300.0,
        "radius": 25.0,
        "fill_color": "#cc8844",
        "name": "Johannisbeere",
    },
]


class TestCompareOverlaySurvivesSceneClear:
    """#337: CanvasScene.clear() must drop _compare_items alongside the C++
    teardown, so no reader of that list (clear_compare_overlay,
    set_compare_overlay_visible) can ever see a dangling wrapper."""

    def test_scene_clear_empties_compare_items(self, qtbot) -> None:
        """CanvasScene.clear() must drop _compare_items, not just the scene.

        Regression test for #337: scene.clear() destroys the C++ side of
        every item, but a naive override would leave stale Python wrappers
        in _compare_items. Any later reader of that list — clear_compare_
        overlay() or set_compare_overlay_visible() — would then raise
        ``RuntimeError: wrapped C/C++ object of type QGraphicsEllipseItem
        has been deleted``.
        """
        scene = CanvasScene(width_cm=1000, height_cm=800)
        scene.set_compare_overlay(PLANT_OBJECTS)
        assert len(scene._compare_items) > 0, (
            "set_compare_overlay should have populated _compare_items"
        )

        scene.clear()

        assert scene._compare_items == []
        # Neither reader of the list may raise on the now-empty list.
        scene.clear_compare_overlay()
        scene.set_compare_overlay_visible(True)

    def test_set_compare_overlay_visible_after_scene_clear_does_not_raise(
        self, qtbot
    ) -> None:
        """set_compare_overlay_visible() must survive a prior scene.clear().

        This is the second reader of _compare_items that #337's first fix
        attempt left unguarded — reachable in the shipped app via the
        checkable "Show Previous Season Overlay" menu action.
        """
        scene = CanvasScene(width_cm=1000, height_cm=800)
        scene.set_compare_overlay(PLANT_OBJECTS)

        scene.clear()

        # Must not raise RuntimeError
        scene.set_compare_overlay_visible(True)
        scene.set_compare_overlay_visible(False)

    def test_clear_compare_overlay_idempotent(self, qtbot) -> None:
        """clear_compare_overlay() on an empty list is a no-op."""
        scene = CanvasScene(width_cm=500, height_cm=500)
        scene.clear_compare_overlay()
        assert scene._compare_items == []

    def test_clear_compare_overlay_removes_items_from_scene(self, qtbot) -> None:
        """clear_compare_overlay() must actually remove items from the scene,
        not merely empty the tracking list."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        scene.set_compare_overlay(PLANT_OBJECTS)
        tracked_items = list(scene._compare_items)
        assert len(tracked_items) > 0
        for item in tracked_items:
            assert item in scene.items()

        scene.clear_compare_overlay()

        assert scene._compare_items == []
        for item in tracked_items:
            assert item not in scene.items()

    def test_scene_clear_resets_visibility_flag(self, qtbot) -> None:
        """scene.clear() must reset _compare_overlay_visible, not just the
        item list — otherwise a freshly loaded overlay after New Plan
        inherits a stale "visible" flag that disagrees with the menu
        action's unchecked state."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        scene.set_compare_overlay_visible(True)
        scene.set_compare_overlay(PLANT_OBJECTS)
        assert scene.compare_overlay_visible is True

        scene.clear()

        assert scene.compare_overlay_visible is False


class TestCalibrationSurvivesSceneClear:
    """#337 round 2: CanvasScene.clear() must also drop the calibration
    trackers (_calibration_markers, _calibration_points, _calibration_image,
    _calibration_mode) — the same dangling-wrapper hazard as the compare
    overlay, in the same class."""

    def test_cancel_calibration_after_scene_clear_does_not_raise(
        self, qtbot
    ) -> None:
        """cancel_calibration() after scene.clear() must not raise
        RuntimeError.

        Regression test: start_image_calibration() + add_calibration_point()
        populate _calibration_markers with QGraphicsLineItem wrappers.
        scene.clear() destroys their C++ side; cancel_calibration() (reached
        via _clear_calibration_markers) would then raise ``RuntimeError:
        wrapped C/C++ object of type QGraphicsLineItem has been deleted``
        on a naive fix that only handled the compare overlay.
        """
        scene = CanvasScene(width_cm=1000, height_cm=800)
        scene.start_image_calibration(None)
        scene.add_calibration_point(QPointF(100, 100))
        assert len(scene._calibration_markers) > 0

        scene.clear()

        assert scene._calibration_markers == []
        assert scene._calibration_mode is False
        # Must not raise RuntimeError
        scene.cancel_calibration()


class TestCompareOverlayClearedOnProjectLoad:
    """#337 round 2: loading a project must not let the previous plan's
    ghosted overlay items survive into the newly loaded plan.

    ProjectManager._deserialize_to_scene() removes existing items by an
    isinstance allow-list that never included the compare overlay's
    QGraphicsEllipseItem/QGraphicsSimpleTextItem — without an explicit
    clear_compare_overlay() call, those items would stay painted on the
    canvas after loading an unrelated plan.
    """

    def test_load_project_clears_previous_compare_overlay(
        self, qtbot, tmp_path
    ) -> None:
        from open_garden_planner.core.project import ProjectManager
        from open_garden_planner.ui.canvas.items import RectangleItem

        manager = ProjectManager()
        scene = CanvasScene(width_cm=1000, height_cm=800)

        # Save an empty-ish plan to load later.
        scene.addItem(RectangleItem(0, 0, 100, 50))
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Simulate the ghosted overlay from a *different*, previously open
        # plan (as _load_compare_overlay_from_previous_season would leave
        # it) still present when the user opens this plan.
        scene.set_compare_overlay(PLANT_OBJECTS)
        assert len(scene._compare_items) > 0
        assert any(
            item in scene.items() for item in scene._compare_items
        )

        manager.load(scene, file_path)

        assert scene._compare_items == []
        # No ghosted overlay item (a raw QGraphicsEllipseItem/
        # QGraphicsSimpleTextItem, not a real CircleItem) may remain.
        from PyQt6.QtWidgets import QGraphicsEllipseItem

        assert not any(
            type(i) is QGraphicsEllipseItem for i in scene.items()
        )
