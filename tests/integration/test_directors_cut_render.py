"""The director's cut on the real engine (Phase 17 L6, #390, ADR-071) — render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins every
decision around a picture (``test_directors_cut.py``); here the ENGINE answers what the
design rests on:

- **a capture IS the view**: same pixels at the view's size, the right size whatever the
  window's size and scale, and the same picture the view shows from that camera;
- **nothing jumps**: the view reads back identically afterwards, its camera untouched;
- **every photo setting off is the view again**, pixel for pixel, and a grade's table does
  not turn the darkest leaves red (Qt's lookup, ``Garden.qml``);
- **a tour's video has its frames**, a time-lapse follows and restores the clock, and the
  agent's picture refuses cleanly and leaves everything as it was.

    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 tests/integration/test_directors_cut_render.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.quick3d_render_support import (
    REPO,
    keep_artifacts,
    render_env,
    render_tier,
)

pytestmark = render_tier

DRIVER = REPO / "tests" / "integration" / "view3d_capture_driver.py"
TIMEOUT_S = 840
#: How far a capture may lie from the view, levels: it is the same render. 0 was measured
#: on Direct3D 11, GPU and WARP.
SAME = 1
#: A grade's identity table against the view: rounding through a 16-level table, measured
#: at mean 0.13, p99 1, at most 5.
TABLE_MEAN, TABLE_MAX = 0.5, 8


def drive(tmp_path: Path, scenario: str, **env: str) -> dict[str, Any]:
    out = tmp_path / scenario
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(DRIVER), "--out", str(out), "--scenario", scenario, "--limit-s", "780"],
        env=render_env(out, **env), capture_output=True, text=True, timeout=TIMEOUT_S, cwd=REPO)
    keep_artifacts(out, proc)
    result_path = out / "result.json"
    assert result_path.is_file(), f"exit {proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    assert "failed" not in result, result.get("trace", result.get("failed"))
    assert proc.returncode == 0
    result["out"] = str(out)
    return result


@pytest.fixture(scope="module")
def host_answers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return drive(tmp_path_factory.mktemp("capture"), "host")


def test_a_capture_at_the_views_size_is_the_view(host_answers: dict[str, Any]) -> None:
    assert host_answers["capture_vs_view"]["max"] <= SAME
    assert host_answers["taken_size"] == host_answers["size"]
    assert host_answers["format"] == "Format_RGBX8888", "an opaque picture"


def test_the_window_is_behind_and_renders_all_the_same(host_answers: dict[str, Any]) -> None:
    """``scripts/quiet_windows``: no focus taken, under the other windows, and every other test
    in this file reads its frames from that very window."""
    behind = host_answers["behind"]
    if behind["checked"]:
        assert behind["no_activation"] and behind["exposed"]
        assert not behind["foreground"]


def test_every_size_comes_out_exact_and_shows_something(host_answers: dict[str, Any]) -> None:
    for name, row in host_answers["sizes"].items():
        width, height = (int(side) for side in name.split("x"))
        assert row["got"] == [width, height], name
        assert not row["flat"], name


def test_another_camera_moves_nothing_on_screen(host_answers: dict[str, Any]) -> None:
    assert host_answers["other_vs_view"]["mean"] > 5.0, "the picture really is from elsewhere"
    assert host_answers["view_after_capture"]["max"] <= SAME
    assert host_answers["camera_kept"]
    assert host_answers["capture_off_after"], "the capture view rests again"


def test_a_capture_from_a_camera_is_what_the_view_shows_from_there(host_answers: dict[str, Any]) -> None:
    assert host_answers["other_vs_view_moved"]["max"] <= SAME


def test_photo_settings_develop_the_picture_and_off_is_the_view_again(host_answers: dict[str, Any]) -> None:
    for name, row in host_answers["photo"].items():
        assert row["mean"] > 1.0, f"{name} changed nothing"
    assert host_answers["no_photo_again"]["max"] <= SAME
    assert host_answers["photo_override"]["max"] <= SAME, "an agent's picture is undeveloped"
    assert host_answers["photo_kept"], "and the owner's settings stay"


def test_the_engine_reported_nothing(host_answers: dict[str, Any]) -> None:
    health = host_answers["health"]
    assert health["ok"] and not health["warnings"] and health["error"] is None


def test_a_grades_table_is_the_view_through_it_and_turns_nothing_red(tmp_path: Path) -> None:
    result = drive(tmp_path, "grades")
    identity = result["identity"]
    assert identity["mean"] <= TABLE_MEAN and identity["max"] <= TABLE_MAX, identity
    assert result["dark_pixels"] > 100, "the frame has dark leaves to judge"
    assert result["dark_red_rise"] <= TABLE_MAX, "R 0 became 57 before Garden.qml's fix"
    grades = result["grades"]
    plain = grades["none"]["means"]
    assert grades["none"]["max"] == 0
    assert grades["golden"]["means"][2] < plain[2] and grades["golden"]["means"][0] > plain[0]
    assert grades["cool"]["means"][2] > plain[2] and grades["cool"]["means"][0] < plain[0]
    mono = grades["mono"]["means"]
    assert max(mono) - min(mono) < 1.0
    assert result["after"]["max"] <= SAME, "and the view comes back"


def test_a_tour_writes_every_frame_and_leaves_the_view_where_it_was(tmp_path: Path) -> None:
    from PyQt6 import QtMultimedia  # noqa: F401 - the tier needs the module to read a video back

    result = drive(tmp_path, "tour")
    tour = result["result"]
    assert tour["ok"], tour
    assert tour["frames"] == result["expected_frames"] and tour["unsettled"] == 0
    assert result["blocker_while_recording"] == "recording"
    assert not result["part_left"]
    video = result["video"]
    assert video["duration_ms"] == 2000 and video["size"] == [1280, 720], video
    assert video["frames"] == result["expected_frames"], video
    assert result["camera_kept"] and result["clock_kept"]


def test_a_time_lapse_follows_the_clock_and_puts_it_back(tmp_path: Path) -> None:
    runs = drive(tmp_path, "timelapse")["runs"]
    day, year = runs["day"], runs["year"]
    assert day["ok"] and year["ok"], runs
    assert day["files"] == year["files"] == 24
    assert day["first_moment"] == ["2026-06-21", "08:00"] and day["last_moment"] == ["2026-06-21", "20:00"]
    assert year["first_moment"][0] == "2026-03-01" and year["last_moment"][0] == "2026-10-31"
    assert day["unsettled"] == year["unsettled"] == 0
    assert day["clock_back"] and year["clock_back"]


def test_the_agents_picture_refuses_cleanly_and_changes_nothing(tmp_path: Path) -> None:
    result = drive(tmp_path, "agent")
    assert result["while_warming"]["refused"] == "warming_up"
    assert result["while_warming"]["ms"] < 100.0, "at once, not after a timeout"
    assert result["in_plan_mode"]["refused"] == "not_open"
    own, other = result["own"], result["other"]
    assert own["image_width_px"] == 640 and other["image_width_px"] == 1024
    assert other["eye"] == [1000.0, -900.0, 700.0] and other["fov_deg"] == 40.0
    assert own["plan_date"] == other["plan_date"] == "2026-06-21"
    assert own["time_of_day"] == "15:00" and own["sun_elevation_deg"] > 0.0
    for kept in ("camera_kept", "clock_kept", "undo_kept", "dirty_kept"):
        assert result[kept], kept
    assert result["back_in_3d"] == 640, "and it works again when the view is back"
