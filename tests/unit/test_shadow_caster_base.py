"""Base stacking in the shared 2D caster model (Phase 17 L1.6, #385, gate G4).

A caster is a solid ``footprint x [base_cm, base_cm + height_cm]``. With the sun
at elevation α its ground shadow is

    S(F, b, h) = { p + t·d : p ∈ F, t ∈ [b / tan α, (b + h) / tan α] }

(``d`` = the unit shadow direction): the footprint projected from the base, swept
on to its projection from the top. The part below the base is somebody else's
shadow — the bed the plant stands on.

Qt-free. Three independent proofs of that definition:

1. the tip moves by exactly ``b / tan α`` (the gate's number);
2. ``S(F, b, h)`` is ``S(F, 0, h)`` translated by ``(b / tan α)·d``;
3. a ray oracle that knows nothing about polygons: a ground point is shaded iff
   the ray from it toward the sun passes through the solid.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_garden_planner.core import shadow_geometry as sg
from open_garden_planner.core.object_height import (
    SOIL_DROP_CM,
    soil_surface_cm,
    standing_base_cm,
)
from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    compute_heatmap,
    point_rasterizer_reference,
)
from open_garden_planner.core.shadow_geometry import (
    ShadowCaster,
    circle_footprint,
    compute_scene_shadows,
    shadow_direction_scene,
    shadow_polygon,
)

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
L_SHAPE = [(0.0, 0.0), (300.0, 0.0), (300.0, 120.0), (120.0, 120.0), (120.0, 400.0), (0.0, 400.0)]
CIRCLE = circle_footprint(40.0, -25.0, 30.0)
FOOTPRINTS = {"square": SQUARE, "l_shape": L_SHAPE, "circle": CIRCLE}
ELEVATIONS = [15.0, 35.0, 60.0]
AZIMUTHS = [0.0, 90.0, 135.0, 203.74, 300.0]
GRID_CM = 1.0 / sg.CLIPPER_SCALE  # pyclipper's integer grid: 1e-3 cm


def _reach(polygons: list[list[tuple[float, float]]], direction: tuple[float, float]) -> tuple[float, float]:
    """(nearest, farthest) extent of a polygon set along ``direction``."""
    along = [x * direction[0] + y * direction[1] for polygon in polygons for x, y in polygon]
    return min(along), max(along)


def _inside(polygons: list[list[tuple[float, float]]], x: float, y: float) -> bool:
    """Even-odd point-in-polygon over a polygon set (holes come as extra rings)."""
    hit = False
    for polygon in polygons:
        count = len(polygon)
        for index in range(count):
            x1, y1 = polygon[index]
            x2, y2 = polygon[(index + 1) % count]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


class TestTipShift:
    """Gate G4: the shadow tip of a raised caster lies base / tan α further from the sun."""

    @pytest.mark.parametrize("azimuth", AZIMUTHS)
    @pytest.mark.parametrize("elevation", ELEVATIONS)
    @pytest.mark.parametrize("name", sorted(FOOTPRINTS))
    def test_tip_and_near_edge_move_by_base_over_tan_alpha(
        self, name: str, elevation: float, azimuth: float
    ) -> None:
        footprint, height, base = FOOTPRINTS[name], 60.0, 38.0
        direction = shadow_direction_scene(azimuth)
        ground = shadow_polygon(footprint, height, elevation, azimuth)
        raised = shadow_polygon(footprint, height, elevation, azimuth, base_cm=base)
        expected = base / math.tan(math.radians(elevation))
        near0, far0 = _reach(ground, direction)
        near1, far1 = _reach(raised, direction)
        assert far1 - far0 == pytest.approx(expected, abs=0.1)
        assert near1 - near0 == pytest.approx(expected, abs=0.1)
        # measured: the only error is the integer grid (two roundings of 0.5e-3 cm)
        assert abs((far1 - far0) - expected) <= 2.0 * GRID_CM
        # and the tip itself: farthest footprint point + (base + height) / tan α
        footprint_far = max(x * direction[0] + y * direction[1] for x, y in footprint)
        assert far1 == pytest.approx(
            footprint_far + (base + height) / math.tan(math.radians(elevation)), abs=0.1)

    def test_the_gate_s_own_numbers(self) -> None:
        """A 60 cm plant on the soil of a 40 cm bed (base 38), sun at 35°: the tip
        was 85.7 cm from the plant and is now 140.0 cm — 54.3 cm further."""
        direction = shadow_direction_scene(180.0)  # sun in the south: shadow due north
        tip = _reach(shadow_polygon(SQUARE, 60.0, 35.0, 180.0, base_cm=38.0), direction)[1]
        old = _reach(shadow_polygon(SQUARE, 60.0, 35.0, 180.0), direction)[1]
        assert old - 100.0 == pytest.approx(85.69, abs=0.01)
        assert tip - 100.0 == pytest.approx(139.96, abs=0.01)
        assert tip - old == pytest.approx(38.0 / math.tan(math.radians(35.0)), abs=2e-3)


class TestSweptShadowDefinition:
    @pytest.mark.parametrize("azimuth", AZIMUTHS)
    @pytest.mark.parametrize("elevation", ELEVATIONS)
    @pytest.mark.parametrize("name", sorted(FOOTPRINTS))
    def test_it_is_the_ground_shadow_translated_by_the_base_offset(
        self, name: str, elevation: float, azimuth: float
    ) -> None:
        footprint, height, base = FOOTPRINTS[name], 120.0, 75.0
        dx, dy = shadow_direction_scene(azimuth)
        offset = base / math.tan(math.radians(elevation))
        ground = shadow_polygon(footprint, height, elevation, azimuth)
        raised = shadow_polygon(footprint, height, elevation, azimuth, base_cm=base)
        assert len(raised) == len(ground) == 1
        moved = sorted((x + dx * offset, y + dy * offset) for x, y in ground[0])
        actual = sorted(raised[0])
        assert len(actual) == len(moved)
        worst = max(math.hypot(a[0] - m[0], a[1] - m[1]) for a, m in zip(actual, moved, strict=True))
        assert worst <= 2.0 * GRID_CM  # one rounding of the offset, one of the vertex

    @pytest.mark.parametrize("azimuth", [135.0, 203.74])
    @pytest.mark.parametrize("elevation", ELEVATIONS)
    def test_a_ray_oracle_agrees_point_by_point(self, elevation: float, azimuth: float) -> None:
        """Independent of the polygon machinery: a ground point q is shaded iff the
        ray from q toward the sun crosses the solid, i.e. ``q - t·d`` lies in the
        footprint for some t in [b / tan α, (b + h) / tan α]. For the axis-aligned
        square that set of t is an interval (slab clipping)."""
        height, base = 80.0, 50.0
        dx, dy = shadow_direction_scene(azimuth)
        tan_a = math.tan(math.radians(elevation))
        t0, t1 = base / tan_a, (base + height) / tan_a
        shadow = shadow_polygon(SQUARE, height, elevation, azimuth, base_cm=base)
        rng = np.random.default_rng(385)
        reach = t1 + 150.0
        checked = shaded = 0
        for qx, qy in rng.uniform(-reach, reach + 100.0, size=(4000, 2)):
            low, high = t0, t1
            for q, d in ((qx, dx), (qy, dy)):  # 0 <= q - t·d <= 100, per axis
                if abs(d) < 1e-12:
                    if not 0.0 <= q <= 100.0:
                        low, high = 1.0, 0.0
                    continue
                a, b = (q - 100.0) / d, q / d
                low, high = max(low, min(a, b)), min(high, max(a, b))
            margin = high - low
            if abs(margin) < 0.05:  # within half a millimetre of the outline: skip
                continue
            checked += 1
            expected = bool(margin > 0.0)
            shaded += expected
            assert _inside(shadow, float(qx), float(qy)) is expected
        assert checked > 3500 and shaded > 20  # the oracle saw both sides

    @pytest.mark.parametrize("elevation", ELEVATIONS)
    def test_a_raised_shadow_leaves_its_own_footprint_when_the_base_is_high_enough(
        self, elevation: float
    ) -> None:
        """The ground under a floating solid is lit once base / tan α exceeds the
        footprint: nothing below the base casts for this caster."""
        base = 150.0 * math.tan(math.radians(elevation))  # offset 150 cm > the 100 cm square
        shadow = shadow_polygon(SQUARE, 10.0, elevation, 180.0, base_cm=base)
        assert not _inside(shadow, 50.0, 50.0)
        assert _inside(shadow, 50.0, 50.0 + 150.0 + 1.0)

    def test_the_bed_casts_the_part_below(self) -> None:
        """A plant on a bed's soil: the union of the bed's shadow and the raised
        plant's is ONE region reaching from the bed to the plant's tip — the stretch
        the plant no longer claims is the bed's own shadow."""
        bed = [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)]
        plant = circle_footprint(100.0, 50.0, 20.0)
        base = soil_surface_cm("RAISED_BED", 40.0)
        union = compute_scene_shadows(
            [ShadowCaster(bed, 40.0), ShadowCaster(plant, 60.0, base)], 35.0, 180.0)
        assert len(union) == 1
        tan_a = math.tan(math.radians(35.0))
        top = max(y for _x, y in union[0])
        assert top == pytest.approx(70.0 + (base + 60.0) / tan_a, abs=0.01)
        assert _inside(union, 100.0, 100.0 + 40.0 / tan_a - 1.0)  # the bed's shadow
        assert _inside(union, 100.0, 70.0 + (base + 60.0) / tan_a - 1.0)  # the plant's tip
        # Before L1.6 the same plant cast from the ground: its tip (70 + 60 / tan α =
        # 155.7) did not even leave the bed's own shadow (100 + 40 / tan α = 157.1),
        # so the plant was invisible in the shadow map.
        from_the_ground = compute_scene_shadows(
            [ShadowCaster(bed, 40.0), ShadowCaster(plant, 60.0)], 35.0, 180.0)
        old_top = max(y for _x, y in from_the_ground[0])
        assert old_top == pytest.approx(100.0 + 40.0 / tan_a, abs=0.01)
        assert 70.0 + 60.0 / tan_a < old_top < top
        assert top - (70.0 + 60.0 / tan_a) == pytest.approx(base / tan_a, abs=0.01)


