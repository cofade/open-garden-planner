"""Unit tests for the ManualTask data model (US-C2)."""
from __future__ import annotations

from open_garden_planner.models.task import ManualTask


class TestManualTaskRoundTrip:
    """Serialisation round-trips and forgiving deserialisation."""

    def test_full_round_trip(self) -> None:
        task = ManualTask(
            id="abc-123",
            date="2026-04-25",
            title="Mulch the asparagus",
            notes="Use straw, 5 cm deep",
            bed_id="bed-7",
        )
        restored = ManualTask.from_dict(task.to_dict())
        assert restored == task

    def test_omits_empty_optionals(self) -> None:
        task = ManualTask(id="x", date="2026-01-01", title="Water seedlings")
        d = task.to_dict()
        assert "notes" not in d
        assert "bed_id" not in d
        # Required/always-present keys remain.
        assert d == {"id": "x", "date": "2026-01-01", "title": "Water seedlings"}

    def test_empty_optionals_round_trip_to_defaults(self) -> None:
        task = ManualTask(id="x", date="2026-01-01", title="Water seedlings")
        restored = ManualTask.from_dict(task.to_dict())
        assert restored.notes == ""
        assert restored.bed_id is None

    def test_bed_id_empty_string_is_preserved(self) -> None:
        # bed_id is omitted only when None — an explicit "" is a real value.
        task = ManualTask(id="x", title="t", bed_id="")
        d = task.to_dict()
        assert d["bed_id"] == ""

    def test_from_dict_is_forgiving(self) -> None:
        # Missing everything but still produces a valid task with a fresh id.
        task = ManualTask.from_dict({})
        assert task.title == ""
        assert task.date == ""
        assert task.notes == ""
        assert task.bed_id is None
        assert task.id  # auto-generated, non-empty


class TestManualTaskDefaults:
    """The auto-generated id default."""

    def test_uuid_default_is_unique(self) -> None:
        a = ManualTask()
        b = ManualTask()
        assert a.id != b.id
        assert len(a.id) > 0
