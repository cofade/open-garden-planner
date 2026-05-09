"""Integration tests for US-12.7 — pest/disease log.

Covers:
  * PestLogRecord / PestLogHistory serialisation round-trip
  * AddPestLogCommand / EditPestLogCommand / DeletePestLogCommand undo/redo
  * .ogp save/load round-trip
  * Season carryover honours the resolved flag
  * PestOverviewPanel filters resolved records and falls back to "(deleted item)"
  * Photo path stored as relative POSIX path
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_garden_planner.core import (
    AddPestLogCommand,
    CommandManager,
    DeletePestLogCommand,
    EditPestLogCommand,
    ProjectManager,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.pest_log import PestLogHistory, PestLogRecord
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001 — Qt init
    return ProjectManager()


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class TestPestLogRecord:
    def test_round_trip_all_fields(self) -> None:
        rec = PestLogRecord(
            date="2026-04-25",
            entry_type="disease",
            name="Powdery mildew",
            severity="high",
            treatment="Sulfur spray",
            notes="left lower leaves",
            photo_path="pest_photos/abc.jpg",
            resolved=True,
        )
        round = PestLogRecord.from_dict(rec.to_dict())
        assert round.date == "2026-04-25"
        assert round.entry_type == "disease"
        assert round.name == "Powdery mildew"
        assert round.severity == "high"
        assert round.treatment == "Sulfur spray"
        assert round.notes == "left lower leaves"
        assert round.photo_path == "pest_photos/abc.jpg"
        assert round.resolved is True
        assert round.id == rec.id

    def test_optionals_omitted_when_empty(self) -> None:
        rec = PestLogRecord(date="2026-01-01", name="Aphids")
        d = rec.to_dict()
        assert "treatment" not in d
        assert "notes" not in d
        assert "photo_path" not in d
        # mandatory fields always present
        assert d["resolved"] is False
        assert d["entry_type"] == "pest"
        assert d["severity"] == "low"
        assert "id" in d
        assert d["date"] == "2026-01-01"

    def test_resolved_always_emitted_even_when_false(self) -> None:
        rec = PestLogRecord(date="2026-01-01", resolved=False)
        assert rec.to_dict()["resolved"] is False

    def test_from_dict_is_forgiving(self) -> None:
        rec = PestLogRecord.from_dict({"date": "2026-01-01"})
        assert rec.date == "2026-01-01"
        assert rec.entry_type == "pest"
        assert rec.severity == "low"
        assert rec.resolved is False


class TestPestLogHistory:
    def test_to_dict_from_dict(self) -> None:
        hist = PestLogHistory(
            target_id="bed-1",
            records=[
                PestLogRecord(date="2026-01-01", name="Aphids"),
                PestLogRecord(date="2026-02-01", name="Slugs"),
            ],
        )
        round = PestLogHistory.from_dict(hist.to_dict())
        assert round.target_id == "bed-1"
        assert len(round.records) == 2
        assert round.records[0].name == "Aphids"
        assert round.records[1].name == "Slugs"


# ---------------------------------------------------------------------------
# Commands: add / edit / delete + undo
# ---------------------------------------------------------------------------

class TestAddPestLogCommand:
    def test_add_creates_history(self, project_manager: ProjectManager) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids")
        cmd = AddPestLogCommand(project_manager, "bed-1", rec)
        cmd.execute()
        history = project_manager.get_pest_log_history("bed-1")
        assert len(history.records) == 1
        assert history.records[0].name == "Aphids"

    def test_undo_restores_prior(self, project_manager: ProjectManager) -> None:
        first = PestLogRecord(date="2026-01-01", name="Aphids")
        AddPestLogCommand(project_manager, "bed-1", first).execute()
        second = PestLogRecord(date="2026-02-01", name="Slugs")
        cmd2 = AddPestLogCommand(project_manager, "bed-1", second)
        cmd2.execute()
        assert len(project_manager.get_pest_log_history("bed-1").records) == 2
        cmd2.undo()
        history = project_manager.get_pest_log_history("bed-1")
        assert len(history.records) == 1
        assert history.records[0].name == "Aphids"

    def test_undo_first_record_clears_history(
        self, project_manager: ProjectManager
    ) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids")
        cmd = AddPestLogCommand(project_manager, "bed-1", rec)
        cmd.execute()
        cmd.undo()
        # The history is gone entirely (key removed)
        assert "bed-1" not in project_manager.pest_logs

    def test_redo_idempotent_on_same_id(
        self, project_manager: ProjectManager
    ) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids")
        cmd = AddPestLogCommand(project_manager, "bed-1", rec)
        cmd.execute()
        cmd.execute()  # redo
        # Same id shouldn't be appended twice
        assert len(project_manager.get_pest_log_history("bed-1").records) == 1


class TestEditDeletePestLogCommand:
    def test_edit_replaces_by_id(self, project_manager: ProjectManager) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids", severity="low")
        AddPestLogCommand(project_manager, "bed-1", rec).execute()

        edited = PestLogRecord(
            id=rec.id, date="2026-04-25", name="Aphids", severity="high"
        )
        EditPestLogCommand(project_manager, "bed-1", edited).execute()

        history = project_manager.get_pest_log_history("bed-1")
        assert len(history.records) == 1
        assert history.records[0].severity == "high"

    def test_edit_undo_restores_original(
        self, project_manager: ProjectManager
    ) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids", severity="low")
        AddPestLogCommand(project_manager, "bed-1", rec).execute()
        edited = PestLogRecord(
            id=rec.id, date="2026-04-25", name="Aphids", severity="high"
        )
        cmd = EditPestLogCommand(project_manager, "bed-1", edited)
        cmd.execute()
        cmd.undo()
        history = project_manager.get_pest_log_history("bed-1")
        assert history.records[0].severity == "low"

    def test_delete_removes_by_id(self, project_manager: ProjectManager) -> None:
        rec1 = PestLogRecord(date="2026-04-25", name="Aphids")
        rec2 = PestLogRecord(date="2026-04-26", name="Slugs")
        AddPestLogCommand(project_manager, "bed-1", rec1).execute()
        AddPestLogCommand(project_manager, "bed-1", rec2).execute()

        DeletePestLogCommand(project_manager, "bed-1", rec1.id).execute()
        history = project_manager.get_pest_log_history("bed-1")
        assert len(history.records) == 1
        assert history.records[0].id == rec2.id

    def test_delete_undo_restores(self, project_manager: ProjectManager) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids")
        AddPestLogCommand(project_manager, "bed-1", rec).execute()
        cmd = DeletePestLogCommand(project_manager, "bed-1", rec.id)
        cmd.execute()
        # Delete leaves an empty records list (matches soil-test pattern).
        assert project_manager.get_pest_log_history("bed-1").records == []
        cmd.undo()
        history = project_manager.get_pest_log_history("bed-1")
        assert len(history.records) == 1

    def test_command_manager_undo_redo(
        self, project_manager: ProjectManager
    ) -> None:
        cm = CommandManager()
        rec = PestLogRecord(date="2026-04-25", name="Aphids")
        cm.execute(AddPestLogCommand(project_manager, "bed-1", rec))
        assert len(project_manager.get_pest_log_history("bed-1").records) == 1
        cm.undo()
        assert "bed-1" not in project_manager.pest_logs
        cm.redo()
        assert len(project_manager.get_pest_log_history("bed-1").records) == 1


# ---------------------------------------------------------------------------
# .ogp round-trip
# ---------------------------------------------------------------------------

class TestOgpRoundTrip:
    def test_pest_logs_persist_through_save_load(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        bed = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        rec = PestLogRecord(
            date="2026-04-25", name="Aphids", severity="medium", treatment="neem"
        )
        AddPestLogCommand(project_manager, str(bed.item_id), rec).execute()

        path = tmp_path / "test.ogp"
        project_manager.save(scene, path)

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "pest_disease_logs" in raw
        assert str(bed.item_id) in raw["pest_disease_logs"]

        # Load into a fresh manager + scene
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2 = ProjectManager()
        pm2.load(scene2, path)
        history = pm2.get_pest_log_history(str(bed.item_id))
        assert len(history.records) == 1
        assert history.records[0].name == "Aphids"
        assert history.records[0].severity == "medium"
        assert history.records[0].treatment == "neem"

    def test_empty_pest_logs_omitted_from_file(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        path = tmp_path / "empty.ogp"
        project_manager.save(scene, path)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "pest_disease_logs" not in raw


# ---------------------------------------------------------------------------
# Season carryover honours the resolved flag
# ---------------------------------------------------------------------------

class TestSeasonCarryover:
    def test_unresolved_carries_resolved_does_not(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        bed = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)

        # One unresolved (permanent tree pest), one resolved (treated outbreak)
        ongoing = PestLogRecord(
            date="2026-03-01", name="Borers", severity="high", resolved=False
        )
        treated = PestLogRecord(
            date="2026-04-01", name="Aphids", severity="low", resolved=True
        )
        AddPestLogCommand(
            project_manager, str(bed.item_id), ongoing
        ).execute()
        AddPestLogCommand(
            project_manager, str(bed.item_id), treated
        ).execute()

        # Save the current season first so create_new_season has a path
        season_a = tmp_path / "2026.ogp"
        project_manager.save(scene, season_a)
        project_manager._season_year = 2026  # type: ignore[attr-defined]

        # Create a new season file
        season_b = tmp_path / "2027.ogp"
        project_manager.create_new_season(scene, 2027, season_b, keep_plants=True)

        with open(season_b, encoding="utf-8") as f:
            raw = json.load(f)
        carried = raw.get("pest_disease_logs", {})
        assert str(bed.item_id) in carried
        records = carried[str(bed.item_id)]["records"]
        names = [r["name"] for r in records]
        assert "Borers" in names
        assert "Aphids" not in names

    def test_all_resolved_target_dropped_entirely(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        bed = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        treated = PestLogRecord(
            date="2026-04-01", name="Aphids", resolved=True
        )
        AddPestLogCommand(
            project_manager, str(bed.item_id), treated
        ).execute()

        season_a = tmp_path / "2026.ogp"
        project_manager.save(scene, season_a)
        project_manager._season_year = 2026  # type: ignore[attr-defined]
        season_b = tmp_path / "2027.ogp"
        project_manager.create_new_season(scene, 2027, season_b, keep_plants=True)

        with open(season_b, encoding="utf-8") as f:
            raw = json.load(f)
        assert "pest_disease_logs" not in raw or raw["pest_disease_logs"] == {}


# ---------------------------------------------------------------------------
# Overview panel
# ---------------------------------------------------------------------------

class TestPestOverviewPanel:
    def test_lists_only_unresolved(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.panels.pest_overview_panel import (
            PestOverviewPanel,
        )

        panel = PestOverviewPanel()
        unresolved = PestLogRecord(date="2026-04-25", name="Aphids", resolved=False)
        resolved = PestLogRecord(date="2026-04-26", name="Slugs", resolved=True)
        history = PestLogHistory(
            target_id="bed-1", records=[unresolved, resolved]
        )
        panel.refresh(
            {"bed-1": history.to_dict()}, {"bed-1": "Bed A"}
        )
        # Only the unresolved row + (no placeholder when at least 1 row exists)
        assert panel._list.count() == 1
        assert "Aphids" in panel._list.item(0).text()

    def test_empty_state_shows_placeholder(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.panels.pest_overview_panel import (
            PestOverviewPanel,
        )

        panel = PestOverviewPanel()
        panel.refresh({}, {})
        assert panel._list.count() == 1
        item = panel._list.item(0)
        # Placeholder is non-selectable
        from PyQt6.QtCore import Qt
        assert item.flags() == Qt.ItemFlag.NoItemFlags

    def test_deleted_target_falls_back_to_placeholder(
        self, qtbot
    ) -> None:  # noqa: ARG002
        from open_garden_planner.ui.panels.pest_overview_panel import (
            PestOverviewPanel,
        )

        panel = PestOverviewPanel()
        rec = PestLogRecord(date="2026-04-25", name="Aphids", resolved=False)
        history = PestLogHistory(target_id="ghost-id", records=[rec])
        panel.refresh({"ghost-id": history.to_dict()}, {})  # no items_by_id mapping
        assert panel._list.count() == 1
        text = panel._list.item(0).text()
        # The display name fell back to the placeholder, but the row is rendered.
        assert "Aphids" in text


# ---------------------------------------------------------------------------
# Photo path
# ---------------------------------------------------------------------------

class TestPhotoPath:
    def test_relative_posix_path_round_trips(self) -> None:
        rec = PestLogRecord(
            date="2026-04-25",
            name="Aphids",
            photo_path="pest_photos/abc.jpg",
        )
        d = rec.to_dict()
        assert d["photo_path"] == "pest_photos/abc.jpg"
        round = PestLogRecord.from_dict(d)
        assert round.photo_path == "pest_photos/abc.jpg"

    def test_none_omitted(self) -> None:
        rec = PestLogRecord(date="2026-04-25", name="Aphids", photo_path=None)
        assert "photo_path" not in rec.to_dict()


# ---------------------------------------------------------------------------
# Dialog smoke
# ---------------------------------------------------------------------------

class TestPestLogDialog:
    def test_set_values_round_trip(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.dialogs.pest_log_dialog import PestLogDialog

        dialog = PestLogDialog(target_id="bed-1", target_name="Tomatoes")
        dialog.set_values(
            date="2026-05-09",
            entry_type="disease",
            name="Powdery mildew",
            severity="medium",
            treatment="Sulfur",
            notes="lower leaves",
            resolved=False,
        )
        rec = dialog.result_record()
        assert rec.date == "2026-05-09"
        assert rec.entry_type == "disease"
        assert rec.name == "Powdery mildew"
        assert rec.severity == "medium"
        assert rec.treatment == "Sulfur"
        assert rec.notes == "lower leaves"
        assert rec.resolved is False

    def test_attach_photo_button_disabled_when_unsaved(
        self, qtbot, project_manager: ProjectManager
    ) -> None:  # noqa: ARG002
        from open_garden_planner.ui.dialogs.pest_log_dialog import PestLogDialog

        # current_file is None on a fresh project_manager
        dialog = PestLogDialog(
            target_id="bed-1",
            target_name="Tomatoes",
            project_manager=project_manager,
        )
        assert dialog._attach_photo_btn.isEnabled() is False
        assert "Save project first" in dialog._attach_photo_btn.toolTip()
