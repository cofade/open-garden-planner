"""The label pass lays the labels out when they change, not when they are painted (review, P1-4).

Which labels have room is decided over EVERY label of the scene (a partial
repaint has to choose as a full one does, §8.9.15). Until this fix that
decision was taken again inside every paint — 9 ms on a plan of 853 labelled
objects, for a 40-pixel repaint as for a full one — and every zoom step
painted the whole viewport twice, because the pass answered "the choice
changed" with a full repaint of a viewport that was being repainted in full.

The first class counts (§8.10.10). The second checks that a kept layout does
not outlive what it was taken from: what the canvas paints is compared with a
layout taken fresh (``CanvasScene.plan_labels_shown``), and with pixels.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas import plan_labels
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
from open_garden_planner.ui.canvas.sun_heatmap import SunMapLabelItem
from tests.large_plan import show_large_plan


@pytest.fixture()
def layouts(monkeypatch) -> list[int]:
    """One entry for every time the labels of a scene were laid out."""
    calls: list[int] = []
    real = plan_labels.place_labels

    def counting(candidates, **kwargs):
        calls.append(len(candidates))
        return real(candidates, **kwargs)

    monkeypatch.setattr(plan_labels, "place_labels", counting)
    return calls


@pytest.fixture()
def foreground(monkeypatch) -> list[QRectF]:
    """The rectangle of every pass of the scene's foreground."""
    passes: list[QRectF] = []
    real = CanvasScene.drawForeground

    def counting(self, painter, rect):
        passes.append(QRectF(rect))
        real(self, painter, rect)

    monkeypatch.setattr(CanvasScene, "drawForeground", counting)
    return passes


def _events() -> None:
    for _ in range(5):
        QApplication.processEvents()


class TestLaidOutOncePerChange:
    def test_repaints_at_one_transform_lay_out_nothing(self, qtbot, layouts) -> None:
        view, _scene, _items = show_large_plan(qtbot)
        _events()
        view.viewport().repaint()
        layouts.clear()
        for _ in range(6):
            view.viewport().repaint()
        for corner in ((700, 400), (20, 30), (1200, 700)):
            view.viewport().repaint(QRect(*corner, 40, 40))
        assert layouts == []

    def test_a_pan_lays_out_nothing(self, qtbot, layouts) -> None:
        """Which labels have room does not change when the plan is moved."""
        view, _scene, _items = show_large_plan(qtbot)
        view.set_scale_bar_visible(False)
        view.set_zoom(view.zoom_factor * 1.5)
        _events()
        view.viewport().repaint()
        layouts.clear()
        bar = view.horizontalScrollBar()
        for _ in range(6):
            bar.setValue(bar.value() + 40)
            view.viewport().repaint()
        assert layouts == []

    def test_a_zoom_step_paints_the_foreground_once(self, qtbot, layouts, foreground) -> None:
        view, _scene, _items = show_large_plan(qtbot)
        _events()
        for _ in range(6):
            layouts.clear()
            foreground.clear()
            view.scale(1.03, 1.03)
            _events()
            assert len(foreground) == 1
            assert len(layouts) == 1

    def test_an_edit_lays_out_once(self, qtbot, layouts) -> None:
        view, _scene, items = show_large_plan(qtbot)
        _events()
        view.viewport().repaint()
        layouts.clear()
        items[3].setPos(items[3].pos() + QPointF(40.0, 25.0))
        _events()
        for _ in range(4):
            view.viewport().repaint()
        assert len(layouts) == 1

    def test_a_picture_of_the_plan_is_laid_out_for_itself(self, qtbot, layouts) -> None:
        """An export is never served from what a viewport kept."""
        from PyQt6.QtGui import QPainter

        from open_garden_planner.services.scene_rendering import render_scene_region

        view, scene, _items = show_large_plan(qtbot, 60)
        _events()
        layouts.clear()
        for _ in range(2):
            image = QImage(900, 540, QImage.Format.Format_RGB32)
            painter = QPainter(image)
            render_scene_region(scene, painter, QRectF(0, 0, 900, 540), scene.canvas_rect)
            painter.end()
        assert len(layouts) == 2
        view.viewport().repaint()


