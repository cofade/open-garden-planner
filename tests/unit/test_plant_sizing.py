"""Unit tests for the plant-sizing resolver (issue #218).

Pins the precedence as *behavior-preserving*: the resolver must reproduce the
historical rules that used to live inline in ``garden_item``,
``circle_item.paint()`` and the species-assignment helper.
"""

from __future__ import annotations

import pytest

from open_garden_planner.core.plant_sizing import (
    PlantSizing,
    db_spacing_radius_cm,
    sizing_for_item,
)

# --- effective_spacing_radius_cm: override > db/2 > None --------------------


def test_override_masks_database() -> None:
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=33.0, db_max_spread_cm=90.0)
    assert s.effective_spacing_radius_cm == pytest.approx(33.0)
    assert s.spacing_source == "override"


def test_database_fallback_is_half_max_spread() -> None:
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=None, db_max_spread_cm=90.0)
    assert s.effective_spacing_radius_cm == pytest.approx(45.0)
    assert s.spacing_source == "database"


def test_none_when_no_data() -> None:
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=None, db_max_spread_cm=None)
    assert s.effective_spacing_radius_cm is None
    assert s.spacing_source == "none"


def test_zero_or_negative_max_spread_is_no_data() -> None:
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=None, db_max_spread_cm=0.0)
    assert s.effective_spacing_radius_cm is None
    assert s.spacing_source == "none"


def test_non_numeric_max_spread_degrades_to_no_data() -> None:
    # A non-numeric DB value degrades gracefully to "no data" rather than
    # raising on the `> 0` comparison (the single _positive_number guard).
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=None, db_max_spread_cm="tall")
    assert s.effective_spacing_radius_cm is None
    assert s.spacing_source == "none"
    assert s.shows_spacing_ring is False


def test_bool_max_spread_is_not_treated_as_number() -> None:
    # bool is a subclass of int; the guard must reject it so True != 1 cm.
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=None, db_max_spread_cm=True)
    assert s.effective_spacing_radius_cm is None
    assert s.spacing_source == "none"


def test_override_zero_still_wins_over_database() -> None:
    # Historical behaviour: any non-None override is returned verbatim, even 0.
    s = PlantSizing(footprint_radius_cm=10.0, spacing_override_cm=0.0, db_max_spread_cm=90.0)
    assert s.effective_spacing_radius_cm == pytest.approx(0.0)
    assert s.spacing_source == "override"


# --- shows_spacing_ring: effective is not None AND effective > footprint ----


def test_ring_shown_when_effective_exceeds_footprint() -> None:
    s = PlantSizing(footprint_radius_cm=20.0, spacing_override_cm=None, db_max_spread_cm=90.0)
    assert s.shows_spacing_ring is True  # effective 45 > 20


def test_ring_hidden_when_effective_equals_footprint() -> None:
    # Boundary: matches the historical strict ``>`` gate (a ring on the edge
    # conveys nothing once the footprint already shows that size — #213).
    s = PlantSizing(footprint_radius_cm=45.0, spacing_override_cm=None, db_max_spread_cm=90.0)
    assert s.effective_spacing_radius_cm == pytest.approx(45.0)
    assert s.shows_spacing_ring is False


def test_ring_hidden_when_footprint_larger() -> None:
    s = PlantSizing(footprint_radius_cm=60.0, spacing_override_cm=None, db_max_spread_cm=90.0)
    assert s.shows_spacing_ring is False


def test_ring_hidden_when_no_spacing_data() -> None:
    s = PlantSizing(footprint_radius_cm=20.0, spacing_override_cm=None, db_max_spread_cm=None)
    assert s.shows_spacing_ring is False


# --- db_spacing_radius_cm (species-assignment helper) -----------------------


def test_db_spacing_radius_present() -> None:
    assert db_spacing_radius_cm({"max_spread_cm": 90}) == pytest.approx(45.0)


def test_db_spacing_radius_absent() -> None:
    assert db_spacing_radius_cm({}) is None


def test_db_spacing_radius_zero() -> None:
    assert db_spacing_radius_cm({"max_spread_cm": 0}) is None


def test_db_spacing_radius_non_numeric() -> None:
    assert db_spacing_radius_cm({"max_spread_cm": "tall"}) is None


# --- sizing_for_item: duck-typed extraction ---------------------------------


class _FakeItem:
    def __init__(self, radius: float, override: float | None, species: dict | None) -> None:
        self.radius = radius
        self.spacing_radius_cm = override
        self.metadata = {"plant_species": species} if species is not None else {}


def test_sizing_for_item_reads_all_three() -> None:
    item = _FakeItem(20.0, None, {"max_spread_cm": 90})
    s = sizing_for_item(item)
    assert s.footprint_radius_cm == pytest.approx(20.0)
    assert s.spacing_override_cm is None
    assert s.db_max_spread_cm == 90
    assert s.effective_spacing_radius_cm == pytest.approx(45.0)


def test_sizing_for_item_without_species_metadata() -> None:
    item = _FakeItem(20.0, None, None)
    s = sizing_for_item(item)
    assert s.db_max_spread_cm is None
    assert s.effective_spacing_radius_cm is None
