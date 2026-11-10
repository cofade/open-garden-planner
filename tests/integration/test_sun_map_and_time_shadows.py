"""While the hours-of-sun map is shown, the time-of-day shadows are not painted (#794).

The map lies above the shadow overlay (z -450 over -500) and always did. But it
is translucent — alpha 32 where the ground is sunny all day — so the shadow of
one instant showed through it: on the family-garden example it changed a third
of the viewport's pixels, and a spot with 14 hours of sun read as one with 6.
With a legend beside the map that is a wrong reading, not a matter of taste.

So the overlay is not painted while a map is shown. It is still SOLVED: the 3D
view's shadow drape and every other reader take the polygons from the
controller, and they must not notice.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    STATE_NIGHT,
    SunShadowController,
    SunShadowOverlayItem,
)

BERLIN = {"latitude": 52.52, "longitude": 13.405}
NOON = datetime(2026, 6, 21, 11, 0, tzinfo=UTC)
EVENING = datetime(2026, 6, 21, 17, 30, tzinfo=UTC)
MIDNIGHT = datetime(2026, 6, 21, 23, 0, tzinfo=UTC)
DAY = date(2026, 6, 21)


def _scene() -> CanvasScene:
    scene = CanvasScene(1200.0, 900.0)
    scene.set_shadows_enabled(False)
    post = RectangleItem(560, 300, 60, 60, object_type=ObjectType.GENERIC_RECTANGLE)
    post.metadata[METADATA_KEY] = 300.0
    scene.addItem(post)
    return scene


def _overlay(scene: CanvasScene) -> SunShadowOverlayItem:
    (overlay,) = [item for item in scene.items() if isinstance(item, SunShadowOverlayItem)]
    return overlay


def _picture(scene: CanvasScene) -> np.ndarray:
    image = QImage(600, 450, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    render_scene_region(scene, painter, QRectF(image.rect()), scene.canvas_rect)
    painter.end()
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16).copy()


def test_a_shown_map_takes_the_overlay_off_the_canvas(qtbot) -> None:
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(NOON)
    controller.set_enabled(True)
    overlay = _overlay(scene)
    assert overlay.isVisible()

    controller.set_map_shown(True)
    assert not overlay.isVisible()
    assert controller.map_shown

    controller.set_map_shown(False)
    assert overlay.isVisible()


def test_the_shadows_are_still_solved_and_published_while_hidden(qtbot) -> None:
    """The 3D view lays ``drape_polygons()`` on its ground: hiding the 2D
    picture must not empty them, and a new instant must still re-solve."""
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(NOON)
    controller.set_enabled(True)
    at_noon = controller.drape_polygons()
    assert at_noon
    published: list[int] = []
    controller.shadows_changed.connect(lambda: published.append(1))

    controller.set_map_shown(True)
    assert controller.drape_polygons() == at_noon
    assert controller.state == STATE_ACTIVE
    assert not published, "hiding the picture is no change of the shadows"

    solves = controller.recompute_count
    controller.set_sim_datetime(EVENING)
    assert controller.recompute_count == solves + 1
    assert controller.drape_polygons() and controller.drape_polygons() != at_noon
    assert published == [1]
    assert not _overlay(scene).isVisible(), "a new solve must not bring the picture back"

    # the same instant again: nothing to solve, and still nothing shown
    controller.recompute_now()
    assert controller.recompute_count == solves + 1
    assert not _overlay(scene).isVisible()


def test_the_overlay_comes_back_with_the_current_shadows(qtbot) -> None:
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(NOON)
    controller.set_enabled(True)
    noon_path = _overlay(scene).path()
    controller.set_map_shown(True)
    controller.set_sim_datetime(EVENING)
    controller.set_map_shown(False)
    overlay = _overlay(scene)
    assert overlay.isVisible()
    assert overlay.path() != noon_path, "the overlay shows the evening's shadows, not the noon's"


def test_night_does_not_darken_the_map_either(qtbot) -> None:
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_map_shown(True)
    controller.set_sim_datetime(MIDNIGHT)
    controller.set_enabled(True)
    assert controller.state == STATE_NIGHT
    assert not _overlay(scene).isVisible()
    assert controller.drape_polygons(), "the night is still published"
    controller.set_map_shown(False)
    assert _overlay(scene).isVisible()


def test_switching_the_shadows_off_and_on_respects_the_map(qtbot) -> None:
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(NOON)
    controller.set_map_shown(True)
    controller.set_enabled(True)
    assert not _overlay(scene).isVisible()
    controller.set_enabled(False)
    assert controller.drape_polygons() == ()
    controller.set_map_shown(False)
    assert not _overlay(scene).isVisible(), "a disabled controller shows nothing"
    controller.set_enabled(True)
    assert _overlay(scene).isVisible()


def test_the_overlay_survives_a_cleared_scene(qtbot) -> None:
    scene = _scene()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(NOON)
    controller.set_enabled(True)
    controller.set_map_shown(True)
    scene.clear()
    controller.recompute_now()          # nothing casts any more
    controller.set_map_shown(False)     # must not touch the deleted overlay
    post = RectangleItem(560, 300, 60, 60, object_type=ObjectType.GENERIC_RECTANGLE)
    post.metadata[METADATA_KEY] = 300.0
    scene.addItem(post)
    controller.recompute_now()
    assert _overlay(scene).isVisible()


def test_the_map_is_the_same_picture_whatever_the_time_of_day(qtbot) -> None:
    """End to end on a real map: with the map shown, a picture of the plan at
    noon is the picture in the evening — and neither holds the post's shadow."""
    scene = _scene()
    shadows = SunShadowController(scene, lambda: BERLIN)
    shadows.set_sim_datetime(NOON)
    shadows.set_enabled(True)
    heatmap = SunHeatmapController(scene, lambda: BERLIN)
    heatmap.computed.connect(lambda shown: shadows.set_map_shown(shown is not None))
    without_map = _picture(scene)
    with qtbot.waitSignal(heatmap.finished, timeout=60000):
        assert heatmap.run_for_day(DAY)
    assert heatmap.heatmap_visible() and shadows.map_shown

    at_noon = _picture(scene)
    shadows.set_sim_datetime(EVENING)
    in_the_evening = _picture(scene)
    assert np.array_equal(at_noon, in_the_evening)

    # switching the map off brings the evening's shadow back
    heatmap.clear()
    assert not shadows.map_shown
    evening_shadow = _picture(scene)
    assert np.abs(evening_shadow - without_map).sum(axis=2).max() > 60
    heatmap.shutdown()