# --------------------------------------------------------------------------
# What is painted is what a fresh layout says
# --------------------------------------------------------------------------


@pytest.fixture()
def painted(monkeypatch) -> list[PlanLabelItem]:
    """Every label the canvas painted since the list was last cleared."""
    drawn: list[PlanLabelItem] = []
    real = PlanLabelItem.paint_text

    def recording(self, painter, option=None, widget=None):
        drawn.append(self)
        real(self, painter, option, widget)

    monkeypatch.setattr(PlanLabelItem, "paint_text", recording)
    return drawn


@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(5000, 3000)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    view.fit_in_view()
    _events()
    return view, scene


def _repainted(view: CanvasView, painted: list[PlanLabelItem]) -> set[str]:
    """The texts a full repaint of the viewport paints."""
    _events()
    painted.clear()
    view.viewport().repaint()
    return {label.text() for label in painted}


def _fresh(view: CanvasView, scene: CanvasScene) -> set[str]:
    """The texts a layout taken now says are shown."""
    return {label.text() for label, _d, _b in scene.plan_labels_shown(view.viewportTransform())}


def _bed(scene: CanvasScene, x: float, y: float, name: str) -> RectangleItem:
    bed = RectangleItem(x, y, 700, 400, object_type=ObjectType.RAISED_BED, name=name)
    scene.addItem(bed)
    bed.initialize_label()
    return bed


