"""A string of lights is a LINE (Phase 17 L5.4, #389; ADR-070 addendum).

The owner's manual test of L5: "A Lichterkette needs to be a 1D object like a fence or
wall, while it is a 2D rectangle, which doesn't really make sense — it doesn't have an
actual width. By giving it a width, this also leads to distorted 2D representations …
Their shadow is not required in 2D sunlight studies." So:

- the String Lights tool draws a LINE — a post at every click — offered with the other
  lines in Change Type, never on a rectangle;
- its 2D picture is drawn ALONG the line (wire, bulbs, posts) from the same layout the
  3D builder builds — nothing is stretched across a box;
- the 2D sun study casts no shadow for it (``object_height.casts_2d_shadow``); its 3D
  model keeps its own thin shadow;
- it has no path or fence style, and it survives save and load as a line.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PyQt6.QtWidgets import QComboBox, QGraphicsScene

from open_garden_planner.core.object_height import (
    NO_2D_SHADOW_TYPE_NAMES,
    casts_2d_shadow,
    effective_height_cm,
)
from open_garden_planner.core.object_types import ObjectType, get_valid_types_for_shape
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.string_lights import BULB_SPACING_CM, layout
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_identified_casters
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel
from open_garden_planner.ui.view3d.snapshot import snapshot_records

#: Three posts in a shallow V, 1.6 m and 1.3 m apart (item-local cm).
LINE: tuple[tuple[float, float], ...] = ((0.0, 0.0), (160.0, 40.0), (300.0, 0.0))


def _event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _string(points=LINE) -> PolylineItem:
    return PolylineItem([QPointF(x, y) for x, y in points], object_type=ObjectType.STRING_LIGHTS)


def test_the_tool_draws_a_line_with_a_post_at_every_click(canvas: CanvasView) -> None:
    """Pick String Lights, click three times, double-click: one line item of the type,
    with the three points clicked, the type's 12 cm wire width and its 2.5 m height."""
    canvas.set_active_tool(ToolType.STRING_LIGHTS)
    tool = canvas.tool_manager.active_tool
    assert tool is not None and tool._object_type is ObjectType.STRING_LIGHTS
    event = _event()
    for x, y in ((100.0, 100.0), (300.0, 160.0), (500.0, 100.0)):
        tool.mouse_press(event, QPointF(x, y))
    tool.mouse_double_click(event, QPointF(500.0, 100.0))
    (item,) = [i for i in canvas.scene().items()
               if getattr(i, "object_type", None) is ObjectType.STRING_LIGHTS]
    assert isinstance(item, PolylineItem) and item.point_count == 3
    assert item.pen().widthF() == pytest.approx(12.0)
    assert effective_height_cm(item.object_type, item.metadata) == pytest.approx(250.0)


def test_change_type_offers_it_with_the_lines_only() -> None:
    assert ObjectType.STRING_LIGHTS in get_valid_types_for_shape("polyline")
    for shape in ("rectangle", "circle", "polygon", "ellipse"):
        assert ObjectType.STRING_LIGHTS not in get_valid_types_for_shape(shape), shape


# ── the 2D picture ───────────────────────────────────────────────────────────


def _render(item: PolylineItem) -> tuple[QImage, QRectF]:
    """The item alone through its real ``paint`` at 1 px per cm, item-local = scene."""
    scene = QGraphicsScene()
    scene.addItem(item)
    source = item.sceneBoundingRect()
    image = QImage(math.ceil(source.width()), math.ceil(source.height()),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()),
                 QRectF(source.left(), source.top(), image.width(), image.height()))
    painter.end()
    scene.removeItem(item)
    return image, source


def _pixel(image: QImage, source: QRectF, x: float, y: float) -> QColor:
    return image.pixelColor(int(round(x - source.left())), int(round(y - source.top())))


def test_the_2d_picture_is_drawn_along_the_line_not_across_a_box(qtbot) -> None:
    """The owner's screenshot: a string drawn as a 3 m deep rectangle showed its bulbs as
    stretched ellipses across the whole box. Now a cream bulb sits on every point the
    layout hangs one, a grey post on every point of the line, and 20 cm off the line —
    beyond the glow — nothing is painted at all."""
    item = _string()
    image, source = _render(item)
    lay = layout(LINE)
    assert len(lay.bulbs) == round(lay.length_cm / BULB_SPACING_CM)
    for x, y in lay.bulbs_xy():
        bulb = _pixel(image, source, x, y)
        assert bulb.alpha() == 255 and bulb.red() > 200 and bulb.green() > 190, (x, y, bulb.name())
    for x, y in LINE:
        post = _pixel(image, source, x, y)
        assert post.alpha() == 255 and abs(post.red() - 0x91) < 25 and post.blue() < 0x91, post.name()
    # beside the middle of each span, 20 cm out along its normal: empty
    for (ax, ay), (bx, by) in zip(LINE, LINE[1:], strict=False):
        length = math.hypot(bx - ax, by - ay)
        nx, ny = -(by - ay) / length, (bx - ax) / length
        for side in (1.0, -1.0):
            mx, my = (ax + bx) / 2.0 + side * 20.0 * nx, (ay + by) / 2.0 + side * 20.0 * ny
            assert _pixel(image, source, mx, my).alpha() == 0, (mx, my)


