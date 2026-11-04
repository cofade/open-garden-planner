"""Combined date/time controls, accurate live-map previews and export readiness."""

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from datetime import date, datetime, time, timedelta
from threading import Event, get_ident

import numpy as np
import pytest
from PyQt6.QtCore import QDate, QPoint, QPointF, Qt, QTime, QTimer
from PyQt6.QtGui import QFont, QPainter, QWheelEvent
from PyQt6.QtWidgets import QApplication, QDateEdit, QProgressDialog, QToolBar
from PyQt6.sip import isdeleted

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plan_timeline import month_number
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import HeatmapWorker

BERLIN = {"latitude": 52.52, "longitude": 13.405}


def test_find_replace_revalidates_cached_results_after_date_and_document_changes(win, qtbot, monkeypatch):
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.panels.find_replace_panel import FindReplacePanel

    plant = CircleItem(100, 100, 50, ObjectType.TREE, name="Future tree", metadata={
        "plant_species": {"common_name": "Apple"},
        "plant_instance": {"planting_date": "2030-01-01"}})
    win.canvas_scene.addItem(plant)
    panel = FindReplacePanel(win.canvas_view)
    qtbot.addWidget(panel)
    win._sim_clock.set_date(date(2030, 1, 1))
    panel._name_edit.setText("Future tree")
    panel._on_search()
    result = panel._results_list.item(0)
    assert result is not None
    identity = plant.item_id_str
    assert result.data(Qt.ItemDataRole.UserRole) == identity
    win.canvas_scene.clearSelection()
    panel._results_list.itemClicked.emit(result)
    qtbot.waitUntil(lambda: win.canvas_scene.selectedItems() == [plant])
    panel._replace_species_edit.setText("Changed")
    win._sim_clock.set_date(date(2029, 1, 1))
    navigation = []
    original_ensure_visible = win.canvas_view.ensureVisible
    monkeypatch.setattr(win.canvas_view, "ensureVisible", lambda *args: navigation.append(args))
    panel._on_replace_species()
    panel._results_list.itemClicked.emit(result)
    qtbot.wait(10)
    assert plant.metadata["plant_species"]["common_name"] == "Apple"
    assert not plant.isSelected()
    assert navigation == []
    monkeypatch.setattr(win.canvas_view, "ensureVisible", original_ensure_visible)
    win._sim_clock.set_date(date(2030, 1, 1))
    assert panel._eligible_matches() == [plant]
    panel._results_list.itemClicked.emit(result)  # queued click precedes document replacement
    win.canvas_scene.clear()
    assert panel._matched_items == [] and panel._results_list.count() == 0
    assert not panel._selection_timer.isActive()
    panel._on_replace_species()
    assert panel._eligible_matches() == []
    panel._on_select_all()
    for number in range(40):
        win.canvas_scene.addItem(RectangleItem(10 * number, 100, 20, 20,
                                              ObjectType.HOUSE, name=f"New {number}"))
    panel._name_edit.clear()
    panel._on_select_all()
    assert panel._results_list.count() == 40
    assert all(panel._results_list.item(n).data(Qt.ItemDataRole.UserRole) != identity for n in range(40))
    win.canvas_scene.clearSelection()
    qtbot.wait(10)
    assert win.canvas_scene.selectedItems() == []  # queued old click cannot alias
    current = panel._results_list.item(0)
    panel._results_list.itemClicked.emit(current)
    qtbot.waitUntil(lambda: len(win.canvas_scene.selectedItems()) == 1)
    assert win.canvas_scene.selectedItems()[0].item_id_str == current.data(Qt.ItemDataRole.UserRole)


def test_pdf_generation_progress_is_created_only_after_map_readiness(win, qtbot, jobs, monkeypatch, tmp_path):
    from open_garden_planner.services.pdf_report_service import PdfReportService
    from open_garden_planner.ui.dialogs.pdf_report_dialog import PdfReportDialog

    target = tmp_path / "report.pdf"
    monkeypatch.setattr(PdfReportDialog, "exec", lambda _self: PdfReportDialog.DialogCode.Accepted)
    monkeypatch.setattr("open_garden_planner.app.application.QFileDialog.getSaveFileName",
                        lambda *_a, **_k: (str(target), ""))
    start(win, qtbot, jobs)
    waiting = []
    def inspect_wait():
        waiting.extend(dialog.labelText() for dialog in win.findChildren(QProgressDialog) if dialog.isVisible())
        jobs[0][1].set()
    QTimer.singleShot(4300, inspect_wait)  # past QProgressDialog's constructor force-show timer
    def generate(*_args):
        assert win._live_sun_map.is_current()
        dialogs = win.findChildren(QProgressDialog)
        assert sum(dialog.labelText() == "Generating PDF…" for dialog in dialogs) == 1
        target.write_bytes(b"%PDF")
    monkeypatch.setattr(PdfReportService, "generate", generate)
    win._on_export_pdf_report()
    assert waiting == ["Updating Hours of Sun for export…"]
    assert target.read_bytes() == b"%PDF"
    assert not any(dialog.isVisible() for dialog in win.findChildren(QProgressDialog))


