"""Integration tests for OffsetTool (US-11.15).

Tests exercise the full select → hover → click workflow.
Distance is now determined by cursor position, not a dialog.
All coordinates are scene-space (Y-down, (0,0) = top-left).
"""

# ruff: noqa: ARG002

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click(
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = modifiers
    return event


def _items_of(view: CanvasView, cls: type) -> list:
    return [i for i in view.scene().items() if isinstance(i, cls)]


def _add_rect(view: CanvasView, x: float, y: float, w: float, h: float) -> RectangleItem:
    item = RectangleItem(x=x, y=y, width=w, height=h)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_circle(view: CanvasView, cx: float, cy: float, r: float) -> CircleItem:
    item = CircleItem(cx, cy, r, object_type=ObjectType.LAWN)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_ellipse(view: CanvasView, x: float, y: float, w: float, h: float) -> EllipseItem:
    item = EllipseItem(x=x, y=y, width=w, height=h)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_polygon(view: CanvasView, vertices: list[QPointF]) -> PolygonItem:
    item = PolygonItem(vertices=vertices, object_type=ObjectType.LAWN)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _offset_click(view: CanvasView, click_pos: QPointF) -> None:
    """Activate offset tool, hover then click at pos — distance from cursor."""
    tool = view.tool_manager.active_tool
    event = _left_click()
    tool.mouse_move(event, click_pos)
    tool.mouse_press(event, click_pos)


# ---------------------------------------------------------------------------
# Rectangle offset
# ---------------------------------------------------------------------------


class TestOffsetRectangle:
    def test_outward_offset_creates_larger_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking outside a rectangle creates a larger RectangleItem."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, RectangleItem))
        # Click ~20 units outside the right edge (boundary at x=800)
        _offset_click(canvas, QPointF(820, 400))

        rects = _items_of(canvas, RectangleItem)
        assert len(rects) == before + 1

    def test_outward_offset_size(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset by ~20 adds ~40 to each dimension."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click 20 units outside the right edge; boundary sampling tolerance ±3
        _offset_click(canvas, QPointF(820, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        nr = new_rects[0]
        assert abs(nr.rect().width() - 640) < 3.0
        assert abs(nr.rect().height() - 440) < 3.0

    def test_outward_offset_larger_than_original(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset always creates a shape wider and taller than original."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(830, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        assert new_rects[0].rect().width() > original.rect().width()
        assert new_rects[0].rect().height() > original.rect().height()

    def test_inward_offset_creates_smaller_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a rectangle creates a smaller RectangleItem."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click well inside the rect, far from boundary → inward offset
        _offset_click(canvas, QPointF(500, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        assert new_rects[0].rect().width() < original.rect().width()
        assert new_rects[0].rect().height() < original.rect().height()

    def test_undo_removes_offset_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after offset removes the created item."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))
        assert len(_items_of(canvas, RectangleItem)) == 2

        canvas.command_manager.undo()
        assert len(_items_of(canvas, RectangleItem)) == 1

    def test_tool_switches_to_select_after_offset(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """After creating an offset, the active tool switches back to SELECT."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))

        assert canvas.tool_manager.active_tool.tool_type == ToolType.SELECT


# ---------------------------------------------------------------------------
# Circle offset
# ---------------------------------------------------------------------------


class TestOffsetCircle:
    def test_outward_offset_creates_larger_circle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking outside a circle creates a larger CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        before_count = len(_items_of(canvas, CircleItem))
        # Click 30 units outside the right boundary (boundary at x=600)
        _offset_click(canvas, QPointF(630, 500))

        circles = _items_of(canvas, CircleItem)
        assert len(circles) == before_count + 1

        new_circles = [c for c in circles if c is not original]
        assert len(new_circles) == 1
        assert new_circles[0].radius > original.radius

    def test_inward_offset_creates_smaller_circle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a circle creates a smaller CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click well inside (30 units from right boundary)
        _offset_click(canvas, QPointF(570, 500))

        new_circles = [c for c in _items_of(canvas, CircleItem) if c is not original]
        assert len(new_circles) == 1
        assert new_circles[0].radius < original.radius

    def test_outward_offset_approximate_radius(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset by ~30 units increases radius by ~30."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        # 30 units outside right boundary
        _offset_click(canvas, QPointF(630, 500))

        new_circles = [c for c in _items_of(canvas, CircleItem) if c is not original]
        assert len(new_circles) == 1
        assert abs(new_circles[0].radius - 130) < 3.0


# ---------------------------------------------------------------------------
# Ellipse offset
# ---------------------------------------------------------------------------


class TestOffsetEllipse:
    def test_outward_offset_creates_larger_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset of an ellipse creates a larger EllipseItem."""
        original = _add_ellipse(canvas, 300, 300, 400, 200)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click outside the right boundary (boundary at x=700)
        _offset_click(canvas, QPointF(725, 400))

        new_items = [e for e in _items_of(canvas, EllipseItem) if e is not original]
        assert len(new_items) == 1
        assert new_items[0].rect().width() > original.rect().width()

    def test_inward_offset_creates_smaller_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Inward offset of an ellipse creates a smaller EllipseItem."""
        original = _add_ellipse(canvas, 300, 300, 400, 200)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click inside near the right boundary
        _offset_click(canvas, QPointF(675, 400))

        new_items = [e for e in _items_of(canvas, EllipseItem) if e is not original]
        assert len(new_items) == 1
        assert new_items[0].rect().width() < original.rect().width()


# ---------------------------------------------------------------------------
# Polygon offset
# ---------------------------------------------------------------------------


class TestOffsetPolygon:
    def test_outward_polygon_offset_creates_polygon(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset of a polygon creates a new PolygonItem."""
        _add_polygon(
            canvas,
            [
                QPointF(200, 200),
                QPointF(800, 200),
                QPointF(800, 600),
                QPointF(200, 600),
            ],
        )
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, PolygonItem))
        _offset_click(canvas, QPointF(820, 400))
        assert len(_items_of(canvas, PolygonItem)) == before + 1

    def test_polygon_offset_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo removes the polygon offset result."""
        _add_polygon(
            canvas,
            [
                QPointF(200, 200),
                QPointF(800, 200),
                QPointF(800, 600),
                QPointF(200, 600),
            ],
        )
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, PolygonItem))
        _offset_click(canvas, QPointF(820, 400))
        assert len(_items_of(canvas, PolygonItem)) == before + 1

        canvas.command_manager.undo()
        assert len(_items_of(canvas, PolygonItem)) == before


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_no_selection_does_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking with no selection is a no-op."""
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()

        result = tool.mouse_press(event, QPointF(500, 500))
        assert result is False

    def test_hover_empty_scene_no_crash(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()
        tool.mouse_move(event, QPointF(500, 500))


# ---------------------------------------------------------------------------
# Look fidelity (issue #470)
#
# An offset copy must look like its source — a rectangle, circle and ellipse
# used to come back in their object type's default fill, pattern and stroke —
# and must *stay* that way across a save -> reload.
# ---------------------------------------------------------------------------

_CUSTOM_FILL = "#3366cc"
_CUSTOM_STROKE = "#cc2222"


def _apply_custom_look(item: object) -> None:
    """Give ``item`` a distinct, non-default look and rebuild its pen/brush.

    ``_setup_styling`` is the same rebuild the style dialogs trigger after
    setting these attributes.
    """
    item.fill_pattern = FillPattern.SOIL
    item.fill_color = QColor(_CUSTOM_FILL)
    item.stroke_color = QColor(_CUSTOM_STROKE)
    item.stroke_width = 3.5
    item.stroke_style = StrokeStyle.DASHED
    item._setup_styling()


def _assert_live_look(source: object, copy: object) -> None:
    """Assert the in-session appearance of ``copy`` matches ``source``."""
    assert copy.fill_color == source.fill_color
    assert copy.fill_pattern == source.fill_pattern
    assert copy.stroke_color == source.stroke_color
    assert copy.stroke_width == pytest.approx(source.stroke_width)
    assert copy.stroke_style == source.stroke_style
    assert copy.pen().color() == source.pen().color()
    assert copy.pen().widthF() == pytest.approx(source.pen().widthF())
    assert copy.pen().style() == source.pen().style()


def _assert_reloaded_look(source: object, reloaded: object) -> None:
    """Assert the persisted *appearance* survives a save -> reload.

    Compared through the pen (what is painted), the fill pattern and the tint
    rather than the ``fill_color``/``stroke_color``/``stroke_width`` mixin
    attributes: those are restored too (see
    ``tests/integration/test_item_appearance_roundtrip.py``), but the brush
    colour is not asserted here because for a patterned fill
    ``create_pattern_brush`` returns a texture brush whose ``color()`` is
    ``#000000`` for both source and copy, so it would pin nothing.
    """
    assert reloaded.fill_pattern == source.fill_pattern
    assert reloaded.pen().color() == source.pen().color()
    assert reloaded.pen().widthF() == pytest.approx(source.pen().widthF())
    assert reloaded.pen().style() == source.pen().style()


class TestOffsetCopyLooksLikeItsSource:
    def test_offset_rectangle_keeps_fill_and_stroke(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        source = _add_rect(canvas, 200, 200, 600, 400)
        _apply_custom_look(source)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))

        copies = [r for r in _items_of(canvas, RectangleItem) if r is not source]
        assert len(copies) == 1
        _assert_live_look(source, copies[0])

    def test_offset_circle_keeps_fill_and_stroke(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        source = _add_circle(canvas, 500, 500, 100)
        _apply_custom_look(source)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(630, 500))

        copies = [c for c in _items_of(canvas, CircleItem) if c is not source]
        assert len(copies) == 1
        _assert_live_look(source, copies[0])

    def test_offset_ellipse_keeps_fill_and_stroke(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        source = _add_ellipse(canvas, 300, 300, 400, 200)
        _apply_custom_look(source)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(725, 400))

        copies = [e for e in _items_of(canvas, EllipseItem) if e is not source]
        assert len(copies) == 1
        _assert_live_look(source, copies[0])

    def test_offset_polygon_keeps_fill_and_stroke(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        source = _add_polygon(
            canvas,
            [
                QPointF(200, 200),
                QPointF(800, 200),
                QPointF(800, 600),
                QPointF(200, 600),
            ],
        )
        _apply_custom_look(source)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))

        copies = [p for p in _items_of(canvas, PolygonItem) if p is not source]
        assert len(copies) == 1
        _assert_live_look(source, copies[0])

    @pytest.mark.parametrize(
        "build, click",
        [
            (lambda v: _add_rect(v, 200, 200, 600, 400), QPointF(820, 400)),
            (lambda v: _add_circle(v, 500, 500, 100), QPointF(630, 500)),
            (lambda v: _add_ellipse(v, 300, 300, 400, 200), QPointF(725, 400)),
        ],
    )
    def test_offset_copy_look_survives_save_and_reload(
        self,
        canvas: CanvasView,
        qtbot: object,
        build: object,
        click: QPointF,
    ) -> None:
        source = build(canvas)
        _apply_custom_look(source)
        canvas.set_active_tool(ToolType.OFFSET)
        _offset_click(canvas, click)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "offset_look.ogp"
            pm = ProjectManager()
            pm.save(canvas.scene(), path)

            reloaded_scene = CanvasScene()
            pm.load(reloaded_scene, path)

        reloaded = [
            i for i in reloaded_scene.items() if isinstance(i, type(source))
        ]
        assert len(reloaded) == 2, "source and its offset copy must both persist"
        for item in reloaded:
            _assert_reloaded_look(source, item)
