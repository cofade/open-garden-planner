"""Geometry-identity regressions (#657, #661, #668).

Three different ways this codebase has lost an object's *identity or frame*:

* #657 â€” an interactive circle resize recomputed the derived centre as
  ``width/2, height/2`` although the circle's rect has a non-zero origin.
* #661 â€” a rotated shape inside a group was serialized in a frame that only
  existed because of Qt's reparent compensation, so it moved on reload.
* #668 â€” chamfer/fillet replaced a named bed with a new UUID, orphaning its
  name, metadata, plant links, garden records and constraints.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.resize_handle import ResizeHandle

_ROTATIONS = [0.0, 30.0, 90.0, 215.0]


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=8000, height_cm=6000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _resize_handles(item) -> list[ResizeHandle]:
    return [child for child in item.childItems() if isinstance(child, ResizeHandle)]


def _drag_handle(handle: ResizeHandle, delta: QPointF) -> None:
    """A real press / move / release on a resize handle (no view transform needed)."""
    start = handle.scenePos()
    mouse = MagicMock()
    mouse.button.return_value = Qt.MouseButton.LeftButton
    mouse.buttons.return_value = Qt.MouseButton.LeftButton
    mouse.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    mouse.scenePos.return_value = start
    handle.mousePressEvent(mouse)
    mouse.scenePos.return_value = start + delta / 2.0
    handle.mouseMoveEvent(mouse)
    mouse.scenePos.return_value = start + delta
    handle.mouseMoveEvent(mouse)
    handle.mouseReleaseEvent(mouse)


# â”€â”€ #657: a handle resize must not displace the stored circle centre â”€â”€â”€â”€â”€â”€


@pytest.mark.parametrize("rotation", _ROTATIONS)
@pytest.mark.parametrize("handle_index", [0, 1, 2, 3, 4, 5, 6, 7])
def test_circle_handle_resize_keeps_centre_and_rect_in_step(
    canvas: CanvasView, qtbot: object, rotation: float, handle_index: int
) -> None:
    scene = canvas.scene()
    item = CircleItem(500.0, 500.0, 100.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(item)
    item.setSelected(True)
    item._apply_rotation(rotation)

    handles = _resize_handles(item)
    assert len(handles) == 8, "a circle offers four corner and four edge handles"
    _drag_handle(handles[handle_index], QPointF(24.0, 18.0))

    assert item.center == item.rect().center(), (
        f"stored centre {item.center} != rect centre {item.rect().center()} "
        f"(rotation {rotation}, handle {handle_index})"
    )
    serialized_centre = QPointF(
        item.pos().x() + item.center.x(), item.pos().y() + item.center.y()
    )
    visible_centre = item.mapToScene(item.rect().center())
    assert serialized_centre == visible_centre, (
        "the centre the serializer writes must be the centre the user sees"
    )


@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_circle_handle_resize_survives_save_and_reload(
    canvas: CanvasView, tmp_path, qtbot: object, rotation: float
) -> None:
    from open_garden_planner.core.project import ProjectManager

    scene = canvas.scene()
    item = CircleItem(500.0, 500.0, 100.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(item)
    item.setSelected(True)
    item._apply_rotation(rotation)
    _drag_handle(_resize_handles(item)[0], QPointF(30.0, 30.0))
    visible_before = item.mapToScene(item.rect().center())

    path = tmp_path / "circle.ogp"
    ProjectManager().save(scene, path)

    loaded_scene = CanvasScene(width_cm=8000, height_cm=6000)
    ProjectManager().load(loaded_scene, path)
    loaded = next(
        entry for entry in loaded_scene.items() if isinstance(entry, CircleItem)
    )
    visible_after = loaded.mapToScene(loaded.rect().center())

    drift = math.hypot(
        visible_after.x() - visible_before.x(), visible_after.y() - visible_before.y()
    )
    assert drift < 1e-6, (
        f"the circle jumped {drift:.3f} cm on reload (rotation {rotation})"
    )


@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_ellipse_handle_resize_is_the_control(
    canvas: CanvasView, qtbot: object, rotation: float
) -> None:
    """EllipseItem stores no derived centre; its rect frame must stay authoritative."""
    scene = canvas.scene()
    item = EllipseItem(400.0, 300.0, 120.0, 80.0)
    scene.addItem(item)
    item.setSelected(True)
    item._apply_rotation(rotation)

    _drag_handle(_resize_handles(item)[0], QPointF(20.0, 20.0))

    serialized_centre = QPointF(
        item.pos().x() + item.rect().center().x(),
        item.pos().y() + item.rect().center().y(),
    )
    assert serialized_centre == item.mapToScene(item.rect().center())


# â”€â”€ #661: a rotated shape inside a group must round-trip in its own frame â”€â”€


def _shape(kind: str):
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if kind == "rectangle":
        return RectangleItem(100.0, 100.0, 120.0, 60.0)
    if kind == "circle":
        return CircleItem(160.0, 130.0, 60.0, object_type=ObjectType.GENERIC_CIRCLE)
    if kind == "ellipse":
        return EllipseItem(100.0, 100.0, 120.0, 60.0)
    if kind == "polygon":
        return PolygonItem([QPointF(100, 100), QPointF(220, 130), QPointF(170, 190)])
    if kind == "polyline":
        return PolylineItem(
            [QPointF(100, 100), QPointF(220, 130), QPointF(170, 190)],
            object_type=ObjectType.FENCE,
        )
    raise AssertionError(kind)


def _shape_centre(item) -> QPointF:
    if hasattr(item, "rect"):
        local = item.rect().center()
    elif hasattr(item, "polygon"):
        local = item.polygon().boundingRect().center()
    else:
        local = item.boundingRect().center()
    return item.mapToScene(local)


@pytest.mark.parametrize(
    "kind", ["rectangle", "circle", "ellipse", "polygon", "polyline"]
)
@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_rotated_grouped_shape_round_trips(
    canvas: CanvasView, tmp_path, qtbot: object, kind: str, rotation: float
) -> None:
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.core.project import ProjectManager

    scene = canvas.scene()
    shape = _shape(kind)
    scene.addItem(shape)
    shape._apply_rotation(rotation)
    companion = CircleItem(800.0, 600.0, 40.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(companion)

    GroupCommand(scene, [shape, companion]).execute()
    group = next(item for item in scene.items() if item.__class__.__name__ == "GroupItem")
    group.setPos(group.pos() + QPointF(50.0, 40.0))

    centre_before = _shape_centre(shape)
    bounds_before = shape.mapToScene(shape.boundingRect()).boundingRect()
    shape_id = shape.item_id

    path = tmp_path / f"group-{kind}.ogp"
    ProjectManager().save(scene, path)

    loaded_scene = CanvasScene(width_cm=8000, height_cm=6000)
    ProjectManager().load(loaded_scene, path)
    loaded = loaded_scene.find_item_by_id(shape_id)
    assert loaded is not None, f"the {kind} did not come back at all"

    centre_after = _shape_centre(loaded)
    bounds_after = loaded.mapToScene(loaded.boundingRect()).boundingRect()
    assert centre_after.x() == pytest.approx(centre_before.x(), abs=1e-6), (
        f"{kind} at rotation {rotation}: scene centre moved on reload"
    )
    assert centre_after.y() == pytest.approx(centre_before.y(), abs=1e-6)
    for got, want, edge in (
        (bounds_after.left(), bounds_before.left(), "left"),
        (bounds_after.top(), bounds_before.top(), "top"),
        (bounds_after.right(), bounds_before.right(), "right"),
        (bounds_after.bottom(), bounds_before.bottom(), "bottom"),
    ):
        assert got == pytest.approx(want, abs=1e-6), (
            f"{kind} at rotation {rotation}: {edge} bound moved on reload"
        )

    # A second save/reload must not drift further (the error used to compound).
    second = tmp_path / f"group-{kind}-again.ogp"
    ProjectManager().save(loaded_scene, second)
    reloaded_scene = CanvasScene(width_cm=8000, height_cm=6000)
    ProjectManager().load(reloaded_scene, second)
    twice = reloaded_scene.find_item_by_id(shape_id)
    assert twice is not None
    assert _shape_centre(twice).x() == pytest.approx(centre_before.x(), abs=1e-6)
    assert _shape_centre(twice).y() == pytest.approx(centre_before.y(), abs=1e-6)


# â”€â”€ #668: a corner edit must keep the bed's identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _a_referenced_bed(scene):
    """A named raised bed with a plant, metadata and all three log types."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    bed = PolygonItem(
        [
            QPointF(400, 400),
            QPointF(800, 400),
            QPointF(800, 700),
            QPointF(400, 700),
        ],
        object_type=ObjectType.RAISED_BED,
    )
    bed.name = "Bed A"
    bed.metadata["garden_tracking"] = {"zone_id": str(bed.item_id)}
    scene.addItem(bed)

    plant = CircleItem(500.0, 500.0, 20.0, object_type=ObjectType.TREE)
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    return bed, plant


