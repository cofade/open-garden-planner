"""The 3D workspace in the REAL app on a real graphics device (Phase 17 L1.3, ADR-065).

Render tier (``OGP_RENDER3D=1``). Every test here starts the app's own ``main()`` in
a child process — ``workspace_gate_child.py``, with ``OGP_QUICK3D=1``, on a bench
plan, on a settings store that is never the developer's (proven in the default
tier: ``test_workspace_gate.py``) — lets a scenario run INSIDE it, and judges what
the process reported. Nothing of Qt Quick is ever shown in this process.

The gates of the story that need pixels, a device or a clock:

- **G2** edit → finished frame, p95 ≤ 50 ms on the small bench plan (a real GPU);
- **G3** (twin) no edit moves the camera of the real host; a document change does;
- **G5** the app closes clean with 3D visible, hidden, and never opened;
- **G6** (twin) a start that died → compatibility mode with its notice, on the
  software adapter by Qt's own account → "try hardware" → hardware again;
- **G7** the leak half of ADR-048 criterion 10: the A/B memory soak — no readback in
  its measured loop; once with the view presenting and once with its frames withheld —
  with its positive control, and DXGI's reading of dedicated GPU memory;
- **G8** Qt WebEngine renders before AND after the 3D host exists;
- **G11** the 2D pan step beside the live 3D view costs at most 1.3 times what it
  costs alone.

How the numbers are taken is ``workspace_gate_measure.py``'s business (and its
docstring's); the BOUNDS are here. A bound that only a hardware adapter can meet
(G2) is judged on a hardware adapter and reported on a software one.

The frozen gate exe runs the three G5 scenarios when ``OGP_WORKSPACE_GATE_EXE``
names it (the build is not this test's job: ``installer/workspace_gate.spec``).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration.quick3d_render_support import render_tier
from tests.integration.workspace_gate_support import PLANS, GateRun, run_gate

pytestmark = render_tier
#: G2 and G11 read the wall clock: they carry ``perf`` as well (ADR-058) and run only
#: when it is asked for — the whole file on the GPU is
#: ``OGP_RENDER3D=1 pytest tests/integration/test_view3d_workspace_render.py -m "perf or not perf" -n 0``.

#: ADR-048, criterion 10, fixed before run v9 was read: the Theil–Sen slope of committed
#: memory over the second half of 20 reloads stays below this many MB per reload.
LEAK_BOUND_MB_PER_RELOAD = 10.0
RELOADS = 20
#: Gate G2.
EDIT_TO_FRAME_P95_MS = 50.0
#: Gate G11.
PAN_RATIO = 1.3
SOFTWARE_ADAPTERS = ("Basic Render", "llvmpipe", "SwiftShader", "softpipe")
#: Everything measured in this module, for the report (printed when the module ends;
#: written to ``OGP_RENDER3D_ARTIFACTS`` when that names a directory).
MEASURED: dict[str, Any] = {}


def _software(adapter: object) -> bool:
    return adapter is None or any(name in str(adapter) for name in SOFTWARE_ADAPTERS)


def _clean(run: GateRun) -> GateRun:
    assert run.problems() == [], f"{run.problems()}\n{run.stderr[-3000:]}"
    # a gate run talks to nobody: the hook answers every request with "offline" — so no
    # close gate says anything about a close DURING the frozen app's update check
    # (workspace_gate_hook.py, point 4: a defect of the shipped app, a follow-up issue)
    assert run.report["network"] == "offline"
    return run


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("workspace-gate")


@pytest.fixture(scope="module", autouse=True)
def _report() -> Iterator[None]:
    yield
    text = json.dumps(MEASURED, indent=1, default=str)
    print(f"\n[workspace render tier] measured:\n{text}")  # noqa: T201 - the tier's report
    target = os.environ.get("OGP_RENDER3D_ARTIFACTS")
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / "workspace-render-measured.json").write_text(text, encoding="utf-8")


# ── G5: the app closes clean — 3D never opened, visible, hidden ──────────────


@pytest.fixture(scope="module")
def never(scratch: Path) -> GateRun:
    return run_gate(scratch, "never")


@pytest.fixture(scope="module")
def visible(scratch: Path) -> GateRun:
    return run_gate(scratch, "visible")


@pytest.fixture(scope="module")
def hidden(scratch: Path) -> GateRun:
    return run_gate(scratch, "hidden")


def test_the_app_closes_clean_when_3d_was_never_opened(never: GateRun) -> None:
    shown = _clean(never).step("shown")
    assert shown["mode"] == "plan" and shown["state"] == "not_started"
    assert shown["quick_modules"] == [], "nothing of Qt Quick is imported before 3D is asked for"
    assert "host_state" not in shown and shown.get("guard_files", []) == []
    assert never.step("closed")["accepted"] is True


def test_the_app_closes_clean_with_3d_visible(visible: GateRun) -> None:
    """Gate G5, and the workflow's render twin: the plan opened by ``main()`` is in the
    real engine, drawn, on the adapter Qt names — and the start marker is gone."""
    shown = _clean(visible).step("visible")
    assert shown["mode"] == "3d" and shown["state"] == "running"
    assert shown["host_state"] == "live" and shown["frames_presented"] >= 1
    assert shown["parts"] >= shown["records"] == 98
    assert shown["qml_warnings"] == [] and shown["scene_graph_error"] is None
    assert shown["off_gui_thread"] == 0, "no Python ran on Qt's render thread"
    assert shown["guard_mode"] == "hardware" and shown["guard_files"] == []
    assert shown["compat"] == "" and shown["message"] == "" and shown["status"] == ""
    assert shown["recoveries"] == 0 and shown["last_error"] is None
    assert "PyQt6.QtQuick3D" in shown["quick_modules"]
    entered = visible.step("entered")
    assert entered["guard_files"] != [], "the start was marked before the engine was built"
    assert visible.qt["adapter"], "Qt named the adapter it renders on"
    MEASURED["G5"] = {"adapter": visible.qt["adapter"], "graphics_api": shown["graphics_api"],
                      "qt_messages": visible.qt["counts"]}


def test_the_app_closes_clean_with_3d_hidden_again(hidden: GateRun) -> None:
    last = _clean(hidden).step("hidden")
    assert last["mode"] == "plan" and last["state"] == "running"
    assert last["host_state"] == "hidden" and last["active"] is False
    assert last["parts"] >= 98, "a hidden view keeps its scene"
    assert hidden.step("closed")["accepted"] is True


@pytest.mark.parametrize("scenario", ["never", "visible", "hidden"])
def test_the_app_closes_clean_when_its_frames_are_paced_by_the_display(
        scratch: Path, scenario: str) -> None:
    """Review 1, P2-12: the three close gates as the PRODUCT starts — without
    ``QT_D3D_NO_VBLANK_THREAD`` (every other gate of this module runs with it, so that
    no scenario depends on whether this machine's display is awake).

    What these prove LESS than they seem to: paced by the display, a view on a
    SLEEPING display presents its first frame and no more. "visible" then closes a
    view that has presented once — a real case, and the one the timer-paced gate
    cannot reach — but not a view that presents frame after frame on an awake display
    while it closes. That stays on the owner's checklist ("close the app with 3D
    visible", the display on)."""
    run = _clean(run_gate(scratch, scenario, timer_paced=False))
    assert run.step("closed")["accepted"] is True
    if scenario == "visible":
        shown = run.step("visible")
        assert shown["state"] == "running" and shown["frames_presented"] >= 1
        assert shown["parts"] >= shown["records"] == 98 and shown["guard_files"] == []
    elif scenario == "hidden":
        last = run.step("hidden")
        assert last["host_state"] == "hidden" and last["active"] is False
    MEASURED.setdefault("G5_paced_by_the_display", {})[scenario] = {
        "adapter": run.qt["adapter"], "qt_messages": run.qt["counts"]}


@pytest.mark.parametrize("scenario", ["never", "visible", "hidden"])
def test_the_frozen_app_closes_clean_too(scratch: Path, scenario: str) -> None:
    exe = os.environ.get("OGP_WORKSPACE_GATE_EXE")
    if not exe:
        pytest.skip("set OGP_WORKSPACE_GATE_EXE to the gate build's exe (installer/workspace_gate.spec)")
    run = _clean(run_gate(scratch, scenario, command=[exe]))
    # it WAS the frozen exe, the hook ran before the app (a runtime hook), and every
    # store this process built is the throw-away one — by Qt's own account of each
    assert run.report["frozen"] is True and run.report["late"] is False
    assert run.report["stores"] == [["cofade_test", run.store]], run.report["stores"]
    assert run.report["production"] not in run.report["stores"]
    closed = run.step("closed")
    assert closed["accepted"] is True and closed["geometry_saved"] is True
    assert [Path(entry).name for entry in closed["recent_files"]] == ["bench_small.ogp"]
    if scenario != "never":
        shown = run.step("visible")
        assert shown["state"] == "running" and shown["parts"] >= 98 and shown["guard_files"] == []
    # the frozen app's update check (two seconds after its window exists) was answered
    # "offline": at most one request, and none when the run closed before it was made
    assert run.report["network_calls"] <= 1
    MEASURED.setdefault("G5_frozen", {})[scenario] = {
        "adapter": run.qt["adapter"], "qt_messages": run.qt["counts"],
        "seconds": run.report["seconds"], "update_checks_answered_offline": run.report["network_calls"]}


# ── G6: a start that died, compatibility mode, and the way back ──────────────


@pytest.fixture(scope="module")
def compat(scratch: Path) -> dict[str, GateRun]:
    """Four starts of the app on ONE store (its start guard lives in the store's own
    folder): one that dies inside its first 3D start, the next one, one that asks for
    hardware again, and the one after."""
    store = f"Open Garden Planner Gate compat {uuid.uuid4().hex[:8]}"
    return {
        "died": run_gate(scratch, "die_in_init", store=store),
        "after": run_gate(scratch, "visible", store=store),
        "asked": run_gate(scratch, "try_hardware", store=store),
        "back": run_gate(scratch, "visible", store=store),
    }


def test_a_start_that_died_leaves_its_marker(compat: dict[str, GateRun]) -> None:
    died = compat["died"]
    assert died.returncode == 3 and died.steps[-1] == "dying", died.steps
    dying = died.step("dying")
    assert dying["guard_mode"] == "hardware" and len(dying["guard_files"]) == 1
    assert dying["guard_files"][0].startswith("view3d-init-")


def test_the_next_start_is_in_compatibility_mode_and_says_so(compat: dict[str, GateRun]) -> None:
    after = _clean(compat["after"])
    shown = after.step("visible")
    assert shown["state"] == "running" and shown["parts"] >= 98
    assert shown["guard_mode"] == "software" and shown["guard_reason"] == "previous_start_died"
    assert shown["prefers_software"] is True
    assert "compatibility mode" in shown["compat"] and "did not start properly" in shown["compat"]
    assert shown["guard_files"] == ["view3d-compat.flag"], "the marker of the dead start is gone"
    if sys.platform == "win32":
        # Qt's own account of the device this window renders on: the software adapter
        assert "Basic Render" in str(after.qt["adapter"]), after.qt["adapter"]
    MEASURED.setdefault("G6", {})["adapter_in_compatibility_mode"] = after.qt["adapter"]


def test_try_hardware_takes_effect_with_the_next_start(compat: dict[str, GateRun]) -> None:
    asked = _clean(compat["asked"])
    assert asked.step("button")["visible"] is True
    during = asked.step("asked_for_hardware")
    assert during["guard_mode"] == "software", "this session keeps the mode it started in"
    assert "next time" in during["compat"] and during["guard_files"] == []
    back = _clean(compat["back"]).step("visible")
    assert back["guard_mode"] == "hardware" and back["prefers_software"] is False
    assert back["compat"] == "" and back["guard_files"] == [] and back["state"] == "running"
    MEASURED.setdefault("G6", {})["adapter_after_try_hardware"] = compat["back"].qt["adapter"]


# ── G2: edit → finished frame ────────────────────────────────────────────────


def _edit_numbers(run: GateRun) -> dict[str, Any]:
    step = run.step("edit_latency")
    keys = ("total_ms", "edit_ms", "wait_ms", "snapshot_ms", "apply_ms", "grab_ms",
            "idle_grab_ms", "to_pass_done_ms", "by_kind")
    return {"adapter": run.qt["adapter"], "pane_px": step["pane_px"], "window_px": step["window_px"],
            "records": step["records"], "measured": step["measured"], "misses": step["misses"],
            **{key: step[key] for key in keys}}


@pytest.mark.perf
def test_an_edit_is_in_a_finished_frame_within_50_ms_on_the_small_plan(scratch: Path) -> None:
    """Gate G2: 120 scripted edits of seven kinds in Split mode at 1600 x 900; the clock
    runs from before the app's own command to a finished readback of the 3D view taken
    the moment the pipeline's pass committed."""
    run = _clean(run_gate(scratch, "edit_latency", width=1600, height=900, edits=120))
    numbers = _edit_numbers(run)
    MEASURED["G2_bench_small"] = numbers
    step = run.step("edit_latency")
    assert step["misses"] == 0 and step["measured"] == step["edits"] >= 100
    assert step["edits_that_reached_the_engine"] == step["measured"], "every edit is a real one"
    assert {"add", "delete", "move", "recolour", "resize", "undo", "redo"} <= set(step["by_kind"])
    if _software(run.qt["adapter"]):
        pytest.skip(f"G2's bound is for a real GPU; measured on {run.qt['adapter']}: "
                    f"p95 {numbers['total_ms']['p95']} ms")
    assert numbers["total_ms"]["p95"] <= EDIT_TO_FRAME_P95_MS, numbers["total_ms"]


@pytest.mark.perf
def test_the_large_plan_is_measured_and_not_judged(scratch: Path) -> None:
    run = _clean(run_gate(scratch, "edit_latency", plan=PLANS / "bench_large.ogp",
                          width=1600, height=900, edits=120))
    MEASURED["G2_bench_large"] = _edit_numbers(run)
    assert run.step("edit_latency")["misses"] == 0


# ── G3 (twin): the camera rule on the real host ──────────────────────────────


def test_no_edit_moves_the_real_cameras_and_a_new_document_does_once(scratch: Path) -> None:
    run = _clean(run_gate(scratch, "camera_rule", edits=100))
    assert run.step("user_zoomed")["settled"] is True
    edits = run.step("edits_done")
    assert edits["edits"] == 100 and edits["moved_by"] == []
    assert edits["cam_version"] == edits["cam_version_before"], "the engine's camera was not set once"
    assert {"add", "delete", "move", "recolour", "resize", "undo", "redo", "date", "time"} <= set(
        edits["kinds"])
    after = run.step("document_changed")
    assert after["cam_version"] == edits["cam_version"] + 1, "a new document frames — once"
    assert after["pose_changed"] is True and after["cam_moved"] is True
    MEASURED["G3"] = {"edits": edits["edits"], "kinds": edits["kinds"],
                      "cam_version": [edits["cam_version_before"], edits["cam_version"],
                                      after["cam_version"]]}


# ── G7: the memory soak ──────────────────────────────────────────────────────
#
# The measured loop takes NO frame from the host (``grabs="none"``, the scenario's
# default): a readback renders a frame that is never presented, and a soak that reads
# back every cycle measures the readback. One frame before the loop and one after it
# prove the picture. The gate is judged twice: with the view PRESENTING and with its
# frames WITHHELD (shown, exposed, nothing draws it — the display asleep).


def _soak(scratch: Path, variant: str, **options: Any) -> dict[str, Any]:
    run = _clean(run_gate(scratch, "soak", variant=variant, reloads=RELOADS, **options))
    step = run.step("soak")
    keys = ("variant", "frames", "grabs", "release", "reloads", "start_mb", "curve_mb",
            "slope_second_half_mb_per_reload", "slope_all_mb_per_reload", "growth_mb",
            "after_the_last_frame_mb", "geometry_uploads", "kept_mb", "parts", "parts_after",
            "cache_releases", "in_the_loop", "frames_presented_per_reload", "presented_again",
            "same_image_at_the_end", "gpu_curve_mb", "gpu_slope_second_half_mb_per_reload")
    numbers = {key: step.get(key) for key in keys}
    numbers["adapter"] = run.qt["adapter"]
    numbers["gpu_before_mb"] = step["gpu_before"].get("process_dedicated_mb")
    numbers["gpu_after_mb"] = step["gpu_after"].get("process_dedicated_mb")
    numbers["gpu_reading"] = ("IDXGIAdapter3::QueryVideoMemoryInfo, local segment, this process"
                              if step["gpu_before"].get("available") else
                              step["gpu_before"].get("why", "not available"))
    name = "/".join([variant, *(f"{key}={options[key]}" for key in ("frames", "grabs", "release",
                                                                   "ground")
                                if key in options)])
    MEASURED.setdefault("G7", {})[name] = numbers
    return numbers


def _took_no_frame(soak: dict[str, Any]) -> None:
    assert soak["grabs"] == "none" and soak["in_the_loop"]["frames_read_back"] == 0
    assert soak["same_image_at_the_end"] is True, "the ONE frame after the loop is the one before it"
    assert soak["parts_after"] == soak["parts"]


# The gate measures what a destroyed MODEL leaves behind, as it did before the ground
# bake existed: with the bake ON, Qt Quick 3D 6.11's QSSGBufferManager::clear() skips
# QHash entries and leaks about half the tile textures on every release (#532, a Qt bug
# read in its source and proven by measurement). That known leak is reported below, with a
# ceiling that catches it getting worse; it is not this gate's to judge.


@pytest.fixture(scope="module")
def soak_rebuild_on(scratch: Path) -> dict[str, Any]:
    return _soak(scratch, "rebuild_on", ground="off")


def test_twenty_rebuilds_of_the_engine_scene_stay_under_the_leak_bound(
        soak_rebuild_on: dict[str, Any]) -> None:
    """ADR-048 criterion 10's leak half, in the production host, the view PRESENTING:
    every reload tears the engine scene down and builds every Model and geometry again."""
    soak = soak_rebuild_on
    _took_no_frame(soak)
    assert soak["geometry_uploads"] == RELOADS * soak["parts"], "every reload rebuilt everything"
    assert min(soak["frames_presented_per_reload"]) >= 1, "every rebuild was drawn and presented"
    assert soak["slope_second_half_mb_per_reload"] < LEAK_BOUND_MB_PER_RELOAD, soak["curve_mb"]


def test_the_workspace_released_the_engines_caches_after_every_rebuild(
        soak_rebuild_on: dict[str, Any]) -> None:
    soak = soak_rebuild_on
    assert soak["cache_releases"] == RELOADS
    assert soak["same_image_at_the_end"] is True, "twenty releases changed a pixel"


def test_dedicated_gpu_memory_does_not_grow_with_the_rebuilds(soak_rebuild_on: dict[str, Any]) -> None:
    """What private bytes cannot see (ADR-048: "on a discrete GPU the gate is blind to
    VRAM leaks"): DXGI's own figure for THIS process on the adapter's local segment."""
    soak = soak_rebuild_on
    if soak["gpu_slope_second_half_mb_per_reload"] is None:
        pytest.skip(f"no dedicated-GPU-memory reading here: {soak['gpu_reading']}")
    assert soak["gpu_slope_second_half_mb_per_reload"] < LEAK_BOUND_MB_PER_RELOAD, soak["gpu_curve_mb"]


def test_the_same_rebuilds_stay_under_the_bound_in_a_view_that_presents_nothing(
        scratch: Path) -> None:
    """The second slope of the gate: the same twenty rebuilds while the view presents no
    frame (the display asleep, a session that does not present — made on purpose: the
    view's expose, update and paint events are eaten). The pipeline goes on applying;
    nothing draws; and when the view presents again it shows the plan as it is."""
    soak = _soak(scratch, "rebuild_on", frames="withheld", ground="off")
    _took_no_frame(soak)
    spell = soak["in_the_loop"]
    assert spell["frames_presented"] == 0 and spell["paint_events_eaten"] > 0, "the device"
    assert soak["geometry_uploads"] == RELOADS * soak["parts"], "the pipeline was not held back"
    assert spell["parts_at_the_end"] == soak["parts"]
    assert soak["slope_second_half_mb_per_reload"] < LEAK_BOUND_MB_PER_RELOAD, soak["curve_mb"]
    assert soak["presented_again"] is True


def test_reloads_that_rebuild_nothing_stay_flat(scratch: Path) -> None:
    soak = _soak(scratch, "rebuild_off")
    _took_no_frame(soak)
    assert soak["geometry_uploads"] == 0, "the same plan again: no Model is rebuilt"
    assert soak["slope_second_half_mb_per_reload"] < LEAK_BOUND_MB_PER_RELOAD, soak["curve_mb"]


def test_the_positive_control_fails_on_exactly_that_gate(scratch: Path) -> None:
    """25 MB kept alive per reload, on the same machine, through the same measurement:
    the gate must see it — or a pass above means nothing."""
    soak = _soak(scratch, "control")
    assert soak["kept_mb"] == 25 * RELOADS and soak["in_the_loop"]["frames_read_back"] == 0
    assert soak["slope_second_half_mb_per_reload"] >= LEAK_BOUND_MB_PER_RELOAD, soak["curve_mb"]


def test_what_the_soak_reads_without_the_release_is_reported(scratch: Path) -> None:
    """The A of the A/B, never judged: the same soak — presenting, no readback — with
    the workspace's release out of reach. On Direct3D 11 with a hardware adapter it
    read 19 MB per reload (ADR-065); on another device it may read anything — which
    is why it is a number in the report and not a bound. If it ever reads like the
    run WITH the release, Qt has stopped keeping what it kept, and the release can go."""
    soak = _soak(scratch, "rebuild_on", release="off")
    assert soak["cache_releases"] == 0 and soak["geometry_uploads"] == RELOADS * soak["parts"]
    assert soak["in_the_loop"]["frames_read_back"] == 0


def test_a_release_inside_the_pass_holds_on_a_real_device_too(scratch: Path) -> None:
    """The "at once" rule — what an animated date runs into — releases from INSIDE the
    pipeline's pass, right after Models were destroyed and created. Here every
    rebuild is such a flood (the threshold set to 1): no poll, no quiet moment."""
    soak = _soak(scratch, "rebuild_on", release="flood", ground="off")
    _took_no_frame(soak)
    assert soak["cache_releases"] >= RELOADS, "every rebuild released with its pass"
    assert soak["geometry_uploads"] == RELOADS * soak["parts"]
    assert soak["slope_second_half_mb_per_reload"] < LEAK_BOUND_MB_PER_RELOAD, soak["curve_mb"]


#: #532, the known ground-texture leak: measured on bench_small (RTX 4070, 2026-10-19)
#: dedicated GPU +10.2 MB per rebuild with the product's release, private +30.4 with the
#: release inside the pass. Not a bound on a leak - a ceiling that fails if it gets WORSE.
GROUND_LEAK_CEILING_MB_PER_RELOAD = 60.0


@pytest.mark.parametrize("release", ["product", "flood"])
def test_the_known_ground_texture_leak_is_reported_and_does_not_get_worse(
        scratch: Path, release: str) -> None:
    """The same rebuilds with the ground bake ON (the product): Qt Quick 3D 6.11 keeps
    about half the tile textures of every release (#532). Reported in MEASURED; the
    ceiling catches a regression beyond the measured leak. When Qt is fixed (or the tiles
    leave the buffer manager's maps) these slopes fall under LEAK_BOUND_MB_PER_RELOAD and
    the bake-off restriction of the gate above can go."""
    soak = _soak(scratch, "rebuild_on", release=release, ground="on")
    _took_no_frame(soak)
    assert soak["slope_second_half_mb_per_reload"] < GROUND_LEAK_CEILING_MB_PER_RELOAD, soak["curve_mb"]
    gpu = soak["gpu_slope_second_half_mb_per_reload"]
    assert gpu is None or gpu < GROUND_LEAK_CEILING_MB_PER_RELOAD, soak["gpu_curve_mb"]


def test_what_a_readback_per_rebuild_costs_a_view_that_presents_nothing_is_reported(
        scratch: Path) -> None:
    """Why nothing takes a frame from the live view, as a number in the report and never
    a bound: the same rebuilds with frames withheld AND one readback per rebuild. A
    readback renders a frame that is never presented; what it holds waits for a
    presented frame, and here none comes."""
    soak = _soak(scratch, "rebuild_on", frames="withheld", grabs="every")
    spell = soak["in_the_loop"]
    assert spell["frames_presented"] == 0 and spell["frames_read_back"] == RELOADS
    assert soak["presented_again"] is True and soak["same_image_at_the_end"] is True


# ── G8: Qt WebEngine beside the 3D host ──────────────────────────────────────


def test_webengine_renders_before_and_after_the_3d_host_exists(scratch: Path) -> None:
    """ADR-048 criterion 2's deferred half: the map picker's engine (a page of one
    colour instead of the picker's own, which needs the network and a key) paints
    the page before the 3D host was created and after, in the same session."""
    run = _clean(run_gate(scratch, "coexist"))
    before, after = run.step("web_before_3d"), run.step("web_after_3d")
    for label, web in (("before", before), ("after", after)):
        assert web["load_finished"] is True and web["loaded_ok"] is True, label
        assert web["centre"] == "#1e90ff", f"{label}: the page was not painted ({web['centre']})"
    assert after["distinct_3d_colours"] >= 16, "the 3D view drew its garden beside it"
    MEASURED["G8"] = {"centre_before": before["centre"], "centre_after": after["centre"],
                      "distinct_3d_colours": after["distinct_3d_colours"],
                      "frame_px": after["frame_px"], "qt_messages": run.qt["counts"]}


# ── G11: what the live 3D view costs the 2D canvas ───────────────────────────


@pytest.mark.perf
def test_a_pan_step_beside_the_live_3d_view_costs_at_most_1_3_times(scratch: Path) -> None:
    """Six rounds of 60 pan steps in Split and 60 in Plan with the canvas at the SAME
    size, alternating (what else the machine does lands on both sides alike): the
    medians over all 360 steps of each, taken with ``processEvents()`` — the flush
    and the composition are in the number."""
    run = _clean(run_gate(scratch, "pan"))
    step = run.step("pan")
    split_sizes = {tuple(size[1:]) for size in step["canvas_px"] if size[0] == "split"}
    plan_sizes = {tuple(size[1:]) for size in step["canvas_px"] if size[0] == "plan"}
    assert split_sizes == plan_sizes and len(split_sizes) == 1, step["canvas_px"]
    assert step["top_level_surface"] == "RasterSurface", "the main window is still a raster window"
    MEASURED["G11"] = {"split_ms": step["split_ms"], "plan_ms": step["plan_ms"],
                       "ratio": step["ratio"], "ratio_of_p10": step["ratio_of_p10"],
                       "ratio_per_round": step["ratio_per_round"],
                       "canvas_px": sorted(split_sizes)}
    assert step["ratio"] <= PAN_RATIO, MEASURED["G11"]


# ── the app's shortcuts while the 3D window has the keyboard ─────────────────


def test_the_apps_shortcuts_work_while_the_3d_window_has_the_focus(scratch: Path) -> None:
    """The 3D view is a native window with its own input: Ctrl+Z must still undo, the
    camera keys must reach the camera, and Alt+1 must lead back to the plan."""
    step = _clean(run_gate(scratch, "shortcut_focus")).step("shortcuts")
    assert step["undo_with_ctrl_z"] is True
    assert step["page_up_zooms"] is True
    assert step["mode_after_alt_1"] == "plan"
    MEASURED["shortcuts"] = {key: step[key] for key in (
        "focus_is_the_3d_window", "undo_with_ctrl_z", "page_up_zooms", "mode_after_alt_1")}
