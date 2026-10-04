"""TEMPORARY CI driver for the Qt Quick 3D spike (ADR-047, Phase 17 L0) — delete before merge.

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

Usage::

    python scripts/spike_q3d_ci.py --unfrozen --out DIR --limit-s 600 -- [spike args]
    python scripts/spike_q3d_ci.py --frozen   --out DIR --limit-s 1500 -- [spike args]
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: S404 - fixed argv, no shell
import sys
import time
from pathlib import Path

FROZEN_BUNDLE = Path("dist") / "OpenGardenPlanner" / "OpenGardenPlanner.exe"


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
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit-s", type=float, default=1500.0, help="hard wall-clock limit")
    args = parser.parse_args(own)

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
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
    # opens). Frozen: no handles at all, like a double-clicked GUI exe.
    with (out / "stdout.txt").open("wb") as so, (out / "stderr.txt").open("wb") as se:
        streams = (subprocess.DEVNULL, subprocess.DEVNULL) if args.frozen else (so, se)
        try:
            code = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                timeout=args.limit_s, check=False,
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
