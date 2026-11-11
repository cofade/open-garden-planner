"""#863/#899: harvest units are translated at display time, never in the data."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.services.harvest_units import harvest_unit_label
from open_garden_planner.services.pdf_report_service import (
    PdfReportOptions,
    _harvest_rows,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.dialogs.harvest_log_dialog import HarvestLogDialog
from open_garden_planner.ui.views.harvest_view import HarvestView


class _German(QTranslator):
    def translate(self, context, source, disambiguation=None, n=-1):
        if context == "HarvestUnits":
            return {"bunch": "Bund", "pcs": "Stk."}.get(source, source)
        return ""


@pytest.fixture
def german(qtbot, monkeypatch):
    translator = _German()
    QCoreApplication.installTranslator(translator)
    try:
        yield
    finally:
        QCoreApplication.removeTranslator(translator)


def _history() -> HarvestHistory:
    return HarvestHistory(
        target_id="plant-1",
        species_key="basil",
        species_name="Basil",
        records=[
            HarvestRecord(
                date="2026-06-21", quantity=2.0, unit="bunch", quality="fresh"
            )
        ],
    )


def test_a_known_unit_is_translated_and_a_custom_one_is_left_alone(german) -> None:
    assert harvest_unit_label("bunch") == "Bund"
    assert harvest_unit_label("pcs") == "Stk."
    assert harvest_unit_label("crates") == "crates"


def test_the_dialog_shows_the_translation_but_stores_the_stable_key(qtbot, german) -> None:
    dialog = HarvestLogDialog()
    qtbot.addWidget(dialog)
    index = dialog._unit_combo.findData("bunch")
    assert index >= 0
    dialog._unit_combo.setCurrentIndex(index)
    assert dialog._unit_combo.currentText() == "Bund"
    dialog._quantity_spin.setValue(2.0)
    assert dialog.result_record().unit == "bunch"


def test_the_harvest_tab_shows_the_translated_unit(qtbot, german) -> None:
    scene = CanvasScene(width_cm=500, height_cm=500)
    pm = ProjectManager()
    pm.set_harvest_history("plant-1", _history())
    view = HarvestView(scene, pm)
    qtbot.addWidget(view)
    view.refresh()
    assert view._table.item(0, 3).text() == "Bund"


def test_the_pdf_harvest_summary_shows_the_translated_unit(german) -> None:
    rows = _harvest_rows(
        PdfReportOptions(harvest_logs={"plant-1": _history().to_dict()})
    )
    assert rows and rows[0][3] == "Bund"
