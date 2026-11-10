"""The UI speaks one language: numbers, months and every word (#792).

End to end on the real main window, with the application language differing
from the (simulated) system locale in both directions, plus the four wording
leaks the issue names: "Select" in a German status bar, the welcome tab that
lost its ampersand, raw type names in the Diagnostics panel, and the raw theme
name in a status message.

The other half of the same rule is pinned here too: what the UI formats for a
reader, a FILE never contains. The plan file, the SVG and the CSV exports are
byte-for-byte the same under an English and a German locale.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QMessageBox, QTabWidget

from open_garden_planner.core import i18n
from open_garden_planner.core.measurements import format_scale_distance
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.shopping_list import ShoppingListCategory, ShoppingListItem
from open_garden_planner.services.diagnostics import DiagnosticRecord, diagnostics_from_records
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.harvest_aggregation import AggregatedHarvest, harvest_csv_rows
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.dialogs import WelcomeDialog
from open_garden_planner.ui.panels.diagnostics_panel import DiagnosticsPanel
from open_garden_planner.ui.theme import ThemeMode, apply_theme
from open_garden_planner.ui.views.planting_calendar_view import _month_abbr


@pytest.fixture
def speak(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    """Load a UI language on a simulated system locale; English is put back after."""

    def _speak(language: str, system: str) -> None:
        monkeypatch.setattr(i18n, "_system_locale", lambda: QLocale(system), raising=False)
        i18n.load_translator(qapp, language)

    yield _speak
    monkeypatch.undo()
    i18n.load_translator(qapp, "en")


def _window(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda _self: None)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    window.showNormal()
    window.resize(1500, 900)
    qtbot.waitExposed(window)
    return window


def _select_a_bed(window, qtbot) -> RectangleItem:
    scene = window.canvas_scene
    bed = RectangleItem(155.8, 20.5, 315.5, 201.5, object_type=ObjectType.GARDEN_BED,
                        layer_id=scene.active_layer.id)
    scene.addItem(bed)
    scene.clearSelection()
    bed.setSelected(True)
    qtbot.wait(400)   # the properties panel rebuilds on a debounce
    return bed


@pytest.mark.parametrize(
    ("language", "system", "mark", "march"),
    [
        pytest.param("en", "de_DE", ".", "Mar", id="english-ui-on-a-german-system"),
        pytest.param("de", "en_US", ",", "Mär", id="german-ui-on-an-american-system"),
    ],
)
def test_the_main_window_formats_in_the_ui_language(
        qtbot, monkeypatch, speak, language, system, mark, march) -> None:
    """Status bar, properties panel and calendar agree on one decimal mark."""
    speak(language, system)
    window = _window(qtbot, monkeypatch)

    # The status bar's coordinates and the selection's area and perimeter.
    window.update_coordinates(155.8, 20.5)
    assert f"155{mark}80" in window.coord_label.text()
    assert f"20{mark}50" in window.coord_label.text()
    _select_a_bed(window, qtbot)
    selection = window.selection_label.text()
    assert f"6{mark}36 m²" in selection, selection       # 315.5 x 201.5 cm
    assert f"10{mark}34 m" in selection, selection

    # Every number field of the properties panel shows the same mark.
    spins = [spin for spin in window.properties_panel.findChildren(QDoubleSpinBox)
             if spin.decimals() > 0]
    assert spins
    other = "," if mark == "." else "."
    for spin in spins:
        assert other not in spin.text(), spin.text()
        assert spin.locale().language() == QLocale(language).language()

    # The planting calendar's month columns.
    assert _month_abbr(3) == march
    # The plan's place in the status bar: one mark, and a separator that is not it.
    window._project_manager.set_location({"latitude": 52.52, "longitude": 13.405})
    qtbot.wait(50)
    place = window.location_label.text()
    assert f"52{mark}5200°N" in place and f"13{mark}4050°E" in place, place
    assert i18n.list_separator() in place


def test_a_german_status_bar_names_the_tool_in_german(qtbot, monkeypatch, speak) -> None:
    """It said "Select", and after a tool change "Rectangle", in every language."""
    speak("de", "en_US")
    window = _window(qtbot, monkeypatch)
    assert window.tool_label.text() == "Auswählen"

    window.canvas_view.set_active_tool(ToolType.RECTANGLE)
    assert window.tool_label.text() == "Rechteck"
    window.canvas_view.set_active_tool(ToolType.SELECT)
    assert window.tool_label.text() == "Auswählen"
    # A tool the view named on the instance keeps that (already translated) name.
    window.canvas_view.set_active_tool(ToolType.HOUSE)
    assert window.tool_label.text() == "Haus"


def test_every_tool_reports_a_name_from_the_catalog(qtbot, monkeypatch, speak) -> None:
    """No tool hands the status bar its English class attribute in a German UI."""
    speak("de", "en_US")
    window = _window(qtbot, monkeypatch)
    # English names whose German is another word ("Polygon", "Ellipse" and
    # "Text" are the same in both, so they prove nothing either way).
    english = {
        "Select", "Rectangle", "Circle", "Polyline", "Callout", "Journal Pin", "Offset",
        "Mirror", "Fillet", "Chamfer", "Measure", "Arc (3-point)", "Split along line",
    }
    names = {
        tool_type: tool.localized_name()
        for tool_type, tool in window.canvas_view._tool_manager._tools.items()
    }
    leaked = {t.name: n for t, n in names.items() if n in english}
    assert not leaked, leaked


def test_the_welcome_tab_keeps_its_ampersand(qtbot, speak) -> None:
    """A tab label reads "&" as a mnemonic marker: "Examples  templates"."""
    speak("en", "de_DE")
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    label = tabs.tabText(1)
    # Qt shows "&&" as one "&"; a single "&" would be dropped from the label.
    assert label.replace("&&", "").count("&") == 0, label
    assert label.replace("&&", "&") == "Examples & templates"


def test_diagnostics_name_an_unnamed_object_by_its_translated_type(qtbot, speak) -> None:
    """The panel said "TREE: spacing overlap" — the enum's name, in every language."""
    records = diagnostics_from_records([
        {"item_id": "a", "object_type": "TREE", "spacing_overlap": "overlap"},
        {"item_id": "b", "object_type": "TREE", "name": "TREE", "spacing_overlap": "overlap"},
    ])
    unnamed, named = records
    assert unnamed.details["label_is_type"] is True
    assert "label_is_type" not in named.details    # a user may call a tree "TREE"

    # A diagnostic that brings its own label (the sun records name the SPECIES of an
    # unnamed plant) is not labelled with the type: the flag is a fact an agent reads.
    own = {"kind": "sun_mismatch", "severity": "warning", "item_ids": ["c"], "message": "",
           "details": {"label": "Tomato", "label_is_species": True}}
    bare = {"kind": "sun_evaluation", "severity": "info", "item_ids": ["c"], "message": ""}
    by_kind = {record.kind: record.details for record in diagnostics_from_records([
        {"item_id": "c", "object_type": "PERENNIAL", "diagnostics": [own, bare],
         "spacing_overlap": "overlap"}])}
    assert len(by_kind) == 3
    assert by_kind["sun_mismatch"] == {"label": "Tomato", "label_is_species": True}
    assert by_kind["sun_evaluation"] == {"label": "PERENNIAL", "label_is_type": True}
    assert by_kind["spacing_overlap"] == {"label": "PERENNIAL", "label_is_type": True}
    # an unnamed plant whose species is called like a type is still a species
    homonym = {"kind": "sun_mismatch", "severity": "warning", "item_ids": ["d"], "message": "",
               "details": {"label": "TREE", "label_is_species": True}}
    (record,) = diagnostics_from_records([
        {"item_id": "d", "object_type": "TREE", "diagnostics": [homonym]}])
    assert record.details == {"label": "TREE", "label_is_species": True}

    speak("en", "de_DE")
    panel = DiagnosticsPanel(CanvasScene())
    qtbot.addWidget(panel)
    assert panel._message(unnamed) == "Tree: spacing overlap"
    assert panel._message(named) == "TREE: spacing overlap"

    speak("de", "en_US")
    assert panel._message(unnamed).startswith("Baum:")
    # A label that is no type name is shown as it is, flagged or not.
    odd = DiagnosticRecord("spacing_overlap", "warning", ["c"], "",
                           {"label": "Tomato 3", "label_is_type": True})
    assert panel._message(odd).startswith("Tomato 3:")