@pytest.mark.parametrize("field", ["planting_date_edit", "removal_date_edit"])
def test_scrolling_lifetime_calendar_does_not_edit_or_remove_a_legacy_plant(win, qtbot, monkeypatch, field):
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel

    plant = CircleItem(100, 100, 50, ObjectType.TREE, name="Legacy tree", metadata={})
    win.canvas_scene.addItem(plant)
    panel = PlantDatabasePanel()
    qtbot.addWidget(panel)
    panel._current_plant_item = plant
    panel._refresh_lifetime_dates(plant)
    panel.show()
    warnings = []
    monkeypatch.setattr("open_garden_planner.ui.panels.plant_database_panel.QMessageBox.warning",
                        lambda *args: warnings.append(args))
    edit = getattr(panel, field)
    edit.clearFocus()
    before = edit.date()
    history = len(win.canvas_view.command_manager._undo_stack)
    wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(edit, wheel)
    assert edit.date() == before
    assert len(win.canvas_view.command_manager._undo_stack) == history
    assert not warnings and plant.metadata == {} and plant.isVisible()


def test_hidden_layers_do_not_remove_data_diagnostics_report_beds_or_capacity(win):
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.pdf_report_service import PdfReportService
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    scene = win.canvas_scene
    bed = RectangleItem(100, 100, 100, 100, ObjectType.CONTAINER)
    house = RectangleItem(-2000, -2000, 100, 100, ObjectType.HOUSE, name="Outside house")
    plant = CircleItem(150, 150, 100, ObjectType.PERENNIAL, name="Big plant")
    for item in (bed, house, plant):
        scene.addItem(item)
        item.layer_id = scene.active_layer.id
    bed._child_item_ids = [plant.item_id]
    plant._parent_bed_id = bed.item_id
    scene.update_layer_visibility(scene.active_layer.id, False)
    records = ProjectManager.diagnostics_snapshot(scene)
    assert any(r.get("item_id") == str(house.item_id) and r["outside_canvas"] for r in records)
    # Containers are not report beds; a hidden normal bed must still get its data page.
    report_bed = RectangleItem(0, 0, 100, 100, ObjectType.GARDEN_BED)
    scene.addItem(report_bed)
    report_bed.layer_id = scene.active_layer.id
    scene.update_layer_visibility(scene.active_layer.id, False)
    assert report_bed in PdfReportService._find_beds(scene)
    win._update_container_capacity()
    assert bed.capacity_overrun


def test_unrelated_commands_keep_plant_paint_caches_but_date_changes_regrow(win, qtbot, monkeypatch):
    from open_garden_planner.core.commands import ChangePropertyCommand
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    paints = []
    original = CircleItem.paint
    def count(item, *args):
        paints.append(item.item_id)
        return original(item, *args)
    monkeypatch.setattr(CircleItem, "paint", count)
    plant = CircleItem(100, 100, 50, ObjectType.TREE, name="Tree")
    house = RectangleItem(300, 100, 100, 100, ObjectType.HOUSE, name="House")
    win.canvas_scene.addItem(plant)
    win.canvas_scene.addItem(house)
    win.show()
    qtbot.wait(150)
    win.canvas_view.viewport().grab()
    assert plant.item_id in paints
    paints.clear()
    win.canvas_view.command_manager.execute(ChangePropertyCommand(house, "name", "House", "Home"))
    win.canvas_view.viewport().grab()
    assert plant.item_id not in paints
    win._sim_clock.set_date(date(2027, 6, 21))
    win.canvas_view.viewport().grab()
    assert plant.item_id in paints


def test_print_legend_uses_the_rendered_plan_date(win, tmp_path, monkeypatch):
    from PyQt6.QtGui import QPdfWriter

    from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager

    win._sim_clock.set_date(date(2030, 6, 21))
    texts = []
    original = QPainter.drawText
    def draw(painter, *args):
        texts.extend(value for value in args if isinstance(value, str))
        return original(painter, *args)
    monkeypatch.setattr(QPainter, "drawText", draw)
    output = tmp_path / "print.pdf"
    printer = QPdfWriter(str(output))
    printer.setResolution(96)
    GardenPrintManager(win.canvas_scene)._render_to_printer(printer)
    assert output.read_bytes().startswith(b"%PDF")
    assert "2030-06-21" in texts and date.today().isoformat() not in texts


def test_print_waits_for_current_map_and_holds_animation_through_preview(win, qtbot, jobs, monkeypatch, tmp_path):
    from PyQt6.QtGui import QPdfWriter

    from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager, PrintOptionsDialog

    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    win._sun_toolbar._date_edit.setDate(QDate(2030, 6, 21))
    win._sun_toolbar.set_animation_active(True)
    monkeypatch.setattr(PrintOptionsDialog, "exec", lambda _self: PrintOptionsDialog.DialogCode.Accepted)
    output = tmp_path / "printed.pdf"
    seen = []
    def preview(manager, parent=None):
        assert win._live_sun_map.is_current()
        assert win._sun_heatmap.displayed_snapshot.day == date(2030, 6, 21)
        assert not win._sun_toolbar.animation_active
        writer = QPdfWriter(str(output))
        writer.setResolution(96)
        manager._render_to_printer(writer)
        seen.append(True)
    monkeypatch.setattr(GardenPrintManager, "print_preview", preview)
    release = QTimer(win)
    release.setInterval(10)
    release.timeout.connect(lambda: jobs[1][1].set() if len(jobs) > 1 else None)
    release.start()
    try:
        win._on_print()
    finally:
        release.stop()
    assert seen and output.read_bytes().startswith(b"%PDF")
    assert win._sun_toolbar.animation_active and win._sun_export_gate._leases == 0


