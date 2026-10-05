"""TEMPORARY CI driver for the Qt Quick 3D spike (ADR-048, Phase 17 L0) — delete before merge.

Runs the dormant ``--spike-q3d`` evidence tool (unfrozen via ``python -m``, or
inside the frozen PyInstaller bundle), bounded by a hard timeout, and then
prints everything it produced **into the job log**: exit code, a manifest of
the output directory (PNG mean luma exposes black frames), ``spike.log`` and
``metrics.json``.

Why a driver instead of a PowerShell ``Start-Process -Wait`` line:

* ``Start-Process -Wait`` has no timeout. Evidence run v1 hung inside the
  frozen exe for 56 minutes until the job limit killed it and left no output
  (a GUI-subsystem exe has no stdout).
* The evidence must be readable from the job log: the artifact download host
  is not reachable from every place the log is read.
* This is an evidence run, not a release gate. The frozen-exe gate command
  keeps its single home (``ogp-change-control`` §2.8, executed by
  ``release.yml``); this driver deliberately does not run ``--selftest``.

A run is green only when the evidence says so, not merely when the process
exits 0: every threshold ``_verdict`` knows is checked against the sections in
``metrics.json`` and printed as PASS/FAIL, and a section whose flag was given
but which is missing fails. The dist-size delta (criterion 9) is asserted by the
workflow's baseline step, not here.

``--frozen-smoke`` starts the bundle normally (no arguments) and requires it
to still be running after 8 s — the shape of the release smoke, run here
because this bundle carries the spike (ADR-038's spike evidence ran both).

Usage::

    python scripts/spike_q3d_ci.py --unfrozen --out DIR --limit-s 600 -- [spike args]
    python scripts/spike_q3d_ci.py --frozen   --out DIR --limit-s 1500 -- [spike args]
    python scripts/spike_q3d_ci.py --frozen-smoke --out DIR
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # noqa: S404 - fixed argv, no shell
import sys
import time
from pathlib import Path

FROZEN_BUNDLE = Path("dist") / "OpenGardenPlanner" / "OpenGardenPlanner.exe"
REPO = Path(__file__).resolve().parents[1]


def _mean_luma(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a runtime dependency
        return "n/a"
    with Image.open(path) as img:
        gray = img.convert("L")
        hist = gray.histogram()
        total = sum(hist) or 1
        return f"{sum(i * n for i, n in enumerate(hist)) / total:.1f}"


def _report(out: Path, code: int | None, elapsed: float) -> None:
    print(f"::group::spike evidence {out}")
    print(f"exit_code={code} elapsed_s={elapsed:.1f}")
    for path in sorted(out.rglob("*")):
        if path.is_file():
            luma = _mean_luma(path) if path.suffix.lower() == ".png" else "-"
            print(f"  {path.relative_to(out).as_posix():40s} {path.stat().st_size:>10d} B"
                  f"  luma={luma}")
    for name in ("spike.log", "stdout.txt", "stderr.txt"):
        log = out / name
        if log.is_file() and log.stat().st_size:
            print(f"----- {name} -----")
            print(log.read_text(encoding="utf-8", errors="replace"))
    metrics = out / "metrics.json"
    if metrics.is_file():
        print("----- metrics.json -----")
        try:
            print(json.dumps(json.loads(metrics.read_text(encoding="utf-8")), indent=2))
        except json.JSONDecodeError:
            print(metrics.read_text(encoding="utf-8", errors="replace"))
    print("::endgroup::")


def _num(value: object) -> float | None:
    """A measured number, or None: a missing or null metric must never pass."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _below(value: object, limit: float) -> bool:
    num = _num(value)
    return num is not None and num < limit


def _at_least(value: object, limit: float) -> bool:
    num = _num(value)
    return num is not None and num >= limit


# What the gate measures, not what it would like to conclude: a run whose memory
# rose 361 MB over 100 reloads still passes it (ADR-048 entry 10, senior pass 8)
LEAK_CHECK = "memory slope over the second half of the reloads < 10 MB/reload"