def test_the_theme_message_names_the_theme_in_the_ui_language(qtbot, monkeypatch, speak) -> None:
    """ "Theme changed to Dark" printed the enum's value in every language."""
    speak("de", "en_US")
    window = _window(qtbot, monkeypatch)
    try:
        window._on_theme_changed(ThemeMode.DARK)
        message = window.statusBar().currentMessage()
        assert window._dark_theme_action.text().replace("&", "") in message
        assert "Dark" not in message and "&" not in message
    finally:
        apply_theme(QApplication.instance(), ThemeMode.LIGHT)


# ── A file never speaks the UI's locale ──────────────────────────────────────

def _plan() -> CanvasScene:
    scene = CanvasScene(width_cm=1000.5, height_cm=800.25)
    layer = scene.active_layer.id
    scene.addItem(RectangleItem(155.8, 20.5, 315.5, 201.5,
                                object_type=ObjectType.GARDEN_BED, layer_id=layer))
    scene.addItem(RectangleItem(500.25, 300.75, 120.125, 80.5,
                                object_type=ObjectType.GENERIC_RECTANGLE, layer_id=layer))
    return scene


def _numbers(node: object) -> list[float]:
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, dict):
        return [n for value in node.values() for n in _numbers(value)]
    if isinstance(node, list):
        return [n for value in node for n in _numbers(value)]
    return []


