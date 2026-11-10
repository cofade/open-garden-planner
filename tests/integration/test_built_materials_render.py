"""The built world's materials on a real renderer (#801, #803) — render tier.

Opt-in (``OGP_RENDER3D=1``). The driver (``quick3d_render_driver.py``, scenario
``built_materials``, scenes in ``built_materials_scenes.py``) renders; these tests JUDGE.

#803, "a black trampoline mat turns tan facing a low sun": the class row faces the
family garden's golden-hour sun. A part's colour there is its albedo times the light, and
the light of a 15-degree sun is warm and the sky's blue - so the judge compares each part
with the SAME part in the same frame rendered with every specular off (``row_diffuse``):
the material may not repaint the part (hue within 10 degrees of its diffuse look, for a
part whose 2D colour has a hue) nor wash it out (a matte surface at most 1.5 times its
diffuse luma). Against the 2D colour itself the trampoline's pad is held to the issue's
10-degree line too; a near-neutral 2D colour (the mat's #303336: HSV saturation 0.11) has
no hue to hold, and the light alone moves a canvas, a plaster wall or a window more than
10 degrees (measured, see each bound).

#801: the roof's tiles read at noon and at the low sun, its mean colour at noon stays
what it was (against the same frame with the picture off), a wall shows its courses, and
the pond's morning glint no longer clips.
"""

from __future__ import annotations

import colorsys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.integration.built_materials_scenes import BITS, CLASS_IDS, ROW_CLASS_COLOURS, WALL_BOXES
from tests.integration.quick3d_render_support import (
    failure_report,
    load_rgb,
    luma,
    render_tier,
    run_driver,
)

pytestmark = render_tier

Run = tuple[dict[str, Any], Path]
#: A bit frame's luma above the black frame's by this much: the bit is set; below LOW:
#: clear; between: the pixel is undecided and belongs to no mask (edges, glow).
HIGH, LOW = 40.0, 12.0
#: Too few pixels to judge a class by.
MIN_PIXELS = 60


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    out = tmp_path_factory.mktemp("built_materials")
    proc, result = run_driver(out, "built_materials")
    assert proc.returncode == 0 and result.get("status") == "ok", failure_report(proc, out)
    return result["scenarios"]["built_materials"], out


def _image(run: Run, key: str) -> np.ndarray:
    return load_rgb(run[1] / run[0][key]["file"]).astype(np.float64)


def _erode(mask: np.ndarray) -> np.ndarray:
    kept = mask.copy()
    kept[1:] &= mask[:-1]
    kept[:-1] &= mask[1:]
    kept[:, 1:] &= mask[:, :-1]
    kept[:, :-1] &= mask[:, 1:]
    return kept


def _class_masks(run: Run) -> dict[str, np.ndarray]:
    assert run[0]["class_ids"] == dict(CLASS_IDS) and run[0]["bits"] == BITS
    black = luma(_image(run, "row_black"))
    ids = np.zeros(black.shape, dtype=np.int64)
    decided = np.ones(black.shape, dtype=bool)
    for bit in range(BITS):
        lift = luma(_image(run, f"row_bit{bit}")) - black
        ids |= (lift > HIGH).astype(np.int64) << bit
        decided &= (lift > HIGH) | (lift < LOW)
    return {name: _erode(decided & (ids == number)) for name, number in CLASS_IDS.items()}


def _hue_sat(rgb: np.ndarray) -> tuple[float, float]:
    h, s, _v = colorsys.rgb_to_hsv(*(np.asarray(rgb, dtype=np.float64) / 255.0))
    return h * 360.0, s


