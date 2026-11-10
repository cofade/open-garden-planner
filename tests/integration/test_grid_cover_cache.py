"""The grid's cut-out is built when the plan changes, not when it is painted (review, P1-2).

The canvas grid is painted after the items and must read as lying under them,
so every standing object is cut out of it (§8.9.17). Until this fix the view
asked every object for what it covers on EVERY paint and united one region per
object in Python: 70 ms of a 120 ms repaint on a plan of 853 objects.

What stands on the plan is a fact of the scene. The scene keeps it, in plan
coordinates, until something changes; a paint, a pan and a zoom read it.

The first class counts (§8.10.10: a count holds on any machine). The second
looks at pixels: a kept answer must not outlive the plan it was taken from.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.commands import MoveItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from tests.large_plan import LARGE_PLAN_ITEMS, show_large_plan


@pytest.fixture()
def cover_calls(monkeypatch) -> list[int]:
    """One entry for every object asked what it covers of the plan."""
    calls: list[int] = []
    for cls in (CircleItem, RectangleItem):
        real = cls.grid_cover_path

        def counting(self, _real=real):
            calls.append(1)
            return _real(self)

        monkeypatch.setattr(cls, "grid_cover_path", counting)
    return calls


class TestBuiltOncePerChange:
    def test_paints_pans_and_zooms_ask_no_object_again(self, qtbot, cover_calls) -> None:
        view, _scene, _items = show_large_plan(qtbot)
        view.set_grid_visible(True)
        QApplication.processEvents()
        view.viewport().repaint()
        assert len(cover_calls) == LARGE_PLAN_ITEMS      # every object, once
        cover_calls.clear()

        for _ in range(5):
            view.viewport().repaint()
        bar = view.horizontalScrollBar()
        view.set_zoom(view.zoom_factor * 1.5)            # something to scroll
        view.viewport().repaint()
        for _ in range(5):
            bar.setValue(bar.value() + 40)
            view.viewport().repaint()
        for _ in range(5):
            view.set_zoom(view.zoom_factor * 1.1)
            view.viewport().repaint()
        QApplication.processEvents()
        view.viewport().repaint()
        assert len(cover_calls) == 0

    def test_an_edit_asks_every_object_once(self, qtbot, cover_calls) -> None:
        view, _scene, items = show_large_plan(qtbot)
        view.set_grid_visible(True)
        QApplication.processEvents()
        view.viewport().repaint()
        cover_calls.clear()

        items[3].setPos(items[3].pos() + QPointF(40.0, 25.0))
        QApplication.processEvents()
        for _ in range(4):
            view.viewport().repaint()
        assert len(cover_calls) == LARGE_PLAN_ITEMS

    def test_with_the_grid_off_nothing_is_built(self, qtbot, cover_calls) -> None:
        view, _scene, items = show_large_plan(qtbot)
        view.set_grid_visible(False)
        cover_calls.clear()
        items[3].setPos(items[3].pos() + QPointF(40.0, 25.0))
        QApplication.processEvents()
        view.viewport().repaint()
        assert len(cover_calls) == 0


# --------------------------------------------------------------------------
# Pixels
# --------------------------------------------------------------------------


def _grab(view: CanvasView) -> QImage:
    QApplication.processEvents()
    return view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _grid_pixels(view: CanvasView) -> set[tuple[int, int]]:
    """The viewport pixels the grid changes."""
    view.set_grid_visible(True)
    with_grid = _grab(view)
    view.set_grid_visible(False)
    without = _grab(view)
    view.set_grid_visible(True)
    return {
        (x, y)
        for y in range(with_grid.height())
        for x in range(with_grid.width())
        if with_grid.pixel(x, y) != without.pixel(x, y)
    }


def _on_disc(view: CanvasView, pixels: set[tuple[int, int]], centre: QPointF, radius_cm: float) -> int:
    """Grid pixels inside the disc round ``centre`` (2 px inside its edge)."""
    middle = view.mapFromScene(centre)
    radius = radius_cm * view.zoom_factor - 2.0
    return sum(
        1 for x, y in pixels if (x - middle.x()) ** 2 + (y - middle.y()) ** 2 < radius ** 2
    )


TREE_AT = QPointF(700.0, 400.0)
TREE_RADIUS = 110.0


@pytest.fixture()
def garden(qtbot):
    scene = CanvasScene(1000, 800)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    lawn = PolygonItem(
        [QPointF(0, 0), QPointF(450, 0), QPointF(450, 800), QPointF(0, 800)],
        object_type=ObjectType.LAWN,
    )
    scene.addItem(lawn)
    tree = CircleItem(TREE_AT.x(), TREE_AT.y(), TREE_RADIUS, object_type=ObjectType.TREE)
    scene.addItem(tree)
    view.set_zoom(0.6)
    view.centerOn(500, 400)
    view.set_grid_visible(True)
    pixels = _grid_pixels(view)            # the first paint keeps the cut-out
    assert _on_disc(view, pixels, TREE_AT, TREE_RADIUS) == 0
    assert len(pixels) > 500
    return view, scene, tree


class TestTheKeptCutOutFollowsThePlan:
    def test_a_move(self, garden) -> None:
        view, _scene, tree = garden
        tree.setPos(0.0, 250.0)                           # now centred on (700, 650)
        pixels = _grid_pixels(view)
        assert _on_disc(view, pixels, TREE_AT, 50.0) > 5
        assert _on_disc(view, pixels, QPointF(700.0, 650.0), TREE_RADIUS) == 0

    def test_a_hidden_object_and_one_shown_again(self, garden) -> None:
        view, _scene, tree = garden
        tree.setVisible(False)
        assert _on_disc(view, _grid_pixels(view), TREE_AT, 50.0) > 5
        tree.setVisible(True)
        assert _on_disc(view, _grid_pixels(view), TREE_AT, TREE_RADIUS) == 0

    def test_a_layer_switched_off_and_on(self, garden) -> None:
        view, scene, tree = garden
        layer = Layer(name="Trees")
        scene.add_layer(layer)
        tree.layer_id = layer.id
        scene.update_layer_visibility(layer.id, False)
        assert not tree.isVisible()
        assert _on_disc(view, _grid_pixels(view), TREE_AT, 50.0) > 5
        scene.update_layer_visibility(layer.id, True)
        assert _on_disc(view, _grid_pixels(view), TREE_AT, TREE_RADIUS) == 0

    def test_an_undo_and_a_redo(self, garden) -> None:
        view, _scene, tree = garden
        manager = view.command_manager
        manager.execute(MoveItemsCommand([tree], QPointF(0.0, 250.0)))
        moved = QPointF(700.0, 650.0)
        pixels = _grid_pixels(view)
        assert _on_disc(view, pixels, moved, TREE_RADIUS) == 0
        assert _on_disc(view, pixels, TREE_AT, 50.0) > 5
        manager.undo()
        pixels = _grid_pixels(view)
        assert _on_disc(view, pixels, TREE_AT, TREE_RADIUS) == 0
        assert _on_disc(view, pixels, moved, 50.0) > 5
        manager.redo()
        pixels = _grid_pixels(view)
        assert _on_disc(view, pixels, moved, TREE_RADIUS) == 0

    def test_an_object_added_and_one_removed(self, garden) -> None:
        view, scene, _tree = garden
        shed = RectangleItem(520, 80, 200, 140, object_type=ObjectType.GARAGE_SHED)
        scene.addItem(shed)
        box = view.mapFromScene(QRectF(520, 80, 200, 140)).boundingRect().adjusted(3, 3, -3, -3)
        assert not [p for p in _grid_pixels(view) if box.contains(*p)]
        scene.removeItem(shed)
        assert len([p for p in _grid_pixels(view) if box.contains(*p)]) > 5

    def test_an_object_that_becomes_a_ground_surface(self, garden) -> None:
        """A terrace is ground: the grid lies on it. What an object IS can
        change without the object moving."""
        view, _scene, tree = garden
        tree.object_type = ObjectType.POND_POOL
        tree.update()
        on_pond = _on_disc(view, _grid_pixels(view), TREE_AT, 50.0)
        tree.object_type = ObjectType.TREE
        tree.update()
        on_tree = _on_disc(view, _grid_pixels(view), TREE_AT, TREE_RADIUS)
        assert on_tree == 0
        assert on_pond > 5

    def test_the_plan_made_larger(self, garden) -> None:
        view, scene, _tree = garden
        beyond = QRectF(1020, 300, 150, 200)              # east of the old plan
        box = view.mapFromScene(beyond).boundingRect()
        assert not [p for p in _grid_pixels(view) if box.contains(*p)]
        scene.resize_canvas(1200, 800)
        assert len([p for p in _grid_pixels(view) if box.contains(*p)]) > 5

    def test_a_pan_and_a_zoom_keep_the_cut_out_on_the_object(self, garden) -> None:
        view, _scene, _tree = garden
        for zoom, centre in ((0.6, (560, 430)), (1.3, (640, 380)), (0.4, (500, 400))):
            view.set_zoom(zoom)
            view.centerOn(*centre)
            pixels = _grid_pixels(view)
            assert len(pixels) > 300
            assert _on_disc(view, pixels, TREE_AT, TREE_RADIUS) == 0
