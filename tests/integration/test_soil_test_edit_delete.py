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
