"""Unit tests for the Agent API diagnostics mapping (Qt-free logic).

Turns harvested warning-flag records into ``Diagnostic`` entries; verifies that
positive indicators (spacing 'ideal', rotation 'good') are NOT reported and that
the ``kind`` filter works.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.diagnostics import diagnostics_from_records


def _record(item_id: str, **flags: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": item_id,
        "name": None,
        "object_type": None,
        "antagonist_warning": False,
        "spacing_overlap": None,
        "capacity_overrun": False,
        "soil_mismatch_level": None,
        "rotation_status": None,
    }
    base.update(flags)
    return base


class TestDiagnosticsMapping:
    def test_each_flag_maps_to_its_kind(self) -> None:
        records = [
            _record("a", name="Apple", antagonist_warning=True),
            _record("b", name="Mint", spacing_overlap="overlap"),
            _record("c", name="Pot", capacity_overrun=True),
            _record("d", name="Kale", soil_mismatch_level="critical"),
            _record("e", name="Bean", rotation_status="violation"),
        ]
        out = diagnostics_from_records(records)
        by_id = {d.item_ids[0]: d for d in out}
        assert by_id["a"].kind == "companion_conflict"
        assert by_id["b"].kind == "spacing_overlap"
        assert by_id["c"].kind == "capacity_overrun"
        assert by_id["d"].kind == "soil_mismatch"
        assert by_id["d"].severity == "critical"
        assert by_id["e"].kind == "crop_rotation"
        assert by_id["e"].severity == "critical"

    def test_one_record_can_yield_multiple_diagnostics(self) -> None:
        out = diagnostics_from_records(
            [_record("a", antagonist_warning=True, spacing_overlap="overlap")]
        )
        assert {d.kind for d in out} == {"companion_conflict", "spacing_overlap"}

    def test_positive_indicators_are_not_reported(self) -> None:
        # spacing 'ideal' and rotation 'good' are good-state markers, not warnings.
        out = diagnostics_from_records(
            [_record("a", spacing_overlap="ideal", rotation_status="good")]
        )
        assert out == []

    def test_suboptimal_rotation_is_a_warning(self) -> None:
        out = diagnostics_from_records([_record("a", rotation_status="suboptimal")])
        assert len(out) == 1
        assert out[0].severity == "warning"

    def test_message_uses_best_available_label(self) -> None:
        named = diagnostics_from_records([_record("a", name="Apple", antagonist_warning=True)])
        assert named[0].message.startswith("Apple")
        unnamed = diagnostics_from_records(
            [_record("a", object_type="TREE", antagonist_warning=True)]
        )
        assert unnamed[0].message.startswith("TREE")

    def test_kind_filter(self) -> None:
        records = [
            _record("a", antagonist_warning=True),
            _record("b", soil_mismatch_level="warning"),
        ]
        out = diagnostics_from_records(records, kind="soil_mismatch")
        assert [d.item_ids[0] for d in out] == ["b"]

    def test_empty(self) -> None:
        assert diagnostics_from_records([]) == []
