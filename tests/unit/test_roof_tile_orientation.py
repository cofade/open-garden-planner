"""Unit tests for HOUSE roof-tile orientation (issue #372).

The roof-tile texture has an intrinsic, non-negotiable direction. Each tile's
rounded free edge points ``+Y`` of the texture and each tile laps the tile
below it -- measured from the texture itself: a dark lapse line near ``y=10``,
then the light rounded free edge filling the rows beneath. That direction is
down-slope, and it is the direction water runs. A tile that laps the wrong way
is not a cosmetic difference; water runs back up under the laps.

``PolygonItem._paint_with_ridge`` splits the polygon into two halves along the
ridge and fills one with the texture and one with a mirrored copy. The halves
were assigned to brushes by ``_split_path_by_line``'s *arbitrary* left/right
naming, which follows the ridge's **direction**, not which side is downhill.
So the half that needed the texture's true down-slope was the one being
mirrored, and the laps pointed back up toward the ridge.

The arithmetic of the fix, which is what makes it a swap rather than a probe:
``normal_tx`` is ``translate(mid) . rotate(angle)``, and a ``QBrush``
transform samples the texture at ``T^-1 . p``, so the texture's ``+Y`` lands
in the world at ``R(angle).(0,1) = (-sin a, cos a)`` -- which is exactly the
left-perpendicular ``(-uy, ux)`` that ``_split_path_by_line`` offsets
``left_path`` along. ``left_path`` is therefore the half the texture's natural
down-slope points *into*, and it is the half that needs the NORMAL brush.

Parametrised over ridge angle because the defect follows ridge direction: at
the axis-aligned angles the naming happens to line up, so a test covering only
0 and 90 would pass against the broken code.
"""

# ruff: noqa: ARG002

import math

import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
)

from open_garden_planner.ui.canvas.items.polygon_item import _split_path_by_line

#: Ridge angles to exercise. 0/90 are the axis-aligned cases where the
#: arbitrary naming coincidentally lines up; the diagonals are where it does
#: not, so both groups are required for the test to mean anything.
RIDGE_ANGLES = [
    pytest.param(0.0, id="ridge0"),
    pytest.param(45.0, id="ridge45"),
    pytest.param(90.0, id="ridge90"),
    pytest.param(135.0, id="ridge135"),
    pytest.param(180.0, id="ridge180"),
    pytest.param(225.0, id="ridge225"),
    pytest.param(270.0, id="ridge270"),
    pytest.param(315.0, id="ridge315"),
]

SIZE = 400


def _split(angle: float) -> tuple[QPainterPath, QPainterPath]:
    """The two clip halves for a square crossed by a ridge at ``angle``."""
    c = SIZE / 2.0
    rad = math.radians(angle)
    dx, dy = math.cos(rad), math.sin(rad)
    p1 = QPointF(c - dx * 500.0, c - dy * 500.0)
    p2 = QPointF(c + dx * 500.0, c + dy * 500.0)
    square = QPainterPath()
    square.addRect(0.0, 0.0, float(SIZE), float(SIZE))
    return _split_path_by_line(square, QLineF(p1, p2))


def _texture_down_in_world(angle: float) -> tuple[float, float]:
    """Where the texture's +Y (down-slope) points in world space.

    ``normal_tx`` is ``translate . rotate(angle)`` and a brush transform maps
    a world point to its texture coordinate, so texture ``+Y`` corresponds to
    world ``R(angle).(0,1) = (-sin a, cos a)``.
    """
    rad = math.radians(angle)
    return -math.sin(rad), math.cos(rad)


def test_texture_down_is_the_left_perpendicular_of_the_ridge() -> None:
    """The identity the fix rests on, asserted for every angle.

    If this stops holding, the swap in ``_paint_with_ridge`` is no longer the
    right assignment and the reasoning in the module docstring is stale.
    """
    for angle in (a for a in (0.0, 30.0, 45.0, 90.0, 137.0, 180.0, 225.0, 300.0)):
        rad = math.radians(angle)
        left_perpendicular = (-math.sin(rad), math.cos(rad))
        assert _texture_down_in_world(angle) == pytest.approx(left_perpendicular)


@pytest.mark.parametrize("angle", RIDGE_ANGLES)
def test_left_path_is_the_half_the_down_slope_points_into(angle: float) -> None:
    """``left_path`` must be the side the texture's down-slope points into.

    This is the geometric fact the fix encodes, and it is independent of any
    rendering: probe a point one step along the texture's down-slope
    direction and assert it lands in ``left_path``.
    """
    left, right = _split(angle)
    c = SIZE / 2.0
    down_x, down_y = _texture_down_in_world(angle)
    probe = QPointF(c + down_x * 40.0, c + down_y * 40.0)

    in_left = left.contains(probe)
    in_right = right.contains(probe)
    # Decisive: the probe is in exactly one half.
    assert in_left != in_right, (
        f"probe at {probe} was ambiguous for ridge {angle} deg "
        f"(left={in_left}, right={in_right})"
    )
    assert in_left, (
        f"ridge {angle} deg: the texture's down-slope points into right_path, "
        "so left_path is not the down-slope half"
    )