def _hue_error(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _mean(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    mean: np.ndarray = image[mask].mean(axis=0)
    return mean


def test_the_masks_find_every_class_of_the_row(run: Run) -> None:
    masks = _class_masks(run)
    seen = {name for name, mask in masks.items() if mask.sum() >= MIN_PIXELS}
    assert set(ROW_CLASS_COLOURS) <= seen, sorted(set(ROW_CLASS_COLOURS) - seen)


def test_no_material_repaints_or_washes_out_a_part_facing_a_low_sun(run: Run) -> None:
    """One part of each class (module docstring). Measured, RTX 4070: every chromatic
    class within 4.2 degrees of its diffuse look (the pad; every other within 2.8), every
    matte one at most 1.43x its diffuse luma (the enamel; the mat 1.00x, the pad 1.18x).
    With every surface at the old 0.78 / 0.35 the mat read 4.08x and 128 degrees off -
    the tan mat - and the pad 1.52x, 13.8 degrees off: this test fails."""
    masks = _class_masks(run)
    frame, diffuse = _image(run, "row"), _image(run, "row_diffuse")
    report = {}
    for name, colour in ROW_CLASS_COLOURS.items():
        mask = masks[name]
        if mask.sum() < MIN_PIXELS:
            continue
        seen, reference = _mean(frame, mask), _mean(diffuse, mask)
        lift = float(luma(seen[None])[0] / max(luma(reference[None])[0], 1.0))
        hue_error = _hue_error(_hue_sat(seen)[0], _hue_sat(reference)[0])
        report[name] = (round(hue_error, 1), round(lift, 2))
        if _hue_sat(colour)[1] >= 0.25:
            assert hue_error <= 10.0, (name, report[name])
        # glass panes and steel are meant to mirror the sky: no lift bound for them
        if name not in ("glass_pane", "steel"):
            assert lift <= 1.5, (name, report[name])
    assert {"rubber", "plastic"} <= set(report), report


def test_the_trampoline_s_mat_stays_dark_and_its_pad_blue(run: Run) -> None:
    """#803's own line. The pad against its 2D colour #427bc2 (hue 213.3): measured 8.0
    degrees, saturation 0.60 on the RTX 4070 and on WARP alike (the issue: 32 degrees,
    saturation 0.22; the old 0.78 / 0.35: 17.7 degrees, saturation 0.34).
    The mat (#303336) as dark as its diffuse self, not a tan sheen (the issue: luma 99)."""
    masks = _class_masks(run)
    frame, diffuse = _image(run, "row"), _image(run, "row_diffuse")
    pad, mat = _mean(frame, masks["plastic"]), _mean(frame, masks["rubber"])
    pad_hue, pad_sat = _hue_sat(pad)
    assert _hue_error(pad_hue, _hue_sat(ROW_CLASS_COLOURS["plastic"])[0]) <= 10.0, (pad, pad_hue)
    assert pad_sat >= 0.4, pad
    mat_diffuse = _mean(diffuse, masks["rubber"])
    assert float(luma(mat[None])[0]) <= 1.25 * float(luma(mat_diffuse[None])[0]) + 2.0, (mat, mat_diffuse)


def _roof_mask(run: Run) -> np.ndarray:
    lift = luma(_image(run, "roof_key_white")) - luma(_image(run, "roof_key_black"))
    return _erode(lift > HIGH)


@pytest.mark.parametrize("sun", ["noon", "low"])
def test_a_tiled_roof_reads_as_tiles(run: Run, sun: str) -> None:
    """#801: the 2D roof's tiles on the 3D roof. Luma spread over the tiles, the roof
    with its picture against the same frame without (the flat roof the survey measured
    at 0.57): measured noon 10.8 vs 2.2, low sun 6.8 vs 2.3 (RTX 4070, 640 x 360)."""
    mask = _roof_mask(run)
    assert mask.sum() > 5000
    tiled = luma(_image(run, f"roof_{sun}"))[mask]
    flat = luma(_image(run, f"roof_{sun}_flat"))[mask]
    assert float(tiled.std()) >= 2.0 * float(flat.std()) + 1.0, (float(tiled.std()), float(flat.std()))


def test_the_roof_keeps_its_noon_colour(run: Run) -> None:
    """The picture's albedo has a mean of 1: the noon roof's mean colour is the flat
    roof's within 4 % luma and 2 degrees of hue (measured: -0.6 %, 0.0 degrees)."""
    mask = _roof_mask(run)
    tiled, flat = _mean(_image(run, "roof_noon"), mask), _mean(_image(run, "roof_noon_flat"), mask)
    flat_luma = float(luma(flat[None])[0])
    assert abs(float(luma(tiled[None])[0]) - flat_luma) <= 0.04 * flat_luma, (tiled, flat)
    assert _hue_error(_hue_sat(tiled)[0], _hue_sat(flat)[0]) <= 2.0, (tiled, flat)


@pytest.mark.parametrize("surface", sorted(WALL_BOXES))
def test_a_wall_is_not_a_flat_slab(run: Run, surface: str) -> None:
    """#801: a garden wall's courses, a house's render, a shed's boards - each close, on
    its side in the shade of a golden-hour sun, where the survey's wall was one navy slab
    (std 1.7). The box is wall only and its light even, so its luma spread is the
    surface's own: with the picture against the same frame without. Measured (RTX 4070,
    640 x 360): masonry 7.0 vs 1.2, plaster 2.1 vs 0.8, cladding 7.3 vs 1.2."""
    shown_image = luma(_image(run, f"wall_{surface}"))
    height, width = shown_image.shape
    x0, y0, x1, y1 = WALL_BOXES[surface]
    mask = np.zeros(shown_image.shape, dtype=bool)
    mask[int(y0 * height):int(y1 * height), int(x0 * width):int(x1 * width)] = True
    shown = float(shown_image[mask].std())
    flat = float(luma(_image(run, f"wall_{surface}_flat"))[mask].std())
    assert shown >= 1.6 * flat + 0.3, (shown, flat)


def _kind_mask(run: Run, item_id: str) -> np.ndarray:
    lift = luma(_image(run, f"kinds_key_{item_id}_white")) - luma(_image(run, f"kinds_key_{item_id}_black"))
    return _erode(lift > HIGH)


def _box_sum(values: np.ndarray, radius: int) -> np.ndarray:
    side = 2 * radius + 1
    total = np.pad(values, radius + 1).cumsum(axis=0).cumsum(axis=1)
    window = total[side:, side:] - total[:-side, side:] - total[side:, :-side] + total[:-side, :-side]
    return window[: values.shape[0], : values.shape[1]]


def _fine_detail(image: np.ndarray, mask: np.ndarray, radius: int = 2) -> float:
    """The luma's spread about its local mean (a 5 x 5 window inside the mask): a tile's
    relief, not the step from one roof face to the next (a hip's faces shade apart)."""
    values, weight = luma(image), mask.astype(np.float64)
    local = _box_sum(values * weight, radius) / np.maximum(_box_sum(weight, radius), 1e-9)
    return float((values - local)[mask].std())


@pytest.mark.parametrize("item_id", ["hip", "shed_roof"])
def test_every_pitched_roof_kind_reads_as_tiles(run: Run, item_id: str) -> None:
    """#801's "each parametric roof kind": a hip roof's four faces and a shed (mono-pitch)
    roof's one plane carry the tiles too (each along its own eave), at noon - against the
    same frame without the picture. Fine detail measured (640 x 360), Direct3D 11 on the
    GPU / WARP / OpenGL: hip 4.1 / 4.9 / 4.1 against 1.5 / 1.5 / 1.4 without; shed 5.2 /
    5.5 / 5.2 against 0.9 / 0.9 / 0.7. (The plain spread does not tell: a hip's four faces
    shade apart, 12.0 without the picture.)"""
    mask = _kind_mask(run, item_id)
    assert mask.sum() > 1500, int(mask.sum())
    tiled = _fine_detail(_image(run, "kinds"), mask)
    flat = _fine_detail(_image(run, "kinds_flat"), mask)
    assert tiled >= 2.0 * flat + 0.5, (tiled, flat)


def test_the_glasshouse_stays_glass(run: Run) -> None:
    """#801: a glasshouse's glass roof and walls stay the glass material, and its frame
    shows no picture: around it the frame with every picture and the frame without are the
    same pixels (a picture laid on its roof would change them). Measured: the largest
    difference 0 on Direct3D 11 (GPU and WARP) and OpenGL; in the hip's and the shed
    roof's own boxes 22 and 25."""
    mask = _kind_mask(run, "glasshouse")
    assert mask.sum() > 200, int(mask.sum())
    rows, columns = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    box = (slice(rows[0], rows[-1] + 1), slice(columns[0], columns[-1] + 1))
    difference = np.abs(_image(run, "kinds")[box] - _image(run, "kinds_flat")[box])
    assert float(difference.max()) <= 3.0, float(difference.max())


def test_the_pond_s_morning_glint_does_not_clip(run: Run) -> None:
    """#803's P2: at the mirror angle of a 20-degree sun, Qt's own glint clipped 4.5 % of
    the water white (1280 x 720); now nothing clips, and the glint stands out of the
    water (measured, 640 x 360: peak luma 170, the water's median 77)."""
    lift = luma(_image(run, "pond_key_white")) - luma(_image(run, "pond_key_black"))
    # the glint is bright in BOTH key frames, so it is a hole in the keyed water: the pond
    # is convex, so each row is filled between its first and last water pixel
    keyed = _erode(lift > HIGH)
    water = np.zeros_like(keyed)
    for row in np.flatnonzero(keyed.any(axis=1)):
        columns = np.flatnonzero(keyed[row])
        water[row, columns[0]:columns[-1] + 1] = True
    assert water.sum() > 2000
    image = _image(run, "pond")
    clipped = (image[water] >= 254.0).any(axis=1)
    assert float(clipped.mean()) == 0.0
    water_luma = luma(image)[water]
    peak = float(water_luma.max())
    assert peak < 254.0 and peak >= 1.6 * float(np.median(water_luma)), (peak, float(np.median(water_luma)))
