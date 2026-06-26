"""Integration tests for US-C3b — trellis vertical gardening.

Covers the two trellis-specific behaviours:
  * 1-D spacing — overlap is measured only along the trellis's long axis, so the
    perpendicular (canvas-Y) offset is ignored and rotation is honoured.
  * the trellis is excluded from soil features (re-assert).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._spacing_circles_enabled = True
    return win


def _plant(scene, parent, cx, cy, radius=20.0) -> CircleItem:
    p = CircleItem(cx, cy, 5.0, object_type=ObjectType.TREE)
    p.spacing_radius_cm = radius
    scene.addItem(p)
    p.parent_bed_id = parent.item_id
    parent.add_child_id(p.item_id)
    return p


class TestTrellis1DSpacing:
    def test_perpendicular_offset_still_overlaps(self, qtbot, monkeypatch) -> None:
        """Two climbers at the same along-bar position overlap even when far apart
        on the perpendicular (canvas-Y) axis — 2-D distance would miss this."""
        win = _make_app(qtbot, monkeypatch)
        scene = win.canvas_scene
        trellis = RectangleItem(0, 0, 200, 10, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        a = _plant(scene, trellis, 50, 5, radius=20)
        b = _plant(scene, trellis, 50, 200, radius=20)  # same x, far in y

        # Explicit discriminator: under plain 2-D the pair would NOT overlap
        # (Euclidean 195 > 40), so a passing assertion proves the 1-D path is live.
        import math
        assert math.hypot(50 - 50, 5 - 200) > 20 + 20

        win._update_spacing_overlaps()
        # 1-D along-x distance == 0 < 40 → overlap.
        assert a._spacing_overlap == "overlap"
        assert b._spacing_overlap == "overlap"

    def test_far_along_bar_no_overlap(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        scene = win.canvas_scene
        trellis = RectangleItem(0, 0, 200, 10, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        a = _plant(scene, trellis, 10, 5, radius=20)
        b = _plant(scene, trellis, 190, 5, radius=20)  # 180 apart along the bar

        win._update_spacing_overlaps()
        assert a._spacing_overlap == "ideal"
        assert b._spacing_overlap == "ideal"

    def test_vertical_trellis_uses_short_dimension_branch(self, qtbot, monkeypatch) -> None:
        """A trellis taller than wide spaces along its (vertical) long edge."""
        win = _make_app(qtbot, monkeypatch)
        scene = win.canvas_scene
        trellis = RectangleItem(0, 0, 10, 200, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        # Same y (same along-bar position), far apart in x → overlap.
        a = _plant(scene, trellis, 5, 50, radius=20)
        b = _plant(scene, trellis, 200, 50, radius=20)

        win._update_spacing_overlaps()
        assert a._spacing_overlap == "overlap"
        assert b._spacing_overlap == "overlap"

    def test_axis_distance_fn_follows_rotation(self, qtbot, monkeypatch) -> None:
        """The distance callable projects onto the rotated long axis (scene space)."""
        win = _make_app(qtbot, monkeypatch)
        trellis = RectangleItem(0, 0, 200, 10, object_type=ObjectType.TRELLIS)
        win.canvas_scene.addItem(trellis)

        # Unrotated: long axis is x → projects onto dx.
        dist = win._trellis_axis_distance_fn(trellis)
        assert abs(dist(10, 0) - 10) < 1e-6
        assert abs(dist(0, 10) - 0) < 1e-6

        # Rotate 90° about the rect centre: long axis becomes y → projects onto dy.
        trellis.setTransformOriginPoint(trellis.rect().center())
        trellis.setRotation(90)
        dist_r = win._trellis_axis_distance_fn(trellis)
        assert abs(dist_r(0, 10) - 10) < 1e-6
        assert abs(dist_r(10, 0) - 0) < 1e-6


class TestTrellisSoilExclusion:
    def test_trellis_never_gets_soil_mismatch(self, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        trellis = RectangleItem(0, 0, 150, 20, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        plant = CircleItem(50, 10, 15, object_type=ObjectType.TREE, name="Bean")
        plant.metadata["plant_species"] = {
            "common_name": "Bean",
            "scientific_name": "Phaseolus vulgaris",
            "ph_min": 6.0,
            "ph_max": 7.0,
        }
        scene.addItem(plant)
        trellis._child_item_ids = [plant._item_id]

        svc = MagicMock()
        svc.get_effective_record.return_value = SoilTestRecord(date="2026-05-01", ph=4.5)
        view.set_soil_service(svc)
        view.refresh_soil_mismatches()

        assert trellis._soil_mismatch_level is None
        # find_smallest_bed_containing still treats the trellis as a drop target.
        assert scene.find_smallest_bed_containing(QPointF(75, 10)) is trellis
