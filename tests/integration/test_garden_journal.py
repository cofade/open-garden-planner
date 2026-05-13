"""Integration tests for US-12.9 — garden journal map-linked notes.

Covers:
  * JournalNote serialisation round-trip
  * AddJournalNoteCommand / EditJournalNoteCommand / DeleteJournalNoteCommand undo/redo
  * .ogp save/load round-trip (pin + note dict survive)
  * JournalPinItem ↔ ProjectManager wiring (a deleted pin removes its note)
  * JournalPanel filters by text query and date range
  * PdfReportService.generate produces a Garden Notes page when requested
  * create_new_season drops journal pins/notes (date-pinned historical record)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from open_garden_planner.core import (
    AddJournalNoteCommand,
    CommandManager,
    DeleteJournalNoteCommand,
    EditJournalNoteCommand,
    ProjectManager,
)
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.panels.journal_panel import JournalPanel


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001 — Qt init
    return ProjectManager()


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class TestJournalNote:
    def test_round_trip_all_fields(self) -> None:
        note = JournalNote(
            date="2026-05-13",
            text="Planted lettuce in bed A; cool spring weather.",
            photo_path="journal_photos/abc.jpg",
            scene_x=120.5,
            scene_y=88.0,
        )
        round_tripped = JournalNote.from_dict(note.to_dict())
        assert round_tripped.id == note.id
        assert round_tripped.date == "2026-05-13"
        assert round_tripped.text.startswith("Planted lettuce")
        assert round_tripped.photo_path == "journal_photos/abc.jpg"
        assert round_tripped.scene_x == pytest.approx(120.5)
        assert round_tripped.scene_y == pytest.approx(88.0)

    def test_optional_photo_omitted_when_none(self) -> None:
        note = JournalNote(date="2026-01-01", text="x", scene_x=0.0, scene_y=0.0)
        d = note.to_dict()
        assert "photo_path" not in d

    def test_from_dict_is_forgiving(self) -> None:
        note = JournalNote.from_dict({"text": "hello"})
        assert note.text == "hello"
        assert note.date == ""
        assert note.photo_path is None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class TestCommands:
    def test_add_command_persists_pin_and_note(
        self, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        note = JournalNote(date="2026-05-13", text="hi", scene_x=10.0, scene_y=20.0)
        pin = JournalPinItem(x=10.0, y=20.0, note_id=note.id)
        cmd = AddJournalNoteCommand(project_manager, scene, pin, note)
        manager = CommandManager()
        manager.execute(cmd)

        assert note.id in project_manager.garden_journal_notes
        assert pin.scene() is scene

    def test_undo_redo_cycles_pin_and_note(
        self, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        note = JournalNote(date="2026-05-13", text="hi", scene_x=10.0, scene_y=20.0)
        pin = JournalPinItem(x=10.0, y=20.0, note_id=note.id)
        cmd = AddJournalNoteCommand(project_manager, scene, pin, note)
        manager = CommandManager()
        manager.execute(cmd)

        manager.undo()
        assert note.id not in project_manager.garden_journal_notes
        assert pin.scene() is None

        manager.redo()
        assert note.id in project_manager.garden_journal_notes
        assert pin.scene() is scene

    def test_edit_command_updates_note_body(
        self, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        note = JournalNote(date="2026-05-13", text="initial", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        manager = CommandManager()
        manager.execute(AddJournalNoteCommand(project_manager, scene, pin, note))

        updated = JournalNote(
            id=note.id,
            date="2026-05-14",
            text="revised observation",
            scene_x=0.0,
            scene_y=0.0,
        )
        manager.execute(EditJournalNoteCommand(project_manager, updated))
        loaded = project_manager.get_journal_note(note.id)
        assert loaded is not None
        assert loaded.text == "revised observation"
        assert loaded.date == "2026-05-14"

        manager.undo()
        loaded = project_manager.get_journal_note(note.id)
        assert loaded is not None
        assert loaded.text == "initial"

    def test_delete_command_removes_pin_and_note_undoable(
        self, project_manager: ProjectManager, scene: CanvasScene
    ) -> None:
        note = JournalNote(date="2026-05-13", text="hi", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        manager = CommandManager()
        manager.execute(AddJournalNoteCommand(project_manager, scene, pin, note))

        manager.execute(DeleteJournalNoteCommand(project_manager, scene, pin))
        assert note.id not in project_manager.garden_journal_notes
        assert pin.scene() is None

        manager.undo()
        assert note.id in project_manager.garden_journal_notes
        assert pin.scene() is scene


# ---------------------------------------------------------------------------
# .ogp save / load round-trip
# ---------------------------------------------------------------------------


class TestReviewerRegressions:
    """Bug fixes from senior-reviewer pass on the US-12.9 branch."""

    def test_delete_key_path_routes_through_journal_command(
        self, project_manager: ProjectManager, scene: CanvasScene, qtbot: object  # noqa: ARG002
    ) -> None:
        """Selecting a pin and pressing Delete used to call DeleteItemsCommand
        directly, removing the pin from the scene but orphaning the note dict
        in ProjectData. The fix routes journal pins through
        DeleteJournalNoteCommand via journal_notes_batch_delete_requested.
        """
        from open_garden_planner.ui.canvas.canvas_view import CanvasView  # noqa: PLC0415

        note = JournalNote(date="2026-05-13", text="x", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        CommandManager().execute(
            AddJournalNoteCommand(project_manager, scene, pin, note)
        )
        assert note.id in project_manager.garden_journal_notes

        # Drive the path that handles the Delete key:
        # canvas_view splits pin ids off and emits journal_notes_batch_delete_requested.
        captured: list[list[str]] = []
        view = CanvasView(scene=scene)
        view.journal_notes_batch_delete_requested.connect(captured.append)
        pin.setSelected(True)
        view._delete_selected_items()

        assert captured == [[note.id]]

    def test_save_syncs_pin_pos_into_note_dict(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        """Dragging a pin used to leave note.scene_x/y stale through save/load.
        The fix syncs each note from its pin's pos() at save time.
        """
        note = JournalNote(date="2026-05-13", text="hi", scene_x=10.0, scene_y=20.0)
        pin = JournalPinItem(x=10.0, y=20.0, note_id=note.id)
        CommandManager().execute(
            AddJournalNoteCommand(project_manager, scene, pin, note)
        )
        # Simulate drag.
        pin.setPos(150.0, 250.0)
        path = tmp_path / "moved.ogp"
        project_manager.save(scene, path)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, path)
        reloaded = pm2.get_journal_note(note.id)
        assert reloaded is not None
        assert reloaded.scene_x == pytest.approx(150.0)
        assert reloaded.scene_y == pytest.approx(250.0)

    def test_pdf_garden_notes_paginates_long_content(
        self,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        """A garden with many long notes used to silently truncate at the
        first page boundary. The fix calls writer.newPage() automatically.
        """
        from open_garden_planner.services.pdf_report_service import (  # noqa: PLC0415
            PdfReportOptions,
            PdfReportService,
        )

        single_note = {"only": JournalNote(
            date="2026-05-13", text="short", scene_x=0.0, scene_y=0.0
        ).to_dict()}
        many_notes: dict[str, dict[str, object]] = {}
        long_body = "This is a journal note paragraph. " * 30
        for i in range(40):
            note = JournalNote(
                date=f"2026-{(i % 12) + 1:02d}-15",
                text=long_body,
                scene_x=0.0,
                scene_y=0.0,
            )
            many_notes[note.id] = note.to_dict()

        def _opts(notes: dict[str, dict[str, object]]) -> PdfReportOptions:
            return PdfReportOptions(
                include_cover=False,
                include_overview=False,
                include_bed_details=False,
                include_plant_list=False,
                include_garden_notes=True,
                garden_journal_notes=notes,
                include_legend=False,
                project_name="Test",
                author="Tester",
            )

        single_out = tmp_path / "single.pdf"
        many_out = tmp_path / "many.pdf"
        PdfReportService.generate(scene, _opts(single_note), single_out)
        PdfReportService.generate(scene, _opts(many_notes), many_out)

        # PDFs declare each page as `/Type /Page` (the root catalog is
        # `/Type /Pages` — note the trailing 's'). Counting the former gives
        # the page count without pulling in a PDF reader dependency.
        single_pages = single_out.read_bytes().count(b"/Type /Page\n") + \
            single_out.read_bytes().count(b"/Type /Page ")
        many_pages = many_out.read_bytes().count(b"/Type /Page\n") + \
            many_out.read_bytes().count(b"/Type /Page ")
        assert single_pages == 1
        # 40 notes × ~30 paragraph repeats spans multiple A4 pages now.
        assert many_pages > single_pages


class TestProjectRoundTrip:
    def test_notes_persist_through_save_load(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        note_a = JournalNote(
            date="2026-05-13", text="first", scene_x=50.0, scene_y=60.0
        )
        note_b = JournalNote(
            date="2026-05-14",
            text="second\nwith two lines",
            photo_path="journal_photos/foo.jpg",
            scene_x=70.0,
            scene_y=80.0,
        )
        pin_a = JournalPinItem(x=50.0, y=60.0, note_id=note_a.id)
        pin_b = JournalPinItem(x=70.0, y=80.0, note_id=note_b.id)
        manager = CommandManager()
        manager.execute(AddJournalNoteCommand(project_manager, scene, pin_a, note_a))
        manager.execute(AddJournalNoteCommand(project_manager, scene, pin_b, note_b))

        path = tmp_path / "garden.ogp"
        project_manager.save(scene, path)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, path)

        assert set(pm2.garden_journal_notes.keys()) == {note_a.id, note_b.id}
        loaded_b = pm2.get_journal_note(note_b.id)
        assert loaded_b is not None
        assert loaded_b.text == "second\nwith two lines"
        assert loaded_b.photo_path == "journal_photos/foo.jpg"

        pins_on_scene = [
            item for item in scene2.items() if isinstance(item, JournalPinItem)
        ]
        assert len(pins_on_scene) == 2
        note_ids = {p.note_id for p in pins_on_scene}
        assert note_ids == {note_a.id, note_b.id}

    def test_new_season_drops_journal_notes_and_pins(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        # Save the current project first so create_new_season has a source.
        note = JournalNote(date="2026-05-13", text="x", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        CommandManager().execute(
            AddJournalNoteCommand(project_manager, scene, pin, note)
        )
        path = tmp_path / "2026.ogp"
        project_manager.save(scene, path)
        project_manager.set_season(2026)
        project_manager.save(scene, path)

        new_path = tmp_path / "2027.ogp"
        project_manager.create_new_season(scene, 2027, new_path)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, new_path)

        assert pm2.garden_journal_notes == {}
        pins = [i for i in scene2.items() if isinstance(i, JournalPinItem)]
        assert pins == []


# ---------------------------------------------------------------------------
# Sidebar panel filtering
# ---------------------------------------------------------------------------


class TestJournalNoteDialog:
    def test_new_note_defaults_to_today(
        self, qtbot: object, project_manager: ProjectManager  # noqa: ARG002
    ) -> None:
        """Regression: opening the dialog for a fresh JournalNote with date=""
        used to leave the QDateEdit at Qt's default 2000-01-01."""
        from datetime import date as _date  # noqa: PLC0415

        from open_garden_planner.ui.dialogs.journal_note_dialog import (  # noqa: PLC0415
            JournalNoteDialog,
        )

        note = JournalNote(scene_x=0.0, scene_y=0.0)  # date=""
        dialog = JournalNoteDialog(
            parent=None, note=note, project_manager=project_manager
        )
        today = _date.today()
        qd = dialog._date_edit.date()
        assert (qd.year(), qd.month(), qd.day()) == (
            today.year, today.month, today.day
        )

    def test_dialog_preserves_existing_note_date(
        self, qtbot: object, project_manager: ProjectManager  # noqa: ARG002
    ) -> None:
        from open_garden_planner.ui.dialogs.journal_note_dialog import (  # noqa: PLC0415
            JournalNoteDialog,
        )

        note = JournalNote(date="2024-03-15", text="anchored", scene_x=0.0, scene_y=0.0)
        dialog = JournalNoteDialog(
            parent=None, note=note, project_manager=project_manager, edit_mode=True
        )
        qd = dialog._date_edit.date()
        assert (qd.year(), qd.month(), qd.day()) == (2024, 3, 15)


