"""The 3D part of the frozen exe's ``--selftest`` (L1.2, ADR-048). Engine loaded in ``run_selftest``.

``main._run_selftest`` calls ``run_selftest()``. It answers one question about
the artifact it runs in: can THIS build render the garden? It

1. imports the Qt Quick bindings (the DLL-load surface a version mismatch
   breaks — the #277 class of failure);
2. loads ``Garden.qml`` and its shaders from the bundle and renders ONE small
   frame without showing a window: a red box on the ground, lit by a known sun,
   and one swatch per material kind — so every shader the package ships is
   compiled by the real backend;
3. judges the frame: the box is red where our own projection puts it, the
   ground is meadow, the ground north-east of the box is in the box's shadow
   (where ``core/shadow_geometry`` — the 2D overlay's code — says it falls),
   every swatch drew. "Not empty" is not enough.

A QML error, a shader that does not compile, a frame that fails the judge or an
exception fails the self-test. So does a hang: a watchdog dumps every thread's
stack into the log and exits with code 1.

It must pass on a machine WITHOUT a GPU: ``release.yml`` runs it on
``windows-latest``, where Direct3D 11 renders on WARP. Nothing here needs more
than one 160 x 120 frame, no sky probe, no post effects.

The exit code is the only channel of a windowed exe; the log
(``default_log_path()``: the app's per-user log directory, or ``OGP_SELFTEST_LOG``)
says why, and which graphics adapter rendered.
"""

from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    GroundSpec,
    Material,
    MeshPart,
    Params,
    Record,
    SunState,
    Transform,
    prism_mesh,
)

from .runlog import RenderLog, watchdog
from .shots import TopDownShot, top_down_pixel

#: The bindings the engine package needs, in dependency order.
ENGINE_MODULES: Final = ("PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D")
#: A hang past this fails the self-test (measured wall times: ADR-048 addendum L1.2).
WATCHDOG_S: Final = 180.0
LOG_NAME: Final = "OpenGardenPlanner-selftest-3d.log"

# ── the scene: plain data, so the judge and the unit tests share it ──────────

SIZE: Final = (160, 120)                   # logical pixels
_CENTER: Final = (200.0, 150.0)            # the middle of the 400 x 300 cm plan rectangle
SHOT: Final = TopDownShot(center=_CENTER, px_per_cm=0.4)
GROUND: Final = GroundSpec(width_cm=400.0, depth_cm=300.0)
SUN: Final = SunState(elevation_deg=45.0, azimuth_deg=225.0)   # in the south-west: shadows fall NE
BOX_TINT: Final = (230, 20, 20, 255)
SWATCH_TINT: Final = (200, 60, 40, 255)
#: Every material kind but the box's own ``vc``, west to east.
SWATCH_KINDS: Final = ("roof", "foliage", "grass", "glass", "water")
_KIND_PARAM: Final = "material_kind"


@dataclass(frozen=True, slots=True)
class Region:
    """An axis-aligned patch of the plan the judge samples (scene cm)."""

    east_cm: float
    north_cm: float
    width_cm: float
    depth_cm: float


def _at(east: float, north: float, width: float, depth: float) -> Region:
    return Region(_CENTER[0] + east, _CENTER[1] + north, width, depth)


