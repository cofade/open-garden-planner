"""Forward-compatibility pin for additive ObjectType growth (#308, Package 3a).

Adding enum members (SANDBOX, TRAMPOLINE, …) does NOT bump FILE_VERSION: an
OLDER app opening a plan that contains a type it doesn't know must degrade
gracefully — geometry, name and metadata survive as a generic shape, nothing
raises. This test simulates the older app by feeding the loader an
`object_type` name that no build knows.
"""

# ruff: noqa: ARG002

import json

import pytest
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


@pytest.fixture
def manager(qtbot) -> ProjectManager:
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:
    return QGraphicsScene()


def _round_trip_with_renamed_type(manager, scene, tmp_path, item, unknown_name: str):
    scene.addItem(item)
    path = tmp_path / "plan.ogp"
    manager.save(scene, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    for obj in data["objects"]:
        if obj.get("object_type") == item.object_type.name:
            obj["object_type"] = unknown_name  # what an older app sees for a newer type
    path.write_text(json.dumps(data), encoding="utf-8")
    scene.clear()
    manager.load(scene, path)


class TestUnknownObjectTypeDegradesGracefully:
    def test_rectangle_falls_back_to_generic_rectangle(self, manager, scene, tmp_path) -> None:
        item = RectangleItem(10, 20, 150, 150, object_type=ObjectType.SANDBOX)
        item.name = "kids corner"
        _round_trip_with_renamed_type(manager, scene, tmp_path, item, "TYPE_FROM_THE_FUTURE")
        loaded = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert len(loaded) == 1
        assert loaded[0].object_type == ObjectType.GENERIC_RECTANGLE
        assert loaded[0].name == "kids corner"
        assert loaded[0].rect().width() == pytest.approx(150)

    def test_circle_falls_back_to_generic_circle(self, manager, scene, tmp_path) -> None:
        item = CircleItem(50, 50, 60, object_type=ObjectType.TRAMPOLINE)
        _round_trip_with_renamed_type(manager, scene, tmp_path, item, "TYPE_FROM_THE_FUTURE")
        loaded = [i for i in scene.items() if isinstance(i, CircleItem)]
        assert len(loaded) == 1
        assert loaded[0].object_type == ObjectType.GENERIC_CIRCLE

    def test_new_roster_round_trips_by_name(self, manager, scene, tmp_path) -> None:
        """And on a build that knows the type, the name round-trips exactly."""
        for obj_type in (ObjectType.SANDBOX, ObjectType.HOT_TUB, ObjectType.PERGOLA):
            scene.clear()
            scene.addItem(RectangleItem(0, 0, 100, 100, object_type=obj_type))
            path = tmp_path / f"{obj_type.name}.ogp"
            manager.save(scene, path)
            scene.clear()
            manager.load(scene, path)
            loaded = [i for i in scene.items() if isinstance(i, RectangleItem)]
            assert loaded and loaded[0].object_type == obj_type
