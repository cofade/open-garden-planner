"""The wind on the real engine (#800) — render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins the
rule and the motion as data (``tests/unit/test_scene3d_wind.py``) and the scene's wiring
(``test_quick3d_qml.py``); here the ENGINE answers the issue's "done when": a crown's sway
is measurable and reads natural at 30 and 60 fps — the pixel amplitude and period of a
tree and a herb, no jitter, no alternation — and nothing changes at wind clock 0.

The pictures are the tour's (``Quick3DHost.capture`` with the clock computed per frame),
on the family garden: its 9.5 m birch about 11 m out, its 1.7 m lilac 5 m out and a 60 cm
basil in a raised bed 3 m out (``view3d_foliage_driver.py``).

    # Windows (Git Bash) - one driver at a time
    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 tests/integration/test_view3d_foliage_render.py
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from open_garden_planner.core.scene3d.wind import sway_frequency_hz
from tests.integration.quick3d_render_support import (
    QML_SOURCE,
    REPO,
    driver_messages,
    keep_artifacts,
    load_rgb,
    render_env,
    render_tier,
)

pytestmark = render_tier

DRIVER = REPO / "tests" / "integration" / "view3d_foliage_driver.py"
TIMEOUT_S = 840
SECONDS = 3.0
#: Measured on the RTX 4070 (Direct3D 11, 960 x 540, 4 s, 2026-11-10): the upper crown's
#: downwind sway, half its swing, 0.86 px for the birch (0.03 before #800), 0.78 px for the
#: lilac, 0.38 px for the basil; the period by zero crossings 2.67 / 1.11 / 0.65 s.
#: As px of a 1080-row picture the birch must sway at least this much — visible.
MIN_TREE_SWAY_1080_PX = 0.8


def _run(out: Path, scenario: str, **arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(DRIVER), "--out", str(out), "--scenario", scenario,
               "--watchdog-s", str(TIMEOUT_S - 60)]
    for key, value in arguments.items():
        command += ["--arg", f"{key}={value}"]
    proc = subprocess.run(command, env=render_env(out, QT_D3D_NO_VBLANK_THREAD="1"),
                          capture_output=True, text=True, timeout=TIMEOUT_S, cwd=REPO)
    keep_artifacts(out, proc)
    file = out / "result.json"
    result = json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}
    if result:
        result["qt_messages"] = driver_messages(proc.stderr)
    assert proc.returncode == 0 and result.get("status") == "ok", (proc.returncode, result.get("error"),
                                                                    proc.stderr[-2000:])
    assert not result["qt_messages"]["errors"], result["qt_messages"]["errors"]
    return proc, result


@pytest.fixture(scope="module")
def sequence(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    out = tmp_path_factory.mktemp("wind_sequence")
    _proc, result = _run(out, "sequence", seconds=str(SECONDS), subjects="tree,shrub,herb")
    return out, result["data"]


def _still_copy(tmp_path: Path) -> Path:
    """The scene with the sway taken out of every shader: what the frames were before."""
    qml = tmp_path / "qml"
    shutil.copytree(QML_SOURCE, qml)
    for name, call in (("foliage.vert", "    VERTEX += plantSway(VERTEX, NORMAL, UV0.y, 1.0) * rest;\n"),
                       ("foliage_door.vert", "    VERTEX += plantSway(VERTEX, NORMAL, UV0.y, 1.0) * rest;\n"),
                       ("plant_sway.vert", "    VERTEX += plantSway(VERTEX, vec3(0.0), 0.0, 0.0) * rest;\n")):
        text = (qml / name).read_text(encoding="utf-8")
        assert text.count(call) == 1, f"the copy no longer finds the sway in {name}"
        (qml / name).write_text(text.replace(call, ""), encoding="utf-8")
    return qml


def _px_to_cm(row: dict[str, Any], height_px: int) -> float:
    """cm per px at the subject's distance."""
    return 2.0 * float(row["distance_cm"]) * math.tan(math.radians(row["fov_deg"]) / 2.0) / height_px


