"""Integration tests for US-C1 — harvest tracking / yield log (#188).

Covers:
  * HarvestRecord / HarvestHistory serialisation round-trip
  * Add / Edit / Delete commands undo/redo
  * The journal link: Add creates a pin-less ``harvest``-tagged note; undo removes it
  * .ogp save/load round-trip + backwards-compat (missing ``harvest_logs``)
  * Season carryover keeps year-stamped harvest history
  * Garden-wide aggregation + CSV export
  * HarvestView dashboard renders rows and emits navigation
  * HarvestLogDialog round-trips entered values
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_garden_planner.core import (
    AddHarvestRecordCommand,
    DeleteHarvestRecordCommand,
    EditHarvestRecordCommand,
    ProjectManager,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.harvest_aggregation import aggregate_by_species_year
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.views.harvest_view import HarvestView


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001 — Qt init
    return ProjectManager()


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class TestHarvestRecord:
    def test_round_trip_all_fields(self) -> None:
        rec = HarvestRecord(
            date="2026-06-24",
            quantity=2.5,
            unit="kg",
            quality="excellent",
            notes="first picking",
            photo_path="harvest_photos/abc.jpg",
            journal_note_id="note-1",
        )
        rt = HarvestRecord.from_dict(rec.to_dict())
        assert rt.date == "2026-06-24"
        assert rt.quantity == 2.5
        assert rt.unit == "kg"
        assert rt.quality == "excellent"
        assert rt.notes == "first picking"
        assert rt.photo_path == "harvest_photos/abc.jpg"
        assert rt.journal_note_id == "note-1"

    def test_history_round_trip_caches_species(self) -> None:
        hist = HarvestHistory(
            target_id="p1",
            species_key="tomato",
            species_name="Tomato",
            records=[HarvestRecord(date="2026-06-24", quantity=1.0, unit="kg")],
        )
        rt = HarvestHistory.from_dict(hist.to_dict())
        assert rt.species_key == "tomato"
        assert rt.species_name == "Tomato"
        assert len(rt.records) == 1


# ---------------------------------------------------------------------------
# Commands + journal link
# ---------------------------------------------------------------------------

class TestHarvestCommands:
    def test_add_creates_history_and_journal_note(
        self, project_manager: ProjectManager
    ) -> None:
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        cmd = AddHarvestRecordCommand(
            project_manager, "p1", rec, species_key="tomato", species_name="Tomato"
        )
        cmd.execute()
        history = project_manager.get_harvest_history("p1")
        assert len(history.records) == 1
        assert history.species_key == "tomato"
        # A pin-less, harvest-tagged journal note was created.
        notes = project_manager.garden_journal_notes
        assert len(notes) == 1
        note = next(iter(notes.values()))
        assert note["tags"] == ["harvest"]
        assert "Tomato" in note["text"]
        # The record links back to it.
        assert history.records[0].journal_note_id == note["id"]

    def test_undo_removes_record_and_note(
        self, project_manager: ProjectManager
    ) -> None:
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        cmd = AddHarvestRecordCommand(
            project_manager, "p1", rec, species_key="tomato", species_name="Tomato"
        )
        cmd.execute()
        cmd.undo()
        assert "p1" not in project_manager.harvest_logs
        assert project_manager.garden_journal_notes == {}

    def test_edit_updates_record_and_note(
        self, project_manager: ProjectManager
    ) -> None:
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        AddHarvestRecordCommand(
            project_manager, "p1", rec, species_key="tomato", species_name="Tomato"
        ).execute()
        note_id = project_manager.get_harvest_history("p1").records[0].journal_note_id

        edited = HarvestRecord(
            id=rec.id,
            date="2026-06-25",
            quantity=4.0,
            unit="kg",
            journal_note_id=note_id,
        )
        EditHarvestRecordCommand(project_manager, "p1", edited).execute()
        history = project_manager.get_harvest_history("p1")
        assert history.records[0].quantity == 4.0
        note = project_manager.garden_journal_notes[note_id]
        assert note["date"] == "2026-06-25"
        assert "4 kg" in note["text"]

    def test_delete_removes_record_and_note_and_undo_restores(
        self, project_manager: ProjectManager
    ) -> None:
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        AddHarvestRecordCommand(
            project_manager, "p1", rec, species_key="tomato", species_name="Tomato"
        ).execute()
        note_id = project_manager.get_harvest_history("p1").records[0].journal_note_id

        cmd = DeleteHarvestRecordCommand(project_manager, "p1", rec.id)
        cmd.execute()
        assert project_manager.get_harvest_history("p1").records == []
        assert note_id not in project_manager.garden_journal_notes
        cmd.undo()
        assert len(project_manager.get_harvest_history("p1").records) == 1
        assert note_id in project_manager.garden_journal_notes

    def test_delete_last_record_removes_key(
        self, project_manager: ProjectManager
    ) -> None:
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        AddHarvestRecordCommand(
            project_manager, "p1", rec, species_key="tomato", species_name="Tomato"
        ).execute()
        DeleteHarvestRecordCommand(project_manager, "p1", rec.id).execute()
        # No phantom empty history left behind.
        assert "p1" not in project_manager.harvest_logs


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestOgpRoundTrip:
    def test_harvest_logs_persist_through_save_load(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        plant = RectangleItem(100, 100, 50, 50, object_type=ObjectType.PERENNIAL)
        scene.addItem(plant)
        rec = HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg")
        AddHarvestRecordCommand(
            project_manager, str(plant.item_id), rec,
            species_key="tomato", species_name="Tomato",
        ).execute()

        path = tmp_path / "test.ogp"
        project_manager.save(scene, path)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "harvest_logs" in raw
        assert str(plant.item_id) in raw["harvest_logs"]

        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2 = ProjectManager()
        pm2.load(scene2, path)
        history = pm2.get_harvest_history(str(plant.item_id))
        assert len(history.records) == 1
        assert history.records[0].quantity == 2.5
        assert history.species_name == "Tomato"

    def test_backwards_compat_missing_key(self) -> None:
        from open_garden_planner.core.project import ProjectData

        restored = ProjectData.from_dict({"version": "1.4", "objects": []})
        assert restored.harvest_logs == {}

    def test_season_carryover_keeps_harvest(
        self, project_manager: ProjectManager, scene: CanvasScene, tmp_path: Path
    ) -> None:
        plant = RectangleItem(100, 100, 50, 50, object_type=ObjectType.PERENNIAL)
        scene.addItem(plant)
        AddHarvestRecordCommand(
            project_manager, str(plant.item_id),
            HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg"),
            species_key="tomato", species_name="Tomato",
        ).execute()
        season_a = tmp_path / "2026.ogp"
        project_manager.save(scene, season_a)
        project_manager._season_year = 2026  # type: ignore[attr-defined]
        season_b = tmp_path / "2027.ogp"
        project_manager.create_new_season(scene, 2027, season_b, keep_plants=True)
        with open(season_b, encoding="utf-8") as f:
            raw = json.load(f)
        carried = raw.get("harvest_logs", {})
        assert str(plant.item_id) in carried
        # The new season starts with a blank journal, so the carried record's
        # journal link is severed (no dangling reference).
        assert raw.get("garden_journal_notes", {}) == {}
        rec_raw = carried[str(plant.item_id)]["records"][0]
        assert rec_raw.get("journal_note_id") is None


# ---------------------------------------------------------------------------
# Aggregation + CSV
# ---------------------------------------------------------------------------

class TestAggregationAndExport:
    def test_dashboard_totals_match(self, project_manager: ProjectManager) -> None:
        for q in (2.0, 1.5):
            AddHarvestRecordCommand(
                project_manager, "p1",
                HarvestRecord(date="2026-06-24", quantity=q, unit="kg"),
                species_key="tomato", species_name="Tomato",
            ).execute()
        rows = aggregate_by_species_year(project_manager.harvest_logs)
        assert len(rows) == 1
        assert rows[0].total_quantity == 3.5
        assert rows[0].entry_count == 2

    def test_csv_export_row_count(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        AddHarvestRecordCommand(
            project_manager, "p1",
            HarvestRecord(date="2026-06-24", quantity=2.0, unit="kg"),
            species_key="tomato", species_name="Tomato",
        ).execute()
        AddHarvestRecordCommand(
            project_manager, "p2",
            HarvestRecord(date="2025-07-01", quantity=5, unit="pcs"),
            species_key="lettuce", species_name="Lettuce",
        ).execute()
        path = tmp_path / "harvest.csv"
        n = ExportService.export_harvest_to_csv(project_manager.harvest_logs, path)
        assert n == 2
        text = path.read_text(encoding="utf-8-sig")
        assert "Tomato" in text
        assert "Lettuce" in text


# ---------------------------------------------------------------------------
# Dashboard view (end-to-end UI)
# ---------------------------------------------------------------------------

class TestHarvestView:
    def test_view_renders_rows_and_navigates(
        self, qtbot: object, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        AddHarvestRecordCommand(
            project_manager, "p1",
            HarvestRecord(date="2026-06-24", quantity=2.5, unit="kg"),
            species_key="tomato", species_name="Tomato",
        ).execute()
        view = HarvestView(scene, project_manager)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._table.rowCount() == 1
        assert view._table.item(0, 0).text() == "Tomato"

        captured: list[str] = []
        view.navigate_to_species.connect(captured.append)
        view._on_row_double_clicked(view._table.item(0, 0))
        assert captured == ["tomato"]

    def test_view_empty_state(
        self, qtbot: object, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        view = HarvestView(scene, project_manager)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        assert view._table.rowCount() == 0
        # The empty-state label is shown and the table hidden (checked via the
        # explicit setVisible state — isVisible() needs a shown top-level window).
        assert not view._empty_label.isHidden()
        assert view._table.isHidden()


# ---------------------------------------------------------------------------
# Dialog (UI)
# ---------------------------------------------------------------------------

class TestHarvestLogDialog:
    def test_result_record_round_trips_values(self, qtbot: object) -> None:
        from open_garden_planner.ui.dialogs import HarvestLogDialog

        dlg = HarvestLogDialog(target_id="p1", target_name="Tomato")
        qtbot.addWidget(dlg)  # type: ignore[attr-defined]
        dlg.set_values(
            date="2026-06-24", quantity=3.0, unit="pcs", quality="good", notes="n"
        )
        assert dlg.has_new_entry is True
        rec = dlg.result_record()
        assert rec.date == "2026-06-24"
        assert rec.quantity == 3.0
        assert rec.unit == "pcs"
        assert rec.quality == "good"
        assert rec.notes == "n"

    def test_journal_dialog_preserves_harvest_tag(self, qtbot: object) -> None:
        # Editing a harvest-linked note through the Journal dialog must not
        # strip its ["harvest"] tag (US-C1 desync guard).
        from open_garden_planner.models.journal_note import JournalNote
        from open_garden_planner.ui.dialogs.journal_note_dialog import (
            JournalNoteDialog,
        )

        note = JournalNote(date="2026-06-24", text="Harvested 2 kg", tags=["harvest"])
        dlg = JournalNoteDialog(note=note)
        qtbot.addWidget(dlg)  # type: ignore[attr-defined]
        assert dlg.result_note().tags == ["harvest"]
