"""Pin agreed tolerance bands and unavailable states, without a Qt runtime."""

from datetime import date

import pytest

from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.sun_mismatch_service import (
    CanopyPlant,
    canopy_members,
    classify_mismatch,
    evaluate_sun,
)

DAY = date(2026, 6, 21)


@pytest.mark.parametrize("required,hours,direction", [
    ("full_sun", 5, None), ("full_sun", 4.999, "too_little"), ("full_sun", 18, None),
    ("partial_sun", 3, None), ("partial_sun", 2.999, "too_little"),
    ("partial_sun", 7, None), ("partial_sun", 7.001, "too_much"),
    ("partial_shade", 1, None), ("partial_shade", .999, "too_little"),
    ("partial_shade", 5, None), ("partial_shade", 5.001, "too_much"),
    ("full_shade", 0, None), ("full_shade", 3, None), ("full_shade", 3.001, "too_much"),
    ("unknown", 0, None), ("unknown", 24, None), ("invalid", 0, None),
])
def test_warning_bands(required, hours, direction):
    evaluation = evaluate_sun("a", required, hours * 60, DAY)
    mismatch = classify_mismatch(evaluation)
    assert (mismatch.direction if mismatch else None) == direction
    if mismatch:
        assert mismatch.severity == "warning" and mismatch.hours == hours


@pytest.mark.parametrize("minutes", [None, -1, float("nan"), float("inf"), "0", True])
def test_unavailable_is_never_zero_or_pass(minutes):
    evaluation = evaluate_sun("a", SunRequirement.FULL_SUN, minutes, DAY, reason="stale")
    assert evaluation.hours is None and evaluation.reason
    assert classify_mismatch(evaluation) is None


def test_canopy_boundary_layers_and_order():
    plants = [CanopyPlant("tree", "Tree", 0, 0, "canopy"),
              CanopyPlant("b", "B", 0, 300, "herbaceous"),
              CanopyPlant("a", "A", 300, 0, "herbaceous"),
              CanopyPlant("a2", "A", -300, 0, "herbaceous"),
              CanopyPlant("unknown", "Z", 0, 0, "unknown"),
              CanopyPlant("outside", "Outside", 300.001, 0)]
    assert [p.item_id for p in canopy_members("tree", (0, 0), 600, plants)] == ["a", "a2", "b", "unknown"]
    assert canopy_members("tree", (0, 0), None, plants) is None
    assert canopy_members("tree", (0, 0), 0, plants) is None
