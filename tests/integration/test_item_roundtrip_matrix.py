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


# ── a recoloured item keeps its look through load → save → load ──────────────
# (found by the 3D ground bake, Phase 17 L1.5 — a second reader of the same items)

RECOLOURED = "#ffc81e1e"  # no object type's default
#: Types a rectangle is drawn as (furniture is a sprite: no fill of its own).
RECTANGLE_TYPES = [
    ObjectType.GENERIC_RECTANGLE, ObjectType.LAWN, ObjectType.TERRACE_PATIO, ObjectType.GARDEN_BED,
    ObjectType.DRIVEWAY, ObjectType.POND_POOL, ObjectType.GREENHOUSE, ObjectType.HOUSE,
    ObjectType.GARAGE_SHED, ObjectType.CONTAINER, ObjectType.WALL_PLANTER,
]


def _reloaded(pm: ProjectManager, scene: QGraphicsScene, path: Path, cls: type
              ) -> tuple[QGraphicsScene, Any, dict[str, Any]]:
    """Save ``scene`` to ``path`` and load it: the new scene (it owns the item), the
    one item of ``cls`` in it, and that item as the file holds it."""
    import json

    pm.save(scene, path)
    saved = next(obj for obj in json.loads(path.read_text(encoding="utf-8"))["objects"]
                 if obj.get("type") != "background_image")
    loaded = QGraphicsScene()
    pm.load(loaded, path)
    (item,) = [candidate for candidate in loaded.items() if isinstance(candidate, cls)]
    return loaded, item, saved


@pytest.mark.parametrize("object_type", RECTANGLE_TYPES, ids=lambda t: t.name)
def test_a_recoloured_rectangle_keeps_its_colour_through_load_save_load(
        object_type: ObjectType, qtbot: Any, tmp_path: Path) -> None:
    """The loader set a rectangle's brush and left ``fill_color`` — what the saver,
    the clipboard and the Agent API read — at the type's default. So a recoloured
    rectangle came back right from the file and was written back WRONG by the next
    save: measured on master v1.30.1, ``#ffc81e1e`` became ``#ff90ee90``
    (GENERIC_RECTANGLE), ``#ff64b43c`` (LAWN), ``#ffdeb887`` (TERRACE_PATIO),
    ``#ff8b5a2b`` (GARDEN_BED). Circles, ellipses and polygons never had it.

    Fixed on master by #502 (``core.item_look.restore_stored_look``, pinned there
    by ``test_item_appearance_roundtrip.py``); this branch's own fix gave way to it.
    Kept for its breadth: eleven rectangle types with a pattern, and the clipboard's
    and the Agent API's read of the loaded item."""
    from open_garden_planner.agent_api.queries import _object_detail
    from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
    from open_garden_planner.core.item_look import style_gaps

    pm = ProjectManager()
    item = RectangleItem(10.0, 20.0, 300.0, 200.0, object_type=object_type, name="Recoloured")
    item.fill_pattern = FillPattern.BRICK
    item.fill_color = QColor(RECOLOURED)
    item.setBrush(create_pattern_brush(FillPattern.BRICK, QColor(RECOLOURED)))
    scene = QGraphicsScene()
    scene.addItem(item)
    kept = [scene]
    for turn in ("first", "second"):
        scene, item, saved = _reloaded(pm, scene, tmp_path / f"{turn}.ogp", RectangleItem)
        kept.append(scene)
        assert (saved["fill_color"], saved["fill_pattern"]) == (RECOLOURED, "BRICK"), turn
        assert QColor(item.fill_color).name(QColor.NameFormat.HexArgb) == RECOLOURED, turn
        assert style_gaps(item) == [], turn
        # the other readers of the attribute: the clipboard and the agent (the paint
        # below 40 % zoom read it too, until #503 removed that paint)
        copied = ProjectManager._serialize_item(item)
        assert copied is not None and copied["fill_color"] == RECOLOURED
        assert _object_detail(copied, {}, {}).fill_color == RECOLOURED


def _stroked(cls: Any) -> Any:
    from open_garden_planner.core.object_types import PathFenceStyle

    if cls == "styled path":
        return PolylineItem([QPointF(0.0, 0.0), QPointF(50.0, 50.0), QPointF(100.0, 50.0)],
                            object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.GRAVEL_PATH)
    if cls is CircleItem:  # the sample is a plant — a sprite, no stroke of its own
        return CircleItem(150.0, 150.0, 40.0, object_type=ObjectType.GENERIC_CIRCLE, name="Round")
    return _create_sample_item(cls)


@pytest.mark.parametrize("cls", [RectangleItem, CircleItem, PolygonItem, EllipseItem, PolylineItem,
                                 "styled path"],
                         ids=lambda c: c if isinstance(c, str) else c.__name__)
def test_a_restroked_item_keeps_its_stroke_through_load_save_load(cls: Any, qtbot: Any, tmp_path: Path) -> None:
    """Colour, width and dash style of a stroke set in the properties panel (the
    attribute and the pen, as the panel sets them). Two losses were found here:
    a dashed LINE came back solid (the polyline branch never wrote a stroke
    style), and a line with a style preset came back with the preset's colour and
    width (its saved stroke was read for style NONE only). And for every shape
    the loaded item's stroke ATTRIBUTES were its type's defaults — the properties
    panel showed them, and undoing a change of width put the default back."""
    from open_garden_planner.core.item_look import style_gaps
    from open_garden_planner.core.object_types import PathFenceStyle, StrokeStyle

    pm = ProjectManager()
    item = _stroked(cls)
    item_cls = type(item)
    if isinstance(item, RectangleItem) and item.object_type is ObjectType.RAISED_BED:
        item = RectangleItem(10.0, 20.0, 100.0, 50.0, object_type=ObjectType.GARDEN_BED, name="MyBed")
    dashed = getattr(item, "path_fence_style", PathFenceStyle.NONE) is PathFenceStyle.NONE
    pen = item.pen()
    pen.setColor(QColor("#dc1e50c8"))
    pen.setWidthF(7.5)
    item.stroke_color, item.stroke_width = QColor("#dc1e50c8"), 7.5
    if dashed:
        pen.setStyle(StrokeStyle.DASH_DOT.to_qt_pen_style())
        item.stroke_style = StrokeStyle.DASH_DOT
    item.setPen(pen)
    wanted = ("#dc1e50c8", 7.5, pen.style())
    scene = QGraphicsScene()
    scene.addItem(item)
    kept = [scene]
    for turn in ("first", "second"):
        scene, item, saved = _reloaded(pm, scene, tmp_path / f"{turn}.ogp", item_cls)
        kept.append(scene)
        assert (saved["stroke_color"], saved["stroke_width"]) == wanted[:2], turn
        assert saved.get("stroke_style", "SOLID") == ("DASH_DOT" if dashed else "SOLID"), turn
        live = item.pen()
        assert (live.color().name(QColor.NameFormat.HexArgb), live.widthF(), live.style()) == wanted, turn
        assert (QColor(item.stroke_color).name(QColor.NameFormat.HexArgb), item.stroke_width) == wanted[:2]
        assert style_gaps(item) == [], turn
