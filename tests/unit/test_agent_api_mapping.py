"""Unit tests for the Agent API snapshot->schema mapping (Qt-free logic).

Also guards the inlined object-type name sets against drift from the real
``ObjectType`` definitions (the mapping inlines them to stay Qt-free).
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.mapping import (
    _BED_TYPE_NAMES,
    _PLANT_TYPE_NAMES,
    plan_summary_from_snapshot,
)


def _snapshot(objects: list[dict[str, Any]], **meta: Any) -> dict[str, Any]:
    base_meta: dict[str, Any] = {"file_name": "demo.ogp", "is_dirty": True}
    base_meta.update(meta)
    return {
        "canvas": {"width": 4000.0, "height": 2500.0},
        "layers": [{"name": "Base"}, {"name": "Plants"}],
        "objects": objects,
        "agent_meta": base_meta,
    }


class TestPlanSummaryMapping:
    def test_counts_beds_plants_shapes(self) -> None:
        objects = [
            {"object_type": "GARDEN_BED"},
            {"object_type": "RAISED_BED"},
            {"object_type": "TREE"},
            {"object_type": "TREE"},
            {"object_type": "GENERIC_RECTANGLE"},
            {"object_type": "HOUSE"},
        ]
        summary = plan_summary_from_snapshot(_snapshot(objects))
        assert summary.bed_count == 2
        assert summary.plant_count == 2
        assert summary.shape_count == 2
        assert summary.canvas_width_cm == 4000.0
        assert summary.canvas_height_cm == 2500.0
        assert summary.layer_names == ["Base", "Plants"]
        assert summary.file_name == "demo.ogp"
        assert summary.is_dirty is True

    def test_object_without_object_type_counts_as_shape(self) -> None:
        summary = plan_summary_from_snapshot(_snapshot([{"type": "polyline"}]))
        assert (summary.bed_count, summary.plant_count, summary.shape_count) == (0, 0, 1)

    def test_empty_plan(self) -> None:
        summary = plan_summary_from_snapshot(
            {
                "canvas": {"width": 100.0, "height": 50.0},
                "layers": [],
                "objects": [],
                "agent_meta": {"file_name": None, "is_dirty": False},
            }
        )
        assert (summary.bed_count, summary.plant_count, summary.shape_count) == (0, 0, 0)
        assert summary.layer_names == []
        assert summary.file_name is None
        assert summary.is_dirty is False

    def test_missing_keys_are_tolerated(self) -> None:
        # A minimal/empty snapshot must not raise.
        summary = plan_summary_from_snapshot({})
        assert summary.bed_count == 0
        assert summary.canvas_width_cm == 0.0
        assert summary.is_dirty is False


class TestNameSetDriftGuard:
    """The mapping inlines the type-name sets; assert they still match source."""

    def test_bed_names_match_soil_container_types(self) -> None:
        from open_garden_planner.core.object_types import SOIL_CONTAINER_TYPES

        assert {t.name for t in SOIL_CONTAINER_TYPES} == _BED_TYPE_NAMES

    def test_plant_names_match_is_plant_type(self) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        assert {t.name for t in ObjectType if is_plant_type(t)} == _PLANT_TYPE_NAMES