class TestJournalPanel:
    def test_panel_filters_by_text_query(self, qtbot: object) -> None:  # noqa: ARG002
        panel = JournalPanel()
        panel.refresh({
            "a": JournalNote(date="2026-05-01", text="planted lettuce").to_dict(),
            "b": JournalNote(date="2026-05-02", text="harvested radish").to_dict(),
            "c": JournalNote(date="2026-05-03", text="checked lettuce").to_dict(),
        })

        panel._search_edit.setText("lettuce")
        # textChanged auto-rebuilds the list. Real notes carry a UserRole id;
        # the placeholder row sets no data, so filtering by truthy data is enough.
        from PyQt6.QtCore import Qt as _Qt  # noqa: PLC0415

        ids = [
            panel._list.item(i).data(_Qt.ItemDataRole.UserRole)
            for i in range(panel._list.count())
        ]
        ids = [i for i in ids if i]
        assert set(ids) == {"a", "c"}

    def test_panel_filters_by_date_range(self, qtbot: object) -> None:  # noqa: ARG002
        from PyQt6.QtCore import QDate  # noqa: PLC0415

        panel = JournalPanel()
        panel.refresh({
            "a": JournalNote(date="2026-04-30", text="early").to_dict(),
            "b": JournalNote(date="2026-05-15", text="mid").to_dict(),
            "c": JournalNote(date="2026-06-10", text="late").to_dict(),
        })

        panel._range_check.setChecked(True)
        panel._date_from.setDate(QDate(2026, 5, 1))
        panel._date_to.setDate(QDate(2026, 5, 31))

        from PyQt6.QtCore import Qt as _Qt  # noqa: PLC0415

        ids = [
            panel._list.item(i).data(_Qt.ItemDataRole.UserRole)
            for i in range(panel._list.count())
        ]
        ids = [i for i in ids if i]
        assert ids == ["b"]


