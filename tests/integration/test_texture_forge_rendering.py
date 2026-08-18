"""Integration gate (§8.10) for the forge textures (#309, Package 3b).

Every fill-pattern texture must reach the user through the app's REAL path —
the Properties panel's apply slots (`_on_property_changed` / `_on_color_changed`,
the same code the Fill Pattern combo and the colour button drive) →
`create_pattern_brush` → item brush → `paint()` → the Y-flipped `scene.render`
the view/export use — with visible material detail; the user's fill colour
must recolour it (the 80/255 tint overlay) without flattening it; a textured
item must show no wrap seam on the canvas in EITHER axis (the legacy
glass/flagstone seams were on-canvas-by-default defects); the gallery
thumbnails render; and the greenhouse tool's default GLASS fill draws
through the real tool workflow.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QComboBox, QGraphicsScene

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.fill_patterns import (
    _TEXTURE_FILES,
    _TEXTURES_DIR,
    FillPattern,
    clear_texture_cache,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel
from open_garden_planner.ui.widgets.gallery_data import render_texture_thumbnail

TEXTURED = sorted((p for p in FillPattern if p is not FillPattern.SOLID), key=lambda p: p.name)
IDS = [p.name for p in TEXTURED]

# The seam metric of scripts/check_texture_tileability.py, applied to the
# item's REAL (tinted) brush painted two tiles wide: the step across the wrap
# boundary (texture column/row 255 → 0, i.e. image column/row 256) must sit
# inside the fill's own 98th-percentile edge family in BOTH axes (1.6).
SEAM_RATIO_THRESHOLD = 1.6
TILE = 256


def _luminance(image: QImage, margin: int = 4) -> np.ndarray:
    """Luminance array of an ARGB32 image, inner region only (the item's pen
    draws the outline on the outermost pixels)."""
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    arr = arr[:, : img.width(), :]
    b, g, r = arr[..., 0].astype(float), arr[..., 1].astype(float), arr[..., 2].astype(float)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum[margin : lum.shape[0] - margin, margin : lum.shape[1] - margin]


def _mean_rgb(image: QImage, margin: int = 4) -> tuple[float, float, float]:
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    arr = arr[margin : img.height() - margin, margin : img.width() - margin, :]
    return float(arr[..., 2].mean()), float(arr[..., 1].mean()), float(arr[..., 0].mean())


def _render_item_alone(item, flip: bool = True) -> QImage:
    """Render ONE item through its real paint() via a bare QGraphicsScene,
    with the view/export Y-flip (translate(0, H) then scale(1, -1))."""
    scene = QGraphicsScene()
    scene.addItem(item)
    source = item.sceneBoundingRect()
    image = QImage(int(source.width()), int(source.height()), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    if flip:
        painter.translate(0, image.height())
        painter.scale(1.0, -1.0)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()), source)
    painter.end()
    scene.removeItem(item)
    return image


def _paint_brush(brush: QBrush, size: int = 2 * TILE + 8) -> QImage:
    """Fill a plain image with the item's brush from origin (0, 0) — the same
    texture rasterisation the item's paint() performs, with a known tile
    phase (wrap boundaries at x = 256, 512)."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setBrushOrigin(0, 0)
    painter.fillRect(0, 0, size, size, brush)
    painter.end()
    return image


def _wrap_seam_ratio(brush: QBrush) -> float:
    """Worse of the two wrap boundaries (image column 255|256 and image row
    255|256), each divided by the 98th percentile of the fill's own
    column-/row-boundary steps."""
    lum = _luminance(_paint_brush(brush), margin=0)
    steps_x = np.mean(np.abs(np.diff(lum, axis=1)), axis=0)  # steps_x[i] = |col i+1 - col i|
    steps_y = np.mean(np.abs(np.diff(lum, axis=0)), axis=1)  # steps_y[i] = |row i+1 - row i|
    ratio_x = float(steps_x[TILE - 1]) / (float(np.percentile(steps_x, 98.0)) + 1e-9)
    ratio_y = float(steps_y[TILE - 1]) / (float(np.percentile(steps_y, 98.0)) + 1e-9)
    return max(ratio_x, ratio_y)


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


@pytest.fixture(autouse=True)
def _fresh_cache(qtbot: object) -> None:
    clear_texture_cache()


def _textured_item(pattern: FillPattern, size: int = 520) -> RectangleItem:
    """A GARDEN_BED-sized rectangle two texture tiles wide (the wrap boundary
    lands inside the fill), textured via the panel's real apply path."""
    item = RectangleItem(0, 0, size, size, object_type=ObjectType.GARDEN_BED)
    item.shadows_enabled = False
    panel = PropertiesPanel(command_manager=CommandManager())
    panel.set_selected_items([item])
    panel._on_property_changed(item, "fill_pattern", pattern)
    assert item.fill_pattern is pattern
    return item


