"""Integration tests for the harvest log (US-C1, issue #188).

Covers the command + persistence layer (add/edit/delete, auto journal note,
undo/redo, .ogp round-trip + backwards-compat), CSV export, and the garden-wide
Harvest Log tab aggregation.
"""

# ruff: noqa: ARG002

from pathlib import Path

import pytest

from open_garden_planner.core import (
    AddHarvestEntryCommand,
    CommandManager,
    DeleteHarvestEntryCommand,
    EditHarvestEntryCommand,
    ProjectManager,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.harvest_log import HarvestEntry
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem


@pytest.fixture()
def pm(qtbot) -> ProjectManager:
    return ProjectManager()


def _entry(**kw) -> HarvestEntry:
    base = {"date": "2026-06-15", "quantity": 1.5, "unit": "kg", "id": "e1"}
    base.update(kw)
    return HarvestEntry(**base)


class TestHarvestCommands:
    def test_add_persists_and_undo_clears(self, pm: ProjectManager) -> None:
        mgr = CommandManager()
        mgr.execute(AddHarvestEntryCommand(pm, "plant-1", _entry()))
        assert "plant-1" in pm.harvest_logs
        assert pm.get_harvest_history("plant-1").entries[0].quantity == 1.5
        mgr.undo()
        assert "plant-1" not in pm.harvest_logs
        mgr.redo()
        assert pm.get_harvest_history("plant-1").entries[0].id == "e1"

    def test_add_marks_dirty(self, pm: ProjectManager) -> None:
        mgr = CommandManager()
        pm.mark_clean()
        mgr.execute(AddHarvestEntryCommand(pm, "plant-1", _entry()))
        assert pm.is_dirty

    def test_edit_replaces_entry(self, pm: ProjectManager) -> None:
        mgr = CommandManager()
        mgr.execute(AddHarvestEntryCommand(pm, "p1", _entry()))
        mgr.execute(EditHarvestEntryCommand(pm, "p1", _entry(quantity=9.0)))
        assert pm.get_harvest_history("p1").entries[0].quantity == 9.0
        mgr.undo()
        assert pm.get_harvest_history("p1").entries[0].quantity == 1.5

    def test_delete_removes_entry(self, pm: ProjectManager) -> None:
        mgr = CommandManager()
        mgr.execute(AddHarvestEntryCommand(pm, "p1", _entry()))
        mgr.execute(DeleteHarvestEntryCommand(pm, "p1", "e1"))
        assert pm.get_harvest_history("p1").entries == []
        mgr.undo()
        assert len(pm.get_harvest_history("p1").entries) == 1

    def test_add_with_journal_note_and_pin(self, qtbot, pm: ProjectManager) -> None:
        from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

        scene = CanvasScene(width_cm=500, height_cm=500)
        note = JournalNote(date="2026-06-15", text="[harvest] 1.5 kg — Tomato")
        pin = JournalPinItem(x=10, y=20, note_id=note.id)
        entry = _entry(journal_note_id=note.id)
        mgr = CommandManager()

        mgr.execute(
            AddHarvestEntryCommand(pm, "p1", entry, scene=scene, pin_item=pin, note=note)
        )
        assert note.id in pm.garden_journal_notes
        assert any(isinstance(i, JournalPinItem) for i in scene.items())

        mgr.undo()
        assert note.id not in pm.garden_journal_notes
        assert not any(isinstance(i, JournalPinItem) for i in scene.items())
        assert "p1" not in pm.harvest_logs

        # Redo must restore entry + note + pin atomically, with no duplication.
        mgr.redo()
        assert note.id in pm.garden_journal_notes
        pins = [i for i in scene.items() if isinstance(i, JournalPinItem)]
        assert len(pins) == 1
        assert len(pm.get_harvest_history("p1").entries) == 1


class TestHarvestPersistence:
    def test_round_trip_ogp(self, qtbot, pm: ProjectManager, tmp_path: Path) -> None:
        scene = CanvasScene(width_cm=500, height_cm=500)
        CommandManager().execute(AddHarvestEntryCommand(pm, "p1", _entry()))
        target = tmp_path / "garden.ogp"
        pm.save(scene, target)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=500, height_cm=500)
        pm2.load(scene2, target)
        assert pm2.get_harvest_history("p1").entries[0].quantity == 1.5

    def test_new_season_carries_harvest_logs(
        self, qtbot, pm: ProjectManager, tmp_path: Path
    ) -> None:
        # Harvest entries are a permanent dated record: a season rollover must
        # carry them into the new season file (unlike journal notes, which drop).
        scene = CanvasScene(width_cm=500, height_cm=500)
        CommandManager().execute(AddHarvestEntryCommand(pm, "p1", _entry()))
        pm.save(scene, tmp_path / "season1.ogp")

        new_file = tmp_path / "season2.ogp"
        pm.create_new_season(scene, new_year=2027, new_file_path=new_file)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=500, height_cm=500)
        pm2.load(scene2, new_file)
        assert pm2.get_harvest_history("p1").entries[0].quantity == 1.5

    def test_backwards_compat_missing_key(
        self, qtbot, pm: ProjectManager, tmp_path: Path
    ) -> None:
        # An older .ogp without the harvest_logs key must load clean.
        import json

        old = {
            "version": "1.4",
            "canvas": {"width": 500, "height": 500},
            "layers": [],
            "objects": [],
        }
        target = tmp_path / "old.ogp"
        target.write_text(json.dumps(old), encoding="utf-8")
        scene = CanvasScene(width_cm=500, height_cm=500)
        pm.load(scene, target)
        assert pm.harvest_logs == {}


