"""The frozen exe's 3D self-test: what it renders and how it judges the frame (L1.2).

``--selftest`` runs in the built exe on a GPU-less release runner; its exit code
is the only channel. So the JUDGE must be right on its own: it is a pure
function of the frame's pixels and is tested here on synthetic frames — a good
one, a blank one, a mirrored one, one without a shadow — with no engine at all.
That it passes on a real render (GPU and WARP, source and frozen) is the render
tier's and the build's job.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import MATERIAL_KINDS, Record, SceneSync
from open_garden_planner.core.scene3d.selection import MITRE_LIMIT, RING_WIDTH_PX
from open_garden_planner.core.shadow_geometry import compute_scene_shadows
from open_garden_planner.ui.view3d.quick3d import selftest
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from open_garden_planner.ui.view3d.quick3d.shots import top_down_pixel
from tests.integration.quick3d_render_support import isolated_env
from tests.unit.test_quick3d_adapter import FakeScene

GROUND = (20, 78, 12)
SHADOW = (8, 26, 6)
BOX = (255, 6, 4)
SWATCH = (150, 12, 6)
GLASS = (60, 60, 14)
LAWN = (12, 30, 150)
RING = (0, 48, 173)          # the canvas's selection blue in linear light (the truth view)
SHADE = (15, 45, 10)         # the 2D shadow drape on the shade layer (L2; measured, GPU and WARP)
LINES = (171, 9, 90)         # the lines overlay's patch: the pin's colour, linear


def _paint(frame: np.ndarray, region: selftest.Region, colour: tuple[int, int, int],
           scale: float, grow_cm: float = 0.0) -> None:
    """Fill the scene-frame rectangle of ``region`` (plus a margin) with ``colour``."""
    height, width = frame.shape[:2]
    half_w, half_h = region.width_cm / 2 + grow_cm, region.depth_cm / 2 + grow_cm
    left, top = top_down_pixel(region.east_cm - half_w, region.north_cm + half_h, selftest.SHOT,
                               (width, height), scale)
    right, bottom = top_down_pixel(region.east_cm + half_w, region.north_cm - half_h, selftest.SHOT,
                                   (width, height), scale)
    frame[round(top):round(bottom), round(left):round(right), :3] = colour


def _paint_screen(frame: np.ndarray, region: selftest.Region, colour: tuple[int, int, int],
                  scale: float, grow_cm: float = 0.0) -> None:
    """A screen door of ``colour`` over ``region``: every second pixel of every second row
    (a quarter, as the 4 x 4 dither keeps at the X-ray opacity)."""
    height, width = frame.shape[:2]
    half_w, half_h = region.width_cm / 2 + grow_cm, region.depth_cm / 2 + grow_cm
    left, top = top_down_pixel(region.east_cm - half_w, region.north_cm + half_h, selftest.SHOT,
                               (width, height), scale)
    right, bottom = top_down_pixel(region.east_cm + half_w, region.north_cm - half_h, selftest.SHOT,
                                   (width, height), scale)
    frame[round(top):round(bottom):2, round(left):round(right):2, :3] = colour


def _good_frame(scale: float = 1.0) -> np.ndarray:
    """What the self-test scene looks like from above, painted by hand."""
    width, height = round(selftest.SIZE[0] * scale), round(selftest.SIZE[1] * scale)
    frame = np.zeros((height, width, 4), np.uint8)
    frame[..., :3] = GROUND
    frame[..., 3] = 255
    _paint(frame, selftest.REGIONS["shadow"], SHADOW, scale, grow_cm=6.0)
    # the ring: RING_WIDTH_PX outside the selected swatch's footprint, ground inside it
    _paint(frame, selftest.RING_REGION, RING, scale,
           grow_cm=RING_WIDTH_PX / selftest.SHOT.px_per_cm)
    _paint(frame, selftest.RING_REGION, GROUND, scale)
    for kind in selftest.SWATCH_KINDS:
        _paint(frame, selftest.REGIONS[kind], GLASS if kind == "glass" else SWATCH, scale, grow_cm=4.0)
    _paint(frame, selftest.REGIONS["box"], BOX, scale, grow_cm=10.0)
    _paint(frame, selftest.REGIONS["lawn"], LAWN, scale, grow_cm=6.0)
    _paint(frame, selftest.REGIONS["shade"], SHADE, scale, grow_cm=6.0)
    _paint(frame, selftest.REGIONS["lines"], LINES, scale, grow_cm=4.0)
    for item_id in selftest.FADED:
        _paint_screen(frame, selftest.REGIONS[item_id], BOX, scale, grow_cm=4.0)
    return frame


def _rendered(rgba: np.ndarray, **extra: object) -> selftest.Rendered:
    """A self-test render as ``_render`` returns it for a good run: the frame, the
    device, and a baked ground of ``GROUND_TILES`` tiles; ``extra`` overrides."""
    fields: dict[str, object] = {"ground_tiles": selftest.GROUND_TILES,
                                 "ground_tiles_painted": selftest.GROUND_TILES, **extra}
    return selftest.Rendered(rgba, 1.0, "Direct3D11", "Microsoft Basic Render Driver", 321.0,
                             {"error": 0}, **fields)  # type: ignore[arg-type]


class TestJudge:
    @pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
    def test_a_good_frame_passes(self, scale: float) -> None:
        assert selftest.judge_frame(_good_frame(scale), device_pixel_ratio=scale) == []

    def test_a_blank_frame_fails_every_content_check(self) -> None:
        frame = _good_frame()
        frame[..., :3] = (207, 226, 242)  # the bare sky colour: nothing was drawn
        problems = selftest.judge_frame(frame)
        # ground, box, shadow, each swatch, the lawn, the shade, each screen door, the
        # lines, the ring
        assert len(problems) == 7 + len(selftest.FADED) + len(selftest.SWATCH_KINDS)
        assert problems[0].startswith("the ground is not lit meadow")
        assert problems[1].startswith("the box is not there")

    def test_a_frame_of_bare_ground_fails(self) -> None:
        frame = _good_frame()
        frame[..., :3] = GROUND  # the ground rendered, no item did
        problems = selftest.judge_frame(frame)
        assert problems[0].startswith("the box is not there")       # the ground itself is fine
        assert problems[1].startswith("the shadow is missing")
        assert problems[-1].startswith("the selection ring did not draw round the roof swatch")
        # … the lawn, the shade, each screen door, the lines and the ring
        assert len(problems) == 6 + len(selftest.FADED) + len(selftest.SWATCH_KINDS)
        assert any(p.startswith("the baked ground does not show the lawn") for p in problems)

    def test_a_drape_that_brightens_the_ground_fails(self) -> None:
        """L2: the blend that let the window's white through the frame's alpha — measured
        on the engine as rgb(79, 107, 75) over a meadow of rgb(25, 73, 11)."""
        frame = _good_frame()
        _paint(frame, selftest.REGIONS["shade"], (79, 107, 75), 1.0, grow_cm=6.0)
        problems = selftest.judge_frame(frame)
        assert len(problems) == 1 and problems[0].startswith("the shadow drape did not darken")

    @pytest.mark.parametrize("drawn", ["whole", "not at all"])
    def test_a_faded_cube_that_is_no_screen_door_fails(self, drawn: str) -> None:
        """L2.4: the X-ray occluder is a screen door — a cube drawn whole (the shader's
        discard did not run) or not at all (it discarded everything) fails."""
        frame = _good_frame()
        _paint(frame, selftest.REGIONS["screen"], BOX if drawn == "whole" else GROUND, 1.0,
               grow_cm=4.0)
        problems = selftest.judge_frame(frame)
        assert len(problems) == 1 and problems[0].startswith("the faded vc cube is not a screen door")

    def test_a_missing_overlay_fails(self) -> None:
        frame = _good_frame()
        _paint(frame, selftest.REGIONS["lines"], GROUND, 1.0, grow_cm=4.0)
        problems = selftest.judge_frame(frame)
        assert len(problems) == 1 and problems[0].startswith("the lines overlay did not draw")

    def test_the_overlay_patches_lie_clear_of_the_box_and_its_shadow(self) -> None:
        from open_garden_planner.core.shadow_geometry import shadow_polygon

        shadow = shadow_polygon(selftest._ring(100.0, 100.0), 100.0, selftest.SUN.elevation_deg,
                                selftest.SUN.azimuth_deg)
        reach = max(x for polygon in shadow for x, _y in polygon) + selftest._BOX.east_cm
        for patch in (selftest.DRAPE_PATCH, selftest.LINES_PATCH, selftest.FADED_PATCH,
                      selftest.FADED_FOLIAGE_PATCH, selftest.FADED_WATER_PATCH):
            assert patch.east_cm - patch.width_cm / 2 > reach
            assert patch.north_cm - patch.depth_cm / 2 > 0.0
            assert patch.north_cm + patch.depth_cm / 2 < selftest.GROUND.depth_cm

    def test_a_ring_that_did_not_draw_fails(self) -> None:
        """The ring's shader failed, or nothing was selected: every material is there,
        the band round the selected swatch is bare ground."""
        frame = _good_frame()
        _paint(frame, selftest.RING_REGION, GROUND, 1.0,
               grow_cm=RING_WIDTH_PX / selftest.SHOT.px_per_cm)
        _paint(frame, selftest.REGIONS[selftest.SELECTED[0]], SWATCH, 1.0, grow_cm=4.0)
        (problem,) = selftest.judge_frame(frame)
        assert problem == ("the selection ring did not draw round the roof swatch: 0% of its "
                           "band is in the ring's colour")

    def test_a_ring_drawn_inside_the_footprint_is_not_the_ring(self) -> None:
        """A band that is there but in the wrong place (depth-tested into the solid, or
        on the wrong side of the outline) does not pass for the ring."""
        frame = _good_frame()
        _paint(frame, selftest.RING_REGION, GROUND, 1.0,
               grow_cm=RING_WIDTH_PX / selftest.SHOT.px_per_cm)
        _paint(frame, selftest.RING_REGION, RING, 1.0, grow_cm=-1.0)
        _paint(frame, selftest.REGIONS[selftest.SELECTED[0]], SWATCH, 1.0, grow_cm=4.0)
        problems = selftest.judge_frame(frame)
        assert [p for p in problems if "selection ring" in p], problems

    def test_a_missing_shadow_fails(self) -> None:
        """The sun is switched off, or the shadow map is broken: lit box, no shadow."""
        frame = _good_frame()
        _paint(frame, selftest.REGIONS["shadow"], GROUND, 1.0, grow_cm=6.0)
        (problem,) = selftest.judge_frame(frame)
        assert problem.startswith("the shadow is missing: the ground north-east of the box")

    @pytest.mark.parametrize("flip", ["east-west", "north-south"])
    def test_a_mirrored_frame_fails(self, flip: str) -> None:
        """The shadow lies north-east of the box and the swatches south of it: a
        mirrored frame cannot have both where they belong."""
        frame = _good_frame()
        mirrored = frame[:, ::-1] if flip == "east-west" else frame[::-1]
        assert selftest.judge_frame(np.ascontiguousarray(mirrored)) != []

    @pytest.mark.parametrize("kind", selftest.SWATCH_KINDS)
    def test_a_material_that_did_not_draw_fails(self, kind: str) -> None:
        frame = _good_frame()
        _paint(frame, selftest.REGIONS[kind], GROUND, 1.0, grow_cm=4.0)
        (problem,) = selftest.judge_frame(frame)
        assert kind in problem

    def test_a_ground_that_was_not_baked_fails(self) -> None:
        """The lawn is a FLAT item: only the ground bake puts it in the frame. Bare
        ground where it lies — a sink that dropped the tiles, a baker that painted
        nothing — fails."""
        frame = _good_frame()
        _paint(frame, selftest.REGIONS["lawn"], GROUND, 1.0, grow_cm=6.0)
        (problem,) = selftest.judge_frame(frame)
        assert problem.startswith("the baked ground does not show the lawn")

    def test_a_frame_of_the_wrong_size_fails_before_any_pixel_is_read(self) -> None:
        (problem,) = selftest.judge_frame(np.zeros((30, 40, 4), np.uint8))
        assert "40x30" in problem and "160x120" in problem


def _footprint(record: Record) -> list[tuple[float, float]]:
    """A self-test item's footprint in scene coordinates (none of them is turned)."""
    return [(record.transform.east_cm + x, record.transform.north_cm + y)
            for x, y in record.footprints[0]]


