"""The export follow-ups of #836, measured on what is rendered.

1. The Harvest Summary shows every row, over as many pages as it needs.
6. The Garden Notes' pages are pages of the report: counted, titled, stamped.
4. A printout has one margin, stated in millimetres, and the Print Options
   dialog counts its pages with it.
5./7. The report dialog's bed label and the default plan name are translated.

(The succession badge is in ``test_succession_badge_export.py``, the text
size in ``test_text_note_size.py``.)
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QCoreApplication, QRectF, QTranslator
from PyQt6.QtGui import QPageLayout, QPainter, QPainterPath
from PyQt6.QtPrintSupport import QPrinter

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.services import pdf_report_service as svc
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowOverlayItem
from open_garden_planner.ui.dialogs import print_dialog
from open_garden_planner.ui.dialogs.pdf_report_dialog import PdfReportDialog
from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager, PrintOptionsDialog
from tests.integration.test_pdf_report_pages import (
    PAGE,
    PAPERS,
    _channels,
    _extent,
    _page_image,
    _pdf_page,
    _pdf_page_count,
    _shaded,
)

# ---------------------------------------------------------------------------
# 1. The Harvest Summary: every row, over as many pages as needed
# ---------------------------------------------------------------------------

def _harvest_logs(rows: int) -> dict[str, dict[str, object]]:
    """*rows* species, each harvested twice in 2026: one summary row apiece."""
    logs: dict[str, dict[str, object]] = {}
    for index in range(rows):
        logs[f"target-{index}"] = {
            "target_id": f"target-{index}",
            "species_key": f"species {index:03d}",
            "species_name": f"Crop {index:03d}",
            "records": [
                {"date": "2026-07-01", "quantity": 1.5 + index, "unit": "kg"},
                {"date": "2026-08-01", "quantity": 0.25, "unit": "kg"},
            ],
        }
    return logs


def _harvest_options(rows: int, **more: object) -> svc.PdfReportOptions:
    options = svc.PdfReportOptions(
        include_cover=False, include_overview=False, include_plant_list=False,
        include_legend=False, include_harvest_summary=True, harvest_logs=_harvest_logs(rows),
    )
    for name, value in more.items():
        setattr(options, name, value)
    return options


@pytest.mark.parametrize("count", [0, 5, 22, 23, 60, 200])
def test_the_harvest_summary_shows_every_row(qtbot, monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    scene = CanvasScene(width_cm=800, height_cm=500)
    options = _harvest_options(count)
    pages = svc.PdfReportService.plan_pages(scene, options, PAGE)
    per_page = svc._table_rows_per_page(PAGE)
    assert len(pages) == max(1, math.ceil(count / per_page))

    drawn: list[str] = []
    for number, (kind, data) in enumerate(pages, start=1):
        assert kind == "harvest_summary"
        image, texts = _page_image(scene, kind, data, monkeypatch, options)
        monkeypatch.undo()
        drawn.extend(texts)
        if len(pages) > 1:
            assert any(f"{number}" in text and f"{len(pages)}" in text and "Harvest Summary" in text
                       for text in texts), texts[:3]
        foot = _channels(image)[int(PAGE.height() - svc._pt(svc._TABLE_FOOT_MM)) + 1:, :, :]
        assert (foot == 255).all(), "a row runs off the page"

    for index in range(count):
        assert drawn.count(f"Crop {index:03d}") == 1, f"Crop {index:03d}"
    if count == 0:
        assert "No harvests logged in this project." in drawn


def _text_rows(page: np.ndarray, left: int, right: int) -> int:
    """How many lines of dark text the columns *left*..*right* of *page* hold."""
    dark = (page[:, left:right, :].max(axis=2) < 110).any(axis=1)
    return int(np.count_nonzero(dark[1:] & ~dark[:-1]) + int(dark[0]))


@pytest.mark.parametrize(("paper", "orientation"), PAPERS)
def test_the_written_report_holds_every_harvest_row(
    qtbot, tmp_path: Path, paper: str, orientation: str
) -> None:
    """End to end: the PDF on disk, rasterised, has one line of text per total."""
    rows = 60
    scene = CanvasScene(width_cm=800, height_cm=500)
    target = tmp_path / "harvest.pdf"
    options = _harvest_options(rows, paper_size=paper, orientation=orientation)
    calls: list[tuple[int, int]] = []
    svc.PdfReportService.generate(scene, options, target, lambda current, total: calls.append((current, total)))

    pages = _pdf_page_count(target)
    assert pages >= 2, "sixty totals do not fit one page"
    assert calls[-1] == (pages, pages)
    dpi = 100
    found = 0
    for number in range(pages):
        page = _channels(_pdf_page(target, number, dpi))
        margin = round(svc._MARGIN_MM / 25.4 * dpi)
        width = page.shape[1] - 2 * margin
        # The "Year" column: one dark "2026" per data row, nothing in the
        # white-on-green header and nothing of the green title.
        left = margin + round(width * 0.40)
        found += _text_rows(page, left, left + round(width * 0.15))
    assert found == rows


# ---------------------------------------------------------------------------
# 6. The Garden Notes' pages are pages of the report
# ---------------------------------------------------------------------------

def _notes(count: int, sentences: int = 6) -> dict[str, dict[str, object]]:
    body = "The beans by the fence need another tie and the lettuce has bolted. " * sentences
    notes: dict[str, dict[str, object]] = {}
    for index in range(count):
        note = JournalNote(
            date=f"2026-{index % 12 + 1:02d}-{index % 27 + 1:02d}",
            text=f"Note {index:03d}. {body}", scene_x=0.0, scene_y=0.0,
        )
        notes[note.id] = note.to_dict()
    return notes


def _notes_options(count: int, **more: object) -> svc.PdfReportOptions:
    options = svc.PdfReportOptions(
        include_cover=False, include_overview=False, include_plant_list=False,
        include_legend=False, include_garden_notes=True, garden_journal_notes=_notes(count),
    )
    for name, value in more.items():
        setattr(options, name, value)
    return options


@pytest.mark.parametrize("count", [0, 1, 12, 40])
def test_every_garden_note_is_on_a_planned_page(qtbot, monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    scene = CanvasScene(width_cm=800, height_cm=500)
    options = _notes_options(count)
    pages = svc.PdfReportService.plan_pages(scene, options, PAGE)
    assert {kind for kind, _data in pages} == {"garden_notes"}
    if count >= 12:
        assert len(pages) > 1, "the notes need more than one page and the plan lists one"

    drawn: list[str] = []
    for number, (kind, data) in enumerate(pages, start=1):
        image, texts = _page_image(scene, kind, data, monkeypatch, options)
        monkeypatch.undo()
        drawn.extend(texts)
        assert sum("Garden Notes" in text for text in texts) == 1, "one title a page"
        if len(pages) > 1:
            assert any(f"{number}" in text and f"{len(pages)}" in text and "Garden Notes" in text
                       for text in texts), texts[:3]
        # Nothing is written below the page.
        foot = _channels(image)[int(PAGE.height()) - 1:, :, :]
        assert (foot == 255).all()

    joined = " ".join(drawn)
    for index in range(count):
        assert joined.count(f"Note {index:03d}.") == 1, f"Note {index:03d}"
    if count == 0:
        assert "No journal notes recorded." in drawn


@pytest.mark.parametrize(("paper", "orientation"), PAPERS)
def test_the_progress_counts_the_garden_notes_pages(
    qtbot, tmp_path: Path, paper: str, orientation: str
) -> None:
    """End to end: what the progress callback is told is the PDF's page count."""
    scene = CanvasScene(width_cm=800, height_cm=500)
    target = tmp_path / "notes.pdf"
    options = _notes_options(40, paper_size=paper, orientation=orientation, include_cover=True,
                             include_harvest_summary=True, harvest_logs=_harvest_logs(60))
    calls: list[tuple[int, int]] = []
    svc.PdfReportService.generate(scene, options, target, lambda current, total: calls.append((current, total)))

    pages = _pdf_page_count(target)
    assert pages >= 6                                   # cover, >= 3 of notes, >= 2 of harvest
    assert {total for _current, total in calls} == {pages}
    assert [current for current, _total in calls] == list(range(pages + 1))