def _direction_probe(angle: float, mirror: bool) -> QImage:
    """Render a two-colour probe through the real brush construction.

    The probe pixmap is RED on its top half and BLUE on its bottom half, so
    BLUE marks the texture's ``+Y`` -- its down-slope -- with no ambiguity
    about tile phase, tiling or antialiasing. This is the measurement that
    settled the fix: correlating the real 256px tile texture was tried first
    and had no discriminating power (peak correlation ~0.03 either way),
    because a few hundred pixels span barely one texture period.
    """
    from PyQt6.QtGui import QPixmap

    pm = QPixmap(64, 64)
    p = QPainter(pm)
    p.fillRect(0, 0, 64, 32, QColor(255, 0, 0))  # texture top    = RED
    p.fillRect(0, 32, 64, 32, QColor(0, 0, 255))  # texture bottom = BLUE
    p.end()

    c = SIZE / 2.0
    tx = QTransform()
    tx.translate(c, c)
    tx.rotate(angle)
    if mirror:
        tx.scale(1.0, -1.0)
    brush = QBrush(pm)
    brush.setTransform(tx)

    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)
    painter.setBrush(brush)
    painter.setPen(QPen(Qt.PenStyle.NoPen))
    painter.drawRect(QRectF(0.0, 0.0, float(SIZE), float(SIZE)))
    painter.end()
    return img


def _sample(img: QImage, angle: float, along_positive_n: bool, distance: int) -> str:
    """Colour at ``centre + distance * n * (+-1)``, where ``n = (-uy, ux)``.

    ``n`` is the left-perpendicular that ``_split_path_by_line`` offsets
    ``left_path`` along, so a BLUE reading here means the texture's
    down-slope points into ``left_path``.
    """
    rad = math.radians(angle)
    nx, ny = -math.sin(rad), math.cos(rad)
    sign = 1.0 if along_positive_n else -1.0
    c = SIZE / 2.0
    x = int(c + nx * distance * sign)
    y = int(c + ny * distance * sign)
    assert 0 <= x < SIZE and 0 <= y < SIZE, "probe point left the canvas"
    return QColor(img.pixel(x, y)).name()


@pytest.mark.parametrize("angle", RIDGE_ANGLES)
def test_both_halves_lap_away_from_the_ridge(angle: float, qtbot: object) -> None:
    """The down-slope invariant, asserted on the real brush construction.

    The NORMAL brush must send the texture's down-slope into ``left_path``
    (the half ``_split_path_by_line`` offsets along ``+n``), and the MIRRORED
    brush into the other half. That is what makes both halves lap away from
    the ridge: the down-slope half keeps the texture's true direction, and
    the up-slope half gets it reflected.

    Before the fix the two were swapped, so whichever half needed the true
    down-slope was the one being mirrored and its laps pointed back up
    toward the ridge.

    ``qtbot`` is required even though unused: a ``QPixmap`` needs a live
    ``QApplication``.
    """
    normal = _direction_probe(angle, mirror=False)
    mirrored = _direction_probe(angle, mirror=True)

    assert _sample(normal, angle, True, 60) == "#0000ff", (
        f"ridge {angle} deg: the normal brush does not send the texture's "
        "down-slope into left_path, so the two halves cannot be assigned as "
        "they are"
    )
    assert _sample(mirrored, angle, False, 60) == "#0000ff", (
        f"ridge {angle} deg: the mirrored brush does not send the down-slope "
        "into the opposite half"
    )


@pytest.mark.parametrize("angle", RIDGE_ANGLES)
def test_the_old_assignment_put_one_half_uphill(qtbot: object, angle: float) -> None:
    """The defect itself: the old code mirrored the down-slope half.

    Asserted against the pre-fix assignment so the regression is pinned to
    the actual behaviour rather than to a rendering artefact. It holds for
    EVERY ridge angle, which is why the bug showed up on both horizontal and
    vertical houses: the naming follows ridge direction, not gravity.
    """
    # Pre-fix: left_path got the MIRRORED brush, right_path the normal one.
    old_left = _direction_probe(angle, mirror=True)
    old_right = _direction_probe(angle, mirror=False)

    # left_path is the +n half. The normal brush sends down-slope there, so
    # the normal brush belongs there -- the old code gave it to right_path
    # instead, leaving left_path (the down-slope half) mirrored.
    assert _sample(old_right, angle, True, 60) == "#0000ff", (
        f"ridge {angle} deg: precondition failed, the normal brush no longer "
        "sends the down-slope into left_path"
    )
    assert _sample(old_left, angle, True, 60) == "#ff0000", (
        f"ridge {angle} deg: the mirrored brush was expected to invert the "
        "down-slope half; if this now reads blue the geometry changed"
    )
