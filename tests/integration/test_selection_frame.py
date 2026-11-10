"""#790 - selection handles sit on the object's own outline; its two labels never overlap.

Before: a handle read ``boundingRect()``, the repaint region, which holds the drop
shadow, a plant sprite's leaf overflow, a warning badge and the spacing ring. A
magnolia drawn 2.20 m wide showed its eight handles on an 8.64 m box while its
spacing ring was shown, and a badge pushed them off-centre. The position label was
anchored at the plant's centre and the diameter label at its edge, so on a plant
narrower on screen than the position text the two ran into each other.

Driven on the real ``CanvasView`` and scene, by selecting the item.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    RectangleItem,
)
from open_garden_planner.ui.canvas.items.resize_handle import (
    HandlePosition,
    ResizeHandle,
    RotationHandle,
)

EXAMPLES = Path(__file__).parents[2] / "src/open_garden_planner/resources/examples"


@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(3000, 2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    return view, scene


def _tree(scene: CanvasScene, x: float, y: float, footprint: float, spread: float) -> CircleItem:
    plant = CircleItem(x, y, footprint, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"common_name": "Magnolia", "max_spread_cm": spread}
    scene.addItem(plant)
    return plant


def _frame_points(rect: QRectF) -> dict[HandlePosition, QPointF]:
    centre = rect.center()
    return {
        HandlePosition.TOP_LEFT: QPointF(rect.left(), rect.top()),
        HandlePosition.TOP_CENTER: QPointF(centre.x(), rect.top()),
        HandlePosition.TOP_RIGHT: QPointF(rect.right(), rect.top()),
        HandlePosition.MIDDLE_LEFT: QPointF(rect.left(), centre.y()),
        HandlePosition.MIDDLE_RIGHT: QPointF(rect.right(), centre.y()),
        HandlePosition.BOTTOM_LEFT: QPointF(rect.left(), rect.bottom()),
        HandlePosition.BOTTOM_CENTER: QPointF(centre.x(), rect.bottom()),
        HandlePosition.BOTTOM_RIGHT: QPointF(rect.right(), rect.bottom()),
    }


def _assert_handles_on(item, outline: QRectF) -> None:
    handles = [child for child in item.childItems() if isinstance(child, ResizeHandle)]
    assert len(handles) == 8
    expected = _frame_points(outline)
    for handle in handles:
        want = item.mapToScene(expected[handle.handle_position])
        got = handle.scenePos()
        assert got.x() == pytest.approx(want.x(), abs=1e-6), handle.handle_position
        assert got.y() == pytest.approx(want.y(), abs=1e-6), handle.handle_position


@pytest.mark.parametrize("rotation", [0.0, 37.0, 215.0])
@pytest.mark.parametrize("rings", [True, False], ids=["rings-on", "rings-off"])
@pytest.mark.parametrize("state", ["overlap", "ideal", None])
def test_a_plants_handles_sit_on_its_footprint_whatever_ring_it_shows(
    canvas, rotation: float, rings: bool, state: str | None
) -> None:
    _view, scene = canvas
    scene.set_spacing_circles_visible(rings)
    plant = _tree(scene, 1180.0, 1080.0, 110.0, 800.0)   # the survey's magnolia: 2.20 m, ring 8 m
    plant._apply_rotation(rotation)
    if state is not None:
        plant.set_spacing_overlap(state)
    plant.set_antagonist_warning(True)                    # the badge widens the bounding rect to one side
    plant.set_companion_highlight("antagonistic")
    plant.setSelected(True)
    QApplication.processEvents()

    assert plant.rect() == QRectF(1070.0, 970.0, 220.0, 220.0)
    _assert_handles_on(plant, plant.rect())
    # and the box they span is the footprint, not the 8 m ring
    handles = [child for child in plant.childItems() if isinstance(child, ResizeHandle)]
    xs, ys = [h.pos().x() for h in handles], [h.pos().y() for h in handles]
    assert max(xs) - min(xs) == pytest.approx(220.0)
    assert max(ys) - min(ys) == pytest.approx(220.0)


def _circle(scene):
    item = CircleItem(900.0, 700.0, 120.0, object_type=ObjectType.POND_POOL)
    scene.addItem(item)
    return item, item.rect()


def _rectangle(scene):
    item = RectangleItem(600.0, 500.0, 400.0, 250.0, object_type=ObjectType.RAISED_BED)
    scene.addItem(item)
    return item, item.rect()


def _ellipse(scene):
    item = EllipseItem(600.0, 500.0, 400.0, 250.0, object_type=ObjectType.GENERIC_ELLIPSE)
    scene.addItem(item)
    return item, item.rect()


def _polygon(scene):
    points = [QPointF(600, 500), QPointF(1000, 520), QPointF(950, 800), QPointF(640, 760)]
    item = PolygonItem(points, object_type=ObjectType.LAWN)
    scene.addItem(item)
    return item, item.polygon().boundingRect()


@pytest.mark.parametrize("make", [_circle, _rectangle, _ellipse, _polygon],
                         ids=["circle", "rectangle", "ellipse", "polygon"])
@pytest.mark.parametrize("rotation", [0.0, 45.0])
@pytest.mark.parametrize("shadows", [True, False], ids=["shadow", "no-shadow"])
def test_every_shapes_handles_sit_on_its_outline_not_on_its_shadow(
    canvas, make, rotation: float, shadows: bool
) -> None:
    _view, scene = canvas
    scene.set_shadows_enabled(shadows)
    item, outline = make(scene)
    item._apply_rotation(rotation)
    item.setSelected(True)
    QApplication.processEvents()
    _assert_handles_on(item, outline)


@pytest.mark.parametrize("rotation", [0.0, 60.0])
def test_the_rotation_handle_stands_over_the_outlines_top_centre(canvas, rotation: float) -> None:
    view, scene = canvas
    plant = _tree(scene, 1180.0, 1080.0, 110.0, 800.0)
    plant._apply_rotation(rotation)
    plant.set_spacing_overlap("overlap")
    plant.set_antagonist_warning(True)
    plant.setSelected(True)
    QApplication.processEvents()
    handle = next(c for c in plant.childItems() if isinstance(c, RotationHandle))
    rect = plant.rect()
    offset_cm = 25.0 / view.transform().m11()     # ROTATION_HANDLE_OFFSET pixels
    assert handle.pos().x() == pytest.approx(rect.center().x())
    assert handle.pos().y() == pytest.approx(rect.top() - offset_cm)


def test_a_handle_drag_still_resizes_the_plant_from_its_footprint(canvas) -> None:
    """The handle moved to the footprint; the drag it starts still tracks the cursor."""
    _view, scene = canvas
    plant = _tree(scene, 1180.0, 1080.0, 110.0, 800.0)
    plant.set_spacing_overlap("overlap")
    plant.setSelected(True)
    handle = next(
        c for c in plant.childItems()
        if isinstance(c, ResizeHandle) and c.handle_position is HandlePosition.MIDDLE_RIGHT
    )
    start = handle.scenePos()
    assert start.x() == pytest.approx(1290.0)
    handle._initial_rect = plant.rect()
    handle._initial_parent_pos = plant.pos()
    plant._on_resize_start()
    handle._apply_resize(QPointF(60.0, 0.0))
    assert plant.rect().width() == pytest.approx(280.0)
    assert handle.scenePos().x() == pytest.approx(start.x() + 60.0)


# --------------------------------------------------------------------------
# The position and the diameter label
# --------------------------------------------------------------------------


def _device_rect(view: CanvasView, label) -> QRectF:
    return label.deviceTransform(view.viewportTransform()).mapRect(label.boundingRect())


@pytest.mark.parametrize("zoom", [0.15, 0.42, 1.0, 3.0, 8.0])
@pytest.mark.parametrize("radius", [12.0, 110.0, 450.0], ids=["herb", "magnolia", "big-tree"])
@pytest.mark.parametrize("rotation", [0.0, 45.0])
@pytest.mark.parametrize(
    "centre", [(1500.0, 1000.0), (2990.0, 1000.0), (10.0, 1990.0)], ids=["middle", "right-edge", "corner"]
)
def test_the_position_and_diameter_labels_never_overlap(
    canvas, zoom: float, radius: float, rotation: float, centre: tuple[float, float]
) -> None:
    view, scene = canvas
    plant = _tree(scene, centre[0], centre[1], radius, radius * 2.0)
    plant._apply_rotation(rotation)
    view.set_zoom(zoom)
    plant.setSelected(True)
    QApplication.processEvents()

    position, diameter = plant._center_label, plant._diameter_label
    assert position.isVisible() and diameter.isVisible()
    first, second = _device_rect(view, position), _device_rect(view, diameter)
    assert not first.intersects(second), (first, second)
    # neither sits on the handle they hang beside
    handle = next(
        c for c in plant.childItems()
        if isinstance(c, ResizeHandle) and c.handle_position is HandlePosition.MIDDLE_RIGHT
    )
    grip = handle.deviceTransform(view.viewportTransform()).mapRect(handle.boundingRect())
    assert not first.intersects(grip) and not second.intersects(grip)


def test_the_labels_follow_a_resize_and_stay_apart(canvas) -> None:
    view, scene = canvas
    plant = _tree(scene, 1500.0, 1000.0, 110.0, 220.0)
    view.set_zoom(0.42)
    plant.setSelected(True)
    plant.set_radius_centered(20.0)
    QApplication.processEvents()
    assert plant._diameter_label._text.endswith("40.0 cm")
    assert not _device_rect(view, plant._center_label).intersects(
        _device_rect(view, plant._diameter_label)
    )
    anchor = plant.mapToScene(QPointF(plant.rect().right(), plant.rect().center().y()))
    assert plant._diameter_label.scenePos() == anchor
    assert plant._center_label.scenePos() == anchor


# --------------------------------------------------------------------------
# End to end: the survey's magnolia in the bundled family garden
# --------------------------------------------------------------------------


def test_the_family_gardens_magnolia_has_its_handles_on_its_crown(qtbot, monkeypatch) -> None:
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(1300, 900)
    win.show()
    qtbot.waitExposed(win)
    win._load_project_file(str(EXAMPLES / "family-garden.ogp"))
    QApplication.processEvents()
    win.canvas_view.fit_in_view()
    win._update_spacing_overlaps()

    magnolia = next(
        item for item in win.canvas_scene.items()
        if getattr(item, "plant_species", "") == "magnolia"
    )
    assert magnolia.spacing_overlap == "overlap"            # its ring is on show
    win.canvas_scene.clearSelection()
    magnolia.setSelected(True)
    QApplication.processEvents()

    handles = [c for c in magnolia.childItems() if isinstance(c, ResizeHandle)]
    xs, ys = [h.pos().x() for h in handles], [h.pos().y() for h in handles]
    # 2.20 m, the crown as drawn. Master: 863.5 cm, the spacing ring's box.
    assert max(xs) - min(xs) == pytest.approx(220.0)
    assert max(ys) - min(ys) == pytest.approx(220.0)
    assert magnolia.boundingRect().width() > 800.0          # the ring is still painted
    assert not _device_rect(win.canvas_view, magnolia._center_label).intersects(
        _device_rect(win.canvas_view, magnolia._diameter_label)
    )