def _inside(polygons: list[list[tuple[float, float]]], x: float, y: float) -> bool:
    """Even-odd point-in-polygon over a set of rings."""
    hit = False
    for polygon in polygons:
        count = len(polygon)
        for index in range(count):
            (x1, y1), (x2, y2) = polygon[index], polygon[(index + 1) % count]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def _samples(region: selftest.Region) -> list[tuple[float, float]]:
    """The corners, edge midpoints and centre of a region."""
    return [(region.east_cm + dx * region.width_cm / 2, region.north_cm + dy * region.depth_cm / 2)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


class TestScene:
    def test_the_scene_uses_every_material_kind(self) -> None:
        """One item per material kind: every shader the bundle ships compiles in the
        self-test, so a missing or broken shader file fails the release, not a user."""
        engine = FakeScene()
        sync = SceneSync(Quick3DSink(engine), selftest.registry(), validate=True)
        sync.apply(selftest.records())
        assert {part.spec.kind for part in engine.parts} == MATERIAL_KINDS
        # one part per kind, and one faded cube per screen-door shader (L2.4)
        assert sync.failures == {} and len(engine.parts) == len(MATERIAL_KINDS) + 3
        assert {selftest.records()[item_id].params["material_kind"] for item_id in
                selftest.FADED} == {"vc", "foliage", "water"}

    def test_every_region_lies_inside_the_frame(self) -> None:
        width, height = selftest.SIZE
        for name, region in selftest.REGIONS.items():
            for x, y in _samples(region):
                px, py = top_down_pixel(x, y, selftest.SHOT, (width, height))
                assert 1 <= px <= width - 1 and 1 <= py <= height - 1, name

    def test_each_item_patch_is_well_inside_its_item(self) -> None:
        records = selftest.records()
        for name in ("box", *selftest.SWATCH_KINDS):
            ring = _footprint(records[name])
            low_x, high_x = min(x for x, _ in ring), max(x for x, _ in ring)
            low_y, high_y = min(y for _, y in ring), max(y for _, y in ring)
            for x, y in _samples(selftest.REGIONS[name]):
                assert low_x + 5 <= x <= high_x - 5 and low_y + 5 <= y <= high_y - 5, name

    def test_the_shadow_patch_is_inside_the_analytic_2d_shadow(self) -> None:
        """Where the judge looks for the shadow is where ``core/shadow_geometry`` — the
        2D overlay's code — puts the box's shadow for the self-test's sun, and it is
        outside the box. Not a guess."""
        box = selftest.records()["box"]
        ring = _footprint(box)
        shadow = compute_scene_shadows([(ring, box.height_cm)], selftest.SUN.elevation_deg,
                                       selftest.SUN.azimuth_deg)
        for x, y in _samples(selftest.REGIONS["shadow"]):
            assert _inside(shadow, x, y), (x, y)
            assert not _inside([ring], x, y), (x, y)

    def test_the_lit_ground_patch_is_in_no_shadow_and_on_no_item(self) -> None:
        records = selftest.records()
        rings = [_footprint(record) for record in records.values()]
        shadows = compute_scene_shadows(
            [(ring, record.height_cm) for ring, record in zip(rings, records.values(), strict=True)],
            selftest.SUN.elevation_deg, selftest.SUN.azimuth_deg)
        for x, y in _samples(selftest.REGIONS["lit ground"]):
            assert not _inside(shadows, x, y), (x, y)
            assert not any(_inside([ring], x, y) for ring in rings), (x, y)

    def test_the_lawn_is_flat_and_its_patch_lies_inside_it_in_no_shadow(self) -> None:
        """The lawn has no height (no builder makes a solid: the ground bake paints
        it), its patch is well inside it, and no item and no shadow covers that patch."""
        records = selftest.records()
        lawn = records["lawn"]
        assert lawn.height_cm is None and selftest.registry().builder_for(lawn.kind)(lawn) == ()
        ring = _footprint(lawn)
        low_x, high_x = min(x for x, _ in ring), max(x for x, _ in ring)
        low_y, high_y = min(y for _, y in ring), max(y for _, y in ring)
        solids = [(_footprint(record), record.height_cm) for record in records.values()
                  if record.height_cm is not None]
        shadows = compute_scene_shadows(solids, selftest.SUN.elevation_deg, selftest.SUN.azimuth_deg)
        for x, y in _samples(selftest.REGIONS["lawn"]):
            assert low_x + 5 <= x <= high_x - 5 and low_y + 5 <= y <= high_y - 5
            assert not _inside(shadows, x, y), (x, y)
            assert not any(_inside([ring], x, y) for ring, _height in solids), (x, y)

    def test_the_ground_has_the_tiles_the_selftest_expects(self) -> None:
        """12 tiles: 128-px tiles at 1 px/cm over the 400 x 300 cm plan."""
        from open_garden_planner.core.scene3d import GroundGrid

        grid = GroundGrid.for_plan(selftest.GROUND.width_cm, selftest.GROUND.depth_cm,
                                   tile_px=selftest.GROUND_TILE_PX)
        assert len(list(grid.tile_keys())) == selftest.GROUND_TILES

    def test_the_selected_swatch_is_in_the_scene_and_its_ring_disturbs_no_other_check(self) -> None:
        """The ring's shader compiles only when something is selected (L1.8). The band the
        judge looks for it in — and all a mitred corner can reach — lies inside the frame
        and clear of every patch the other checks sample."""
        (selected,) = selftest.SELECTED
        assert selected in selftest.records() and selected in selftest.SWATCH_KINDS
        region = selftest.RING_REGION
        footprint = _footprint(selftest.records()[selected])
        assert (min(x for x, _ in footprint), max(x for x, _ in footprint)) == (
            region.east_cm - region.width_cm / 2, region.east_cm + region.width_cm / 2)
        reach = RING_WIDTH_PX * MITRE_LIMIT / selftest.SHOT.px_per_cm     # cm
        low_x, high_x = region.east_cm - region.width_cm / 2 - reach, region.east_cm + region.width_cm / 2 + reach
        low_y, high_y = region.north_cm - region.depth_cm / 2 - reach, region.north_cm + region.depth_cm / 2 + reach
        assert low_x > 0.0 and high_x < selftest.GROUND.width_cm
        assert low_y > 0.0 and high_y < selftest.GROUND.depth_cm
        for name, patch in selftest.REGIONS.items():
            if name == selected:
                continue   # its own patch is inside the footprint (the test above)
            for x, y in _samples(patch):
                assert not (low_x <= x <= high_x and low_y <= y <= high_y), name
        band = selftest.ring_band((selftest.SIZE[1], selftest.SIZE[0]), 1.0)
        side = region.width_cm * selftest.SHOT.px_per_cm
        assert int(band.sum()) == pytest.approx(4 * RING_WIDTH_PX * (side + RING_WIDTH_PX), rel=0.05)

    def test_the_render_selects_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """…and ``_render`` really asks for the ring (not a default of nothing)."""
        from open_garden_planner.ui.view3d.quick3d import offscreen

        asked: dict[str, object] = {}

        def render(*_arguments: object, **options: object) -> object:
            asked.update(options)
            raise RuntimeError("far enough")

        monkeypatch.setattr(offscreen, "render_records", render)
        with pytest.raises(RuntimeError, match="far enough"):
            selftest._render(lambda *_a, **_k: None, None)  # noqa: SLF001
        assert asked["selected"] == ("roof",)

    def test_everything_stands_on_the_plan_rectangle(self) -> None:
        for record in selftest.records().values():
            for x, y in _footprint(record):
                assert 0.0 < x < selftest.GROUND.width_cm and 0.0 < y < selftest.GROUND.depth_cm


class TestRun:
    def test_an_import_failure_is_reported_and_fails(self, monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path) -> None:
        import importlib

        real = importlib.import_module

        def broken(name: str, *args: object, **kwargs: object) -> object:
            if name == "PyQt6.QtQuick3D":
                raise ImportError("DLL load failed while importing QtQuick3D")
            return real(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(importlib, "import_module", broken)
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        assert any(line.startswith("  FAIL import PyQt6.QtQuick3D") for line in result.lines)
        assert not any("frame" in line and "OK" in line for line in result.lines)  # nothing rendered

    def test_a_render_error_is_reported_and_fails(self, monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path) -> None:
        def explode(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("2 Qt error(s) during the render — QSpirvCompiler: Failed to parse shader")

        monkeypatch.setattr(selftest, "_render", explode)
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        (failure,) = [line for line in result.lines if "FAIL" in line]
        assert "QSpirvCompiler" in failure and "RuntimeError" in failure
        assert "FAIL" in (tmp_path / "selftest.log").read_text(encoding="utf-8")

    def test_a_frame_the_judge_rejects_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        blank = _good_frame()
        blank[..., :3] = (207, 226, 242)
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(blank))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok and any("FAIL" in line and "box" in line for line in result.lines)

    def test_a_builder_that_failed_fails_the_selftest_even_if_the_frame_looks_right(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Review P2-4: the pipeline CONTAINS a failed builder — the item is then in the
        frame without a solid. ``render_records`` names it; the self-test must look."""
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(_good_frame(),
            build_failures=("water: ValueError: degenerate footprint",)))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        (failure,) = [line for line in result.lines if "FAIL" in line]
        assert "the builder of water: ValueError: degenerate footprint failed" in failure

    def test_a_message_from_another_thread_fails_the_selftest_even_if_the_frame_looks_right(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Review round 3, P2-10. The recorder may be installed around the self-test's frame
        only because every message of it arrives on the rendering thread. The render tier
        asserted that; the self-test dropped the number — and a frozen exe on a runner is
        where it must hold."""
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(_good_frame(),
            other_threads=2))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        (failure,) = [line for line in result.lines if "FAIL" in line]
        assert "2 Qt message(s) of the render arrived on another thread" in failure

    def test_the_render_hands_the_thread_count_to_the_judge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """…and ``_render`` really takes it from the frame (not a default of 0)."""
        from types import SimpleNamespace

        from open_garden_planner.ui.view3d.quick3d import offscreen

        frame = SimpleNamespace(rgba=_good_frame, device_pixel_ratio=1.0, graphics_api="Direct3D11",
                                adapter="x", open_ms=1.0, build_failures={},
                                qt={"counts": {"error": 0}, "other_threads": 3}, sky_builds=0,
                                ground_tiles=selftest.GROUND_TILES, ground_failure=None)
        monkeypatch.setattr(offscreen, "render_records", lambda *_a, **_k: frame)
        assert selftest._render(lambda *_a, **_k: None, None).other_threads == 3  # noqa: SLF001

    @pytest.mark.parametrize(("extra", "said"), [
        ({"ground_tiles": 0}, "the ground shows 0 tiles, expected 12"),
        ({"ground_tiles": 1}, "the ground shows 1 tiles, expected 12"),
        ({"ground_failure": ("MemoryError", "no image")},
         "the ground could not be baked: MemoryError: no image"),
    ], ids=["no tiles", "one tile", "a bake that raised"])
    def test_a_ground_that_was_not_baked_fails_the_selftest_even_if_the_frame_looks_right(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path, extra: dict[str, object],
            said: str) -> None:
        """L1.5: the frozen exe bakes its ground with the product's baker — the tile
        upload and the multi-pass path. A ground of other tiles than the grid's, or a
        bake that raised, fails whatever the pixels say."""
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(_good_frame(), **extra))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        (failure,) = [line for line in result.lines if "FAIL" in line]
        assert said in failure

    def test_the_render_bakes_with_the_products_baker_in_passes(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_render`` hands ``render_records`` the product's ``GroundBaker`` with a
        budget of 0 and 128-px tiles, and reports what it painted."""
        from types import SimpleNamespace

        from open_garden_planner.ui.view3d.ground_bake import GroundBaker
        from open_garden_planner.ui.view3d.quick3d import offscreen

        seen: dict[str, object] = {}

        def fake(*_args: object, **kwargs: object) -> object:
            baker = kwargs["ground_baker"]
            assert isinstance(baker, GroundBaker)
            seen.update(budget=baker.budget_s, grid=None)
            baker.tiles_painted = 12  # what a full run of passes paints (the render tier runs one)
            return SimpleNamespace(rgba=_good_frame, device_pixel_ratio=1.0,
                                   graphics_api="Direct3D11", adapter="x", open_ms=1.0,
                                   build_failures={}, qt={"counts": {}, "other_threads": 0},
                                   ground_tiles=12, ground_failure=None, sky_builds=0)

        monkeypatch.setattr(offscreen, "render_records", fake)
        rendered = selftest._render(lambda *_a, **_k: None, None)  # noqa: SLF001
        assert seen["budget"] == 0.0 and selftest.GROUND_TILE_PX == 128
        assert (rendered.ground_tiles, rendered.ground_tiles_painted) == (12, 12)

    def test_a_sky_in_the_selftest_fails_it_even_if_the_frame_looks_right(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """L1.4, gate G8. The self-test runs where there is no GPU (``release.yml``, on
        WARP), and there ONE sky's light probe costs longer than the whole test may
        take (9-13 s on the dev box's WARP, 40-85 s on a CI runner). It renders the
        plain background and the flat fill; a sky that crept in is a FAIL, not a slow
        release."""
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: selftest.Rendered(
            _good_frame(), 1.0, "Direct3D11", "Microsoft Basic Render Driver", 321.0, {"error": 0},
            ground_tiles=selftest.GROUND_TILES, sky_builds=1))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert not result.ok
        (failure,) = [line for line in result.lines if "FAIL" in line]
        assert "built 1 sky texture(s)" in failure

    def test_the_selftest_asks_for_no_sky_and_reads_the_count_from_the_frame(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from open_garden_planner.ui.view3d.quick3d import offscreen

        asked: dict[str, object] = {}

        def render(*_arguments: object, **options: object) -> SimpleNamespace:
            asked.update(options)
            return SimpleNamespace(rgba=_good_frame, device_pixel_ratio=1.0, graphics_api="x",
                                   adapter="x", open_ms=1.0, build_failures={}, sky_builds=2,
                                   qt={"counts": {}, "other_threads": 0},
                                   ground_tiles=selftest.GROUND_TILES, ground_failure=None)

        monkeypatch.setattr(offscreen, "render_records", render)
        assert selftest._render(lambda *_a, **_k: None, None).sky_builds == 2  # noqa: SLF001
        assert not asked.get("sky_light", False) and not asked.get("prefer_software", False)
        assert "look" not in asked, "the self-test renders the host's own neutral day"

    def test_with_the_callers_log_it_arms_no_watchdog_and_leaves_the_log_open(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """``main`` bounds the WHOLE ``--selftest`` with one watchdog and one log
        (``faulthandler`` has ONE timer per process: a second watchdog in here would
        replace the outer one, and cancel it on the way out)."""
        from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog

        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(_good_frame()))
        log = RenderLog(tmp_path / "whole.log", mirror=False)
        try:
            result = selftest.run_selftest(log=log, watchdog_s=None)
            log("after", note="the caller's log is still open")
        finally:
            log.close()
        text = (tmp_path / "whole.log").read_text(encoding="utf-8")
        assert result.ok and result.log_path == tmp_path / "whole.log"
        assert "[watchdog]" not in text and "[selftest_done] result=PASS" in text
        assert "[after]" in text

    def test_a_good_frame_passes_and_names_the_device(self, monkeypatch: pytest.MonkeyPatch,
                                                      tmp_path) -> None:
        monkeypatch.setattr(selftest, "_render", lambda *_a, **_k: _rendered(_good_frame()))
        result = selftest.run_selftest(tmp_path / "selftest.log")
        assert result.ok, result.lines
        assert all(line.startswith("  OK  ") for line in result.lines)
        assert any("on Direct3D11 / Microsoft Basic Render Driver" in line for line in result.lines)
        log = (tmp_path / "selftest.log").read_text(encoding="utf-8")
        assert "watchdog" in log and "PASS" in log

    def test_the_log_path_can_come_from_the_environment(self, monkeypatch: pytest.MonkeyPatch,
                                                        tmp_path) -> None:
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(tmp_path / "from-env.log"))
        assert selftest.default_log_path() == tmp_path / "from-env.log"

    def test_the_default_log_lives_in_the_apps_one_log_directory(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Beside ``app.log`` and ``crash.log`` — through the ONE helper that resolves that
        directory, not a second path computation."""
        from open_garden_planner.core import logging_config

        monkeypatch.delenv("OGP_SELFTEST_LOG", raising=False)
        home = Path("per-user-app-data") / "cofade" / "Open Garden Planner"
        monkeypatch.setattr(logging_config, "resolve_log_dir", lambda: home)
        assert selftest.default_log_path() == home / "OpenGardenPlanner-selftest-3d.log"


def test_nothing_in_the_engine_package_writes_into_the_temp_directory() -> None:
    """CWE-377: a predictable file name in the shared temp directory can be pre-created
    or symlinked by another local user (``/tmp`` on Linux). The self-test log first
    went there; it now goes into the app's per-user log directory, and no module of
    the package touches ``tempfile``. ``main.py``, which runs the self-test, may import
    it since master's A1 block (#453) — for ``tempfile.TemporaryDirectory``, whose name
    is random and whose directory is the user's own — but neither file may reach for a
    predictable name (``gettempdir`` / ``mktemp`` / ``tempdir``)."""
    import ast

    package = Path(selftest.__file__).resolve().parent
    sources = [*sorted(package.glob("*.py")), package.parents[2] / "main.py"]
    assert len(sources) >= 12
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        if path.name != "main.py":
            assert "tempfile" not in imported, path.name
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not names & {"gettempdir", "mktemp", "tempdir"}, path.name


_DEFAULT_LOG = textwrap.dedent("""
    import sys
    import tempfile
    from pathlib import Path

    from PyQt6.QtCore import QStandardPaths

    profile = Path(sys.argv[2]).resolve()
    # BEFORE anything is created: does Qt resolve per-user paths inside the profile this
    # test handed us? (writableLocation creates nothing.) If not, stop — never write
    # into a real profile.
    asked = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)).resolve()
    if profile not in asked.parents:
        print("NOT_REDIRECTED", asked)
        sys.exit(3)

    import open_garden_planner.app.settings as app_settings
    app_settings.ORGANIZATION_NAME = "cofade_test"
    app_settings.APPLICATION_NAME = sys.argv[1]

    import open_garden_planner.main as ogp_main
    from open_garden_planner.ui.view3d.quick3d import selftest

    def no_engine(*_args, **_kwargs):
        raise RuntimeError("stand-in: this child renders nothing")

    selftest._render = no_engine
    code = ogp_main._run_selftest()
    log = selftest.default_log_path()
    print("LOG", log)
    print("EXISTS", log.is_file())
    print("UNDER_TEMP_ROOT", log.resolve().parent == Path(tempfile.gettempdir()).resolve())
    print("CODE", code)
""")


def test_the_selftest_writes_its_log_beside_the_apps_logs_not_into_temp(tmp_path: Path) -> None:
    """End to end, in a child, with the app's REAL log-directory helper:
    ``main._run_selftest`` names the application before anything resolves a path, and
    the log lands in ``<per-user app data>/<organisation>/<application>/`` — never
    under a predictable name directly in the shared temp directory (CWE-377).

    Review round 2, P2-8: this test used to run in the developer's real profile under a
    throwaway identity, and left ``%APPDATA%\\cofade_test\\`` behind. The child now gets
    a user profile of the test process's own (``isolated_env``); it first ASKS Qt where
    per-user data would go — which creates nothing — and stops unless the answer is
    inside that profile. Where a platform's Qt does not follow the environment, the
    test skips instead of writing."""
    from tests.integration.quick3d_render_support import session_profile

    identity = f"Open Garden Planner Selftest Probe {os.getpid()}"
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    env.pop("OGP_SELFTEST_LOG", None)
    # where Qt's per-user data root is inside the test's profile (Windows / Linux)
    root = session_profile() if sys.platform == "win32" else tmp_path
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _DEFAULT_LOG, identity, str(root)], env=env,
        capture_output=True, text=True, timeout=170, cwd=tmp_path)
    if proc.returncode == 3:
        pytest.skip("Qt's per-user paths do not follow the environment here "
                    f"({proc.stdout.strip()}): the test will not write into a real profile")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-2000:]
    out = dict(line.split(" ", 1) for line in proc.stdout.splitlines()
               if line.startswith(("LOG ", "EXISTS ", "UNDER_TEMP_ROOT ", "CODE ")))
    log = Path(out["LOG"])
    assert log.name == "OpenGardenPlanner-selftest-3d.log"
    assert log.parent.name == identity and log.parent.parent.name == "cofade_test"
    assert root.resolve() in log.resolve().parents, "the log is inside the test's own profile"
    assert out["EXISTS"] == "True" and out["UNDER_TEMP_ROOT"] == "False"
    assert out["CODE"] == "1"  # the stand-in render failed: the verdict is still honest
    assert f"3D self-test log: {log}" in proc.stdout
    assert "FAIL" in log.read_text(encoding="utf-8")


