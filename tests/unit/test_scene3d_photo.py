"""Photo mode's settings and colour grades (Phase 17 L6.1, #390). Qt-free decisions."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import photo
from open_garden_planner.core.scene3d.photo import (
    BLUR_MAX,
    GRADES,
    LUT_SIZE,
    NO_GRADE,
    NO_PHOTO,
    VIGNETTE_MAX,
    PhotoSettings,
    blur_amount,
    exposure_gain,
    focus_distance_cm,
    focus_range_cm,
    lut_strip,
)
from open_garden_planner.ui.view3d.quick3d.look import photo_properties


def table(grade: str, **adjust: float) -> np.ndarray:
    """The strip as (red index, green index, blue index) -> RGBA, in Qt's addressing:
    its shader reads column size x blue + red and, for texture data, row = green."""
    width, height, pixels = lut_strip(grade, **adjust)
    assert (width, height) == (LUT_SIZE * LUT_SIZE, LUT_SIZE)
    strip = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    cube = np.zeros((LUT_SIZE, LUT_SIZE, LUT_SIZE, 4), dtype=np.uint8)
    for blue in range(LUT_SIZE):
        for green in range(LUT_SIZE):
            for red in range(LUT_SIZE):
                # the shader un-flips rows for a loaded PNG: texelFetch y = size - 1 - green
                cube[red, green, blue] = strip[LUT_SIZE - 1 - green, LUT_SIZE * blue + red]
    return cube


def test_the_module_is_free_of_qt() -> None:
    tree = ast.parse(Path(photo.__file__).read_text(encoding="utf-8"))
    names = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not any(name.startswith("PyQt6") for name in names)


def test_no_photo_develops_nothing() -> None:
    """Every setting off IS the view: the scene's own defaults, through the mapping."""
    properties = photo_properties(NO_PHOTO, (0.0, 0.0, 100.0), (0.0, 100.0, 0.0), 720.0)
    assert properties["photoExposure"] == 1.0
    assert properties["photoVignette"] == 0.0
    assert properties["photoBlur"] == 0.0
    assert not NO_PHOTO.depth_of_field


def test_the_scene_declares_what_the_mapping_writes_and_starts_with_nothing_on() -> None:
    from tests.unit.test_quick3d_qml import strip_comments  # noqa: PLC0415 - the scan's helper

    scene = Path(photo.__file__).parents[2] / "ui/view3d/quick3d/qml/Garden.qml"
    text = strip_comments(scene.read_text(encoding="utf-8"))
    for name, default in (("photoExposure", "1.0"), ("photoVignette", "0.0"), ("photoBlur", "0.0")):
        assert f"property real {name}: {default}" in text, name
    assert "property bool photoGraded: false" in text
    for name in photo_properties(NO_PHOTO, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 720.0):
        assert f"property real {name}:" in text, name


@pytest.mark.parametrize(("stops", "gain"), [(0.0, 1.0), (1.0, 2.0), (-1.0, 0.5), (2.0, 4.0), (-2.0, 0.25)])
def test_exposure_is_in_photographers_stops(stops: float, gain: float) -> None:
    assert exposure_gain(stops) == pytest.approx(gain)


