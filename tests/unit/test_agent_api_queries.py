"""Unit tests for the Agent API read/query helpers (Qt-free logic).

Exercises list/get/spatial/measure over a hand-built ``.ogp``-shaped snapshot,
the curated-vs-raw return modes, and the per-geometry bounding-box normaliser.
"""

from __future__ import annotations

import math
from typing import Any

from open_garden_planner.agent_api import queries
from open_garden_planner.agent_api.schema import Measurement, ObjectDetail, ObjectRef


def _snapshot() -> dict[str, Any]:
    """A small plan: one raised bed holding two plants, plus two loose shapes."""
    return {
        "canvas": {"width": 1000.0, "height": 800.0},
        "layers": [
            {"id": "L1", "name": "Base"},
            {"id": "L2", "name": "Plants"},
        ],
        "agent_meta": {"file_name": "demo.ogp", "is_dirty": False},
        "objects": [
            {
                "type": "rectangle",
                "item_id": "bed1",
                "x": 0.0,
                "y": 0.0,
                "width": 200.0,
                "height": 100.0,
                "object_type": "RAISED_BED",
                "name": "Bed A",
                "layer_id": "L1",
                "child_item_ids": ["p1", "p2"],
                "fill_color": "#ff00ff00",
                "stroke_color": "#ff000000",
                "rotation_angle": 30.0,
            },
            {
                "type": "circle",
                "item_id": "p1",
                "center_x": 50.0,
                "center_y": 50.0,
                "radius": 15.0,
                "object_type": "TREE",
                "name": "Apple",
                "layer_id": "L2",
                "parent_bed_id": "bed1",
                "plant_species": "apple",
                "metadata": {"plant_species": {"common_name": "Apple"}},
            },
            {
                "type": "circle",
                "item_id": "p2",
                "center_x": 150.0,
                "center_y": 50.0,
                "radius": 10.0,
                "object_type": "PERENNIAL",
                "name": "Mint",
                "layer_id": "L2",
                "parent_bed_id": "bed1",
                "plant_species": "mint",
            },
            {
                "type": "polygon",
                "item_id": "path1",
                "points": [
                    {"x": 300.0, "y": 300.0},
                    {"x": 400.0, "y": 300.0},
                    {"x": 400.0, "y": 400.0},
                    {"x": 300.0, "y": 400.0},
                ],
                "name": "Path",
            },
            {
                "type": "ellipse",
                "item_id": "pond1",
                "center_x": 700.0,
                "center_y": 600.0,
                "semi_x": 50.0,
                "semi_y": 30.0,
                "object_type": "POND",
            },
        ],
    }


class TestListObjects:
    def test_lists_all_as_object_refs(self) -> None:
        out = queries.list_objects(_snapshot())
        assert len(out) == 5
        assert all(isinstance(o, ObjectRef) for o in out)
        ids = {o.item_id for o in out}
        assert ids == {"bed1", "p1", "p2", "path1", "pond1"}

    def test_filter_by_category(self) -> None:
        out = queries.list_objects(_snapshot(), type="plant")
        assert {o.item_id for o in out} == {"p1", "p2"}
        out = queries.list_objects(_snapshot(), type="bed")
        assert {o.item_id for o in out} == {"bed1"}
        out = queries.list_objects(_snapshot(), type="shape")
        assert {o.item_id for o in out} == {"path1", "pond1"}

    def test_filter_by_object_type_name(self) -> None:
        out = queries.list_objects(_snapshot(), type="TREE")
        assert [o.item_id for o in out] == ["p1"]

    def test_filter_by_geometry_kind(self) -> None:
        out = queries.list_objects(_snapshot(), type="circle")
        assert {o.item_id for o in out} == {"p1", "p2"}

    def test_filter_by_layer_name_and_id(self) -> None:
        by_name = queries.list_objects(_snapshot(), layer="Plants")
        by_id = queries.list_objects(_snapshot(), layer="L2")
        assert {o.item_id for o in by_name} == {"p1", "p2"}
        assert {o.item_id for o in by_id} == {"p1", "p2"}

    def test_filter_by_parent(self) -> None:
        out = queries.list_objects(_snapshot(), parent="bed1")
        assert {o.item_id for o in out} == {"p1", "p2"}

    def test_raw_returns_serialiser_dicts(self) -> None:
        out = queries.list_objects(_snapshot(), type="TREE", raw=True)
        assert isinstance(out[0], dict)
        # raw preserves keys the curated schema does not surface
        assert out[0]["radius"] == 15.0

    def test_object_ref_geometry(self) -> None:
        bed = next(o for o in queries.list_objects(_snapshot()) if o.item_id == "bed1")
        assert (bed.center_x_cm, bed.center_y_cm) == (100.0, 50.0)
        assert (bed.width_cm, bed.height_cm) == (200.0, 100.0)
        assert bed.layer_name == "Base"


