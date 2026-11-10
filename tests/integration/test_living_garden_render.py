"""The living garden on the real engine (Phase 17 L5, #389, ADR-070) — render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins
every decision (``test_scene3d_weather.py``, ``test_scene3d_particles.py``,
``test_living_garden.py``); here the ENGINE answers the issue's two gates and the
look's own questions:

- **with reduced motion the idle frame counter stays at 0** — the product's
  ``LookController``, raining, the garden's life on: once the first build is over,
  no frame is presented (and, the positive control, without reduced motion the
  view draws continuously);
- **the particles cost at most 15 % of a frame at Medium** — the cost of a finished
  frame, read back, interleaved (``view3d_living_driver.scenario_frame_cost``);
- the Beauty Board's living shots (``render_beauty_board.py --living``) render with no
  Qt error, each weather looks different from clear, the night lights brighten the
  night, and the counts stay within the 5,000 particles.

    # Windows (Git Bash) - one driver at a time
    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 -m "perf or not perf"
        tests/integration/test_living_garden_render.py      (one command line)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core.scene3d.particles import MAX_PARTICLES
from tests.integration.quick3d_render_support import (
    REPO,
    driver_messages,
    keep_artifacts,
    render_env,
    render_tier,
)

pytestmark = render_tier

DRIVER = REPO / "tests" / "integration" / "view3d_living_driver.py"
BOARD = REPO / "scripts" / "render_beauty_board.py"
TIMEOUT_S = 840
#: Issue #389: the particles cost at most this share of a frame at Medium. Measured on
#: the RTX 4070 (bench_small, 1280 x 720, interleaved readbacks, 2026-11-02): clear with
#: the garden's life +0.6 %, snow +1.9 %, rain +3.7 % over the look without L5.
MAX_COST = 0.15


def _run(command: list[str], out: Path, **env: str) -> subprocess.CompletedProcess[str]:
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command, env=render_env(out, **env), capture_output=True, text=True, timeout=TIMEOUT_S,
        cwd=REPO)
    keep_artifacts(out, proc)
    return proc


def run_scenario(out: Path, scenario: str, **arguments: str
                 ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [sys.executable, str(DRIVER), "--out", str(out), "--scenario", scenario,
               "--watchdog-s", str(TIMEOUT_S - 60)]
    for key, value in arguments.items():
        command += ["--arg", f"{key}={value}"]
    # presented by timer: no scenario may depend on whether the display is awake
    proc = _run(command, out, QT_D3D_NO_VBLANK_THREAD="1")
    file = out / "result.json"
    result = json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}
    if result:
        result["qt_messages"] = driver_messages(proc.stderr)
    return proc, result


def _ok(proc: subprocess.CompletedProcess[str], result: dict[str, Any]) -> dict[str, Any]:
    assert proc.returncode == 0 and result.get("status") == "ok", (proc.returncode, result.get("error"),
                                                                    proc.stderr[-2000:])
    assert not result["qt_messages"]["errors"], result["qt_messages"]["errors"]
    return result["data"]


@pytest.mark.perf
def test_with_reduced_motion_the_idle_frame_counter_stays_at_zero(tmp_path: Path) -> None:
    """Issue #389's gate — raining, life on, the product's controller."""
    data = _ok(*run_scenario(tmp_path / "idle", "idle"))
    reduced, animated = data["reduced"], data["animated"]
    assert reduced["settled_after_s"] is not None, "the first build went quiet"
    assert reduced["frames_during_quiet"] == 0, reduced
    assert reduced["wind_time"] == [0.0, 0.0] and reduced["animating"] is False
    assert reduced["precip_kind"] == 1 and reduced["precip_loads"] == 1, "it IS raining"
    assert reduced["health"]["ok"] and not reduced["health"]["qml_warnings"]
    # the positive control: the same scene, motion on, draws on and on
    assert animated["settled_after_s"] is None and animated["frames_during_quiet"] > 30, animated
    assert animated["wind_time"][1] > animated["wind_time"][0]


