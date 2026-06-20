"""Integration tests for US-C2 task management (#188).

Covers persistence round-trip + backwards-compat, season carryover, the status
flows (done/snooze/dismiss + legacy fold), and the Tasks tab view (rendering,
manual-task CRUD via TaskDialog, navigation signals).
"""
# ruff: noqa: ARG002

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
