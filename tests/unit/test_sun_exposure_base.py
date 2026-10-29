"""Where a caster stands, and whom it never shades — the per-plant sun estimate (US-F3)
with the base rule (Phase 17 L1.6) in it. Qt-free.

Two things master's v1.30.1 did not have, both through the ONE walk's data:

- a caster's solid is ``footprint x [base, base + height]`` in the grouped sweeps too
  (``GroupedCaster.base_cm``) — the same solid the overlay's ``ShadowCaster`` has;
- a receiver that stands on a parent's soil (``SunReceiver.stands_on``) is not shaded
  by that parent. Without it every plant in a raised bed read 0 hours: the bed's
  footprint covers the ground point under the plant all day.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    compute_heatmap,
    compute_sun_exposure,
    point_rasterizer_reference,
)
from open_garden_planner.core.shadow_geometry import (
    GroupedCaster,
    ShadowCaster,
    compute_grouped_shadows,
    compute_scene_shadows,
    shadow_polygon,
)

DAY = date(2026, 6, 21)
BERLIN = (52.52, 13.405)
BED = ((100.0, 100.0), (300.0, 100.0), (300.0, 220.0), (100.0, 220.0))


def circle(x: float, y: float, radius: float) -> tuple[tuple[float, float], ...]:
    return tuple((x + radius * math.cos(i * math.tau / 24), y + radius * math.sin(i * math.tau / 24))
                 for i in range(24))


def no_raster(_polygons: object, grid: HeatmapGrid) -> np.ndarray:
    """The grid is not what these tests ask (it is compared separately)."""
    return np.zeros((grid.rows, grid.cols), dtype=bool)


def minutes(casters: list[IdentifiedCaster], receivers: list[SunReceiver]) -> dict[str, float]:
    result = compute_sun_exposure(casters, receivers, *BERLIN, DAY,
                                  HeatmapGrid(0, 0, 10, 60, 60), no_raster)
    assert result is not None
    return dict(result.receiver_minutes)


# ── the soil parent ──────────────────────────────────────────────────────────


def test_a_plant_on_a_bed_s_soil_is_not_shaded_by_that_bed() -> None:
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    tomato = IdentifiedCaster("tomato", (circle(200, 160, 30),), 180.0, base_cm=38.0)
    open_ground = minutes([tomato], [SunReceiver("tomato", 200, 160)])["tomato"]
    assert open_ground == 990.0, "Berlin, 21 June: 16.5 hours of daylight samples"
    # what v1.30.1 read: the bed's footprint covers the point under the plant all day
    assert minutes([bed, tomato], [SunReceiver("tomato", 200, 160)]) == {"tomato": 0.0}
    # the plant stands ON the bed: the bed is under it, not between it and the sun
    assert minutes([bed, tomato], [SunReceiver("tomato", 200, 160, stands_on="bed")]) == {
        "tomato": open_ground}


def test_only_the_named_parent_is_spared() -> None:
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    other_bed = IdentifiedCaster("other", (BED,), 40.0)      # a second solid over the same ground
    tomato = IdentifiedCaster("tomato", (circle(200, 160, 30),), 180.0, base_cm=38.0)
    receiver = SunReceiver("tomato", 200, 160, stands_on="bed")
    assert minutes([bed, other_bed, tomato], [receiver]) == {"tomato": 0.0}
    # a parent id nobody casts with, and a receiver named as its own parent: no effect
    assert minutes([bed, tomato], [SunReceiver("tomato", 200, 160, stands_on="gone")]) == {
        "tomato": 0.0}
    assert minutes([tomato], [SunReceiver("tomato", 200, 160, stands_on="tomato")]) == {
        "tomato": 990.0}


def test_two_plants_on_one_bed_are_each_spared_the_bed_and_shade_each_other() -> None:
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    south = IdentifiedCaster("south", (circle(200, 130, 10),), 150.0, base_cm=38.0)
    north = IdentifiedCaster("north", (circle(200, 190, 10),), 20.0, base_cm=38.0)
    result = minutes([bed, south, north],
                     [SunReceiver("south", 200, 130, stands_on="bed"),
                      SunReceiver("north", 200, 190, stands_on="bed")])
    alone = minutes([bed, north], [SunReceiver("north", 200, 190, stands_on="bed")])["north"]
    assert alone == 990.0
    assert result["south"] > result["north"], "the tall plant south of it shades the low one"
    assert 0.0 < result["north"] < alone


def test_a_wall_still_shades_the_plant_on_the_bed() -> None:
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    tomato = IdentifiedCaster("tomato", (circle(200, 160, 30),), 180.0, base_cm=38.0)
    wall = IdentifiedCaster("wall", (((50.0, 60.0), (350.0, 60.0), (350.0, 70.0), (50.0, 70.0)),), 300.0)
    receiver = SunReceiver("tomato", 200, 160, stands_on="bed")
    with_wall = minutes([bed, tomato, wall], [receiver])["tomato"]
    assert 0.0 < with_wall < 990.0 - 120.0, "a 3 m wall 90 cm south of it takes hours of midday sun"


def test_a_plant_on_the_ground_beside_the_bed_is_still_shaded_by_it() -> None:
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    beside = IdentifiedCaster("beside", (circle(200, 232, 5),), 30.0)    # 12 cm north of the bed
    without = minutes([beside], [SunReceiver("beside", 200, 232)])["beside"]
    with_bed = minutes([bed, beside], [SunReceiver("beside", 200, 232)])["beside"]
    assert without == 990.0 and with_bed < without - 60.0, (with_bed, without)


@pytest.mark.parametrize(("kind", "metadata", "solid", "base"), [
    ("RAISED_BED", {}, True, 38.0),                               # the default 40 cm rim
    ("RAISED_BED", {"object_height_cm": 2.0}, True, 0.0),         # an edging: a solid that lifts nothing
    ("RAISED_BED", {"object_height_cm": 1.0}, True, 0.0),
    ("GARDEN_BED", {}, False, 0.0),                               # in the ground: no solid at all
    ("GARDEN_BED", {"object_height_cm": 15.0}, True, 13.0),       # a mounded bed
    ("CONTAINER", {"object_height_cm": 30.0}, True, 30.0),        # a pot: the soil is at its height
    ("TRELLIS", {"object_height_cm": 200.0}, False, 0.0),         # holds no soil
    ("HOUSE", {"object_height_cm": 600.0}, False, 0.0),
    (None, {"object_height_cm": 40.0}, False, 0.0),
])
def test_a_soil_parent_is_a_solid_whether_or_not_it_lifts(
        kind: str | None, metadata: dict[str, float], solid: bool, base: float) -> None:
    """``is_solid_soil_parent`` is the question the sun estimate asks ("is the plant in the
    parent's solid?"); ``standing_base_cm`` the one the casters and the 3D records ask
    ("how high is its soil?"). They differ exactly where a solid lifts nothing."""
    from open_garden_planner.core.object_height import is_solid_soil_parent, standing_base_cm
    from open_garden_planner.core.object_types import ObjectType

    parent_type = ObjectType[kind] if kind is not None else None
    assert is_solid_soil_parent(parent_type, dict(metadata)) is solid
    assert standing_base_cm(parent_type, dict(metadata)) == base
    assert solid or base == 0.0, "nothing is lifted by a parent that is no solid"


# ── the base in the grouped sweeps ───────────────────────────────────────────


@pytest.mark.parametrize(("elevation", "azimuth"), [(61.0, 180.0), (20.0, 95.0), (8.0, 300.0)])
@pytest.mark.parametrize("base", [0.0, 38.0, 73.0])
def test_a_grouped_caster_is_the_overlay_s_solid(elevation: float, azimuth: float, base: float) -> None:
    footprints = (circle(200, 160, 30), circle(260, 160, 12))
    grouped = compute_grouped_shadows([GroupedCaster(footprints, 180.0, base)], elevation, azimuth)
    assert grouped is not None
    union, owned = grouped
    overlay = compute_scene_shadows([ShadowCaster(list(fp), 180.0, base) for fp in footprints],
                                    elevation, azimuth)
    assert union == overlay, "the heatmap's union is the overlay's union, base included"
    assert owned == [overlay], "one owner: its own union is the same polygons"
    single = compute_grouped_shadows([GroupedCaster((footprints[0],), 180.0, base)], elevation, azimuth)
    assert single is not None
    assert single[1] == [shadow_polygon(footprints[0], 180.0, elevation, azimuth, base)]


def test_a_pair_stands_on_the_ground_and_nothing_else_is_read_as_a_base() -> None:
    footprints = (circle(200, 160, 30),)
    pair = compute_grouped_shadows([(footprints, 180.0)], 30.0, 180.0)
    on_ground = compute_grouped_shadows([GroupedCaster(footprints, 180.0)], 30.0, 180.0)
    raised = compute_grouped_shadows([GroupedCaster(footprints, 180.0, 38.0)], 30.0, 180.0)
    assert pair == on_ground and raised != on_ground
    with pytest.raises(TypeError, match="GroupedCaster"):
        compute_grouped_shadows([(footprints, 180.0, 38.0)], 30.0, 180.0)   # a bare 3-tuple
    with pytest.raises(TypeError, match="GroupedCaster"):
        compute_grouped_shadows([[footprints, 180.0]], 30.0, 180.0)         # a list


def test_the_grid_of_the_estimate_is_the_heatmap_of_the_same_solids() -> None:
    """One day, both ways: the identified casters' grid equals ``compute_heatmap`` over the
    overlay's ``ShadowCaster``s — bases included. (Before the merge the receiver run
    dropped the base, and the heatmap would have disagreed with the overlay.)"""
    grid = HeatmapGrid(0, 0, 20, 30, 30)
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    tomato = IdentifiedCaster("tomato", (circle(200, 160, 30),), 180.0, base_cm=38.0)
    result = compute_sun_exposure([bed, tomato], [], *BERLIN, DAY, grid, point_rasterizer_reference,
                                  step_minutes=60)
    assert result is not None
    with_base = compute_heatmap(
        [ShadowCaster(list(BED), 40.0), ShadowCaster(list(tomato.footprints[0]), 180.0, 38.0)],
        *BERLIN, DAY, grid, point_rasterizer_reference, step_minutes=60)
    without_base = compute_heatmap(
        [ShadowCaster(list(BED), 40.0), ShadowCaster(list(tomato.footprints[0]), 180.0)],
        *BERLIN, DAY, grid, point_rasterizer_reference, step_minutes=60)
    assert with_base is not None and without_base is not None
    assert np.array_equal(result.minutes, with_base)
    assert not np.array_equal(with_base, without_base), "the base is visible in this grid"


def test_a_raised_neighbour_s_shadow_starts_beyond_its_base_offset() -> None:
    """A stated limit of the ground-level estimate, pinned so that it is a decision: a
    caster on raised soil casts onto the GROUND plane from base / tan(alpha) on, so a
    receiver right behind it is reached later in the day than it would be on the soil."""
    elevation, azimuth = 45.0, 180.0      # shadows fall due north, as long as the solid is high
    post = (circle(200, 100, 2),)
    grouped = compute_grouped_shadows([GroupedCaster(post, 100.0, 38.0)], elevation, azimuth)
    assert grouped is not None
    ys = [y for polygon in grouped[1][0] for _x, y in polygon]
    assert min(ys) == pytest.approx(100.0 - 2.0 + 38.0, abs=0.01)
    assert max(ys) == pytest.approx(100.0 + 2.0 + 138.0, abs=0.01)



# ── elevated receivers (#641) ───────────────────────────────────────────────


def test_obstacle_below_receiver_elevation_casts_zero_shade() -> None:
    """An obstacle strictly lower than the receiver's soil elevation cannot shade it (#641)."""
    edging = IdentifiedCaster("edging", (((50.0, 90.0), (350.0, 90.0), (350.0, 100.0), (50.0, 100.0)),), 30.0)
    bed = IdentifiedCaster("bed", (BED,), 40.0)
    tomato = IdentifiedCaster("tomato", (circle(200, 110, 10),), 100.0, base_cm=38.0)

    # At ground level (elevation_cm=0.0): edging shades the ground point
    ground_rx = SunReceiver("tomato", 200, 110, stands_on="bed", elevation_cm=0.0)
    res_ground = minutes([edging, bed, tomato], [ground_rx])["tomato"]

    # Elevated on the bed's soil (elevation_cm=38.0): edging top (30 cm) <= receiver elevation (38 cm)
    elevated_rx = SunReceiver("tomato", 200, 110, stands_on="bed", elevation_cm=38.0)
    res_elevated = minutes([edging, bed, tomato], [elevated_rx])["tomato"]

    # Without the edging
    alone = minutes([bed, tomato], [elevated_rx])["tomato"]

    assert res_elevated == alone == 990.0, "obstacle below receiver elevation casts zero shade"
    assert res_ground < alone - 120.0, "ground-level receiver is falsely shaded by the low edging"


