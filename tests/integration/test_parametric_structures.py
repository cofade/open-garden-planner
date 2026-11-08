"""#768 / #769: parametric glasshouse and pergola, in 2D and in 3D.

A GREENHOUSE is a first-class building now: its plan is the item's outline, it
owns a linked ``ROOF_RIDGE`` like a house, and its ridge is anodised aluminium.
A PERGOLA is drawn and built from one layout (``core.pergola``), so the canvas
picture and the 3D frame show the same posts, beams, rafters and purlins.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from open_garden_planner.core.furniture_renderer import (
    get_furniture_svg_path,
    is_furniture_type,
    paints_picture,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.pergola import layout as pergola_layout
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.roof_ridge_link import (
    GREENHOUSE_RIDGE_COLOUR,
    build_linked_ridge,
    linked_ridge,
)
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel
from open_garden_planner.ui.widgets.gallery_data import _structure_items
from tests.unit.scene3d_builder_cases import covers, polygon_record, rectangle


def _scene_view(qtbot) -> tuple[CanvasScene, CanvasView]:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return scene, view


def _paint_rect(item: RectangleItem) -> QImage:
    """Paint one rectangle item alone, through its real ``paint`` (no drop shadow:
    the opaque shadow rect would swamp every ink metric)."""
    item.shadows_enabled = False
    rect = item.rect()
    image = QImage(max(int(rect.width()), 1), max(int(rect.height()), 1),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image


def _coverage(image: QImage) -> float:
    total = opaque = 0
    for y in range(image.height()):
        for x in range(image.width()):
            total += 1
            if image.pixelColor(x, y).alpha() > 10:
                opaque += 1
    return opaque / max(total, 1)


def _count_colour(image: QImage, colour: QColor, tolerance: int = 12) -> int:
    found = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 10 and max(
                abs(pixel.red() - colour.red()),
                abs(pixel.green() - colour.green()),
                abs(pixel.blue() - colour.blue()),
            ) <= tolerance:
                found += 1
    return found


class TestGreenhouseRidge:
    def test_converting_a_rectangle_gets_an_aluminium_ridge(self, qtbot) -> None:
        scene, view = _scene_view(qtbot)
        rect = RectangleItem(100, 50, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE,
                             layer_id=scene.active_layer.id)
        scene.addItem(rect)
        panel = PropertiesPanel(command_manager=view.command_manager)

        panel._on_property_changed(rect, "object_type", ObjectType.GREENHOUSE)

        ridge = linked_ridge(rect)
        assert isinstance(ridge, PolylineItem)
        assert ridge.metadata.get("ridge_finish") == "aluminium"
        assert ridge.stroke_color == GREENHOUSE_RIDGE_COLOUR
        assert len(view.command_manager._undo_stack) == 1

        # Converting on to a HOUSE repaints it brown and drops the finish flag.
        panel._on_property_changed(rect, "object_type", ObjectType.HOUSE)
        ridge = linked_ridge(rect)
        assert isinstance(ridge, PolylineItem)
        assert "ridge_finish" not in ridge.metadata
        assert ridge.stroke_color != GREENHOUSE_RIDGE_COLOUR

        # ... and undo restores the greenhouse's aluminium ridge.
        view.command_manager.undo()
        ridge = linked_ridge(rect)
        assert isinstance(ridge, PolylineItem)
        assert ridge.metadata.get("ridge_finish") == "aluminium"
        assert ridge.stroke_color == GREENHOUSE_RIDGE_COLOUR

    def test_build_linked_ridge_marks_the_finish(self, qtbot) -> None:
        scene, _view = _scene_view(qtbot)
        greenhouse = RectangleItem(0, 0, 300, 200, object_type=ObjectType.GREENHOUSE,
                                   layer_id=scene.active_layer.id)
        scene.addItem(greenhouse)
        ridge = build_linked_ridge(greenhouse, scene.active_layer.id)
        assert ridge is not None
        assert ridge.get_metadata("ridge_finish") == "aluminium"
        assert ridge.pen().color() == GREENHOUSE_RIDGE_COLOUR

    def test_the_3d_builder_uses_the_live_ridge(self) -> None:
        registry = production_registry()
        natural = polygon_record(
            "GREENHOUSE", rectangle(300.0, 200.0), 220.0, shape="rectangle",
            params={"ridge": ((-150.0, 0.0), (150.0, 0.0))},
        )
        natural_parts = registry.build(natural)
        assert {part.name for part in natural_parts} == {"frame", "glass"}

        # A ridge dragged across the short axis is the roof's: the framed house
        # cannot show it, so the glass gable roof is built instead (#768).
        edited = polygon_record(
            "GREENHOUSE", rectangle(300.0, 200.0), 220.0, shape="rectangle",
            params={"ridge": ((0.0, -100.0), (0.0, 100.0))},
        )
        edited_parts = registry.build(edited)
        assert {part.name for part in edited_parts} == {"glass", "roof"}
        # the glass walls and the glass tiles take the item's tint; the
        # aluminium cap/fascia does not (#768)
        assert sum(part.tinted for part in edited_parts) == 2
        assert [part.name for part in edited_parts if not part.tinted] == ["roof"]
        # a tinted part must be neutral: the sink multiplies it by the item colour
        for part in edited_parts:
            if part.tinted:
                assert np.allclose(part.mesh.colors[:, :3], 1.0)
        top = max(float(part.mesh.positions[:, 2].max()) for part in edited_parts)
        assert top == pytest.approx(220.0, rel=1e-4)

    def test_the_canvas_paints_glass_and_aluminium_bars(self, qtbot) -> None:
        item = RectangleItem(0, 0, 300, 200, object_type=ObjectType.GREENHOUSE)
        image = _paint_rect(item)
        assert _coverage(image) > 0.5  # the glass fill
        # the glazing bars and ridge cap are #B0B5B9
        assert _count_colour(image, GREENHOUSE_RIDGE_COLOUR) > 50


class TestPergola:
    def test_the_layout_is_one_stack_of_members(self) -> None:
        plan = pergola_layout(400.0, 300.0, 250.0)
        assert plan is not None
        assert (len(plan.posts), len(plan.beams), len(plan.rafters), len(plan.purlins)) == (
            4, 4, 9, 5
        )
        assert plan.post <= 14.0
        assert plan.beam_depth <= 18.0
        assert plan.rafter_width <= 8.0
        assert plan.purlins[0].y0 > -150.0 and plan.purlins[-1].y1 < 150.0
        # the purlins' top IS the item's height, the rafters sit under them
        assert plan.rafter_top + plan.purlin_depth == pytest.approx(250.0)
        assert plan.beam_bottom > 0.0
        # the posts stand inside the footprint
        assert all(abs(post.x1) < 200.0 and abs(post.y1) < 150.0 for post in plan.posts)

    def test_the_canvas_paints_the_layout(self, qtbot) -> None:
        from open_garden_planner.core.scene3d.builders import palette

        item = RectangleItem(0, 0, 400, 300, object_type=ObjectType.PERGOLA)
        image = _paint_rect(item)
        coverage = _coverage(image)
        assert 0.10 < coverage < 0.95, f"an open frame, not a block: {coverage:.2f}"
        # the 3D colours: mid oak beams/rafters, light oak purlins
        assert _count_colour(image, QColor(*palette.PLANK.srgb)) > 50
        assert _count_colour(image, QColor(*palette.OAK_LIGHT.srgb)) > 10

    def test_the_3d_build_uses_the_same_layout(self) -> None:
        plan = pergola_layout(400.0, 300.0, 250.0)
        assert plan is not None
        record = polygon_record("PERGOLA", rectangle(400.0, 300.0), 250.0, shape="rectangle")
        parts = production_registry().build(record)
        assert parts
        meshes = [part.mesh for part in parts]
        for post in plan.posts:
            cx, cy = post.centre
            assert covers(meshes, cx, cy), "every post of the layout is built"
        top = max(float(part.mesh.positions[:, 2].max()) for part in parts)
        assert top == pytest.approx(250.0, rel=1e-4)

    def test_a_pergola_is_no_sprite_any_more(self) -> None:
        assert not is_furniture_type(ObjectType.PERGOLA)
        assert get_furniture_svg_path(ObjectType.PERGOLA) is None
        assert paints_picture(ObjectType.PERGOLA)
        pergolas = [item for item in _structure_items()
                    if item.object_type is ObjectType.PERGOLA]
        assert len(pergolas) == 1
        assert pergolas[0].thumbnail is not None and not pergolas[0].thumbnail.isNull()