def test_the_picture_follows_the_line_s_width(qtbot) -> None:
    """The width is the line's stroke width (the Properties panel's): a wider stroke,
    a bigger post and bulb — the item's bounds grow with it, so nothing is clipped."""
    narrow, wide = _string(), _string()
    pen = wide.pen()
    pen.setWidthF(24.0)
    wide.setPen(pen)
    assert wide.boundingRect().height() > narrow.boundingRect().height() + 20.0
    image, source = _render(wide)
    assert _pixel(image, source, 0.0 + 10.0, 0.0).alpha() == 255, "a 24 cm post reaches 10 cm out"


def test_a_string_of_lights_casts_no_2d_shadow(qtbot) -> None:
    """The owner: "Their shadow is not required in 2D sunlight studies, because the
    shadowed area is basically irrelevant." The one caster walk leaves it out (a fence of
    the same line and height casts); the 3D record says so too, and its 3D model still
    casts its own thin shadow."""
    assert frozenset({"STRING_LIGHTS"}) == NO_2D_SHADOW_TYPE_NAMES
    assert not casts_2d_shadow(ObjectType.STRING_LIGHTS) and casts_2d_shadow(ObjectType.FENCE)
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    string = _string()
    fence = PolylineItem([QPointF(x, y + 500.0) for x, y in LINE], object_type=ObjectType.FENCE)
    fence.metadata["object_height_cm"] = 250.0
    scene.addItem(string)
    scene.addItem(fence)
    casters = {caster.item_id for caster in collect_identified_casters(scene)}
    assert str(fence.item_id) in casters and str(string.item_id) not in casters
    records = snapshot_records(scene)
    record = records[str(string.item_id)]
    assert record.height_cm == pytest.approx(250.0), "it keeps its height: the posts' tops"
    assert not record.has_2d_caster and records[str(fence.item_id)].has_2d_caster
    from open_garden_planner.core.scene3d.builders import production_registry

    parts = production_registry().build(record)
    assert any(part.casts_shadow and part.name == "string lights" for part in parts)


def test_it_has_no_path_or_fence_style(canvas: CanvasView, qtbot) -> None:
    """A path or fence style has no meaning for a string: the Properties panel offers
    none (a fence still gets its style menu)."""
    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)

    def style_menus(item: Any) -> list[QComboBox]:
        canvas.scene().addItem(item)
        panel.set_selected_items([item])
        return [combo for combo in panel.findChildren(QComboBox)
                if any("──" in combo.itemText(i) for i in range(combo.count()))]

    assert style_menus(PolylineItem([QPointF(0, 0), QPointF(200, 0)], object_type=ObjectType.FENCE))
    assert not style_menus(_string())


def test_it_survives_save_and_load_as_a_line(qtbot) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(_string())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "string.ogp"
        ProjectManager().save(scene, path)
        loaded = CanvasScene(width_cm=2000, height_cm=2000)
        ProjectManager().load(loaded, path)
    (item,) = [i for i in loaded.items() if getattr(i, "object_type", None) is ObjectType.STRING_LIGHTS]
    assert isinstance(item, PolylineItem)
    assert [(round(p.x(), 3), round(p.y(), 3)) for p in item.points] == list(LINE)
    assert item.pen().widthF() == pytest.approx(12.0)


def test_the_gallery_shows_a_painted_string(qtbot) -> None:
    """A string has no sprite: the gallery's picture is painted by the canvas's painter."""
    from open_garden_planner.ui.widgets.gallery_data import _furniture_items

    (entry,) = [item for item in _furniture_items() if item.object_type is ObjectType.STRING_LIGHTS]
    assert entry.tool_type is ToolType.STRING_LIGHTS
    image = entry.thumbnail.toImage()
    cream = sum(1 for y in range(image.height()) for x in range(image.width())
                if (c := image.pixelColor(x, y)).alpha() > 200 and c.red() > 220 and c.green() > 200)
    assert cream >= 4, "its bulbs show"