_HANG = textwrap.dedent("""
    import sys
    import time
    from pathlib import Path
    from open_garden_planner.ui.view3d.quick3d import selftest

    def stuck(*_args, **_kwargs):
        time.sleep(120)  # a render that never comes back

    selftest._render = stuck
    result = selftest.run_selftest(Path(sys.argv[1]), watchdog_s=1.5)
    print("returned", result.ok, flush=True)
""")


def test_a_hang_becomes_exit_code_1_with_the_stack_in_the_log(tmp_path: Path) -> None:
    """The release runner must never sit in a hung self-test: the watchdog dumps every
    thread's stack into the log and exits the process with code 1 — in a child here,
    because that exit is real."""
    log = tmp_path / "selftest.log"
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _HANG, str(log)], env=env, capture_output=True, text=True,
        timeout=100)
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    assert "returned" not in proc.stdout, "the hang must end the process, not return a verdict"
    text = log.read_text(encoding="utf-8")
    assert "[watchdog] armed=True seconds=1.5 what=the 3D self-test frame" in text
    # the reason in words, BEFORE the exit (review P1-4) — then faulthandler's own dump
    assert "[watchdog] fired=True" in text
    assert "the 3D self-test frame did not finish within 1.5 s" in text
    assert text.index("[watchdog] fired=True") < text.index("Timeout (0:00:01")
    assert "in stuck" in text and "run_selftest" in text


