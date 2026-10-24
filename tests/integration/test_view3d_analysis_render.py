"""Analyze in 3D on the real engine (Phase 17 L2, #386) — the render tier (opt-in).

``view3d_analysis_driver.py`` renders top-down truth frames (no tone curve: a pixel is
linear radiance) in a child process with a real window system and measures them.
What only pixels can show:

- the shadow drape DARKENS the ground towards the canvas's shadow blue, by its
  multiplier, in every mood. The first build brightened it: its blend wrote the
  frame's alpha as 1 - a(1 - a), and the view's texture let the window's white
  through — measured rgb(79, 107, 75) over a meadow of rgb(25, 73, 11); the second,
  an unlit colour blended over the ground, went through the mood's exposure and
  brightened the night garden (PF-L3D-06, ADR-063 addendum);
- the hours-of-sun drape keeps the map's row 0 in the SOUTH: north up the truth
  view, the shaded north half of the test map is the dark half at the top;
- the compass's north arrow points up the north-up view;
- an occluder faded by X-ray lets the ground through — a PrincipledMaterial solid
  and a custom-material crown alike, both screen doors — and KEEPS its shadow;
- Cutaway takes the roof part away, leaves the walls, and keeps the roof's shadow.

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
    assert drape[2] / drape[1] > 1.05 * ground[2] / ground[1]
    # the shade layer MULTIPLIES the frame: the linear truth view shows the product
    from open_garden_planner.core.scene3d.drape import SHADE_MULTIPLIER

    expected = [m * g for m, g in zip(SHADE_MULTIPLIER, ground, strict=True)]
    assert drape == pytest.approx(expected, abs=2.0)


@pytest.mark.parametrize("mood", ["noon", "golden", "night"])
def test_the_shade_darkens_in_every_mood_and_brightens_no_pixel(measured: dict, mood: str) -> None:
    """Through the mood's exposure and tone curve: night's exposure is 2.4, and an unlit
    colour blended over the ground turned the night garden lighter (3D review of #386)."""
    change = measured[f"mood_{mood}"]
    assert change["brightest"] <= 2.0, "no pixel under the shade got lighter"
    assert change["darkest"] < -4.0 and change["darkened"] > 2000


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
    # a screen door: about a quarter of the box's pixels, the ground between them — the
    # ground in the box's own shadow, which the faded box still casts
    assert 0.15 * solid[0] < faded[0] < 0.45 * solid[0], "a quarter of the box is drawn"
    assert faded[1] > solid[1] + 5.0 and faded[1] < ground[1], "the shaded ground shows through"
    assert measured["wall_faded"] == pytest.approx(measured["crown_faded"], abs=6.0), (
        "a principled solid and a custom-material crown fade alike")


@pytest.mark.parametrize("name", ["wall", "crown"])
def test_a_faded_occluder_keeps_its_shadow(measured: dict, name: str) -> None:
    """A blended part dropped out of the shadow map (3D review of #386): the screen
    door is opaque, so the shadow north of the box is as dark faded as solid."""
    solid, faded = measured[f"{name}_shadow_solid"], measured[f"{name}_shadow_faded"]
    assert luma(solid) < 0.75 * luma(measured["ground"]), "the probe lies in the box's shadow"
    assert faded == pytest.approx(solid, abs=1.5)


def test_cutaway_takes_the_roof_away_and_leaves_the_walls(measured: dict) -> None:
    assert measured["roof_shown"][0] > 200
    cut = measured["roof_cut"]
    assert not (cut[0] > 1.5 * cut[1]), "no roof red is left: the roof is cut"
    assert measured["walls_cut"] == pytest.approx(measured["walls_shown"], abs=1.0)


def test_cutaway_keeps_the_roofs_shadow(measured: dict) -> None:
    """A hidden roof took its shadow off the lawn (3D review of #386): the cut roof is a
    screen door with nothing left, still a shadow caster."""
    shown, cut = measured["roof_shadow_shown"], measured["roof_shadow_cut"]
    assert luma(shown) < 0.75 * luma(measured["ground"]), "the probe lies in the roof's shadow"
    assert cut == pytest.approx(shown, abs=1.5)


@pytest.mark.parametrize("name", ["cut_roof", "faded_box"])
def test_a_screen_door_part_leaves_no_ao_ghost_at_medium(measured: dict, name: str) -> None:
    """3D review round 2 of #386: the depth pass that fills ambient occlusion's depth
    texture does not run the screen door's discard — a cut roof left a ghost of itself
    and a faded part its whole silhouette, from the Medium preset (the AUTO start) up.
    Screen-door parts collapse in that pass, so they add nothing through AO. Measured:
    at most 1.5 luma with the collapse, up to 26 luma on ~3,000-4,000 px without it."""
    added = measured[f"ao_{name}"]
    assert added["compared"] > 50_000, "most of the frame is compared"
    assert added["over_3"] == 0 and added["max"] <= 3.0
