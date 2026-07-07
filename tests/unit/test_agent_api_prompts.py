"""Unit tests for the Agent API read-analysis prompt text builders (US-D1.5).

Pure PlanSummary/Diagnostic/ObjectRef fixtures -> assert the composed prompt
text is sane and non-empty. No Qt, no mcp, no live server (same spirit as
test_agent_api_mapping.py / test_agent_api_diagnostics.py).
"""

from __future__ import annotations

from open_garden_planner.agent_api.prompts import (
    render_audit_plan_prompt,
    render_describe_garden_prompt,
)
from open_garden_planner.agent_api.schema import Diagnostic, ObjectRef, PlanSummary


def _summary(**overrides: object) -> PlanSummary:
    base: dict[str, object] = {
        "file_name": "demo.ogp",
        "is_dirty": False,
        "canvas_width_cm": 4000.0,
        "canvas_height_cm": 2500.0,
        "bed_count": 1,
        "plant_count": 2,
        "shape_count": 0,
        "layer_names": ["Base", "Plants"],
    }
    base.update(overrides)
    return PlanSummary(**base)  # type: ignore[arg-type]


def _diagnostic(**overrides: object) -> Diagnostic:
    base: dict[str, object] = {
        "kind": "spacing_overlap",
        "severity": "warning",
        "item_ids": ["abc"],
        "message": "Mint is closer than its spacing radius to a neighbour.",
    }
    base.update(overrides)
    return Diagnostic(**base)  # type: ignore[arg-type]


def _object_ref(**overrides: object) -> ObjectRef:
    base: dict[str, object] = {
        "item_id": "abc",
        "type": "circle",
        "object_type": "TREE",
        "name": "Apple",
        "layer_name": "Plants",
        "center_x_cm": 50.0,
        "center_y_cm": 60.0,
        "width_cm": 30.0,
        "height_cm": 30.0,
    }
    base.update(overrides)
    return ObjectRef(**base)  # type: ignore[arg-type]


class TestAuditPlanPrompt:
    def test_includes_plan_summary_counts(self) -> None:
        text = render_audit_plan_prompt(_summary(), [])
        assert "Beds/containers: 1" in text
        assert "Plants: 2" in text
        assert "demo.ogp" in text

    def test_no_diagnostics_says_none(self) -> None:
        text = render_audit_plan_prompt(_summary(), [])
        assert "none" in text.lower()

    def test_lists_each_diagnostic(self) -> None:
        diags = [
            _diagnostic(kind="companion_conflict", message="Apple is too close to Fennel."),
            _diagnostic(kind="soil_mismatch", severity="critical", message="Kale soil is off."),
        ]
        text = render_audit_plan_prompt(_summary(), diags)
        assert "companion_conflict" in text
        assert "Apple is too close to Fennel." in text
        assert "soil_mismatch" in text
        assert "Kale soil is off." in text

    def test_unsaved_plan_flagged(self) -> None:
        text = render_audit_plan_prompt(_summary(file_name=None, is_dirty=True), [])
        assert "unsaved" in text.lower()

    def test_saved_plan_with_pending_edits_flagged(self) -> None:
        text = render_audit_plan_prompt(_summary(file_name="demo.ogp", is_dirty=True), [])
        assert "demo.ogp (unsaved changes)" in text


class TestDescribeGardenPrompt:
    def test_includes_plan_summary(self) -> None:
        text = render_describe_garden_prompt(_summary(), [])
        assert "demo.ogp" in text
        assert "4000" in text and "2500" in text

    def test_empty_plan_says_so(self) -> None:
        text = render_describe_garden_prompt(_summary(bed_count=0, plant_count=0), [])
        assert "empty" in text.lower()

    def test_lists_each_object(self) -> None:
        objs = [_object_ref(), _object_ref(item_id="def", name="Mint", type="rectangle")]
        text = render_describe_garden_prompt(_summary(), objs)
        assert "Apple" in text
        assert "Mint" in text
        assert "Plants" in text  # layer_name surfaced

    def test_caps_object_list_and_notes_remainder(self) -> None:
        objs = [
            _object_ref(item_id=str(i), name=f"Plant {i}") for i in range(55)
        ]
        text = render_describe_garden_prompt(_summary(), objs)
        assert "Plant 0" in text
        assert "Plant 49" in text
        assert "Plant 50" not in text
        assert "...and 5 more — use list_objects for the full list." in text
