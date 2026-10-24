"""Boolean union over a selection, contact, ellipses and one undo step (#550)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu, QMessageBox

from open_garden_planner.core.constraints import AnchorRef, AnchorType
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.shape_boolean import _polygon_area
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    RectangleItem,
)


@pytest.fixture
def confirm(monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Ok
    )


def _view(qtbot) -> tuple[CanvasScene, CanvasView]:
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return scene, view


def _add(scene: CanvasScene, *items):
    layer_id = scene.active_layer.id
    for item in items:
        item.layer_id = layer_id
        scene.addItem(item)
        item.setSelected(True)


def _polygons(scene: CanvasScene) -> list[PolygonItem]:
    return [item for item in scene.items() if isinstance(item, PolygonItem)]


def test_three_shapes_merge_into_one_and_undo_restores_all(qtbot, confirm) -> None:
    scene, view = _view(qtbot)
    rect = RectangleItem(100, 100, 300, 200)
    left = CircleItem(100, 200, 100)
    right = CircleItem(400, 200, 100)
    rect.fill_color = QColor("#123456")
    rect.stroke_color = QColor("#654321")
    rect.fill_pattern = FillPattern.GRAVEL
    rect._setup_styling()  # derive the live brush/pen from the attributes
    rect.metadata["future_field"] = {"keep": True}
    _add(scene, rect, left, right)

    view.boolean_operation("union")

    result = _polygons(scene)[0]
    assert all(item.scene() is None for item in (rect, left, right))
    assert result.metadata["future_field"] == {"keep": True}
    assert result.fill_color == QColor("#123456")
    assert result.stroke_color == QColor("#654321")
    assert result.fill_pattern == FillPattern.GRAVEL
    assert view.command_manager.undo_depth == 1

    view.command_manager.undo()
    assert all(item.scene() is scene for item in (rect, left, right))
    assert rect.metadata["future_field"] == {"keep": True}
    assert not _polygons(scene)

    view.command_manager.redo()
    assert all(item.scene() is None for item in (rect, left, right))
    assert len(_polygons(scene)) == 1


def test_three_shapes_survive_save_and_reopen(qtbot, confirm, tmp_path) -> None:
    scene, view = _view(qtbot)
    rect = RectangleItem(100, 100, 300, 200)
    left = CircleItem(100, 200, 100)
    right = CircleItem(400, 200, 100)
    rect.metadata["future_field"] = {"keep": True}
    _add(scene, rect, left, right)
    view.boolean_operation("union")
    result = _polygons(scene)[0]
    geometry = result.polygon()

    path = tmp_path / "merged.ogp"
    ProjectManager().save(scene, path)
    restored = CanvasScene()
    ProjectManager().load(restored, path)

    polygon = next(item for item in restored.items() if isinstance(item, PolygonItem))
    assert polygon.polygon() == geometry
    assert polygon.metadata["future_field"] == {"keep": True}


def test_touching_rectangles_merge_but_disjoint_ones_are_refused(
    qtbot, monkeypatch
) -> None:
    scene, view = _view(qtbot)
    left = RectangleItem(0, 0, 100, 100)
    right = RectangleItem(100, 0, 100, 100)
    _add(scene, left, right)

    questions = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: questions.append(True) or QMessageBox.StandardButton.Ok,
    )
    view.boolean_operation("union")
    assert questions == [True]
    assert len(_polygons(scene)) == 1
    assert _polygon_area(_polygons(scene)[0].polygon()) == pytest.approx(20000.0, rel=1e-6)

    gap_scene, gap_view = _view(qtbot)
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(300, 0, 100, 100)
    _add(gap_scene, first, second)
    gap_view.boolean_operation("union")
    assert all(item.scene() is gap_scene for item in (first, second))
    assert not _polygons(gap_scene)
    assert gap_view.command_manager.undo_depth == 0


@pytest.mark.parametrize("operation", ["union", "intersect", "subtract"])
def test_ellipse_can_take_part_in_every_operation(qtbot, confirm, operation) -> None:
    scene, view = _view(qtbot)
    ellipse = EllipseItem(0, 0, 120, 80)
    rect = RectangleItem(40, 20, 120, 80)
    _add(scene, ellipse, rect)

    view.boolean_operation(operation)

    assert len(_polygons(scene)) == 1
    assert view.command_manager.undo_depth == 1


def test_three_shapes_offer_only_union_in_the_context_menu(
    qtbot, confirm, monkeypatch
) -> None:
    scene, view = _view(qtbot)
    items = [
        RectangleItem(100, 100, 300, 200),
        CircleItem(100, 200, 100),
        CircleItem(400, 200, 100),
    ]
    _add(scene, *items)
    captured = {}

    def choose_union(menu, *_args):
        submenu = next(
            action.menu()
            for action in menu.actions()
            if action.menu() is not None
            and any(entry.text() == "Union" for entry in action.menu().actions())
        )
        captured["actions"] = [entry.text() for entry in submenu.actions()]
        return submenu.actions()[0]

    monkeypatch.setattr(QMenu, "exec", choose_union)
    items[0].contextMenuEvent(MagicMock(spec=QGraphicsSceneContextMenuEvent))
    assert captured["actions"] == ["Union"]
    assert len(_polygons(scene)) == 1


def test_corner_touching_rectangles_merge(qtbot, confirm) -> None:
    scene, view = _view(qtbot)
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(100, 100, 100, 100)
    _add(scene, first, second)

    view.boolean_operation("union")

    assert len(_polygons(scene)) == 1


def test_a_union_that_would_enclosing_a_hole_is_refused(qtbot, monkeypatch) -> None:
    scene, view = _view(qtbot)
    ring = [
        RectangleItem(0, 0, 300, 20),
        RectangleItem(0, 180, 300, 20),
        RectangleItem(0, 20, 20, 160),
        RectangleItem(280, 20, 20, 160),
    ]
    _add(scene, *ring)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: pytest.fail("a hole-producing union must be refused before confirmation"),
    )
    view.boolean_operation("union")
    assert all(item.scene() is scene for item in ring)
    assert not _polygons(scene)
    assert view.command_manager.undo_depth == 0


def test_a_selection_spanning_layers_is_refused(qtbot, monkeypatch) -> None:
    """One result, one layer: refuse rather than pick an arbitrary subject's."""
    from open_garden_planner.models.layer import Layer

    scene, view = _view(qtbot)
    other = Layer(name="Other", z_order=2)
    scene.add_layer(other)
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(50, 0, 100, 100)
    _add(scene, first, second)
    second.layer_id = other.id

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: pytest.fail("a cross-layer selection must be refused"),
    )
    view.boolean_operation("union")

    assert all(item.scene() is scene for item in (first, second))
    assert not _polygons(scene)
    assert view.command_manager.undo_depth == 0