# ---------------------------------------------------------------------------
# PDF Garden Notes page
# ---------------------------------------------------------------------------


class TestPdfGardenNotesPage:
    def test_pdf_includes_garden_notes_page_when_requested(
        self,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        from open_garden_planner.services.pdf_report_service import (  # noqa: PLC0415
            PdfReportOptions,
            PdfReportService,
        )

        notes = {
            "n1": JournalNote(
                date="2026-05-13", text="first note", scene_x=0.0, scene_y=0.0
            ).to_dict(),
            "n2": JournalNote(
                date="2026-05-14", text="second note", scene_x=0.0, scene_y=0.0
            ).to_dict(),
        }
        opts = PdfReportOptions(
            include_cover=False,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_garden_notes=True,
            garden_journal_notes=notes,
            include_legend=False,
            project_name="Test",
            author="Tester",
        )
        out = tmp_path / "notes.pdf"
        PdfReportService.generate(scene, opts, out)
        assert out.exists()
        # PDF that contains a rendered page is non-trivially sized.
        assert out.stat().st_size > 1000

    def test_pdf_omits_garden_notes_page_by_default(
        self,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        from open_garden_planner.services.pdf_report_service import (  # noqa: PLC0415
            PdfReportOptions,
            PdfReportService,
        )

        # Keep cover=True on both so generate() actually emits a PDF; the
        # delta between the two is precisely the Garden Notes page.
        opts_with = PdfReportOptions(
            include_cover=True,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_garden_notes=True,
            garden_journal_notes={
                "n1": JournalNote(
                    date="2026-05-13", text="x", scene_x=0.0, scene_y=0.0
                ).to_dict(),
            },
            include_legend=False,
            project_name="Test",
            author="Tester",
        )
        opts_without = PdfReportOptions(
            include_cover=True,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_garden_notes=False,
            include_legend=False,
            project_name="Test",
            author="Tester",
        )
        path_with = tmp_path / "with.pdf"
        path_without = tmp_path / "without.pdf"
        PdfReportService.generate(scene, opts_with, path_with)
        PdfReportService.generate(scene, opts_without, path_without)
        assert path_with.exists()
        assert path_without.exists()
        assert path_with.stat().st_size > path_without.stat().st_size
