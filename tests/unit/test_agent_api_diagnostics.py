"""Unit tests for the Agent API diagnostics mapping (Qt-free logic).

Turns harvested warning-flag records into ``Diagnostic`` entries; verifies that
positive indicators (spacing 'ideal', rotation 'good') are NOT reported and that
the ``kind`` filter works.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from open_garden_planner.agent_api import diagnostics as diagnostics_module
from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.agent_api.schema import Diagnostic


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
        "outside_canvas": False,
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

    def test_outside_canvas_maps_to_its_kind(self) -> None:
        """issue #380: an object fully off-plan is a warning kind."""
        out = diagnostics_from_records([_record("a", name="Bed", outside_canvas=True)])
        assert len(out) == 1
        assert out[0].kind == "outside_canvas"
        assert out[0].severity == "warning"
        assert "outside the plan canvas" in out[0].message

    def test_outside_canvas_false_is_silent(self) -> None:
        assert diagnostics_from_records([_record("a", outside_canvas=False)]) == []

    def test_outside_canvas_kind_filter(self) -> None:
        records = [
            _record("a", outside_canvas=True),
            _record("b", antagonist_warning=True),
        ]
        out = diagnostics_from_records(records, kind="outside_canvas")
        assert [d.item_ids[0] for d in out] == ["a"]

    def test_empty(self) -> None:
        assert diagnostics_from_records([]) == []


class TestDocumentedKinds:
    """Every kind the producer can emit is discoverable by an agent (#380 review).

    ``outside_canvas`` was added to the producer but not to the two places an
    agent reads the legal ``kind`` values, so a caller filtering by the
    documented list could never ask for it.
    """

    @staticmethod
    def _emitted_kinds() -> set[str]:
        source = Path(diagnostics_module.__file__).read_text(encoding="utf-8")
        return set(re.findall(r'kind="([a-z_]+)"', source))

    def test_emitted_kinds_are_found(self) -> None:
        assert "outside_canvas" in self._emitted_kinds()

    def test_schema_field_lists_every_emitted_kind(self) -> None:
        description = Diagnostic.model_fields["kind"].description or ""
        missing = {k for k in self._emitted_kinds() if f"'{k}'" not in description}
        assert not missing, f"Diagnostic.kind description omits {sorted(missing)}"

    def test_tool_docstring_lists_every_emitted_kind(self) -> None:
        server_src = (
            Path(diagnostics_module.__file__).with_name("server.py").read_text(encoding="utf-8")
        )
        start = server_src.index("async def get_diagnostics")
        doc = server_src[start : server_src.index('"""', server_src.index('"""', start) + 3)]
        missing = {k for k in self._emitted_kinds() if f"'{k}'" not in doc}
        assert not missing, f"get_diagnostics docstring omits {sorted(missing)}"
