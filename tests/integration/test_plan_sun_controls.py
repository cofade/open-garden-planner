"""Combined date/time controls, accurate live-map previews and export readiness."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date, datetime, time
from threading import Event, get_ident

import numpy as np
import pytest
from PyQt6.QtCore import QDate, QTime, QTimer
from PyQt6.QtWidgets import QApplication, QDateEdit, QProgressDialog, QToolBar
from PyQt6.sip import isdeleted

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plan_timeline import month_number
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import HeatmapWorker

BERLIN = {"latitude": 52.52, "longitude": 13.405}


@pytest.fixture
def win(qtbot, monkeypatch):
    get_settings().show_welcome_on_startup = False
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    monkeypatch.setattr(app, "_confirm_discard_changes", lambda: True)
    app._sim_clock.set_datetime(datetime(2026, 6, 21, 12))
    app._project_manager._location = dict(BERLIN)
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
    assert not app._live_sun_map.enabled
    assert len(app._sun_toolbar.findChildren(QDateEdit)) == 1
    names = [bar.objectName() for bar in app.findChildren(QToolBar)]
    assert names.count("SunSimToolbar") == 1 and "PlanTimelineToolbar" not in names
    assert not hasattr(app, "_sun_sim_action") and not hasattr(app, "_shadows_action")
    assert not hasattr(app._sun_toolbar, "_june_button")


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
    assert bar._state_label.text() == "Today"


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
    assert len(rows) == (1 if width == 1600 else 2)


@pytest.mark.parametrize("language", ["de", "es"])
def test_translated_controls_fit_two_rows_at_narrow_width(qtbot, language):
    from open_garden_planner.core.i18n import load_translator

    app = QApplication.instance()
    try:
        assert load_translator(app, language)
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
        assert len({group.y() for group in groups}) == 2
        assert all(bar._content.rect().contains(group.geometry()) for group in groups)
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