class _Records:
    """The garden records keyed by bed UUID, as the ProjectData holds them."""

    def __init__(self, bed_id) -> None:
        self.soil = {str(bed_id): {"records": [{"ph": 6.5}]}}
        self.pest = {str(bed_id): [{"pest": "aphid"}]}
        self.harvest = {str(bed_id): [{"crop": "tomato"}]}


@pytest.mark.parametrize("tool_name", ["chamfer", "fillet"])
def test_corner_edit_keeps_the_bed_identity(
    canvas: CanvasView, qtbot: object, tool_name: str
) -> None:
    """The real tool path: the bed must survive with its UUID and records."""
    from open_garden_planner.core.tools.chamfer_tool import ChamferTool
    from open_garden_planner.core.tools.corner_edit_base import find_nearest_corner
    from open_garden_planner.core.tools.fillet_tool import FilletTool

    scene = canvas.scene()
    bed, plant = _a_referenced_bed(scene)
    records = _Records(bed.item_id)
    old_id = bed.item_id

    target = find_nearest_corner(canvas, QPointF(400.0, 400.0))
    assert target is not None and target.item is bed
    tool = ChamferTool(canvas) if tool_name == "chamfer" else FilletTool(canvas)
    tool.apply_to_target(target)

    replacements = [
        item
        for item in scene.items()
        if getattr(item, "item_id", None) == old_id and item is not bed
    ]
    assert bed.scene() is None, "the original bed must be replaced"
    assert len(replacements) == 1, "exactly one replacement must carry the UUID"
    new_item = replacements[0]
    assert new_item.name == "Bed A"
    assert new_item.metadata == {"garden_tracking": {"zone_id": str(old_id)}}
    assert new_item.metadata is not bed.metadata, "metadata must be a copy"
    assert str(new_item.item_id) in records.soil
    assert str(new_item.item_id) in records.pest
    assert str(new_item.item_id) in records.harvest
    assert plant.parent_bed_id == new_item.item_id, "the plant lost its parent"
    assert plant.item_id in new_item.child_item_ids

    # Undo/redo must also keep identity, not alternate between two objects.
    canvas.command_manager.undo()
    assert bed.scene() is scene and bed.item_id == old_id
    canvas.command_manager.redo()
    assert new_item.scene() is scene and new_item.item_id == old_id
    assert new_item.name == "Bed A"
    assert plant.parent_bed_id == old_id