def test_the_plan_file_is_the_same_in_every_locale(qtbot, speak, tmp_path: Path) -> None:
    saved: dict[str, dict] = {}
    for language, system in (("en", "de_DE"), ("de", "en_US")):
        speak(language, system)
        path = tmp_path / f"plan_{language}.ogp"
        ProjectManager().save(_plan(), path)
        text = path.read_text(encoding="utf-8")
        assert "155.8" in text and "155,8" not in text
        saved[language] = json.loads(text)
    # Ids and timestamps differ between two saves; every NUMBER must not.
    assert _numbers(saved["en"]["objects"]) and (
        sorted(_numbers(saved["en"]["objects"])) == sorted(_numbers(saved["de"]["objects"])))
    assert saved["en"]["canvas"] == saved["de"]["canvas"]

    # ... and a plan saved in German opens in English with the same geometry.
    speak("en", "de_DE")
    scene = CanvasScene()
    ProjectManager().load(scene, tmp_path / "plan_de.ogp")
    widths = sorted(round(item.rect().width(), 3) for item in scene.items()
                    if isinstance(item, RectangleItem))
    assert widths == [120.125, 315.5]


def test_the_svg_export_is_the_same_in_every_locale(qtbot, speak, tmp_path: Path) -> None:
    exported = {}
    for language, system in (("en", "de_DE"), ("de", "en_US")):
        speak(language, system)
        path = tmp_path / f"plan_{language}.svg"
        ExportService.export_to_svg(_plan(), path, output_width_cm=10.0)
        exported[language] = path.read_bytes()
    assert exported["en"] == exported["de"]
    assert b"," not in exported["en"].split(b"viewBox=")[1].split(b'"')[1]


def test_csv_exports_keep_a_decimal_point_in_a_german_ui(qtbot, speak, tmp_path: Path) -> None:
    speak("de", "en_US")
    rows = harvest_csv_rows([AggregatedHarvest("tomato", "Tomate", 2026, "kg", 2.5, 3)])
    assert rows[0]["total_quantity"] == "2.5"

    item = ShoppingListItem("s1", ShoppingListCategory.SEEDS, "Tomate", 2.5, "g", price_each=1.25)
    path = tmp_path / "shopping.csv"
    ExportService.export_shopping_list_to_csv([item], path)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert (row["quantity"], row["price_each"], row["total_cost"]) == ("2.5", "1.25", "3.125")


def test_the_shopping_list_shows_german_numbers_and_copies_plain_ones(qtbot, speak) -> None:
    """The table speaks the UI language; the clipboard rows stay spreadsheet-plain."""
    from open_garden_planner.ui.dialogs.shopping_list_dialog import ShoppingListDialog

    speak("de", "en_US")
    item = ShoppingListItem("s1", ShoppingListCategory.SEEDS, "Tomate", 2.5, "g", price_each=1.25)
    assert ShoppingListDialog._format_total(item) == "3,13"
    assert ShoppingListDialog._plain_total(item) in ("3.12", "3.13")   # float rounding


def test_a_pdf_scale_label_keeps_a_decimal_point(qtbot, speak) -> None:
    """The report's numbers are the export services' own, not the UI formatters'."""
    speak("de", "en_US")
    assert format_scale_distance(150) == "1.5 m"
    assert format_scale_distance(250000) == "2.5 km"
