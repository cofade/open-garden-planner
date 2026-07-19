"""Mechanical tileability check for fill-pattern textures (US-E9, #264).

Metric: a texture tiles seamlessly when its wrap seam (last column against
first column, last row against first row) is no rougher than the roughest
transitions the texture ALREADY contains. The mean-vs-mean ratio punishes
structured tiles unfairly (a decking board gap is a hard edge that repeats
every 64 px — the wrap seam legitimately looks like one), so the seam's
mean luminance step is compared against the 98th percentile of the
internal adjacent-row/column mean steps: a seamless tile's seam sits
inside its own edge family (ratio ≤ 1-ish), a genuinely non-tiling image
(e.g. a gradient, or a photo crop) towers above it.

Threshold: 1.6 — calibrated in tests/unit/test_texture_tileability.py:
the asset-forge pilots and the wood/gravel/grass calibrators pass, a
synthetic gradient fails by an order of magnitude. Several LEGACY textures
(e.g. glass, flagstone, stone) fail — real seams, recorded in the test's
known-seamed list as future regeneration candidates for this very skill.

Usage:  venv/Scripts/python.exe scripts/check_texture_tileability.py [paths...]
(no paths = check every PNG in resources/textures/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

SEAM_RATIO_THRESHOLD = 1.6

#: Percentile of the internal step distribution the seam is measured
#: against — high enough to include a structured tile's own hard edges.
_INTERNAL_PERCENTILE = 98.0

_TEXTURES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "textures"
)


def seam_ratios(image: Image.Image) -> tuple[float, float]:
    """(horizontal, vertical) wrap-seam roughness vs the texture's own
    roughest internal transitions (98th percentile of per-lag mean steps)."""
    grey = np.asarray(image.convert("L"), dtype=np.float64)
    eps = 1e-9
    # Per-column-boundary mean step (axis=1) and per-row-boundary (axis=0).
    internal_x = np.mean(np.abs(np.diff(grey, axis=1)), axis=0)  # (w-1,)
    internal_y = np.mean(np.abs(np.diff(grey, axis=0)), axis=1)  # (h-1,)
    ref_x = float(np.percentile(internal_x, _INTERNAL_PERCENTILE)) + eps
    ref_y = float(np.percentile(internal_y, _INTERNAL_PERCENTILE)) + eps
    seam_x = float(np.mean(np.abs(grey[:, 0] - grey[:, -1])))
    seam_y = float(np.mean(np.abs(grey[0, :] - grey[-1, :])))
    return seam_x / ref_x, seam_y / ref_y


def is_tileable(image: Image.Image, threshold: float = SEAM_RATIO_THRESHOLD) -> bool:
    ratio_x, ratio_y = seam_ratios(image)
    return ratio_x <= threshold and ratio_y <= threshold


def main(argv: list[str]) -> int:
    paths = (
        [Path(p) for p in argv[1:]]
        if len(argv) > 1
        else sorted(_TEXTURES_DIR.glob("*.png"))
    )
    failures = 0
    for path in paths:
        ratio_x, ratio_y = seam_ratios(Image.open(path))
        verdict = "ok" if max(ratio_x, ratio_y) <= SEAM_RATIO_THRESHOLD else "SEAM"
        if verdict != "ok":
            failures += 1
        print(f"{path.name:20s} x={ratio_x:6.2f} y={ratio_y:6.2f}  {verdict}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
