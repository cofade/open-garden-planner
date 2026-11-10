"""A surface's detail picture as the engine samples it (#801): ``surface_detail``.

The roof's tiles and the walls' plaster, courses and boards are the canvas's own
pictures. The texel keeps a surface's MEAN colour its vertex colour (so a roof's noon
colour does not move and the mipmaps reach that flat mean far away) and turns the
picture's luminance into slopes the shader bends the normal by.
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.core.fill_patterns import FillPattern, pattern_rgb
from open_garden_planner.core.scene3d.materials import SURFACES
from open_garden_planner.core.scene3d.surface_detail import (
    ALBEDO_ENCODE,
    MAX_SLOPE,
    albedo_multiplier,
    detail_texels,
    height_slopes,
)

PICTURED = sorted({surface.detail.pattern for surface in SURFACES.values() if surface.detail is not None})


def _texels(rgb: np.ndarray) -> np.ndarray:
    return np.frombuffer(detail_texels(rgb), dtype=np.uint8).reshape(rgb.shape[0], rgb.shape[1], 4)


@pytest.mark.parametrize("pattern", PICTURED)
def test_every_detail_picture_keeps_the_surface_s_mean_colour(qtbot, pattern: str) -> None:
    rgb = pattern_rgb(FillPattern[pattern])
    assert rgb is not None and rgb.shape == (256, 256, 3), "the canvas's own 256-px picture"
    assert float(albedo_multiplier(rgb).mean()) == pytest.approx(1.0, abs=1e-9)
    texels = _texels(rgb)
    decoded = texels[..., 0].astype(np.float64) / 255.0 / ALBEDO_ENCODE
    assert float(decoded.mean()) == pytest.approx(1.0, abs=0.01)    # after the byte, within 1 %
    assert int(texels[..., 0].max()) < 255                          # the brightest texel is not clipped
    assert float(decoded.std()) > 0.05                              # and it shows the picture
    assert (texels[..., 3] == 255).all()


@pytest.mark.parametrize("pattern", PICTURED)
def test_the_slopes_of_a_tiling_picture_average_to_flat(qtbot, pattern: str) -> None:
    """The pictures tile, so the central differences wrap: the slopes sum to zero, and a
    far surface, whose mipmap averages them, shades as a plane."""
    rgb = pattern_rgb(FillPattern[pattern])
    assert rgb is not None
    along_u, along_v = height_slopes(rgb)
    assert float(along_u.mean()) == pytest.approx(0.0, abs=1e-12)
    assert float(along_v.mean()) == pytest.approx(0.0, abs=1e-12)
    texels = _texels(rgb)
    for channel in (1, 2):
        assert float(texels[..., channel].astype(np.float64).mean()) == pytest.approx(127.5, abs=1.5)


def test_a_flat_picture_is_the_flat_surface() -> None:
    texels = _texels(np.full((8, 8, 3), 120, dtype=np.uint8))
    assert (texels[..., 0] == round(ALBEDO_ENCODE * 255)).all()
    assert (np.abs(texels[..., 1:3].astype(int) - 128) <= 1).all()


def test_a_bright_stripe_raises_and_slopes_away_on_either_side() -> None:
    """Bright = raised (as the ground's detail normals): left of a bright column the
    height rises along u, right of it it falls - and v sees nothing."""
    rgb = np.full((8, 9, 3), 60, dtype=np.uint8)
    rgb[:, 4] = 220
    along_u, along_v = height_slopes(rgb)
    assert float(along_u[0, 3]) > 0.0 > float(along_u[0, 5])
    assert not along_v.any()
    assert float(np.abs(along_u).max()) <= 1.0
    texels = _texels(rgb)
    assert int(texels[0, 3, 1]) > 128 > int(texels[0, 5, 1])
    assert MAX_SLOPE == 0.5


def test_a_picture_too_small_or_flat_is_refused() -> None:
    with pytest.raises(ValueError):
        detail_texels(np.zeros((2, 8, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        detail_texels(np.zeros((8, 8), dtype=np.uint8))
