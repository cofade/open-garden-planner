"""The PDF report's plan pages are true to scale and centred (#782).

The overview page drew a bar labelled ``10 m`` whose length was clamped, and
whose length assumed the plan filled the page's width. A plan that is taller
than the page is fitted by its height, so even an unclamped bar was wrong.

Every test here measures the rendered picture: the marker rectangle's pixel
width gives the true scale, and the bar must agree with its own label.
"""

from __future__ import annotations

import re

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from open_garden_planner.core.item_look import adopt_pen, fill_brush
from open_garden_planner.services import pdf_report_service as svc
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

PAGE_W, PAGE_H = 780, 520
MARKER = QColor(255, 0, 255)
BAR_INK = QColor("#333333")

# (canvas width, canvas height) in cm: the default plan, a small plan whose 10 m
# is more than a quarter of the page, a plan taller than the page, a very wide
# plan whose 10 m is under 20 pt, and a small square plot.
CANVASES = [
    (5000, 3000),
    (2000, 1500),
    (2000, 4000),
    (100000, 60000),
    (600, 600),
]


def _to_cm(label: str) -> float:
    match = re.fullmatch(r"([0-9.]+) (cm|m|km)", label)
    assert match, f"unexpected scale bar label {label!r}"
    return float(match.group(1)) * {"cm": 1.0, "m": 100.0, "km": 100000.0}[match.group(2)]


def _columns_of(img: QImage, colour: QColor, rows: range) -> list[int]:
    wanted = colour.rgb()
    return [
        x for x in range(img.width())
        if any(img.pixel(x, y) == wanted for y in rows)
    ]


def _render_overview(
    monkeypatch: pytest.MonkeyPatch, canvas_w: float, canvas_h: float
) -> tuple[QImage, list[str], float]:
    """The overview page as pixels (1 px = 1 pt), its texts, the marker's width in cm."""
    scene = CanvasScene(width_cm=canvas_w, height_cm=canvas_h)
    marker_cm = canvas_w * 0.25
    marker = RectangleItem(canvas_w * 0.25, canvas_h * 0.4, marker_cm, canvas_h * 0.1)
    marker.fill_color = QColor(MARKER)
    marker.setBrush(fill_brush(marker, MARKER))
    adopt_pen(marker, QPen(Qt.PenStyle.NoPen))
    scene.addItem(marker)

    texts: list[str] = []
    draw_text = QPainter.drawText

    def spy(self: QPainter, *args: object) -> object:
        texts.append(str(args[-1]))
        return draw_text(self, *args)

    monkeypatch.setattr(QPainter, "drawText", spy)
    img = QImage(PAGE_W, PAGE_H, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)  # no antialiasing: the bar and the marker have hard ends
    try:
        svc._render_overview(painter, QRectF(0, 0, PAGE_W, PAGE_H), scene, svc.PdfReportOptions())
    finally:
        painter.end()
    return img, texts, marker_cm


def _measure(img: QImage, marker_cm: float) -> tuple[float, int, list[int]]:
    """Points per cm of the drawn plan, the bar's length in pt, the plan's columns."""
    marker_cols = _columns_of(img, MARKER, range(img.height()))
    assert marker_cols, "the marker rectangle is not in the picture"
    marker_px = marker_cols[-1] - marker_cols[0] + 1
    pt_per_cm = marker_px / marker_cm

    # The bar is the lowest horizontal run of bar ink above the title block.
    title_top = img.height() - round(svc._pt(8.0))
    best_row: list[int] = []
    for y in range(title_top - 1, title_top - round(svc._pt(14)), -1):
        cols = _columns_of(img, BAR_INK, range(y, y + 1))
        if len(cols) > len(best_row):
            best_row = cols
    assert best_row, "no scale bar was drawn"
    return pt_per_cm, best_row[-1] - best_row[0], marker_cols


@pytest.mark.parametrize(("canvas_w", "canvas_h"), CANVASES)
def test_the_overview_scale_bar_is_as_long_as_its_label_says(
    qtbot: object, monkeypatch: pytest.MonkeyPatch, canvas_w: float, canvas_h: float
) -> None:
    img, texts, marker_cm = _render_overview(monkeypatch, canvas_w, canvas_h)
    pt_per_cm, bar_pt, _cols = _measure(img, marker_cm)

    labels = [t for t in texts if re.fullmatch(r"[0-9.]+ (cm|m|km)", t)]
    assert len(labels) == 1, f"expected one scale bar label, got {texts}"
    labelled_cm = _to_cm(labels[0])

    # One pixel for each end of the bar, one for the marker's own rounding.
    tolerance = 2.0 + 2.0 * labelled_cm / marker_cm
    assert bar_pt == pytest.approx(labelled_cm * pt_per_cm, abs=tolerance), (
        f"a bar labelled {labels[0]} is {bar_pt} pt long, "
        f"but that distance is {labelled_cm * pt_per_cm:.1f} pt on this page"
    )
    # A bar somebody can read and lay a ruler on: neither a stub nor a banner.
    assert 20.0 - 1.0 <= bar_pt <= PAGE_W * 0.25 + 1.0


@pytest.mark.parametrize(("canvas_w", "canvas_h"), CANVASES)
def test_the_overview_plan_is_centred_on_its_page(
    qtbot: object, monkeypatch: pytest.MonkeyPatch, canvas_w: float, canvas_h: float
) -> None:
    img, _texts, marker_cm = _render_overview(monkeypatch, canvas_w, canvas_h)
    pt_per_cm, _bar_pt, marker_cols = _measure(img, marker_cm)

    # The marker starts a quarter of the way into the plan, so the plan's left
    # edge is one marker width to its left.
    plan_left = marker_cols[0] - marker_cm * pt_per_cm
    plan_right = plan_left + canvas_w * pt_per_cm
    assert plan_left == pytest.approx(PAGE_W - plan_right, abs=3.0), (
        f"the plan sits at {plan_left:.1f}..{plan_right:.1f} pt of a {PAGE_W} pt page"
    )


@pytest.mark.parametrize(
    ("preferred_fits", "pt_per_cm"),
    [(True, 0.156), (False, 0.4), (False, 0.0078), (False, 1.3)],
)
def test_the_picked_distance_fits_and_prefers_ten_metres(
    preferred_fits: bool, pt_per_cm: float
) -> None:
    distance_cm = svc._pick_pdf_scale_distance(pt_per_cm, PAGE_W)
    bar_pt = distance_cm * pt_per_cm
    assert 20.0 <= bar_pt <= PAGE_W * 0.25
    assert (distance_cm == 1000.0) is preferred_fits


def test_the_canvas_and_the_report_share_one_list_of_round_distances() -> None:
    from open_garden_planner.core.measurements import SCALE_BAR_NICE_DISTANCES_CM
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    assert tuple(CanvasView._SCALE_BAR_NICE_DISTANCES) == SCALE_BAR_NICE_DISTANCES_CM
    assert list(SCALE_BAR_NICE_DISTANCES_CM) == sorted(SCALE_BAR_NICE_DISTANCES_CM)
