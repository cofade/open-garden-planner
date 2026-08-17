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
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QMouseEvent, QPainter, QPixmap

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
# the default cm footprint (1 px/cm, 2-px grid): swing 0.205, hammock 0.426,
# pergola 0.530, wheelbarrow 0.567 … sandbox 0.999; at 24 px (1-px grid):
# swing 0.319 … 1.000.
# The floor sits below the measured minimum with headroom; the ceiling is the
# physical maximum because framed objects legitimately fill their footprint
# (sandbox 0.999) — the anti-"solid block" guard is the separate flatness test.
COVERAGE_BAND = (0.18, 1.00)
THUMB_MIN_COVERAGE = 0.25
# Flatness guard: a sprite that degrades to one flat fill (fallback rect, lost
# gradients) has ~zero luminance spread; shipped minimum is rain_barrel 0.106
# (2026-08-17), most sit at 0.17-0.26.
MIN_LUMINANCE_STD = 0.05

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


def _coverage(pixmap: QPixmap, step: int = 2) -> float:
    """Opaque fraction on a `step`-px sampling grid (step=1 for tiny images —
    a 24x18 thumbnail has only 108 samples at step 2, too coarse to gate)."""
    image = pixmap.toImage()
    total = opaque = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            total += 1
            if image.pixelColor(x, y).alpha() > 10:
                opaque += 1
    return opaque / max(total, 1)


def _luminance_std(pixmap: QPixmap) -> float:
    image = pixmap.toImage()
    vals = []
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if c.alpha() > 10:
                vals.append(0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5


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
        assert _coverage(pixmap, step=1) >= THUMB_MIN_COVERAGE, obj_type.name

    @pytest.mark.parametrize("obj_type", ALL_TYPES, ids=lambda t: t.name)
    def test_not_a_flat_block(self, obj_type: ObjectType) -> None:
        """Shading/material detail survived: the render is not one flat fill."""
        w, h = FURNITURE_DEFAULT_DIMENSIONS[obj_type]
        pixmap = render_furniture_pixmap(obj_type, width=w, height=h)
        assert pixmap is not None
        assert _luminance_std(pixmap) >= MIN_LUMINANCE_STD, obj_type.name

    def test_non_uniform_stretch_still_renders(self) -> None:
        """The canvas stretches art to the user's rect — must not fail or vanish."""
        pixmap = render_furniture_pixmap(ObjectType.BENCH, width=90, height=90)  # 180x60 art → square
        assert pixmap is not None and _coverage(pixmap) > 0.5


class TestGalleryThumbnails:
    def test_non_square_art_is_letterboxed(self, qtbot: object) -> None:
        """lounger (70x190) → 64 px thumb keeps its aspect: the art occupies a
        centred ~24-px-wide band, so 20 columns on each side stay transparent.
        (bench would be a vacuous choice — its art already clears the top/bottom
        rows under the old stretch-to-square; senior review 2026-08-17.)"""
        thumb = render_svg_thumbnail(_FURNITURE_DIR / "lounger.svg", size=64)
        assert thumb is not None
        img = thumb.toImage()
        band = 64 * 70 / 190          # 23.6 px wide art band
        margin = int((64 - band) / 2)  # 20 empty columns each side
        for x in list(range(0, margin)) + list(range(64 - margin, 64)):
            assert all(img.pixelColor(x, y).alpha() == 0 for y in range(64)), f"column {x} should be empty"
        assert any(img.pixelColor(32, y).alpha() > 10 for y in range(64)), "centre column carries the art"

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
        item = next(i for i in canvas.scene().items() if isinstance(i, item_cls))  # topmost = newest
        assert item.object_type == obj_type
        # the REAL paint path: render the scene (→ item.paint → furniture branch)
        # into an image and require ink inside the item's footprint
        source = item.sceneBoundingRect()
        image = QImage(int(source.width()), int(source.height()), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        canvas.scene().render(painter, QRectF(0, 0, image.width(), image.height()), source)
        painter.end()
        assert _coverage(QPixmap.fromImage(image)) > 0.15, obj_type.name

    @pytest.mark.parametrize("obj_type", sorted(NEW_ROSTER, key=lambda t: t.name), ids=lambda t: t.name)
    def test_offered_in_change_type_menu_for_its_shape(self, obj_type: ObjectType) -> None:
        shape = "circle" if NEW_ROSTER[obj_type][1] is CircleItem else "rectangle"
        assert obj_type in get_valid_types_for_shape(shape)

    def test_bbq_grill_is_offered_for_circles(self) -> None:
        """BBQ is a circle-tool object; it must be reachable from the circle menu (#308)."""
        assert ObjectType.BBQ_GRILL in get_valid_types_for_shape("circle")
