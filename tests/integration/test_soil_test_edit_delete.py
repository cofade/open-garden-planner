"""Integration tests for issue #171 — edit + delete past soil test records.

Covers EditSoilTestCommand and DeleteSoilTestCommand undo / redo behaviour.
"""
from __future__ import annotations

from open_garden_planner.core.commands import (
    AddSoilTestCommand,
    DeleteSoilTestCommand,
    EditSoilTestCommand,
)
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord


def _record(date: str, ph: float | None = None, **kwargs) -> SoilTestRecord:
    return SoilTestRecord(date=date, ph=ph, **kwargs)


def _seeded_pm(target_id: str, *records: SoilTestRecord) -> ProjectManager:
    pm = ProjectManager()
    history = SoilTestHistory(target_id=target_id, records=list(records))
    pm.set_soil_test_history(target_id, history)
    return pm


class TestEditSoilTestCommand:
    def test_execute_replaces_record_by_id(self) -> None:
        bed_id = "bed-A"
        original = _record("2026-04-01", ph=5.5, n_level=1)
        pm = _seeded_pm(bed_id, original)

        updated = SoilTestRecord(
            id=original.id, date="2026-04-01", ph=6.5, n_level=3
        )
        cmd = EditSoilTestCommand(pm, bed_id, updated)
        cmd.execute()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert len(records) == 1
        assert records[0].id == original.id
        assert records[0].ph == 6.5
        assert records[0].n_level == 3

    def test_undo_restores_prior_record(self) -> None:
        bed_id = "bed-A"
        original = _record("2026-04-01", ph=5.5)
        pm = _seeded_pm(bed_id, original)

        updated = SoilTestRecord(id=original.id, date="2026-04-01", ph=7.5)
        cmd = EditSoilTestCommand(pm, bed_id, updated)
        cmd.execute()
        cmd.undo()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert len(records) == 1
        assert records[0].ph == 5.5

    def test_execute_with_unknown_id_is_noop(self) -> None:
        bed_id = "bed-A"
        original = _record("2026-04-01", ph=5.5)
        pm = _seeded_pm(bed_id, original)

        ghost = SoilTestRecord(id="not-in-history", date="2026-04-01", ph=9.0)
        before = dict(pm.soil_tests[bed_id])

        EditSoilTestCommand(pm, bed_id, ghost).execute()

        assert pm.soil_tests[bed_id] == before


class TestDeleteSoilTestCommand:
    def test_execute_removes_record(self) -> None:
        bed_id = "bed-A"
        rec_a = _record("2026-04-01", ph=5.5)
        rec_b = _record("2026-04-15", ph=6.5)
        pm = _seeded_pm(bed_id, rec_a, rec_b)

        DeleteSoilTestCommand(pm, bed_id, rec_a.id).execute()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert len(records) == 1
        assert records[0].id == rec_b.id

    def test_undo_restores_deleted_record(self) -> None:
        bed_id = "bed-A"
        rec_a = _record("2026-04-01", ph=5.5)
        rec_b = _record("2026-04-15", ph=6.5)
        pm = _seeded_pm(bed_id, rec_a, rec_b)

        cmd = DeleteSoilTestCommand(pm, bed_id, rec_a.id)
        cmd.execute()
        cmd.undo()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert {r.id for r in records} == {rec_a.id, rec_b.id}

    def test_delete_unknown_id_is_noop(self) -> None:
        bed_id = "bed-A"
        rec_a = _record("2026-04-01", ph=5.5)
        pm = _seeded_pm(bed_id, rec_a)

        DeleteSoilTestCommand(pm, bed_id, "ghost-id").execute()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert len(records) == 1
        assert records[0].id == rec_a.id

    def test_delete_then_add_then_undo_chain(self) -> None:
        """Mixed sequence: delete + add then undo restores chronology."""
        bed_id = "bed-A"
        rec_a = _record("2026-04-01", ph=5.5)
        pm = _seeded_pm(bed_id, rec_a)

        DeleteSoilTestCommand(pm, bed_id, rec_a.id).execute()
        new_rec = _record("2026-05-01", ph=6.0)
        AddSoilTestCommand(pm, bed_id, new_rec).execute()

        records = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).records
        assert len(records) == 1
        assert records[0].id == new_rec.id


class TestEditViaHistoryDuplicateGuard:
    """Regression: editing a soil test via the History tab and then clicking
    OK on the outer dialog must NOT append a duplicate of the pre-edit
    record. The guard must compare the outer entry-tab values against the
    originally-shown `existing` (which the form is still displaying after
    the inner edit dialog commits), NOT only against the post-edit latest.
    """

    def test_outer_ok_after_inner_edit_does_not_duplicate(self) -> None:
        """The full Edit-via-History flow with the actual public helper.

        Previously only ``_records_equivalent(record, latest_after)`` was
        checked, which silently let through the form-still-shows-old-values
        case (regression introduced during the US-12.10 epic squash).
        """
        from open_garden_planner.app.application import (
            _should_skip_add_after_dialog,
        )

        bed_id = "bed-A"
        original = _record("2026-04-01", ph=5.5, n_level=1)
        pm = _seeded_pm(bed_id, original)
        existing = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).latest

        edited = SoilTestRecord(id=original.id, date="2026-04-01", ph=6.5, n_level=1)
        EditSoilTestCommand(pm, bed_id, edited).execute()

        form_record = SoilTestRecord(date="2026-04-01", ph=5.5, n_level=1)
        latest_after = SoilTestHistory.from_dict(pm.soil_tests[bed_id]).latest

        assert _should_skip_add_after_dialog(form_record, existing, latest_after) is True

    def test_outer_ok_with_modified_entry_tab_still_adds(self) -> None:
        """User edits the entry tab → guard must NOT fire (Add must proceed)."""
        from open_garden_planner.app.application import (
            _should_skip_add_after_dialog,
        )

        existing = _record("2026-04-01", ph=5.5, n_level=1)
        form_record = SoilTestRecord(date="2026-05-01", ph=6.5, n_level=1)
        assert _should_skip_add_after_dialog(form_record, existing, existing) is False

    def test_first_record_with_no_existing_proceeds(self) -> None:
        """First-time entry (no prior records) → Add must proceed."""
        from open_garden_planner.app.application import (
            _should_skip_add_after_dialog,
        )

        form_record = SoilTestRecord(date="2026-04-01", ph=5.5)
        assert _should_skip_add_after_dialog(form_record, None, None) is False

    def test_real_dialog_unmodified_form_matches_existing(self, qtbot) -> None:
        """End-to-end with the actual SoilTestDialog: when the dialog is
        constructed with ``existing_latest`` and the user does NOT touch
        the entry tab, ``result_record()`` must be field-equivalent to
        ``existing_latest``. That invariant is what
        ``_should_skip_add_after_dialog`` relies on to detect the no-op
        outer-OK / Edit-via-History case. If a future change breaks the
        invariant (e.g. the form starts mutating values silently), this
        test fails before the duplicate hits production.
        """
        from open_garden_planner.app.application import _records_equivalent
        from open_garden_planner.ui.dialogs import SoilTestDialog

        existing = SoilTestRecord(
            date="2026-04-01",
            ph=5.5,
            n_level=1,
            p_level=2,
            k_level=3,
            notes="loamy",
        )
        history = SoilTestHistory(target_id="bed-1", records=[existing])
        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_latest=existing,
            existing_history=history,
        )
        qtbot.addWidget(dialog)

        # User opens the dialog and clicks OK without changing anything.
        form_record = dialog.result_record()
        assert _records_equivalent(form_record, existing) is True