def test_cancel_print_readiness_is_quiet_and_creates_no_preview(win, qtbot, jobs, monkeypatch):
    from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager, PrintOptionsDialog

    start(win, qtbot, jobs)
    win._sun_toolbar.set_animation_active(True)
    monkeypatch.setattr(PrintOptionsDialog, "exec", lambda _self: PrintOptionsDialog.DialogCode.Accepted)
    def cancel(dialog):
        dialog.cancel()
        return QProgressDialog.DialogCode.Rejected
    monkeypatch.setattr(QProgressDialog, "exec", cancel)
    previews, errors = [], []
    monkeypatch.setattr(GardenPrintManager, "print_preview", lambda *_a, **_k: previews.append(True))
    monkeypatch.setattr("open_garden_planner.app.application.QMessageBox.critical", lambda *a: errors.append(a))
    win._on_print()
    assert not previews and not errors
    assert win._sun_toolbar.animation_active and win._sun_export_gate._leases == 0


def test_print_revalidates_document_before_each_paint(win, monkeypatch):
    from open_garden_planner.ui.dialogs.print_dialog import GardenPrintManager, PrintOptionsDialog

    monkeypatch.setattr(PrintOptionsDialog, "exec", lambda _self: PrintOptionsDialog.DialogCode.Accepted)
    errors, touches = [], []
    def preview(manager, parent=None):
        win._sim_clock.set_date(date(2030, 6, 21))
        class UntouchedPrinter:
            def pageLayout(self):
                touches.append(True)
                raise AssertionError("Stale printing touched its output device")
        manager._render_to_printer(UntouchedPrinter())
    monkeypatch.setattr(GardenPrintManager, "print_preview", preview)
    monkeypatch.setattr("open_garden_planner.app.application.QMessageBox.critical", lambda *a: errors.append(a))
    win._on_print()
    assert errors and not touches and win._sun_export_gate._leases == 0


def test_gui_map_timeout_releases_animation_and_never_renders(win, qtbot, jobs):
    start(win, qtbot, jobs)
    win._sun_toolbar.set_animation_active(True)
    win._sun_export_gate.timeout_s = .04
    rendered = []
    with pytest.raises(TimeoutError, match="timed out"):
        win._sun_export_gate.run_gui(lambda: rendered.append(True))
    assert not rendered and win._sun_toolbar.animation_active
    assert win._sun_export_gate._leases == 0


