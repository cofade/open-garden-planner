"""Mechanical tileability gate for fill-pattern textures (US-E9, #264).

The metric lives in ``scripts/check_texture_tileability.py`` (loaded here
by path — scripts/ is not a package); this test pins:
- the asset-forge pilot textures pass,
- known-good existing textures pass (threshold calibration),
- a synthetic non-tileable image FAILS (the metric has teeth),
- the legacy-seam list doesn't silently grow.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image

_ROOT = Path(__file__).parent.parent.parent
_TEXTURES = _ROOT / "src" / "open_garden_planner" / "resources" / "textures"

_spec = importlib.util.spec_from_file_location(
    "check_texture_tileability", _ROOT / "scripts" / "check_texture_tileability.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

#: Legacy textures with real wrap seams (mechanical audit 2026-07-20) —
#: regeneration candidates for the ogp-asset-forge skill, grandfathered
#: with owner sign-off pending (PROVENANCE.md). This list may only shrink.
KNOWN_SEAMED_LEGACY = {"flagstone.png", "glass.png"}


def test_pilot_textures_are_tileable() -> None:
    for name in ("decking.png", "corten.png"):
        image = Image.open(_TEXTURES / name)
        assert _mod.is_tileable(image), f"{name} fails the seam check"


def test_known_good_calibrators_pass() -> None:
    """≥1 existing texture must pass (issue #264's calibration rule) —
    three do, spanning organic and structured styles."""
    for name in ("wood.png", "gravel.png", "grass.png"):
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


def test_legacy_seam_list_does_not_grow() -> None:
    failing = {
        path.name
        for path in sorted(_TEXTURES.glob("*.png"))
        if not _mod.is_tileable(Image.open(path))
    }
    assert failing <= KNOWN_SEAMED_LEGACY, (
        f"new seamed textures appeared: {failing - KNOWN_SEAMED_LEGACY}"
    )