def test_a_second_ambient_load_on_a_live_host_draws(tmp_path: Path) -> None:
    """The product reloads the ambient buffer into the SAME live geometry on every date
    step and every light edit. ADR-069 withdrew an in-place reload (#531) that drew a
    replaced geometry as nothing while still picking it: here a bulb's glow shows at A;
    reloaded WHILE SHOWN it moves to B (the product's common path — a date step, a lamp
    moved); it is gone after an empty load, and shows at B again after the next (a load
    while hidden, then shown). In CI on OpenGL and on Direct3D 11 (``ci.yml``)."""
    data = _ok(*run_scenario(tmp_path / "reload", "reload"))
    frames = data["frames"]
    for name in ("a", "a2", "b"):
        assert frames[name]["pixels"] >= 20, (name, frames)
    assert frames["none"]["pixels"] < frames["a"]["pixels"] / 4, frames

    def apart(one: str, other: str) -> float:
        (x0, y0), (x1, y1) = frames[one]["middle"], frames[other]["middle"]
        return abs(x0 - x1) + abs(y0 - y1)

    assert apart("a", "a2") > 40.0, f"a reload while shown moved the glow: {frames}"
    assert apart("a2", "b") < 15.0, f"the same bulb at B, shown either way: {frames}"
    assert data["ambient_loads"] >= 4


@pytest.mark.perf
def test_the_particles_cost_at_most_fifteen_percent_of_a_frame_at_medium(tmp_path: Path) -> None:
    data = _ok(*run_scenario(tmp_path / "cost", "frame_cost"))
    assert data["software"] is False, "the gate is the GPU's (WARP draws on demand only)"
    for weather in ("clear", "rain", "snow"):
        assert data["cost"][weather] <= MAX_COST, (weather, data["cost"], data["readback_ms"])
    assert data["precipitation_loads"] == 1, "one load for the host's life: a weather builds nothing"
    assert data["health"]["ok"] and not data["health"]["qml_warnings"]


# L7 (#391, 3D review): the weather's gates hold on BOTH skies — the atmosphere's cloud
# deck brightened a cloudy evening before its clouds got their own light scale
@pytest.mark.parametrize("sky", ["painted", "atmosphere"])
def test_the_living_board_renders_every_shot(tmp_path: Path, sky: str) -> None:
    out = tmp_path / "board"
    proc = _run([sys.executable, str(BOARD), "--out", str(out), "--size", "640x360",
                 "--shots", "none", "--living", "--moods", "--dusk", "--presets", "medium",
                 "--sky", sky, "--watchdog-s", str(TIMEOUT_S - 60)], out)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0 and metrics["status"] == "ok", (proc.returncode, metrics.get("error"))
    assert metrics["qt_messages"]["counts"].get("error", 0) == 0
    rows = {row["shot"]: row for row in metrics["living"]}
    assert set(rows) == {"overcast", "rain", "snow", "morning_dew", "autumn_leaves",
                         "butterflies", "fireflies", "lights_night"}
    moods = {name: row["mood"] for name, row in rows.items()}
    assert moods["overcast"] == "overcast" and moods["rain"] == "rain" and moods["snow"] == "snow"
    assert moods["morning_dew"] == "morning_dew" and moods["lights_night"] == "night"
    for row in rows.values():
        assert row["build_date"] == row["date"], row["shot"]
        assert row["precip_particles"] + row["ambient_particles"] <= MAX_PARTICLES
        assert not row["build_failures"], row["shot"]
    assert rows["autumn_leaves"]["ambient_by_kind"]["leaf"] > 0
    assert rows["butterflies"]["ambient_by_kind"]["butterfly"] > 0
    assert rows["fireflies"]["life"]["fireflies"] > 0.5 and rows["fireflies"]["ambient_by_kind"]["firefly"] > 0
    assert rows["lights_night"]["lamps"] == 4 and rows["lights_night"]["lamp_lights"] == 4
    # snow lies white: the snowy December frame is the brightest of them
    assert rows["snow"]["mean_luma"] > rows["overcast"]["mean_luma"]
    # #687: and on the built tops too - roofs, a bed's soil, decks, the trampoline's mat
    # (ADR-070 decision 6 left them bare); whitened pixels against the same frame bare
    tops = rows["snow"]["snow_tops"]
    assert tops["share"] >= 0.02 and tops["luma"] >= tops["bare_luma"] + 40.0, tops
    # a cloudy evening is an evening (3D review of L5, round 3: an overcast sunset was 98 % as
    # bright as noon), and it fades into the night with no step at sunset — every weather
    # (partly cloudy since L7: between the clear evening and the overcast one)
    for weather in ("partly_cloudy", "overcast", "rain", "snow"):
        dusk = metrics[f"dusk_{weather}"]["medium"]
        assert dusk["monotone"], (weather, dusk["rises"])
        # #802: the garden's own light fades too (the golden-hour camera; the clear evening's
        # default framing is gated in test_view3d_looks_render.py)
        assert dusk["ground_monotone"], (weather, dusk["ground_rises"])
        assert dusk["sunset_step"] <= dusk["day_ramp_max_step"], (weather, dusk)
        # #695: the sky-facing set-sun probe under this weather — the meadow camera hid
        # the sun behind the poplar, and a black disc went unseen for three reviews
        assert dusk["sky_dusk_ok"], (weather, dusk["sky_dusk"])
        assert all(row["measured"] for row in dusk["sky_dusk"]), (weather, dusk["sky_dusk"])
        assert min(row["dip_luma"] for row in dusk["sky_dusk"]) >= -10.0, (
            weather, dusk["sky_dusk"])
        evening = metrics[f"moods_{weather}"]["medium"]["sunset_over_noon"]
        # measured at medium: 0.761 / 0.781 / 0.674 (ADR-070's high-preset figures: 0.77 /
        # 0.79 / 0.68); 0.98 before the round-3 fix
        assert evening["luminance"] < 0.85, (weather, evening)
    # #687: under a full cloud the sky is the light, and what an object hides of it grounds
    # it: the box's lit-side foot at least twice the clear look's (measured at this size
    # 0.144 / 0.146 / 0.121 against clear's 0.044; 0.060 / 0.059 / 0.053 before), and open
    # flat ground does not occlude itself (far meadow 0.21 / 0.07 / 0.0; 1.0 / 0.93 / 2.0)
    occlusion = metrics["living_occlusion"]["medium"]
    clear_foot = occlusion["clear"]["contact"]["S"]["contact"]
    for weather in ("overcast", "rain", "snow"):
        row = occlusion[weather]
        assert row["contact"]["S"]["contact"] >= 2.0 * clear_foot, (weather, row["contact"], clear_foot)
        assert row["far_darkening"] is not None and row["far_darkening"] <= 0.75, (weather, row)
        assert row["rim"] is not None and row["rim"] <= 3.0, (weather, row)


