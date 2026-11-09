"""The PDF report's pages and the printout are sharp, complete and inside their frames (#788).

Five defects, one group of tests each, every one measured on what is rendered:

1. plan pictures were 72-dpi bitmaps;
2. the plant list stopped after one page without a word, and a plant with a
   species but no name of its own had a blank Name cell;
3. a bed-detail page blew a 40 cm pot up to a page of blur;
4. a print tile painted shadows on its own margin and footer;
5. the legend page was one "Layer 1" swatch, and the cover of a plan opened
   from an example said "Untitled" or a file stem.
"""

from __future__ import annotations

import ast
import math
import re
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QMarginsF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPainterPath, QPen
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPrintSupport import QPrinter

from open_garden_planner.core.item_look import adopt_pen, fill_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services import pdf_report_service as svc
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowOverlayItem
from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager

EXAMPLES = ["family-garden", "balcony", "food-forest", "raised-bed"]
PAPERS = [("A4", "landscape"), ("A4", "portrait"), ("A3", "landscape"), ("Letter", "portrait")]
PAGE = QRectF(0, 0, 780, 520)            # a page as pixels: 1 px = 1 pt
MARKER = QColor(255, 0, 255)
SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"


def _channels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    buffer = image.bits()
    buffer.setsize(image.sizeInBytes())
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].copy()   # blue, green, red; own memory


def _is_magenta(pixels: np.ndarray) -> np.ndarray:
    return (pixels[:, :, 2] > 170) & (pixels[:, :, 0] > 170) & (pixels[:, :, 1] < 100)


def _marked(item: RectangleItem | CircleItem, colour: QColor = MARKER) -> None:
    item.fill_color = QColor(colour)
    item.setBrush(fill_brush(item, colour))
    adopt_pen(item, QPen(Qt.PenStyle.NoPen))


