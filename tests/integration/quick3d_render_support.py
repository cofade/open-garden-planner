"""The judging half of the 3D render tier: start the driver, read frames, predict pixels.

Not a test module. See ``quick3d_render_driver.py`` for why the tier is split into
a process that renders (real QPA) and tests that judge (the offscreen test
process), and ``docs/08-crosscutting-concepts`` §8.10.26 for the pattern.

Running the tier (opt-in; it opens windows on the desktop)::

    # Windows (PowerShell):  $env:OGP_RENDER3D = "1"; venv\\Scripts\\python.exe -m pytest <files>
    # Linux:                 OGP_RENDER3D=1 xvfb-run -a -s "-screen 0 1920x1080x24" \\
    #                            python -m pytest <files>

    <files> = tests/integration/test_quick3d_render.py tests/integration/test_quick3d_engine.py

THREE rules for every child process a test of the engine package starts:

- **It never builds a settings store on the developer's key.** The app's settings are a
  registry key on Windows, which no environment variable moves; ``tests/conftest.py``
  rebinds the store's names for the test process, and a child does not import
  conftest. ``isolated_env`` therefore puts ``quick3d_child_site`` first on the
  child's ``PYTHONPATH``: its ``sitecustomize`` rebinds the names the moment the
  child imports the app's settings module — before a store can exist — and empties
  the child's own key at exit. (Loading a plan ends with a write to Recent Files.)
- **It never sees the developer's data, and leaves nothing in the developer's
  profile.** ``isolated_env`` points the variables the app's data directory hangs on
  at a directory of the test's own, and the user PROFILE itself (which Qt's standard
  paths and the graphics driver's caches follow: ``USERPROFILE`` on Windows, ``HOME``
  elsewhere) at one of this test process's own — whatever the parent's environment
  says. It is the parent's environment with those variables REPLACED, not an empty
  one: a child still needs ``PATH``, the display, the CI switches.
- **No Python Qt message handler beside a shown window.** Qt renders a shown window
  on a thread of its own, and PyQt's handler trampoline needs the GIL: the two
  deadlock (``qt_messages.py``). So the driver installs none for its shown-host
  scenarios. Qt writes its messages to the child's stderr in a fixed pattern
  (``QT_MESSAGE_PATTERN``), and ``driver_messages`` classifies them HERE, in the
  test process — the render tier runs the render loop the product runs.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from open_garden_planner.core.scene3d import Record, pose_ring
from open_garden_planner.ui.view3d.quick3d.qt_messages import CLASSES, classify, graphics_adapter
from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot, top_down_pixel

REPO = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).resolve().with_name("quick3d_render_driver.py")
QML_SOURCE = REPO / "src" / "open_garden_planner" / "ui" / "view3d" / "quick3d" / "qml"
#: A directory that holds one file, ``sitecustomize.py``: Python imports it at start-up in
#: every child whose environment ``isolated_env`` built (module docstring, first rule).
CHILD_SITE = Path(__file__).resolve().with_name("quick3d_child_site")
#: Set in every environment ``isolated_env`` builds: "this process was started isolated".
ISOLATED_MARK = "OGP_TEST_ISOLATED_CHILD"
DRIVER_TIMEOUT_S = 840
QT_ERRORS_EXIT = 4
#: How Qt prints a message on the child's stderr, and what the driver prints between
#: scenarios — one prefix, so that everything else on stderr is recognisably not Qt's.
QT_LINE = "OGPQT|"
QT_MESSAGE_PATTERN = QT_LINE + "%{type}|%{category}|%{message}"
SCENARIO_MARK = QT_LINE + "scenario|"


def render_tier_skip_reason() -> str | None:
    """None when the render tier can run here, else why it is skipped."""
    if os.environ.get("OGP_RENDER3D") != "1":
        return "render tier (opt-in): set OGP_RENDER3D=1 — it needs a real window system"
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return "render tier on Linux needs an X display: run under xvfb-run"
    return None


render_tier = [
    pytest.mark.skipif(render_tier_skip_reason() is not None,
                       reason=render_tier_skip_reason() or ""),
    # one driver process serves a whole module (seconds on a GPU, a minute or two on
    # a software rasteriser); the global 180 s per-test timeout would abort the
    # module fixture the first test pays for
    pytest.mark.timeout(900),
]


#: The variables the app derives its per-user data directory from
#: (``services/plant_library.get_app_data_dir`` reads them on every call), and the
#: folder each is pointed at under a test's own scratch directory.
PRIVATE_DIRS = (("APPDATA", "appdata"), ("XDG_DATA_HOME", "data_home"),
                ("XDG_CONFIG_HOME", "config_home"))


def private_dirs(scratch: Path) -> dict[str, str]:
    """``PRIVATE_DIRS`` as variable → directory under ``scratch`` (created here)."""
    made = {}
    for name, folder in PRIVATE_DIRS:
        target = scratch / folder
        target.mkdir(parents=True, exist_ok=True)
        made[name] = str(target)
    return made


_SESSION_PROFILE: list[Path] = []


def session_profile() -> Path:
    """A user profile for the children of THIS test process — one per process, in an
    unpredictable temp directory, removed at exit.

    What hangs on the profile is not the app's data but what Qt and the graphics
    driver keep per user: ``QStandardPaths`` (the app's log directory, Qt Quick's
    shader cache) and the driver's shader caches. Per process and not per test, so
    that the children of one run share warm caches as the processes of a real
    session do — and none of it lands in the developer's profile.
    """
    if not _SESSION_PROFILE:
        root = Path(tempfile.mkdtemp(prefix="ogp-quick3d-profile-"))
        atexit.register(shutil.rmtree, root, True)  # ignore_errors: a child may still hold a file
        _SESSION_PROFILE.append(root)
    return _SESSION_PROFILE[0]


def profile_dirs() -> dict[str, str]:
    """The variables that move a child's user profile to ``session_profile()``.

    Windows: ``USERPROFILE``. Measured (Qt 6.11): the shell expands its known folders
    from it, so ``QStandardPaths`` answers ``<USERPROFILE>/AppData/Roaming`` and
    ``…/AppData/Local`` — it does NOT read ``APPDATA``. ``LOCALAPPDATA`` goes along
    for code that reads the variable. Elsewhere: ``HOME`` — what every XDG location
    without a variable of its own falls back to (the state directory, Documents) —
    and ``XDG_CACHE_HOME`` (the data and config homes are per test: ``private_dirs``).
    """
    profile = session_profile()
    if sys.platform == "win32":
        local = profile / "AppData" / "Local"
        local.mkdir(parents=True, exist_ok=True)
        (profile / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
        return {"USERPROFILE": str(profile), "LOCALAPPDATA": str(local)}
    cache, home = profile / "cache", profile / "home"
    cache.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "XDG_CACHE_HOME": str(cache)}


def kept_from_the_real_home(environ: dict[str, str]) -> dict[str, str]:
    """What a child still needs once ``HOME`` points elsewhere (not on Windows) — two
    read-only lookups, named so that nothing else follows the real home by accident:

    - ``PYTHONUSERBASE``: Python's per-user site directory hangs on ``HOME``; a
      ``pip install --user`` environment would lose its packages in the child;
    - ``XAUTHORITY``: Xlib falls back to ``~/.Xauthority`` for the display's cookie
      (``xvfb-run`` sets the variable itself).
    """
    if sys.platform == "win32":
        return {}
    kept = {}
    user_base = site.getuserbase()
    if "PYTHONUSERBASE" not in environ and user_base:
        kept["PYTHONUSERBASE"] = user_base
    cookie = Path.home() / ".Xauthority"
    if "XAUTHORITY" not in environ and cookie.is_file():
        kept["XAUTHORITY"] = str(cookie)
    return kept


def isolated_env(scratch: Path, **extra: str) -> dict[str, str]:
    """A child's environment that cannot reach the developer's data, profile or
    settings, with THIS checkout's code on its path — the base of every child a test
    of the engine package starts.

    ``APPDATA`` / ``XDG_DATA_HOME`` / ``XDG_CONFIG_HOME`` are set EXPLICITLY to
    directories under ``scratch`` (``private_dirs``), whatever the parent has: the
    app keeps custom plants, plant lists and smart symbols under the first two,
    and a child that loads a plan creates them. The user profile is this test
    process's own (``profile_dirs``): logs and caches. PYTHONPATH: a
    ``python tests/…/driver.py`` child would otherwise import whatever the venv's
    editable install points at — from a git worktree, the main checkout. Its FIRST
    entry is ``CHILD_SITE``: the start-up hook that gives the child a settings key
    of its own.
    """
    env = dict(os.environ)
    env.update(kept_from_the_real_home(env))  # read BEFORE the home moves
    env.update(private_dirs(scratch))
    env.update(profile_dirs())
    paths = [str(CHILD_SITE), str(REPO / "src"), str(REPO), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in paths if p)
    env[ISOLATED_MARK] = "1"
    env.update(extra)
    return env


def render_env(scratch: Path, **extra: str) -> dict[str, str]:
    """``isolated_env`` plus a REAL Qt platform, and Qt's messages on stderr.

    The test process runs ``QT_QPA_PLATFORM=offscreen`` (tests/conftest.py), which
    selects the software scene graph — no 3D. Windows: the default platform and
    Direct3D 11 (the real GPU, or WARP where there is none). Linux: xcb + OpenGL
    (Mesa llvmpipe in a container).

    Qt's own handler writes every message to stderr in ``QT_MESSAGE_PATTERN``
    (forced: on Windows a process without a console logs to the debugger
    otherwise), and ``qt.rhi.general`` debug output is on, so that the adapter is
    named — all without a line of Python on Qt's render thread.
    """
    env = isolated_env(scratch)
    env.pop("QT_QPA_PLATFORM", None)
    if sys.platform.startswith("linux"):
        env["QT_QPA_PLATFORM"] = "xcb"
        env.setdefault("QSG_RHI_BACKEND", "opengl")
        env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"  # Chromium refuses root with a sandbox
    env["QT_FORCE_STDERR_LOGGING"] = "1"
    env["QT_MESSAGE_PATTERN"] = QT_MESSAGE_PATTERN
    env["QT_LOGGING_RULES"] = "qt.rhi.general.debug=true"
    env.update(extra)
    return env


def driver_messages(stderr: str) -> dict[str, Any]:
    """Qt's messages from a child's stderr, classified with the product's own rules.

    Returns counts per class for the whole run and per scenario (the driver prints
    a mark before each), the error / warning / environment lines, and the graphics
    adapter Qt named. Lines without the pattern's prefix continue the message
    before them (a shader error is several lines) or are not Qt's at all.
    """
    records: list[list[str]] = []  # scenario, kind, category, text
    scenario = ""
    continues = False  # the lines that follow belong to the last record
    for line in stderr.splitlines():
        if line.startswith(SCENARIO_MARK):
            scenario, continues = line[len(SCENARIO_MARK):].strip(), False
        elif line.startswith(QT_LINE):
            kind, _, rest = line[len(QT_LINE):].partition("|")
            category, _, text = rest.partition("|")
            records.append([scenario, kind, "" if category == "default" else category, text])
            continues = True
        elif continues:
            records[-1][3] += "\n" + line
    counts = dict.fromkeys(CLASSES, 0)
    by_scenario: dict[str, dict[str, int]] = {}
    kept: dict[str, list[str]] = {name: [] for name in CLASSES}
    for where, kind, category, text in records:
        cls = classify(kind, text, category)
        counts[cls] += 1
        by_scenario.setdefault(where, dict.fromkeys(CLASSES, 0))[cls] += 1
        kept[cls].append(f"{kind}: {category + ': ' if category else ''}{text}")
    return {"counts": counts, "by_scenario": by_scenario, "errors": kept["error"],
            "warnings": kept["warning"], "environment": kept["environment"],
            "adapter": graphics_adapter(kept["info"]), "messages": len(records)}


def run_driver(out: Path, scenarios: str, *, qml_dir: Path | None = None,
               env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    """Run the driver; return the process and its ``result.json`` ({} when it wrote none)."""
    command = [sys.executable, str(DRIVER), "--out", str(out), "--scenarios", scenarios,
               "--watchdog-s", str(DRIVER_TIMEOUT_S - 60)]
    if qml_dir is not None:
        command += ["--qml-dir", str(qml_dir)]
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        command, env=env if env is not None else render_env(out), capture_output=True, text=True,
        timeout=DRIVER_TIMEOUT_S, cwd=REPO)
    result_file = out / "result.json"
    result = json.loads(result_file.read_text(encoding="utf-8")) if result_file.is_file() else {}
    if result:
        # what Qt said while windows were SHOWN — read from the child's stderr, judged here
        shown = driver_messages(proc.stderr)
        result["qt_messages"] = shown
        result["adapter"] = shown["adapter"] or _offscreen_adapter(result)
    keep_artifacts(out, proc)
    return proc, result


def _offscreen_adapter(result: dict[str, Any]) -> str | None:
    """The adapter an offscreen frame of the run named (a run without a shown window)."""
    for scenario in result.get("scenarios", {}).values():
        for frame in scenario.values() if isinstance(scenario, dict) else ():
            if isinstance(frame, dict) and frame.get("adapter"):
                return str(frame["adapter"])
    return None


def keep_artifacts(out: Path, proc: subprocess.CompletedProcess[str]) -> None:
    """Copy a driver run's frames, ``result.json`` and log to ``OGP_RENDER3D_ARTIFACTS``
    (CI uploads that directory) — a failed render on a runner nobody can log into is
    only debuggable from its pictures."""
    target = os.environ.get("OGP_RENDER3D_ARTIFACTS")
    if not target:
        return
    destination = Path(target) / f"{out.parent.name}-{out.name}"
    shutil.copytree(out, destination, dirs_exist_ok=True)
    (destination / "driver-stdio.txt").write_text(
        f"exit {proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        encoding="utf-8")


def failure_report(proc: subprocess.CompletedProcess[str], out: Path) -> str:
    """Everything a failed driver run left behind, for the assertion message."""
    log = out / "render.log"
    tail = log.read_text(encoding="utf-8", errors="replace")[-3000:] if log.is_file() else "<no log>"
    return f"exit {proc.returncode}\n--- stderr ---\n{proc.stderr[-2000:]}\n--- render.log ---\n{tail}"


# ── pixels ───────────────────────────────────────────────────────────────────


def load_rgb(path: Path) -> np.ndarray:
    """A PNG as an (h, w, 3) int array."""
    from PyQt6.QtGui import QImage

    image = QImage(str(path))
    assert not image.isNull(), f"cannot read {path}"
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bytes(bits), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, :image.width(), :3].astype(np.int64)


def luma(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


# The top-down view is not tone-mapped: a pixel is linear radiance, so the probe
# colours of the driver (pure red / blue / yellow tints) clip to pure channels there.
def red_mask(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., 0] > 150) & (rgb[..., 1] < 70) & (rgb[..., 2] < 70)


def blue_mask(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., 2] > 150) & (rgb[..., 0] < 70) & (rgb[..., 1] < 90)


def yellow_mask(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., 0] > 150) & (rgb[..., 1] > 150) & (rgb[..., 2] < 90)


def polygon_mask(points: Sequence[tuple[float, float]], width: int, height: int) -> np.ndarray:
    """Pixels whose CENTRE lies inside the pixel-space polygon (even-odd rule)."""
    xs, ys = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    inside = np.zeros((height, width), dtype=bool)
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        if y1 == y2:
            continue
        crosses = (y1 > ys) != (y2 > ys)
        at = (x2 - x1) * (ys - y1) / (y2 - y1) + x1
        inside ^= crosses & (xs < at)
    return inside


def scene_polygon_mask(polygon: Sequence[tuple[float, float]], shot: TopDownShot,
                       shape: tuple[int, ...], dpr: float = 1.0) -> np.ndarray:
    """Where OUR projection puts a scene-frame polygon in a top-down frame."""
    height, width = shape[:2]
    pixels = [top_down_pixel(x, y, shot, (width, height), dpr) for x, y in polygon]
    return polygon_mask(pixels, width, height)


def footprint_mask(record: Record, shot: TopDownShot, shape: tuple[int, ...],
                   dpr: float = 1.0) -> np.ndarray:
    """The CPU prediction of a prism in the top-down view: its posed footprint
    (``core.scene3d.pose_ring``) — an orthographic top view shows the top face only."""
    return scene_polygon_mask(pose_ring(record.transform, record.footprints[0]), shot, shape, dpr)


def iou(first: np.ndarray, second: np.ndarray) -> float:
    union = int((first | second).sum())
    return float((first & second).sum() / union) if union else 0.0


def centroid(mask: np.ndarray) -> tuple[float, float]:
    """Centre of a mask in continuous pixel coordinates (pixel centres at +0.5)."""
    rows, cols = np.nonzero(mask)
    assert rows.size, "empty mask"
    return float(cols.mean() + 0.5), float(rows.mean() + 0.5)
