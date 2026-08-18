"""Mechanical tileability gate for fill-pattern textures (US-E9, #264; all 24
regenerated seamless-by-construction in Package 3b, #309).

The metric lives in ``scripts/check_texture_tileability.py`` (loaded here
by path — scripts/ is not a package); this test pins:
- EVERY shipped texture passes (since #309 there is no grandfathered seam),
- the calibrators still pass (threshold calibration, unchanged at 1.6),
- a synthetic non-tileable image FAILS (the metric has teeth),
- the legacy-seam list is — and stays — empty.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_ROOT = Path(__file__).parent.parent.parent
_TEXTURES = _ROOT / "src" / "open_garden_planner" / "resources" / "textures"

_spec = importlib.util.spec_from_file_location(
    "check_texture_tileability", _ROOT / "scripts" / "check_texture_tileability.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

#: Legacy textures with real wrap seams. Was {"flagstone.png", "glass.png"}
#: (mechanical audit 2026-07-20); emptied 2026-08-18 by Package 3b (#309) —
#: every texture is now generated on a torus. This set may only shrink, and
#: it cannot shrink further: `test_legacy_seam_list_is_empty` pins it.
KNOWN_SEAMED_LEGACY: set[str] = set()

ALL_TEXTURES = sorted(p.name for p in _TEXTURES.glob("*.png"))


@pytest.mark.parametrize("name", ALL_TEXTURES)
def test_every_texture_is_tileable(name: str) -> None:
    image = Image.open(_TEXTURES / name)
    ratio_x, ratio_y = _mod.seam_ratios(image)
    assert _mod.is_tileable(image), f"{name} fails the seam check (x={ratio_x:.2f}, y={ratio_y:.2f})"


def test_known_good_calibrators_pass() -> None:
    """The three calibrators from #264 (organic + structured) still pass at
    the unchanged 1.6 threshold — the recalibration rule of #309 ("design
    seams below 1.6; recalibrate only with a written rationale") held."""
    for name in ("wood.png", "gravel.png", "grass.png", "decking.png"):
        assert _mod.is_tileable(Image.open(_TEXTURES / name)), name


def test_metric_rejects_non_tileable() -> None:
    # Horizontal gradient exercises the x branch…
    gradient = np.tile(
        np.linspace(0, 255, 256, dtype=np.uint8), (256, 1)
    )
    image = Image.fromarray(gradient, mode="L").convert("RGB")
    assert not _mod.is_tileable(image)
    # …its transpose the y branch (is_tileable short-circuits on `and`).
    transposed = Image.fromarray(gradient.T.copy(), mode="L").convert("RGB")
    assert not _mod.is_tileable(transposed)


def test_metric_rejects_detailed_non_tiling_texture() -> None:
    """A DETAILED image that doesn't tile must also fail — teeth beyond the
    trivial gradient. Fixture: a real shipped texture under a luminance
    ramp, the classic uneven-lighting defect of photo/AI-generated
    candidates (texture detail intact, wrap seam = a lighting jump)."""
    wood = np.asarray(
        Image.open(_TEXTURES / "wood.png").convert("L"), dtype=np.float64
    )
    ramp = 0.55 + 0.45 * np.linspace(0.0, 1.0, wood.shape[1])[None, :]
    lit = np.clip(wood * ramp, 0, 255).astype(np.uint8)
    image = Image.fromarray(lit, mode="L").convert("RGB")
    assert not _mod.is_tileable(image)


def test_legacy_seam_list_is_empty() -> None:
    """#309 emptied the grandfather list; a re-grown list would mean a seamed
    texture was committed without going through the forge."""
    assert not KNOWN_SEAMED_LEGACY
    failing = {
        path.name
        for path in sorted(_TEXTURES.glob("*.png"))
        if not _mod.is_tileable(Image.open(path))
    }
    assert failing == set(), f"seamed textures: {failing}"