def test_elevated_receiver_clears_fence_shadow_faster_than_ground() -> None:
    """An elevated plant clears a fence's shadow earlier in the day and gets more sun (#641)."""
    # Fence of height 120 cm located south at y in [70, 80]
    fence = IdentifiedCaster("fence", (((50.0, 70.0), (350.0, 70.0), (350.0, 80.0), (50.0, 80.0)),), 120.0)
    bed = IdentifiedCaster("bed", (BED,), 50.0)
    thyme = IdentifiedCaster("thyme", (circle(200, 115, 10),), 20.0, base_cm=48.0)

    ground_rx = SunReceiver("thyme", 200, 115, stands_on="bed", elevation_cm=0.0)
    elevated_rx = SunReceiver("thyme", 200, 115, stands_on="bed", elevation_cm=48.0)

    ground_sun = minutes([fence, bed, thyme], [ground_rx])["thyme"]
    elevated_sun = minutes([fence, bed, thyme], [elevated_rx])["thyme"]

    # Elevated receiver clears shadow hours earlier because effective fence height is only 120 - 48 = 72 cm
    assert elevated_sun >= ground_sun + 120.0, (
        f"elevated plant ({elevated_sun} min) must receive significantly more sun than ground ({ground_sun} min)"
    )

def test_non_finite_receiver_elevation_is_excluded() -> None:
    """Non-finite receiver elevations (NaN, Inf) must be rejected and not receive daylight."""
    # One valid receiver, one NaN elevation receiver, one Inf elevation receiver
    r_valid = SunReceiver(item_id="valid", x_cm=250.0, y_cm=250.0, elevation_cm=0.0)
    r_nan = SunReceiver(item_id="nan", x_cm=250.0, y_cm=250.0, elevation_cm=float("nan"))
    r_inf = SunReceiver(item_id="inf", x_cm=250.0, y_cm=250.0, elevation_cm=float("inf"))

    res = minutes([], [r_valid, r_nan, r_inf])
    # Only the valid receiver should have exposure minutes calculated
    assert "valid" in res
    assert "nan" not in res
    assert "inf" not in res
