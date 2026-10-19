"""Starting the workspace gate from a test, and reading what it reports (L1.3).

Not a test module. The gate (``workspace_gate_hook.py``) runs the REAL app in a child
process on a real Qt platform; this is the parent's side: the scenario file, the
child's environment — ``render_env``, the engine story's one source of a child's
environment, never a copy of the parent's — and the verdict on what Qt said.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.integration.quick3d_render_support import driver_messages, render_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHILD = HERE / "workspace_gate_child.py"
PLANS = REPO / "tests" / "fixtures" / "plans"
FAILED_STEPS = frozenset({"REFUSED", "TIMEOUT", "EXCEPTION", "FORCED_QUIT"})
GATE_TIMEOUT_S = 600


@dataclass(frozen=True)
class GateRun:
    """One finished run of the gate."""

    returncode: int
    report: dict[str, Any]
    qt: dict[str, Any]          # ``driver_messages`` of the child's stderr
    stderr: str
    store: str
    log: str                    # the child's ``app.log`` ("" if it wrote none)

    @property
    def steps(self) -> list[str]:
        return [str(entry["step"]) for entry in self.report.get("steps", [])]

    def step(self, name: str) -> dict[str, Any]:
        """The LAST step of that name."""
        for entry in reversed(self.report.get("steps", [])):
            if entry["step"] == name:
                return dict(entry)
        raise AssertionError(f"the gate never reached step {name!r}: {self.steps}\n"
                             f"{self.stderr[-2000:]}")

    def problems(self) -> list[str]:
        """Why this run is not a clean one: the exit code, a failed step, a Qt warning
        or error, an ERROR line in the app's log. Empty for a clean run."""
        found = []
        if self.returncode != 0:
            found.append(f"exit code {self.returncode}")
        found += [f"step {name}" for name in self.steps if name in FAILED_STEPS]
        found += [f"Qt error: {text[:300]}" for text in self.qt["errors"]]
        found += [f"Qt warning: {text[:300]}" for text in self.qt["warnings"]]
        found += [f"app.log: {line[:300]}" for line in self.log.splitlines()
                  if " ERROR " in line or " CRITICAL " in line]
        if self.steps[-1:] != ["closed"]:
            found.append(f"the run did not end with a closed window: {self.steps[-3:]}")
        return found


def write_spec(scratch: Path, scenario: str, *, store: str | None = None,
               **arguments: Any) -> tuple[Path, Path, str]:
    """A scenario file under ``scratch``: (the file, the report's path, the store's name)."""
    name = store or f"Open Garden Planner Gate {uuid.uuid4().hex[:12]}"
    out = scratch / f"gate-{scenario}-{uuid.uuid4().hex[:6]}.json"
    spec = out.with_suffix(".spec.json")
    spec.write_text(json.dumps({"scenario": scenario, "out": str(out), "store": name,
                                "args": arguments}), encoding="utf-8")
    return spec, out, name


def app_log_of(scratch: Path, store: str) -> str:
    """The app's rotating log of a gate child: it lives in the log directory Qt derives
    from the application's name, under the child's own profile (``render_env``)."""
    from tests.integration.quick3d_render_support import session_profile

    found = sorted(session_profile().rglob(f"{store}/app.log")) + sorted(
        scratch.rglob(f"{store}/app.log"))
    return found[0].read_text(encoding="utf-8", errors="replace") if found else ""


def run_gate(scratch: Path, scenario: str, *, plan: Path | None = PLANS / "bench_small.ogp",
             store: str | None = None, command: list[str] | None = None,
             software: bool = False, timer_paced: bool = True,
             **arguments: Any) -> GateRun:
    """Run one scenario in a fresh process and return what happened.

    ``command``: what to start instead of the source child — the frozen gate exe.
    ``software``: start the process with Qt's own software switch (the render tier's
    WARP run); the workspace's compatibility mode is a different, per-window route.
    ``timer_paced`` (the default): Qt's own ``QT_D3D_NO_VBLANK_THREAD=1``. On Windows
    Qt asks a display-vblank thread for its update requests, and with the display
    asleep that thread is silent: a visible window presents its first frame and no
    more. With the switch Qt paces them by timer, so frames are PRESENTED whatever
    the display does — the ordinary render path, and what no scenario may depend
    on is whether this machine's display happens to be awake. The memory soak needs
    it most: what a destroyed Model held is given back at the end of a PRESENTED
    frame (its ``frames="withheld"`` variant takes the frames away on purpose).
    ``False`` runs the child as the product starts: paced by the display.
    """
    spec, out, name = write_spec(scratch, scenario, store=store, **arguments)
    argv = [*(command or [sys.executable, str(CHILD)]), *([str(plan)] if plan else [])]
    extra = {}
    if software:
        extra["QSG_RHI_PREFER_SOFTWARE_RENDERER"] = "1"
    if timer_paced:
        extra["QT_D3D_NO_VBLANK_THREAD"] = "1"
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        argv, capture_output=True, text=True, timeout=GATE_TIMEOUT_S, cwd=scratch,
        env=render_env(scratch, OGP_QUICK3D="1", OGP_WORKSPACE_GATE=str(spec), **extra))
    report = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    return GateRun(proc.returncode, report, driver_messages(proc.stderr), proc.stderr, name,
                   app_log_of(scratch, name))
