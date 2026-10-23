"""Analyze in 3D on the real engine (Phase 17 L2, #386) — the render tier (opt-in).

``view3d_analysis_driver.py`` renders top-down truth frames (no tone curve: a pixel is
linear radiance) in a child process with a real window system and measures them.
What only pixels can show:

- the drape DARKENS the ground towards the canvas's shadow blue. The first build
  brightened it: its blend wrote the frame's alpha as 1 - a(1 - a), and the view's
  texture let the window's white through — measured rgb(79, 107, 75) over a meadow
  of rgb(25, 73, 11) (PF-L3D, ADR-059 addendum "Analyze in 3D");
- the hours-of-sun drape keeps the map's row 0 in the SOUTH: north up the truth
  view, the shaded north half of the test map is the dark half at the top;
- the compass's north arrow points up the north-up view;
- an occluder faded by X-ray lets the ground through — a PrincipledMaterial solid
  and a custom-material crown alike (the crown blends only while it fades);
- Cutaway takes the roof part away and leaves the walls.

Run it on the GPU and on WARP (``QSG_RHI_PREFER_SOFTWARE_RENDERER=1``); the unit and
integration tiers hold everything that is not a pixel.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.quick3d_render_support import REPO, render_env, render_tier

pytestmark = render_tier
DRIVER = Path(__file__).with_name("view3d_analysis_driver.py")


def luma(rgb: list[float]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


@pytest.fixture(scope="module")
def measured(tmp_path_factory: pytest.TempPathFactory) -> dict:
    out = tmp_path_factory.mktemp("analysis")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, str(DRIVER), str(out)], env=render_env(out), capture_output=True,
        text=True, timeout=600, cwd=REPO)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-3000:]
    data = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert data["qt_errors"] == 0, "a shader or QML error: the frames are not the scene"
    return data


def test_the_shadow_drape_darkens_the_ground_towards_its_blue(measured: dict) -> None:
    ground, drape = measured["ground"], measured["shadow_drape"]
    assert luma(drape) < 0.8 * luma(ground)
    assert drape[2] / drape[1] > ground[2] / ground[1] + 0.06
    # the blend of the canvas's colour at its own alpha, within a few grey levels
    from open_garden_planner.core.scene3d.color import srgb8_to_linear
    from open_garden_planner.core.scene3d.drape import SHADOW_RGBA

    *colour, alpha = srgb8_to_linear(SHADOW_RGBA)
    expected = [alpha * 255.0 * c + (1.0 - alpha) * g for c, g in zip(colour, ground, strict=True)]
    assert drape == pytest.approx(expected, abs=4.0)


def test_the_hours_of_sun_drape_keeps_row_zero_in_the_south(measured: dict) -> None:
    north, south = measured["sun_hours_north"], measured["sun_hours_south"]
    assert luma(north) < 0.6 * luma(south), "the shaded north half is the dark one"
    assert north[2] > north[0], "deep shade is the ramp's indigo end"


def test_the_compass_points_north_up_the_truth_view(measured: dict) -> None:
    top, bottom = measured["north_arrow_rows"]
    assert bottom < measured["frame_rows"] * 0.25, "the red north arrow is at the top"
    assert top >= 0


@pytest.mark.parametrize("name", ["wall", "crown"])
def test_a_faded_occluder_lets_the_ground_through(measured: dict, name: str) -> None:
    solid, faded, ground = measured[f"{name}_solid"], measured[f"{name}_faded"], measured["ground"]
    assert solid[0] > 200 and solid[1] < 30, "the box is drawn in its red"
    assert faded[0] < 0.6 * solid[0] and faded[1] > 0.6 * ground[1], "the ground shows through"
    assert measured["wall_faded"] == pytest.approx(measured["crown_faded"], abs=3.0), (
        "a principled solid and a custom-material crown fade alike")


def test_cutaway_takes_the_roof_away_and_leaves_the_walls(measured: dict) -> None:
    assert measured["roof_shown"][0] > 200
    assert measured["roof_cut"] == pytest.approx(measured["ground"], abs=2.0)
    assert measured["walls_cut"] == pytest.approx(measured["walls_shown"], abs=1.0)