def test_a_long_note_is_wrapped_at_the_page_width(qtbot, tmp_path: Path) -> None:
    """The lines of a note run to the right margin, not to three quarters of it."""
    scene = CanvasScene(width_cm=800, height_cm=500)
    target = tmp_path / "wrap.pdf"
    svc.PdfReportService.generate(scene, _notes_options(1, sentences=20), target)
    dpi = 100
    page = _channels(_pdf_page(target, 0, dpi))
    margin = round(svc._MARGIN_MM / 25.4 * dpi)
    frame = page.shape[1] - 2 * margin
    ink = np.flatnonzero((page.max(axis=2) < 110).any(axis=0))
    reach = (int(ink[-1]) - margin) / frame
    assert 0.86 <= reach <= 1.0, f"the longest line ends at {reach:.0%} of the page width"


# ---------------------------------------------------------------------------
# 4. One print margin, in millimetres
# ---------------------------------------------------------------------------

MARGIN_MM = 10.0
PRINTABLE_W_MM, PRINTABLE_H_MM = 297.0 - 2 * MARGIN_MM, 210.0 - 2 * MARGIN_MM


def _print_through_the_preview(
    monkeypatch: pytest.MonkeyPatch, scene: CanvasScene, target: Path, denominator: int,
    legend: bool = True, texts: list[str] | None = None,
) -> QPageLayout:
    """Print *scene* by the app's own route, File > Print, into the PDF *target*.

    ``GardenPrintManager.print_preview`` builds the printer and its page
    layout; only the preview window is replaced, by one that prints at once.
    Returns the layout the app gave the printer.
    """
    layouts: list[QPageLayout] = []

    class _Preview:
        def __init__(self, printer: QPrinter, _parent: object = None) -> None:
            self._printer = printer
            self._slots: list[object] = []
            self.paintRequested = self

        def connect(self, slot: object) -> None:
            self._slots.append(slot)

        def setWindowTitle(self, _title: str) -> None:
            pass

        def reject(self) -> None:
            pass

        def exec(self) -> int:
            layouts.append(QPageLayout(self._printer.pageLayout()))
            self._printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            self._printer.setOutputFileName(str(target))
            layouts.append(QPageLayout(self._printer.pageLayout()))
            for slot in self._slots:
                slot(self._printer)                    # type: ignore[operator]
            return 0

    monkeypatch.setattr(print_dialog, "QPrintPreviewDialog", _Preview)
    if texts is not None:
        draw_text = QPainter.drawText

        def spy(self: QPainter, *args: object) -> object:
            texts.append(str(args[-1]))
            return draw_text(self, *args)

        monkeypatch.setattr(QPainter, "drawText", spy)
    manager = GardenPrintManager(scene, project_name="Plan")
    manager.configure(scale_denominator=denominator, include_grid=False, include_labels=True,
                      include_legend=legend)
    manager.print_preview()
    monkeypatch.undo()
    first = layouts[0].margins(QPageLayout.Unit.Millimeter)
    second = layouts[1].margins(QPageLayout.Unit.Millimeter)
    assert first.left() == pytest.approx(second.left(), abs=0.01), "the PDF printer changed the margin"
    return layouts[0]


