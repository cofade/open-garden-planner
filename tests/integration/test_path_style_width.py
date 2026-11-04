"""Tests for path style default widths and width-preserving style switches (issue #727)."""

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.item_look import line_look_for_preset
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    get_path_fence_style_info,
)
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem


@pytest.fixture
def points() -> list[QPointF]:
    return [QPointF(0.0, 0.0), QPointF(100.0, 0.0), QPointF(100.0, 100.0)]


def test_all_path_styles_default_to_80_cm() -> None:
    """All path styles default to 80 cm; fence styles keep their widths."""
    path_styles = [
        PathFenceStyle.GRAVEL_PATH,
        PathFenceStyle.STEPPING_STONES,
        PathFenceStyle.PAVED_PATH,
        PathFenceStyle.WOODEN_BOARDWALK,
        PathFenceStyle.DIRT_PATH,
    ]
    for style in path_styles:
        info = get_path_fence_style_info(style)
        assert info.category == "path"
        assert info.stroke_width == 80.0, f"{style.name} width is {info.stroke_width}, expected 80.0"

    # Fences unchanged
    assert get_path_fence_style_info(PathFenceStyle.WOODEN_FENCE).stroke_width == 3.0
    assert get_path_fence_style_info(PathFenceStyle.METAL_FENCE).stroke_width == 2.5
    assert get_path_fence_style_info(PathFenceStyle.CHAIN_LINK).stroke_width == 2.0
    assert get_path_fence_style_info(PathFenceStyle.HEDGE_FENCE).stroke_width == 8.0
    assert get_path_fence_style_info(PathFenceStyle.STONE_WALL).stroke_width == 5.0


def test_new_path_item_starts_at_80_cm(qtbot: object, points: list[QPointF]) -> None:
    """A newly constructed PolylineItem for any path style starts at 80 cm."""
    path_styles = [
        PathFenceStyle.GRAVEL_PATH,
        PathFenceStyle.STEPPING_STONES,
        PathFenceStyle.PAVED_PATH,
        PathFenceStyle.WOODEN_BOARDWALK,
        PathFenceStyle.DIRT_PATH,
    ]
    for style in path_styles:
        item = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=style)
        assert item.pen().widthF() == 80.0, f"{style.name} initialized with {item.pen().widthF()} != 80.0"


def test_switching_path_style_preserves_user_set_width(qtbot: object, points: list[QPointF]) -> None:
    """Switching a path's style preserves the manually set stroke width."""
    item = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.GRAVEL_PATH)
    assert item.pen().widthF() == 80.0

    # User customises width to 100 cm
    pen = item.pen()
    pen.setWidthF(100.0)
    item.setPen(pen)
    assert item.pen().widthF() == 100.0

    # Switch Style -> Dirt via line_look_for_preset
    dirt_look = line_look_for_preset(item, PathFenceStyle.DIRT_PATH)
    assert dirt_look.pen.widthF() == 100.0
    from open_garden_planner.core.item_look import apply_line_look
    apply_line_look(item, dirt_look)
    assert item.path_fence_style == PathFenceStyle.DIRT_PATH
    assert item.pen().widthF() == 100.0

    # Switch back Style -> Gravel
    gravel_look = line_look_for_preset(item, PathFenceStyle.GRAVEL_PATH)
    assert gravel_look.pen.widthF() == 100.0
    apply_line_look(item, gravel_look)
    assert item.path_fence_style == PathFenceStyle.GRAVEL_PATH
    assert item.pen().widthF() == 100.0


def test_switching_from_plain_line_to_path_seeds_with_preset_width(qtbot: object, points: list[QPointF]) -> None:
    """Switching a plain polyline (width 3.0) to a path seeds with 80 cm."""
    plain = PolylineItem(points, object_type=ObjectType.FENCE, path_fence_style=PathFenceStyle.NONE)
    assert plain.pen().widthF() == 3.0

    path_look = line_look_for_preset(plain, PathFenceStyle.GRAVEL_PATH)
    assert path_look.pen.widthF() == 80.0


def test_switching_from_path_to_fence_seeds_with_fence_width(qtbot: object, points: list[QPointF]) -> None:
    """Switching an 80 cm path to a wooden fence sets width to 3.0 cm."""
    path = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.GRAVEL_PATH)
    assert path.pen().widthF() == 80.0

    fence_look = line_look_for_preset(path, PathFenceStyle.WOODEN_FENCE)
    assert fence_look.pen.widthF() == 3.0