class TestGetObject:
    def test_curated_detail(self) -> None:
        detail = queries.get_object(_snapshot(), "p1")
        assert isinstance(detail, ObjectDetail)
        assert detail.species_key == "apple"
        assert detail.species_name == "Apple"  # resolved from metadata dict
        assert detail.parent_bed_id == "bed1"
        assert math.isclose(detail.area_cm2, math.pi * 15.0 * 15.0)

    def test_bed_detail_exposes_children_and_rotation(self) -> None:
        detail = queries.get_object(_snapshot(), "bed1")
        assert isinstance(detail, ObjectDetail)
        assert detail.child_item_ids == ["p1", "p2"]
        assert detail.rotation_deg == 30.0
        assert detail.area_cm2 == 200.0 * 100.0

    def test_polygon_area_is_shoelace(self) -> None:
        detail = queries.get_object(_snapshot(), "path1")
        assert isinstance(detail, ObjectDetail)
        assert detail.area_cm2 == 100.0 * 100.0  # the square path

    def test_ellipse_area(self) -> None:
        detail = queries.get_object(_snapshot(), "pond1")
        assert isinstance(detail, ObjectDetail)
        assert math.isclose(detail.area_cm2, math.pi * 50.0 * 30.0)

    def test_raw_mode(self) -> None:
        raw = queries.get_object(_snapshot(), "p1", raw=True)
        assert isinstance(raw, dict)
        assert raw["center_x"] == 50.0

    def test_unknown_id_returns_none(self) -> None:
        assert queries.get_object(_snapshot(), "nope") is None


class TestSpatialQueries:
    def test_objects_in_region_bbox_intersect(self) -> None:
        # A 100x100 box at the origin catches the bed and the apple, not mint
        # (its bbox spans x 140..160) nor the far shapes.
        out = queries.objects_in_region(_snapshot(), 0.0, 0.0, 100.0, 100.0)
        assert {o.item_id for o in out} == {"bed1", "p1"}

    def test_objects_in(self) -> None:
        out = queries.objects_in(_snapshot(), "bed1")
        assert {o.item_id for o in out} == {"p1", "p2"}

    def test_empty_parent_matches_nothing(self) -> None:
        # An empty parent id must NOT match every unparented object.
        assert queries.list_objects(_snapshot(), parent="") == []
        assert queries.objects_in(_snapshot(), "") == []
        assert queries.plants_in_bed(_snapshot(), "") == []

    def test_plants_in_bed_excludes_non_plants(self) -> None:
        # Even if a non-plant were parented, plants_in_bed only returns plants.
        snap = _snapshot()
        snap["objects"].append(
            {"type": "rectangle", "item_id": "label1", "x": 10, "y": 10,
             "width": 5, "height": 5, "object_type": "TEXT", "parent_bed_id": "bed1"}
        )
        out = queries.plants_in_bed(snap, "bed1")
        assert {o.item_id for o in out} == {"p1", "p2"}

    def test_nearest_objects_ranking_and_k(self) -> None:
        out = queries.nearest_objects(_snapshot(), 0.0, 0.0, k=2)
        assert [o.item_id for o in out] == ["p1", "bed1"]

    def test_nearest_objects_type_filter(self) -> None:
        out = queries.nearest_objects(_snapshot(), 1000.0, 800.0, k=1, type="plant")
        assert [o.item_id for o in out] == ["p2"]

    def test_measure_distance(self) -> None:
        result = queries.measure_distance(_snapshot(), "p1", "p2")
        assert isinstance(result, Measurement)
        assert result.distance_cm == 100.0
        assert (result.dx_cm, result.dy_cm) == (100.0, 0.0)

    def test_measure_distance_unknown_id(self) -> None:
        assert queries.measure_distance(_snapshot(), "p1", "nope") is None

    def test_nearest_k_zero_or_negative_returns_none(self) -> None:
        assert queries.nearest_objects(_snapshot(), 0.0, 0.0, k=0) == []
        assert queries.nearest_objects(_snapshot(), 0.0, 0.0, k=-3) == []

    def test_empty_item_id_addresses_nothing(self) -> None:
        # callout/background serialise without an item_id; "" must not resolve.
        snap = _snapshot()
        snap["objects"].append({"type": "callout", "target_x": 10, "target_y": 20})
        assert queries.get_object(snap, "") is None
        assert queries.measure_distance(snap, "", "p1") is None