def test_a_result_over_the_polygon_vertex_cap_is_refused(qtbot, monkeypatch) -> None:
    """A saved polygon above the loader's cap would vanish on reopen (#550).

    ``ProjectManager`` refuses a polygon above ``MAX_POLYGON_VERTICES`` with a
    log line, so a union that flattening pushes over the cap must never reach
    the scene: the user would see it, save it, and lose it on the next open.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPainterPath, QPolygonF

    from open_garden_planner.core import shape_boolean
    from open_garden_planner.ui.canvas.items.polygon_item import (
        MAX_POLYGON_VERTICES,
    )

    scene, view = _view(qtbot)
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(50, 0, 100, 100)
    _add(scene, first, second)

    contour = QPainterPath()
    contour.addRect(0, 0, 150, 100)
    over_cap = QPolygonF(
        [
            QPointF(float(index % 100), float(index // 100))
            for index in range(MAX_POLYGON_VERTICES + 1)
        ]
    )
    monkeypatch.setattr(
        shape_boolean, "union_outline_many", lambda _paths: (contour, over_cap)
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: pytest.fail("an over-cap result must be refused before confirmation"),
    )

    view.boolean_operation("union")

    assert all(item.scene() is scene for item in (first, second))
    assert not _polygons(scene)
    assert view.command_manager.undo_depth == 0


@pytest.mark.parametrize(
    "case", ["plant", "linked", "constrained", "locked", "different_data"]
)
def test_refusal_leaves_the_scene_and_history_unchanged(qtbot, monkeypatch, case) -> None:
    scene, view = _view(qtbot)
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(50, 0, 100, 100)
    _add(scene, first, second)
    if case == "plant":
        second.object_type = ObjectType.TREE
    elif case == "linked":
        first.parent_bed_id = scene.active_layer.id
    elif case == "constrained":
        scene.constraint_graph.add_constraint(
            AnchorRef(first.item_id, AnchorType.CENTER),
            AnchorRef(second.item_id, AnchorType.CENTER),
            200.0,
        )
    elif case == "locked":
        scene.active_layer.locked = True
    elif case == "different_data":
        first.metadata["future_field"] = "a"
        second.metadata["future_field"] = "b"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: pytest.fail("an invalid selection must be refused before confirmation"),
    )
    before = [ProjectManager._serialize_item(item) for item in (first, second)]
    view.boolean_operation("union")

    assert all(item.scene() is scene for item in (first, second))
    assert [ProjectManager._serialize_item(item) for item in (first, second)] == before
    assert not _polygons(scene)
    assert view.command_manager.undo_depth == 0
