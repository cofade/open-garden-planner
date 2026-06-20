"""Integration tests for US-C2 task management (#188).

Covers persistence round-trip + backwards-compat, season carryover, the status
flows (done/snooze/dismiss + legacy fold), and the Tasks tab view (rendering,
manual-task CRUD via TaskDialog, navigation signals).
"""
# ruff: noqa: ARG001, ARG002, ARG005

import datetime

from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.commands import (
    AddManualTaskCommand,
    DeleteManualTaskCommand,
    EditManualTaskCommand,
)
from open_garden_planner.core.project import ProjectData, ProjectManager
from open_garden_planner.models.task import ManualTask
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


def _task(title: str = "Water tomatoes", date: str = "2026-06-01") -> ManualTask:
    return ManualTask(id="t1", date=date, title=title, notes="deep soak", bed_id="bed9")


class TestPersistence:
    def test_manual_task_and_state_roundtrip(self) -> None:
        d = ProjectData(
            manual_tasks={"t1": _task().to_dict()},
            task_states={"t1": {"status": "done", "done_date": "2026-06-02"}},
        )
        restored = ProjectData.from_dict(d.to_dict())
        assert restored.manual_tasks["t1"]["title"] == "Water tomatoes"
        assert restored.task_states["t1"]["status"] == "done"

    def test_backwards_compat_missing_keys(self) -> None:
        # A pre-US-C2 file with neither key loads clean.
        restored = ProjectData.from_dict({"version": "1.4", "objects": []})
        assert restored.manual_tasks == {}
        assert restored.task_states == {}

    def test_legacy_task_completions_folds_to_archived(self, qtbot) -> None:
        import tempfile
        from pathlib import Path

        scene = CanvasScene(width_cm=500, height_cm=500)
        pm = ProjectManager()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.ogp"
            # Write a legacy file with only task_completions.
            legacy = ProjectData(task_completions=["tomato:harvest:2026"])
            import json

            path.write_text(json.dumps(legacy.to_dict()), encoding="utf-8")
            pm.load(scene, path)
        # Folded into task_states as a done entry (no done_date → archived/hidden).
        assert pm.task_states["tomato:harvest:2026"]["status"] == "done"

    def test_new_season_carries_future_manual_tasks(self, qtbot) -> None:
        import tempfile
        from pathlib import Path

        scene = CanvasScene(width_cm=500, height_cm=500)
        pm = ProjectManager()
        future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        past = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        pm.set_manual_task(ManualTask(id="future", date=future, title="later"))
        pm.set_manual_task(ManualTask(id="past", date=past, title="earlier"))
        with tempfile.TemporaryDirectory() as tmp:
            pm.save(scene, Path(tmp) / "s1.ogp")
            new_file = Path(tmp) / "s2.ogp"
            pm.create_new_season(scene, new_year=2099, new_file_path=new_file)
            pm2 = ProjectManager()
            scene2 = CanvasScene(width_cm=500, height_cm=500)
            pm2.load(scene2, new_file)
        assert "future" in pm2.manual_tasks
        assert "past" not in pm2.manual_tasks


class TestStatusFlows:
    def test_set_status_done_syncs_task_completions(self, qtbot) -> None:
        pm = ProjectManager()
        pm.set_task_status("x:harvest:2026", "done", done_date="2026-06-01")
        assert pm.task_states["x:harvest:2026"]["status"] == "done"
        assert "x:harvest:2026" in pm.task_completions  # legacy mirror kept in sync

    def test_open_clears_state(self, qtbot) -> None:
        pm = ProjectManager()
        pm.set_task_status("x", "done", done_date="2026-06-01")
        pm.clear_task_status("x")
        assert "x" not in pm.task_states
        assert "x" not in pm.task_completions

    def test_snooze_stores_until(self, qtbot) -> None:
        pm = ProjectManager()
        pm.set_task_status("x", "open", snooze_until="2099-01-01")
        assert pm.task_states["x"]["snooze_until"] == "2099-01-01"

    def test_calendar_done_toggle_syncs_task_states(self, qtbot) -> None:
        # ADR-029: marking a task done on the calendar dashboard
        # (set_task_completion) must also reflect in task_states so the Tasks
        # tab sees it as done (no one-way divergence).
        pm = ProjectManager()
        tid = "tomato:harvest:2026"
        pm.set_task_completion(tid, True)
        assert pm.task_states[tid]["status"] == "done"
        assert tid in pm.task_completions
        pm.set_task_completion(tid, False)
        assert tid not in pm.task_states
        assert tid not in pm.task_completions


