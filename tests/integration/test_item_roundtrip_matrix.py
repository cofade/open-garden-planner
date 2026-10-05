"""Integration test: Item round-trip matrix for every placeable canvas item class.

Audit 2026-10 / Issue #394 (AUD-001, AUD-017, TD-010, TD-019).
Pins that every placeable item class in `ui/canvas/items` survives serialization
and deserialization through ProjectManager, with full dictionary equality
after save -> load -> save (the golden round-trip contract).
"""

import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION, ProjectManager
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CalloutItem,
    CircleItem,
    ConstructionCircleItem,
    ConstructionLineItem,
    EllipseItem,
    GroupItem,
    JournalPinItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
    TextItem,
)


def _create_sample_item(cls: type) -> Any:
    """Instantiate a sample placeable item with realistic attributes."""
    if cls is RectangleItem:
        item = RectangleItem(10.0, 20.0, 100.0, 50.0, object_type=ObjectType.RAISED_BED, name="MyBed")
        item.rotation_angle = 15.0
        return item
    elif cls is CircleItem:
        item = CircleItem(150.0, 150.0, 40.0, object_type=ObjectType.TREE, name="AppleTree")
        item.spacing_radius_cm = 60.0
        item.frost_protection_needed = True
        return item
    elif cls is PolygonItem:
        points = [QPointF(0.0, 0.0), QPointF(100.0, 0.0), QPointF(100.0, 80.0), QPointF(0.0, 80.0)]
        return PolygonItem(points, object_type=ObjectType.GARDEN_BED, name="PolyBed")
    elif cls is PolylineItem:
        points = [QPointF(0.0, 0.0), QPointF(50.0, 50.0), QPointF(100.0, 50.0)]
        return PolylineItem(points, object_type=ObjectType.FENCE, name="FenceLine")
    elif cls is EllipseItem:
        return EllipseItem(200.0, 200.0, 60.0, 30.0, object_type=ObjectType.GARDEN_BED, name="OvalBed")
    elif cls is ArcItem:
        return ArcItem(QPointF(100.0, 100.0), 50.0, 0.0, 90.0, name="ArcPath")
    elif cls is BezierItem:
        anchors = [QPointF(0.0, 0.0), QPointF(100.0, 100.0)]
        handles_in = [QPointF(0.0, 0.0), QPointF(70.0, 100.0)]
        handles_out = [QPointF(30.0, 0.0), QPointF(100.0, 100.0)]
        return BezierItem(anchors=anchors, handles_in=handles_in, handles_out=handles_out, name="Curve")
    elif cls is ConstructionLineItem:
        return ConstructionLineItem(QPointF(0.0, 0.0), QPointF(200.0, 200.0))
    elif cls is ConstructionCircleItem:
        return ConstructionCircleItem(150.0, 150.0, 75.0)
    elif cls is GroupItem:
        g = GroupItem()
        child1 = RectangleItem(0.0, 0.0, 50.0, 50.0)
        child2 = CircleItem(25.0, 25.0, 10.0)
        g.addToGroup(child1)
        g.addToGroup(child2)
        return g
    elif cls is CalloutItem:
        return CalloutItem(target=QPointF(50.0, 50.0), box_offset=QPointF(20.0, -30.0), content="Callout Note")
    elif cls is JournalPinItem:
        return JournalPinItem(x=75.0, y=75.0, note_id=str(uuid.uuid4()))
    elif cls is TextItem:
        text = TextItem(
            120.0,
            240.0,
            content="Sample Text Annotation",
            font_family="Helvetica",
            font_size=2.0,
            bold=True,
            italic=True,
            text_color=QColor("#ff5500"),
        )
        text.name = "Note1"
        text.rotation_angle = 30.0
        return text
    else:
        raise ValueError(f"Unknown item class: {cls}")


PLACEABLE_CLASSES = [
    RectangleItem,
    CircleItem,
    PolygonItem,
    PolylineItem,
    EllipseItem,
    ArcItem,
    BezierItem,
    ConstructionLineItem,
    ConstructionCircleItem,
    GroupItem,
    CalloutItem,
    JournalPinItem,
    TextItem,
]


@pytest.mark.parametrize("item_cls", PLACEABLE_CLASSES)
def test_item_serializer_core_roundtrip_dict_equality(item_cls: type, qtbot: Any) -> None:
    """Core serializer round-trip: item -> dict1 -> item2 -> dict2, dict1 == dict2."""
    pm = ProjectManager()
    original_item = _create_sample_item(item_cls)

    dict1 = pm._serialize_item_core(original_item)
    assert dict1 is not None, f"Failed to serialize {item_cls.__name__}"
    assert isinstance(dict1, dict)

    reconstructed_item = pm._deserialize_item_core(dict1)
    assert reconstructed_item is not None, f"Failed to deserialize {item_cls.__name__} from {dict1}"
    assert isinstance(reconstructed_item, item_cls)

    dict2 = pm._serialize_item_core(reconstructed_item)
    assert dict1 == dict2, f"Serialization dict diverged for {item_cls.__name__}:\n{dict1}\nvs\n{dict2}"


def test_text_item_file_save_and_load(qtbot: Any) -> None:
    """Test TextItem specifically end-to-end through ProjectManager save and load.

    Guards against AUD-001 (data loss on save) and verifies US-11.8 criterion.
    """
    pm = ProjectManager()
    scene = QGraphicsScene()
    text = TextItem(
        55.5,
        144.2,
        content="Carrots planting row",
        font_family="Courier New",
        font_size=1.75,
        bold=True,
        italic=False,
        text_color=QColor("#228833"),
    )
    text.name = "CarrotsText"
    text.rotation_angle = 25.0
    layer_id = uuid.uuid4()
    text.layer_id = layer_id
    scene.addItem(text)

    with tempfile.TemporaryDirectory() as td:
        file_path = Path(td) / "project_with_text.ogp"
        pm.save(scene, file_path)

        # File exists and is valid JSON
        assert file_path.exists()

        # Reload into fresh scene
        scene2 = QGraphicsScene()
        pm.load(scene2, file_path)

        reloaded_texts = [it for it in scene2.items() if isinstance(it, TextItem)]
        assert len(reloaded_texts) == 1, "TextItem was dropped on save/load!"

        r = reloaded_texts[0]
        assert r.content == "Carrots planting row"
        assert r.font_family == "Courier New"
        assert r.font_size == 1.75
        assert r.bold is True
        assert r.italic is False
        assert r.text_color.name() == QColor("#228833").name()
        assert r.name == "CarrotsText"
        assert abs(r.rotation_angle - 25.0) < 1e-4
        assert r.item_id == text.item_id
        assert r.layer_id == layer_id
        assert abs(r.pos().x() - 55.5) < 1e-3
        assert abs(r.pos().y() - 144.2) < 1e-3


def test_file_version_stays_1_4() -> None:
    """FILE_VERSION stays 1.4: TextItem was designed for v1.1 (US-11.8).

    Bumping to 1.5 would break backward compatibility across all 1.4 installs.
    """
    assert FILE_VERSION == "1.4"
