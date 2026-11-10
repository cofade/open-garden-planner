"""The succession badge is part of the plan's picture, drawn to its scale (#836, point 2).

The badge names the crops that follow in a bed: content of the plan, not an
editing aid. It was a constant-pixel overlay drawn by hand: 47 pixels tall in a
300-dpi PNG (4 mm for three lines), and on a 1200-dpi printer its text was
resolved for the printer and overprinted its own box. It is now painted in the
scene's label pass, with the object labels' size in every export, above the
plants that grow in its bed, and only where it has room on its bed.

Every test measures a rendered picture: the badge is found by its green on a
black bed, its text by being bright.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services import pdf_report_service as svc
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import apply_rect_like_geometry
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.garden_item import SuccessionBadgeItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.dialogs.print_dialog import (
    PRINT_MARGIN_MM,
    GardenPrintManager,
    default_page_layout,
)
from tests.integration.test_pdf_report_pages import _channels, _marked, _pdf_page

CANVAS_W, CANVAS_H = 900.0, 650.0
BED = QRectF(300.0, 250.0, 390.0, 190.0)             # the raised-bed example's bed
CROPS = [("Radish", False), ("Bean (Bush)", True), ("Lettuce", False)]
A4_WIDTH_CM = 29.7
#: A line of text a person reads on paper: 2 mm is a 6 pt line.
MIN_LINE_MM = 2.0
MAX_LINE_MM = 8.0


def _scene(bed_rect: QRectF = BED, crops: list[tuple[str, bool]] | None = None) -> tuple[CanvasScene, RectangleItem]:
    scene = CanvasScene(width_cm=CANVAS_W, height_cm=CANVAS_H)
    bed = RectangleItem(
        bed_rect.x(), bed_rect.y(), bed_rect.width(), bed_rect.height(),
        object_type=ObjectType.GARDEN_BED,
    )
    _marked(bed, QColor(0, 0, 0))
    scene.addItem(bed)
    bed.set_succession_indicator(CROPS if crops is None else crops)
    return scene, bed


def _badge_green(pixels: np.ndarray) -> np.ndarray:
    """Where *pixels* has the badge's green (on a black bed nothing else is green)."""
    blue, green, red = (pixels[:, :, index].astype(np.int16) for index in range(3))
    return (green > 70) & (green > red + 30) & (green > blue + 30)


def _badge_box(pixels: np.ndarray) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the badge's green in *pixels*, or None."""
    mask = _badge_green(pixels)
    lines = np.flatnonzero(mask.sum(axis=1) >= 3)
    columns = np.flatnonzero(mask.sum(axis=0) >= 3)
    if not lines.size or not columns.size:
        return None
    return int(columns[0]), int(lines[0]), int(columns[-1]), int(lines[-1])


def _bright(pixels: np.ndarray) -> np.ndarray:
    return pixels.min(axis=2) > 170


def _png(scene: CanvasScene, tmp_path: Path, dpi: int) -> np.ndarray:
    target = tmp_path / f"plan-{dpi}.png"
    ExportService.export_to_png(scene, target, dpi=dpi, output_width_cm=A4_WIDTH_CM)
    return _channels(QImage(str(target)))


def _bed_in_pixels(pixels: np.ndarray, bed_rect: QRectF = BED) -> tuple[float, float, float, float]:
    """The bed's (left, top, right, bottom) in a picture of the whole plan, Y up."""
    scale = pixels.shape[1] / CANVAS_W
    return (bed_rect.left() * scale, (CANVAS_H - bed_rect.bottom()) * scale,
            bed_rect.right() * scale, (CANVAS_H - bed_rect.top()) * scale)