class TestBaseZeroIsToday:
    @pytest.mark.parametrize("azimuth", AZIMUTHS)
    @pytest.mark.parametrize("elevation", [0.5, 15.0, 35.0, 60.0, 90.0])
    def test_a_caster_on_the_ground_equals_the_plain_pair(self, elevation: float, azimuth: float) -> None:
        pairs = [(SQUARE, 100.0), (L_SHAPE, 37.5), (CIRCLE, 450.0)]
        casters = [ShadowCaster(fp, h) for fp, h in pairs]
        assert casters[0].base_cm == 0.0
        assert compute_scene_shadows(casters, elevation, azimuth) == compute_scene_shadows(
            pairs, elevation, azimuth)
        for (fp, h), caster in zip(pairs, casters, strict=True):
            assert shadow_polygon(fp, h, elevation, azimuth) == shadow_polygon(
                fp, h, elevation, azimuth, base_cm=caster.base_cm)

    @pytest.mark.parametrize("bad", [-5.0, float("nan"), float("inf"), float("-inf")])
    def test_a_base_that_is_no_height_above_ground_is_the_ground(self, bad: float) -> None:
        assert shadow_polygon(SQUARE, 100.0, 35.0, 180.0, base_cm=bad) == shadow_polygon(
            SQUARE, 100.0, 35.0, 180.0)
        assert compute_scene_shadows([ShadowCaster(SQUARE, 100.0, bad)], 35.0, 180.0) == (
            compute_scene_shadows([(SQUARE, 100.0)], 35.0, 180.0))

    def test_no_height_still_casts_nothing_whatever_the_base(self) -> None:
        assert shadow_polygon(SQUARE, None, 35.0, 180.0, base_cm=40.0) == []
        assert compute_scene_shadows([ShadowCaster(SQUARE, 0.0, 40.0)], 35.0, 180.0) == []

    def test_night_is_empty_for_a_raised_caster_too(self) -> None:
        assert compute_scene_shadows([ShadowCaster(SQUARE, 100.0, 40.0)], -3.0, 180.0) == []

    def test_the_fallback_sweep_carries_the_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reference = shadow_polygon(SQUARE, 100.0, 59.29, 203.74, base_cm=38.0)

        def broken(*_args: object, **_kwargs: object) -> None:
            raise sg.pyclipper.ClipperException("no MinkowskiSum on this build")

        monkeypatch.setattr(sg.pyclipper, "MinkowskiSum", broken)
        fallback = sg.shadow_polygon(SQUARE, 100.0, 59.29, 203.74, base_cm=38.0)
        direction = shadow_direction_scene(203.74)
        assert _reach(fallback, direction) == pytest.approx(_reach(reference, direction), abs=1e-3)