def test_legacy_dates_remain_visible_but_new_calendar_choices_are_bounded(win, qtbot):
    from PyQt6.QtTest import QTest

    from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel
    from open_garden_planner.ui.plant_lifetime import change_lifetime_date

    plant = CircleItem(100, 100, 50, ObjectType.TREE, metadata={
        "plant_species": {"common_name": "Old tree", "scientific_name": "Old tree"},
        "plant_instance": {"planting_date": "1900-01-01"}})
    win.canvas_scene.addItem(plant)
    panel = PlantDatabasePanel()
    qtbot.addWidget(panel)
    panel.set_selected_items([plant])
    panel.show()
    qtbot.wait(30)
    assert panel.planting_date_edit.date() == QDate(1900, 1, 1)
    calendar = panel.planting_date_edit.calendarWidget()
    edit = panel.planting_date_edit
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(edit.width() - 8, edit.height() // 2))
    qtbot.waitUntil(calendar.isVisible)
    assert calendar.minimumDate() == QDate(MIN_PLAN_DATE)
    assert calendar.maximumDate() == QDate(MAX_PLAN_DATE)
    assert plant.metadata["plant_instance"]["planting_date"] == "1900-01-01"
    assert panel.planting_date_edit.date() == QDate(1900, 1, 1)
    calendar.hide()
    with pytest.raises(ValueError, match="supported plan range"):
        change_lifetime_date(plant, "removal_date", "1901-01-01")
    assert "removal_date" not in plant.metadata["plant_instance"]


@pytest.fixture
def win(qtbot, monkeypatch):
    get_settings().show_welcome_on_startup = False
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    monkeypatch.setattr(app, "_confirm_discard_changes", lambda: True)
    app._sim_clock.set_datetime(datetime(2026, 6, 21, 12))
    app._project_manager.set_location(dict(BERLIN))
    app._project_manager.mark_clean()
    app.canvas_scene.resize_canvas(500, 500)
    yield app


@pytest.fixture
def jobs(win, monkeypatch, qtbot):
    launched = []
    def controlled(worker):
        release = Event()
        launched.append((worker, release))
        while not release.wait(.01) and not worker._cancelled:
            pass
        # Even canceled workers emit to prove acceptance is guarded on Qt.
        if not getattr(worker, "_test_fail", False):
            worker.success.emit(np.full((worker._grid.rows, worker._grid.cols), 600, np.float32))
    monkeypatch.setattr(HeatmapWorker, "run", controlled)
    yield launched
    for _worker, release in launched:
        release.set()
    if not isdeleted(win):
        win._live_sun_map.shutdown()
        win._sun_heatmap.shutdown()


def start(win, qtbot, jobs):
    win._sun_toolbar._heatmap_button.click()
    qtbot.waitUntil(lambda: len(jobs) == 1)


def complete(win, qtbot, jobs, number=0):
    jobs[number][1].set()
    qtbot.waitUntil(lambda: win._live_sun_map.is_current())


def test_one_permanent_strip_and_defaults_ignore_obsolete_setting(qtbot):
    get_settings().show_shadows = False
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    assert not app._sun_toolbar.isHidden()
    assert app._sun_controller.enabled and app.canvas_scene._shadows_enabled
    assert not app._sun_toolbar.animation_active
    assert not app._sun_toolbar._location_button.isHidden()
    assert not app._live_sun_map.enabled
    assert len(app._sun_toolbar.findChildren(QDateEdit)) == 1
    names = [bar.objectName() for bar in app.findChildren(QToolBar)]
    assert names.count("SunSimToolbar") == 1 and "PlanTimelineToolbar" not in names
    assert not hasattr(app, "_sun_sim_action") and not hasattr(app, "_shadows_action")
    assert not hasattr(app._sun_toolbar, "_june_button")


@pytest.mark.parametrize("accepted", [False, True])
def test_sun_location_hint_opens_existing_dialog_and_recovers_map(win, qtbot, jobs, monkeypatch, accepted):
    from PyQt6.QtWidgets import QDialog

    from open_garden_planner.ui.dialogs.location_dialog import LocationDialog

    project, bar = win._project_manager, win._sun_toolbar
    project.set_location(None)
    project.mark_clean()
    assert not bar._location_button.isHidden()  # visible before Hours of Sun is enabled
    bar._heatmap_button.click()
    qtbot.waitUntil(lambda: win._live_sun_map._failed is not None)
    assert bar._map_label.isHidden()  # the actionable explanation replaces "unavailable"
    opened = []

    def choose_location(dialog):
        opened.append(dialog)
        assert dialog.windowTitle() == "Set Garden Location"
        dialog._lat_spin.setValue(0)  # zero is a valid coordinate, not missing
        dialog._lon_spin.setValue(0)
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(LocationDialog, "exec", choose_location)
    bar._location_button.click()
    assert len(opened) == 1
    if not accepted:
        assert project.location is None and not project.is_dirty
        assert not bar._location_button.isHidden()
        assert not jobs
        return
    assert project.location["latitude"] == project.location["longitude"] == 0
    assert bar._location_button.isHidden()
    qtbot.waitUntil(lambda: len(jobs) == 1)
    complete(win, qtbot, jobs)
    assert win._live_sun_map.is_current()
    assert bar._map_label.isHidden()
    # Document replacement must show the prerequisite again, without toggling the toolbar.
    project.new_project()
    assert not bar._location_button.isHidden()


def test_month_day_clamping_time_edit_animation_and_today(win):
    bar = win._sun_toolbar
    bar._date_edit.setDate(QDate(2028, 1, 31))
    bar._time_edit.setTime(QTime(15, 17))
    bar.set_animation_active(True)
    bar._month_slider.setSliderDown(True)
    bar._month_slider.setValue(month_number(date(2028, 2, 1)))
    assert win._sim_clock.plan_date == date(2028, 2, 29)
    bar._on_animate_tick()
    bar._month_slider.setValue(month_number(date(2028, 3, 1)))
    assert win._sim_clock.plan_date == date(2028, 3, 31)
    assert bar.animation_active and win._sim_clock.time_of_day == time(15, 27)
    bar._month_slider.setSliderDown(False)
    bar._date_edit.setDate(QDate(2027, 6, 21))
    bar._month_slider.setValue(month_number(date(2027, 7, 1)))
    assert win._sim_clock.plan_date == date(2027, 7, 21)
    bar._today_button.click()
    assert win._sim_clock.plan_date == date.today()
    assert win._sim_clock.time_of_day == time(15, 27)
    assert bar._today_button.text() == bar.tr("Today") and not bar._today_button.isEnabled()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1284, 800])