class TestTheKeptLayoutFollowsTheScene:
    def test_a_rename(self, canvas, painted) -> None:
        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        assert _repainted(view, painted) == {"Herbs"}
        bed.name = "Salad"
        assert _repainted(view, painted) == {"Salad"} == _fresh(view, scene)

    def test_a_selection(self, canvas, painted) -> None:
        """A plant too small on screen for its name shows it while selected."""
        view, scene = canvas
        plant = CircleItem(2500, 1500, 20, object_type=ObjectType.PERENNIAL, name="Sage")
        scene.addItem(plant)
        plant.initialize_label()
        assert _repainted(view, painted) == set()
        plant.setSelected(True)
        assert _repainted(view, painted) == {"Sage"} == _fresh(view, scene)
        plant.setSelected(False)
        assert _repainted(view, painted) == set() == _fresh(view, scene)

    def test_labels_switched_off_and_on(self, canvas, painted) -> None:
        """Hiding a label that ignores the view's transformations emits no
        ``changed``: the label says so itself."""
        view, scene = canvas
        _bed(scene, 1000, 1000, "Herbs")
        _bed(scene, 3000, 1000, "Salad")
        assert _repainted(view, painted) == {"Herbs", "Salad"}
        scene.set_labels_visible(False)
        assert _repainted(view, painted) == set()
        scene.set_labels_visible(True)
        assert _repainted(view, painted) == {"Herbs", "Salad"}

    def test_one_objects_label_switched_off(self, canvas, painted) -> None:
        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        _bed(scene, 3000, 1000, "Salad")
        assert _repainted(view, painted) == {"Herbs", "Salad"}
        bed.label_visible = False
        assert _repainted(view, painted) == {"Salad"}
        bed.label_visible = True
        assert _repainted(view, painted) == {"Herbs", "Salad"}

    def test_an_area_label_switched_on(self, canvas, painted) -> None:
        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        assert _repainted(view, painted) == {"Herbs"}
        bed.area_label_visible = True
        shown = _repainted(view, painted)
        assert len(shown) == 2 and shown == _fresh(view, scene)
        bed.area_label_visible = False
        assert _repainted(view, painted) == {"Herbs"}

    def test_an_object_removed_and_one_added(self, canvas, painted) -> None:
        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        assert _repainted(view, painted) == {"Herbs"}
        scene.removeItem(bed)
        painted.clear()
        view.viewport().repaint()                  # at once: no event loop in between
        assert painted == []
        _bed(scene, 3000, 1000, "Salad")
        painted.clear()
        view.viewport().repaint()
        assert {label.text() for label in painted} == {"Salad"}

    def test_a_cleared_scene(self, canvas, painted) -> None:
        view, scene = canvas
        _bed(scene, 1000, 1000, "Herbs")
        assert _repainted(view, painted) == {"Herbs"}
        scene.clear()
        painted.clear()
        view.viewport().repaint()                  # the kept labels are gone with the scene
        assert painted == []

    def test_a_layer_switched_off(self, canvas, painted) -> None:
        from open_garden_planner.models.layer import Layer

        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        layer = Layer(name="Beds")
        scene.add_layer(layer)
        bed.layer_id = layer.id
        assert _repainted(view, painted) == {"Herbs"}
        scene.update_layer_visibility(layer.id, False)
        assert _repainted(view, painted) == set()
        scene.update_layer_visibility(layer.id, True)
        assert _repainted(view, painted) == {"Herbs"}

    def test_an_hour_of_the_sun_map_hidden_and_shown(self, canvas, painted) -> None:
        view, scene = canvas
        hour = SunMapLabelItem("6 h")
        hour.setPos(1000.0, 1500.0)
        scene.addItem(hour)
        assert _repainted(view, painted) == {"6 h"}
        hour.setVisible(False)
        assert _repainted(view, painted) == set()
        hour.setVisible(True)
        assert _repainted(view, painted) == {"6 h"}
        hour.setText("7 h")
        assert _repainted(view, painted) == {"7 h"}

    def test_a_blocker_stated_by_the_view(self, canvas, painted) -> None:
        view, scene = canvas
        bed = _bed(scene, 1000, 1000, "Herbs")
        assert _repainted(view, painted) == {"Herbs"}
        world = view.viewportTransform()
        box = bed._label_item.deviceTransform(world).mapRect(bed._label_item.boundingRect())
        scene.set_label_blockers(view.viewport(), [box])
        assert _repainted(view, painted) == set()
        scene.set_label_blockers(view.viewport(), [])
        assert _repainted(view, painted) == {"Herbs"}

    def test_two_views_of_one_scene_each_keep_their_own(self, canvas, painted, qtbot) -> None:
        view, scene = canvas
        plant = CircleItem(2500, 1500, 40, object_type=ObjectType.PERENNIAL, name="Sage")
        scene.addItem(plant)
        plant.initialize_label()
        close = CanvasView(scene)
        qtbot.addWidget(close)
        close.resize(600, 400)
        close.show()
        qtbot.waitExposed(close)
        close.set_zoom(1.0)
        close.centerOn(2500, 1500)
        for _ in range(2):
            assert _repainted(view, painted) == _fresh(view, scene)
            assert _repainted(close, painted) == _fresh(close, scene) == {"Sage"}

    def test_a_large_plan_paints_what_a_fresh_layout_says(self, qtbot, painted) -> None:
        """Through zoom steps, pans and an edit, without a full relayout in
        between: the labels on the canvas are the labels of a fresh layout."""
        view, scene, items = show_large_plan(qtbot, 300)
        view.set_scale_bar_visible(False)

        def check() -> None:
            _events()
            painted.clear()
            view.viewport().repaint()
            world = view.viewportTransform()
            seen = QRectF(view.viewport().rect())
            expected = {
                id(label) for label, _d, box in scene.plan_labels_shown(world) if box.intersects(seen)
            }
            assert {id(label) for label in painted} == expected
            assert len(expected) > 5

        check()
        view.set_zoom(view.zoom_factor * 1.4)
        check()
        bar = view.horizontalScrollBar()
        bar.setValue(bar.value() + 130)
        check()
        bar.setValue(bar.value() - 55)
        view.verticalScrollBar().setValue(view.verticalScrollBar().value() + 37)
        check()
        items[5].setPos(items[5].pos() + QPointF(300.0, 0.0))
        check()
        items[9].setSelected(True)
        check()


