"""Unit tests: per-object fill-pattern transform (issue #665).

The three values are display-only: they move/turn/resize the *texture*, never
the object. The sign and the composition order are the parts a fixture cannot
guess, so they are pinned here:

* ``angle_deg`` is clockwise **as displayed** (the canvas and every export flip
  scene Y, so a positive angle is Qt's positive ``QTransform.rotate``);
* ``offset`` is in the item's centimetre frame, independent of scale/angle;
* a plain ``FillTransform()`` is the identity and leaves the brush untouched.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap

from open_garden_planner.core.fill_patterns import (
    FillPattern,
    FillTransform,
    _tinted_cache,
    create_pattern_brush,
)


class TestModel:
    def test_default_is_the_identity(self) -> None:
        transform = FillTransform()
        assert transform.is_identity
        assert transform.to_dict() is None
        assert transform.brush_transform().isIdentity()

    @pytest.mark.parametrize(
        "transform",
        [
            FillTransform(angle_deg=30),
            FillTransform(scale=2.0),
            FillTransform(offset_x_cm=12.5),
            FillTransform(offset_y_cm=-7.0),
            FillTransform(angle_deg=-45, scale=0.5, offset_x_cm=3, offset_y_cm=4),
        ],
    )
    def test_round_trips_through_the_stored_block(self, transform: FillTransform) -> None:
        stored = transform.to_dict()
        assert stored is not None
        assert FillTransform.from_dict(stored) == transform

    def test_offset_is_independent_of_scale_and_angle(self) -> None:
        """The acceptance rule: the same centimetre offset at every scale/angle."""
        for transform in (
            FillTransform(offset_x_cm=25),
            FillTransform(angle_deg=37, offset_x_cm=25),
            FillTransform(scale=3.0, offset_x_cm=25),
            FillTransform(angle_deg=-90, scale=0.25, offset_x_cm=25),
        ):
            assert transform.brush_transform().map(QPointF(0.0, 0.0)) == QPointF(25.0, 0.0)

    def test_scale_multiplies_the_tile_axes(self) -> None:
        transform = FillTransform(scale=2.0)
        assert transform.brush_transform().map(QPointF(1.0, 0.0)) == QPointF(2.0, 0.0)
        assert transform.brush_transform().map(QPointF(0.0, 1.0)) == QPointF(0.0, 2.0)

    def test_angle_is_qts_positive_rotation(self) -> None:
        """Qt's +90 maps local +x to +y; the Y-flipped canvas shows that clockwise."""
        transform = FillTransform(angle_deg=90)
        mapped = transform.brush_transform().map(QPointF(1.0, 0.0))
        assert mapped.x() == pytest.approx(0.0, abs=1e-9)
        assert mapped.y() == pytest.approx(1.0, abs=1e-9)


def test_malformed_values_fall_back_to_defaults() -> None:
    assert FillTransform.from_dict(None) == FillTransform()
    assert FillTransform.from_dict("nope") == FillTransform()
    assert FillTransform.from_dict({"angle_deg": "x", "scale": True}) == FillTransform()
    assert FillTransform.from_dict({"scale": 0}) == FillTransform()
    assert FillTransform.from_dict({"scale": -2}) == FillTransform()
    assert FillTransform.from_dict({"angle_deg": float("nan")}) == FillTransform()
    assert FillTransform.from_dict({"offset_x_cm": math.inf}) == FillTransform()


def test_unrepresentable_integers_never_raise() -> None:
    """A huge JSON integer is a valid ``int`` but not a valid ``float``.

    ``float(10**400)`` raises ``OverflowError``; the stored block arrives from
    an untrusted file, and both directions promised to tolerate malformed data
    (P2 of the #665 review).
    """
    huge = 10**400
    assert FillTransform.from_dict({"angle_deg": huge}) == FillTransform()
    assert FillTransform.from_dict({"scale": huge}) == FillTransform()
    assert FillTransform.from_dict({"offset_x_cm": huge}) == FillTransform()
    assert FillTransform(offset_x_cm=huge).to_dict() is None