class TestBboxNormaliserPerShape:
    """Every serialised geometry kind must yield a sane (non-garbage) bbox.

    Dicts mirror the real per-type serialisers (project.py ``_serialize_item_core``
    and each item's ``to_dict``); ``test_agent_api_geometry.py`` round-trips real
    items to guard these keys against drift.
    """

    def test_construction_line_segment(self) -> None:
        # Regression: x1/y1/x2/y2 previously fell through to (0,0,0,0).
        line = {
            "type": "construction_line",
            "item_id": "cl",
            "x1": 500.0,
            "y1": 600.0,
            "x2": 700.0,
            "y2": 800.0,
        }
        assert queries.object_bbox(line) == (500.0, 600.0, 200.0, 200.0)
        assert queries.object_center(line) == (600.0, 700.0)

    def test_construction_circle(self) -> None:
        circ = {
            "type": "construction_circle",
            "item_id": "cc",
            "center_x": 100.0,
            "center_y": 50.0,
            "radius": 20.0,
        }
        assert queries.object_bbox(circ) == (80.0, 30.0, 40.0, 40.0)

    def test_arc_uses_radius(self) -> None:
        arc = {
            "type": "arc",
            "item_id": "a",
            "center_x": 10.0,
            "center_y": 10.0,
            "radius": 5.0,
            "start_deg": 0.0,
            "span_deg": 90.0,
        }
        assert queries.object_bbox(arc) == (5.0, 5.0, 10.0, 10.0)

    def test_polyline(self) -> None:
        poly = {
            "type": "polyline",
            "item_id": "pl",
            "points": [{"x": 0.0, "y": 0.0}, {"x": 30.0, "y": 10.0}, {"x": 10.0, "y": 40.0}],
        }
        assert queries.object_bbox(poly) == (0.0, 0.0, 30.0, 40.0)

    def test_callout_is_point(self) -> None:
        callout = {"type": "callout", "target_x": 12.0, "target_y": 34.0, "box_dx": 5, "box_dy": 5}
        assert queries.object_bbox(callout) == (12.0, 34.0, 0.0, 0.0)

    def test_journal_pin_is_point(self) -> None:
        pin = {"type": "journal_pin", "item_id": "jp", "x": 7.0, "y": 8.0, "note_id": "n"}
        assert queries.object_bbox(pin) == (7.0, 8.0, 0.0, 0.0)

    def test_background_image_position(self) -> None:
        bg = {"type": "background_image", "position": {"x": 100.0, "y": 200.0}, "scale_factor": 1.0}
        assert queries.object_bbox(bg) == (100.0, 200.0, 0.0, 0.0)

    def test_group_unions_child_boxes_in_group_frame(self) -> None:
        # Group/smart-symbol children serialise in the group's LOCAL frame; the
        # group dict has only x/y, so the bbox must union the offset child boxes
        # (not collapse to a zero-size point at the origin).
        group = {
            "type": "group",
            "item_id": "g1",
            "x": 100.0,
            "y": 100.0,
            "children": [
                {"type": "rectangle", "item_id": "c1", "x": 0.0, "y": 0.0,
                 "width": 50.0, "height": 50.0},
                {"type": "circle", "item_id": "c2", "center_x": 200.0,
                 "center_y": 200.0, "radius": 10.0},
            ],
        }
        # child1 abs (100,100,50,50); child2 abs (290,290,20,20) -> union:
        assert queries.object_bbox(group) == (100.0, 100.0, 210.0, 210.0)

    def test_bezier_bbox_includes_control_handles(self) -> None:
        # The control hull bounds the curve; ignoring handles under-approximates.
        bez = {
            "type": "bezier",
            "item_id": "b1",
            "anchors": [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}],
            "handles_in": [{"x": 0.0, "y": 0.0}, {"x": 70.0, "y": 200.0}],
            "handles_out": [{"x": 30.0, "y": -150.0}, {"x": 100.0, "y": 0.0}],
        }
        assert queries.object_bbox(bez) == (0.0, -150.0, 100.0, 350.0)

    def test_bezier_without_handles_uses_anchors(self) -> None:
        bez = {"type": "bezier", "item_id": "b2",
               "anchors": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}]}
        assert queries.object_bbox(bez) == (0.0, 0.0, 10.0, 20.0)


class TestBboxNormaliser:
    def test_point_like_shapes_collapse_to_zero_size(self) -> None:
        # A group has x/y but no width: it normalises to a zero-size anchor box.
        x, y, w, h = queries.object_bbox(
            {"type": "group", "item_id": "g", "x": 12.0, "y": 34.0}
        )
        assert (x, y, w, h) == (12.0, 34.0, 0.0, 0.0)

    def test_bezier_uses_anchor_extent(self) -> None:
        bez = {
            "type": "bezier",
            "item_id": "b",
            "anchors": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}],
        }
        assert queries.object_bbox(bez) == (0.0, 0.0, 10.0, 20.0)

    def test_empty_snapshot_is_tolerated(self) -> None:
        assert queries.list_objects({}) == []
        assert queries.get_object({}, "x") is None
        assert queries.objects_in_region({}, 0, 0, 1, 1) == []