@pytest.mark.parametrize("language", ["en", "de", "es"])
@pytest.mark.parametrize("located", [True, False])
def test_themed_strip_centres_controls_and_uses_status_space_only_when_needed(qtbot, theme, width, language, located):
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

    app = QApplication.instance()
    original_stylesheet = app.styleSheet()
    original_theme = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    try:
        load_translator(app, language)
        apply_theme(app, ThemeMode(theme))
        get_settings().show_welcome_on_startup = False
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        if located:
            win._project_manager.set_location(BERLIN)
            win._project_manager.mark_clean()
        win._sim_clock.set_date(date.today())
        win.resize(width, 800)
        win.show()
        qtbot.wait(60)
        # a size set before the first show did not hold on CI's Linux runner (the
        # "1284" variants ran at 796 px): set it again once shown, and check it held
        win.resize(width, 800)
        qtbot.wait(20)
        assert win.width() == width, (win.width(), width)
        bar = win._sun_toolbar
        assert bar._today_button.text() == bar.tr("Today")  # the button itself says where the date is
        assert bar._date_edit.height() == bar._time_edit.height()
        assert bar._map_label.isHidden()
        for group_index in range(bar._flow.count()):
            group = bar._flow.itemAt(group_index).widget()
            # Check immediate controls, excluding nested line edits/spin buttons.
            controls = [group.layout().itemAt(i).widget() for i in range(group.layout().count())]
            centres = [child.mapTo(bar, child.rect().center()).y() for child in controls if child.isVisible()]
            assert max(centres) - min(centres) <= 1
        month_centre = bar._month_slider.mapTo(bar, bar._month_slider.rect().center()).y()
        time_centre = bar._slider.mapTo(bar, bar._slider.rect().center()).y()
        if width == 1284:
            # the measured groups, so a CI failure says how far the row is over
            assert abs(month_centre - time_centre) <= 1, (
                [bar._flow.itemAt(i).widget().sizeHint().width() for i in range(bar._flow.count())],
                bar.flow_width(), bar._today_button.width(), bar.font().family(),
                bar.font().pointSizeF(), bar.logicalDpiX())

        assert bar._location_button.isVisible() == (not located)
        if not located:
            assert bar._location_button.text() == bar.tr("Set location for sunlight…")
            assert bar._content.rect().contains(bar._location_button.parentWidget().geometry())
            assert len({bar._flow.itemAt(i).widget().y() for i in range(bar._flow.count())}) <= 2
            bar.set_map_status(None, False, "unavailable")
            assert bar._map_label.isHidden() and bar._location_button.isVisible()
            return

        bar.set_map_status(date.today(), False)
        qtbot.wait(20)
        assert bar._map_label.isHidden()  # A current map shares the sole calendar's date.
        heat_right = bar._heatmap_button.mapTo(bar, QPoint(bar._heatmap_button.width(), 0)).x()
        hidden_left = bar._hidden_button.mapTo(bar, QPoint()).x()
        assert 0 <= hidden_left - heat_right <= bar._flow.spacing() + 1

        bar.set_map_status(date.today(), True)
        assert bar._map_label.text() == bar.tr("Updating…")

        old_day = date(2025, 6, 21)
        bar.set_map_status(old_day, True)
        qtbot.wait(20)
        assert bar._map_label.isVisible()
        assert old_day.isoformat() in bar._map_label.text() and bar.tr("Updating…") in bar._map_label.text()
        # A retained result's status tuple can stay unchanged while the selected
        # date moves. The presentation must still follow the sole calendar.
        bar.set_datetime_local(datetime.combine(old_day, time(12)))
        assert bar._map_label.text() == bar.tr("Updating…")
        bar.set_map_status(old_day, False, "failure")
        assert bar._map_label.text() == "failure"
        bar.set_map_status(None, False)
        qtbot.wait(20)
        assert bar._map_label.isHidden()
        win._sim_clock.set_date(old_day)
        assert bar._today_button.text() == bar.tr("Past") and bar._today_button.isEnabled()
    finally:
        load_translator(app, "en")
        apply_theme(app, original_theme)
        app.setStyleSheet(original_stylesheet)


@pytest.mark.parametrize("width", [1600, 1000, 800])
def test_groups_wrap_without_clipping_and_calendar_fits(win, qtbot, width):
    win.resize(width, 800)
    win.show()
    qtbot.wait(80)
    bar = win._sun_toolbar
    bar._flow.activate()
    groups = [bar._flow.itemAt(i).widget() for i in range(bar._flow.count())]
    assert all(bar._content.rect().contains(group.geometry()) for group in groups)
    assert bar._date_edit.width() >= bar._date_edit.fontMetrics().horizontalAdvance("2000-00-00") + 40
    rows = {group.y() for group in groups}
    assert 1 <= len(rows) <= 2
    if width == 1600:
        assert len(rows) == 1