def _period_s(series: np.ndarray, fps: int) -> float:
    """Twice the mean interval between zero crossings of the detrended, lightly smoothed
    series (the flutter riding on the swing is averaged out over a sixth of a second)."""
    k = max(1, fps // 6)
    smooth = np.convolve(series - series.mean(), np.ones(k) / k, mode="same")
    crossings = np.nonzero(np.diff(np.sign(smooth)) != 0)[0]
    assert len(crossings) >= 2, "less than one swing in the window"
    return float(2.0 * np.mean(np.diff(crossings)) / fps)


def _sway(row: dict[str, Any], fps: int) -> tuple[np.ndarray, np.ndarray]:
    return np.array(row[f"fps{fps}"]["dx"]), np.array(row[f"fps{fps}"]["dy"])


@pytest.mark.parametrize("fps", [30, 60])
def test_a_tree_sways_visibly_and_slowly_a_shrub_less_and_a_herb_barely(
        sequence: tuple[Path, dict[str, Any]], fps: int) -> None:
    """The issue's gate in pixels: the birch's upper crown sways at least
    ``MIN_TREE_SWAY_1080_PX`` (as px of a 1080-row picture; 0.06 before); in cm the sway
    follows the plant's size (tree > shrub > herb, the tree at least 4 x the herb) and the
    taller plant swings slower — each period within 40 % of the rule's
    (``wind.sway_frequency_hz`` of its height; the window is short and the gust and the
    branches ride on the swing)."""
    _out, data = sequence
    height_px = int(data["size"][1])
    sway_cm, periods = {}, {}
    for subject in ("tree", "shrub", "herb"):
        row = data[subject]
        dx, dy = _sway(row, fps)
        main = dx if np.ptp(dx) >= np.ptp(dy) else dy
        sway_px = float(np.ptp(main) / 2.0)
        sway_cm[subject] = sway_px * _px_to_cm(row, height_px)
        periods[subject] = _period_s(main, fps)
        rule = 1.0 / sway_frequency_hz(row["height_cm"])
        assert 0.6 * rule <= periods[subject] <= 1.4 * rule / 0.9, (subject, periods[subject], rule)
        if subject == "tree":
            assert sway_px * 1080.0 / height_px >= MIN_TREE_SWAY_1080_PX, (sway_px, height_px)
    assert sway_cm["tree"] > sway_cm["shrub"] > sway_cm["herb"], sway_cm
    assert sway_cm["tree"] >= 4.0 * sway_cm["herb"], sway_cm
    assert periods["tree"] > periods["shrub"] > periods["herb"], periods


def test_the_motion_is_smooth_and_a_frame_index_is_a_picture(sequence: tuple[Path, dict[str, Any]]) -> None:
    """No jitter, no alternation, determinism: the frame of a clock value is one picture
    (the same index twice: 0 levels apart; frame i at 30 fps IS frame 2i at 60 fps, so
    their translations agree exactly); the step a frame stays under a third of a pixel at
    30 fps and halves at 60; the downwind track never swings back and forth on two frames
    running; and next to nothing of the motion lies above a third of the frame rate."""
    _out, data = sequence
    for subject in ("tree", "shrub", "herb"):
        row = data[subject]
        assert row["repeat_max_diff"] == 0, subject
        dx30, dy30 = _sway(row, 30)
        dx60, dy60 = _sway(row, 60)
        np.testing.assert_allclose(dx60[::2][:len(dx30)], dx30, atol=1e-6)
        np.testing.assert_allclose(dy60[::2][:len(dy30)], dy30, atol=1e-6)
        steps = {}
        for fps, (dx, dy) in ((30, (dx30, dy30)), (60, (dx60, dy60))):
            step = np.hypot(np.diff(dx), np.diff(dy))
            steps[fps] = float(step.max())
            main = dx if np.ptp(dx) >= np.ptp(dy) else dy
            d1 = np.diff(main)
            big = np.abs(d1) > 0.25 * np.abs(d1).max()
            zigzags = (d1[:-2] * d1[1:-1] < 0.0) & (d1[1:-1] * d1[2:] < 0.0) & big[1:-1]
            assert not zigzags.any(), (subject, fps, int(zigzags.sum()))
            for series in (dx, dy):
                signal = (series - series.mean()) * np.hanning(len(series))
                power = np.abs(np.fft.rfft(signal)) ** 2
                freqs = np.fft.rfftfreq(len(series), 1.0 / fps)
                assert power[freqs > fps / 3.0].sum() <= 0.01 * power.sum(), (subject, fps)
        assert steps[30] <= 1.0 / 3.0, (subject, steps)
        assert steps[60] <= 0.7 * steps[30], (subject, steps)


def test_at_rest_nothing_moves_and_the_woods_shader_shows_nothing(
        sequence: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    """The issue's "no change at wind clock 0": with every sway taken out of the shaders,
    the frame at rest is the same picture to the level — and so is every frame with the
    clock running, the plants' wood through its swaying shader included (Medium draws no
    lawn blades, whose own wind is the only other motion)."""
    out, data = sequence
    _proc, still = _run(tmp_path / "still", "sequence", seconds="0.5", fps="30",
                        subjects="tree,herb", qml=str(_still_copy(tmp_path)))
    still_data = still["data"]
    for subject in ("tree", "herb"):
        now = load_rgb(out / data[subject]["rest"])
        before = load_rgb(tmp_path / "still" / still_data[subject]["rest"])
        assert np.array_equal(now, before), subject
        assert max(still_data[subject]["fps30"]["change"]) == 0.0, subject


def _shadowless_sway_copy(tmp_path: Path) -> Path:
    """The control: the scene whose SHADOW pass skips the sway (the colour pass keeps it)."""
    qml = tmp_path / "qml_control"
    shutil.copytree(QML_SOURCE, qml)
    for name, call in (("foliage.vert", "    VERTEX += plantSway(VERTEX, NORMAL, UV0.y, 1.0) * rest;\n"),
                       ("plant_sway.vert", "    VERTEX += plantSway(VERTEX, vec3(0.0), 0.0, 0.0) * rest;\n")):
        text = (qml / name).read_text(encoding="utf-8")
        assert text.count(call) == 1, f"the control no longer finds the sway in {name}"
        (qml / name).write_text(text.replace(
            call, "#if !QSSG_ENABLE_ORTHO_SHADOW_PASS\n" + call + "#endif\n"), encoding="utf-8")
    return qml


def test_a_crowns_shadow_moves_with_its_crown(tmp_path: Path) -> None:
    """The shadow pass runs the same sway: in a wind 20 x the look's, seen from above at a
    35° sun with every plant's own pixels masked out, the ground (the plants' shadows)
    changes with the clock as the crowns do. The control — the same scene whose shadow pass
    skips the sway — changes its crowns and leaves the ground (nearly) as it was: a crown
    swaying over a fixed shadow, which this test exists to catch."""
    _proc, result = _run(tmp_path / "shadow", "shadow", gain="20")
    _proc, control = _run(tmp_path / "control", "shadow", gain="20",
                          qml=str(_shadowless_sway_copy(tmp_path)))
    data, fixed = result["data"], control["data"]
    for wind in ("t11.0", "t12.3"):
        assert data[wind]["plants_changed_px"] > 1000, data
        assert fixed[wind]["plants_changed_px"] > 1000, fixed
        # measured (RTX 4070, 640 x 360): 5,777 / 7,015 px against the control's 872 /
        # 1,661 (leaf tips swung past the masks' two-pixel margin)
        assert data[wind]["ground_changed_px"] > 2000, data
        assert data[wind]["ground_changed_px"] > 3 * fixed[wind]["ground_changed_px"], (data, fixed)


def test_backlit_leaves_show_no_stripes_on_high_and_ultra(tmp_path: Path) -> None:
    """#805: the diagonal stripes across backlit leaves at golden hour are ambient occlusion
    banding on FLAT micro-leaves (Qt's pass takes a camera-facing normal), not shadow acne:
    the shadow bias and the shadow map's fit do not change them, AO off removes them. With
    the look's flat-surface bias (``look.AO_FLAT_BIAS_CM``) the stripe share inside the
    cherry's crown stays within 25 % of the AO-free floor on High and Ultra; the control —
    the same look with the bias at 0, as before — lies at least 50 % above it (measured,
    RTX 4070, 1920 x 1080: 0.326 against 0.164 without AO; 0.184 with the bias)."""
    _proc, result = _run(tmp_path / "stripes", "stripes", presets="high,ultra")
    data = result["data"]
    for preset in ("high", "ultra"):
        row = data[preset]
        assert row["ao_bias_cm"] >= 1.0, row
        assert row["look"] <= 1.25 * row["no_ao"], (preset, row)
        assert row["bias0"] >= 1.5 * row["no_ao"], (preset, row)   # the measure sees the defect