def _assert_badge_reads(pixels: np.ndarray, mm_per_px: float, where: str,
                        bed: tuple[float, float, float, float] | None = None) -> tuple[int, int, int, int]:
    box = _badge_box(pixels)
    assert box is not None, f"{where}: no succession badge in the picture"
    left, top, right, bottom = box
    # Three lines and the padding of about one more.
    line_mm = (bottom - top + 1) * mm_per_px / (len(CROPS) + 1)
    assert MIN_LINE_MM <= line_mm <= MAX_LINE_MM, (
        f"{where}: a line of the badge is {line_mm:.2f} mm tall"
    )
    # Its text is in it: bright ink inside the box ...
    inside = _bright(pixels[top:bottom + 1, left:right + 1])
    assert 0.02 < inside.mean() < 0.6, f"{where}: the badge holds no readable text"
    # ... and none of it beside the box, on the black bed.
    if bed is not None:
        bed_left, bed_top, bed_right, bed_bottom = (round(value) for value in bed)
        around = _bright(pixels[bed_top + 2:bed_bottom - 2, bed_left + 2:bed_right - 2]).copy()
        around[max(0, top - bed_top - 4):bottom - bed_top + 2, max(0, left - bed_left - 4):right - bed_left + 2] = False
        assert not around.any(), f"{where}: the badge's text runs out of its box"
        assert left >= bed_left - 2 and right <= bed_right + 2, f"{where}: the badge is beside its bed"
        assert top >= bed_top - 2 and bottom <= bed_bottom + 2, f"{where}: the badge is above or below its bed"
    return box


# ---------------------------------------------------------------------------
# Exports: PNG, the report's plan pages, a printout
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dpi", [150, 300])
def test_the_badge_is_legible_in_a_png(qtbot, tmp_path: Path, dpi: int) -> None:
    scene, _bed = _scene()
    pixels = _png(scene, tmp_path, dpi)
    _assert_badge_reads(pixels, 25.4 / dpi, f"PNG at {dpi} dpi", _bed_in_pixels(pixels))


def test_the_badge_has_one_size_on_paper_at_every_resolution(qtbot, tmp_path: Path) -> None:
    scene, _bed = _scene()
    heights = {}
    for dpi in (150, 300):
        box = _badge_box(_png(scene, tmp_path, dpi))
        assert box is not None
        heights[dpi] = (box[3] - box[1] + 1) * 25.4 / dpi
    assert heights[300] == pytest.approx(heights[150], rel=0.08), heights


def test_an_export_leaves_the_badge_as_it_was_on_the_canvas(qtbot, tmp_path: Path) -> None:
    scene, bed = _scene()
    badge = bed._succession_badge_item
    assert isinstance(badge, SuccessionBadgeItem)
    before = (badge.font().pointSizeF(), QRectF(badge.boundingRect()))
    _png(scene, tmp_path, 300)
    assert (badge.font().pointSizeF(), QRectF(badge.boundingRect())) == before


@pytest.mark.parametrize("page", ["overview", "bed"])
def test_the_badge_is_legible_on_the_reports_plan_pages(qtbot, page: str) -> None:
    scene, bed = _scene()
    canvas = scene.canvas_rect
    source = canvas if page == "overview" else svc._bed_frame(svc._bed_rect(bed), canvas)
    frame = svc._fit_rect(source, QRectF(0, 0, 770, 480))            # an A4 page's worth, points
    picture = svc._scene_to_image(scene, source, frame)
    pixels = _channels(picture)
    mm_per_px = 25.4 / svc.PLAN_RENDER_DPI
    _assert_badge_reads(pixels, mm_per_px, f"report {page} page")


@pytest.mark.parametrize("denominator", [0, 50])
def test_the_badge_is_legible_and_whole_in_a_printout(qtbot, tmp_path: Path, denominator: int) -> None:
    """A 1200-dpi printer resolves a font in points for itself: the text stays in its box."""
    from PyQt6.QtPrintSupport import QPrinter

    scene, _bed = _scene()
    target = tmp_path / "print.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(target))
    printer.setPageLayout(default_page_layout())
    manager = GardenPrintManager(scene, project_name="Plan")
    manager.configure(scale_denominator=denominator, include_grid=False, include_labels=True,
                      include_legend=False)
    manager._render_to_printer(printer)
    del printer

    dpi = 200
    mm = dpi / 25.4
    pixels = _channels(_pdf_page(target, 0, dpi))
    printable_w, printable_h = 297.0 - 2 * PRINT_MARGIN_MM, 210.0 - 2 * PRINT_MARGIN_MM
    if denominator:
        # 9 m x 6.5 m at 1:50 is 180 mm x 130 mm: one sheet, from its top-left corner.
        paper_per_cm, offset_x, offset_y = 10.0 / denominator, 0.0, 0.0
    else:
        paper_per_cm = min(printable_w / CANVAS_W, printable_h / CANVAS_H)
        offset_x = (printable_w - CANVAS_W * paper_per_cm) / 2.0
        offset_y = (printable_h - CANVAS_H * paper_per_cm) / 2.0
    bed = (
        (PRINT_MARGIN_MM + offset_x + BED.left() * paper_per_cm) * mm,
        (PRINT_MARGIN_MM + offset_y + (CANVAS_H - BED.bottom()) * paper_per_cm) * mm,
        (PRINT_MARGIN_MM + offset_x + BED.right() * paper_per_cm) * mm,
        (PRINT_MARGIN_MM + offset_y + (CANVAS_H - BED.top()) * paper_per_cm) * mm,
    )
    _assert_badge_reads(pixels, 1.0 / mm, f"print at 1:{denominator or 'fit'}", bed)


