"""The 3D self-test on a real renderer, from source (Phase 17 L1.2, #385 — gate G10).

``--selftest`` is the gate every release passes through in the frozen exe, on a
runner without a GPU. Here the same code runs from source in a subprocess with a
real window system: it passes on the default adapter, it passes on the software
rasteriser (Windows: WARP — the release runner's condition), and it FAILS when a
shader is broken or when nothing can render. The frozen-exe half is the build's
(``ogp-change-control`` §2.8, ``docs/07-deployment-view``).

Judge and wiring are unit-tested without a GPU: ``tests/unit/test_quick3d_selftest.py``,
``tests/unit/test_main_hardening.py``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.quick3d_render_support import QML_SOURCE, REPO, render_env, render_tier

pytestmark = render_tier

# Run the package's own self-test in a child and turn its verdict into an exit code.
_RUN = (
    "import sys\n"
    "from pathlib import Path\n"
    "from open_garden_planner.ui.view3d.quick3d.selftest import run_selftest\n"
    "result = run_selftest(Path(sys.argv[1]), qml_dir=Path(sys.argv[2]) if len(sys.argv) > 2 else None)\n"
    "print('\\n'.join(result.lines))\n"
    "sys.exit(0 if result.ok else 1)\n"
)


#: Where the child's start-up hook (``quick3d_child_site``) reports, at exit, whether the
#: settings module was imported and how many settings stores the process built.
STORES = "OGP_TEST_CHILD_STORES"


def _selftest(tmp_path: Path, *args: str, **env: str) -> tuple[subprocess.CompletedProcess[str], str]:
    log = tmp_path / "selftest.log"
    env.setdefault(STORES, str(tmp_path / "stores.txt"))
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _RUN, str(log), *args], env=render_env(tmp_path, **env),
        capture_output=True, text=True, timeout=600, cwd=REPO)
    return proc, log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""


def test_the_3d_selftest_passes_on_the_default_adapter(tmp_path: Path) -> None:
    proc, log = _selftest(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:] + log
    lines = proc.stdout.splitlines()
    assert [line for line in lines if "import" in line] == [
        "  OK   import PyQt6.QtQml", "  OK   import PyQt6.QtQuick", "  OK   import PyQt6.QtQuick3D"]
    (frame,) = [line for line in lines if "Qt Quick 3D frame" in line]
    assert frame.startswith("  OK   Qt Quick 3D frame 160x120 on ") and "6 materials" in frame
    assert "[watchdog] armed=True" in log and "result=PASS" in log
    assert "adapter=None" not in log, "the log must name the graphics device"
    # The frozen exe runs this code under the PRODUCTION settings names — nothing can
    # rebind them there. So the 3D block must not build a settings store. (The settings
    # MODULE is imported — importing anything below ``open_garden_planner.ui`` does that —
    # which builds nothing: the second number is the count of stores built.)
    _imported, built = (tmp_path / "stores.txt").read_text(encoding="utf-8").split()
    assert built == "0", f"the 3D self-test built {built} settings store(s)"


@pytest.mark.skipif(sys.platform != "win32", reason="WARP is Direct3D's software rasteriser")
def test_the_3d_selftest_passes_without_a_gpu(tmp_path: Path) -> None:
    """The release runner's condition: Direct3D 11 on WARP. Forced here with
    ``QSG_RHI_PREFER_SOFTWARE_RENDERER=1``; the log proves which adapter rendered."""
    proc, log = _selftest(tmp_path, QSG_RHI_PREFER_SOFTWARE_RENDERER="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:] + log
    assert "adapter=Microsoft Basic Render Driver" in log
    assert "Microsoft Basic Render Driver" in proc.stdout


@pytest.mark.skipif(sys.platform != "win32",
                    reason="the whole --selftest also imports Qt3D, which needs the bundled Qt runtime")
def test_the_whole_selftest_command_passes(tmp_path: Path) -> None:
    """``python -m open_garden_planner --selftest`` — the Qt3D block, the Agent API
    block and the new 3D block together, as the frozen exe runs them."""
    log = tmp_path / "selftest.log"
    stores = tmp_path / "stores.txt"
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-m", "open_garden_planner", "--selftest"],
        env=render_env(tmp_path, OGP_SELFTEST_LOG=str(log), **{STORES: str(stores)}),
        capture_output=True, text=True, timeout=600, cwd=REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    # THE WHOLE COMMAND builds no settings store (it imports the settings module for
    # the application's two names, and nothing else of it): the frozen exe runs it under
    # the production names, against the user's real settings — which it must not touch.
    assert stores.read_text(encoding="utf-8").split() == ["1", "0"], "--selftest built a settings store"
    assert "SELFTEST: PASS" in proc.stdout
    assert "OK   Qt Quick 3D frame 160x120" in proc.stdout
    assert f"3D self-test log: {log}" in proc.stdout and log.is_file()
    # ONE watchdog around every block (review P1-4), and the verdict is in the log too
    text = log.read_text(encoding="utf-8")
    assert text.count("[watchdog] armed=True") == 1
    assert "[watchdog] armed=True seconds=300.0 what=--selftest" in text
    order = [text.index(marker) for marker in (
        "[selftest_start]", "[watchdog] armed=True", "[rendered]", "[selftest_done] result=PASS",
        "[selftest_exit] code=0 result=PASS")]
    assert order == sorted(order), text
    assert "[watchdog] fired=True" not in text, "the watchdog must not have announced a hang"
    assert "Timeout (" not in text, "faulthandler must not have dumped"
    # The self-test's own safety net is a subsystem too (review round 3, P2-5): a real
    # supervising process was started for this run, released, and left with exit code 0
    # — "supervisor=none" used to pass unnoticed. And no Qt message of the render arrived
    # on another thread than the one that rendered (P2-10).
    assert "what=--selftest supervisor=process " in text
    assert "[watchdog] released=True what=--selftest supervisor_exit=0" in text
    assert "[selftest_supervisor] ok=True detail=started, released, left" in text
    assert "[supervisor]" not in text, "the supervisor had nothing to do, and wrote nothing"
    assert "other_threads=0" in text


def test_the_3d_selftest_fails_on_a_shader_that_does_not_compile(tmp_path: Path) -> None:
    """Positive control: one renamed call in ``water.frag`` — a Qt WARNING, and a frame
    that still renders — fails the self-test and says why."""
    qml = tmp_path / "qml"
    shutil.copytree(QML_SOURCE, qml)
    shader = qml / "water.frag"
    text = shader.read_text(encoding="utf-8")
    assert "waterLuma(LIGHT_COLOR)" in text
    shader.write_text(text.replace("waterLuma(LIGHT_COLOR)", "waterLumaRenamed(LIGHT_COLOR)"),
                      encoding="utf-8")
    proc, log = _selftest(tmp_path, str(qml))
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    (failure,) = [line for line in proc.stdout.splitlines() if "FAIL" in line]
    assert "Qt Quick 3D render -> RenderError" in failure and "shader" in failure.lower()
    assert "result=FAIL" in log


def test_the_3d_selftest_draws_and_judges_the_selection_ring(tmp_path: Path) -> None:
    """L1.8: the ring's shader is compiled only when something is selected, so the
    self-test selects one swatch — and says so in its verdict line."""
    proc, log = _selftest(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:] + log
    (frame,) = [line for line in proc.stdout.splitlines() if "Qt Quick 3D frame" in line]
    assert frame.endswith("(Garden.qml, 6 materials, a baked ground of 12 tiles in 12 tile "
                          "paints, the selection ring)")  # the ground: L1.5


@pytest.mark.parametrize(("file", "old", "new"), [
    ("ring.vert", "POSITION.z, uDepthScale);", "POSITION.z, uDepthScaleMissing);"),
    ("ring.frag", "vec4(uColor, 1.0)", "vec4(uColorMissing, 1.0)"),
], ids=["ring.vert", "ring.frag"])
def test_the_3d_selftest_fails_on_a_ring_shader_that_does_not_compile(
        tmp_path: Path, file: str, old: str, new: str) -> None:
    """Positive control for the release gate: without the selected swatch the ring's
    shaders would never be compiled before a user selects something."""
    qml = tmp_path / "qml"
    shutil.copytree(QML_SOURCE, qml)
    shader = qml / file
    text = shader.read_text(encoding="utf-8")
    assert old in text
    shader.write_text(text.replace(old, new), encoding="utf-8")
    proc, log = _selftest(tmp_path, str(qml))
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    (failure,) = [line for line in proc.stdout.splitlines() if "FAIL" in line]
    assert "Qt Quick 3D render -> RenderError" in failure and "shader" in failure.lower()
    assert "result=FAIL" in log


def test_the_3d_selftest_fails_when_the_ring_is_drawn_behind_its_item(tmp_path: Path) -> None:
    """…and the JUDGE is not deaf either: a ring that compiles but is not where the
    band is (moved inward instead of outward) fails on the pixels."""
    qml = tmp_path / "qml"
    shutil.copytree(QML_SOURCE, qml)
    shader = qml / "ring.vert"
    text = shader.read_text(encoding="utf-8")
    assert "world.xyz += outward * (UV0.x * width);" in text
    shader.write_text(text.replace("world.xyz += outward * (UV0.x * width);",
                                   "world.xyz -= outward * (UV0.x * width * 4.0);"),
                      encoding="utf-8")
    proc, log = _selftest(tmp_path, str(qml))
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    failures = [line for line in proc.stdout.splitlines() if "FAIL" in line]
    assert any("the selection ring did not draw round the roof swatch" in line for line in failures)
    assert "result=FAIL" in log


def test_the_3d_selftest_fails_where_nothing_renders(tmp_path: Path) -> None:
    """Under the offscreen platform Qt Quick falls back to the software scene graph,
    which has no 3D. The render refuses to hand out a frame without the garden and
    names the backend — the self-test cannot pass by accident, and its message
    says what is wrong with the machine rather than "the box is not there"."""
    proc, log = _selftest(tmp_path, QT_QPA_PLATFORM="offscreen")
    assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
    (failure,) = [line for line in proc.stdout.splitlines() if "FAIL" in line]
    assert "Qt Quick 3D render -> RenderError" in failure
    assert "Software backend" in failure and "no 3D frame can be rendered" in failure
    assert "result=FAIL" in log