def test_under_cloud_open_snow_has_no_rim_and_stays_with_low(tmp_path: Path) -> None:
    """#687 and its comment, at the board's own frame (high, 1280 x 720, the family garden,
    where the survey saw it): under snow the open ground is within 3 luma of the Low preset
    (no occlusion) and no light rim above 3 runs above a silhouette — the clear values gave
    -17 and 10.1, the meadow occluding itself everywhere but beside a nearer object; and an
    overcast box's lit-side foot is at least the clear look's (the issue's gate, on the side
    where occlusion alone darkens in both looks: the shadow side's is the cast shadow)."""
    out = tmp_path / "board"
    plan = REPO / "src" / "open_garden_planner" / "resources" / "examples" / "family-garden.ogp"
    proc = _run([sys.executable, str(BOARD), "--plan", str(plan), "--out", str(out),
                 "--size", "1280x720", "--shots", "none", "--living", "--presets", "high",
                 "--watchdog-s", str(TIMEOUT_S - 60)], out)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0 and metrics["status"] == "ok", (proc.returncode, metrics.get("error"))
    occlusion = metrics["living_occlusion"]["high"]
    snow = occlusion["snow"]
    assert abs(snow["snow_minus_low"]) <= 3.0, snow            # measured -2.93 (was -17.0)
    for weather in ("overcast", "rain", "snow"):
        row = occlusion[weather]
        assert row["rim"] is not None and row["rim"] <= 3.0, (weather, row)   # 1.92 / 1.21 / 2.07
        assert row["far_darkening"] <= 3.0, (weather, row)                    # 2.64 / 1.93 / 2.79
    clear, overcast = occlusion["clear"]["contact"], occlusion["overcast"]["contact"]
    assert overcast["S"]["contact"] >= clear["S"]["contact"], (overcast, clear)   # 0.0395 / 0.0223
    # the clear look keeps the spike's occlusion (#687 changes no clear frame): its rim is
    # recorded, not judged (8.0 measured; a follow-up for the owner)
    assert occlusion["clear"]["rim"] is not None
