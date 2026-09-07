"""Unit tests for the Agent API snapshot->schema mapping (Qt-free logic).

Also guards the inlined object-type name sets against drift from the real
``ObjectType`` definitions (the mapping inlines them to stay Qt-free).
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.mapping import (
    _BED_TYPE_NAMES,
    _PLANT_TYPE_NAMES,
    layers_from_snapshot,
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


class TestLayersMapping:
    """US-D2.4: the curated Layer list built from the raw snapshot records."""

    def _three_layer_snapshot(self) -> dict[str, Any]:
        return {
            "canvas": {"width": 4000.0, "height": 2500.0},
            "layers": [
                {
                    "id": "aaaa0000-0000-0000-0000-000000000001",
                    "name": "Top",
                    "visible": True,
                    "locked": False,
                    "opacity": 1.0,
                    "z_order": 2,
                },
                {
                    "id": "aaaa0000-0000-0000-0000-000000000002",
                    "name": "Hidden",
                    "visible": False,
                    "locked": True,
                    "opacity": 0.5,
                    "z_order": 1,
                },
                {
                    "id": "aaaa0000-0000-0000-0000-000000000003",
                    "name": "Base",
                    "visible": True,
                    "locked": False,
                    "opacity": 1.0,
                    "z_order": 0,
                },
            ],
            "objects": [
                {"item_id": "o1", "layer_id": "aaaa0000-0000-0000-0000-000000000001"},
                {"item_id": "o2", "layer_id": "aaaa0000-0000-0000-0000-000000000001"},
                {"item_id": "o3", "layer_id": "aaaa0000-0000-0000-0000-000000000003"},
                {"item_id": "o4"},  # no layer
            ],
            "agent_meta": {
                "file_name": None,
                "is_dirty": False,
                "active_layer_id": "aaaa0000-0000-0000-0000-000000000003",
            },
        }

    def test_ids_visibility_lock_z_order_and_active_flag(self) -> None:
        layers = layers_from_snapshot(self._three_layer_snapshot())
        assert [lyr.name for lyr in layers] == ["Top", "Hidden", "Base"]
        top, hidden, base = layers
        assert top.layer_id == "aaaa0000-0000-0000-0000-000000000001"
        assert (top.visible, top.locked, top.z_order, top.is_active) == (
            True,
            False,
            2,
            False,
        )
        assert (hidden.visible, hidden.locked, hidden.opacity) == (False, True, 0.5)
        assert (base.is_active, base.z_order) == (True, 0)

    def test_object_counts_are_per_layer_and_ignore_unlayered(self) -> None:
        layers = layers_from_snapshot(self._three_layer_snapshot())
        assert [lyr.object_count for lyr in layers] == [2, 0, 1]

    def test_no_active_layer_meta_leaves_all_inactive(self) -> None:
        snapshot = self._three_layer_snapshot()
        snapshot["agent_meta"]["active_layer_id"] = None
        assert all(not lyr.is_active for lyr in layers_from_snapshot(snapshot))

    def test_missing_layer_keys_are_tolerated(self) -> None:
        # A raw record missing optional keys must not raise (Layer.to_dict
        # defaults mirrored).
        layers = layers_from_snapshot({"layers": [{}], "objects": []})
        assert layers[0].name == ""
        assert layers[0].visible is True
        assert layers[0].locked is False
        assert layers[0].opacity == 1.0
        assert layers[0].z_order == 0
        assert layers[0].is_active is False
        assert layers[0].object_count == 0

    def test_plan_summary_carries_layers_and_keeps_layer_names(self) -> None:
        summary = plan_summary_from_snapshot(self._three_layer_snapshot())
        # Back-compat: layer_names stays, 'layers' is the richer additive field.
        assert summary.layer_names == ["Top", "Hidden", "Base"]
        assert [lyr.name for lyr in summary.layers] == ["Top", "Hidden", "Base"]
        assert summary.layers[2].is_active is True
        assert summary.layers[0].object_count == 2