@pytest.mark.parametrize("theme", [None, "dark"])
@pytest.mark.parametrize("language", ["de", "es"])
@pytest.mark.parametrize("font_points", [9, 10])
def test_translated_controls_fit_two_rows_at_narrow_width(
    qtbot, language, font_points, theme, ui_font_family,
):
    # themed too: the theme's padding put German at 10 pt on a third row once the
    # Today button made room for "Vergangenheit" (PR #584 review). The family is
    # the session's real one (PF-TST-26): offscreen Windows has no font database,
    # so conftest registers a Windows face instead of measuring the box engine.
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

    app = QApplication.instance()
    original_font = app.font()
    original_stylesheet = app.styleSheet()
    original_theme = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    try:
        app.setFont(QFont(ui_font_family, font_points))

        assert load_translator(app, language)
        if theme is not None:
            apply_theme(app, ThemeMode(theme))
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        win.resize(800, 800)
        win.show()
        qtbot.wait(80)
        win.resize(800, 800)
        win._sun_toolbar.set_map_status(date(2026, 6, 21), True)
        qtbot.wait(50)
        bar = win._sun_toolbar
        groups = [bar._flow.itemAt(i).widget() for i in range(bar._flow.count())]
        assert len({group.y() for group in groups}) == 2, [
            (group.width(), group.sizeHint().width(), group.y()) for group in groups]
        assert all(bar._content.rect().contains(group.geometry()) for group in groups)
        # the reflow's own criterion, not only the layout's slack beyond it
        assert bar._flow.rows_for_width(bar.flow_width()) <= 2, bar._month_slider.width()
        win.resize(1650, 800)
        qtbot.wait(50)
        assert len({group.y() for group in groups}) == 1
        assert bar._month_slider.width() == bar._slider.width() == 180
        win.resize(800, 800)
        qtbot.wait(50)
        assert len({group.y() for group in groups}) == 2
        assert all(bar._content.rect().contains(group.geometry()) for group in groups)
    finally:
        app.setFont(original_font)
        load_translator(app, "en")
        if theme is not None:
            apply_theme(app, original_theme)
            app.setStyleSheet(original_stylesheet)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_today_button_says_past_or_future_in_place_and_nothing_after_it_moves(qtbot, theme, language):
    """Owner manual pass of #386: a separate Past/Future label changed width as the
    date moved and pushed the controls after it, the month slider being dragged
    included. The Today button says it in its own place, at one width."""
    from PyQt6.QtWidgets import QToolButton

    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

    app = QApplication.instance()
    original_stylesheet = app.styleSheet()
    original_theme = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    try:
        assert load_translator(app, language)
        apply_theme(app, ThemeMode(theme))
        get_settings().show_welcome_on_startup = False
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        win._sim_clock.set_date(date.today())
        win.resize(1284, 800)
        win.show()
        qtbot.wait(60)
        win.resize(1284, 800)  # once shown: a size set before did not hold on CI's Linux
        qtbot.wait(20)
        assert win.width() == 1284, win.width()
        bar = win._sun_toolbar
        button = bar._today_button
        width, slider_x = button.width(), bar._month_slider.mapTo(bar, QPoint()).x()
        assert button.text() == bar.tr("Today") and not button.isEnabled()
        now = bar._month_slider.value()
        # the scrub the owner made: across today and back, by the month slider
        for month, text in ((now - 1, bar.tr("Past")), (now + 3, bar.tr("Future")),
                            (now - 12, bar.tr("Past")), (now, bar.tr("Today"))):
            bar._month_slider.setValue(month)
            qtbot.wait(20)
            assert button.text() == text
            assert button.isEnabled() == (text != bar.tr("Today"))
            assert button.width() == width, text
            assert bar._month_slider.mapTo(bar, QPoint()).x() == slider_x, text
        assert win._sim_clock.plan_date == date.today()
        for text in (bar.tr("Today"), bar.tr("Past"), bar.tr("Future")):
            probe = QToolButton(bar)  # the same style: the plain size of this one text
            probe.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            probe.setText(text)
            probe.ensurePolished()
            assert probe.sizeHint().width() < width, text
            probe.deleteLater()
        win._sim_clock.set_date(date(date.today().year + 2, 6, 1))
        assert button.text() == bar.tr("Future")
        assert button.toolTip() == bar.tr("The plan date is in the future. Click to go back to today.")
        button.click()
        assert win._sim_clock.plan_date == date.today()
        assert button.text() == bar.tr("Today") and not button.isEnabled()
    finally:
        load_translator(app, "en")
        apply_theme(app, original_theme)
        app.setStyleSheet(original_stylesheet)


@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_today_button_width_holds_with_fractional_font_metrics(qtbot, language):
    """Qt measures a tool button's text as a bounding rect rounded up. The one width
    must be built from that measure, or fractional metrics move it by 1 px (PR #584
    review: 378 of 480 font/scale/language combinations did with horizontalAdvance).
    Unhinted fonts at fractional sizes give fractional advances on a real font engine;
    the offscreen platform's box engine has only whole ones, so a run there proves
    little - run with QT_QPA_PLATFORM=minimal:enable_fonts for real fonts, headless."""
    from PyQt6.QtGui import QFontMetrics

    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

    box = QFontMetrics(QFont("Verdana", 9))
    if box.horizontalAdvance("i") == box.horizontalAdvance("W"):
        pytest.skip("box font engine (offscreen on Windows): every advance is whole, nothing to measure")
    app = QApplication.instance()
    try:
        assert load_translator(app, language)
        bar = SunSimToolbar()
        qtbot.addWidget(bar)
        button = bar._today_button
        now = datetime.now().replace(second=0, microsecond=0)
        for family in ("Verdana", "Segoe UI", "DejaVu Sans", "Arial"):
            for points in (8.25, 8.5, 9.0, 9.5, 10.5):
                font = QFont(family)
                font.setPointSizeF(points)
                font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                button.setFont(font)
                widths = {}
                for days in (0, -40, 40):
                    bar.set_datetime_local(now + timedelta(days=days))
                    widths[button.text()] = button.sizeHint().width()
                assert len(widths) == 3 and len(set(widths.values())) == 1, (family, points, widths)
    finally:
        load_translator(app, "en")


def test_live_date_change_retains_honestly_dated_preview_and_latest_request(win, qtbot, jobs):
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    first = win._sun_heatmap.displayed_snapshot
    win._sun_toolbar._date_edit.setDate(QDate(2027, 6, 21))
    assert win._sun_toolbar._heatmap_button.isChecked()
    assert win._sun_toolbar._heatmap_button.isEnabled()
    assert win._sun_heatmap.heatmap_visible()
    assert win._sun_heatmap.displayed_snapshot == first
    assert "2026-06-21" in win._sun_toolbar._map_label.text()
    assert "Updating" in win._sun_toolbar._map_label.text()
    qtbot.waitUntil(lambda: len(jobs) == 2)
    for year in (2028, 2029, 2030):
        win._sun_toolbar._date_edit.setDate(QDate(year, 6, 21))
    assert win._sun_heatmap.receiver_minutes == {}
    jobs[1][1].set()
    qtbot.waitUntil(lambda: len(jobs) == 3)
    assert jobs[2][0]._day == date(2030, 6, 21)
    assert win._sun_heatmap.displayed_snapshot == first
    complete(win, qtbot, jobs, 2)
    assert win._sun_heatmap.displayed_snapshot.day == date(2030, 6, 21)
    assert "Updating" not in win._sun_toolbar._map_label.text()