class TestTheGroundPathIsTheReleasedCode:
    """The platform-independent half of "nothing on the ground changed" (review
    round 1, P1-2).

    ``tests/unit/shadow_geometry_v1_29_10.py`` is ``core/shadow_geometry.py`` as
    released in v1.29.10 — the same git blob, checked below — kept as an oracle.
    For every caster that stands on the ground the released functions and today's
    return the very same polygons, compared exactly. Both run on the machine the
    test runs on, so they share its C library: unlike the golden fixture, this
    holds bit for bit on Linux, on Windows, anywhere — and it is what makes the
    change provably confined to casters with a base.
    """

    RELEASED_BLOB = "bde1030b22428cfb4a3bc5c415a01fe3b3342baf"  # git rev-parse v1.29.10:<the file>

    @staticmethod
    def _cases() -> list[tuple[list[tuple[float, float]], float | None, float, float]]:
        rng = np.random.default_rng(385)
        footprints = [SQUARE, SQUARE[::-1], L_SHAPE, CIRCLE,
                      [(0.0, 0.0), (400.0, 0.0), (400.0, 1.5), (0.0, 1.5)],   # a fence strip
                      [(12.3455, 7.0005), (97.1235, 3.4995), (55.5555, 88.8885)]]  # half grid steps
        for _ in range(40):  # random simple polygons: a star-shaped ring round a centre
            count = int(rng.integers(3, 12))
            angles = np.sort(rng.uniform(0.0, 2.0 * math.pi, count))
            radii = rng.uniform(5.0, 400.0, count)
            centre = rng.uniform(-2000.0, 2000.0, 2)
            ring = [(float(centre[0] + r * math.cos(a)), float(centre[1] + r * math.sin(a)))
                    for a, r in zip(angles, radii, strict=True)]
            footprints.append(ring if rng.random() < 0.5 else ring[::-1])
        cases = []
        heights = [None, 0.0, -5.0, 0.004, 1.0, 37.5, 100.0, 450.0, 1234.567]
        elevations = [-3.0, 0.49, 0.5, 5.0, 15.0, 35.0, 59.29, 60.0, 89.999, 90.0]
        for index, footprint in enumerate(footprints):
            for step in range(6):
                cases.append((footprint, heights[(index + step) % len(heights)],
                              elevations[(index * 3 + step) % len(elevations)],
                              float(rng.uniform(0.0, 360.0)) if step else 203.74))
        return cases

    def test_the_oracle_is_the_released_file(self) -> None:
        import hashlib
        from pathlib import Path

        from tests.unit import shadow_geometry_v1_29_10 as released

        content = Path(released.__file__).read_bytes().replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()  # noqa: S324 — git's id
        assert blob == self.RELEASED_BLOB
        assert not hasattr(released, "ShadowCaster") and not hasattr(released, "base_offset_cm")

    def test_one_caster_on_the_ground(self) -> None:
        from tests.unit import shadow_geometry_v1_29_10 as released

        cases = self._cases()
        assert len(cases) == 276
        cast = 0
        for footprint, height, elevation, azimuth in cases:
            before = released.shadow_polygon(footprint, height, elevation, azimuth)
            assert sg.shadow_polygon(footprint, height, elevation, azimuth) == before
            assert sg.shadow_polygon(footprint, height, elevation, azimuth, base_cm=0.0) == before
            assert sg.compute_scene_shadows([(footprint, height)], elevation, azimuth) == (
                released.compute_scene_shadows([(footprint, height)], elevation, azimuth))
            if height is not None and height > 0.0:
                assert sg.compute_scene_shadows([ShadowCaster(footprint, height)], elevation, azimuth) == (
                    released.compute_scene_shadows([(footprint, height)], elevation, azimuth))
            cast += bool(before)
        assert cast > 100  # most of them really cast something

    def test_the_integer_paths_themselves(self) -> None:
        """One level down: the paths handed to the union, before any float exists."""
        from tests.unit import shadow_geometry_v1_29_10 as released

        for footprint, height, elevation, azimuth in self._cases():
            length = sg.shadow_length_cm(height, elevation)
            if length is None:
                continue
            direction = sg.shadow_direction_scene(azimuth)
            before = released._caster_paths_int(footprint, length, direction)
            assert sg._caster_paths_int(footprint, length, direction) == before
            assert sg._caster_paths_int(footprint, length, direction, 0.0) == before

    def test_a_whole_scene_on_the_ground(self) -> None:
        from tests.unit import shadow_geometry_v1_29_10 as released

        pairs = [(footprint, height) for footprint, height, _e, _a in self._cases()[::5]]
        grounded = [ShadowCaster(footprint, height) for footprint, height in pairs  # type: ignore[arg-type]
                    if height is not None]
        plain = [(c.footprint, c.height_cm) for c in grounded]
        for elevation in (0.5, 15.0, 35.0, 60.0):
            for azimuth in (0.0, 135.0, 203.74, 300.0):
                before = released.compute_scene_shadows(pairs, elevation, azimuth)
                assert sg.compute_scene_shadows(pairs, elevation, azimuth) == before
                assert sg.compute_scene_shadows(grounded, elevation, azimuth) == (
                    released.compute_scene_shadows(plain, elevation, azimuth))

    def test_the_heatmap_of_a_scene_on_the_ground(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``compute_heatmap`` with the RELEASED shadow function in place of today's:
        the same minutes, exactly, for casters on the ground."""
        from datetime import date

        from open_garden_planner.core import shade_aggregation
        from tests.unit import shadow_geometry_v1_29_10 as released

        casters = [(SQUARE, 100.0), (L_SHAPE, 37.5), (CIRCLE, 450.0)]
        grid = HeatmapGrid.for_rect(-400.0, -400.0, 1000.0, 1200.0, cell_cm=25.0)
        days = (date(2026, 6, 21), date(2026, 12, 21))
        today = [compute_heatmap(casters, 52.52, 13.405, day, grid, point_rasterizer_reference)
                 for day in days]
        as_casters = [compute_heatmap([ShadowCaster(fp, h) for fp, h in casters], 52.52, 13.405, day,
                                      grid, point_rasterizer_reference) for day in days]
        monkeypatch.setattr(shade_aggregation, "compute_scene_shadows", released.compute_scene_shadows)
        before = [compute_heatmap(casters, 52.52, 13.405, day, grid, point_rasterizer_reference)
                  for day in days]
        for now, wrapped, then in zip(today, as_casters, before, strict=True):
            assert now is not None and wrapped is not None and then is not None
            assert np.array_equal(now, then) and np.array_equal(wrapped, then)
            assert float(then.min()) < float(then.max())  # a real map, not all sun

    def test_and_a_base_really_is_a_different_shadow(self) -> None:
        from tests.unit import shadow_geometry_v1_29_10 as released

        before = released.compute_scene_shadows([(SQUARE, 100.0)], 35.0, 203.74)
        assert sg.compute_scene_shadows([ShadowCaster(SQUARE, 100.0, 38.0)], 35.0, 203.74) != before


class TestACasterIsATypeNotALength:
    """Review round 1, P2-4: a third element is a base only when a ``ShadowCaster``
    says so. Before, any 3-tuple's last element was read as a height above ground."""

    def test_the_two_accepted_shapes(self) -> None:
        assert sg.caster_fields(ShadowCaster(SQUARE, 60.0, 38.0)) == (SQUARE, 60.0, 38.0)
        assert sg.caster_fields(ShadowCaster(SQUARE, 60.0)) == (SQUARE, 60.0, 0.0)
        assert sg.caster_fields((SQUARE, 60.0)) == (SQUARE, 60.0, 0.0)
        assert sg.caster_fields((SQUARE, None)) == (SQUARE, None, 0.0)

    @pytest.mark.parametrize("bad", [
        (SQUARE, 60.0, 38.0),           # a bare 3-tuple: is the third a base, a name, an id?
        (SQUARE, 60.0, "item-7"),
        (SQUARE,),
        (),
        [SQUARE, 60.0],                 # a list is not the pair
        (SQUARE, 60.0, 38.0, 1.0),
    ], ids=["3-tuple", "3-tuple-with-id", "1-tuple", "empty", "list", "4-tuple"])
    def test_anything_else_is_refused(self, bad: object) -> None:
        with pytest.raises(TypeError, match="ShadowCaster or a \\(footprint, height_cm\\) tuple"):
            sg.caster_fields(bad)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            compute_scene_shadows([bad], 35.0, 180.0)  # type: ignore[list-item]

    def test_another_named_tuple_is_not_a_caster(self) -> None:
        from typing import NamedTuple

        class Lookalike(NamedTuple):
            footprint: list[tuple[float, float]]
            height_cm: float

        with pytest.raises(TypeError):
            sg.caster_fields(Lookalike(SQUARE, 60.0))  # type: ignore[arg-type]

    def test_the_heatmap_refuses_it_too(self) -> None:
        from datetime import date

        grid = HeatmapGrid.for_rect(-200.0, -200.0, 500.0, 500.0, cell_cm=50.0)
        with pytest.raises(TypeError):
            compute_heatmap([(SQUARE, 60.0, 38.0)], 52.52, 13.405, date(2026, 6, 21), grid,  # type: ignore[list-item]
                            point_rasterizer_reference)


class TestHeatmapConsumesTheBase:
    def test_every_sample_rasterises_the_raised_shadow(self) -> None:
        """The heatmap worker hands its casters to the same shadow function as the
        overlay: what reaches the rasteriser is ``compute_scene_shadows`` of the
        casters WITH their base."""
        from datetime import date

        from open_garden_planner.core.shade_aggregation import daylight_samples
        from open_garden_planner.core.shadow_geometry import MIN_SUN_ELEVATION_DEG

        casters = [ShadowCaster(SQUARE, 60.0, 38.0)]
        grid = HeatmapGrid.for_rect(-200.0, -200.0, 500.0, 500.0, cell_cm=50.0)
        seen: list[list[list[tuple[float, float]]]] = []

        def rasterise(polygons: list[list[tuple[float, float]]], g: HeatmapGrid) -> np.ndarray:
            seen.append(polygons)
            return point_rasterizer_reference(polygons, g)

        day = date(2026, 6, 21)
        raised = compute_heatmap(casters, 52.52, 13.405, day, grid, rasterise)
        samples = daylight_samples(52.52, 13.405, day)
        assert len(seen) == len(samples) > 60
        for polygons, sample in zip(seen, samples, strict=True):
            assert polygons == compute_scene_shadows(
                casters, max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG), sample.azimuth_deg)
        grounded = compute_heatmap([(SQUARE, 60.0)], 52.52, 13.405, day, grid,
                                   point_rasterizer_reference)
        assert raised is not None and grounded is not None
        assert not np.array_equal(raised, grounded)  # the map really changes
        # the ground under the raised solid's own footprint gets sun the grounded one never does
        row, col = grid.cell_at(50.0, 50.0)
        assert grounded[row, col] == 0.0 and raised[row, col] > 0.0