_NOWHERE = textwrap.dedent("""
    import sys
    import time
    from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog, watchdog

    sys.stderr = None            # a windowed frozen exe has none
    log = RenderLog(None, mirror=False)   # … and its log could not be opened
    with watchdog(1.0, log, what="a run without any output"):
        time.sleep(120)
    print("returned", flush=True)
""")


def test_a_hang_ends_the_process_even_with_nowhere_to_write(tmp_path: Path) -> None:
    """No log file and no stderr: the watchdog used to switch itself OFF there ("nothing
    to dump into") — an unbounded self-test in exactly the build that has no other
    channel. Now the stacks are lost and the exit is not."""
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _NOWHERE], env=env, capture_output=True, text=True, timeout=100,
        cwd=tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    assert "returned" not in proc.stdout


# ── the second line of defence: a process that ends this one from outside ────
#
# Review round 2, P2-6. In a process deadlocked inside Qt and the graphics driver the
# watchdog above wrote its dump and the process STAYED ALIVE (every run): on Windows
# ``_exit`` is ``ExitProcess``, which waits in a DLL's detach code. That real deadlock
# is the render tier's control (``test_the_supervised_watchdog_ends_the_deadlock``);
# here the first line of defence is switched off instead, so that only the second one
# can end the child — on every machine, without a GPU.
#
# Review round 3: a supervisor acts for ONE block of its own PARENT, on validated
# arguments. Every test that starts one runs in a child process of its own — a
# supervisor that got something wrong must never be able to reach the test runner.