# ---------------------------------------------------------------------------
# The canvas: constant size, above the plants, only where it has room
# ---------------------------------------------------------------------------

def _view(scene: CanvasScene, qtbot, zoom: float) -> CanvasView:
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 760)
    view.show()
    qtbot.waitExposed(view)
    view.fit_in_view()
    view.scale(zoom, zoom)
    view.centerOn(BED.center())
    qtbot.wait(50)
    return view


def _grab(view: CanvasView) -> np.ndarray:
    """The bed as the viewport shows it, and a few pixels around it.

    Only the bed: the view paints things of its own around the plan, and on
    the black bed the badge is the one thing that is green.
    """
    frame = view.viewportTransform().mapRect(BED).toAlignedRect().adjusted(-6, -6, 6, 6)
    return _channels(view.viewport().grab(frame).toImage())


def test_the_badge_keeps_its_size_on_screen_while_it_has_room(qtbot) -> None:
    scene, _bed = _scene()
    heights = []
    for zoom in (1.0, 2.0):
        view = _view(scene, qtbot, zoom)
        box = _badge_box(_grab(view))
        assert box is not None, f"no badge at zoom x{zoom:g}"
        heights.append(box[3] - box[1] + 1)
        view.close()
    assert abs(heights[0] - heights[1]) <= 1, heights
    assert 30 <= heights[0] <= 70, "three lines of small text and their padding"


def test_the_badge_is_left_out_where_it_would_cover_its_bed(qtbot) -> None:
    """Zoomed far out the bed is smaller than its badge: the badge is not drawn."""
    scene, bed = _scene()
    view = _view(scene, qtbot, 0.2)
    world = view.viewportTransform()
    on_screen = world.mapRect(bed.sceneBoundingRect())
    assert on_screen.width() < 140, "the test's zoom leaves the bed large"
    assert _badge_box(_grab(view)) is None, f"the badge covers a bed of {on_screen.width():.0f} px"


def test_what_stands_in_the_bed_does_not_cover_the_badge(qtbot) -> None:
    """The bed's plants are drawn after the bed; the badge is drawn after them."""
    scene, _bed = _scene()
    view = _view(scene, qtbot, 1.0)
    alone = int(_badge_green(_grab(view)).sum())
    assert alone > 500
    view.close()

    # Something on the badge's corner of the bed, drawn after the bed (white:
    # a plant's own green would be taken for the badge's).
    pot = CircleItem(BED.left() + 30, BED.top() + 30, 28)
    _marked(pot, QColor(255, 255, 255))
    scene.addItem(pot)
    view = _view(scene, qtbot, 1.0)
    covered = int(_badge_green(_grab(view)).sum())
    assert abs(covered - alone) <= 0.01 * alone, (
        f"what stands in the bed is painted over the badge: {covered} of {alone} px of it show"
    )


def test_the_badge_follows_its_bed_when_the_bed_is_resized(qtbot, tmp_path: Path) -> None:
    scene, bed = _scene()
    smaller = QRectF(BED.left() + 150, BED.top() + 60, BED.width() - 150, BED.height() - 60)
    apply_rect_like_geometry(bed, {
        "rect_x": smaller.x(), "rect_y": smaller.y(), "width": smaller.width(),
        "height": smaller.height(), "pos_x": 0.0, "pos_y": 0.0,
    })
    pixels = _png(scene, tmp_path, 150)
    _assert_badge_reads(pixels, 25.4 / 150, "after a resize", _bed_in_pixels(pixels, smaller))


