"""Photo mode's settings and colour grades (Phase 17 L6.1, #390, ADR-071). Qt-free.

Photo mode is the only place a view of the garden may leave the look the plan's sun
and weather decide (``ogp-lush-cinematic`` §2: "DOF/vignette only in photo mode"). It
changes how a picture is DEVELOPED — exposure, depth of field, vignette, a colour grade
— and never what stands in the garden: no height, no shadow, no sun, no date. Every
setting off is the view itself, pixel for pixel (the render tier pins it).

A grade is a 3D lookup table computed here, 100 % procedural like everything else in
the 3D view: Qt Quick 3D's table is a strip of ``LUT_SIZE`` slices of ``LUT_SIZE`` x
``LUT_SIZE`` texels, one slice per blue level, applied to the tone-mapped picture.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = ["BLUR_MAX", "DEFAULT_BLUR", "EXPOSURE_EV_RANGE", "GRADES", "LUT_SIZE", "NO_GRADE",
           "NO_PHOTO", "VIGNETTE_MAX", "PhotoSettings", "blur_amount", "exposure_gain",
           "focus_distance_cm", "focus_range_cm", "lut_strip"]

#: The table's edge: Qt's default, and all a smooth grade needs.
LUT_SIZE: Final = 16
#: Two stops up clipped two thirds of a noon picture (3D review): the top stops short of that.
EXPOSURE_EV_RANGE: Final = (-2.0, 1.5)
#: Qt's ``depthOfFieldBlurAmount`` at a setting of 1, at a picture 1080 pixels high. Its blur
#: has three taps: at 8 they read as ghosts of a trellis and of leaves.
BLUR_MAX: Final = 5.0
#: What "focus here" switches on when no blur was asked for yet.
DEFAULT_BLUR: Final = 0.8
#: Qt's ``vignetteRadius`` at a setting of 1: an exponent, and the control that reaches only
#: into the corners. Its ``vignetteStrength`` stays at Qt's 15: a lower one darkens the middle
#: of the picture too (2.4 took the mean luma from 99 to 47). The colour is black in
#: ``Garden.qml``: Qt's default grey BRIGHTENS a picture darker than it (a third of a night).
VIGNETTE_MAX: Final = 0.20
#: How deep the band that stays sharp is, as a share of the focused point's depth: half of it
#: in front of the point, half behind (Qt's ``depthOfFieldFocusRange``).
FOCUS_RANGE_SHARE: Final = 0.40
_FOCUS_RANGE_MIN_CM: Final = 30.0
NO_GRADE: Final = "none"
#: The picture height the blur amount is defined at. Qt's blur is measured in pixels of the
#: picture, so a 4K photo needs twice the amount of a 1080p one to look the same.
_BLUR_REFERENCE_PX: Final = 1080.0


@dataclass(frozen=True, slots=True)
class PhotoSettings:
    """How a picture is developed. ``focus_scene``: the point in focus (E, N, up, cm)."""

    exposure_ev: float = 0.0
    vignette: float = 0.0            # 0..1
    grade: str = NO_GRADE
    blur: float = 0.0                # 0..1: 0 is everything sharp
    focus_scene: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.exposure_ev) or not (
                EXPOSURE_EV_RANGE[0] <= self.exposure_ev <= EXPOSURE_EV_RANGE[1]):
            raise ValueError(f"exposure_ev must lie in {EXPOSURE_EV_RANGE}, got {self.exposure_ev!r}")
        for name, value in (("vignette", self.vignette), ("blur", self.blur)):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in 0..1, got {value!r}")
        if self.grade not in GRADES:
            raise ValueError(f"unknown grade {self.grade!r}; choose from {sorted(GRADES)}")
        if self.focus_scene is not None and (
                len(self.focus_scene) != 3 or not all(math.isfinite(v) for v in self.focus_scene)):
            raise ValueError(f"focus_scene must be a finite (E, N, up) point, got {self.focus_scene!r}")

    @property
    def depth_of_field(self) -> bool:
        """Something is out of focus: a point was picked and there is blur to apply."""
        return self.focus_scene is not None and self.blur > 0.0


def exposure_gain(exposure_ev: float) -> float:
    """Photographers' stops as a factor on the look's own exposure."""
    return float(2.0 ** exposure_ev)


def focus_distance_cm(settings: PhotoSettings, eye: tuple[float, float, float],
                      target: tuple[float, float, float]) -> float:
    """How deep the focused point lies in front of a camera at ``eye`` looking at ``target``;
    0 without one, or behind the camera. A depth is what Qt takes, but a POINT is what the user
    picked: on a tour the focus stays on the plant. Along the view's axis, not the way to the
    point: Qt compares depths, and off-axis the straight distance is sharp somewhere else
    (a clicked point near a corner kept 0.37 of its sharpness)."""
    if settings.focus_scene is None:
        return 0.0
    length = math.dist(target, eye)
    if length <= 0.0:   # no axis to measure along
        return math.dist(settings.focus_scene, eye)
    depth = sum((point - start) * (end - start) for point, end, start
                in zip(settings.focus_scene, target, eye, strict=True)) / length
    return max(depth, 0.0)


def focus_range_cm(distance_cm: float) -> float:
    return max(distance_cm * FOCUS_RANGE_SHARE, _FOCUS_RANGE_MIN_CM)


def blur_amount(settings: PhotoSettings, picture_height_px: float) -> float:
    """Qt's blur amount for ``settings.blur`` in a picture of this height (module constant)."""
    return settings.blur * BLUR_MAX * max(picture_height_px, 1.0) / _BLUR_REFERENCE_PX