def test_time_animation_does_not_request_full_day_work(win, qtbot, jobs):
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    for _ in range(10):
        win._sun_toolbar._on_animate_tick()
    qtbot.wait(300)
    assert len(jobs) == 1 and win._live_sun_map.is_current()


def test_bulk_layer_changes_debounce_scene_collection_itself(win, qtbot, jobs, monkeypatch):
    from open_garden_planner.core.commands import SetLayerPropertyCommand

    layer = win.canvas_scene.layers[0]
    for number in range(150):
        item = RectangleItem(number, 100, 20, 20, object_type=ObjectType.TOOL_SHED)
        item.layer_id = layer.id
        win.canvas_scene.addItem(item)
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    captures = []
    collect = win._live_sun_map._snapshot
    def counted():
        captures.append(True)
        return collect()
    monkeypatch.setattr(win._live_sun_map, "_snapshot", counted)
    win.canvas_view.command_manager.execute(
        SetLayerPropertyCommand(win.canvas_scene, layer, "visible", True, False))
    assert captures == []  # no synchronous O(N) scan for any of the N notifications
    assert not win._live_sun_map.is_current()
    qtbot.waitUntil(lambda: len(jobs) == 2)
    assert len(captures) == 1
    complete(win, qtbot, jobs, 1)


@pytest.mark.parametrize("hop", ["begin", "render"])
def test_abandoned_bridge_hop_cannot_pause_animation_or_write_later(win, qtbot, monkeypatch, tmp_path, hop):
    gate = win._sun_export_gate
    bridge = win._agent_bridge
    original = bridge.run_on_main
    queued = Event()
    deliver = Event()
    calls = []
    def short_hop(action):
        calls.append(True)
        if len(calls) == (1 if hop == "begin" else 2):
            queued.set()
            assert deliver.wait(2)
            return original(action, timeout=.05)
        return original(action)
    monkeypatch.setattr(bridge, "run_on_main", short_hop)
    win._sun_toolbar.set_animation_active(True)
    target = tmp_path / "abandoned.png"
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(gate.run_worker, bridge, lambda: target.write_bytes(b"wrong"))
        if hop == "render":
            # Let the initial hop execute, then deliberately stop servicing Qt.
            qtbot.waitUntil(queued.is_set)
        else:
            assert queued.wait(1)
        deliver.set()
        # Waiting here without event processing deterministically abandons the hop.
        with pytest.raises(TimeoutError):
            future.result(timeout=1)
    QApplication.processEvents()  # deliver the abandoned begin/render and its cleanup
    qtbot.waitUntil(lambda: gate._leases == 0)
    assert win._sun_toolbar.animation_active
    assert not target.exists()


def test_edit_refreshes_map_and_off_rejects_late_result(win, qtbot, jobs):
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    win.canvas_scene.addItem(RectangleItem(100, 100, 60, 60, object_type=ObjectType.TOOL_SHED))
    qtbot.waitUntil(lambda: len(jobs) == 2)
    win._sun_toolbar._heatmap_button.click()
    jobs[1][1].set()
    qtbot.waitUntil(lambda: not win._sun_heatmap.result_pending)
    assert not win._sun_heatmap.heatmap_visible()
    assert win._sun_heatmap.displayed_snapshot is None
    qtbot.wait(250)
    assert len(jobs) == 2 and not win._live_sun_map.enabled


def test_location_and_document_changes_drop_old_preview(win, qtbot, jobs):
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    win._project_manager.set_location({"latitude": 50, "longitude": 8})
    assert not win._sun_heatmap.heatmap_visible()
    qtbot.waitUntil(lambda: len(jobs) == 2)
    win._new_project_document(width_cm=500, height_cm=500)
    jobs[1][1].set()
    qtbot.waitUntil(lambda: not win._sun_heatmap.result_pending)
    assert win._sun_heatmap.displayed_snapshot is None and not win._live_sun_map.enabled


def test_gui_export_waits_then_renders_current_result_and_resumes_animation(win, qtbot, jobs):
    start(win, qtbot, jobs)
    win._sun_toolbar.set_animation_active(True)
    QTimer.singleShot(80, jobs[0][1].set)
    seen = []
    result = win._sun_export_gate.run_gui(lambda: seen.append(win._sun_heatmap.displayed_snapshot) or "rendered")
    assert result == "rendered" and seen == [win._sun_heatmap.displayed_snapshot]
    assert seen[0].day == win._sim_clock.plan_date
    assert win._sun_toolbar.animation_active


def test_gui_export_cancel_writes_nothing(win, qtbot, jobs, tmp_path):
    start(win, qtbot, jobs)
    target = tmp_path / "must-not-exist.png"
    def cancel():
        dialog = next((w for w in QApplication.topLevelWidgets() if isinstance(w, QProgressDialog)), None)
        if dialog is not None:
            dialog.cancel()
    QTimer.singleShot(60, cancel)
    with pytest.raises(RuntimeError, match="canceled"):
        win._sun_export_gate.run_gui(lambda: target.write_bytes(b"wrong"))
    assert not target.exists()