class TestSoilRule:
    """ONE rule for where a plant stands: the soil of a soil container with a height."""

    def test_a_bed_s_soil_lies_two_centimetres_below_its_rim(self) -> None:
        """A bed has a rim height and no fill in the plan: the drop is an assumption."""
        assert SOIL_DROP_CM == 2.0
        assert soil_surface_cm("RAISED_BED", 40.0) == 38.0
        assert soil_surface_cm("GARDEN_BED", 25.0) == 23.0

    @pytest.mark.parametrize("kind", ["CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"])
    def test_a_container_s_soil_is_at_its_height(self, kind: str) -> None:
        """Review round 1, P2-7. A container's resolved height IS its soil fill height
        (FR-SUN-02: the fill stands in for the height), so that is where the soil is.
        Round 0 put it 2 cm lower — below the plan's own soil level, for a lip the plan
        does not hold."""
        from open_garden_planner.core.container_model import container_height_cm
        from open_garden_planner.core.object_height import effective_height_cm

        assert soil_surface_cm(kind, 30.0) == 30.0
        for metadata in (None, {}, {"container_height_cm": 45.0}):
            fill = container_height_cm(metadata)
            assert effective_height_cm(kind, metadata) == fill       # the datum …
            assert standing_base_cm(kind, metadata) == fill          # … is where a plant stands
        # an explicit height wins over the fill; the soil is at the top the user gave
        assert standing_base_cm(kind, {"container_height_cm": 20.0, "object_height_cm": 90.0}) == 90.0

    @pytest.mark.parametrize("height", [None, 0.0, -3.0, float("nan"), float("inf")])
    def test_no_height_means_the_ground(self, height: float | None) -> None:
        assert soil_surface_cm("RAISED_BED", height) == 0.0
        assert soil_surface_cm("CONTAINER", height) == 0.0

    def test_a_parent_taller_than_the_scene_can_hold_has_no_soil_to_stand_on(self) -> None:
        """Merge of 9944012. The scene contract holds no length beyond ``MAX_LENGTH_CM``
        (10 km): a bed taller than that gets no record, hence no solid. Nothing stands
        on a parent that is not there — the rule an infinite height already followed.
        Without it a bed of 10 km + 1 cm had no record while its plant floated at
        9,999.99 m over nothing, and a taller one took its plant out of the scene too."""
        from open_garden_planner.core import object_height
        from open_garden_planner.core.scene3d import MAX_LENGTH_CM

        assert object_height.MAX_PARENT_HEIGHT_CM == MAX_LENGTH_CM == 1e6  # a mirror, pinned
        assert soil_surface_cm("RAISED_BED", MAX_LENGTH_CM) == MAX_LENGTH_CM - SOIL_DROP_CM
        assert soil_surface_cm("CONTAINER", MAX_LENGTH_CM) == MAX_LENGTH_CM  # the tallest that is held
        for kind in ("RAISED_BED", "GARDEN_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"):
            for height in (MAX_LENGTH_CM + 0.5, MAX_LENGTH_CM + 2.0, 2e6, 1e300, float("inf")):
                assert soil_surface_cm(kind, height) == 0.0, (kind, height)
                assert standing_base_cm(kind, {"object_height_cm": height}) == 0.0, (kind, height)

    def test_a_rim_lower_than_the_drop_is_soil_at_ground_level(self) -> None:
        assert soil_surface_cm("RAISED_BED", 1.5) == 0.0 and soil_surface_cm("RAISED_BED", 2.0) == 0.0
        assert soil_surface_cm("CONTAINER", 1.5) == 1.5  # no drop to fall below

    @pytest.mark.parametrize(("kind", "metadata", "expected"), [
        ("RAISED_BED", None, 38.0),                             # the type default, 40 cm
        ("RAISED_BED", {"object_height_cm": 75.0}, 73.0),       # an explicit height
        ("CONTAINER", None, 30.0),                              # the default fill height: the soil
        ("CONTAINER_ROUND", {"container_height_cm": 45.0}, 45.0),
        ("WALL_PLANTER", None, 30.0),
        ("GARDEN_BED", None, 0.0),                              # in the ground
        ("GARDEN_BED", {"object_height_cm": 25.0}, 23.0),       # the user raised it
        ("TRELLIS", None, 0.0),                                 # a plant parent that holds no soil
        ("HOUSE", None, 0.0),
        (None, None, 0.0),
    ])
    def test_standing_base(self, kind: str | None, metadata: dict | None, expected: float) -> None:
        assert standing_base_cm(kind, metadata) == expected