def test_trim_keeps_the_bed_identity(canvas: CanvasView, qtbot: object) -> None:
    """A trim replaces the shape too, so it must keep the referenced UUID."""
    from open_garden_planner.core.tools.trim_tool import TrimExtendTool, _TrimTarget
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

    scene = canvas.scene()
    bed, plant = _a_referenced_bed(scene)
    old_id = bed.item_id
    records = _Records(old_id)

    tool = TrimExtendTool(canvas)
    target = _TrimTarget(
        item=bed,
        seg_index=0,  # the top edge, from (400, 400) to (800, 400)
        t_start=0.3,
        t_end=0.7,
        p1_scene=QPointF(400.0, 400.0),
        p2_scene=QPointF(800.0, 400.0),
    )
    tool._trim_polygon(target)

    assert bed.scene() is None
    trimmed = next(
        item
        for item in scene.items()
        if isinstance(item, PolylineItem) and item.item_id == old_id
    )
    assert trimmed.name == "Bed A"
    assert trimmed.metadata == {"garden_tracking": {"zone_id": str(old_id)}}
    assert plant.parent_bed_id == old_id
    assert plant.item_id in trimmed.child_item_ids
    assert str(trimmed.item_id) in records.soil
    # The open shape stays where the bed was, not at the scene origin (an
    # unrotated bed drawn at 400/400 has pos (0, 0), so the check that matters
    # is that every point is still inside the bed's old bounds).
    scene_points = [trimmed.mapToScene(point) for point in trimmed.points]
    assert all(399.0 <= point.x() <= 801.0 for point in scene_points)
    assert all(399.0 <= point.y() <= 701.0 for point in scene_points)

