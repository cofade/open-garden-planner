"""A vector export must not carry bitmap detail no printer can show (#850).

``core.raster_resolution.raster_level`` rounds the painter's scale UP to a power
of two so one pixmap serves a whole zoom level. Right for a canvas, wasteful for
an export: on a page whose scale falls just above the previous level the file
carries 1.3-1.7x the pixels a viewer can see (measured on the bundled examples).
``services/svg_export._fit_picture`` cuts each picture to its own device size —
and only down, never up, so a shadow feather keeps its pixels.
"""

from __future__ import annotations

import base64
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPixmap, QTransform

from open_garden_planner.services.svg_export import (
    _fit_picture,
    _PixmapOp,
    _State,
    write_svg,
)


def _state(scale: float = 1.0, rotation_deg: float = 0.0) -> _State:
    transform = QTransform.fromScale(scale, scale)
    if rotation_deg:
        transform = QTransform().rotate(rotation_deg) * transform
    return _State(
        transform=transform,
        pen=QPen(Qt.PenStyle.NoPen),
        brush=QBrush(Qt.BrushStyle.NoBrush),
        brush_origin=QPointF(),
        opacity=1.0,
        clip=None,
    )


def _picture(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#c03020"))
    return pixmap


def _embedded_pixel_sizes(path) -> list[tuple[int, int]]:
    text = path.read_text(encoding="utf-8")
    sizes = []
    for payload in re.findall(r"base64,([^\"]+)", text):
        header = base64.b64decode(payload[:64])
        sizes.append((int.from_bytes(header[16:20], "big"),
                      int.from_bytes(header[20:24], "big")))
    return sizes


def test_a_picture_finer_than_its_place_is_cut_to_the_export(qtbot, tmp_path) -> None:
    """The wiring: ``write_svg`` fits, so every writer of a file gets the cut."""
    path = tmp_path / "plan.svg"
    op = _PixmapOp(_state(), QRectF(0.0, 0.0, 32.0, 32.0), _picture(128))
    write_svg([op], path, 100.0, 100.0)
    assert _embedded_pixel_sizes(path) == [(32, 32)]


def test_the_device_size_is_taken_through_the_state_transform(qtbot, tmp_path) -> None:
    """A sprite is drawn in plan units; only the transform says how big it lands.

    8 units at a 4x device scale is 32 units of page: a 128-pixel picture is cut to
    32 even though the target rectangle is only 8 wide.
    """
    path = tmp_path / "plan.svg"
    op = _PixmapOp(_state(scale=4.0), QRectF(0.0, 0.0, 8.0, 8.0), _picture(128))
    write_svg([op], path, 100.0, 100.0)
    assert _embedded_pixel_sizes(path) == [(32, 32)]


def test_a_turned_picture_is_measured_by_its_edge_not_its_bounding_box() -> None:
    """A rotation inflates the axis-aligned box but not the picture's own edge.

    Measuring the box (what an AABB does) would let a 30-degree sprite keep its
    oversampling: the box of a 40-unit square at 30 degrees is 54.6 units.
    """
    square = QRectF(0.0, 0.0, 40.0, 40.0)
    turned = _PixmapOp(_state(rotation_deg=30.0), square, _picture(200))
    assert turned.state.transform.mapRect(square).width() > 50.0
    fitted = _fit_picture(turned)
    assert max(fitted.pixmap.width(), fitted.pixmap.height()) == 40


def test_a_picture_already_at_the_export_s_size_is_untouched(qtbot, tmp_path) -> None:
    """A shadow feather is one pixel per unit: nothing is enlarged or re-encoded."""
    path = tmp_path / "plan.svg"
    op = _PixmapOp(_state(), QRectF(0.0, 0.0, 64.0, 64.0), _picture(64))
    same = _fit_picture(op)
    assert same is op
    write_svg([op], path, 100.0, 100.0)
    assert _embedded_pixel_sizes(path) == [(64, 64)]


def test_a_repeated_picture_is_embedded_once_and_placed_twice(qtbot, tmp_path) -> None:
    """#850: a texture tile or a species sprite is written once, drawn by <use>.

    The referenced <image> keeps its own x/y, so the <use> carries only the
    difference; a wrong delta would move the second copy (the balcony's
    regression in the fidelity suite).
    """
    import re

    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    path = tmp_path / "repeated.svg"
    picture = _picture(16)
    first = _PixmapOp(_state(), QRectF(0.0, 0.0, 16.0, 16.0), picture)
    second = _PixmapOp(_state(), QRectF(40.0, 0.0, 16.0, 16.0), picture)
    write_svg([first, second], path, 100.0, 100.0)
    text = path.read_text(encoding="utf-8")
    assert len(re.findall(r"base64,", text)) == 1
    uses = re.findall(r"<use\b[^>]*>", text)
    assert len(uses) == 1
    assert 'x="40"' in uses[0]

    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    QSvgRenderer(str(path)).render(painter, QRectF(0, 0, 100, 100))
    painter.end()
    assert image.pixelColor(5, 5).name() == "#c03020"
    assert image.pixelColor(45, 5).name() == "#c03020"


def test_distinct_pictures_are_not_merged(qtbot, tmp_path) -> None:
    import re

    path = tmp_path / "distinct.svg"
    red = _PixmapOp(_state(), QRectF(0.0, 0.0, 16.0, 16.0), _picture(16))
    blue_pixmap = QPixmap(16, 16)
    blue_pixmap.fill(QColor("#2040c0"))
    blue = _PixmapOp(_state(), QRectF(40.0, 0.0, 16.0, 16.0), blue_pixmap)
    write_svg([red, blue], path, 100.0, 100.0)
    text = path.read_text(encoding="utf-8")
    assert len(re.findall(r"base64,", text)) == 2
    assert "<use" not in text


def test_a_picture_keeps_its_aspect_ratio() -> None:
    op = _PixmapOp(_state(), QRectF(0.0, 0.0, 40.0, 20.0), _picture(200))
    fitted = _fit_picture(op)
    assert (fitted.pixmap.width(), fitted.pixmap.height()) == (40, 40)


def test_a_non_finite_target_never_aborts_the_export() -> None:
    """A degenerate draw is passed through: the fit is not a reason to fail an export.

    ``math.floor(width * nan)`` raises ``ValueError`` and ``inf`` raises
    ``OverflowError``; a corrupt or emptied target must not take the whole SVG
    export down with it (``core.sprite_raster`` guards the same arithmetic).
    """
    for bad in (float("nan"), float("inf")):
        for target in (QRectF(0.0, 0.0, bad, 10.0), QRectF(0.0, 0.0, 10.0, bad),
                       QRectF(0.0, 0.0, bad, bad)):
            op = _PixmapOp(_state(), target, _picture(64))
            assert _fit_picture(op) is op, (bad, target)
    for target in (QRectF(0.0, 0.0, 0.0, 10.0), QRectF(0.0, 0.0, 10.0, 0.0)):
        op = _PixmapOp(_state(), target, _picture(64))
        assert _fit_picture(op) is op
    flipped = _fit_picture(_PixmapOp(_state(), QRectF(0.0, 0.0, -10.0, 10.0), _picture(64)))
    assert (flipped.pixmap.width(), flipped.pixmap.height()) == (10, 10)
    for bad_scale in (0.0, float("nan"), float("inf")):
        op = _PixmapOp(_state(scale=bad_scale), QRectF(0.0, 0.0, 10.0, 10.0), _picture(64))
        assert _fit_picture(op) is op
    tiny = _PixmapOp(_state(), QRectF(0.0, 0.0, 0.2, 0.2), _picture(64))
    fitted = _fit_picture(tiny)
    assert (fitted.pixmap.width(), fitted.pixmap.height()) == (1, 1)
