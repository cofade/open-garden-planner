"""The Qt-free reference-point metadata contract (#666, ADR-080)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from open_garden_planner.core import reference_points as ref


def test_marker_and_helpers_read_a_plain_metadata_dict():
    metadata = ref.build_metadata(parent=None)
    assert ref.is_reference_point(metadata)
    assert not ref.is_reference_point({})
    assert ref.parent_id(metadata) is None
    assert not ref.on_contour(metadata)
    assert ref.size_mode(metadata) == ref.SIZE_MODE_PLAN
    assert ref.size_value(metadata) == pytest.approx(ref.DEFAULT_SIZE_CM)
    assert ref.radius_cm(metadata) == pytest.approx(ref.DEFAULT_SIZE_CM / 2)
    assert ref.color(metadata) == ref.DEFAULT_COLOR
    assert ref.stroke_width(metadata) == pytest.approx(ref.DEFAULT_STROKE_WIDTH)


def test_build_metadata_keeps_a_parent_and_its_contour_flag():
    parent = uuid4()
    metadata = ref.build_metadata(parent=parent, on_contour_value=True, size=10.0)
    assert ref.parent_id(metadata) == parent
    assert ref.on_contour(metadata)
    assert ref.size_value(metadata) == pytest.approx(10.0)


def test_on_contour_without_a_parent_is_false():
    metadata = ref.build_metadata(parent=None, on_contour_value=True)
    assert not ref.on_contour(metadata)
    assert ref.PARENT_ID not in metadata


def test_screen_mode_uses_pixels_and_a_plan_size_is_clamped():
    metadata = ref.build_metadata(mode=ref.SIZE_MODE_SCREEN, size=20.0)
    assert ref.size_mode(metadata) == ref.SIZE_MODE_SCREEN
    assert ref.size_value(metadata) == pytest.approx(20.0)
    assert ref.radius_cm(metadata) == pytest.approx(10.0)

    tiny = ref.build_metadata(size=0.1)
    huge = ref.build_metadata(size=10_000.0)
    assert ref.size_value(tiny) == pytest.approx(ref.MIN_SIZE)
    assert ref.size_value(huge) == pytest.approx(ref.MAX_SIZE_PLAN)


def test_unknown_values_fall_back_safely():
    metadata = {
        ref.MARKER: True,
        ref.PARENT_ID: "not-a-uuid",
        ref.SIZE_MODE: "banana",
        ref.SIZE: "not-a-number",
        ref.COLOR: None,
        ref.STROKE_WIDTH: "not-a-number",
    }
    assert ref.parent_id(metadata) is None
    assert ref.size_mode(metadata) == ref.SIZE_MODE_PLAN
    assert ref.size_value(metadata) == pytest.approx(ref.DEFAULT_SIZE_CM)
    assert ref.color(metadata) == ref.DEFAULT_COLOR
    assert ref.stroke_width(metadata) == pytest.approx(ref.DEFAULT_STROKE_WIDTH)


def test_attached_to_returns_only_bound_points_of_that_parent():
    parent = SimpleNamespace(item_id=uuid4())
    other = SimpleNamespace(item_id=uuid4())
    bound = SimpleNamespace(metadata=ref.build_metadata(parent=parent.item_id))
    independent = SimpleNamespace(metadata=ref.build_metadata())
    elsewhere = SimpleNamespace(metadata=ref.build_metadata(parent=other.item_id))
    scene = SimpleNamespace(items=lambda: [parent, bound, independent, elsewhere])

    assert ref.attached_to(scene, parent) == [bound]
    assert ref.attached_to_any(scene, [parent, other]) == [bound, elsewhere]
    assert ref.attached_to(None, parent) == []
