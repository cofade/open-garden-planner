"""The sun shadow's soft edge is a smooth falloff at every zoom (#793).

Until #793 the edge was four stacked strokes: four flat bands (1.25 to 2.5 cm
wide) that read as one soft edge at 100 % zoom and as four stripes from 200 %
on, the innermost of them darker than the shade itself. These tests paint the
overlay and measure the falloff on pixels: no band, no ring, the reach it
always had, and the shade's own geometry untouched.

The arithmetic is tested Qt-free in ``tests/unit/test_soft_edge.py``.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from open_garden_planner.core.shadow_geometry import WeightedShadowRegion
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    _SHADOW_COLOR,
    SunShadowOverlayItem,
)

#: How far the soft edge reaches past the shade, centimetres of plan: what the
#: stacked strokes reached (half their widest width), stated here and not read
#: from the code, so that the reach cannot change unnoticed.
FEATHER_REACH_CM = 7.0

#: Device pixels per centimetre of plan: 100 %, a 300-dpi picture of a plan at
#: 1:100, 200 %, 400 % and 1000 % zoom.
SCALES = [1.0, 300 / 2.54 / 100, 2.0, 4.0, 10.0]

CANVAS = QRectF(0.0, 0.0, 400.0, 300.0)
SHADE = QRectF(100.0, 100.0, 100.0, 100.0)


def _overlay(shade: QPainterPath | None = None) -> SunShadowOverlayItem:
    overlay = SunShadowOverlayItem()
    overlay.set_clip_rect(CANVAS)
    if shade is None:
        shade = QPainterPath()
        shade.addRect(SHADE)
    overlay.set_shadow_path(shade)
    return overlay


def _paint(overlay: SunShadowOverlayItem, window: QRectF, scale: float) -> np.ndarray:
    """The overlay over white, ``window`` of the plan at ``scale`` px a cm: how
    much darker than white each pixel is (0 to 255)."""
    image = QImage(
        max(1, round(window.width() * scale)), max(1, round(window.height() * scale)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(-window.left(), -window.top())
    overlay._paint_exact(painter)
    painter.end()
    return _darkness(image)


def _darkness(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return 255 - rows[:, : image.width(), 0].astype(np.int16)


def _east_profile(overlay: SunShadowOverlayItem, scale: float) -> tuple[np.ndarray, int, int]:
    """Darkness along a line across the shade's east edge (x = 200): the
    profile, the index of the first pixel outside the shade, and the reach in
    pixels."""
    window = QRectF(180.0, 148.0, 40.0, 4.0)
    picture = _paint(overlay, window, scale)
    row = picture[picture.shape[0] // 2]
    return row, round(20.0 * scale), round(FEATHER_REACH_CM * scale)


@pytest.mark.parametrize("scale", SCALES)
def test_the_falloff_has_no_bands(qtbot, scale: float) -> None:
    """Four stacked strokes are four flat stretches with a step between them."""
    row, edge, reach = _east_profile(_overlay(), scale)
    falloff = row[edge: edge + reach]
    core = int(row[edge - 3])
    steps = -np.diff(np.concatenate(([core], falloff, [0])))
    even = core / reach
    # no step much larger than an even ramp's (the strokes: up to 39 of 97)
    assert steps.max() <= 1.6 * even + 2.0, (scale, steps.tolist())
    # ... and it never stands still for three pixels within the falloff
    flat = 0
    for step in steps[: reach - 1]:
        flat = flat + 1 if step == 0 else 0
        assert flat < 2 or even < 0.75, (scale, falloff.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_the_falloff_only_gets_lighter_away_from_the_shade(qtbot, scale: float) -> None:
    row, edge, reach = _east_profile(_overlay(), scale)
    outside = row[edge - 1: edge + reach + 4]
    assert (np.diff(outside) <= 1).all(), (scale, outside.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_no_ring_darker_than_the_shade(qtbot, scale: float) -> None:
    """The innermost stroke was 15 levels darker than the shade it edged."""
    row, edge, reach = _east_profile(_overlay(), scale)
    core = int(row[edge - 3])
    assert row[edge - 2: edge + reach].max() <= core + 1, (scale, row.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_the_falloff_starts_at_the_shades_own_tone(qtbot, scale: float) -> None:
    row, edge, _reach = _east_profile(_overlay(), scale)
    core = int(row[edge - 3])
    # one pixel into the falloff: an even ramp's first step and a little
    assert core - int(row[edge]) <= core / (FEATHER_REACH_CM * scale) + 4, (scale, row.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_the_falloff_reaches_seven_centimetres_and_no_further(qtbot, scale: float) -> None:
    overlay = _overlay()
    row, edge, reach = _east_profile(overlay, scale)
    core = int(row[edge - 3])
    halfway = int(row[edge + round(0.5 * reach)])
    assert 0.3 * core <= halfway <= 0.7 * core, (scale, halfway, core)
    beyond = row[edge + reach + max(2, round(2 * scale)):]
    assert beyond.size and not beyond.any(), (scale, beyond.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_the_shade_itself_is_where_its_outline_puts_it(qtbot, scale: float) -> None:
    """The soft edge changes no ground that is in shade: the full tone is the
    outline's fill, to the pixel."""
    overlay = _overlay()
    window = QRectF(80.0, 80.0, 140.0, 140.0)
    picture = _paint(overlay, window, scale)
    core = int(picture[picture.shape[0] // 2, picture.shape[1] // 2])
    full = picture >= core - 1
    left, right = round(20.0 * scale), round(120.0 * scale)
    wanted = np.zeros_like(full)
    wanted[left:right, left:right] = True
    # anti-aliasing may differ on the outline's own pixels, nowhere else
    assert np.count_nonzero(full ^ wanted) <= 4 * (right - left) + 4
    assert full[left + 2: right - 2, left + 2: right - 2].all()


def test_the_interior_keeps_one_flat_tone(qtbot) -> None:
    picture = _paint(_overlay(), QRectF(100.0, 100.0, 100.0, 100.0), 4.0)
    inside = picture[4:-4, 4:-4]
    assert inside.max() - inside.min() <= 1


def test_the_shade_is_cut_off_at_the_canvas_and_so_is_its_edge(qtbot) -> None:
    shade = QPainterPath()
    shade.addRect(QRectF(300.0, 100.0, 200.0, 100.0))   # runs 100 cm past the canvas
    overlay = _overlay(shade)
    picture = _paint(overlay, QRectF(380.0, 80.0, 40.0, 140.0), 4.0)
    canvas_edge = round(20.0 * 4.0)
    assert not picture[:, canvas_edge + 1:].any()
    assert picture[:, : canvas_edge - 1].any()
    # the canvas cuts the shade: there is no falloff along the cut
    middle = picture[picture.shape[0] // 2]
    assert middle[canvas_edge - 2] == middle[canvas_edge - 20]


def test_night_has_no_edge_to_soften(qtbot) -> None:
    shade = QPainterPath()
    shade.addRect(CANVAS)
    overlay = _overlay(shade)
    assert overlay._feathered is False
    picture = _paint(overlay, QRectF(-20.0, -20.0, 440.0, 340.0), 1.0)
    inside = picture[22:-22, 22:-22]
    assert inside.max() - inside.min() <= 1


def test_a_light_shade_gets_a_light_edge_and_a_shared_boundary_none(qtbot) -> None:
    """Each region is edged at its own strength (#698); where a light shade
    runs into a solid one the boundary lies inside the whole shade."""
    solid = [(100.0, 100.0), (150.0, 100.0), (150.0, 200.0), (100.0, 200.0)]
    light = [(150.0, 100.0), (200.0, 100.0), (200.0, 200.0), (150.0, 200.0)]
    overlay = _overlay()
    overlay.set_weighted_regions((
        WeightedShadowRegion([solid], occlusion=1.0, transmittance=0.0),
        WeightedShadowRegion([light], occlusion=0.3, transmittance=0.7),
    ))
    scale = 4.0
    picture = _paint(overlay, QRectF(80.0, 148.0, 140.0, 4.0), scale)
    row = picture[picture.shape[0] // 2]
    west_edge, boundary, east_edge = round(20 * scale), round(70 * scale), round(120 * scale)
    solid_tone, light_tone = int(row[west_edge + 8]), int(row[east_edge - 8])
    assert light_tone < 0.5 * solid_tone
    # 2 cm outside each edge: the same share of each shade's own tone
    beside_solid = int(row[west_edge - round(2 * scale)])
    beside_light = int(row[east_edge + round(2 * scale)])
    assert beside_solid / solid_tone == pytest.approx(1.0 - 2.0 / FEATHER_REACH_CM, abs=0.1)
    assert beside_light / light_tone == pytest.approx(1.0 - 2.0 / FEATHER_REACH_CM, abs=0.15)
    # the shared boundary: a step from one flat tone to the other, no edge on it
    assert set(row[boundary - 12: boundary - 2].tolist()) <= {solid_tone, solid_tone - 1, solid_tone + 1}
    assert set(row[boundary + 2: boundary + 12].tolist()) <= {light_tone, light_tone - 1, light_tone + 1}


def test_a_picture_painted_in_two_halves_is_the_picture_painted_at_once(qtbot) -> None:
    """A pan paints a strip of the overlay's device cache; the lattice is
    anchored in the plan, so a strip computes the cells the whole computes."""
    overlay = _overlay()
    scale = 4.0
    window = QRectF(170.0, 170.0, 60.0, 60.0)
    whole = _paint(overlay, window, scale)
    size = whole.shape[0]
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    for strip in (QRectF(0, 0, 97, size), QRectF(97, 0, size - 97, size)):
        painter = QPainter(image)
        painter.setClipRect(strip, Qt.ClipOperation.IntersectClip)
        painter.scale(scale, scale)
        painter.translate(-window.left(), -window.top())
        overlay._paint_exact(painter)
        painter.end()
    assert np.abs(_darkness(image) - whole).max() <= 1


def test_an_exported_picture_has_the_smooth_edge_too(qtbot) -> None:
    """The export paints the overlay uncached, through the same code."""
    scene = CanvasScene(400.0, 300.0)
    overlay = _overlay()
    scene.addItem(overlay)
    scale = 300 / 2.54 / 25      # a 300-dpi picture of the plan at 1:25

    def export() -> np.ndarray:
        image = QImage(round(400 * scale), round(300 * scale), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        render_scene_region(scene, painter, QRectF(image.rect()), scene.canvas_rect)
        painter.end()
        return _darkness(image)

    with_shade = export()
    overlay.setVisible(False)
    row = (with_shade - export())[round(150 * scale)]     # what the overlay adds to the plan
    edge, reach = round(200 * scale), round(FEATHER_REACH_CM * scale)
    falloff = row[edge: edge + reach]
    core = int(row[edge - 4])
    steps = -np.diff(np.concatenate(([core], falloff)))
    assert steps.max() <= 1.6 * core / reach + 2.0, steps.tolist()
    assert falloff[-1] <= 0.15 * core
    assert not row[edge + reach + 6:].any()


def test_the_edge_has_the_shadow_colour(qtbot) -> None:
    image = QImage(80, 8, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.scale(2.0, 2.0)
    painter.translate(-180.0, -148.0)
    _overlay()._paint_exact(painter)
    painter.end()
    pixel = image.pixelColor(46, 4)            # 3 cm outside the east edge
    share = 1.0 - 3.0 / FEATHER_REACH_CM
    alpha = _SHADOW_COLOR.alphaF() * share
    for got, ink in ((pixel.red(), _SHADOW_COLOR.red()), (pixel.green(), _SHADOW_COLOR.green()),
                     (pixel.blue(), _SHADOW_COLOR.blue())):
        assert got == pytest.approx(255 * (1 - alpha) + ink * alpha, abs=8)
    assert QColor(image.pixel(70, 4)) == QColor(Qt.GlobalColor.white)
