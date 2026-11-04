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
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core import (
    AddJournalNoteCommand,
    CommandManager,
    DeleteJournalNoteCommand,
    EditJournalNoteCommand,
    ProjectManager,
)
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.journal_panel import JournalPanel


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:
    return ProjectManager()


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:
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
        self, project_manager: ProjectManager, scene: CanvasScene, qtbot: object
    ) -> None:
        """Selecting a pin and pressing Delete used to call DeleteItemsCommand
        directly, removing the pin from the scene but orphaning the note dict
        in ProjectData. The fix routes journal pins through
        DeleteJournalNoteCommand via journal_notes_batch_delete_requested.
        """
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

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

    def test_delete_key_prunes_notes_for_pins_inside_a_group(
        self, project_manager: ProjectManager, scene: CanvasScene, qtbot: object
    ) -> None:
        """A group hides its pins from the top-level selection.

        Deleting the group removed the pins but kept their note records; the
        batch delete now walks the tree, and undo restores the group with the
        pin still inside it (P2 of the #674 review).
        """
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.canvas_view import CanvasView
        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        note = JournalNote(date="2026-05-13", text="x", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        other = RectangleItem(100, 100, 50, 50, layer_id=scene.active_layer.id)
        scene.addItem(other)
        CommandManager().execute(
            AddJournalNoteCommand(project_manager, scene, pin, note)
        )
        GroupCommand(scene, [pin, other]).execute()
        group = pin.parentItem()
        assert group is not None

        view = CanvasView(scene=scene)

        def journal_commands(note_ids: list[str]) -> list[DeleteJournalNoteCommand]:
            # The application's factory, reduced to its command construction.
            pins = {
                item.note_id: item
                for item in scene.items()
                if isinstance(item, JournalPinItem)
            }
            return [
                DeleteJournalNoteCommand(
                    project_manager,
                    scene,
                    pins[note_id],
                    remove_pin=pins[note_id].parentItem() is None,
                )
                for note_id in note_ids
                if note_id in pins
            ]

        view.journal_note_command_factory = journal_commands
        group.setSelected(True)
        view._delete_selected_items()

        assert note.id not in project_manager.garden_journal_notes
        assert group.scene() is None

        # ONE compound step: the note and the group's pin undo together.
        view.command_manager.undo()
        assert group.scene() is scene
        assert pin.parentItem() is group, "undo lost the pin's group membership"
        assert note.id in project_manager.garden_journal_notes

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

    def test_save_stores_a_grouped_pins_scene_position(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        """A grouped pin's ``pos()`` is group-local, not scene coordinates.

        Pins are groupable since #674; saving ``pos()`` would write a note
        position missing the group's transform (round-6 review P2).
        """
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        note = JournalNote(date="2026-05-13", text="hi", scene_x=0.0, scene_y=0.0)
        pin = JournalPinItem(x=0.0, y=0.0, note_id=note.id)
        other = RectangleItem(100, 100, 50, 50, layer_id=scene.active_layer.id)
        scene.addItem(other)
        CommandManager().execute(
            AddJournalNoteCommand(project_manager, scene, pin, note)
        )
        GroupCommand(scene, [pin, other]).execute()
        group = pin.parentItem()
        assert group is not None
        group.setPos(300.0, 200.0)

        path = tmp_path / "grouped-pin.ogp"
        project_manager.save(scene, path)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, path)
        reloaded = pm2.get_journal_note(note.id)
        assert reloaded is not None
        assert reloaded.scene_x == pytest.approx(300.0)
        assert reloaded.scene_y == pytest.approx(200.0)

    def test_pdf_garden_notes_paginates_long_content(
        self,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        """A garden with many long notes used to silently truncate at the
        first page boundary. The fix calls writer.newPage() automatically.
        """
        from open_garden_planner.services.pdf_report_service import (
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
        self, qtbot: object, project_manager: ProjectManager
    ) -> None:
        """Regression: opening the dialog for a fresh JournalNote with date=""
        used to leave the QDateEdit at Qt's default 2000-01-01."""
        from datetime import date as _date

        from open_garden_planner.ui.dialogs.journal_note_dialog import (
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
        self, qtbot: object, project_manager: ProjectManager
    ) -> None:
        from open_garden_planner.ui.dialogs.journal_note_dialog import (
            JournalNoteDialog,
        )

        note = JournalNote(date="2024-03-15", text="anchored", scene_x=0.0, scene_y=0.0)
        dialog = JournalNoteDialog(
            parent=None, note=note, project_manager=project_manager, edit_mode=True
        )
        qd = dialog._date_edit.date()
        assert (qd.year(), qd.month(), qd.day()) == (2024, 3, 15)


class TestJournalPanel:
    def test_panel_filters_by_text_query(self, qtbot: object) -> None:
        panel = JournalPanel()
        panel.refresh({
            "a": JournalNote(date="2026-05-01", text="planted lettuce").to_dict(),
            "b": JournalNote(date="2026-05-02", text="harvested radish").to_dict(),
            "c": JournalNote(date="2026-05-03", text="checked lettuce").to_dict(),
        })

        panel._search_edit.setText("lettuce")
        # textChanged auto-rebuilds the list. Real notes carry a UserRole id;
        # the placeholder row sets no data, so filtering by truthy data is enough.
        from PyQt6.QtCore import Qt as _Qt

        ids = [
            panel._list.item(i).data(_Qt.ItemDataRole.UserRole)
            for i in range(panel._list.count())
        ]
        ids = [i for i in ids if i]
        assert set(ids) == {"a", "c"}

    def test_panel_filters_by_date_range(self, qtbot: object) -> None:
        from PyQt6.QtCore import QDate

        panel = JournalPanel()
        panel.refresh({
            "a": JournalNote(date="2026-04-30", text="early").to_dict(),
            "b": JournalNote(date="2026-05-15", text="mid").to_dict(),
            "c": JournalNote(date="2026-06-10", text="late").to_dict(),
        })

        panel._range_check.setChecked(True)
        panel._date_from.setDate(QDate(2026, 5, 1))
        panel._date_to.setDate(QDate(2026, 5, 31))

        from PyQt6.QtCore import Qt as _Qt

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
        from open_garden_planner.services.pdf_report_service import (
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
        from open_garden_planner.services.pdf_report_service import (
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

class TestPinPointerInteraction:
    """A pin is selected, dragged and opened by its visible head (PF-CAN-40).

    A pin carries ``ItemIgnoresTransformations``, which ``QGraphicsScene.itemAt``
    never hits, so the canvas owns a small pin hit test. These tests drive real
    viewport events rather than calling that helper.
    """

    @staticmethod
    def _canvas(qtbot) -> tuple[CanvasScene, CanvasView]:
        scene = CanvasScene(width_cm=2000, height_cm=1500)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.resize(1000, 800)
        view.show()
        qtbot.waitExposed(view)
        return scene, view

    @staticmethod
    def _head(view: CanvasView, pin: JournalPinItem) -> QPoint:
        return view.mapFromScene(pin.mapToScene(QPointF(0.0, -10.0)))

    def test_click_selects_the_pin_and_ctrl_click_adds_a_shape(self, qtbot) -> None:
        scene, view = self._canvas(qtbot)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        rect = RectangleItem(500, 400, 200, 100, layer_id=scene.active_layer.id)
        scene.addItem(pin)
        scene.addItem(rect)
        view.centerOn(350, 350)

        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._head(view, pin),
        )
        assert scene.selectedItems() == [pin]

        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            view.mapFromScene(rect.mapToScene(rect.rect().center())),
        )
        assert set(scene.selectedItems()) == {pin, rect}

        view.group_selected()
        assert pin.parentItem() is not None
        assert rect.parentItem() is pin.parentItem()

    def test_drag_moves_the_pin_and_undo_restores_it(self, qtbot) -> None:
        scene, view = self._canvas(qtbot)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        scene.addItem(pin)
        view.centerOn(pin.pos())
        start = self._head(view, pin)
        target = start + QPoint(60, 30)
        undo_depth = len(view.command_manager._undo_stack)

        QTest.mousePress(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start,
        )
        QTest.mouseMove(view.viewport(), target)
        QTest.mouseRelease(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            target,
        )

        assert pin.isSelected()
        assert pin.pos() != QPointF(200, 200)
        assert len(view.command_manager._undo_stack) == undo_depth + 1
        view.command_manager.undo()
        assert pin.pos() == QPointF(200, 200)

    def test_double_click_opens_the_note(self, qtbot) -> None:
        scene, view = self._canvas(qtbot)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        scene.addItem(pin)
        view.centerOn(pin.pos())
        seen: list[str] = []
        view.journal_note_edit_requested.connect(seen.append)

        QTest.mouseDClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._head(view, pin),
        )
        assert seen == ["note-1"]

    def test_a_lost_release_is_committed_on_the_next_move(self, qtbot) -> None:
        """A release outside the viewport must not lose the pin's undo step."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QMouseEvent

        scene, view = self._canvas(qtbot)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        scene.addItem(pin)
        view.centerOn(pin.pos())
        start = self._head(view, pin)
        target = start + QPoint(60, 30)
        undo_depth = len(view.command_manager._undo_stack)

        QTest.mousePress(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start,
        )
        QTest.mouseMove(view.viewport(), target)
        local = QPointF(target)
        lost_release = QMouseEvent(
            QEvent.Type.MouseMove,
            local,
            local,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(lost_release)

        assert pin.pos() != QPointF(200, 200)
        assert len(view.command_manager._undo_stack) == undo_depth + 1
        view.command_manager.undo()
        assert pin.pos() == QPointF(200, 200)

    def test_a_pin_drag_after_a_resize_is_its_own_undo_step(self, qtbot) -> None:
        """A resize already on the stack must not swallow the next pin drag."""
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_rect_resize,
        )

        scene, view = self._canvas(qtbot)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        rect = RectangleItem(600, 400, 100, 80, layer_id=scene.active_layer.id)
        scene.addItem(pin)
        scene.addItem(rect)
        view.centerOn(pin.pos())
        old, new = build_rect_resize(rect, 150, 100)
        view.command_manager.execute(
            ResizeItemCommand(rect, old, new, apply_rect_like_geometry)
        )
        resized_depth = len(view.command_manager._undo_stack)

        start = self._head(view, pin)
        QTest.mousePress(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start,
        )
        QTest.mouseMove(view.viewport(), start + QPoint(60, 30))
        QTest.mouseRelease(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start + QPoint(60, 30),
        )

        assert len(view.command_manager._undo_stack) == resized_depth + 1
        view.command_manager.undo()
        assert pin.pos() == QPointF(200, 200)

    def test_selection_survives_a_minimap_refresh(self, qtbot) -> None:
        """The minimap suppresses overlays' paint, not their visibility.

        ``setVisible(False)`` deselects an item; the minimap refreshes while
        the scene changes, so a selected pin lost its selection mid-drag
        (manual test 4 of PR #713).
        """
        from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget

        scene, view = self._canvas(qtbot)
        minimap = MinimapWidget(view, scene)
        qtbot.addWidget(minimap)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        scene.addItem(pin)
        view.centerOn(pin.pos())

        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._head(view, pin),
        )
        assert pin.isSelected()

        minimap._do_update()
        assert pin.isSelected(), "a thumbnail refresh deselected the pin"
        assert pin.isVisible()

    def test_a_group_with_a_pin_survives_a_minimap_refresh(self, qtbot) -> None:
        """A grouped pin is a child; suppressing its paint keeps the group selected."""
        from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget

        scene, view = self._canvas(qtbot)
        minimap = MinimapWidget(view, scene)
        qtbot.addWidget(minimap)
        pin = JournalPinItem(200, 200, "note-1", layer_id=scene.active_layer.id)
        rect = RectangleItem(400, 150, 200, 100, layer_id=scene.active_layer.id)
        scene.addItem(pin)
        scene.addItem(rect)
        view.centerOn(300, 200)
        pin.setSelected(True)
        rect.setSelected(True)
        view.group_selected()
        group = pin.parentItem()
        assert group is not None
        scene.clearSelection()
        group.setSelected(True)

        minimap._do_update()
        assert group.isSelected(), "a thumbnail refresh deselected the group"
        assert pin.isSelected(), "the grouped pin lost the selection Qt propagates"