def test_the_vignette_reaches_only_into_the_corners() -> None:
    """Qt: colour x (u (1-u) v (1-v) x 15) ^ radius. Measured: a lower strength darkened the
    middle too. So the setting is the exponent, and the middle stays within 2 %."""
    strongest = photo_properties(PhotoSettings(vignette=1.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                                 720.0)["photoVignette"]
    assert strongest == pytest.approx(VIGNETTE_MAX)
    middle = (0.25 * 0.25 * 15.0) ** strongest
    corner = (0.05 * 0.95 * 0.05 * 0.95 * 15.0) ** strongest
    assert middle > 0.975
    assert corner < 0.55


def test_the_vignette_darkens_towards_black_and_never_brightens() -> None:
    """Qt's default colour is grey: a third of a night's pixels came out BRIGHTER (3D review)."""
    qml = (Path(photo.__file__).parents[2] / "ui" / "view3d" / "quick3d" / "qml"
           / "Garden.qml").read_text(encoding="utf-8")
    assert 'vignetteColor: "black"' in qml


def test_the_focus_is_a_point_so_a_moving_camera_keeps_it() -> None:
    settings = PhotoSettings(blur=0.5, focus_scene=(100.0, 0.0, 0.0))
    assert focus_distance_cm(settings, (0.0, 0.0, 0.0), (100.0, 0.0, 0.0)) == pytest.approx(100.0)
    assert focus_distance_cm(settings, (100.0, 300.0, 400.0), (100.0, 0.0, 0.0)) == pytest.approx(500.0)
    assert focus_distance_cm(NO_PHOTO, (5.0, 5.0, 5.0), (5.0, 6.0, 5.0)) == 0.0


def test_the_focus_is_a_depth_along_the_view_and_not_the_way_to_the_point() -> None:
    """Qt compares depths. A clicked point off the axis at the straight distance kept 0.37 of
    its sharpness near a corner (3D review); along the axis it keeps all of it."""
    settings = PhotoSettings(blur=0.5, focus_scene=(300.0, 400.0, 0.0))
    eye, target = (0.0, 0.0, 0.0), (0.0, 1000.0, 0.0)
    assert focus_distance_cm(settings, eye, target) == pytest.approx(400.0), "not 500, its distance"


def test_a_point_behind_the_camera_or_a_camera_without_a_direction_gives_a_usable_depth() -> None:
    settings = PhotoSettings(blur=0.5, focus_scene=(0.0, -100.0, 0.0))
    assert focus_distance_cm(settings, (0.0, 0.0, 0.0), (0.0, 50.0, 0.0)) == 0.0
    assert focus_distance_cm(settings, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) == pytest.approx(100.0)


def test_what_stays_sharp_grows_with_the_distance_and_never_vanishes() -> None:
    assert focus_range_cm(4000.0) == pytest.approx(1600.0)
    assert focus_range_cm(10.0) >= 30.0


def test_a_focus_without_blur_or_blur_without_a_focus_is_no_depth_of_field() -> None:
    assert not PhotoSettings(blur=0.5).depth_of_field
    assert not PhotoSettings(focus_scene=(1.0, 2.0, 3.0)).depth_of_field
    assert PhotoSettings(blur=0.5, focus_scene=(1.0, 2.0, 3.0)).depth_of_field
    properties = photo_properties(PhotoSettings(blur=1.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1080.0)
    assert properties["photoBlur"] == 0.0


def test_the_blur_is_scaled_to_the_picture_so_a_4k_photo_looks_like_its_preview() -> None:
    """Qt's blur is in pixels of the picture."""
    settings = PhotoSettings(blur=0.5, focus_scene=(1.0, 2.0, 3.0))
    assert blur_amount(settings, 1080.0) == pytest.approx(0.5 * BLUR_MAX)
    assert blur_amount(settings, 2160.0) == pytest.approx(2.0 * blur_amount(settings, 1080.0))


@pytest.mark.parametrize("bad", [
    {"exposure_ev": 2.5}, {"exposure_ev": float("nan")}, {"vignette": -0.1}, {"vignette": 1.5},
    {"blur": 2.0}, {"blur": math.inf}, {"grade": "sepia?"}, {"focus_scene": (1.0, 2.0)},
    {"focus_scene": (1.0, 2.0, float("inf"))},
])
def test_the_settings_refuse_what_they_cannot_mean(bad: dict) -> None:
    with pytest.raises(ValueError):
        PhotoSettings(**bad)


def test_the_identity_table_reads_as_identity_in_qts_own_addressing() -> None:
    cube = table(NO_GRADE).astype(np.int32)
    levels = np.round(np.linspace(0.0, 255.0, LUT_SIZE)).astype(np.int32)
    for red, green, blue in ((0, 0, 0), (15, 15, 15), (3, 7, 11), (15, 0, 0), (0, 15, 0), (0, 0, 15)):
        assert tuple(cube[red, green, blue][:3]) == (levels[red], levels[green], levels[blue])
    assert (cube[..., 3] == 255).all()


def test_as_texture_data_the_rows_run_opposite_to_qts_identity_png() -> None:
    """Measured against the resource itself: identical, upside down. Qt un-flips rows for an
    image it loaded (``LoadWithFlippedY``), and a data texture is not flipped on upload."""
    _, height, pixels = lut_strip(NO_GRADE)
    strip = np.frombuffer(pixels, np.uint8).reshape(height, -1, 4)
    assert (strip[0, :, 1] == 255).all(), "the first row is the brightest green"
    assert (strip[-1, :, 1] == 0).all()


def test_a_table_carries_the_looks_adjustments_exactly_as_qts_shader_does() -> None:
    """``apply_bcs``: contrast about 0.5, then saturation about the plain mean — and clamped,
    which Qt's is not: that clamp is the point (Garden.qml: a colour below 0 reads the
    neighbouring slice)."""
    saturation, contrast = 1.06, 1.04
    cube = table(NO_GRADE, saturation=saturation, contrast=contrast).astype(np.float64) / 255.0
    for red, green, blue in ((5, 9, 2), (0, 15, 0), (12, 12, 12), (15, 0, 15)):
        rgb = np.array((red, green, blue)) / 15.0
        adjusted = 0.5 + (rgb - 0.5) * contrast
        mean = adjusted.sum() * 0.33333
        expected = np.clip(mean + (adjusted - mean) * saturation, 0.0, 1.0)
        assert cube[red, green, blue][:3] == pytest.approx(expected, abs=1.0 / 255.0 + 1e-9)


@pytest.mark.parametrize("grade", sorted(GRADES))
def test_every_grade_is_a_valid_opaque_table(grade: str) -> None:
    width, height, pixels = lut_strip(grade)
    assert len(pixels) == width * height * 4
    assert (np.frombuffer(pixels, np.uint8).reshape(-1, 4)[:, 3] == 255).all()


def test_each_grade_does_what_its_name_says() -> None:
    mid = (8, 8, 8)
    grey = table(NO_GRADE)[mid][:3].astype(np.int32)
    golden = table("golden")[mid][:3].astype(np.int32)
    cool = table("cool")[mid][:3].astype(np.int32)
    assert golden[0] > grey[0] and golden[2] < grey[2], "warmer"
    assert cool[2] > grey[2] and cool[0] < grey[0], "cooler"
    film = table("film")
    assert film[0, 0, 0][0] > table(NO_GRADE)[0, 0, 0][0], "lifted blacks"
    mono = table("mono").reshape(-1, 4)[:, :3]
    assert (mono.max(axis=1) - mono.min(axis=1)).max() <= 1, "no colour left"
    crisp, plain = table("crisp"), table(NO_GRADE)
    assert crisp[15, 0, 0][0] >= plain[15, 0, 0][0]
    assert int(crisp[2, 2, 2][0]) < int(plain[2, 2, 2][0]), "more contrast: darker shadows"


def test_crisp_leaves_the_ends_of_the_range_where_they_are() -> None:
    """A straight gain took a third of a sunset's pixels to a channel at 0 (3D review)."""
    crisp, plain = table("crisp"), table(NO_GRADE)
    assert (crisp[0, 0, 0][:3] == plain[0, 0, 0][:3]).all()
    assert (crisp[15, 15, 15][:3] == plain[15, 15, 15][:3]).all()
    channels = crisp.reshape(-1, 4)[:, :3]
    assert (channels == 0).mean() < (plain.reshape(-1, 4)[:, :3] == 0).mean() + 0.04


def test_golden_keeps_a_blue_sky_blue() -> None:
    """Blue x 0.88 took 46 % of the sky's colour, a muddy olive (3D review)."""
    sky = (9, 11, 14)   # red, green, blue levels of a table
    graded, plain = table("golden")[sky][:3].astype(np.int32), table(NO_GRADE)[sky][:3].astype(np.int32)
    assert graded[2] > graded[1] > graded[0], "still blue"
    assert plain[2] - graded[2] < 0.08 * plain[2]


def test_an_unknown_grade_is_refused() -> None:
    with pytest.raises(ValueError):
        lut_strip("sepia?")