def test_gui_cancel_wins_when_readiness_finishes_in_same_event_turn(win, monkeypatch, tmp_path):
    readiness = Future()
    monkeypatch.setattr(win._live_sun_map, "ensure_current", lambda: readiness)
    target = tmp_path / "must-not-write-ready-map.png"
    def ready_then_cancel():
        readiness.set_result(None)
        dialog = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QProgressDialog))
        dialog.cancel()
    QTimer.singleShot(40, ready_then_cancel)
    with pytest.raises(RuntimeError, match="canceled"):
        win._sun_export_gate.run_gui(lambda: target.write_bytes(b"must not be written"))
    assert not target.exists()


def test_worker_export_waits_outside_gui_and_times_out_without_writing(win, qtbot, jobs, tmp_path):
    start(win, qtbot, jobs)
    target = tmp_path / "must-not-exist.pdf"
    win._sun_export_gate.timeout_s = .08
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(win._sun_export_gate.run_worker, win._agent_bridge,
                             lambda: target.write_bytes(b"wrong"))
        qtbot.waitUntil(future.done)
        with pytest.raises(TimeoutError, match="timed out"):
            future.result()
    assert not target.exists()


def test_worker_export_returns_to_gui_only_for_snapshot_and_render(win, qtbot, jobs):
    start(win, qtbot, jobs)
    gui_thread = get_ident()
    seen = []
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(win._sun_export_gate.run_worker, win._agent_bridge,
                             lambda: seen.append(get_ident()) or "ready")
        QTimer.singleShot(80, jobs[0][1].set)
        qtbot.waitUntil(future.done)
        assert future.result() == "ready"
    assert seen == [gui_thread]


def test_document_replacement_fails_waiting_export(win, qtbot, jobs):
    start(win, qtbot, jobs)
    future = win._live_sun_map.ensure_current()
    win._new_project_document(width_cm=500, height_cm=500)
    with pytest.raises(RuntimeError, match="document was replaced"):
        future.result()


def test_no_map_export_still_rejects_document_replacement(win, tmp_path):
    gate = win._sun_export_gate
    request = gate._begin()
    try:
        win._new_project_document(width_cm=500, height_cm=500)
        target = tmp_path / "wrong.png"
        with pytest.raises(RuntimeError, match="garden changed"):
            gate._render(request, lambda: target.write_bytes(b"wrong"))
        assert not target.exists()
    finally:
        gate._end()


def test_missing_location_fails_export_without_waiting(win, qtbot):
    win._project_manager.set_location(None)
    win._sun_toolbar._heatmap_button.click()
    ready = win._live_sun_map.ensure_current()
    assert ready.done()
    with pytest.raises(RuntimeError, match="location"):
        ready.result()
    assert win._sun_toolbar._heatmap_button.isEnabled()


def test_failed_refresh_labels_old_map_unavailable_and_refuses_export(win, qtbot, jobs):
    start(win, qtbot, jobs)
    complete(win, qtbot, jobs)
    win._sim_clock.set_date(date(2027, 6, 21))
    qtbot.waitUntil(lambda: len(jobs) == 2)
    jobs[1][0]._test_fail = True
    jobs[1][1].set()
    qtbot.waitUntil(lambda: not win._sun_heatmap.result_pending)
    assert "Unavailable" in win._sun_toolbar._map_label.text()
    with pytest.raises(RuntimeError, match="could not be computed"):
        win._live_sun_map.ensure_current().result()


def test_real_mcp_image_and_pdf_wait_for_current_map(win, qtbot, jobs, monkeypatch, tmp_path):
    from tests.integration.test_agent_api_lifecycle import _run, _server

    start(win, qtbot, jobs)
    pending = []
    begin = win._sun_export_gate._begin
    def observe():
        request = begin()
        pending.append(not request.ready.done())
        worker = win._sun_heatmap._worker
        def release_worker():
            next(release for candidate, release in jobs if candidate is worker).set()
        QTimer.singleShot(80, release_worker)
        return request
    monkeypatch.setattr(win._sun_export_gate, "_begin", observe)
    target = tmp_path / "current.pdf"
    server = _server(win)
    async def body(ctx):
        http_client, client_session, url = ctx
        async with http_client(url) as (read, write, _), client_session(read, write) as session:
            await session.initialize()
            rendered = await session.call_tool("render_canvas_image", {"image_width_px": 400})
            assert not rendered.isError and any(part.type == "image" for part in rendered.content)
            win._agent_bridge.run_on_main(lambda: win._sim_clock.set_date(date(2027, 6, 21)))
            exported = await session.call_tool("export_pdf", {"file_path": str(target)})
            assert not exported.isError, exported.content
    try:
        _run(server, body, qtbot)
    finally:
        server.stop()
    assert pending == [True, True]
    assert target.read_bytes().startswith(b"%PDF")
    assert win._sun_heatmap.displayed_snapshot.day == date(2027, 6, 21)


def test_real_mcp_timeout_returns_error_and_creates_no_pdf(win, qtbot, jobs, tmp_path):
    from tests.integration.test_agent_api_lifecycle import _run, _server

    start(win, qtbot, jobs)
    win._sun_export_gate.timeout_s = .08
    target = tmp_path / "must-not-exist.pdf"
    server = _server(win)
    async def body(ctx):
        http_client, client_session, url = ctx
        async with http_client(url) as (read, write, _), client_session(read, write) as session:
            await session.initialize()
            result = await session.call_tool("export_pdf", {"file_path": str(target)})
            assert result.isError
            assert "timed out" in str(result.content)
    try:
        _run(server, body, qtbot)
    finally:
        server.stop()
    assert not target.exists()
