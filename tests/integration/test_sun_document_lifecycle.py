"""Old workers and overlays must not cross document boundaries (#428)."""

from datetime import date
from threading import Event

import numpy as np
import pytest
from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.ui.canvas.sun_heatmap import HeatmapWorker

DAY = date(2026, 6, 21)
BERLIN = {"latitude": 52.52, "longitude": 13.405}


@pytest.mark.parametrize("operation", ["new", "open", "recovery"])
@pytest.mark.parametrize("queued", [False, True])
def test_document_replacement_rejects_old_worker(qtbot, monkeypatch, tmp_path, operation, queued):
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._sim_clock.set_date(DAY)
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    replacement = tmp_path / "replacement.ogp"
    win._project_manager.save(win.canvas_scene, replacement)
    win._project_manager.set_location(BERLIN)
    release = Event()
    entered = Event()

    def controlled_run(worker):
        entered.set()
        release.wait(5)
        # Deliberately emit even after cancellation to exercise the GUI guard.
        worker.success.emit(np.full((worker._grid.rows, worker._grid.cols), 990, np.float32))

    monkeypatch.setattr(HeatmapWorker, "run", controlled_run)
    heatmap = win._sun_heatmap
    try:
        assert heatmap.run_for_day(DAY, cell_cm=100)
        assert entered.wait(5)
        win._sun_toolbar.set_heatmap_active(True)
        if queued:
            release.set()
            assert heatmap._worker.wait(5000)
            assert heatmap.result_pending and not heatmap.is_running
        if operation == "new":
            win._new_project_document(width_cm=1000, height_cm=1000)
        elif operation == "open":
            win._load_project_file(str(replacement))
        else:
            win._load_recovery_file(replacement)
        release.set()
        qtbot.waitUntil(lambda: not heatmap.result_pending, timeout=5000)
        assert not heatmap.heatmap_visible()
        assert not win._sun_toolbar._heatmap_button.isChecked()
        win._project_manager.set_location(BERLIN)
        with qtbot.waitSignal(heatmap.finished, timeout=5000) as result:
            assert heatmap.run_for_day(DAY, cell_cm=100)
        assert result.args == [True]
    finally:
        release.set()
        heatmap.shutdown()


def test_failed_prevalidation_preserves_heatmap(qtbot, monkeypatch, tmp_path):
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._sim_clock.set_date(DAY)
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    win._project_manager.set_location(BERLIN)
    with qtbot.waitSignal(win._sun_heatmap.finished, timeout=5000):
        assert win._sun_heatmap.run_for_day(DAY, cell_cm=100)
    win._sun_toolbar.set_heatmap_active(True)
    broken = tmp_path / "broken.ogp"
    broken.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        win._load_project_file(str(broken))
    assert win._sun_heatmap.heatmap_visible()
    assert win._sun_toolbar._heatmap_button.isChecked()


@pytest.mark.parametrize("operation", ["new_plan", "open_plan"])
@pytest.mark.parametrize("queued", [False, True])
def test_document_replacement_over_real_mcp(qtbot, monkeypatch, tmp_path, operation, queued):
    from tests.integration.test_agent_api_lifecycle import _caller, _run, _server

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._sim_clock.set_date(DAY)
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    target = tmp_path / "wire.ogp"
    win._project_manager.save(win.canvas_scene, target)
    win._project_manager.set_location(BERLIN)
    release, entered = Event(), Event()
    def controlled_run(worker):
        entered.set()
        release.wait(15)
        worker.success.emit(np.full((worker._grid.rows, worker._grid.cols), 990, np.float32))
    monkeypatch.setattr(HeatmapWorker, "run", controlled_run)
    server = _server(win)
    try:
        assert win._sun_heatmap.run_for_day(DAY, cell_cm=100)
        assert entered.wait(5)
        win._sun_toolbar.set_heatmap_active(True)
        if queued:
            release.set()
            assert win._sun_heatmap._worker.wait(5000)
        args = {"force": True}
        if operation == "open_plan":
            args["file_path"] = str(target)
        else:
            args.update(width_cm=1000, height_cm=1000)
        _run(server, _caller({"tool": operation, "args": args}), qtbot)
        release.set()
        qtbot.waitUntil(lambda: not win._sun_heatmap.result_pending)
        assert not win._sun_heatmap.heatmap_visible() and not win._sun_heatmap.receiver_minutes
        assert not win._sun_toolbar._heatmap_button.isChecked()
        assert not win.sun_exposure_coordinator.evaluations
    finally:
        release.set()
        win._sun_heatmap.shutdown()
        server.stop()