windows_only = pytest.mark.skipif(sys.platform != "win32",
                                  reason="the supervising process is Windows-only (runlog.py)")
NONCE = "0123456789abcdef0123456789abcdef"

_SUPERVISED = textwrap.dedent("""
    import faulthandler
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path
    from open_garden_planner.ui.view3d.quick3d import runlog

    mode, log_path = sys.argv[1], Path(sys.argv[2])
    runlog.GRACE_S = 2.0
    log = runlog.RenderLog(log_path, mirror=False)
    if mode == "stuck":
        # the in-process watchdog cannot end this process — as in the measured deadlock
        faulthandler.dump_traceback_later = lambda *args, **kwargs: None
        with runlog.watchdog(1.5, log, what="the supervised block", supervised=True):
            time.sleep(120)
    elif mode == "in-time":
        # a block that is over before the supervising process is even up: the supervisor
        # must not end a process that finished its block and simply lives on
        with runlog.watchdog(1.5, log, what="the supervised block", supervised=True) as armed:
            pass
        print("SUPERVISOR_EXIT", armed.supervisor_exit, armed.supervised, flush=True)
        time.sleep(6.0)   # past the deadline and the grace period
    elif mode == "released":
        supervisor = runlog.start_supervisor(60.0, log_path, "a released block")
        print("STARTED", supervisor is not None, flush=True)
        time.sleep(1.5)   # the supervisor is up and waiting
        print("WAITING", supervisor.process.poll() is None, flush=True)
        supervisor.release()
        print("GONE", supervisor.wait(30.0), flush=True)
    elif mode == "two-blocks":
        # The reviewer's sequence, raw (no waiting for A's supervisor): block A is over at
        # once, block B begins before A's supervising process is up. With ONE event name
        # per process, A's late supervisor found B's event, took it for its own, and
        # terminated the healthy block 2 s later.
        first = runlog.start_supervisor(2.0, log_path, "block A")
        first.release()
        second = runlog.start_supervisor(60.0, log_path, "block B")
        time.sleep(5.0)   # block B is healthy, and longer than A's deadline
        print("B_ALIVE_AFTER_A_DEADLINE", flush=True)
        second.release()
        print("EXITS", first.wait(30.0), second.wait(30.0), flush=True)
    elif mode == "two-watchdogs":
        # the same through the public door: two supervised blocks, one after the other
        with runlog.watchdog(1.0, log, what="block A", supervised=True) as a:
            pass
        with runlog.watchdog(30.0, log, what="block B", supervised=True) as b:
            time.sleep(5.0)
        print("EXITS", a.supervisor_exit, b.supervisor_exit, flush=True)
    elif mode == "left-at-once":
        # The reviewer's gap (round 4, P2-1): the block hands its supervisor a creation
        # time that is not the one Windows reports. The supervisor leaves AT ONCE, while
        # the block still runs — and used to say 0, like one that did its job.
        real_created = runlog._created
        runlog._created = lambda k32, handle: real_created(k32, handle) + 1
        with runlog.watchdog(20.0, log, what="the supervised block", supervised=True) as armed:
            time.sleep(1.5)
            print("DURING", armed.supervisor.process.poll(), flush=True)
        print("AFTER", armed.supervisor_exit, armed.supervised, "|", armed.gap, flush=True)
    elif mode == "arming-fails":
        # Round 4, P2-2: the supervising process is started — and then arming fails.
        started = []
        real_start = runlog.start_supervisor
        runlog.start_supervisor = lambda *a: started.append(real_start(*a)) or started[-1]
        real_arm = faulthandler.dump_traceback_later

        def cannot_arm(*_args, **_kwargs):
            raise RuntimeError("unable to start watchdog thread")

        faulthandler.dump_traceback_later = cannot_arm
        try:
            with runlog.watchdog(3.0, log, what="the block that cannot be armed", supervised=True):
                print("THE BLOCK RAN", flush=True)
        except RuntimeError as error:
            print("RAISED", error, flush=True)
        faulthandler.dump_traceback_later = real_arm
        print("ARMED", [item.what for item in runlog._ARMED], flush=True)
        print("STRAY", started[0].process.poll() is None, flush=True)
        with runlog.watchdog(30.0, log, what="the next block", supervised=True) as armed:
            time.sleep(1.0)
        print("NEXT", armed.supervisor_exit, armed.supervised, flush=True)
        time.sleep(6.5)   # past the first block's deadline and grace period: nobody ends us
    elif mode == "wrong-creation-time":
        # Our own child, the right pid, the right event — and a creation time that is not
        # ours: a process that reused the pid. Only that check stands between it and us.
        k32 = runlog._kernel32()
        created = runlog._created(k32, k32.GetCurrentProcess()) + 1
        nonce = "0123456789abcdef0123456789abcdef"
        event = k32.CreateEventW(None, True, False, runlog._event_name(os.getpid(), created, nonce))
        helper = subprocess.Popen([*runlog.self_command(), str(os.getpid()), str(created), nonce,
                                   "1", "-", "what:not ours"])
        print("HELPER", helper.wait(timeout=30), flush=True)
        time.sleep(2.0)
    elif mode == "no-event":
        # Our own child, the right pid, the right creation time — and no release event of
        # that name: not a block it can find. It must not wait on the process alone (it
        # would end us 1 s from now), and it must not say that it supervised.
        k32 = runlog._kernel32()
        created = runlog._created(k32, k32.GetCurrentProcess())
        helper = subprocess.Popen([*runlog.self_command(), str(os.getpid()), str(created),
                                   "fedcba9876543210fedcba9876543210", "1", "-", "what:no such block"])
        print("HELPER", helper.wait(timeout=30), flush=True)
        time.sleep(3.0)   # past the deadline it was given
    elif mode == "wait-fails":
        # Round 5, P2-4: our own child, the right pid, creation time and event — and its
        # WaitForMultipleObjects FAILS (not a timeout). It watched nothing.
        k32 = runlog._kernel32()
        created = runlog._created(k32, k32.GetCurrentProcess())
        nonce = "0123456789abcdef0123456789abcdef"
        event = k32.CreateEventW(None, True, False, runlog._event_name(os.getpid(), created, nonce))
        base, *_flags, script = runlog.self_command()
        code = "\\n".join([
            "import importlib.util, sys",
            "spec = importlib.util.spec_from_file_location('runlog_under_test', sys.argv[1])",
            "runlog = importlib.util.module_from_spec(spec)",
            "sys.modules['runlog_under_test'] = runlog",
            "spec.loader.exec_module(runlog)",
            "real = runlog._kernel32",
            "def broken():",
            "    k32 = real()",
            "    k32.WaitForMultipleObjects = lambda *a: 0xFFFFFFFF",
            "    return k32",
            "runlog._kernel32 = broken",
            "sys.exit(runlog.supervisor_main(sys.argv[2:]))",
        ])
        helper = subprocess.Popen([base, "-I", "-c", code, script, str(os.getpid()), str(created), nonce,
                                   "1", "-", "what:its wait fails"], stderr=subprocess.PIPE, text=True)
        _out, said = helper.communicate(timeout=30)
        print("HELPER", helper.returncode, said.strip(), flush=True)
        time.sleep(3.0)   # past the deadline it was given: nobody ended us
    print("returned", flush=True)
""")