def test_a_long_plan_says_how_many_more_in_the_ui_language(qtbot) -> None:
    from PyQt6.QtCore import QCoreApplication

    from tests.integration.test_export_followups import _Catalogue

    crops = [(f"Crop {index}", False) for index in range(7)]
    catalogue = _Catalogue({("SuccessionBadgeItem", "+{count} more"): "+{count} weitere"})
    QCoreApplication.installTranslator(catalogue)
    try:
        _scene_, bed = _scene(crops=crops)
        rows = [text for text, _current, _overflow in bed._succession_badge_item._rendered_rows()]
    finally:
        QCoreApplication.removeTranslator(catalogue)
    assert rows[-1] == "+3 weitere"
    assert len(rows) == 5


def test_a_plain_scene_still_shows_the_badge(qtbot) -> None:
    """Outside a CanvasScene nothing runs the label pass: the item paints itself."""
    from PyQt6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
    bed = RectangleItem(BED.x(), BED.y(), BED.width(), BED.height(), object_type=ObjectType.GARDEN_BED)
    _marked(bed, QColor(0, 0, 0))
    scene.addItem(bed)
    bed.set_succession_indicator(CROPS)
    image = QImage(900, 650, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 900, 650), QRectF(0, 0, CANVAS_W, CANVAS_H))
    painter.end()
    assert _badge_box(_channels(image)) is not None


def test_the_minimap_blanks_the_badge_as_it_blanks_every_screen_space_item(qtbot) -> None:
    """The minimap suppresses constant-size items with ``ItemHasNoContents``."""
    from PyQt6.QtWidgets import QGraphicsItem

    scene, bed = _scene()

    def picture() -> np.ndarray:
        image = QImage(900, 650, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.translate(0, 650)
        painter.scale(1.0, -1.0)
        scene.render(painter, QRectF(0, 0, 900, 650), scene.canvas_rect)
        painter.end()
        return _channels(image)

    assert _badge_box(picture()) is not None
    bed._succession_badge_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
    assert _badge_box(picture()) is None


def test_the_badge_is_in_the_svg_as_text_at_the_labels_size(qtbot, tmp_path: Path) -> None:
    import re

    from PyQt6.QtSvg import QSvgRenderer

    from open_garden_planner.services.svg_export import SVG_UNITS_PER_INCH

    scene, bed = _scene()
    bed.name = "Bed one"                               # an object label to compare with
    target = tmp_path / "plan.svg"
    ExportService.export_to_svg(scene, target, output_width_cm=A4_WIDTH_CM)
    text = target.read_text(encoding="utf-8")

    def font_size_of(word: str) -> float:
        """The font size of the group that holds the text *word*, in SVG units."""
        at = text.index(word)
        sizes = re.findall(r'font-size="([0-9.]+)"', text[:at])
        assert sizes, f"{word!r} is not text in the SVG"
        return float(sizes[-1])

    crop = font_size_of("Radish")
    assert "Lettuce" in text
    line_mm = crop / SVG_UNITS_PER_INCH * 25.4
    assert MIN_LINE_MM <= line_mm <= MAX_LINE_MM, f"the badge's text is {line_mm:.2f} mm in the SVG"
    # ... which is the size of an object's name (a whole pixel of it at most apart).
    assert crop == pytest.approx(font_size_of("Bed one"), abs=1.0)

    # The box itself, rasterised. Its text is not measured here: QSvgRenderer is
    # not a browser and sets the text in a substitute typeface (section 8.36).
    dpi = 150
    width = round(A4_WIDTH_CM / 2.54 * dpi)
    height = round(width * CANVAS_H / CANVAS_W)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    QSvgRenderer(str(target)).render(painter)
    painter.end()
    pixels = _channels(image)
    box = _badge_box(pixels)
    assert box is not None
    bed_left, bed_top, bed_right, bed_bottom = _bed_in_pixels(pixels)
    assert bed_left - 2 <= box[0] and box[2] <= bed_right + 2
    assert bed_top - 2 <= box[1] and box[3] <= bed_bottom + 2
    assert MIN_LINE_MM <= (box[3] - box[1] + 1) * 25.4 / dpi / (len(CROPS) + 1) <= MAX_LINE_MM