# Each evidence flag and the metrics section it must leave behind: a probe that
# was asked for and wrote nothing is a failure, not a pass with fewer checks.
_REQUIRED_SECTIONS = {
    "--iou": "shadow_iou_by_preset",
    "--orient": "orientation",
    "--pick": "pick",
    "--update-bench": "update_bench",
    "--second-window": "second_window",
    "--coexist": "coexist",
    "--pan-bench": "pan_bench",
}


def _flag_value(spike_args: list[str], flag: str) -> str | None:
    """The value of ``--flag N`` or ``--flag=N`` in the spike's arguments, or None."""
    for idx, arg in enumerate(spike_args):
        if arg == flag:
            return spike_args[idx + 1] if idx + 1 < len(spike_args) else None
        if arg.startswith(flag + "="):
            return arg.partition("=")[2]
    return None


def _child_env(frozen: bool) -> dict[str, str]:
    """The spike child's environment. The unfrozen child imports THIS checkout's
    ``src``, not whatever the venv's editable install points at (from a git
    worktree: the main checkout); the frozen child gets the environment unchanged."""
    env = dict(os.environ)
    if not frozen:
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(REPO / "src"), env.get("PYTHONPATH")) if p)
    return env


def _attributed(open_ms: float | None, breakdown: object) -> bool:
    """Two-sided: every bucket is a number and together they explain open time."""
    if open_ms is None or not isinstance(breakdown, dict) or not breakdown:
        return False
    parts = [_num(v) for v in breakdown.values()]
    return all(p is not None for p in parts) and abs(open_ms - sum(parts)) < 100.0  # type: ignore[arg-type]


def _ran(metrics: dict) -> dict:
    """The flags the spike itself parsed (``metrics["args"]``), or {} without them."""
    ran = metrics.get("args")
    return ran if isinstance(ran, dict) else {}


def _requested_sections(spike_args: list[str], ran: dict | None = None) -> list[str]:
    """Sections asked for by the driver's argv OR recorded as run by the spike: either
    alone has a hole (an abbreviation the argv scan cannot see; an early error that
    wrote no ``args``), so a section is required when either asks for it."""
    ran = ran or {}
    flags = {arg.split("=", 1)[0] for arg in spike_args}
    sections = [section for flag, section in _REQUIRED_SECTIONS.items()
                if flag in flags or ran.get(flag.lstrip("-").replace("-", "_")) is True]
    count = _flag_value(spike_args, "--soak")  # exact flag: not --soak-leak-mb
    soak = ran.get("soak")
    if (count is not None and count.isdigit() and int(count) > 0) or (
            isinstance(soak, int) and not isinstance(soak, bool) and soak > 0):
        sections.append("soak")
    return sections


