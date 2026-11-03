"""Frames for an H.264 / MPEG-4 stream: BT.709, limited range, 4:2:0 (L6.2, #390). Qt-free.

Why this module exists (measured, ADR-071). Handed RGBA frames, Qt's FFmpeg recorder
converts them with swscale's default matrix, BT.601, and the MP4 it writes carries no
colour tag. Every player treats an untagged HD stream as BT.709, so the picture comes
back wrong: (200, 60, 30) read back as (212, 73, 27), and (30, 180, 90) as (19, 159, 91)
— the lawn duller, the roof redder, in every video. Handing the recorder YUV that was
already computed with the BT.709 matrix leaves it nothing to convert: the same colours
read back within 2 levels. Nothing here depends on a player's guess beyond that HD rule,
so a tour's sizes are all HD (``ui/view3d/tour_recorder.py``).

Inputs are display values (sRGB-encoded 8-bit): BT.709's matrix applies to gamma-encoded
components, and BT.709 and sRGB share their primaries.

Fixed point, not floats: about 4 ms a megapixel against 18, which is a 4K frame in 33 ms
instead of 150. It runs for every frame of a tour.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = ["rgb_to_yuv420", "yuv_to_rgb"]

_KR: Final = 0.2126
_KB: Final = 0.0722
_KG: Final = 1.0 - _KR - _KB
#: 16.16 fixed point of the limited-range matrix: Y spans 219 codes, Cb and Cr 224.
_SHIFT: Final = 16
_ONE: Final = 1 << _SHIFT
_Y_SCALE: Final = 219.0 / 255.0
_C_SCALE: Final = 224.0 / 255.0
_YR: Final = round(_KR * _Y_SCALE * _ONE)
_YG: Final = round(_KG * _Y_SCALE * _ONE)
_YB: Final = round(_KB * _Y_SCALE * _ONE)
_UR: Final = round(-_KR / (2.0 * (1.0 - _KB)) * _C_SCALE * _ONE)
_UG: Final = round(-_KG / (2.0 * (1.0 - _KB)) * _C_SCALE * _ONE)
_UB: Final = round(0.5 * _C_SCALE * _ONE)
_VR: Final = round(0.5 * _C_SCALE * _ONE)
_VG: Final = round(-_KG / (2.0 * (1.0 - _KR)) * _C_SCALE * _ONE)
_VB: Final = round(-_KB / (2.0 * (1.0 - _KR)) * _C_SCALE * _ONE)
_ROUND: Final = 1 << (_SHIFT - 1)


def rgb_to_yuv420(rgb: NDArray[np.uint8]) -> tuple[NDArray[np.uint8], NDArray[np.uint8],
                                                   NDArray[np.uint8]]:
    """An ``(h, w, 3 or 4)`` uint8 image as its Y, Cb and Cr planes, each uint8.

    Both sides must be even (4:2:0 has one chroma sample per 2 x 2 pixels); the chroma
    planes are half as wide and high, each sample the mean of its four pixels.
    Raises ``ValueError`` otherwise. Alpha, when there is a fourth channel, is ignored.
    """
    if rgb.ndim != 3 or rgb.shape[2] < 3 or rgb.dtype != np.uint8:
        raise ValueError(f"expected an (h, w, 3 or 4) uint8 image, got {rgb.shape} {rgb.dtype}")
    height, width = rgb.shape[:2]
    if height % 2 or width % 2 or not height or not width:
        raise ValueError(f"4:2:0 needs even sides, got {width} x {height}")
    red = rgb[..., 0].astype(np.int32)
    green = rgb[..., 1].astype(np.int32)
    blue = rgb[..., 2].astype(np.int32)
    luma = ((_YR * red + _YG * green + _YB * blue + _ROUND) >> _SHIFT) + 16

    def block_sums(channel: NDArray[np.int32]) -> NDArray[np.int32]:
        total: NDArray[np.int32] = (channel[0::2, 0::2] + channel[1::2, 0::2]
                                    + channel[0::2, 1::2] + channel[1::2, 1::2])
        return total

    red_sum, green_sum, blue_sum = block_sums(red), block_sums(green), block_sums(blue)
    # sums of four, not means: two more bits to shift away
    half = 1 << (_SHIFT + 1)
    chroma_b = ((_UR * red_sum + _UG * green_sum + _UB * blue_sum + half) >> (_SHIFT + 2)) + 128
    chroma_r = ((_VR * red_sum + _VG * green_sum + _VB * blue_sum + half) >> (_SHIFT + 2)) + 128
    return (np.clip(luma, 0, 255).astype(np.uint8),
            np.clip(chroma_b, 0, 255).astype(np.uint8),
            np.clip(chroma_r, 0, 255).astype(np.uint8))


def yuv_to_rgb(luma: float, chroma_b: float, chroma_r: float) -> tuple[float, float, float]:
    """The inverse for one sample — what a player does with an untagged HD stream. The
    tests' oracle, and the reason the numbers above can be checked without a player."""
    y = (luma - 16.0) / _Y_SCALE
    cb = (chroma_b - 128.0) / _C_SCALE
    cr = (chroma_r - 128.0) / _C_SCALE
    red = y + 2.0 * (1.0 - _KR) * cr
    blue = y + 2.0 * (1.0 - _KB) * cb
    green = (y - _KR * red - _KB * blue) / _KG
    return (red, green, blue)