def test_nan_is_never_written_to_json() -> None:
    assert FillTransform(angle_deg=float("nan")).to_dict() is None


def _probe_texture(pattern: FillPattern = FillPattern.WOOD) -> QPixmap:
    """A 64 x 64 texture whose left half is black and right half white."""
    image = QImage(64, 64, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    for x in range(32, 64):
        for y in range(64):
            image.setPixel(x, y, QColor(255, 255, 255).rgb())
    return QPixmap.fromImage(image)


def _paint_in_display_orientation(brush) -> QImage:
    """Fill a 200 x 200 image through the same Y flip the canvas/export uses."""
    image = QImage(200, 200, QImage.Format.Format_RGB32)
    image.fill(QColor(255, 255, 255))
    painter = QPainter(image)
    painter.translate(0, 200)
    painter.scale(1, -1)
    painter.fillRect(0, 0, 200, 200, brush)
    painter.end()
    return image


@pytest.fixture
def probe_brush(qtbot, monkeypatch):
    """Install a black/white probe texture and return a brush factory."""
    from open_garden_planner.core import fill_patterns

    monkeypatch.setitem(fill_patterns._texture_cache, FillPattern.WOOD, _probe_texture())
    _tinted_cache.clear()

    def build(transform: FillTransform | None):
        return create_pattern_brush(
            FillPattern.WOOD, QColor(255, 0, 0), transform
        )

    yield build
    _tinted_cache.clear()


def test_untouched_pattern_is_the_original_brush(probe_brush) -> None:
    plain = probe_brush(None)
    identity = probe_brush(FillTransform())
    assert plain.transform().isIdentity()
    assert identity.transform().isIdentity()
    assert _paint_in_display_orientation(plain) == _paint_in_display_orientation(identity)


def test_a_quarter_turn_is_clockwise_on_the_canvas(probe_brush) -> None:
    image = _paint_in_display_orientation(probe_brush(FillTransform(angle_deg=90)))
    # The texture's +x half is the BRIGHT one. A clockwise quarter turn takes
    # that half from screen-right to screen-bottom.
    top = image.pixelColor(100, 40).red()
    bottom = image.pixelColor(100, 160).red()
    assert top < 128 < bottom

    opposite = _paint_in_display_orientation(probe_brush(FillTransform(angle_deg=-90)))
    assert opposite.pixelColor(100, 40).red() > 128 > opposite.pixelColor(100, 160).red()


def test_scale_enlarges_the_tile_period(probe_brush) -> None:
    image = _paint_in_display_orientation(probe_brush(FillTransform(scale=2.0)))
    # 64 px tile x 2 = 128 px: dark 0..64, bright 64..128, dark 128..192.
    assert image.pixelColor(32, 100).red() < 128
    assert image.pixelColor(96, 100).red() > 128
    assert image.pixelColor(160, 100).red() < 128


def test_offset_shifts_the_pattern_right(probe_brush) -> None:
    baseline = _paint_in_display_orientation(probe_brush(None))
    shifted = _paint_in_display_orientation(
        probe_brush(FillTransform(offset_x_cm=32))
    )
    # A 32 cm shift (half of the 64 cm tile) puts the texture's left half where
    # its right half was: each sample flips from dark to bright and back.
    assert baseline.pixelColor(16, 100).red() < 128
    assert shifted.pixelColor(16, 100).red() > 128
    assert baseline.pixelColor(48, 100).red() > 128
    assert shifted.pixelColor(48, 100).red() < 128


def test_solid_pattern_ignores_the_transform() -> None:
    brush = create_pattern_brush(
        FillPattern.SOLID, QColor("#123456"), FillTransform(angle_deg=90, scale=2)
    )
    assert brush.transform().isIdentity()
    assert brush.color() == QColor("#123456")