def _verdict(metrics: dict, spike_args: list[str] | None = None,
             expect_caches: str | None = None) -> list[str]:
    """Every ADR-048 threshold the present metric sections can be judged on.

    Thresholds use explicit number checks: ``x or default`` turned a perfect
    0.0 px projection error into a failure, and a null metric must fail rather
    than raise or pass.
    """
    checks: list[tuple[str, bool]] = [
        ("status ok", metrics.get("status") == "ok"),
        ("no frame-wait timeouts", metrics.get("wait_timeouts") == 0),
    ]
    ran = _ran(metrics)
    checks += [(f"{section} measured (its flag was given)", bool(metrics.get(section)))
               for section in _requested_sections(spike_args or [], ran)]
    by_preset = metrics.get("shadow_iou_by_preset") or {
        "high": metrics.get("shadow_iou") or {}}
    for preset, probe in by_preset.items():
        checks += [(f"shadow IoU {preset} {k} >= 0.85", _at_least(v.get("iou"), 0.85))
                   for k, v in (probe.get("results") or {}).items()]
    first_frame = _num(metrics.get("first_frame_ms"))
    first_ready = _num(metrics.get("first_ready_ms"))
    open_ms = _num(metrics.get("open_ms"))
    qml_load = _num(metrics.get("qml_load_ms"))
    caches = metrics.get("shader_caches")
    checks += [("open time measured to a finished readback",
                first_frame is not None and first_frame > 0
                and first_ready is not None and first_ready >= first_frame),
               ("open time includes QML load and scene build",
                open_ms is not None and first_ready is not None and qml_load is not None
                and open_ms >= first_ready + qml_load),
               ("open time is fully attributed (breakdown within 100 ms)",
                _attributed(open_ms, metrics.get("open_breakdown_ms"))),
               ("the run records which shader caches it found", isinstance(caches, dict))]
    if expect_caches is not None and isinstance(caches, dict):
        found = caches.get("found_before_run")
        checks.append((f"shader caches at start: {expect_caches}",
                       isinstance(found, list) and (bool(found) == (expect_caches == "found"))))
    qt = metrics.get("qt_messages")
    checks += [("Qt reported no shader/QML error", isinstance(qt, dict) and qt.get("errors") == []),
               # clean runs emit no Qt warnings at all (llvmpipe, measured): any warning
               # here is read, and excused explicitly if benign — never ignored
               ("Qt reported no warning", isinstance(qt, dict)
                and (qt.get("counts") or {}).get("warning") == 0)]
    orient = metrics.get("orientation")
    if orient:
        checks += [("ground north-up", orient.get("ground_texture_ok") is True),
                   ("sky sun at the solar azimuth", orient.get("sky_ok") is True)]
    pick = metrics.get("pick")
    if pick:
        n = pick.get("n")
        checks += [("20 pick targets", n == 20),
                   ("picks all hit", pick.get("hits") == n),
                   ("picks hit after re-attach", pick.get("hits_after_reattach") == n),
                   ("frame unchanged after re-attach",
                    _below(pick.get("reattach_frame_diff"), 1.0)),
                   ("adversarial picks all hit",
                    _at_least(pick.get("adversarial_n"), 5)
                    and pick.get("adversarial_hits") == pick.get("adversarial_n")),
                   ("click pixels match our own projection",
                    _below(pick.get("max_projection_err_px"), 1.0)),
                   ("picked points within 3 cm of the target",
                    _below(pick.get("max_xy_err_cm"), 3.0))]
    probed = ({arg.split("=", 1)[0] for arg in spike_args or []} & {"--iou", "--orient"}
              or ran.get("iou") is True or ran.get("orient") is True)
    if probed or "probe_restore_frame_diff" in metrics:  # required, not optional, once probed
        checks.append(("the probes leave the view as they found it (< 1 luma)",
                       _below(metrics.get("probe_restore_frame_diff"), 1.0)))
    second = metrics.get("second_window")
    if second:
        checks.append(("the second window renders the first window's view (< 1 luma)",
                       _below(second.get("frame_diff_vs_first"), 1.0)))
    coexist = metrics.get("coexist")
    if coexist:
        checks += [("WebEngine page drawn", coexist.get("web_ok") is True),
                   ("3D frame unchanged with WebEngine alive", coexist.get("frame3d_ok") is True)]
    soak = metrics.get("soak")
    soak_n = _flag_value(spike_args or [], "--soak")
    if soak and soak_n is not None and soak_n.isdigit():
        checks += [(f"soak ran {soak_n} cycles", soak.get("cycles") == int(soak_n)),
                   (f"soak reloaded the project {int(soak_n) // 5} times",
                    soak.get("project_reloads") == int(soak_n) // 5)]
    if soak:
        # The close's witness is the process exit code, checked before this verdict.
        checks += [("animation really ran before the close", soak.get("animation_advanced") is True)]
        if "project_reloads" in soak:
            checks += [("every project reload rebuilt every model",
                        soak.get("models_per_reload_ok") is True),
                       (LEAK_CHECK, _below(soak.get("leak_slope_mb_per_reload"), 10.0))]
    failures = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return failures


def _smoke() -> int:
    """Normal start of the bundle (no arguments) must still be running after 8 s."""
    if not FROZEN_BUNDLE.is_file():
        print(f"frozen bundle missing: {FROZEN_BUNDLE}")
        return 1
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [str(FROZEN_BUNDLE.resolve())], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(8.0)
    code = proc.poll()
    if code is None:
        proc.kill()
        proc.wait(timeout=30)
        print("smoke: still running after 8 s (PASS)")
        return 0
    print(f"::error::smoke: the bundle exited after < 8 s with code {code}")
    return 1


def main(argv: list[str]) -> int:
    if "--" in argv:
        split = argv.index("--")
        own, spike_args = argv[:split], argv[split + 1 :]
    else:
        own, spike_args = argv, []
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--frozen", action="store_true", help="run the PyInstaller bundle")
    mode.add_argument("--unfrozen", action="store_true", help="run python -m open_garden_planner")
    mode.add_argument("--frozen-smoke", action="store_true",
                      help="normal start of the bundle must survive 8 s")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit-s", type=float, default=1500.0, help="hard wall-clock limit")
    parser.add_argument("--expect-caches", choices=("none", "found"),
                        help="criterion 5: the run must find no shader caches (a first launch) "
                             "or some (a warm relaunch)")
    parser.add_argument("--expect-leak", action="store_true",
                        help="positive control: pass only if the leak gate (and nothing else) fails")
    args = parser.parse_args(own)

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.frozen_smoke:
        return _smoke()
    if args.frozen:
        if not FROZEN_BUNDLE.is_file():
            print(f"frozen bundle missing: {FROZEN_BUNDLE}")
            return 1
        cmd = [str(FROZEN_BUNDLE.resolve())]
    else:
        cmd = [sys.executable, "-m", "open_garden_planner"]
    cmd += ["--spike-q3d", "--out", str(out), *spike_args]
    print("running:", " ".join(cmd), flush=True)

    t0 = time.perf_counter()
    code: int | None
    # Unfrozen: capture Python's own streams (tracebacks before the spike log
    # opens). Frozen: DEVNULL. The exe has no console, but unlike a double-click
    # it gets valid std handles, so this does NOT reproduce #291's no-handle
    # condition; only the release gate's Start-Process launch does.
    with (out / "stdout.txt").open("wb") as so, (out / "stderr.txt").open("wb") as se:
        streams = (subprocess.DEVNULL, subprocess.DEVNULL) if args.frozen else (so, se)
        try:
            code = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                timeout=args.limit_s, check=False, env=_child_env(args.frozen),
            ).returncode
        except subprocess.TimeoutExpired:
            code = None
    elapsed = time.perf_counter() - t0
    _report(out, code, elapsed)
    if code is None:
        print(f"::error::spike exceeded the {args.limit_s:.0f} s limit and was killed")
        return 124
    if code != 0:
        print(f"::error::spike exited with {code}")
        return code
    metrics_path = out / "metrics.json"
    if not metrics_path.is_file():
        print("::error::no metrics.json")
        return 1
    print("verdict:")
    failures = _verdict(json.loads(metrics_path.read_text(encoding="utf-8")), spike_args,
                        args.expect_caches)
    if args.expect_leak:  # the gate must fire on a known leak, on the same runner
        soak = json.loads(metrics_path.read_text(encoding="utf-8")).get("soak") or {}
        slope = _num(soak.get("leak_slope_mb_per_reload"))
        if failures == [LEAK_CHECK] and slope is not None and slope >= 10.0:
            print("positive control: the leak gate fired on the deliberate leak (PASS)")
            return 0
        print(f"::error::positive control: expected exactly [{LEAK_CHECK!r}], got {failures}")
        return 1
    if failures:
        print(f"::error::evidence checks failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