def _ring(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


_BOX: Final = _at(0.0, 20.0, 100.0, 100.0)           # footprint of the 100 cm cube
_SWATCH_SIDE: Final = 40.0
_SWATCHES: Final = {kind: _at(-150.0 + 75.0 * index, -105.0, _SWATCH_SIDE, _SWATCH_SIDE)
                    for index, kind in enumerate(SWATCH_KINDS)}

#: Where the judge looks. Each patch lies well inside what it samples; the shadow
#: patch is inside the analytic 2D shadow of the box for ``SUN`` and outside the
#: box (pinned by ``tests/unit/test_quick3d_selftest.py``).
REGIONS: Final[dict[str, Region]] = {
    "box": _at(0.0, 20.0, 50.0, 50.0),
    "lit ground": _at(-150.0, 60.0, 40.0, 60.0),
    "shadow": _at(60.0, 85.0, 15.0, 15.0),
    **{kind: Region(region.east_cm, region.north_cm, 20.0, 20.0)
       for kind, region in _SWATCHES.items()},
}


def _item(item_id: str, footprint: Region, height: float, tint: tuple[int, int, int, int],
          kind: str) -> Record:
    return Record(
        item_id=item_id, kind="SELFTEST", shape="rectangle",
        footprints=(_ring(footprint.width_cm, footprint.depth_cm),),
        transform=Transform(east_cm=footprint.east_cm, north_cm=footprint.north_cm),
        material=Material("SELFTEST", fill_rgba=tint), height_cm=height,
        params=Params({"seed": item_id, _KIND_PARAM: kind}),
    )


def records() -> dict[str, Record]:
    """The self-test scene: the box and one low swatch per other material kind."""
    scene = {"box": _item("box", _BOX, 100.0, BOX_TINT, "vc")}
    for kind, region in _SWATCHES.items():
        scene[kind] = _item(kind, region, 30.0, SWATCH_TINT, kind)
    return scene


def _builder(record: Record) -> tuple[MeshPart, ...]:
    kind = str(record.params[_KIND_PARAM])
    height = record.height_cm if record.height_cm is not None else 0.0
    return (MeshPart(prism_mesh(record.footprints, height), kind,
                     casts_shadow=kind not in ("glass", "water"), tinted=True, name=kind),)


def registry() -> BuilderRegistry:
    """Builds each self-test item as a tinted prism in the material kind it names."""
    out = BuilderRegistry()
    out.register("SELFTEST", _builder)
    return out


# ── the judge: a pure function of the pixels ─────────────────────────────────


def _mean(rgba: NDArray[np.uint8], region: Region, ratio: float) -> NDArray[np.float64]:
    height, width = rgba.shape[:2]
    left, top = top_down_pixel(region.east_cm - region.width_cm / 2,
                               region.north_cm + region.depth_cm / 2, SHOT, (width, height), ratio)
    right, bottom = top_down_pixel(region.east_cm + region.width_cm / 2,
                                   region.north_cm - region.depth_cm / 2, SHOT, (width, height), ratio)
    patch = rgba[int(np.ceil(top)):int(np.floor(bottom)), int(np.ceil(left)):int(np.floor(right)), :3]
    mean: NDArray[np.float64] = patch.reshape(-1, 3).astype(np.float64).mean(axis=0)
    return mean


def _luma(rgb: NDArray[np.float64]) -> float:
    return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])


def _shown(rgb: NDArray[np.float64]) -> str:
    return f"rgb({rgb[0]:.0f}, {rgb[1]:.0f}, {rgb[2]:.0f})"


def judge_frame(rgba: NDArray[np.uint8], device_pixel_ratio: float = 1.0) -> list[str]:
    """What is wrong with a self-test frame — an empty list for a good one.

    ``rgba``: ``(height, width, 4)``, row 0 on top, the top-down view of
    ``records()`` under ``SUN`` (un-tone-mapped: a pixel is linear radiance).
    """
    height, width = rgba.shape[:2]
    expected = (round(SIZE[0] * device_pixel_ratio), round(SIZE[1] * device_pixel_ratio))
    if (width, height) != expected:
        return [f"the frame is {width}x{height}, expected {expected[0]}x{expected[1]}"]
    problems: list[str] = []
    lit = _mean(rgba, REGIONS["lit ground"], device_pixel_ratio)
    if not (lit[1] > 30 and lit[1] > 1.5 * lit[0] and lit[1] > 1.5 * lit[2]):
        problems.append(f"the ground is not lit meadow: {_shown(lit)}")
    box = _mean(rgba, REGIONS["box"], device_pixel_ratio)
    if not (box[0] > 120 and box[0] > 3 * box[1] and box[0] > 3 * box[2]):
        problems.append(f"the box is not there in its lit colour: {_shown(box)}")
    shadow = _mean(rgba, REGIONS["shadow"], device_pixel_ratio)
    if not _luma(shadow) < 0.75 * _luma(lit):
        problems.append("the shadow is missing: the ground north-east of the box is as bright "
                        f"as the lit ground ({_shown(shadow)} vs {_shown(lit)})")
    for kind in SWATCH_KINDS:
        swatch = _mean(rgba, REGIONS[kind], device_pixel_ratio)
        if kind == "glass":  # it blends: judged by not being bare ground
            if float(np.abs(swatch - lit).max()) <= 10:
                problems.append(f"the glass swatch did not draw: {_shown(swatch)}")
        elif not (swatch[0] > 40 and swatch[0] > 2 * swatch[1] and swatch[0] > 2 * swatch[2]):
            problems.append(f"the {kind} swatch did not draw in its tint: {_shown(swatch)}")
    return problems


# ── running it ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Rendered:
    """One self-test frame and what is known about it."""

    rgba: NDArray[np.uint8]
    device_pixel_ratio: float
    graphics_api: str
    adapter: str | None
    open_ms: float
    qt_counts: dict[str, int]
    #: Items whose builder failed (``OffscreenFrame.build_failures``): any is a FAIL.
    build_failures: tuple[str, ...] = ()
    #: Qt messages of the render that arrived on another thread than the one that
    #: rendered (``QtMessages.other_threads``): any is a FAIL — the recorder is only
    #: allowed here because there are none, and a frozen exe is where that must hold.
    other_threads: int = 0


