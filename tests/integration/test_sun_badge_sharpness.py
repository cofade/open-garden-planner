"""The sun-mismatch badge is drawn for the painter that shows it (#794).

The badge was a 24-pixel pixmap in a ``QGraphicsPixmapItem`` scaled to four
tenths of its plant: a 1.1 m badge at 400 % zoom was that bitmap enlarged 19
times, nearest neighbour — blocks of 19 pixels. It is drawn through the one
rule every canvas bitmap follows now (``core.raster_resolution``, §8.9.14), so
it is as fine as the device at every zoom and pixel ratio.

A bitmap of 24 pixels enlarged can change at 23 columns at most; a picture drawn
for the device changes wherever the icon's outline runs. That count is the
measure here.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.sun_mismatch_service import SunMismatch
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem
from open_garden_planner.ui.canvas.items.garden_item import SunBadgeItem
from open_garden_planner.ui.sun_exposure_coordinator import SunExposureCoordinator

#: The source bitmap's side: what the badge was made of.
SOURCE_PX = 24


def _plant(scene: CanvasScene, radius: float = 140.0) -> CircleItem:
    """A flat-coloured disc standing in for a plant: the badge is measured on it."""
    plant = CircleItem(600.0, 400.0, radius, object_type=ObjectType.GENERIC_CIRCLE)
    plant.fill_pattern = FillPattern.SOLID
    plant.fill_color = QColor(214, 226, 190)
    plant.setBrush(create_pattern_brush(FillPattern.SOLID, plant.fill_color))
    scene.addItem(plant)
    return plant


def _badge(plant: CircleItem) -> SunBadgeItem:
    mismatch = SunMismatch("plant", SunRequirement.FULL_SUN, 1.5, date(2026, 6, 21), "too_little")
    SunExposureCoordinator._badge(plant, mismatch, "Tomato")
    badge = plant._sun_badge
    assert isinstance(badge, SunBadgeItem) and badge.isVisible()
    return badge


def _columns_that_change(picture: np.ndarray) -> int:
    """At how many column borders the picture differs from its neighbour."""
    return int((np.abs(np.diff(picture, axis=1)).sum(axis=2) > 24).any(axis=0).sum())


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16).copy()


def _painted_alone(badge: SunBadgeItem, side_px: int, pixel_ratio: float = 1.0) -> np.ndarray:
    """The badge's own paint into a white square of ``side_px`` device pixels."""
    image = QImage(side_px, side_px, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(pixel_ratio)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    bounds = badge.boundingRect()
    scale = side_px / pixel_ratio / bounds.width()
    painter.scale(scale, scale)
    painter.translate(-bounds.topLeft())
    badge.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return _pixels(image)


@pytest.mark.parametrize("side_px", [96, 448, 1120, 1800])
def test_the_badge_is_as_fine_as_the_device_shows_it(qtbot, side_px: int) -> None:
    """448 px is the 1.1 m badge of the family-garden example at 400 %; 1800 px
    is past the size a sprite is kept at and is drawn from the vector."""
    scene = CanvasScene(1200, 800)
    badge = _badge(_plant(scene))
    picture = _painted_alone(badge, side_px)
    # the icon's ink spans three quarters of the badge's width: most of those
    # columns differ from their neighbour, where the bitmap had 23 borders
    wanted = min(0.6 * side_px, 6 * (SOURCE_PX - 1))
    assert _columns_that_change(picture) > wanted, _columns_that_change(picture)


@pytest.mark.parametrize("pixel_ratio", [1.0, 1.5, 2.0])
def test_the_badge_is_as_fine_on_a_dense_display(qtbot, pixel_ratio: float) -> None:
    scene = CanvasScene(1200, 800)
    badge = _badge(_plant(scene))
    picture = _painted_alone(badge, round(240 * pixel_ratio), pixel_ratio)
    assert _columns_that_change(picture) > 3 * (SOURCE_PX - 1)


def test_the_badge_is_upright_and_where_it_was(qtbot) -> None:
    """The sun in the upper left, the warning triangle in the lower right, in
    the rectangle the placement gives it — whatever paints it."""
    scene = CanvasScene(1200, 800)
    scene.set_shadows_enabled(False)
    plant = _plant(scene)
    badge = _badge(plant)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    view.set_zoom(4.0)
    view.centerOn(plant)
    QApplication.processEvents()
    with_badge = _pixels(view.viewport().grab().toImage())
    badge.setOpacity(0.0)
    QApplication.processEvents()
    without = _pixels(view.viewport().grab().toImage())
    ink = np.abs(with_badge - without).sum(axis=2) > 60
    rows, columns = np.nonzero(ink)
    area = badge.sceneBoundingRect()
    top_left = view.mapFromScene(area.left(), area.bottom())        # north-west: the view flips y
    bottom_right = view.mapFromScene(area.right(), area.top())
    assert columns.min() >= top_left.x() - 1 and columns.max() <= bottom_right.x() + 1
    assert rows.min() >= top_left.y() - 1 and rows.max() <= bottom_right.y() + 1
    width, height = bottom_right.x() - top_left.x(), bottom_right.y() - top_left.y()
    assert width == pytest.approx(0.4 * 2 * 140.0 * 4.0, rel=0.02)
    # the sun's disc: centre (9, 9) of 24, radius 4 — the ring has ink, its middle has none
    def at(x_units: float, y_units: float) -> bool:
        return bool(ink[round(top_left.y() + y_units / 24 * height), round(top_left.x() + x_units / 24 * width)])
    assert at(9, 5) and at(9, 13) and at(5, 9) and at(13, 9)
    assert not at(9, 9)
    # the triangle's base runs along the bottom right: (11, 22) to (23, 22)
    assert at(17, 22) and not at(4, 22)
    # sharp in the view too: the ring is cut by many columns, not by blocks of 19
    box = ink[top_left.y(): bottom_right.y(), top_left.x(): bottom_right.x()]
    changes = int((box[:, 1:] != box[:, :-1]).any(axis=0).sum())
    assert changes > 6 * (SOURCE_PX - 1), changes


def test_a_new_theme_gives_the_badge_its_colours(qtbot) -> None:
    from open_garden_planner.ui.theme import ThemeMode, apply_theme

    app = QApplication.instance()
    scene = CanvasScene(1200, 800)
    plant = _plant(scene)
    try:
        apply_theme(app, ThemeMode.LIGHT)
        badge = _badge(plant)
        light = _painted_alone(badge, 240)
        apply_theme(app, ThemeMode.DARK)
        SunExposureCoordinator._badge(
            plant, SunMismatch("plant", SunRequirement.FULL_SUN, 1.5, date(2026, 6, 21), "too_little"), "Tomato")
        dark = _painted_alone(plant._sun_badge, 240)
    finally:
        apply_theme(app, ThemeMode.LIGHT)
    assert np.abs(light - dark).max() > 60


def test_the_badge_keeps_its_place_in_the_plant(qtbot) -> None:
    scene = CanvasScene(1200, 800)
    plant = _plant(scene, radius=50.0)
    badge = _badge(plant)
    inside = badge.mapRectToParent(badge.boundingRect())
    assert inside.width() == pytest.approx(0.4 * 100.0)
    assert plant.rect().contains(inside)
    assert QRectF(inside).center().x() == pytest.approx(plant.rect().center().x(), abs=0.5)
