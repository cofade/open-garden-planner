"""The 3D view as the default (Phase 17 L1.9): what the app pays for it, in the REAL app
on a real graphics device.

Render tier (``OGP_RENDER3D=1``) and wall clock (``perf``): every test starts the app's own
``main()`` in a child process through the workspace gate (``workspace_gate_support.run_gate``:
a throw-away profile and settings store, proven in ``test_workspace_gate.py``) and judges what
the scenario of ``workspace_default_measure.py`` reported. The whole file:

    OGP_RENDER3D=1 pytest tests/integration/test_view3d_default_render.py -m "perf or not perf" -n 0

- **The start costs no engine**: with 3D never opened, not one module of Qt Quick, QML or
  ``ui/view3d/quick3d`` is loaded (the import scan of the default; its default-tier twin is
  ``test_view3d_workspace.py::test_g1_the_engine_is_never_imported_before_3d_is_asked_for``).
- **The first 3D click** reaches a finished frame within ``FIRST_FRAME_BUDGET_S``.
- **Date playback (#531)**: a date that keeps changing (a step every 33 ms) regrows the
  dated plants at most twice a second, the light follows the steps, and the view ends on the
  last date; the control (no interval: the behaviour before L1.9) regrows on every step.

The bounds are here; the measured numbers of the budget table are §8.32.9.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.quick3d_render_support import render_tier
from tests.integration.workspace_gate_support import GateRun, run_gate

pytestmark = [*render_tier, pytest.mark.perf]

#: The first switch to 3D (View → "3D View": Split) to the first finished readback, on a
#: hardware adapter. Measured on the RTX 4070 (§8.32.9): 2.3 s (small plan), 3.3 s (large),
#: 4.5 s on the first run of the day.
FIRST_FRAME_BUDGET_S = 10.0
SOFTWARE_ADAPTERS = ("Basic Render", "llvmpipe", "SwiftShader", "softpipe")


def _clean(run: GateRun) -> GateRun:
    assert run.problems() == [], f"{run.problems()}\n{run.stderr[-3000:]}"
    assert run.report["network"] == "offline"
    return run


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("default-flip")


def _folder(scratch: Path, name: str) -> Path:
    folder = scratch / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@pytest.fixture(scope="module")
def budget(scratch: Path) -> GateRun:
    return _clean(run_gate(_folder(scratch, "budget"), "budget", edits=100))


def test_the_app_starts_with_no_engine_module_loaded(budget: GateRun) -> None:
    before = budget.step("before_3d")
    assert before["engine"] == [], before["engine"]
    assert before["mode"] == "plan" and before["state"] == "not_started"


def test_the_first_3d_click_reaches_a_finished_frame_within_the_budget(budget: GateRun) -> None:
    opened = budget.step("opened")
    assert opened["mode"] == "split", "View → 3D View shows Split from Plan mode"
    assert opened["state"] == "running" and opened["engine"] > 0
    adapter = budget.qt["adapter"]
    if adapter is None or any(name in str(adapter) for name in SOFTWARE_ADAPTERS):
        pytest.skip(f"a software adapter is measured, not judged: {opened['first_readback_s']} s")
    assert opened["first_readback_s"] <= FIRST_FRAME_BUDGET_S, opened


def test_a_hundred_edits_after_the_first_frame_are_all_in_3d(budget: GateRun) -> None:
    edited = budget.step("edited")
    assert edited["edits"] == 100 and edited["passes"] >= 50
    assert edited["snapshots"] >= edited["passes"]
    assert edited["memory_after_edits"]["private_mb"] > 0


@pytest.fixture(scope="module")
def playback(scratch: Path) -> dict[str, dict[str, Any]]:
    runs = {}
    for name, interval in (("product", None), ("control", 0)):
        arguments: dict[str, Any] = {"seconds": 30, "plants": 20}
        if interval is not None:
            arguments["interval_ms"] = interval
        run = _clean(run_gate(_folder(scratch, f"play-{name}"), "date_playback", **arguments))
        runs[name] = run.step("date_playback")
    return runs


def test_a_held_date_key_regrows_at_most_twice_a_second(playback: dict[str, dict[str, Any]]) -> None:
    """Measured (30 s, 20 dated trees, RTX 4070): 1.5 to 1.6 regrowth passes a second — the
    steps themselves are slower than a key's repeat in this loop (5 to 8 a second)."""
    product = playback["product"]
    assert product["interval_ms"] == 500 and product["plants"] == 20
    cap = product["held_s"] * 1000.0 / product["interval_ms"] + 2
    assert 0 < product["regrowth_passes"] <= cap, product
    assert product["models_regrown"] <= cap * product["plants"]
    assert product["light_passes"] > 0, "the light follows the steps in between"
    assert product["shown_date"] == product["clock_date"], "it ends on the last date"


def test_without_the_interval_every_step_regrows(playback: dict[str, dict[str, Any]]) -> None:
    """The control: the behaviour before L1.9 — and the reason for the interval."""
    product, control = playback["product"], playback["control"]
    assert control["interval_ms"] == 0
    assert control["regrowth_passes"] == control["steps"] > product["regrowth_passes"]
    assert control["models_regrown"] == control["steps"] * control["plants"]
    assert control["shown_date"] == control["clock_date"]
