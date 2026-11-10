"""The soft edge is never darker than the shade — in concave places too (review round 2, P1-3).

The falloff reads blurred coverage as a distance to the shade
(``core.soft_edge``). That holds beside a straight edge and nowhere else: in
the inside corner of an L, in the cusp between two round shades, in a sunlit
hole and in a narrow sunlit slot, more than half of what surrounds a sunlit
point is shade, the "distance" comes out negative and the falloff's weight
above 1. Until this fix such ground was painted up to 22 levels DARKER than the
shade it lies beside (shade 163, cusp 141), along the whole length of a 4 cm
slot.

The invariant, measured on the painted overlay at 100 %, a 300-dpi picture,
400 % and 1000 %: **no pixel is darker than the shade's own tone** — outside
the shade, on its outline and inside it. And beside the straight parts of the
same shapes the falloff is what it was: it only gets lighter away from the
shade.

``tests/integration/test_shadow_feather.py`` measures the falloff beside one
rectangle; ``tests/unit/test_soft_edge.py`` the arithmetic.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPainterPath

from open_garden_planner.core.shadow_geometry import WeightedShadowRegion
from open_garden_planner.core.soft_edge import (
    MASK_FULL_WEIGHT,
    MAX_WEIGHT,
    feather_fields,
    feather_grid,
)
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowOverlayItem
from tests.integration.test_shadow_feather import FEATHER_REACH_CM, _darkness

#: Device pixels per centimetre of plan: 100 %, a 300-dpi picture of a plan at
#: 1:100, 400 % and 1000 % zoom.
SCALES = [1.0, 300 / 2.54 / 100, 4.0, 10.0]

CANVAS = QRectF(0.0, 0.0, 400.0, 300.0)


def _rect(x: float, y: float, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.addRect(QRectF(x, y, w, h))
    return path


def _disc(x: float, y: float, diameter: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QRectF(x, y, diameter, diameter))
    return path


#: name -> (the shade, a window round its concave place, a point deep inside it)
SHAPES: dict[str, tuple[QPainterPath, QRectF, tuple[float, float]]] = {
    "the inside corner of an L": (
        _rect(50, 50, 100, 200).united(_rect(50, 150, 250, 100)),
        QRectF(130.0, 110.0, 60.0, 60.0), (100.0, 200.0),
    ),
    "the cusps between two round shades": (
        _disc(60, 100, 100).united(_disc(150, 100, 100)),
        QRectF(125.0, 95.0, 60.0, 45.0), (110.0, 150.0),
    ),
    "a sunlit hole of 8 cm": (
        _rect(50, 50, 300, 200).subtracted(_rect(195, 145, 8, 8)),
        QRectF(180.0, 130.0, 40.0, 40.0), (100.0, 100.0),
    ),
    "a sunlit slot of 4 cm": (
        _rect(50, 50, 100, 200).united(_rect(154, 50, 100, 200)),
        QRectF(132.0, 120.0, 40.0, 40.0), (100.0, 150.0),
    ),
    "a sunlit slot of 3 cm, off the lattice": (
        _rect(50, 50, 101.3, 200).united(_rect(154.3, 50, 100, 200)),
        QRectF(132.0, 30.0, 40.0, 60.0), (100.0, 150.0),
    ),
}


def _overlay(shade: QPainterPath) -> SunShadowOverlayItem:
    overlay = SunShadowOverlayItem()
    overlay.set_clip_rect(CANVAS)
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


def _tone(overlay: SunShadowOverlayItem, inside: tuple[float, float], scale: float) -> int:
    """How dark the shade itself is, deep inside it."""
    window = QRectF(inside[0] - 4.0, inside[1] - 4.0, 8.0, 8.0)
    picture = _paint(overlay, window, scale)
    assert picture.min() == picture.max(), "the interior is not one flat tone"
    return int(picture.max())


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("name", list(SHAPES))
def test_no_pixel_is_darker_than_the_shade(qtbot, name: str, scale: float) -> None:
    shade, window, inside = SHAPES[name]
    overlay = _overlay(shade)
    tone = _tone(overlay, inside, scale)
    picture = _paint(overlay, window, scale)
    assert tone > 40
    darkest = int(picture.max())
    assert darkest <= tone + 1, (
        f"{name} at {scale:.2f} px/cm: ground beside the shade is {darkest - tone} levels "
        f"darker than the shade ({tone}), on {int((picture > tone + 1).sum())} pixels"
    )


@pytest.mark.parametrize("scale", SCALES)
def test_the_whole_picture_of_every_shape_holds_it(qtbot, scale: float) -> None:
    """Not only the windows round the places the review named."""
    for name, (shade, _window, inside) in SHAPES.items():
        overlay = _overlay(shade)
        tone = _tone(overlay, inside, scale)
        step = 100.0 if scale > 4.0 else 400.0       # tiles: a picture of 12 megapixels at 1000 %
        for left in np.arange(0.0, 400.0, step):
            for top in np.arange(0.0, 300.0, step):
                tile = QRectF(float(left), float(top), step, step).intersected(CANVAS)
                assert int(_paint(overlay, tile, scale).max()) <= tone + 1, (name, scale, tile)


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("name", list(SHAPES))
def test_beside_a_straight_edge_the_falloff_only_gets_lighter(qtbot, name: str, scale: float) -> None:
    """West of every one of these shapes lies open ground: the falloff there
    is the one beside a rectangle."""
    shade, _window, inside = SHAPES[name]
    overlay = _overlay(shade)
    west = shade.boundingRect().left()
    # a disc's westmost point; the middle of a straight west edge
    row_y = shade.boundingRect().center().y() if "round" in name else inside[1]
    window = QRectF(west - 12.0, row_y - 1.0, 16.0, 2.0)
    picture = _paint(overlay, window, scale)
    row = picture[picture.shape[0] // 2][::-1]            # from inside the shade outwards
    assert (np.diff(row) <= 1).all(), (name, scale, row.tolist())
    tone = _tone(overlay, inside, scale)
    edge = round(4.0 * scale)
    reach = round(FEATHER_REACH_CM * scale)
    # it starts at the shade's tone, within an even ramp's first step and a little
    assert tone - int(row[edge]) <= tone / max(reach, 1) + 0.08 * tone + 4, (name, scale, row.tolist())
    halfway = int(row[edge + round(0.5 * reach)])
    assert 0.25 * tone <= halfway <= 0.75 * tone, (name, scale, halfway, tone)
    beyond = row[edge + reach + max(2, round(2 * scale)):]
    assert beyond.size and not beyond.any(), (name, scale, beyond.tolist())


@pytest.mark.parametrize("scale", SCALES)
def test_across_a_slot_the_ground_is_lightest_in_the_middle(qtbot, scale: float) -> None:
    """A valley, not a ridge: from either wall the ground only gets lighter
    towards the middle of a sunlit slot (10 cm: wide enough to measure)."""
    shade = _rect(50, 50, 100, 200).united(_rect(160, 50, 100, 200))
    overlay = _overlay(shade)
    picture = _paint(overlay, QRectF(146.0, 149.0, 18.0, 2.0), scale)
    row = picture[picture.shape[0] // 2]
    middle = row.size // 2
    assert (np.diff(row[:middle]) <= 1).all(), (scale, row.tolist())
    assert (np.diff(row[middle:]) >= -1).all(), (scale, row.tolist())
    assert int(row.max()) <= _tone(overlay, (100.0, 150.0), scale) + 1


@pytest.mark.parametrize("scale", SCALES)
def test_where_a_light_and_a_solid_shade_meet_nothing_is_darker_than_the_solid_one(
    qtbot, scale: float
) -> None:
    """#698: an open frame casts a light shade. In the inside corner where a
    light and a solid region meet, sunlit ground is at most as dark as the
    darker of the two; beside the light region alone, at most as dark as it."""
    solid = [(50.0, 50.0), (150.0, 50.0), (150.0, 250.0), (50.0, 250.0)]
    light = [(150.0, 150.0), (300.0, 150.0), (300.0, 250.0), (150.0, 250.0)]
    overlay = SunShadowOverlayItem()
    overlay.set_clip_rect(CANVAS)
    overlay.set_shadow_path(_rect(50, 50, 100, 200).united(_rect(150, 150, 150, 100)))
    overlay.set_weighted_regions([
        WeightedShadowRegion(polygons=[solid], occlusion=1.0),
        WeightedShadowRegion(polygons=[light], occlusion=0.4),
    ])
    solid_tone = _tone(overlay, (100.0, 150.0), scale)
    light_tone = _tone(overlay, (260.0, 200.0), scale)
    assert light_tone < solid_tone
    corner = _paint(overlay, QRectF(130.0, 110.0, 60.0, 60.0), scale)
    assert int(corner.max()) <= solid_tone + 1, (scale, int(corner.max()), solid_tone)
    # north of the light region, out of the solid one's reach
    beside_light = _paint(overlay, QRectF(220.0, 130.0, 60.0, 19.0), scale)
    assert int(beside_light.max()) <= light_tone + 1, (scale, int(beside_light.max()), light_tone)
    # ... and it is a falloff there: something is painted
    assert int(beside_light.max()) >= 0.5 * light_tone


class TestWhereTheClampIs:
    """The arithmetic, Qt-free. The lattice is NOT clamped — a clamp there
    either leaves a cell's width of too-dark ground along a concave outline or
    starts every falloff under the shade's tone (both measured) — so the
    painter must be: these pin the two halves of that contract."""

    def test_on_the_lattice_a_sunlit_slot_weighs_more_than_the_shade(self) -> None:
        grid = feather_grid(4.0)
        assert grid is not None
        coverage = np.full((60, 80), 255, dtype=np.uint8)
        coverage[:, 38:42] = 0                            # a slot four cells wide
        weight, tone = feather_fields(coverage, grid)
        assert tone is None
        assert float(weight[30, 39]) > 1.05               # what the painter clamps
        assert float(weight.max()) <= MAX_WEIGHT

    def test_the_mask_has_room_for_every_weight_and_the_shade_at_half_a_byte(self) -> None:
        # doubling the mask with saturation is the clamp to 1 only if ...
        assert MASK_FULL_WEIGHT == 2.0
        # ... and it clamps after the enlargement only if no weight saturates before
        assert MAX_WEIGHT <= MASK_FULL_WEIGHT

    def test_the_tone_is_never_above_the_darkest_shade_near_a_cell(self) -> None:
        grid = feather_grid(4.0)
        assert grid is not None
        coverage = np.zeros((60, 80), dtype=np.uint8)
        coverage[:, :30] = 255
        coverage[30:, 30:60] = 255
        strength = np.zeros_like(coverage)
        strength[:, :30] = 255                            # solid
        strength[30:, 30:60] = 102                        # 0.4
        _weight, tone = feather_fields(coverage, grid, strength)
        assert tone is not None
        assert float(tone.max()) <= 1.0
        # beside the light region alone, out of the solid one's reach
        assert float(tone[20:29, 52:58].max()) <= 0.4 + 1e-3
        assert float(tone[20:29, 52:58].min()) >= 0.4 - 1e-2
