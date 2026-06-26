"""Integration tests for US-C3a — Container & wall-planter gardening.

Covers the three load-bearing behaviours of the predicate split:
  * Containers/wall planters/trellises accept dropped plants as children
    (``is_plant_parent_type`` seam via ``find_smallest_bed_containing``).
  * Containers participate in the soil-mismatch seam (``is_bed_type``); the
    trellis is excluded (it holds no soil).
  * Container capacity-overrun badge wiring
    (``GardenPlannerApp._update_container_capacity``).
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

# ---------------------------------------------------------------------------
# Parent acceptance: containers/wall planters/trellises take dropped plants.


class TestContainersAcceptPlants:
    def _scene(self, qtbot) -> CanvasScene:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        return scene

    def test_rect_container_is_a_drop_target(self, qtbot) -> None:
        scene = self._scene(qtbot)
        container = RectangleItem(0, 0, 100, 60, object_type=ObjectType.CONTAINER)
        scene.addItem(container)
        found = scene.find_smallest_bed_containing(QPointF(50, 30))
        assert found is container

    def test_wall_planter_is_a_drop_target(self, qtbot) -> None:
        scene = self._scene(qtbot)
        planter = RectangleItem(0, 0, 120, 40, object_type=ObjectType.WALL_PLANTER)
        scene.addItem(planter)
        found = scene.find_smallest_bed_containing(QPointF(60, 20))
        assert found is planter

    def test_trellis_is_a_drop_target(self, qtbot) -> None:
        # Trellis is a plant-parent (not soil) — still accepts dropped plants.
        scene = self._scene(qtbot)
        trellis = RectangleItem(0, 0, 150, 20, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        found = scene.find_smallest_bed_containing(QPointF(75, 10))
        assert found is trellis

    def test_non_parent_is_not_a_drop_target(self, qtbot) -> None:
        scene = self._scene(qtbot)
        house = RectangleItem(0, 0, 100, 60, object_type=ObjectType.HOUSE)
        scene.addItem(house)
        assert scene.find_smallest_bed_containing(QPointF(50, 30)) is None

    def test_smallest_parent_wins_when_nested(self, qtbot) -> None:
        scene = self._scene(qtbot)
        bed = RectangleItem(0, 0, 200, 200, object_type=ObjectType.GARDEN_BED)
        pot = RectangleItem(10, 10, 40, 40, object_type=ObjectType.CONTAINER)
        scene.addItem(bed)
        scene.addItem(pot)
        # Point inside both → the smaller container is the more specific parent.
        found = scene.find_smallest_bed_containing(QPointF(30, 30))
        assert found is pot


# ---------------------------------------------------------------------------
# Soil seam: containers participate; trellis does not.


def _mismatch_plant() -> CircleItem:
    plant = CircleItem(50, 30, 15, object_type=ObjectType.TREE, name="Tomato")
    plant.metadata["plant_species"] = {
        "common_name": "Tomato",
        "scientific_name": "Solanum lycopersicum",
        "ph_min": 5.8,
        "ph_max": 7.0,
    }
    return plant


def _soil_service_mock(record: SoilTestRecord | None) -> MagicMock:
    svc = MagicMock()
    svc.get_effective_record.return_value = record
    return svc


class TestContainerSoilSeam:
    def test_container_gets_soil_mismatch(self, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        container = RectangleItem(0, 0, 100, 60, object_type=ObjectType.CONTAINER)
        scene.addItem(container)
        plant = _mismatch_plant()
        scene.addItem(plant)
        container._child_item_ids = [plant._item_id]

        view.set_soil_service(_soil_service_mock(SoilTestRecord(date="2026-05-01", ph=5.0)))
        view.refresh_soil_mismatches()

        assert container._soil_mismatch_level == "warning"

    def test_trellis_excluded_from_soil(self, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        trellis = RectangleItem(0, 0, 150, 20, object_type=ObjectType.TRELLIS)
        scene.addItem(trellis)
        plant = _mismatch_plant()
        scene.addItem(plant)
        trellis._child_item_ids = [plant._item_id]

        view.set_soil_service(_soil_service_mock(SoilTestRecord(date="2026-05-01", ph=5.0)))
        view.refresh_soil_mismatches()

        # Trellis is not a soil container → no mismatch level is ever assigned.
        assert trellis._soil_mismatch_level is None


# ---------------------------------------------------------------------------
# Capacity wiring (real GardenPlannerApp method).


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


class TestContainerCapacity:
    def _add_plant(self, scene, container, cx, cy, radius) -> CircleItem:
        plant = CircleItem(cx, cy, radius, object_type=ObjectType.TREE)
        scene.addItem(plant)
        plant.parent_bed_id = container.item_id
        container.add_child_id(plant.item_id)
        return plant

    def test_overfilled_container_flags_overrun(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        scene = win.canvas_scene
        # Container footprint = 10×10 = 100 cm².
        container = RectangleItem(0, 0, 10, 10, object_type=ObjectType.CONTAINER)
        scene.addItem(container)
        # Two plants of radius 5 → ~78.5 cm² each → 157 cm² > 100 cm².
        self._add_plant(scene, container, 3, 3, 5)
        self._add_plant(scene, container, 7, 7, 5)

        win._update_container_capacity()
        assert container.capacity_overrun is True

    def test_within_capacity_no_overrun(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        scene = win.canvas_scene
        # Large container, one small plant → comfortably within capacity.
        container = RectangleItem(0, 0, 100, 100, object_type=ObjectType.CONTAINER)
        scene.addItem(container)
        self._add_plant(scene, container, 50, 50, 5)

        win._update_container_capacity()
        assert container.capacity_overrun is False

    def test_badge_not_drawn_after_type_change(self, qtbot) -> None:
        """A flagged container that becomes a non-container draws no phantom badge."""
        from unittest.mock import MagicMock

        container = RectangleItem(0, 0, 10, 10, object_type=ObjectType.CONTAINER)
        container.set_capacity_overrun(True)
        # Sanity: while it is a container, the badge paints.
        painter = MagicMock()
        container._draw_capacity_badge(painter)
        assert painter.drawPolygon.called

        # Change Type to a generic rectangle — the stale flag must not paint.
        container.object_type = ObjectType.GENERIC_RECTANGLE
        painter2 = MagicMock()
        container._draw_capacity_badge(painter2)
        assert not painter2.drawPolygon.called
