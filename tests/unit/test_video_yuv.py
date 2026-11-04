"""BT.709 frames for a video (Phase 17 L6.2, #390): the matrix, by its round trip."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core import video_yuv
from open_garden_planner.core.video_yuv import rgb_to_yuv420, yuv_to_rgb

#: White, black and greys land exactly on the limits of limited range.
LIMITS = [((255, 255, 255), (235, 128, 128)), ((0, 0, 0), (16, 128, 128)),
          ((128, 128, 128), (126, 128, 128))]
#: The garden's colours the issue's measurement used, and the primaries.
COLOURS = [(200, 60, 30), (30, 180, 90), (255, 0, 0), (0, 255, 0), (0, 0, 255), (18, 40, 12),
           (240, 230, 200)]


def flat(colour: tuple[int, int, int], size: tuple[int, int] = (8, 8)) -> np.ndarray:
    image = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    image[...] = colour
    return image


def test_the_module_is_free_of_qt() -> None:
    tree = ast.parse(Path(video_yuv.__file__).read_text(encoding="utf-8"))
    names = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith("PyQt6") for name in names)


@pytest.mark.parametrize(("colour", "expected"), LIMITS)
def test_the_grey_axis_is_limited_range(colour: tuple[int, int, int], expected: tuple[int, int, int]) -> None:
    luma, chroma_b, chroma_r = rgb_to_yuv420(flat(colour))
    assert (int(luma[0, 0]), int(chroma_b[0, 0]), int(chroma_r[0, 0])) == expected


@pytest.mark.parametrize("colour", COLOURS)
def test_a_colour_survives_the_round_trip_within_two_levels(colour: tuple[int, int, int]) -> None:
    """The bug this module exists for read (200, 60, 30) back as (212, 73, 27): a matrix a
    player does not assume. Here the inverse is BT.709's, what a player does with HD."""
    luma, chroma_b, chroma_r = rgb_to_yuv420(flat(colour))
    back = yuv_to_rgb(float(luma[0, 0]), float(chroma_b[0, 0]), float(chroma_r[0, 0]))
    assert np.abs(np.array(back) - np.array(colour)).max() <= 2.0, back


def test_it_is_the_bt709_matrix_and_not_bt601() -> None:
    """The positive control: the same pixel through BT.601's luma is measurably elsewhere,
    so the round trip above could not pass with the wrong matrix."""
    red = rgb_to_yuv420(flat((255, 0, 0)))[0][0, 0]
    assert int(red) == 63                       # 16 + 219 x 0.2126 (BT.601: 16 + 219 x 0.299 = 81)


def test_the_planes_are_4_2_0_and_chroma_is_the_mean_of_its_four_pixels() -> None:
    image = np.zeros((4, 6, 4), dtype=np.uint8)   # RGBX: the fourth channel is ignored
    image[..., 3] = 255
    image[0:2, 0:2, 0] = (255, 0)                 # a red and a black pixel per row: half red
    luma, chroma_b, chroma_r = rgb_to_yuv420(image)
    assert luma.shape == (4, 6) and chroma_b.shape == chroma_r.shape == (2, 3)
    half = rgb_to_yuv420(flat((128, 0, 0)))
    assert abs(int(chroma_r[0, 0]) - int(half[2][0, 0])) <= 1
    assert abs(int(chroma_b[0, 0]) - int(half[1][0, 0])) <= 1
    assert luma.dtype == chroma_b.dtype == np.uint8


@pytest.mark.parametrize("shape", [(3, 4, 3), (4, 5, 3), (0, 0, 3), (4, 4), (4, 4, 2)])
def test_it_refuses_what_4_2_0_cannot_hold(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        rgb_to_yuv420(np.zeros(shape, dtype=np.uint8))


def test_it_refuses_anything_but_8_bits() -> None:
    with pytest.raises(ValueError):
        rgb_to_yuv420(np.zeros((4, 4, 3), dtype=np.float32))  # type: ignore[arg-type]
