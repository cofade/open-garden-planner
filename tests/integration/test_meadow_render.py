"""The meadow's grass on the real engine (#798, ADR-048 addendum "the meadow's grass") —
render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins the
design (``test_scene3d_meadow.py``: the texture's mean is the meadow's albedo, every mip
keeps it; ``test_quick3d_qml.py``: every piece of ground draws ``ground.frag`` with the
same inputs; ``test_scene3d_ground_rules.py``: the bake leaves open ground open). Here the
ENGINE answers the issue's "done when", per bundled example, through the production Beauty
Board's ``--meadow`` phase (``render_beauty_board.py``, ``board_probes.flat_share`` /
``temporal_noise`` / ``repeat_amplitude``):

- the default framing is no felt table: the share of FLAT green pixels (local luma std
  under 1.5 over 9 x 9 px — the 3D survey's instrument; 79-80 % on the base) stays under
  ``MAX_FLAT_GREEN`` on every example, and the meadow itself has a texture;
- the far meadow does not shimmer while the default framing orbits, nor in a low flight
  beside the plan (``MAX_ZIGZAG``), and the grass's 2.56 m repeat does not show from
  above (``MAX_REPEAT_LUMA``).

The plan's edge and the horizon are judged where they always were, on the new surface:
``test_view3d_looks_render.py`` (``--edge``, ``--horizon``).

    # Windows (Git Bash) - one board at a time
    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 tests/integration/test_meadow_render.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.quick3d_render_support import REPO, keep_artifacts, render_env, render_tier

pytestmark = render_tier

BOARD = REPO / "scripts" / "render_beauty_board.py"
EXAMPLES = REPO / "src" / "open_garden_planner" / "resources" / "examples"
PLANS = ("family-garden", "food-forest", "raised-bed", "balcony")
TIMEOUT_S = 1500
#: The flat share depends on the picture's size: at 640 x 360 a pixel covers four times the
#: grass, its 9 x 9 window four times the ground, and the default framing read 0.31 / 0.24
#: flat green (family garden / food forest; base about 0.8). The bounds below are the
#: evidence's, at 1280 x 720 — this tier runs on a GPU (CI's render job does not run it).
SIZE = "1280x720"

# ── the bounds, each with what was measured (RTX 4070, High; the base 56ab8e0c and the
# branch, 2026-11-10; at 1280 x 720 unless said) ─────────────────────────────────────
#: The default framing's share of flat green pixels. Base: 0.73-0.80 (family garden 0.790,
#: food forest 0.804, raised bed 0.734, balcony 0.753). Branch: 0.000-0.131 — what is left is
#: the fogged band at the top of the frame, flat by the haze.
MAX_FLAT_GREEN = 0.20
#: The meadow's own texture in the default framing: the mean local luma std over the
#: meadow (``meadow_mask``). Base: 0.54-0.62 (the survey's 0.54). Branch: 5.7-9.7.
MIN_MEADOW_TEXTURE = 2.0
#: The far meadow's flicker through a move: the zigzag RMS of fixed ground points read
#: bilinearly (``board_probes.track_luma``). Base (a flat meadow): orbit 0.09-0.10, flight
#: 0.03-0.04. Branch: orbit 0.23-0.33, flight 0.10-0.11. The grass WITHOUT mipmaps (the
#: positive control, a mutated Garden.qml through ``--qml-dir``): orbit 3.38, flight 5.40.
MAX_ZIGZAG = 0.6
#: The grass's repeat from 60 m above: the luma amplitude of the frame folded onto one
#: repeat (``board_probes.repeat_amplitude``). Flat base 0.002; the first round's grass,
#: whose 2.56 m mottle drew a visible lattice, 2.15; the branch 0.86.
MAX_REPEAT_LUMA = 1.5


def _board(out: Path, plan: str) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(BOARD), "--out", str(out), "--plan", str(EXAMPLES / f"{plan}.ogp"),
         "--presets", "high", "--shots", "none", "--meadow", "--size", SIZE,
         "--watchdog-s", str(TIMEOUT_S - 60)],
        env=render_env(out), capture_output=True, text=True, timeout=TIMEOUT_S, cwd=REPO)
    keep_artifacts(out, proc)
    file = out / "metrics.json"
    metrics = json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}
    log = (out / "board.log").read_text(encoding="utf-8", errors="replace")[-2500:] if (
        out / "board.log").is_file() else "<no log>"
    assert proc.returncode == 0 and metrics.get("status") == "ok", (
        f"exit {proc.returncode}\n{proc.stderr[-2000:]}\n{log}")
    assert metrics["qt_messages"]["counts"]["error"] == 0, metrics["qt_messages"]
    assert metrics["qt_messages"]["counts"]["warning"] == 0, metrics["qt_messages"]
    return dict(metrics["meadow"]["high"])


@pytest.mark.parametrize("plan", PLANS)
def test_the_default_framing_is_no_felt_table(tmp_path: Path, plan: str) -> None:
    """#798's "done when": the meadow's share of flat tiles in the default framing is under
    a stated bound on every bundled example, the far meadow does not shimmer in a camera
    move and its repeat does not show."""
    meadow = _board(tmp_path / plan, plan)
    default = meadow["default"]
    assert default["frame"]["flat_green"] < MAX_FLAT_GREEN, default
    assert default["meadow"]["pixels"] > 10_000, default      # the probe saw the meadow
    assert default["meadow"]["local_std"] > MIN_MEADOW_TEXTURE, default
    for move in ("orbit", "flight"):
        assert meadow[move]["points"] >= 100, (move, meadow[move])
        assert meadow[move]["zigzag_rms"] < MAX_ZIGZAG, (move, meadow[move])
    assert meadow["repeat"]["periodic"] < MAX_REPEAT_LUMA, meadow["repeat"]