Rgb = NDArray[np.float64]


def _luma(rgb: Rgb) -> Rgb:
    result: Rgb = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    return result


def _golden(rgb: Rgb) -> Rgb:
    """Warm highlights, a little warmth in the shadows too: late afternoon."""
    luma = _luma(rgb)[..., None]
    warm = rgb * np.array((1.05, 1.0, 0.95))   # 0.88 took 46 % of a blue sky's colour: olive
    return np.asarray(warm + (0.02 * (1.0 - luma)) * np.array((1.0, 0.45, 0.0)))


def _crisp(rgb: Rgb) -> Rgb:
    """More contrast and saturation around the mid-tones: a bright, clear day. A curve that
    leaves 0 and 1 where they are: a straight gain took a third of a sunset to a channel at 0."""
    contrast = rgb + 0.48 * (rgb - 0.5) * rgb * (1.0 - rgb)
    luma = _luma(contrast)[..., None]
    return np.asarray(luma + (contrast - luma) * 1.08)


def _cool(rgb: Rgb) -> Rgb:
    """A blue morning: cooler everywhere, the greens barely touched."""
    return np.asarray(rgb * np.array((0.93, 1.0, 1.09)))


def _film(rgb: Rgb) -> Rgb:
    """Lifted blacks, softened highlights, slightly fewer colours: printed film."""
    luma = _luma(rgb)[..., None]
    muted = luma + (rgb - luma) * 0.88
    return np.asarray(0.045 + muted * 0.91)


def _mono(rgb: Rgb) -> Rgb:
    """Black and white, with the filmic curve the view already has."""
    return np.repeat(_luma(rgb)[..., None], 3, axis=-1)


#: Grade key -> the colour transform (display values 0..1 in, not necessarily clamped out).
GRADES: Final[dict[str, Callable[[Rgb], Rgb] | None]] = {
    NO_GRADE: None, "golden": _golden, "crisp": _crisp, "cool": _cool, "film": _film,
    "mono": _mono,
}

NO_PHOTO: Final = PhotoSettings()


def lut_strip(grade: str, *, saturation: float = 1.0, contrast: float = 1.0,
              size: int = LUT_SIZE) -> tuple[int, int, bytes]:
    """The grade as ``(width, height, RGBA bytes)`` for a ``QQuick3DTextureData``: ``size``
    slices of ``size`` x ``size`` side by side, red along a slice, green from the LAST row
    to the first, blue from slice to slice. ``NO_GRADE`` is the identity, which is Qt's own
    ``identity.png`` upside down; ``ValueError`` when ``grade`` is not a key of ``GRADES``.

    ``saturation``, ``contrast``: the look's own, in the same formula and order as Qt's
    ``apply_bcs`` (a grade replaces that step: ``Garden.qml`` says why). So a table's input
    is 0..1 by construction, and ``NO_GRADE`` with the look's values IS the graded-off view."""
    if grade not in GRADES:
        raise ValueError(f"unknown grade {grade!r}; choose from {sorted(GRADES)}")
    levels = np.linspace(0.0, 1.0, size, dtype=np.float64)
    green, slices, red = np.meshgrid(levels, levels, levels, indexing="ij")
    # (rows = green, slices = blue, columns = red) -> (rows, slices x columns)
    identity = np.stack((red, green, slices), axis=-1)
    adjusted = 0.5 + (identity - 0.5) * contrast
    mean = adjusted.sum(axis=-1, keepdims=True) * 0.33333
    adjusted = np.clip(mean + (adjusted - mean) * saturation, 0.0, 1.0)
    transform = GRADES[grade]
    graded = adjusted if transform is None else transform(adjusted)
    # Qt's effect samples the table raw (a Texture's flipV does not reach it), and a loaded
    # identity.png has its top row at v = 1: as texture DATA the rows go the other way
    laid_out = graded.reshape(size, size * size, 3)[::-1]
    alpha = np.ones((*laid_out.shape[:2], 1), dtype=np.float64)
    rgba = np.concatenate((np.clip(laid_out, 0.0, 1.0), alpha), axis=-1)
    pixels: NDArray[np.uint8] = np.round(rgba * 255.0).astype(np.uint8)
    return size * size, size, pixels.tobytes()