def _supervised(mode: str, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    log = tmp_path / "supervised.log"
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _SUPERVISED, mode, str(log)],
        env=isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen"), capture_output=True, text=True,
        timeout=100, cwd=tmp_path)
    return proc, log.read_text(encoding="utf-8") if log.is_file() else ""


@windows_only
def test_the_supervisor_ends_a_process_its_own_watchdog_cannot_end(tmp_path: Path) -> None:
    proc, text = _supervised("stuck", tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    assert "returned" not in proc.stdout
    armed = "[watchdog] armed=True seconds=1.5 what=the supervised block supervisor=process "
    fired = "[supervisor] fired=True what=the supervised block"
    assert armed in text and fired in text and text.index(armed) < text.index(fired)
    assert "still alive 3.5 s after its watchdog was armed" in text  # 1.5 s + the grace period
    assert "terminated from outside, exit code 1" in text


@windows_only
def test_the_supervisor_leaves_a_process_alone_whose_block_finished_first(tmp_path: Path) -> None:
    """The block is over before the supervising process has started. Had the late
    supervisor waited on the process alone, it would have ended — 3.5 s later — a
    process that finished its block and simply lives on: a pytest run that called the
    bounded self-test, 310 s after the test passed.

    The block signals its release event and KEEPS it until the supervisor has left
    (review round 4): the late supervisor finds it, signalled, and leaves with the code
    for "released" — which it can therefore tell from "there is no such block"."""
    proc, text = _supervised("in-time", tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, proc.stdout + proc.stderr[-2000:]
    assert "supervisor=process " in text and "[supervisor]" not in text
    assert "SUPERVISOR_EXIT 0 True" in proc.stdout
    assert "[watchdog] released=True what=the supervised block supervisor_exit=0" in text


# Wall-clock: the child looks 1.5 s into its block for a supervising process that must be
# gone by then; beside the default run's workers that process starts and leaves later
# ("DURING None" — measured twice on 2026-10-19), so it runs in the serial perf step (ADR-058).
@pytest.mark.perf
@windows_only
def test_a_supervisor_that_never_supervised_says_so_in_its_exit_code(tmp_path: Path) -> None:
    """Review round 4, P2-1 — the reviewer's sequence. The supervisor cannot find its
    block (a creation time that is not the process's) and leaves AT ONCE: 1.5 s into a
    20 s block it is gone. It used to exit 0, the block's ``Armed`` said "supervised",
    and the self-test logged ``ok=True detail=started, released, left`` — for a run
    that had no safety net at all. Its exit code is 4 now, and the block says why."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    proc, text = _supervised("left-at-once", tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, proc.stdout + proc.stderr[-2000:]
    assert runlog.SUPERVISOR_IDLE == 4
    assert "DURING 4" in proc.stdout, "it left while the block ran — and said that it had not supervised"
    (after,) = [line for line in proc.stdout.splitlines() if line.startswith("AFTER ")]
    assert after.startswith("AFTER 4 False | its supervising process left without having supervised")
    assert "exit code 4" in after
    assert "released=True what=the supervised block supervisor_exit=4 note=the supervising process left" in text


@windows_only
def test_a_watchdog_that_cannot_be_armed_leaves_nothing_armed_and_no_supervisor(tmp_path: Path) -> None:
    """Review round 4, P2-2. The supervising process was started and the process marked
    armed BEFORE the ``try``: when arming then failed, every later watchdog was refused
    ("already armed") and a live supervisor remained that would have ended the process
    at the deadline. Now the failure disarms what was armed so far: nothing is left,
    the supervisor is released and gone, the next block is armed and supervised — and
    the process lives past the failed block's deadline."""
    proc, text = _supervised("arming-fails", tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, proc.stdout + proc.stderr[-2000:]
    lines = [line for line in proc.stdout.splitlines() if line]
    assert "THE BLOCK RAN" not in lines, "a block that could not be armed must not run"
    assert lines[:3] == ["RAISED unable to start watchdog thread", "ARMED []", "STRAY False"], lines
    assert "NEXT 0 True" in lines
    assert "[supervisor]" not in text, "nobody was terminated"


@windows_only
def test_a_released_supervisor_goes_at_once(tmp_path: Path) -> None:
    proc, text = _supervised("released", tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert [line for line in proc.stdout.splitlines() if line] == [
        "STARTED True", "WAITING True", "GONE 0", "returned"]
    assert "[supervisor]" not in text


@windows_only
@pytest.mark.parametrize("mode", ["two-blocks", "two-watchdogs"])
def test_a_finished_blocks_supervisor_cannot_end_the_block_after_it(tmp_path: Path, mode: str) -> None:
    """Review round 3, P1-2. The release event was named per PROCESS. Block A finished
    before its supervising process was up; block B created "the" event again; A's late
    supervisor opened it, waited out A's deadline and terminated the process — 4.1 s
    into a healthy block with a 60 s budget, with "block A was still alive" in the log.
    The event is named per BLOCK now (a random nonce on the supervisor's command
    line): A's supervisor finds nothing and leaves."""
    proc, text = _supervised(mode, tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, (
        f"exit {proc.returncode}: the healthy second block did not survive the first one's "
        f"supervisor\n{proc.stdout}{proc.stderr[-1500:]}\n{text}")
    # A's supervisor came up after A was over: it found A's own event, signalled, and
    # left as "released" (0) — it never looked at B's, whose name carries another nonce
    assert "EXITS 0 0" in proc.stdout, proc.stdout
    assert "[supervisor]" not in text, text


@windows_only
def test_the_supervisor_never_ends_another_process_that_got_the_pid(tmp_path: Path) -> None:
    """A pid is reused. The supervisor knows its process by pid AND creation time: here
    it is our own child, the pid is ours, the release event exists — and the creation
    time is not ours. It leaves — saying that it supervised nobody (4) — and we live."""
    proc, _text = _supervised("wrong-creation-time", tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert "HELPER 4" in proc.stdout and "returned" in proc.stdout


@windows_only
def test_a_supervisor_that_finds_no_release_event_leaves_and_says_it_never_supervised(
        tmp_path: Path) -> None:
    """The process is the one named, and there is no release event of the block's name:
    not a block the supervisor can find (or one that ended more than 15 s ago). It leaves
    at once — waiting on the process alone would end, at the deadline, a process that
    finished its block and simply lives on — and its exit code is 4, not 0: it never
    supervised (review round 4, P2-1; a mutant that answered 0 here survived the first
    version of these tests)."""
    proc, text = _supervised("no-event", tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, proc.stdout + proc.stderr[-2000:]
    assert "HELPER 4" in proc.stdout, proc.stdout
    assert "[supervisor]" not in text, "nobody was terminated"


@windows_only
def test_a_supervisor_whose_wait_fails_says_so_and_terminates_nothing(tmp_path: Path) -> None:
    """Review round 5, P2-4. The supervisor's ``WaitForMultipleObjects`` FAILED — and it
    exited 0, "it did its job": everything that was not a timeout counted as a release
    (measured). It had watched nothing. Now only the two answers that mean "the process
    ended" and "released" are 0; a failed wait is exit code 3 like every other failure of
    its own, one line on stderr, and no process is terminated."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    proc, text = _supervised("wait-fails", tmp_path)
    assert proc.returncode == 0 and "returned" in proc.stdout, proc.stdout + proc.stderr[-2000:]
    (helper,) = [line for line in proc.stdout.splitlines() if line.startswith("HELPER ")]
    assert helper.startswith(f"HELPER {runlog.SUPERVISOR_FAILED} "), helper
    assert "failed: the wait for the supervised process failed (0xFFFFFFFF)" in helper
    assert "[supervisor]" not in text, "nobody was terminated"


def test_a_watchdog_whose_arming_fails_is_not_left_armed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-2 on every platform, without a supervisor: arming fails (``faulthandler`` cannot
    start its thread) — the error reaches the caller, the block does not run, and the
    process is not left "armed": the next watchdog works."""
    import faulthandler

    from open_garden_planner.ui.view3d.quick3d import runlog

    log = runlog.RenderLog(tmp_path / "arming.log", mirror=False)
    real = faulthandler.dump_traceback_later

    def cannot_arm(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("unable to start watchdog thread")

    monkeypatch.setattr(faulthandler, "dump_traceback_later", cannot_arm)
    ran: list[int] = []
    with pytest.raises(RuntimeError, match="unable to start watchdog thread"), \
            runlog.watchdog(5.0, log, what="cannot be armed"):
        ran.append(1)
    assert ran == [] and runlog._ARMED == []  # noqa: SLF001
    monkeypatch.setattr(faulthandler, "dump_traceback_later", real)
    with runlog.watchdog(5.0, log, what="the next block") as armed:
        assert len(runlog._ARMED) == 1 and runlog._ARMED[0] is armed  # noqa: SLF001
    assert runlog._ARMED == []  # noqa: SLF001
    log.close()


def test_what_a_block_says_about_its_supervisor() -> None:
    """``Armed.gap``: "" only for a supervisor that held the block's event and left; else
    words a log line and the self-test's FAIL line can carry."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    class Gone:
        pass

    def armed(exit_code: int | None, *, released: bool = True) -> runlog.Armed:
        made = runlog.Armed(5.0, "x", supervisor=Gone())  # type: ignore[arg-type]
        made.supervisor_exit, made.released = exit_code, released
        return made

    assert armed(0).gap == "" and armed(0).supervised is True
    for code, words in ((2, "refused"), (3, "failed itself"), (4, "left without having supervised"),
                        (None, "had not left 15 s after its release"), (9, "ended with exit code 9")):
        gap = armed(code).gap
        assert gap.startswith("its supervising process ") and words in gap, gap
        # review round 5, P2-5: a supervisor that had NOT LEFT 15 s after its release read
        # as "supervised" beside a gap that said it had not left (measured)
        assert armed(code).supervised is False, code
    # while the block runs nothing is known to be missing: a supervising process was started
    running = armed(None, released=False)
    assert running.supervised is True and running.gap == ""
    for code in (0, 2, 3, 4, 9, None):
        for released in (False, True):
            block = armed(code, released=released)
            assert block.supervised is (block.gap == ""), (code, released)
    none = runlog.Armed(5.0, "x", unsupervised_because="none (it could not be started)")
    assert none.gap == "none (it could not be started)" and none.supervised is False
    assert (runlog.SUPERVISOR_DONE, runlog.SUPERVISOR_REFUSED, runlog.SUPERVISOR_FAILED,
            runlog.SUPERVISOR_IDLE) == (0, 2, 3, 4)
    doc = runlog.__doc__ or ""
    assert "NO start timeout DURING the block" in doc and "``SUPERVISOR_EXIT_WAIT_S``" in doc


@windows_only
def test_the_supervisor_only_acts_for_the_process_that_started_it(tmp_path: Path) -> None:
    """Review round 3, P2-4: any pid was accepted. A supervisor started by THIS process
    and pointed at another one — a stand-in that sleeps — with everything else in
    order (the right creation time, a release event that exists): it refuses with one
    line and exit code 2, and the stand-in lives past the deadline."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    victim = subprocess.Popen(  # noqa: S603 - fixed argv
        [runlog.self_command()[0], "-I", "-c", "import time; time.sleep(60)"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    k32 = runlog._kernel32()  # noqa: SLF001
    handle = k32.OpenProcess(0x1000, False, victim.pid)
    created = runlog._created(k32, handle)  # noqa: SLF001
    k32.CloseHandle(handle)
    event = k32.CreateEventW(None, True, False, runlog._event_name(victim.pid, created, NONCE))  # noqa: SLF001
    try:
        assert created > 0 and event
        supervisor = subprocess.run(  # noqa: S603 - fixed argv, our own code
            [*runlog.self_command(), str(victim.pid), str(created), NONCE, "1", "-", "what:not mine"],
            env=env, capture_output=True, text=True, timeout=60)
        assert supervisor.returncode == runlog.SUPERVISOR_REFUSED == 2, supervisor.stderr
        assert supervisor.stderr.strip().splitlines() == [
            "--selftest-supervisor: refused: the process named is not the one that started this "
            "supervisor."]
        with pytest.raises(subprocess.TimeoutExpired):
            victim.wait(timeout=3.0)  # past the supervisor's deadline: nobody ended it
    finally:
        victim.kill()
        victim.wait(timeout=30)
        k32.CloseHandle(event)


def _valid_arguments(tmp_path: Path, **changes: str) -> list[str]:
    log = tmp_path / "block.log"
    log.write_text("", encoding="utf-8")
    order = {"pid": "4711", "created": "133000000000000000", "nonce": NONCE, "seconds": "310",
             "log": str(log), "what": "what:--selftest"}
    order.update(changes)
    return list(order.values())


def test_a_supervisors_arguments_are_read_into_an_order(tmp_path: Path) -> None:
    from open_garden_planner.ui.view3d.quick3d import runlog

    order = runlog.parse_supervisor_arguments(_valid_arguments(tmp_path))
    assert (order.pid, order.created, order.nonce, order.seconds, order.what) == (
        4711, 133000000000000000, NONCE, 310.0, "--selftest")
    assert order.log_path == str(tmp_path / "block.log")
    assert runlog.parse_supervisor_arguments(_valid_arguments(tmp_path, log="-")).log_path is None
    # the label goes into a log line: one line, bounded
    long = runlog.parse_supervisor_arguments(_valid_arguments(tmp_path, what="what:a\nb " + "x" * 500))
    assert "\n" not in long.what and len(long.what) == 200
    assert (runlog.MIN_SUPERVISED_S, runlog.MAX_SUPERVISED_S) == (0.5, 86_400.0)
    for edge in ("0.5", "86400"):
        assert runlog.parse_supervisor_arguments(_valid_arguments(tmp_path, seconds=edge)).seconds > 0


@pytest.mark.parametrize(("change", "words"), [
    ({"pid": "abc"}, "process id"), ({"pid": "0"}, "process id"), ({"pid": "-5"}, "process id"),
    ({"pid": "1e3"}, "process id"), ({"pid": str(2**32)}, "process id"),
    ({"created": "0"}, "creation time"), ({"created": "yesterday"}, "creation time"),
    ({"nonce": "0123"}, "nonce"), ({"nonce": NONCE.upper()}, "nonce"), ({"nonce": "g" * 32}, "nonce"),
    # nan and inf used to be an uncaught traceback, -1 a wait of 49 days, 0 a kill at once
    ({"seconds": "nan"}, "deadline"), ({"seconds": "inf"}, "deadline"), ({"seconds": "-inf"}, "deadline"),
    ({"seconds": "-1"}, "deadline"), ({"seconds": "0"}, "deadline"), ({"seconds": "0.49"}, "deadline"),
    ({"seconds": "86401"}, "deadline"), ({"seconds": "soon"}, "deadline"),
    ({"log": "relative.log"}, "not absolute"), ({"what": "--selftest"}, "does not name"),
])
def test_a_supervisor_refuses_arguments_it_may_not_act_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        change: dict[str, str], words: str) -> None:
    """Review round 3, P2-4. Malformed arguments: exit code 2 and ONE line — never a
    traceback, never a terminate (nothing is opened before the arguments are in order)."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    monkeypatch.setattr(runlog, "_supervise", lambda _order: pytest.fail("it went on to supervise"))
    arguments = _valid_arguments(tmp_path, **change)
    with pytest.raises(ValueError, match=words):
        runlog.parse_supervisor_arguments(arguments)
    assert runlog.supervisor_main(arguments) == runlog.SUPERVISOR_REFUSED == 2
    (line,) = capsys.readouterr().err.strip().splitlines()
    assert line.startswith("--selftest-supervisor: refused: ") and words in line
    assert "internal" in line and "Traceback" not in line
    assert line.isascii(), "the one line must be printable on any console"


def test_the_supervisors_one_line_survives_a_console_that_lacks_a_character(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Found with the frozen exe in round 3: a refusal held an ellipsis. Where the console's
    code page has no such character the print raises — and the line, suppressed with the
    exception, is gone. The line is written in ASCII, whatever it holds."""
    import io

    from open_garden_planner.ui.view3d.quick3d import runlog

    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp437", errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stderr", console)
    runlog._say("refused: 0.5 \u2026 86400 s \u2014 \u00e4")  # noqa: SLF001
    console.flush()
    assert raw.getvalue() == b"--selftest-supervisor: refused: 0.5 \\u2026 86400 s \\u2014 \\xe4\n"
    monkeypatch.setattr(sys, "stderr", None)  # a windowed exe: nothing to write to, nothing raised
    runlog._say("refused: nobody listens")  # noqa: SLF001


def test_a_supervisor_refuses_the_wrong_number_of_arguments_and_a_log_it_would_have_to_create(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from open_garden_planner.ui.view3d.quick3d import runlog

    monkeypatch.setattr(runlog, "_supervise", lambda _order: pytest.fail("it went on to supervise"))
    valid = _valid_arguments(tmp_path)
    missing = tmp_path / "never-written.log"
    folder = tmp_path / "a-folder"
    folder.mkdir()
    for arguments, words in (([], "6 arguments expected, 0 given"), (valid[:5], "5 given"),
                             ([*valid, "extra"], "7 given"),
                             (_valid_arguments(tmp_path, log=str(missing)), "creates no file"),
                             (_valid_arguments(tmp_path, log=str(folder)), "not a regular file")):
        assert runlog.supervisor_main(arguments) == 2
        assert words in capsys.readouterr().err
    assert not missing.exists(), "a supervisor creates no file"


def test_a_supervisor_that_fails_itself_says_one_line_and_terminates_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from open_garden_planner.ui.view3d.quick3d import runlog

    def broken(_order: object) -> int:
        raise OSError("kernel32 said no")

    monkeypatch.setattr(runlog, "_supervise", broken)
    assert runlog.supervisor_main(_valid_arguments(tmp_path)) == runlog.SUPERVISOR_FAILED == 3
    assert capsys.readouterr().err.strip() == "--selftest-supervisor: failed: OSError"


def test_one_watchdog_per_process_a_second_one_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review round 3, P1-2: a supervisor acts for exactly one block, and ``faulthandler``
    has ONE timer — a watchdog inside a watchdog used to replace the outer one's timer
    and cancel it on the way out. Refused BEFORE anything is touched: the outer watchdog
    stays armed, and a new one can be armed once it is over."""
    import faulthandler

    from open_garden_planner.ui.view3d.quick3d import runlog

    calls: list[str] = []
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda *_a, **_k: calls.append("arm"))
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: calls.append("cancel"))
    log = runlog.RenderLog(tmp_path / "one.log", mirror=False)
    try:
        with runlog.watchdog(60.0, log, what="the outer block") as outer:
            for supervised in (False, True):
                with pytest.raises(runlog.WatchdogError, match="already armed.*'the outer block'"), \
                        runlog.watchdog(30.0, log, what="the inner block", supervised=supervised):
                    pytest.fail("the inner block ran")
            assert calls == ["arm"], "the refusal touched the outer watchdog's timer"
            with runlog.watchdog(0.0, log, what="a watchdog that is switched off"):
                pass  # not armed: nothing to collide with
        assert calls == ["arm", "cancel"] and outer.supervisor is None
        with runlog.watchdog(60.0, log, what="the next block"):
            pass
        assert calls == ["arm", "cancel", "arm", "cancel"]
    finally:
        log.close()
    assert "the inner block" not in (tmp_path / "one.log").read_text(encoding="utf-8")


def test_the_supervisor_is_started_as_this_checkouts_own_file() -> None:
    """From source it runs ``runlog.py`` itself — never ``-m open_garden_planner``, which
    from a git worktree could start another checkout's application — isolated, under
    the interpreter BEHIND the virtual environment (a venv's ``python.exe`` is a
    launcher on Windows: its child would be the supervisor's parent, not us). Nothing
    but the standard library is imported at the top of that file."""
    import ast

    from open_garden_planner.ui.view3d.quick3d import runlog

    command = runlog.self_command()
    assert command[1:] == ["-I", str(Path(runlog.__file__).resolve())]
    assert Path(command[0]).is_file()
    assert command[0] == (getattr(sys, "_base_executable", None) or sys.executable)
    tree = ast.parse(Path(runlog.__file__).read_text(encoding="utf-8"))
    top_level = {alias.name.split(".")[0] for node in tree.body if isinstance(node, ast.Import)
                 for alias in node.names}
    top_level |= {(node.module or "").split(".")[0] for node in tree.body
                  if isinstance(node, ast.ImportFrom)}
    assert top_level <= {"__future__", "contextlib", "faulthandler", "math", "os", "re", "secrets",
                         "stat", "subprocess", "sys", "threading", "time", "collections",
                         "dataclasses", "pathlib", "typing"}, top_level


@pytest.mark.skipif(sys.platform == "win32", reason="the supervisor exists on Windows")
def test_without_a_supervisor_the_log_says_so_and_what_bounds_a_deadlock(tmp_path: Path) -> None:
    """Elsewhere ``faulthandler``'s exit was measured to end even the deadlock (Linux);
    the log says that there is no supervisor, and what the bound is beyond that."""
    from open_garden_planner.ui.view3d.quick3d import runlog

    assert runlog.start_supervisor(5.0, None, "x") is None
    log = runlog.RenderLog(tmp_path / "plain.log", mirror=False)
    try:
        with runlog.watchdog(30.0, log, what="a block", supervised=True) as armed:
            pass
    finally:
        log.close()
    assert armed.supervisor is None and not armed.supervised
    text = (tmp_path / "plain.log").read_text(encoding="utf-8")
    assert "supervisor=none (not on this platform: _exit ends the process" in text
    assert "in CI the step's" in text