class TestHarvestCsvExport:
    def test_export_csv(self, qtbot, pm: ProjectManager, tmp_path: Path) -> None:
        from open_garden_planner.services.export_service import ExportService

        mgr = CommandManager()
        mgr.execute(AddHarvestEntryCommand(pm, "p1", _entry(quantity=2.0)))
        mgr.execute(
            AddHarvestEntryCommand(pm, "p1", _entry(id="e2", date="2026-07-01", quantity=3.0))
        )
        out = tmp_path / "h.csv"
        count = ExportService.export_harvest_log_to_csv(
            pm.harvest_logs, {"p1": "Tomato"}, out
        )
        assert count == 2
        text = out.read_text(encoding="utf-8-sig")
        assert "Tomato" in text
        assert "2026-07-01" in text


class TestHarvestPdfPage:
    def test_harvest_summary_page_renders(self, qtbot, tmp_path: Path) -> None:
        from open_garden_planner.models.harvest_log import HarvestLogHistory
        from open_garden_planner.services.pdf_report_service import (
            PdfReportOptions,
            PdfReportService,
        )

        scene = CanvasScene(width_cm=500, height_cm=500)
        tomato = CircleItem(0, 0, 25, object_type=ObjectType.PERENNIAL)
        tomato.name = "Tomato"
        scene.addItem(tomato)
        harvest_data = {
            str(tomato.item_id): HarvestLogHistory(
                str(tomato.item_id), [_entry(quantity=2.0)]
            ).to_dict()
        }
        opts = PdfReportOptions(
            include_cover=True,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_garden_notes=False,
            include_harvest_summary=True,
            harvest_data=harvest_data,
            include_legend=False,
            project_name="Test",
        )
        out = tmp_path / "report.pdf"
        PdfReportService.generate(scene, opts, out)
        assert out.exists() and out.stat().st_size > 0


class TestHarvestLogTab:
    def test_tab_aggregates(self, qtbot, pm: ProjectManager) -> None:
        from open_garden_planner.ui.views.harvest_log_view import HarvestLogView

        scene = CanvasScene(width_cm=500, height_cm=500)
        tomato = CircleItem(0, 0, 25, object_type=ObjectType.PERENNIAL)
        tomato.name = "Tomato"
        scene.addItem(tomato)

        mgr = CommandManager()
        mgr.execute(
            AddHarvestEntryCommand(pm, str(tomato.item_id), _entry(quantity=2.0))
        )

        view = HarvestLogView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()
        # Crop, Unit, 2026, Total -> 4 columns; one data row.
        assert view._table.rowCount() == 1
        assert view._table.item(0, 0).text() == "Tomato"
