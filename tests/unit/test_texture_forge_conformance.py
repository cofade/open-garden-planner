"""Conformance gate for the texture forge (Package 3b, #309, ADR-042 / FR-30).

`scripts/generate_asset_forge_textures.py` is the single source of every
fill-pattern texture. This test pins the contract between the generator, the
`FillPattern` loader table and the committed PNGs:

- registry ↔ `_TEXTURE_FILES` ↔ files on disk agree (no orphan, no missing);
- every committed PNG is 256×256 RGB and decodes to EXACTLY the generator's
  pixels (pixel-determinism — PNG is lossless, and the deflate stream is
  deliberately not the contract because it depends on the zlib build Pillow
  bundles: a Linux CI wheel and a Windows wheel may encode identical pixels to
  different bytes);
- the visual-weight band the runtime tint needs (mean luminance, spread,
  local detail — a texture that flattens to one tone under the 80/255 tint
  overlay would fail here before an owner ever sees it);
- the gate has teeth (a one-pixel edit is reported STALE) and regeneration
  is a no-op for current files (no git noise across platforms);
- the Qt-painted legacy generator is gone (one generator, one contract).

The generator is loaded by path — `scripts/` is not a package (same pattern
as `test_texture_tileability.py`).
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from open_garden_planner.core.fill_patterns import _TEXTURE_FILES, FillPattern

_ROOT = Path(__file__).parent.parent.parent
_TEXTURES = _ROOT / "src" / "open_garden_planner" / "resources" / "textures"

_spec = importlib.util.spec_from_file_location(
    "generate_asset_forge_textures", _ROOT / "scripts" / "generate_asset_forge_textures.py"
)
forge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(forge)

ALL_NAMES = sorted(forge.TEXTURES)

# Visual-weight band, measured on the shipped set 2026-08-18 (8-bit luminance):
# mean 46.7 (compost) … 215.3 (glass); std 4.6 (concrete, sand) … 29.3 (brick);
# local detail (mean |neighbour step|, both axes summed) 2.61 (corten) … 20.7
# (gravel). Floors sit under the smoothest shipped materials with headroom;
# the mean band keeps room for the tint to move the hue in both directions.
MEAN_BAND = (40.0, 225.0)
MIN_STD = 4.0
MIN_LOCAL_DETAIL = 2.0


def _grey(name: str) -> np.ndarray:
    with Image.open(_TEXTURES / f"{name}.png") as im:
        return np.asarray(im.convert("L"), dtype=np.float64)


class TestRegistry:
    def test_registry_matches_loader_table(self) -> None:
        assert set(forge.TEXTURES) == set(_TEXTURE_FILES.values())

    def test_registry_matches_files_on_disk(self) -> None:
        on_disk = {p.stem for p in _TEXTURES.glob("*.png")}
        assert on_disk == set(forge.TEXTURES), (
            f"orphans: {on_disk - set(forge.TEXTURES)}, missing: {set(forge.TEXTURES) - on_disk}"
        )

    def test_every_non_solid_pattern_has_a_texture(self) -> None:
        for pattern in FillPattern:
            if pattern is FillPattern.SOLID:
                continue
            assert pattern in _TEXTURE_FILES, pattern.name

    def test_legacy_qt_generator_is_gone(self) -> None:
        """One generator, one contract (#309): the Qt-painted script must not
        come back as a second, ungated source of textures."""
        assert not (_ROOT / "scripts" / "generate_textures.py").exists()


class TestCommittedFiles:
    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_is_256_rgb(self, name: str) -> None:
        with Image.open(_TEXTURES / f"{name}.png") as im:
            assert im.size == (forge.SIZE, forge.SIZE), im.size
            assert im.mode == "RGB", im.mode

    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_pixels_match_generator(self, name: str) -> None:
        """Pixel-exact determinism: regenerate in-process, compare with the
        committed file's decoded pixels."""
        assert forge.is_current(name), (
            f"{name}.png differs from the generator — run "
            "scripts/generate_asset_forge_textures.py and commit"
        )

    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_visual_weight_band(self, name: str) -> None:
        g = _grey(name)
        mean = float(g.mean())
        std = float(g.std())
        detail = float(np.mean(np.abs(np.diff(g, axis=0))) + np.mean(np.abs(np.diff(g, axis=1))))
        assert MEAN_BAND[0] <= mean <= MEAN_BAND[1], f"{name}: mean {mean:.1f}"
        assert std >= MIN_STD, f"{name}: std {std:.2f} (flat — the tint would erase it)"
        assert detail >= MIN_LOCAL_DETAIL, f"{name}: local detail {detail:.2f}"


class TestGateMechanics:
    """The determinism gate must have teeth and must not churn files."""

    def test_check_flags_a_single_pixel_edit(self, tmp_path: Path) -> None:
        src = _TEXTURES / "sand.png"
        dst = tmp_path / "sand.png"
        with Image.open(src) as im:
            arr = np.array(im.convert("RGB"))
        arr[10, 10, 0] = (int(arr[10, 10, 0]) + 7) % 256
        Image.fromarray(arr, "RGB").save(dst)
        assert not forge.is_current("sand", dst)
        assert forge.is_current("sand", src)

    def test_regeneration_leaves_current_files_untouched(self, tmp_path: Path, monkeypatch) -> None:
        """Re-running the generator on an up-to-date file must not rewrite it —
        otherwise a Windows/Linux zlib difference would show up as a spurious
        diff on every regeneration."""
        dst = tmp_path / "sand.png"
        shutil.copy(_TEXTURES / "sand.png", dst)
        before = dst.read_bytes()
        monkeypatch.setattr(forge, "TEXTURES_DIR", tmp_path)
        assert forge.main(["--only", "sand"]) == 0
        assert dst.read_bytes() == before
        assert forge.main(["--check", "--only", "sand"]) == 0

    def test_check_reports_missing_file(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(forge, "TEXTURES_DIR", tmp_path)
        assert forge.main(["--check", "--only", "sand"]) == 1

    def test_unknown_name_is_rejected(self) -> None:
        assert forge.main(["--check", "--only", "no-such-texture"]) == 2