# --------------------------------------------------------------------------
# Pixels: no label is left on the canvas, and none is missing
# --------------------------------------------------------------------------


def _on_screen(view: CanvasView) -> QImage:
    """The viewport's pixels as they are on the screen now.

    The window's backing store, not ``QWidget.grab()``: a grab paints the
    widget afresh and in full, so it can never show a pixel that a partial
    repaint left behind — which is what these tests are about.
    """
    _events()
    window = view.screen().grabWindow(view.winId()).toImage()
    viewport = view.viewport()
    corner = viewport.mapTo(view, QPoint(0, 0))
    return window.copy(
        corner.x(), corner.y(), viewport.width(), viewport.height()
    ).convertToFormat(QImage.Format.Format_RGB32)


def _differ(a: QImage, b: QImage, box: QRectF) -> int:
    area = box.toAlignedRect().intersected(a.rect())
    return sum(
        1
        for y in range(area.top(), area.bottom() + 1)
        for x in range(area.left(), area.right() + 1)
        if a.pixel(x, y) != b.pixel(x, y)
    )


class TestNoStalePixels:
    def test_a_label_that_gains_room_is_painted_where_nothing_else_was_repainted(self, canvas) -> None:
        """Two beds whose names would touch: the larger one's is shown. When it
        is taken away the other name has room — and that name lies outside
        everything the removal repaints."""
        view, scene = canvas
        small = RectangleItem(2000, 1400, 150, 120, object_type=ObjectType.RAISED_BED,
                              name="A long name of a small bed")
        scene.addItem(small)
        small.initialize_label()
        large = RectangleItem(2200, 1380, 160, 160, object_type=ObjectType.RAISED_BED,
                              name="The larger bed beside it")
        scene.addItem(large)
        large.initialize_label()
        world = view.viewportTransform()
        shown = {label.text() for label, _d, _b in scene.plan_labels_shown(world)}
        assert shown == {"The larger bed beside it"}, "the two names do not compete: " + repr(shown)
        box = small._label_item.deviceTransform(world).mapRect(small._label_item.boundingRect())
        other = large._label_item.deviceTransform(world).mapRect(large._label_item.boundingRect())
        # the start of the freed name: clear of the label that goes
        start = QRectF(box.left(), box.top(), 40.0, box.height())
        assert not start.intersects(other.adjusted(-4.0, -4.0, 4.0, 4.0))
        before = _on_screen(view)

        large.label_visible = False                   # only the larger bed's label goes
        after = _on_screen(view)                      # the event loop painted, nobody else
        assert _differ(before, after, start) > 20, "the freed name was not painted"

    def test_a_label_that_loses_its_room_leaves_no_pixels(self, canvas) -> None:
        view, scene = canvas
        small = RectangleItem(2000, 1400, 150, 120, object_type=ObjectType.RAISED_BED,
                              name="A long name of a small bed")
        scene.addItem(small)
        small.initialize_label()
        large = RectangleItem(2200, 1380, 160, 160, object_type=ObjectType.RAISED_BED,
                              name="The larger bed beside it")
        scene.addItem(large)
        large.initialize_label()
        large.label_visible = False
        world = view.viewportTransform()
        box = small._label_item.deviceTransform(world).mapRect(small._label_item.boundingRect())
        start = QRectF(box.left(), box.top(), 40.0, box.height())
        with_name = _on_screen(view)
        small.label_visible = False
        bare = _on_screen(view)
        small.label_visible = True
        assert _differ(_on_screen(view), bare, start) > 20        # the name is there
        assert _differ(_on_screen(view), with_name, start) == 0

        large.label_visible = True                    # ... and now has to give way
        after = _on_screen(view)
        other = large._label_item.deviceTransform(world).mapRect(large._label_item.boundingRect())
        assert not start.intersects(other.adjusted(-4.0, -4.0, 4.0, 4.0))
        assert _differ(after, bare, start) == 0, "pixels of a label that lost its room"