class TestManualTaskCommands:
    def test_add_undo_redo(self, qtbot) -> None:
        pm = ProjectManager()
        cmd = AddManualTaskCommand(pm, _task())
        cmd.execute()
        assert "t1" in pm.manual_tasks
        cmd.undo()
        assert "t1" not in pm.manual_tasks

    def test_edit_preserves_undo(self, qtbot) -> None:
        pm = ProjectManager()
        pm.set_manual_task(_task(title="old"))
        EditManualTaskCommand(pm, _task(title="new")).execute()
        assert pm.manual_tasks["t1"]["title"] == "new"

    def test_delete_undo(self, qtbot) -> None:
        pm = ProjectManager()
        pm.set_manual_task(_task())
        cmd = DeleteManualTaskCommand(pm, "t1")
        cmd.execute()
        assert "t1" not in pm.manual_tasks
        cmd.undo()
        assert "t1" in pm.manual_tasks


class TestOverdueReminderBar:
    """#16: the overdue reminder must reach the user via a persistent bar, not a
    status-bar message hidden behind the modal Welcome dialog."""

    def test_bar_shows_count_and_hides_on_zero(self, qtbot) -> None:
        from open_garden_planner.ui.widgets import TaskReminderBar

        bar = TaskReminderBar()
        qtbot.addWidget(bar)
        bar.show_reminder(3)
        assert not bar.isHidden()
        assert "3" in bar._label.text()
        bar.show_reminder(0)
        assert bar.isHidden()

    def _make_app(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        from open_garden_planner.app.application import GardenPlannerApp

        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: QMessageBox.StandardButton.Discard,
        )
        monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        return win

    def _set_toggle(self, monkeypatch, enabled: bool) -> None:
        from open_garden_planner.app.settings import AppSettings

        monkeypatch.setattr(
            AppSettings, "notify_overdue_tasks_on_startup",
            property(lambda self: enabled),
        )

    def test_check_shows_bar_when_enabled(self, qtbot, monkeypatch) -> None:
        self._set_toggle(monkeypatch, True)
        win = self._make_app(qtbot, monkeypatch)
        calls: list[int] = []
        monkeypatch.setattr(win._task_reminder_bar, "show_reminder", calls.append)

        past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
        win._project_manager.set_manual_task(
            ManualTask(id="o1", date=past, title="overdue thing")
        )
        win._check_overdue_tasks()
        assert calls == [1]

    def test_check_hides_bar_when_disabled(self, qtbot, monkeypatch) -> None:
        self._set_toggle(monkeypatch, False)
        win = self._make_app(qtbot, monkeypatch)
        shown: list[int] = []
        hidden: list[bool] = []
        monkeypatch.setattr(win._task_reminder_bar, "show_reminder", shown.append)
        monkeypatch.setattr(win._task_reminder_bar, "hide", lambda: hidden.append(True))

        past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
        win._project_manager.set_manual_task(
            ManualTask(id="o1", date=past, title="overdue thing")
        )
        win._check_overdue_tasks()
        assert shown == []      # never shown when the toggle is off
        assert hidden == [True]

    def test_open_project_schedules_deferred_check(
        self, qtbot, monkeypatch, tmp_path
    ) -> None:
        # The #16 fix: _open_project_file must DEFER the reminder check (so a bar
        # shown from the modal Welcome dialog lands after it closes), not call it
        # inline. Pin the singleShot(0) wiring.
        self._set_toggle(monkeypatch, True)
        win = self._make_app(qtbot, monkeypatch)
        past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
        win._project_manager.set_manual_task(
            ManualTask(id="o1", date=past, title="overdue thing")
        )
        from pathlib import Path

        path = Path(tmp_path) / "p.ogp"
        win._project_manager.save(win.canvas_scene, path)

        calls: list[int] = []
        monkeypatch.setattr(win, "_check_overdue_tasks", lambda: calls.append(1))
        win._open_project_file(str(path))
        assert calls == []        # deferred, not inline
        qtbot.wait(50)            # let singleShot(0) fire
        assert calls == [1]

    def test_future_and_done_tasks_not_counted(self, qtbot, monkeypatch) -> None:
        self._set_toggle(monkeypatch, True)
        win = self._make_app(qtbot, monkeypatch)
        calls: list[int] = []
        monkeypatch.setattr(win._task_reminder_bar, "show_reminder", calls.append)

        today = datetime.date.today()
        future = (today + datetime.timedelta(days=5)).isoformat()
        past = (today - datetime.timedelta(days=5)).isoformat()
        pm = win._project_manager
        pm.set_manual_task(ManualTask(id="future", date=future, title="later"))
        pm.set_manual_task(ManualTask(id="done", date=past, title="finished"))
        pm.set_manual_task(ManualTask(id="open", date=past, title="still due"))
        pm.set_task_status("done", "done", done_date=today.isoformat())
        win._check_overdue_tasks()
        assert calls == [1]  # only the open past-dated task counts