class TestPaintsThroughRealPath:
    @pytest.mark.parametrize("pattern", TEXTURED, ids=IDS)
    def test_texture_paints_with_visible_detail(self, qtbot: object, pattern: FillPattern) -> None:
        item = _textured_item(pattern)
        lum = _luminance(_render_item_alone(item))
        # a real texture brush, not a solid fallback (texture missing → QBrush(color))
        assert not item.brush().texture().isNull(), f"{pattern.name}: solid fallback brush"
        assert lum.std() > 2.0, f"{pattern.name}: flat fill on canvas (std {lum.std():.2f})"

    @pytest.mark.parametrize("pattern", TEXTURED, ids=IDS)
    def test_no_wrap_seam_on_canvas(self, qtbot: object, pattern: FillPattern) -> None:
        """The item's real (tinted) brush painted two tiles wide: the wrap
        boundary must sit inside the fill's own edge family (legacy glass
        2.1×, flagstone 3.4× — the on-canvas seams #309 exists to remove)."""
        item = _textured_item(pattern)
        ratio = _wrap_seam_ratio(item.brush())
        assert ratio <= SEAM_RATIO_THRESHOLD, f"{pattern.name}: wrap seam ratio {ratio:.2f} on canvas"

    def test_seam_metric_has_teeth_on_canvas(self, qtbot: object) -> None:
        """Positive control: a texture under a luminance ramp (the classic
        non-tiling defect) painted through the same brush path MUST fail."""
        pixmap = QPixmap(str(_TEXTURES_DIR / f"{_TEXTURE_FILES[FillPattern.WOOD]}.png"))
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
        ramp = (0.55 + 0.45 * np.linspace(0.0, 1.0, img.width()))[None, :, None]
        arr[:, : img.width(), :3] = np.clip(arr[:, : img.width(), :3] * ramp, 0, 255).astype(np.uint8)
        assert _wrap_seam_ratio(QBrush(QPixmap.fromImage(img))) > SEAM_RATIO_THRESHOLD

    @pytest.mark.parametrize("pattern", TEXTURED, ids=IDS)
    def test_user_colour_recolours_without_flattening(self, qtbot: object, pattern: FillPattern) -> None:
        """The tint (user colour at 80/255 over the texture) must MOVE the hue
        (red vs blue fill colours give a clearly different render) while the
        material detail survives underneath (spread stays well above flat)."""
        item = _textured_item(pattern)
        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])
        renders = {}
        for name, color in (("red", QColor(220, 40, 40)), ("blue", QColor(40, 60, 220))):
            btn = MagicMock()
            btn.color = color
            panel._on_color_changed(item, "fill_color", btn)
            assert item.fill_color == color
            renders[name] = _render_item_alone(item)
        r_red, _g, b_red = _mean_rgb(renders["red"])
        r_blue, _g, b_blue = _mean_rgb(renders["blue"])
        assert r_red - r_blue > 25 and b_blue - b_red > 25, f"{pattern.name}: tint does not read"
        for name, image in renders.items():
            std = _luminance(image).std()
            assert std > 1.5, f"{pattern.name}/{name}: tint flattened the texture (std {std:.2f})"


class TestChrome:
    def test_properties_panel_offers_every_pattern_by_name(self, qtbot: object) -> None:
        item = RectangleItem(0, 0, 100, 100, object_type=ObjectType.GARDEN_BED)
        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])
        combos = [c for c in panel.findChildren(QComboBox) if isinstance(c.itemData(0), FillPattern)]
        assert combos, "fill-pattern combo not found"
        combo = combos[0]
        offered = {combo.itemData(i): combo.itemText(i) for i in range(combo.count())}
        assert set(offered) == set(FillPattern)
        for pattern, text in offered.items():
            assert text and text != pattern.name, f"{pattern.name}: raw enum name shown"

    @pytest.mark.parametrize("pattern", TEXTURED, ids=IDS)
    def test_gallery_thumbnail_renders(self, qtbot: object, pattern: FillPattern) -> None:
        thumb = render_texture_thumbnail(pattern, QColor(120, 140, 100))
        assert thumb is not None and not thumb.isNull()
        lum = _luminance(thumb.toImage(), margin=8)
        assert lum.std() > 1.0, f"{pattern.name}: flat thumbnail"


class TestGreenhouseDefault:
    def test_greenhouse_tool_draws_glass_that_paints_seamlessly(self, canvas: CanvasView, qtbot: object) -> None:
        """GLASS is the default greenhouse fill — the one legacy seam that was
        on canvas by default. Draw through the real tool and check the render."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.GREENHOUSE)
        tool = canvas.tool_manager.active_tool  # a PolygonTool: clicks + double-click to close
        for pt in (QPointF(100, 100), QPointF(620, 100), QPointF(620, 620), QPointF(100, 620)):
            tool.mouse_press(event, pt)
        tool.mouse_double_click(event, QPointF(100, 620))
        item = next(i for i in canvas.scene().items() if isinstance(i, PolygonItem))
        assert item.object_type == ObjectType.GREENHOUSE
        assert item.fill_pattern is FillPattern.GLASS
        assert not item.brush().texture().isNull()
        canvas.scene().removeItem(item)
        item.shadows_enabled = False
        lum = _luminance(_render_item_alone(item))
        assert lum.std() > 2.0
        assert _wrap_seam_ratio(item.brush()) <= SEAM_RATIO_THRESHOLD
