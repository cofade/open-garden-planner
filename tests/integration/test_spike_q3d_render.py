"""End-to-end render of the Qt Quick 3D spike — the first test that renders a 3D frame.

Opt-in (render tier "B" of the plan): needs a real RHI context, which the
default ``QT_QPA_PLATFORM=offscreen`` CI job cannot create (the offscreen QPA
falls back to the *software* scene graph, which has no 3D). Run it with::

    OGP_RENDER3D=1 xvfb-run -a -s "-screen 0 1920x1080x24" \\
        venv/bin/python -m pytest tests/integration/test_spike_q3d_render.py

The spike runs in a subprocess with ``QT_QPA_PLATFORM=xcb`` +
``QSG_RHI_BACKEND=opengl`` (Mesa llvmpipe in a container, the real GPU on a dev
box) and the assertions are about MEANING, never pixel-exact goldens: the
shadow map agrees with the analytic 2D shadow (ADR-047 criterion 8), the ground
texture is north-up, the sky's sun disc sits at the solar azimuth.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    os.environ.get("OGP_RENDER3D") != "1" or not os.environ.get("DISPLAY"),
    reason="render tier: set OGP_RENDER3D=1 and run under a display (xvfb-run)",
)


@pytest.fixture(scope="module")
def spike_metrics(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    out = tmp_path_factory.mktemp("spike_q3d")
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", QSG_RHI_BACKEND="opengl")
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    proc = subprocess.run(  # noqa: S603 — fixed argv, our own module
        [sys.executable, "-m", "open_garden_planner", "--spike-q3d",
         "--plan", str(REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"),
         "--out", str(out), "--presets", "medium", "--shots", "noon",
         "--size", "640x360", "--fps-seconds", "0", "--iou", "--orient"],
        env=env, capture_output=True, text=True, timeout=900, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads((out / "metrics.json").read_text(encoding="utf-8")), out


def test_renders_a_real_frame(spike_metrics: tuple[dict, Path]) -> None:
    metrics, out = spike_metrics
    assert metrics["graphics_api"] in ("OpenGL", "Direct3D11", "Vulkan", "Metal", "Direct3D12")
    from PyQt6.QtGui import QImage

    img = QImage(str(out / "noon_medium.png"))
    assert not img.isNull()
    values = {img.pixel(x, y) for x in range(0, img.width(), 37) for y in range(0, img.height(), 29)}
    assert len(values) > 200  # a real scene, not a cleared framebuffer


def test_shadow_map_agrees_with_the_analytic_shadow(spike_metrics: tuple[dict, Path]) -> None:
    metrics, _ = spike_metrics
    for elev, row in metrics["shadow_iou"]["results"].items():
        assert row["iou"] >= 0.85, (elev, row)


def test_ground_is_north_up_and_sky_sun_follows_the_azimuth(spike_metrics: tuple[dict, Path]) -> None:
    metrics, _ = spike_metrics
    assert metrics["orientation"]["ground_texture_ok"], metrics["orientation"]["ground_texture_ncc"]
    assert metrics["orientation"]["sky_ok"], metrics["orientation"]["sky_sun_disc"]
