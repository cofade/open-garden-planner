"""Backwards-compatible `.ogp` round-trip tests for containers (US-C3a).

Container properties are additive ``metadata`` keys, so:
  * a saved container round-trips its type + metadata, and
  * a pre-C3 file (no container keys) still loads at the unchanged
    ``FILE_VERSION`` — no version bump, no crash.
"""
from __future__ import annotations

import json

import pytest
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture
def manager(qtbot) -> ProjectManager:  # noqa: ARG001 — qtbot for Qt init
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:  # noqa: ARG001
    return QGraphicsScene()


def test_file_version_not_bumped() -> None:
    """Container support must stay additive — no FILE_VERSION bump."""
    assert FILE_VERSION == "1.4"


def test_container_metadata_round_trips(manager, scene, tmp_path) -> None:
    container = RectangleItem(0, 0, 80, 50, object_type=ObjectType.CONTAINER)
    container.metadata["container_material"] = "terracotta"
    container.metadata["container_drainage"] = False
    container.metadata["container_height_cm"] = 45.0
    container.metadata["container_soil_volume_l"] = 12.5
    scene.addItem(container)

    file_path = tmp_path / "container.ogp"
    manager.save(scene, file_path)

    scene.clear()
    manager.load(scene, file_path)

    items = [i for i in scene.items() if isinstance(i, RectangleItem)]
    assert len(items) == 1
    loaded = items[0]
    assert loaded.object_type is ObjectType.CONTAINER
    assert loaded.metadata["container_material"] == "terracotta"
    assert loaded.metadata["container_drainage"] is False
    assert loaded.metadata["container_height_cm"] == 45.0
    assert loaded.metadata["container_soil_volume_l"] == 12.5


def test_round_container_round_trips(manager, scene, tmp_path) -> None:
    pot = CircleItem(0, 0, 25, object_type=ObjectType.CONTAINER_ROUND)
    pot.metadata["container_material"] = "metal"
    scene.addItem(pot)

    file_path = tmp_path / "round.ogp"
    manager.save(scene, file_path)
    scene.clear()
    manager.load(scene, file_path)

    items = [i for i in scene.items() if isinstance(i, CircleItem)]
    assert len(items) == 1
    assert items[0].object_type is ObjectType.CONTAINER_ROUND
    assert items[0].metadata["container_material"] == "metal"


def test_pre_c3_file_loads_unchanged(manager, scene, tmp_path) -> None:
    """A plain bed (no container keys) saves at v1.4 and reloads cleanly.

    Simulates an older project file: the saved JSON carries the unchanged
    FILE_VERSION and no ``container_*`` metadata, and loads without error.
    """
    bed = RectangleItem(10, 10, 200, 100, object_type=ObjectType.GARDEN_BED)
    scene.addItem(bed)
    file_path = tmp_path / "legacy.ogp"
    manager.save(scene, file_path)

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    assert raw["version"] == "1.4"
    assert "container_material" not in json.dumps(raw)

    scene.clear()
    manager.load(scene, file_path)  # must not raise

    beds = [i for i in scene.items() if isinstance(i, RectangleItem)]
    assert len(beds) == 1
    assert beds[0].object_type is ObjectType.GARDEN_BED
