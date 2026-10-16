"""Integration tests: an item's stored appearance survives save/reload and copies.

Issues #438/#469/#470. The `.ogp` loader rebuilt each item's brush and pen from
the file but never wrote back the **stored attributes** those are derived from
(``fill_pattern``, ``fill_color``, ``stroke_color``, ``stroke_width``,
``stroke_style``). The item constructors pre-seed those attributes with the
object type's style, so after a reload the *Properties panel* â€” which reads the
attributes â€” showed the type defaults while the canvas painted the file's
colours, and the **next save wrote the defaults back over the user's colours**.

These tests pin three things, through the real save/load path:

* the stored attributes equal the file's values after a reload (panel);
* the reloaded pen/brush and the **rendered pixels** equal the pre-save item's
  (panel == canvas, and the look did not change);
* a Ctrl+D duplicate keeps them too (the copy paths share the same serializer).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, StrokeStyle
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

FILL = QColor("#ff90ee90")      # the owner's light green
STROKE = QColor("#ffff0000")    # red
PATTERN = FillPattern.ROOF_TILES


def _rectangle() -> RectangleItem:
    return RectangleItem(200, 200, 400, 300, object_type=ObjectType.GENERIC_RECTANGLE)


def _circle() -> CircleItem:
    return CircleItem(400, 400, 150, object_type=ObjectType.GENERIC_CIRCLE)


def _ellipse() -> EllipseItem:
    return EllipseItem(200, 200, 400, 300, object_type=ObjectType.GENERIC_ELLIPSE)


def _polygon() -> PolygonItem:
    return PolygonItem(
        vertices=[QPointF(100, 100), QPointF(500, 100), QPointF(500, 400), QPointF(100, 400)],
        object_type=ObjectType.GENERIC_POLYGON,
    )


def _polyline() -> PolylineItem:
    return PolylineItem(
        points=[QPointF(100, 100), QPointF(400, 250), QPointF(700, 100)],
        object_type=ObjectType.FENCE,
    )


BUILDERS = [_rectangle, _circle, _ellipse, _polygon, _polyline]
IDS = ["rectangle", "circle", "ellipse", "polygon", "polyline"]
# A polyline is a line: it has no fill, so its serializer stores no fill keys.
CASES = [(b, b is not _polyline) for b in BUILDERS]
CASE_IDS = [f"{name}-{'filled' if has_fill else 'line'}" for name, (_, has_fill) in zip(IDS, CASES, strict=True)]


def _style_like_the_owner(item: object, *, has_fill: bool = True) -> None:
    """Recolour an item the way the Properties panel does (texture + stroke).

    ``has_fill=False`` for a polyline: a line has no fill (and its serializer
    stores none), and Qt would otherwise *fill* the open path with the texture.
    The dash is left off there too â€” the line serializer writes no dash style
    (#467, owned by the L1 branch), so a dashed line would test that defect.
    """
    item.stroke_color = QColor(STROKE)
    item.stroke_width = 3.5
    if has_fill:
        item.stroke_style = StrokeStyle.DASHED
    if has_fill:
        item.fill_pattern = PATTERN
        item.fill_color = QColor(FILL)
        # The panel rebuilds the brush from the two attributes above; a test
        # that only sets the attributes would leave the item painting its
        # constructor's brush and compare two different things.
        item.setBrush(create_pattern_brush(PATTERN, QColor(FILL)))
    pen = item.pen()
    pen.setColor(QColor(STROKE))
    pen.setWidthF(3.5)
    if has_fill:
        pen.setStyle(StrokeStyle.DASHED.to_qt_pen_style())
    item.setPen(pen)


def _render(item: object) -> QImage:
    scene = QGraphicsScene()
    scene.addItem(item)
    source = item.sceneBoundingRect()
    image = QImage(
        max(1, int(source.width())), max(1, int(source.height())),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.translate(0, image.height())
    painter.scale(1.0, -1.0)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()), source)
    painter.end()
    scene.removeItem(item)
    return image


def _mean_rgb(image: QImage) -> tuple[float, float, float]:
    total = [0.0, 0.0, 0.0]
    count = 0
    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):
            colour = QColor(image.pixel(x, y))
            if colour.alpha() < 8:
                continue
            r, g, b, _ = colour.getRgb()
            total[0] += r
            total[1] += g
            total[2] += b
            count += 1
    assert count, "nothing painted"
    return total[0] / count, total[1] / count, total[2] / count


def _roundtrip(scene: CanvasScene) -> CanvasScene:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "look.ogp"
        ProjectManager().save(scene, path)
        reloaded = CanvasScene()
        ProjectManager().load(reloaded, path)
    return reloaded


class TestTheStoredAppearanceSurvivesAReload:
    @pytest.mark.parametrize("build,has_fill", CASES, ids=CASE_IDS)
    def test_attributes_and_look_match_after_save_and_reload(
        self, canvas: CanvasView, qtbot: object, build: object, has_fill: bool
    ) -> None:
        item = build()
        _style_like_the_owner(item, has_fill=has_fill)
        before = _render(item)
        before_mean = _mean_rgb(before)

        scene = canvas.scene()
        item.layer_id = scene.active_layer.id if scene.active_layer else None
        scene.addItem(item)

        reloaded_scene = _roundtrip(scene)
        found = [i for i in reloaded_scene.items() if type(i) is type(item)]
        assert len(found) == 1, "the item did not survive the round trip"
        after = found[0]
        reloaded_scene.removeItem(after)

        # Panel: the STORED attributes must be the file's values, not the type
        # defaults (#469). These are what the Properties panel reads.
        if has_fill:
            assert after.fill_pattern == item.fill_pattern
            assert after.fill_color == item.fill_color
        assert after.stroke_color == item.stroke_color
        assert after.stroke_width == pytest.approx(item.stroke_width)
        if has_fill:
            assert after.stroke_style == item.stroke_style

        # Canvas: what it paints must agree with those attributes and with the
        # pre-save render (#438 â€” no colour lost, no default written back).
        assert after.pen().color() == item.pen().color()
        assert after.pen().widthF() == pytest.approx(item.pen().widthF())
        assert after.pen().style() == item.pen().style()
        after_mean = _mean_rgb(_render(after))
        for channel, (x, y) in enumerate(zip(before_mean, after_mean, strict=True)):
            assert abs(x - y) < 12, (
                f"channel {channel} moved from {x:.1f} to {y:.1f} across save/reload"
            )

    def test_the_fill_colour_is_the_chosen_colour_not_the_texture_default(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The owner's exact case: a light-green fill over the roof-tile texture.

        Before #502 the texture's brown dominated, so this rendered as the
        standard roof-tile colour even though the file was correct.
        """
        item = _rectangle()
        _style_like_the_owner(item)
        scene = canvas.scene()
        item.layer_id = scene.active_layer.id if scene.active_layer else None
        scene.addItem(item)

        reloaded_scene = _roundtrip(scene)
        after = next(i for i in reloaded_scene.items() if isinstance(i, RectangleItem))
        reloaded_scene.removeItem(after)
        r, g, b = _mean_rgb(_render(after))
        assert g - r > 40, f"the light-green fill does not read (g - r {g - r:.1f})"


class TestCopiesKeepTheLook:
    def test_duplicate_keeps_the_stored_appearance(self, canvas: CanvasView, qtbot: object) -> None:
        source = RectangleItem(200, 200, 400, 300, object_type=ObjectType.GENERIC_RECTANGLE)
        canvas.scene().addItem(source)
        _style_like_the_owner(source)
        source.setSelected(True)

        canvas.duplicate_selected()

        copies = [i for i in canvas.scene().items() if isinstance(i, RectangleItem) and i is not source]
        assert len(copies) == 1, "duplicate did not create exactly one copy"
        copy = copies[0]
        assert copy.fill_pattern == source.fill_pattern
        assert copy.fill_color == source.fill_color
        assert copy.stroke_color == source.stroke_color
        assert copy.stroke_width == pytest.approx(source.stroke_width)
        assert copy.stroke_style == source.stroke_style
        assert copy.pen().color() == source.pen().color()