@dataclass(frozen=True, slots=True)
class SelftestResult:
    ok: bool
    #: ``"  OK   …"`` / ``"  FAIL …"`` lines in the format of ``main._run_selftest``.
    lines: tuple[str, ...]
    log_path: Path


def default_log_path() -> Path:
    """Where the self-test log goes: ``OGP_SELFTEST_LOG`` if set, else the app's ONE
    per-user log directory — beside ``app.log`` and ``crash.log``
    (``core.logging_config.resolve_log_dir``).

    Never the temp directory: on Linux ``/tmp`` is shared between users, and a file
    with a predictable name there can be pre-created or symlinked by another local
    user (CWE-377). The directory hangs on the application's name, which the
    caller must have given Qt first (``main._run_selftest`` does, as ``main`` does
    for the crash log).
    """
    override = os.environ.get("OGP_SELFTEST_LOG")
    if override:
        return Path(override)
    from open_garden_planner.core.logging_config import resolve_log_dir

    return resolve_log_dir() / LOG_NAME


def _render(log: RenderLog, qml_dir: Path | None) -> Rendered:
    from .offscreen import render_records  # the engine loads here

    frame = render_records(records(), shot=SHOT, sun=SUN, ground=GROUND, size=SIZE,
                           registry=registry(), qml_dir=qml_dir, log=log, graphics_info=True)
    return Rendered(frame.rgba(), frame.device_pixel_ratio, frame.graphics_api, frame.adapter,
                    frame.open_ms, dict(frame.qt.get("counts", {})),
                    tuple(f"{item_id}: {error}" for item_id, error in frame.build_failures.items()),
                    int(frame.qt.get("other_threads", 0)))


def run_selftest(log_path: Path | None = None, *, watchdog_s: float | None = WATCHDOG_S,
                 qml_dir: Path | None = None, log: RenderLog | None = None) -> SelftestResult:
    """Import the engine, render the self-test frame, judge it (module docstring).

    Never raises: every failure becomes a ``FAIL`` line and ``ok=False``. Only a
    watchdog ends the process itself (exit code 1), and says so in the log first.

    Standalone it opens its own log at ``log_path`` (default: ``default_log_path()``)
    and bounds the render with ``watchdog_s``. ``main`` runs the WHOLE ``--selftest``
    under one watchdog and one log: it passes that ``log`` and ``watchdog_s=None``
    (``faulthandler`` has one timer per process — a second one here would replace
    the outer one and cancel it on the way out).
    """
    owns_log = log is None
    if log is None:
        path = log_path if log_path is not None else default_log_path()
        log = RenderLog(path, mirror=False)  # stdout carries the verdict lines, the file the detail
    else:
        path = log.path if log.path is not None else default_log_path()
    lines: list[str] = []
    started = time.perf_counter()

    def say(ok: bool, text: str) -> None:
        lines.append(f"  {'OK  ' if ok else 'FAIL'} {text}")
        log("selftest", line=lines[-1].strip())

    for name in ENGINE_MODULES:
        try:
            importlib.import_module(name)
            say(True, f"import {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, never abort
            say(False, f"import {name} -> {exc}")
    if all(line.startswith("  OK  ") for line in lines):
        try:
            if watchdog_s is None:  # the caller bounds the whole run
                rendered = _render(log, qml_dir)
            else:
                with watchdog(watchdog_s, log, what="the 3D self-test frame"):
                    rendered = _render(log, qml_dir)
            problems = [f"the builder of {failure} failed: the item has no solid"
                        for failure in rendered.build_failures]
            if rendered.other_threads:
                problems.append(
                    f"{rendered.other_threads} Qt message(s) of the render arrived on another "
                    "thread than the one that rendered: the message recorder is not safe here")
            problems += judge_frame(rendered.rgba, rendered.device_pixel_ratio)
            where = f"{rendered.graphics_api} / {rendered.adapter or 'adapter unknown'}"
            if problems:
                for problem in problems:
                    say(False, f"Qt Quick 3D frame on {where}: {problem}")
            else:
                height, width = rendered.rgba.shape[:2]
                say(True, f"Qt Quick 3D frame {width}x{height} on {where} in "
                          f"{rendered.open_ms:.0f} ms (Garden.qml, {len(SWATCH_KINDS) + 1} materials)")
        except Exception as exc:  # noqa: BLE001 - a QML or shader error arrives here
            say(False, f"Qt Quick 3D render -> {type(exc).__name__}: {exc}")
    ok = all(line.startswith("  OK  ") for line in lines)
    log("selftest_done", result="PASS" if ok else "FAIL",
        wall_ms=round((time.perf_counter() - started) * 1000.0))
    if owns_log:
        log.close()
    return SelftestResult(ok, tuple(lines), path)
