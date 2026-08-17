"""Integration gate (§8.10) for the generated object sprites (#308, Package 3a).

Every furniture/infrastructure sprite must render to visible pixels through
the app's real path — `core.furniture_renderer.render_furniture_pixmap` —
exactly as the canvas items use it, keep its visual weight inside the gated
band, stay legible at gallery-thumbnail size, letterbox correctly in the
gallery, and be placeable through the real canvas tools (new roster).
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap

from open_garden_planner.core.furniture_renderer import (
    _FURNITURE_DIR,
    _FURNITURE_FILES,
    _INFRASTRUCTURE_FILES,
    FURNITURE_DEFAULT_DIMENSIONS,
    clear_furniture_cache,
    render_furniture_pixmap,
)
from open_garden_planner.core.object_types import ObjectType, get_valid_types_for_shape
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.widgets.gallery_data import render_svg_thumbnail

ALL_TYPES = sorted({*_FURNITURE_FILES, *_INFRASTRUCTURE_FILES}, key=lambda t: t.name)

# Visual-weight band for man-made objects. Most FILL their footprint (unlike
# plants) — but open structures are legitimately airy: an A-frame swing seen
# from above is beam + legs + two seats. Shipped set measured 2026-08-17 at
# the default cm footprint (1 px/cm): swing 0.204, hammock 0.426, pergola
# 0.530, wheelbarrow 0.567 … sandbox 0.999; at 24 px: swing 0.407 … 1.000.
# Bounds sit below the measured minima with headroom; the ceiling is the
# physical maximum (a sprite may fill its whole footprint).
COVERAGE_BAND = (0.18, 1.00)
THUMB_MIN_COVERAGE = 0.35

# New Package-3a roster (#308) → the tool that draws each and the item class it produces
NEW_ROSTER: dict[ObjectType, tuple[ToolType, type]] = {
    ObjectType.SANDBOX: (ToolType.SANDBOX, RectangleItem),
    ObjectType.TRAMPOLINE: (ToolType.TRAMPOLINE, CircleItem),
    ObjectType.HOT_TUB: (ToolType.HOT_TUB, RectangleItem),
    ObjectType.SWING: (ToolType.SWING, RectangleItem),
    ObjectType.PICNIC_TABLE: (ToolType.PICNIC_TABLE, RectangleItem),
    ObjectType.HAMMOCK: (ToolType.HAMMOCK, RectangleItem),
    ObjectType.WHEELBARROW: (ToolType.WHEELBARROW, RectangleItem),
    ObjectType.PERGOLA: (ToolType.PERGOLA, RectangleItem),
    ObjectType.BIRD_BATH: (ToolType.BIRD_BATH, CircleItem),
}


def _coverage(pixmap: QPixmap) -> float:
    image = pixmap.toImage()
    total = opaque = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            total += 1
            if image.pixelColor(x, y).alpha() > 10:
                opaque += 1
    return opaque / max(total, 1)


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


@pytest.fixture(autouse=True)
def _fresh_cache(qtbot: object) -> None:
    clear_furniture_cache()


class TestRealRenderPath:
    @pytest.mark.parametrize("obj_type", ALL_TYPES, ids=lambda t: t.name)
    def test_coverage_within_band_at_default_footprint(self, obj_type: ObjectType) -> None:
        w, h = FURNITURE_DEFAULT_DIMENSIONS[obj_type]
        pixmap = render_furniture_pixmap(obj_type, width=w, height=h)
        assert pixmap is not None and not pixmap.isNull()
        cov = _coverage(pixmap)
        lo, hi = COVERAGE_BAND
        assert lo <= cov <= hi, f"{obj_type.name}: coverage {cov:.3f} outside {COVERAGE_BAND}"

    @pytest.mark.parametrize("obj_type", ALL_TYPES, ids=lambda t: t.name)
    def test_legible_at_thumbnail_size(self, obj_type: ObjectType) -> None:
        w, h = FURNITURE_DEFAULT_DIMENSIONS[obj_type]
        s = 24.0 / max(w, h)
        pixmap = render_furniture_pixmap(obj_type, width=w * s, height=h * s)
        assert pixmap is not None
        assert _coverage(pixmap) >= THUMB_MIN_COVERAGE, obj_type.name

    def test_non_uniform_stretch_still_renders(self) -> None:
        """The canvas stretches art to the user's rect — must not fail or vanish."""
        pixmap = render_furniture_pixmap(ObjectType.BENCH, width=90, height=90)  # 180x60 art → square
        assert pixmap is not None and _coverage(pixmap) > 0.5


class TestGalleryThumbnails:
    def test_non_square_art_is_letterboxed(self, qtbot: object) -> None:
        """bench (180x60) → 64 px thumb keeps its aspect: top/bottom rows transparent."""
        thumb = render_svg_thumbnail(_FURNITURE_DIR / "bench.svg", size=64)
        assert thumb is not None
        img = thumb.toImage()
        assert all(img.pixelColor(x, 0).alpha() == 0 for x in range(64)), "top row should be empty"
        assert all(img.pixelColor(x, 63).alpha() == 0 for x in range(64)), "bottom row should be empty"
        # and the middle band carries the art
        assert any(img.pixelColor(x, 32).alpha() > 10 for x in range(64))

    def test_square_art_fills_the_thumbnail(self, qtbot: object) -> None:
        thumb = render_svg_thumbnail(_FURNITURE_DIR / "table_round.svg", size=64)
        assert thumb is not None
        assert _coverage(thumb) > 0.6


class TestNewRosterWorkflow:
    """End-to-end: pick the tool, draw, get an SVG-rendered item of the right type."""

    @pytest.mark.parametrize("obj_type", sorted(NEW_ROSTER, key=lambda t: t.name), ids=lambda t: t.name)
    def test_tool_draws_item_that_paints(self, canvas: CanvasView, qtbot: object, obj_type: ObjectType) -> None:
        tool_type, item_cls = NEW_ROSTER[obj_type]
        event = _left_click_event()
        canvas.set_active_tool(tool_type)
        tool = canvas.tool_manager.active_tool
        assert tool is not None and tool._object_type == obj_type
        if item_cls is CircleItem:
            tool.mouse_press(event, QPointF(100, 100))
            tool.mouse_press(event, QPointF(160, 100))
        else:
            tool.mouse_press(event, QPointF(100, 100))
            tool.mouse_move(event, QPointF(260, 200))
            tool.mouse_release(event, QPointF(260, 200))
        item = next(i for i in reversed(canvas.scene().items()) if isinstance(i, item_cls))
        assert item.object_type == obj_type
        # the real paint path: furniture types hide pen/brush and blit the sprite
        rect = item.rect()
        pixmap = render_furniture_pixmap(obj_type, width=rect.width(), height=rect.height())
        assert pixmap is not None and _coverage(pixmap) > 0.15

    @pytest.mark.parametrize("obj_type", sorted(NEW_ROSTER, key=lambda t: t.name), ids=lambda t: t.name)
    def test_offered_in_change_type_menu_for_its_shape(self, obj_type: ObjectType) -> None:
        shape = "circle" if NEW_ROSTER[obj_type][1] is CircleItem else "rectangle"
        assert obj_type in get_valid_types_for_shape(shape)

    def test_bbq_grill_is_offered_for_circles(self) -> None:
        """BBQ is a circle-tool object; it must be reachable from the circle menu (#308)."""
        assert ObjectType.BBQ_GRILL in get_valid_types_for_shape("circle")