def _filled_scene(width: float, height: float) -> CanvasScene:
    """A plan under one shadow that covers all of it: the plan is one grey area."""
    scene = CanvasScene(width_cm=width, height_cm=height)
    shadow = SunShadowOverlayItem()
    shadow.set_clip_rect(scene.canvas_rect)
    outline = QPainterPath()
    outline.addRect(QRectF(-9000, -9000, 27000, 27000))
    shadow.set_shadow_path(outline)
    scene.addItem(shadow)
    return scene


def test_the_print_margin_is_ten_millimetres_all_round(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _print_through_the_preview(
        monkeypatch, _filled_scene(2400, 1600), tmp_path / "margins.pdf", 0
    )
    margins = layout.margins(QPageLayout.Unit.Millimeter)
    for side in (margins.left(), margins.top(), margins.right(), margins.bottom()):
        assert side == pytest.approx(MARGIN_MM, abs=0.05)
    paint = layout.paintRect(QPageLayout.Unit.Millimeter)
    assert paint.width() == pytest.approx(PRINTABLE_W_MM, abs=0.1)
    assert paint.height() == pytest.approx(PRINTABLE_H_MM, abs=0.1)
    assert print_dialog.PRINT_MARGIN_MM == MARGIN_MM


@pytest.mark.parametrize("denominator", [0, 50])
def test_the_printed_plan_keeps_the_stated_margin_and_scale(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, denominator: int
) -> None:
    """Measured on the printed page: where the plan starts, and how wide it is."""
    scene = _filled_scene(2400, 1600)
    target = tmp_path / "print.pdf"
    _print_through_the_preview(monkeypatch, scene, target, denominator)

    dpi = 100
    mm = dpi / 25.4
    content_h = PRINTABLE_H_MM - GardenPrintManager.LEGEND_HEIGHT_MM
    page = _pdf_page(target, 0, dpi)
    centre = (round((MARGIN_MM + PRINTABLE_W_MM / 2) * mm), round((MARGIN_MM + 20) * mm))
    left, top, right, _bottom = _extent(_shaded(page, centre))

    assert top == pytest.approx(MARGIN_MM * mm, abs=2), "the plan does not start at the top margin"
    if denominator:
        # The first sheet is a full tile: margin to margin, at 1:denominator.
        assert left == pytest.approx(MARGIN_MM * mm, abs=2)
        assert right == pytest.approx((MARGIN_MM + PRINTABLE_W_MM) * mm, abs=2)
        cols = math.ceil(scene.width_cm * 10 / denominator / PRINTABLE_W_MM)
        rows = math.ceil(scene.height_cm * 10 / denominator / content_h)
        assert _pdf_page_count(target) == cols * rows
    else:
        fit = min(PRINTABLE_W_MM / scene.width_cm, content_h / scene.height_cm)
        assert (right - left) / mm == pytest.approx(scene.width_cm * fit, abs=1.5)


@pytest.mark.parametrize(("width", "height", "denominator", "legend"), [
    (2400.0, 1600.0, 50, True), (2400.0, 1600.0, 100, True), (2400.0, 1600.0, 20, False),
    (900.0, 650.0, 50, True), (5000.0, 3000.0, 100, True),
    (2800.0, 1000.0, 100, True),          # 280 mm of paper: wider than one sheet's 277
    (1000.0, 1905.0, 100, True),          # 190.5 mm: taller than a sheet less its legend
    (2770.0, 1790.0, 100, True),          # 179 mm does not fit above a 12 mm legend ...
    (2770.0, 1790.0, 100, False),         # ... and fits without one
])
def test_the_print_dialog_counts_the_pages_the_printout_has(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    width: float, height: float, denominator: int, legend: bool,
) -> None:
    """The page count the dialog states is the page count of the printed PDF."""
    scene = CanvasScene(width_cm=width, height_cm=height)
    dialog = PrintOptionsDialog(width, height, grid_visible=False, labels_visible=True)
    qtbot.addWidget(dialog)
    dialog._scale_combo.setCurrentIndex(
        [denom for _name, denom in print_dialog.SCALE_PRESETS].index(denominator)
    )
    dialog._legend_check.setChecked(legend)

    target = tmp_path / "count.pdf"
    _print_through_the_preview(monkeypatch, scene, target, dialog.scale_denominator,
                               legend=dialog.include_legend)
    printed = _pdf_page_count(target)

    stated = dialog._page_info_label.text()
    expected = "1 page" if printed == 1 else f"{printed} pages"
    assert stated.startswith(expected), f"the dialog says {stated!r}, the printout has {printed} pages"


@pytest.mark.parametrize(("width", "height"), [(900.0, 650.0), (2400.0, 1600.0), (1000.0, 3000.0)])
def test_a_fitted_printout_states_the_scale_it_is_printed_at(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: float, height: float
) -> None:
    """The footer's 1:N of a fit-to-page printout is the measured scale of the plan."""
    scene = _filled_scene(width, height)
    texts: list[str] = []
    target = tmp_path / "fit.pdf"
    _print_through_the_preview(monkeypatch, scene, target, 0, texts=texts)

    stated = next(int(text.split(":")[1]) for text in texts if text.startswith("1:"))
    dpi = 100
    page = _pdf_page(target, 0, dpi)
    centre = (page.width() // 2, round(40 / 25.4 * dpi))
    left, _top, right, _bottom = _extent(_shaded(page, centre))
    printed_width_cm = (right - left + 1) / dpi * 2.54
    measured = width / printed_width_cm
    assert stated == pytest.approx(measured, rel=0.02), (
        f"the footer says 1:{stated}, the plan is printed at 1:{measured:.1f}"
    )


# ---------------------------------------------------------------------------
# 5. and 7. Words
# ---------------------------------------------------------------------------

class _Catalogue(QTranslator):
    """A translator that answers from a dict: (context, source) -> translation."""

    def __init__(self, entries: dict[tuple[str, str], str]) -> None:
        super().__init__()
        self._entries = entries

    def translate(self, context, source, disambiguation=None, n=-1):
        return self._entries.get((context, source), "")


def test_the_bed_detail_checkbox_does_not_promise_a_page_per_bed(qtbot) -> None:
    dialog = PdfReportDialog(project_name="Plan")
    qtbot.addWidget(dialog)
    label = dialog._cb_bed_details.text()
    assert "one page per bed" not in label
    assert "small beds" in label


def test_the_default_plan_name_is_translated_on_the_cover(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan that was never saved is not "Untitled" in a German report."""
    catalogue = _Catalogue({("ProjectManager", "Untitled"): "Unbenannt"})
    QCoreApplication.installTranslator(catalogue)
    try:
        manager = ProjectManager()
        assert manager.project_name == "Unbenannt"
        assert manager.display_name == "Unbenannt"
        options = svc.PdfReportOptions(project_name=manager.display_name)
        scene = CanvasScene(width_cm=800, height_cm=500)
        _image, texts = _page_image(scene, "cover", None, monkeypatch, options)
        assert "Unbenannt" in texts
        assert "Untitled" not in texts
    finally:
        QCoreApplication.removeTranslator(catalogue)
    assert ProjectManager().project_name == "Untitled"


def test_the_agents_default_file_names_do_not_follow_the_ui_language(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A German UI named an agent's PDF "Unbenannt.pdf": a file an agent asks for by
    name must not depend on the language the user reads. The UI's own default (a save
    dialog's suggestion, the window title) stays translated."""
    from open_garden_planner.agent_api import exports
    from open_garden_planner.services.soil_service import SoilService

    names: list[str] = []

    class Named(Exception):
        """The name is known; the export itself is not this test's subject."""

    def record(requested, *, default_filename=None, suffix, project_manager):
        assert requested is None
        names.append(default_filename)
        raise Named

    monkeypatch.setattr(exports, "resolve_export_path", record)
    catalogue = _Catalogue({("ProjectManager", "Untitled"): "Unbenannt"})
    QCoreApplication.installTranslator(catalogue)
    try:
        manager = ProjectManager()
        scene = CanvasScene(width_cm=800, height_cm=500)
        soil = SoilService(manager)
        for export in (
            lambda: exports.export_pdf_file(scene, manager, None, "A4", "landscape"),
            lambda: exports.export_dxf_file(scene, manager, None),
            lambda: exports.export_csv_file(scene, manager, soil, "shopping_list", None),
            lambda: exports.export_csv_file(scene, manager, soil, "harvest", None),
        ):
            with pytest.raises(Named):
                export()
        assert names == ["Untitled.pdf", "Untitled.dxf", "Untitled_shopping_list.csv",
                         "Untitled_harvest.csv"]
        assert manager.file_stem == "Untitled"
        assert manager.project_name == "Unbenannt", "the UI's name is the language's"

        # with a file, both are its stem
        manager.save(scene, tmp_path / "Mein Garten.ogp")
        assert manager.file_stem == manager.project_name == "Mein Garten"
        names.clear()
        with pytest.raises(Named):
            exports.export_dxf_file(scene, manager, None)
        assert names == ["Mein Garten.dxf"]
    finally:
        QCoreApplication.removeTranslator(catalogue)


def test_an_empty_report_title_falls_back_to_a_translated_name(qtbot) -> None:
    catalogue = _Catalogue({("PdfReportDialog", "Garden Plan"): "Gartenplan"})
    QCoreApplication.installTranslator(catalogue)
    try:
        dialog = PdfReportDialog(project_name="")
        qtbot.addWidget(dialog)
        assert dialog.project_name == "Gartenplan"
    finally:
        QCoreApplication.removeTranslator(catalogue)