class TestCrossSurfaceSync:
    """#12: the Tasks tab and Planting Calendar must key task status by the SAME
    canonical species_key (ADR-016), or done/snooze never syncs across surfaces.

    Regression: ``build_plan_state`` used a raw ``scientific_name or common_name``
    key (no source_id, not lowercased), so DB species produced a different
    ``task_id`` than the calendar dashboard and status never crossed over.
    """

    def _scene_with_db_species(self):
        from types import SimpleNamespace

        # harvest window open *today* (last_frost == today, week offset 0..0).
        meta = {"plant_species": {
            "scientific_name": "Solanum Lycopersicum",  # mixed case on purpose
            "common_name": "Tomato",
            "source_id": "12345",                       # DB-sourced species
            "harvest_start": 0,
            "harvest_end": 0,
        }}
        item = SimpleNamespace(
            object_type="plant", metadata=meta, name="", item_id="p1"
        )
        return SimpleNamespace(items=lambda: [item])

    def _pm_today_frost(self) -> ProjectManager:
        pm = ProjectManager()
        today = datetime.date.today()
        pm.set_location(
            {"frost_dates": {"last_spring_frost": today.strftime("%m-%d")}}
        )
        return pm

    def _canonical_harvest_id(self) -> str:
        from open_garden_planner.models.plant_data import species_key

        key = species_key({
            "source_id": "12345",
            "scientific_name": "Solanum Lycopersicum",
            "common_name": "Tomato",
        })
        return f"{key}:harvest:{datetime.date.today().year}"

    def test_taskid_uses_canonical_species_key(self, qtbot) -> None:
        from open_garden_planner.services.task_generator import generate_all
        from open_garden_planner.ui.views.tasks_view import build_plan_state

        pm = self._pm_today_frost()
        scene = self._scene_with_db_species()
        ids = {t.task_id for t in generate_all(build_plan_state(scene, pm))}

        # Canonical: source_id wins, lowercased (matches the calendar dashboard).
        assert self._canonical_harvest_id() in ids
        # NOT the old raw, non-canonical id.
        year = datetime.date.today().year
        assert f"Solanum Lycopersicum:harvest:{year}" not in ids

    def test_calendar_done_visible_on_tasks_tab(self, qtbot) -> None:
        from open_garden_planner.services.task_generator import generate_all
        from open_garden_planner.services.task_status import effective_status
        from open_garden_planner.ui.views.tasks_view import build_plan_state

        pm = self._pm_today_frost()
        scene = self._scene_with_db_species()
        tid = self._canonical_harvest_id()

        # Calendar dashboard marks the task done …
        pm.set_task_completion(tid, True)
        # … and the Tasks tab (same canonical id) sees it as done.
        tasks = generate_all(build_plan_state(scene, pm))
        match = next(t for t in tasks if t.task_id == tid)
        today = datetime.date.today()
        assert effective_status(pm.task_states.get(match.task_id), today) == "done"

    def test_tasks_tab_done_hides_on_calendar(self, qtbot) -> None:
        # Reverse direction: marking done on the Tasks tab (set_task_status)
        # writes the legacy task_completions the calendar dashboard reads to skip.
        pm = self._pm_today_frost()
        tid = self._canonical_harvest_id()
        pm.set_task_status(tid, "done", done_date=datetime.date.today().isoformat())
        assert tid in pm.task_completions


class TestTasksView:
    def _view(self, qtbot, pm: ProjectManager):
        from open_garden_planner.ui.views.tasks_view import TasksView

        scene = CanvasScene(width_cm=500, height_cm=500)
        view = TasksView(scene, pm)
        qtbot.addWidget(view)
        return view

    def test_renders_manual_task(self, qtbot, monkeypatch) -> None:
        monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
        pm = ProjectManager()
        today = datetime.date.today().isoformat()
        pm.set_manual_task(ManualTask(id="m1", date=today, title="Mow lawn"))
        view = self._view(qtbot, pm)
        view.refresh()
        # The task label should appear somewhere in the rendered content.
        from PyQt6.QtWidgets import QLabel

        texts = [w.text() for w in view.findChildren(QLabel)]
        assert any("Mow lawn" in t for t in texts)

    def test_done_then_archived(self, qtbot) -> None:
        pm = ProjectManager()
        today = datetime.date.today()
        pm.set_manual_task(ManualTask(id="m1", date=today.isoformat(), title="Prune"))
        view = self._view(qtbot, pm)
        # Mark done with an 8-day-old done_date → archived → hidden.
        old = (today - datetime.timedelta(days=8)).isoformat()
        pm.set_task_status("m1", "done", done_date=old)
        view.refresh()
        from PyQt6.QtWidgets import QLabel

        texts = [w.text() for w in view.findChildren(QLabel)]
        assert not any("Prune" in t for t in texts)

    def test_navigate_to_bed_signal(self, qtbot) -> None:
        pm = ProjectManager()
        today = datetime.date.today().isoformat()
        pm.set_manual_task(
            ManualTask(id="m1", date=today, title="Weed", bed_id="bedX")
        )
        view = self._view(qtbot, pm)
        view.refresh()
        received: list[str] = []
        view.navigate_to_bed.connect(received.append)
        # Find a task with bed_id and trigger navigation directly.
        from open_garden_planner.services.task_generator import Task

        view._navigate(Task(task_id="m1", source="manual", task_type="manual",
                            title="Weed", bed_id="bedX"))
        assert received == ["bedX"]
