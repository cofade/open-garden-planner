"""Smart Symbols are gone; a plan that contains one opens as a plain group (#1009).

ADR-032 designed the escape route: a symbol was stored as ``type: "group"``
plus a ``smart_symbol`` key and its generated children. Once the loader stops
reading that key, an old plan opens as a plain group with unchanged geometry
and typed members; the next save drops the key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import GroupItem, RectangleItem


def _scene_with_group(tmp_path: Path) -> tuple[Path, list[tuple[str, float, float]]]:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    bed = RectangleItem(
        100.0, 100.0, 300.0, 200.0,
        object_type=ObjectType.RAISED_BED, layer_id=scene.active_layer.id,
        name="Raised bed frame",
    )
    plant = RectangleItem(
        140.0, 140.0, 60.0, 60.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
        name="Tomato row",
    )
    scene.addItem(bed)
    scene.addItem(plant)
    group = GroupItem(layer_id=scene.active_layer.id, name="Old symbol")
    scene.addItem(group)
    group.addToGroup(bed)
    group.addToGroup(plant)
    group.setPos(QPointF(40.0, 20.0))
    group._apply_rotation(31.0)

    children = [
        (type(item).__name__, round(item.scenePos().x(), 3),
         round(item.scenePos().y(), 3))
        for item in (bed, plant)
    ]
    path = tmp_path / "old-smart-symbol.ogp"
    ProjectManager().save(scene, path)
    return path, children


def test_an_old_smart_symbol_opens_as_a_plain_group_with_its_geometry(
    qtbot, tmp_path: Path,
) -> None:
    path, children = _scene_with_group(tmp_path)

    # Simulate the pre-removal file: the group carries the parametric key.
    data = json.loads(path.read_text(encoding="utf-8"))
    group_dict = next(obj for obj in data["objects"] if obj.get("type") == "group")
    group_dict["smart_symbol"] = {"id": "raised_bed_rows", "version": 1,
                                  "params": {"rows": 4}}
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded, path)

    groups = [item for item in loaded.items() if isinstance(item, GroupItem)]
    assert len(groups) == 1
    group = groups[0]
    assert type(group) is GroupItem, "the parametric class must not come back"
    assert group.rotation() == pytest.approx(31.0, abs=0.01)
    assert group.name == "Old symbol"

    members = [
        item for item in loaded.items()
        if item.parentItem() is group and hasattr(item, "item_id")
    ]
    assert len(members) == 2
    assert sorted(
        (type(item).__name__, round(item.scenePos().x(), 3),
         round(item.scenePos().y(), 3))
        for item in members
    ) == sorted(children)
    # Typed children are not flattened by the removal (#599's types survive).
    assert sorted(str(item.object_type) for item in members) == sorted(
        [str(ObjectType.RAISED_BED), str(ObjectType.PERENNIAL)]
    )


def test_the_next_save_drops_the_parametric_key(qtbot, tmp_path: Path) -> None:
    path, _children = _scene_with_group(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    group_dict = next(obj for obj in data["objects"] if obj.get("type") == "group")
    group_dict["smart_symbol"] = {"id": "raised_bed_rows", "version": 1}
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = CanvasScene(width_cm=5000, height_cm=3000)
    manager = ProjectManager()
    manager.load(loaded, path)
    resaved = tmp_path / "resaved.ogp"
    manager.save(loaded, resaved)

    text = resaved.read_text(encoding="utf-8")
    assert "smart_symbol" not in text
    # The group is still a group with its members (nothing is lost on save).
    saved = json.loads(text)
    group_dict = next(obj for obj in saved["objects"] if obj.get("type") == "group")
    assert len(group_dict["children"]) == 2
    assert group_dict["rotation"] == pytest.approx(31.0, abs=0.01)