def _page_image(scene: CanvasScene, page_type: str, data: object, monkeypatch: pytest.MonkeyPatch | None = None,
                options: svc.PdfReportOptions | None = None) -> tuple[QImage, list[str]]:
    """One report page painted as pixels (1 px = 1 pt), and the texts drawn on it."""
    texts: list[str] = []
    if monkeypatch is not None:
        draw_text = QPainter.drawText

        def spy(self: QPainter, *args: object) -> object:
            texts.append(str(args[-1]))
            return draw_text(self, *args)

        monkeypatch.setattr(QPainter, "drawText", spy)
    image = QImage(int(PAGE.width()), int(PAGE.height()), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        svc.PdfReportService.render_page(
            painter, PAGE, scene, options or svc.PdfReportOptions(), page_type, data
        )
    finally:
        painter.end()
    return image, texts


def _plant(x: float, y: float, kind: ObjectType, name: str = "", species: str = "") -> CircleItem:
    metadata = {"plant_species": {"common_name": species, "scientific_name": ""}} if species else None
    return CircleItem(x, y, 15, object_type=kind, name=name, metadata=metadata)


def _pdf_page_count(path: Path) -> int:
    document = QPdfDocument(None)
    document.load(str(path))
    count = document.pageCount()
    document.close()
    return count


def _pdf_page(path: Path, page: int, dpi: int = 100) -> QImage:
    document = QPdfDocument(None)
    document.load(str(path))
    size = document.pagePointSize(page)
    picture = document.render(page, QSize(round(size.width() * dpi / 72), round(size.height() * dpi / 72)))
    flat = QImage(picture.size(), QImage.Format.Format_RGB32)
    flat.fill(QColor("white"))
    painter = QPainter(flat)
    painter.drawImage(0, 0, picture)
    painter.end()
    document.close()
    return flat


# ---------------------------------------------------------------------------
# 1. Plan pictures are sharp at print size
# ---------------------------------------------------------------------------

def _striped_scene() -> tuple[CanvasScene, int]:
    """A plan with 40 black bars, 2 cm wide, 4 cm apart: a 1.4 mm pitch on A4."""
    scene = CanvasScene(width_cm=800, height_cm=500)
    bars = 40
    for index in range(bars):
        bar = RectangleItem(300 + index * 4.0, 200, 2.0, 100)
        _marked(bar, QColor(0, 0, 0))
        scene.addItem(bar)
    return scene, bars


def test_a_plan_picture_resolves_what_a_printer_can_print(qtbot) -> None:
    scene, bars = _striped_scene()
    frame = svc._fit_rect(scene.canvas_rect, QRectF(0, 0, 770, 480))     # an A4 page's worth
    picture = svc._scene_to_image(scene, scene.canvas_rect, frame)

    assert picture.width() >= frame.width() / 72.0 * 300 - 1               # 300 dpi of the frame
    row = _channels(picture)[picture.height() // 2, :, 1]
    dark = row < 128
    runs = int(np.count_nonzero(dark[1:] & ~dark[:-1]) + int(dark[0]))
    assert runs == bars, f"{runs} of {bars} bars are told apart"


@pytest.mark.parametrize(("paper", "orientation"), PAPERS)
def test_the_written_pdf_holds_its_plan_picture_at_print_resolution(
    qtbot, tmp_path: Path, paper: str, orientation: str
) -> None:
    scene, _bars = _striped_scene()
    target = tmp_path / "report.pdf"
    options = svc.PdfReportOptions(
        paper_size=paper, orientation=orientation, include_cover=False, include_overview=True,
        include_plant_list=False, include_legend=False,
    )
    svc.PdfReportService.generate(scene, options, target)
    raw = target.read_bytes()
    widths = [int(value) for value in re.findall(rb"/Width (\d+)", raw)]
    page = re.search(rb"/MediaBox \[0 0 ([0-9.]+) ([0-9.]+)\]", raw)
    assert widths and page, "no picture or no page in the PDF"
    # The plan cannot be wider than the page: a 300-dpi picture of even half
    # the page's width has more columns than the whole page has at 72 dpi x 2.
    assert max(widths) >= float(page.group(1)) * 2.0, (max(widths), page.group(1))
    frame_width_pt = float(page.group(1)) - 2 * svc._pt(svc._MARGIN_MM)
    assert max(widths) / (frame_width_pt / 72.0) <= 300.5                  # and no more than 300 dpi


# ---------------------------------------------------------------------------
# 2. The plant list: every plant, with a name, over as many pages as needed
# ---------------------------------------------------------------------------

def _planted_scene(count: int) -> CanvasScene:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    kinds = [ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL]
    for index in range(count):
        x, y = 50 + (index % 20) * 90, 50 + (index // 20) * 90
        if index % 3 == 0:
            scene.addItem(_plant(x, y, kinds[index % 3], name=f"Own name {index}"))
        else:
            scene.addItem(_plant(x, y, kinds[index % 3], species=f"Species {index}"))
    return scene


@pytest.mark.parametrize("count", [0, 5, 21, 22, 70, 200])
def test_the_plant_list_shows_every_plant_with_a_name(
    qtbot, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    scene = _planted_scene(count)
    options = svc.PdfReportOptions(include_cover=False, include_overview=False, include_legend=False)
    pages = svc.PdfReportService.plan_pages(scene, options, PAGE)
    per_page = svc._table_rows_per_page(PAGE)
    assert len(pages) == max(1, math.ceil(count / per_page))

    drawn: list[str] = []
    for number, (kind, data) in enumerate(pages, start=1):
        assert kind == "plant_list"
        image, texts = _page_image(scene, kind, data, monkeypatch)
        monkeypatch.undo()
        drawn.extend(texts)
        if len(pages) > 1:
            assert any(f"{number}" in text and f"{len(pages)}" in text and "Plant List" in text
                       for text in texts), texts[:3]
        # No row is painted over the foot of the page.
        foot = _channels(image)[int(PAGE.height() - svc._pt(svc._TABLE_FOOT_MM)) + 1:, :, :]
        assert (foot == 255).all(), "a row runs off the page"

    expected = [f"Own name {i}" if i % 3 == 0 else f"Species {i}" for i in range(count)]
    for name in expected:
        assert drawn.count(name) == 1, name
    assert "" not in [text for text in drawn if text in expected]


@pytest.mark.parametrize(("paper", "orientation"), PAPERS)
def test_the_page_count_and_the_progress_follow_the_plant_list(
    qtbot, tmp_path: Path, paper: str, orientation: str
) -> None:
    scene = _planted_scene(90)
    target = tmp_path / "report.pdf"
    options = svc.PdfReportOptions(paper_size=paper, orientation=orientation)
    calls: list[tuple[int, int]] = []
    svc.PdfReportService.generate(scene, options, target, lambda current, total: calls.append((current, total)))
    pages = _pdf_page_count(target)
    assert pages >= 5                                   # cover, overview, >= 2 list pages, legend
    assert calls[-1] == (pages, pages)
    assert [current for current, _total in calls] == list(range(pages + 1))
    assert {total for _current, total in calls} == {pages}


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_plant_of_a_bundled_example_is_listed_with_a_name(qtbot, example: str) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    plants = svc._plant_items(scene)
    assert plants, "the example has no plants"
    options = svc.PdfReportOptions(include_cover=False, include_overview=False, include_legend=False)
    pages = svc.PdfReportService.plan_pages(scene, options, PAGE)
    rows = [row for _kind, (page_rows, *_rest) in pages for row in page_rows]
    assert len(rows) == len(plants)
    assert all(name.strip() and name != "Unnamed" for name, *_cells in rows), [r[0] for r in rows][:8]


# ---------------------------------------------------------------------------
# 3. Bed-detail pages have a sensible frame
# ---------------------------------------------------------------------------

def _pot(x: float, y: float, name: str, radius: float = 20.0) -> CircleItem:
    pot = CircleItem(x, y, radius, object_type=ObjectType.CONTAINER_ROUND, name=name)
    _marked(pot)
    return pot


def test_a_small_pot_is_not_blown_up_to_a_page(qtbot) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    scene.addItem(_pot(1000, 700, "Pot"))
    (group,) = svc._bed_groups(scene)
    image, _texts = _page_image(scene, "bed", group)
    columns = np.flatnonzero(_is_magenta(_channels(image)).any(axis=0))
    assert columns.size, "the pot is not on its page"
    width = int(columns[-1] - columns[0] + 1)
    # A 40 cm pot in a frame of at least 150 cm: under a third of the picture.
    assert width < 0.3 * PAGE.width(), width
    assert width > 0.05 * PAGE.width(), width        # and still plainly there


def test_small_pots_side_by_side_share_one_page_and_far_ones_do_not(qtbot) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    for index in range(3):
        scene.addItem(_pot(300 + index * 70, 400, f"Pot {index + 1}"))
    scene.addItem(_pot(1700, 1200, "Pot 9"))
    bed = RectangleItem(900, 300, 400, 150, object_type=ObjectType.RAISED_BED, name="Bed 1")
    scene.addItem(bed)
    names = [[member.name for member in group] for group in svc._bed_groups(scene)]
    assert sorted(names) == sorted([["Bed 1"], ["Pot 1", "Pot 2", "Pot 3"], ["Pot 9"]])
    assert names == sorted(names, key=lambda group: group[0])     # in reading order


@pytest.mark.parametrize(
    ("bed", "canvas"),
    [
        (QRectF(100, 100, 40, 40), QRectF(0, 0, 2000, 1500)),      # a pot
        (QRectF(10, 20, 40, 900), QRectF(0, 0, 2000, 1500)),       # a strip along the edge
        (QRectF(200, 200, 1500, 80), QRectF(0, 0, 2000, 1500)),    # a long border
        (QRectF(50, 50, 300, 200), QRectF(0, 0, 400, 300)),        # a bed on a balcony
        (QRectF(0, 0, 60, 60), QRectF(0, 0, 100, 100)),            # a plan smaller than the minimum
    ],
)
def test_a_bed_frame_shows_the_bed_in_context_inside_the_plan(qtbot, bed: QRectF, canvas: QRectF) -> None:
    frame = svc._bed_frame(bed, canvas)
    assert canvas.contains(frame) or (frame.width() >= canvas.width() - 1e-6)
    assert frame.united(bed) == frame or not canvas.contains(bed.adjusted(-20, -20, 20, 20))
    assert frame.width() >= min(svc._BED_MIN_EXTENT_CM, canvas.width()) - 1e-6
    assert frame.height() >= min(svc._BED_MIN_EXTENT_CM, canvas.height()) - 1e-6
    short, long = sorted((frame.width(), frame.height()))
    if long < min(canvas.width(), canvas.height()):
        assert short / long >= svc._BED_MIN_ASPECT - 1e-6


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_bed_of_a_bundled_example_gets_a_readable_page(qtbot, example: str) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    groups = svc._bed_groups(scene)
    beds = svc.PdfReportService._find_beds(scene)
    assert sorted(id(member) for group in groups for member in group) == sorted(id(bed) for bed in beds)
    for group in groups:
        united = QRectF()
        for member in group:
            united = united.united(svc._bed_rect(member))
        frame = svc._bed_frame(united, scene.canvas_rect)
        # Nothing is magnified beyond 1:4 on an A4 page (26 cm of paper).
        assert frame.width() >= min(svc._BED_MIN_EXTENT_CM, scene.width_cm) - 1e-6
        assert frame.intersects(united)


# ---------------------------------------------------------------------------
# 4. Nothing paints outside its frame
# ---------------------------------------------------------------------------

def _shadowed_scene() -> CanvasScene:
    """A plan under one shadow that covers all of it and runs far past its edges."""
    scene = CanvasScene(width_cm=2400, height_cm=1600)
    shadow = SunShadowOverlayItem()
    shadow.set_clip_rect(scene.canvas_rect)
    outline = QPainterPath()
    outline.addRect(QRectF(-3000, -3000, 9000, 9000))
    shadow.set_shadow_path(outline)
    scene.addItem(shadow)
    return scene


def _shaded(image: QImage, like: tuple[int, int]) -> np.ndarray:
    """Where *image* has the colour it has at pixel *like*: the shadowed plan."""
    pixels = _channels(image).astype(np.int16)
    wanted = pixels[like[1], like[0]]
    assert wanted.max() < 235, "the sample is not on the shadowed plan"
    return (np.abs(pixels - wanted) < 12).all(axis=2)


def _extent(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the area *mask* fills.

    A line counts when a fifth of it is set and so is a neighbour: a footer's
    grey text and its hairline rule have the shadow's grey in their
    antialiasing — a pixel here and there, or one line of them.
    """
    def solid(share: np.ndarray) -> np.ndarray:
        on = share > 0.2
        beside = np.zeros_like(on)
        beside[1:] |= on[:-1]
        beside[:-1] |= on[1:]
        return np.flatnonzero(on & beside)

    columns, lines = solid(mask.mean(axis=0)), solid(mask.mean(axis=1))
    assert columns.size and lines.size, "the shadowed plan is not in the picture"
    return int(columns[0]), int(lines[0]), int(columns[-1]), int(lines[-1])


PRINT_MARGIN_MM = 10.0
PRINTABLE_W_MM, PRINTABLE_H_MM = 297.0 - 2 * PRINT_MARGIN_MM, 210.0 - 2 * PRINT_MARGIN_MM


def _printed_pages(scene: CanvasScene, tmp_path: Path, denominator: int) -> tuple[Path, int]:
    target = tmp_path / "print.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(target))
    printer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
        QMarginsF(PRINT_MARGIN_MM, PRINT_MARGIN_MM, PRINT_MARGIN_MM, PRINT_MARGIN_MM),
        QPageLayout.Unit.Millimeter,
    ))
    manager = GardenPrintManager(scene, project_name="Plan")
    manager.configure(scale_denominator=denominator, include_grid=False, include_labels=True,
                      include_legend=True)
    manager._render_to_printer(printer)
    del printer
    return target, _pdf_page_count(target)


@pytest.mark.parametrize("denominator", [0, 50, 100])
def test_a_print_tile_paints_nothing_on_its_margin_or_footer(qtbot, tmp_path: Path, denominator: int) -> None:
    scene = _shadowed_scene()
    target, pages = _printed_pages(scene, tmp_path, denominator)
    dpi = 100
    mm = dpi / 25.4
    content_h = PRINTABLE_H_MM - GardenPrintManager.LEGEND_HEIGHT_MM
    cols = rows = 1
    if denominator:
        cols = math.ceil(scene.width_cm * 10 / denominator / PRINTABLE_W_MM)
        rows = math.ceil(scene.height_cm * 10 / denominator / content_h)
    assert pages == cols * rows
    for number in range(pages):
        page = _pdf_page(target, number, dpi)
        if denominator:
            row, col = divmod(number, cols)
            tile_x = 0.0
            tile_w = min(PRINTABLE_W_MM, scene.width_cm * 10 / denominator - col * PRINTABLE_W_MM)
            tile_h = min(content_h, scene.height_cm * 10 / denominator - (rows - 1 - row) * content_h)
        else:
            fit = min(PRINTABLE_W_MM / scene.width_cm, content_h / scene.height_cm)
            tile_w, tile_h = scene.width_cm * fit, scene.height_cm * fit
            tile_x = (PRINTABLE_W_MM - tile_w) / 2.0
        painted = _channels(page).min(axis=2) < 235          # anything but white paper
        left = round((PRINT_MARGIN_MM + tile_x) * mm)
        right = round((PRINT_MARGIN_MM + tile_x + tile_w) * mm)
        top = round(PRINT_MARGIN_MM * mm)
        bottom = round((PRINT_MARGIN_MM + tile_h) * mm)
        rule = round((PRINT_MARGIN_MM + content_h) * mm)
        where = f"page {number + 1} of {pages} at 1:{denominator or 'fit'}"

        # The tile itself is the plan, all of it.
        assert painted[top + 3:bottom - 3, left + 3:right - 3].mean() > 0.99, where
        # The paper's own margin, all round.
        edge = round((PRINT_MARGIN_MM - 1.0) * mm)
        ring = painted.copy()
        ring[edge:-edge, edge:-edge] = False
        assert not ring.any(), f"{where}: the plan is painted on the paper's margin"
        # Beside the tile and below it, down to the footer's rule: blank paper.
        assert not painted[:rule - 3, right + 3:].any(), f"{where}: painted right of its tile"
        assert not painted[:rule - 3, :left - 3].any(), f"{where}: painted left of its tile"
        assert not painted[bottom + 3:rule - 3, :].any(), f"{where}: painted below its tile"
        # The footer holds its three texts and nothing else.
        assert painted[rule + 3:, :].mean() < 0.08, f"{where}: the plan runs over the footer"


def test_report_pages_paint_the_plan_only_inside_their_frame(qtbot) -> None:
    scene = _shadowed_scene()
    bed = RectangleItem(1000, 600, 300, 150, object_type=ObjectType.RAISED_BED, name="Bed")
    scene.addItem(bed)
    for kind, data, sample in (("overview", None, (390, 150)), ("bed", [bed], (60, 250))):
        image, _texts = _page_image(scene, kind, data)
        first_column, _first_line, last_column, last_line = _extent(_shaded(image, sample))
        title_top = PAGE.height() - svc._pt(8.0)
        assert last_line < title_top, f"{kind}: the plan is painted over the title block"
        # A frame of the plan's own aspect ratio, centred on the page.
        assert abs((first_column + last_column) / 2.0 - PAGE.width() / 2.0) <= 2.0


def test_no_scene_painter_replaces_the_clip_it_was_handed() -> None:
    """The guard against drift (PF-CAN-54). ``QPainter.setClipPath`` replaces
    the painter's clip unless told to intersect it, and a print tile or a PDF
    frame is such a clip: a ``paint()`` that replaces it paints on the margin."""
    allowed = {
        # Not scene painters: a widget's own thumbnail, a wipe between two frames.
        SRC / "ui" / "widgets" / "gallery_data.py",
        SRC / "ui" / "view3d" / "wipe.py",
        # Sets an exact clip on a painter of its own, with nothing to preserve.
        SRC / "services" / "svg_export.py",
    }
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in ("setClipPath", "setClipRect", "setClipRegion"):
                continue
            arguments = [ast.unparse(argument) for argument in node.args]
            arguments += [ast.unparse(keyword.value) for keyword in node.keywords]
            if not any(argument.endswith("IntersectClip") for argument in arguments):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == [], (
        "a painter clip without Qt.ClipOperation.IntersectClip replaces the clip "
        f"of the print tile or PDF frame it paints into: {offenders}"
    )


# ---------------------------------------------------------------------------
# 5. The legend lists what is on the plan; the cover carries the plan's title
# ---------------------------------------------------------------------------

def test_the_legend_lists_the_objects_and_plants_on_the_plan(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    lawn = RectangleItem(100, 100, 600, 400, object_type=ObjectType.LAWN)
    _marked(lawn)
    scene.addItem(lawn)
    for index in range(3):
        scene.addItem(RectangleItem(900 + index * 200, 100, 150, 100, object_type=ObjectType.RAISED_BED))
    scene.addItem(_plant(300, 900, ObjectType.TREE, species="Apple Tree"))
    scene.addItem(_plant(500, 900, ObjectType.TREE, species="Apple Tree"))
    scene.addItem(_plant(700, 900, ObjectType.PERENNIAL, name="Grandmother's rose"))

    entries = svc._legend_entries(scene)
    labels = [entry.label for entry in entries]
    assert labels == ["Objects", "Lawn", "Raised Bed (3)", "Plants", "Apple Tree (2)", "Grandmother's rose"]
    assert not any("Layer" in label for label in labels)

    options = svc.PdfReportOptions(include_cover=False, include_overview=False, include_plant_list=False)
    ((kind, data),) = svc.PdfReportService.plan_pages(scene, options, PAGE)
    image, texts = _page_image(scene, kind, data, monkeypatch)
    assert set(labels) <= set(texts)
    # The lawn's sample is the lawn as the plan paints it: this one is magenta.
    assert _is_magenta(_channels(image)).sum() > 30


def test_an_empty_plan_has_a_legend_page_that_says_so(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = CanvasScene(width_cm=500, height_cm=500)
    options = svc.PdfReportOptions(include_cover=False, include_overview=False, include_plant_list=False)
    ((kind, data),) = svc.PdfReportService.plan_pages(scene, options, PAGE)
    _image, texts = _page_image(scene, kind, data, monkeypatch)
    assert "Nothing is drawn on this plan yet." in texts


@pytest.mark.parametrize("example", EXAMPLES)
def test_a_bundled_examples_legend_fits_its_pages(qtbot, example: str) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    options = svc.PdfReportOptions(include_cover=False, include_overview=False, include_plant_list=False)
    pages = svc.PdfReportService.plan_pages(scene, options, PAGE)
    entries = svc._legend_entries(scene)
    assert sum(len(data[0]) for _kind, data in pages) == len(entries) > 3
    for kind, data in pages:
        image, _texts = _page_image(scene, kind, data)
        assert not (_channels(image) == 255).all()


def test_a_plan_opened_from_an_example_carries_the_examples_title(qtbot, tmp_path: Path) -> None:
    manager = ProjectManager()
    scene = CanvasScene()
    assert manager.display_name == "Untitled"
    manager.load(scene, BUNDLED_EXAMPLES / "family-garden.ogp", as_template=True)
    assert manager.display_name == "Family garden - 24 x 16 m"
    assert manager.project_name == "Untitled"            # file-name defaults are unchanged
    manager.load(scene, BUNDLED_EXAMPLES / "de" / "family-garden.ogp", as_template=True)
    assert manager.display_name == "Familiengarten - 24 x 16 m"

    saved = tmp_path / "my-plot.ogp"
    manager.save(scene, saved)
    assert manager.display_name == "my-plot"
    manager.load(scene, saved, as_template=True)         # a user's own template
    assert manager.display_name == "my-plot"
    manager.new_project()
    assert manager.display_name == "Untitled"


def test_the_cover_shows_the_title_it_is_given(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = CanvasScene(width_cm=500, height_cm=500)
    options = svc.PdfReportOptions(project_name="Family garden - 24 x 16 m")
    _image, texts = _page_image(scene, "cover", None, monkeypatch, options)
    assert "Family garden - 24 x 16 m" in texts
