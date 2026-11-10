"""The wind's sway of a plant as data (#800, ADR-059 addendum "the wind that shows").

``core/scene3d/wind.py`` states the shaders' ``plantSway`` in numpy. These tests pin the
rule (the amplitude is a share of the plant's height, linear in the look's wind), the
motion's shape (a cantilever: the foot stays, the top moves most; a taller plant swings
slower), rest (nothing moves at clock 0), determinism, smoothness at 30 and 60 fps, the
seamless wrap of the clock and the GLSL's numbers against the module's (a drift guard:
the render tier measures the pixels, ``test_view3d_wind_render.py``).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.plant_art import SpriteRef
from open_garden_planner.core.plant_forge import forge_plant
from open_garden_planner.core.scene3d import Mesh, MeshPart, Transform, engine_model_matrix
from open_garden_planner.core.scene3d.frame import scene_to_engine_points
from open_garden_planner.core.scene3d.look import WIND_STRENGTH
from open_garden_planner.core.scene3d.weather import WEATHER_SPECS
from open_garden_planner.core.scene3d.wind import (
    ACROSS_OF_SWAY,
    ACROSS_SHARE,
    BRANCH_OF_SWAY,
    BRANCH_SHARE,
    CLOCK_PERIOD_S,
    FLUTTER_MIN_HZ,
    FLUTTER_OF_SWAY,
    FLUTTER_SHARE,
    FLUTTER_SPREAD,
    GUST_DEPTH,
    GUST_HZ,
    GUST_WAVE_PER_CM,
    LEAN,
    NO_SWAY,
    SWAY_HZ_AT_1M,
    SWAY_HZ_RANGE,
    SWAY_HZ_SPREAD,
    SWAY_SHARE,
    WIND_FROM_DEG,
    SwayFrame,
    hourly,
    rest_ramp,
    sway_amplitude_cm,
    sway_frame,
    sway_frequency_hz,
    sway_offsets,
    wind_sway_scene,
)

QML_DIR = (Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "ui" / "view3d"
           / "quick3d" / "qml")
SWAY_SHADERS = ("foliage.vert", "foliage_door.vert", "plant_sway.vert")
BIRCH = SpriteRef("species", "birch")


def _engine_wind(strength: float = WIND_STRENGTH) -> np.ndarray:
    east, north = wind_sway_scene(strength)
    return np.asarray(scene_to_engine_points(np.array([[east, north, 0.0]]))[0])


def _model(east: float = 1420.0, north: float = 560.0, yaw: float = 0.0) -> np.ndarray:
    return engine_model_matrix(Transform(east, north, 0.0, yaw))


def _column(height: float) -> np.ndarray:
    """Item-local ENGINE points on the axis, foot to top."""
    return np.array([[0.0, height * k, 0.0] for k in (0.0, 0.25, 0.5, 0.75, 1.0)])


class TestTheRule:
    def test_the_amplitude_is_half_a_percent_of_the_height_under_a_clear_days_wind(self) -> None:
        assert SWAY_SHARE == 0.005
        assert sway_amplitude_cm(950.0) == pytest.approx(4.75)
        assert sway_amplitude_cm(174.0) == pytest.approx(0.87)
        assert sway_amplitude_cm(60.0) == pytest.approx(0.30)
        assert sway_amplitude_cm(1200.0) == pytest.approx(6.0)

    def test_the_weathers_wind_keeps_its_meaning(self) -> None:
        """Calm is still; a weather that raises the wind raises the sway, linearly."""
        assert sway_amplitude_cm(950.0, 0.0) == 0.0
        for spec in WEATHER_SPECS.values():
            assert sway_amplitude_cm(950.0, spec.wind_strength) == pytest.approx(
                4.75 * spec.wind_strength / WIND_STRENGTH)
        assert sway_amplitude_cm(950.0, WEATHER_SPECS["rain"].wind_strength) == pytest.approx(9.5)
        east, north = wind_sway_scene(0.0)
        assert east == 0.0 and north == 0.0
        east, north = wind_sway_scene(WIND_STRENGTH)
        assert math.hypot(east, north) == pytest.approx(1.0)
        # downwind of a wind from the west-south-west: towards the east-north-east
        assert math.degrees(math.atan2(east, north)) == pytest.approx((WIND_FROM_DEG + 180.0) % 360.0)

    def test_a_taller_plant_swings_slower(self) -> None:
        heights = (20.0, 60.0, 174.0, 400.0, 950.0, 2000.0)
        rates = [sway_frequency_hz(h) for h in heights]
        assert rates == sorted(rates, reverse=True)
        assert sway_frequency_hz(100.0) == pytest.approx(SWAY_HZ_AT_1M)
        assert sway_frequency_hz(950.0) == pytest.approx(0.389, abs=0.001)
        assert sway_frequency_hz(950.0, 0.0) == pytest.approx(0.9 * 0.389, abs=0.001)
        assert sway_frequency_hz(950.0, 1.0) == pytest.approx(1.1 * 0.389, abs=0.001)
        assert SWAY_HZ_RANGE[0] <= min(rates) and max(rates) <= SWAY_HZ_RANGE[1]
        # a leaf never flutters near a frame rate's Nyquist (15 Hz at 30 fps): at most
        # 5.1 Hz, six frames a cycle at 30 fps
        fastest = max(FLUTTER_MIN_HZ, FLUTTER_OF_SWAY * SWAY_HZ_RANGE[1] * SWAY_HZ_SPREAD[1])             * FLUTTER_SPREAD[1]
        assert fastest < 5.1 and 30.0 / fastest > 5.8

    def test_every_frequency_is_whole_cycles_an_hour(self) -> None:
        for hz in (0.07, 0.389, 1.2, 2.5, 3.7):
            cycles = hourly(hz) * CLOCK_PERIOD_S / (2.0 * math.pi)
            assert cycles == pytest.approx(round(float(cycles)), abs=1e-9)
            assert float(hourly(hz)) == pytest.approx(2.0 * math.pi * hz, rel=2e-3 if hz > 0.1 else 2e-2)

    def test_the_rest_ramp(self) -> None:
        assert rest_ramp(0.0) == 0.0 and rest_ramp(-1.0) == 0.0
        assert rest_ramp(2.0) == 1.0 and rest_ramp(3602.0) == 1.0
        assert 0.0 < rest_ramp(1.0) < 1.0


class TestTheFrame:
    def test_a_plant_sways_by_its_own_fitted_size_and_every_part_alike(self) -> None:
        parts = forge_plant(BIRCH, 950.0, 154.0, seed=7, cache=None)
        frame = sway_frame("birch-1", parts)
        assert frame.sways
        assert frame.height_cm == pytest.approx(950.0, rel=1e-4)    # the fit makes the top the data's
        assert 0.9 * 154.0 <= frame.radius_cm <= 1.05 * 154.0       # REACH_MAX of the forge: 1.04
        assert 0.0 <= frame.phase < 1.0

    def test_the_phase_comes_from_the_item_id_and_two_items_differ(self) -> None:
        parts = forge_plant(BIRCH, 950.0, 154.0, seed=7, cache=None)
        phases = {sway_frame(f"plant-{k}", parts).phase for k in range(40)}
        assert len(phases) == 40
        assert sway_frame("plant-3", parts) == sway_frame("plant-3", parts)

    def test_an_item_without_leaves_does_not_sway(self) -> None:
        box = Mesh.from_arrays(
            np.array([[0, 0, 0], [100, 0, 0], [0, 100, 200]], np.float32),
            np.array([[0, 0, 1]] * 3, np.float32), np.ones((3, 4), np.float32),
            np.zeros((3, 2), np.float32), np.array([[0, 1, 2]], np.uint32))
        assert sway_frame("shed", (MeshPart(box, "vc"),)) == NO_SWAY
        assert sway_frame("shed", ()) == NO_SWAY
        assert sway_frame("hedge", (MeshPart(box, "foliage"),)).height_cm == pytest.approx(200.0)


class TestTheMotion:
    def _series(self, frame: SwayFrame, points: np.ndarray, fps: float, seconds: float,
                start: float = 10.0, **kw: object) -> np.ndarray:
        model, wind = _model(), _engine_wind()
        return np.stack([sway_offsets(points, frame, model, wind, start + i / fps, **kw)
                         for i in range(int(seconds * fps) + 1)])

    def test_nothing_moves_at_rest_without_a_frame_or_in_a_calm(self) -> None:
        frame = SwayFrame(950.0, 154.0, 0.3)
        pts = _column(950.0)
        normals = np.tile([0.0, 0.0, 1.0], (len(pts), 1))
        phases = np.linspace(0.0, 0.9, len(pts))
        assert not sway_offsets(pts, frame, _model(), _engine_wind(), 0.0,
                                leaf_phase=phases, normals=normals).any()
        assert not sway_offsets(pts, NO_SWAY, _model(), _engine_wind(), 12.0).any()
        assert not sway_offsets(pts, frame, _model(), _engine_wind(0.0), 12.0).any()

    def test_a_cantilever_the_foot_stays_and_the_top_swings_by_the_rule(self) -> None:
        frame = SwayFrame(950.0, 154.0, 0.3)
        series = self._series(frame, _column(950.0), 30.0, 60.0)
        assert not series[:, 0].any()                     # the foot on the axis never moves
        down = _engine_wind() / np.linalg.norm(_engine_wind())
        along = series[:, -1] @ down
        amp = sway_amplitude_cm(950.0)
        swing = (along.max() - along.min()) / 2.0
        # the swing about the lean is the amplitude times the gust (0.3 .. 1.0)
        assert (1.0 - 2.0 * GUST_DEPTH) * amp <= swing <= amp * 1.0001
        assert along.mean() > 0.0                          # it leans downwind
        reach = [np.linalg.norm(series[:, k], axis=1).max() for k in range(5)]
        assert reach == sorted(reach)                      # the higher, the more

    def test_a_tree_sways_more_and_slower_than_a_shrub_and_a_herb(self) -> None:
        tops = {}
        for height in (950.0, 174.0, 60.0):
            frame = SwayFrame(height, height / 4.0, 0.3)
            series = self._series(frame, _column(height)[-1:], 60.0, 20.0)[:, 0]
            down = _engine_wind() / np.linalg.norm(_engine_wind())
            along = series @ down
            spectrum = np.abs(np.fft.rfft(along - along.mean()))
            peak = np.fft.rfftfreq(len(along), 1.0 / 60.0)[int(np.argmax(spectrum[1:]) + 1)]
            tops[height] = (along.max() - along.min(), peak)
        assert tops[950.0][0] > tops[174.0][0] > tops[60.0][0]
        assert tops[950.0][1] < tops[174.0][1] < tops[60.0][1]

    @pytest.mark.parametrize("fps", [30.0, 60.0])
    @pytest.mark.parametrize("height", [950.0, 174.0, 60.0])
    def test_the_motion_is_smooth_frame_to_frame(self, fps: float, height: float) -> None:
        """No jitter and no alternation: the step a frame is bounded by the fastest term's
        speed, no coordinate swings back and forth on two frames running by a quarter of its
        largest step (a zigzag), and nothing of the motion lies above a third of the frame
        rate."""
        frame = SwayFrame(height, height / 5.0, 0.3)
        pts = np.array([[0.2, 0.95, 0.0], [0.0, 1.0, 0.0], [-0.15, 0.7, 0.1]]) * height
        normals = np.tile([0.6, 0.0, 0.8], (3, 1))
        series = self._series(frame, pts, fps, 12.0, leaf_phase=np.array([0.1, 0.5, 0.9]),
                              normals=normals)
        amp = sway_amplitude_cm(height)
        hz = sway_frequency_hz(height, frame.phase)
        speed = 2.0 * math.pi * amp * (1.0 * hz + ACROSS_SHARE * ACROSS_OF_SWAY * hz
                                       + BRANCH_SHARE * 1.5 * max(BRANCH_OF_SWAY) * hz
                                       + FLUTTER_SHARE * max(FLUTTER_MIN_HZ, FLUTTER_OF_SWAY * hz)
                                       * FLUTTER_SPREAD[1] + GUST_DEPTH * GUST_HZ * 3.0)
        steps = np.linalg.norm(np.diff(series, axis=0), axis=2)
        assert steps.max() <= speed / fps
        d1 = np.diff(series, axis=0)
        big = np.abs(d1) > 0.25 * np.abs(d1).max(axis=0)
        zigzags = (d1[:-2] * d1[1:-1] < 0.0) & (d1[1:-1] * d1[2:] < 0.0) & big[1:-1]
        assert not zigzags.any()
        signal = (series - series.mean(axis=0)) * np.hanning(len(series))[:, None, None]
        power = np.abs(np.fft.rfft(signal, axis=0)) ** 2
        freqs = np.fft.rfftfreq(len(signal), 1.0 / fps)
        assert power[freqs > fps / 3.0].sum() <= 1e-4 * power.sum()

    def test_the_same_moment_is_the_same_picture_and_the_clocks_wrap_is_seamless(self) -> None:
        frame = SwayFrame(950.0, 154.0, 0.3)
        pts = np.array([[150.0, 900.0, 0.0], [0.0, 950.0, 30.0]])
        kw = {"leaf_phase": np.array([0.2, 0.7]), "normals": np.tile([0.0, 1.0, 0.0], (2, 1))}
        one = sway_offsets(pts, frame, _model(), _engine_wind(), 11.5, **kw)
        two = sway_offsets(pts, frame, _model(), _engine_wind(), 11.5, **kw)
        assert np.array_equal(one, two)
        np.testing.assert_allclose(
            sway_offsets(pts, frame, _model(), _engine_wind(), CLOCK_PERIOD_S + 2.5, **kw),
            sway_offsets(pts, frame, _model(), _engine_wind(), 2.5, **kw), atol=1e-6)

    def test_neighbours_are_out_of_step(self) -> None:
        """Two plants a metre apart with their own phases do not swing together."""
        height = 400.0
        top = _column(height)[-1:]
        down = _engine_wind() / np.linalg.norm(_engine_wind())
        tracks = []
        for east, phase in ((1000.0, 0.11), (1100.0, 0.64)):
            frame = SwayFrame(height, 100.0, phase)
            model = _model(east, 500.0)
            tracks.append(np.array([sway_offsets(top, frame, model, _engine_wind(), 10.0 + i / 30.0)[0] @ down
                                    for i in range(600)]))
        a, b = (t - t.mean() for t in tracks)
        assert abs(float(np.corrcoef(a, b)[0, 1])) < 0.6

    def test_the_wind_blows_the_same_way_whichever_way_a_plant_is_turned(self) -> None:
        frame = SwayFrame(400.0, 1.0, 0.25)    # radius 1: the branches add nothing on the axis
        top = _column(400.0)[-1:]
        straight = sway_offsets(top, frame, _model(yaw=0.0), _engine_wind(), 13.0)[0]
        turned_model = _model(yaw=90.0)
        turned = sway_offsets(top, frame, turned_model, _engine_wind(), 13.0)[0]
        np.testing.assert_allclose(turned_model[:3, :3] @ turned, straight, atol=1e-9)


def _sway_block(name: str) -> str:
    text = (QML_DIR / name).read_text(encoding="utf-8")
    found = re.search(r"// ---- the plant's sway \(#800\).*?// ---- end of the plant's sway", text, re.S)
    assert found, name
    return found.group(0)


def test_the_shaders_carry_one_sway_block_with_the_modules_numbers() -> None:
    """Drift guard: the three shaders share ONE text of ``plantSway``, and every number in
    it is the module's (the numpy mirror the rule is tested on)."""
    blocks = {name: _sway_block(name) for name in SWAY_SHADERS}
    assert len(set(blocks.values())) == 1, "the sway block differs between shaders"
    code = blocks["foliage.vert"]
    expected = [
        f"return {SWAY_SHARE} * h * wind * gust * offset;",
        f"clamp({SWAY_HZ_AT_1M} * inversesqrt(max(h, 1.0) / 100.0), {SWAY_HZ_RANGE[0]}, {SWAY_HZ_RANGE[1]}) "
        f"* ({SWAY_HZ_SPREAD[0]} + {SWAY_HZ_SPREAD[1] - SWAY_HZ_SPREAD[0]:.1f} * uSwayFrame.z)",
        f"{1.0 - GUST_DEPTH:.2f} + {GUST_DEPTH} * sin(swayHourly({GUST_HZ}) * t - {GUST_WAVE_PER_CM} *",
        f"down * ({LEAN} + sin(swayHourly(hz) * t + seed))",
        f"across * ({ACROSS_SHARE} * sin(swayHourly({ACROSS_OF_SWAY} * hz) * t + seed + 1.7))",
        f"offset += {BRANCH_SHARE} * reach * vec3(sin(swayHourly({BRANCH_OF_SWAY[0]} * hz) * t",
        f"0.35 * sin(swayHourly({BRANCH_OF_SWAY[1]} * hz) * t",
        f"sin(swayHourly({BRANCH_OF_SWAY[2]} * hz) * t",
        f"max({FLUTTER_MIN_HZ}, {FLUTTER_OF_SWAY} * hz) * ({FLUTTER_SPREAD[0]} + "
        f"{FLUTTER_SPREAD[1] - FLUTTER_SPREAD[0]:.1f} * fract(leafPhase * 7.31))",
        f"offset += leaf * {FLUTTER_SHARE} * y * sin(swayHourly(flutterHz) * t + 6.2831853 * leafPhase * 13.0) * n;",
        f"floor(hz * {CLOCK_PERIOD_S:.1f} + 0.5) / {CLOCK_PERIOD_S:.1f}",
        "vec3 offset = body * mat3(MODEL_MATRIX);",
        "vec3 origin = MODEL_MATRIX[3].xyz;",
    ]
    flat = " ".join(code.split())
    for snippet in expected:
        assert " ".join(snippet.split()) in flat, snippet


@pytest.mark.parametrize("shader", SWAY_SHADERS)
def test_every_sway_moves_only_by_the_rest_ramp(shader: str) -> None:
    source = (QML_DIR / shader).read_text(encoding="utf-8")
    main = source.split("void MAIN()", 1)[1]
    assert "float rest = smoothstep(0.0, 2.0, uTime);" in main
    moves = [line.strip() for line in main.splitlines() if re.match(r"\s*VERTEX\s*\+=", line)]
    assert len(moves) == 1 and moves[0].endswith("* rest;"), moves
