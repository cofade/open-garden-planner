"""An item's style ATTRIBUTES describe what its brush and pen paint — for every
operation that makes an item out of an item (review of Phase 17 L1.5, P1-1).

An item states its look twice: in ``fill_color`` / ``fill_pattern`` /
``stroke_color`` / ``stroke_width`` / ``stroke_style`` (what the project file,
the clipboard, the properties panel and the 3D ground bake read) and in its live
``brush()`` and ``pen()`` (what the canvas paints). The offset tool and the
corner tools copied the second and not the first: an offset copy of a blue
brick terrace was saved, and baked, as default wood. Nothing asserted the class.

THE GUARD of the class is not in this file: it is the teardown fixture in
``conftest.py``, which holds every item of every scene an integration test
builds to ``style_gaps(item) == []`` — whatever wrote the item. This file is
the part that knows the operations by name:

1. every operation that makes an item out of an item, on a recoloured,
   patterned, dash-stroked source of every shape it accepts: the derived item's
   attributes describe its brush and pen (``core.item_look.style_gaps``), and
   where the operation is a copy, the copy looks like its source;
2. the look survives the project file: derived → saved → loaded;
3. the writers that restyle an item in place — a freshly drawn line, the
   properties panel's edits and their undo, a type change — leave it in step,
   and undo what they did;
4. a MAP, read off the source, of the places that build an item from an item.
   It is documentation with a tripwire, not the guard: it knows four spellings
   in two folders, and a review that planted six forgetful operations saw it
   catch one.

Operations that CANNOT derive an item, and are therefore not here: undo / redo
of a delete, group / ungroup, move / rotate / resize / vertex edits (the same
item object), changing an item's type (it re-styles the item from the type:
``GardenItemMixin``'s type change sets the attributes and calls
``_setup_styling``), the Agent API (it creates items from a spec without style
keys and has no copy, mirror, array or offset tool), plant lists and smart
symbols (they build items from data, not from items).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.item_look import (
    MIN_STROKE_WIDTH,
    _same_brush,
    adopt_pen,
    paints_sprite,
    saved_stroke_colour,
    saved_stroke_width,
    style_gaps,
)
from open_garden_planner.core.mirror_geometry import build_mirrored_item
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    StrokeStyle,
    get_path_fence_style_info,
    get_style,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.core.tools.corner_edit_base import (
    CornerTarget,
    rebuild_with_corner_replaced,
    rectangle_corners_local,
)
from open_garden_planner.core.tools.offset_tool import _compute_offset_item
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.panels import PropertiesPanel
from tests.integration.conftest import fail_on_style_gaps, guarded, style_gaps_in, watched_scenes

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "open_garden_planner"

FILL = QColor(30, 60, 200)        # blue …
PATTERN = FillPattern.BRICK       # … brick: neither is any type's default
STROKE = QColor(200, 30, 30, 220)
WIDTH = 6.5
STYLE = StrokeStyle.DASHED


def restyle(item: Any) -> Any:
    """Recolour, re-pattern and re-stroke an item the way the properties panel
    does: the attribute AND the live Qt object, together."""
    if not isinstance(item, PolylineItem):
        item.fill_pattern = PATTERN
        item.fill_color = QColor(FILL)
        item.setBrush(create_pattern_brush(PATTERN, QColor(FILL)))
    # a style preset paints its own picture along the line: its pen is not dashed
    dashed = getattr(item, "path_fence_style", PathFenceStyle.NONE) is PathFenceStyle.NONE
    item.stroke_color = QColor(STROKE)
    item.stroke_width = WIDTH
    pen = QPen(item.pen())
    pen.setColor(QColor(STROKE))
    pen.setWidthF(WIDTH)
    if dashed:
        item.stroke_style = STYLE
        pen.setStyle(STYLE.to_qt_pen_style())
    item.setPen(pen)
    assert style_gaps(item) == []
    return item


SOURCES: dict[str, Callable[[], Any]] = {
    "rectangle": lambda: RectangleItem(100.0, 100.0, 300.0, 200.0, object_type=ObjectType.TERRACE_PATIO),
    "polygon": lambda: PolygonItem(
        [QPointF(100.0, 100.0), QPointF(400.0, 100.0), QPointF(400.0, 180.0), QPointF(220.0, 180.0),
         QPointF(220.0, 300.0), QPointF(100.0, 300.0)], object_type=ObjectType.LAWN),
    "circle": lambda: CircleItem(300.0, 300.0, 90.0, object_type=ObjectType.GENERIC_CIRCLE),
    "ellipse": lambda: EllipseItem(100.0, 100.0, 300.0, 180.0, object_type=ObjectType.GENERIC_ELLIPSE),
    "polyline": lambda: PolylineItem(
        [QPointF(100.0, 100.0), QPointF(300.0, 140.0), QPointF(360.0, 320.0)], object_type=ObjectType.FENCE),
    "styled path": lambda: PolylineItem(
        [QPointF(100.0, 100.0), QPointF(300.0, 140.0), QPointF(360.0, 320.0)], object_type=ObjectType.PATH,
        path_fence_style=PathFenceStyle.GRAVEL_PATH),
}


def source(shape: str) -> Any:
    return restyle(SOURCES[shape]())


def looks_like(copy: Any, original: Any) -> list[str]:
    """What of the original's painted look the copy does not have."""
    off = []
    if not _same_brush(copy.brush(), original.brush()):
        off.append("brush")
    mine, theirs = copy.pen(), original.pen()
    if (mine.color(), mine.widthF(), mine.style()) != (theirs.color(), theirs.widthF(), theirs.style()):
        off.append(f"pen {mine.color().name()} {mine.widthF()} {mine.style().name}")
    return off


_SCENES: list[CanvasScene] = []  # a scene owns its items: kept while the module's tests run


def through_the_file(item: Any, tmp_path: Path) -> Any:
    """``item`` saved in a plan and loaded again — the one item of the loaded plan."""
    scene = CanvasScene(width_cm=2000.0, height_cm=1500.0)
    if item.scene() is not None:
        item.scene().removeItem(item)
    scene.addItem(item)
    manager = ProjectManager()
    path = tmp_path / f"plan_{len(list(tmp_path.iterdir()))}.ogp"
    manager.save(scene, path)
    loaded = CanvasScene()
    _SCENES.extend((scene, loaded))
    ProjectManager().load(loaded, path)
    found = [candidate for candidate in loaded.items() if getattr(candidate, "object_type", None) is not None
             and candidate.parentItem() is None]
    assert len(found) == 1, found
    return found[0]


# ── the operations ────────────────────────────────────────────────────────────


def _serialised(item: Any) -> Any:
    """The clipboard, duplicate and the four array commands: ``_serialize_item`` →
    ``_deserialize_item`` (``CanvasView`` delegates both to ``ProjectManager``)."""
    data = ProjectManager._serialize_item(item)  # noqa: SLF001
    assert data is not None
    return ProjectManager._deserialize_item(data)  # noqa: SLF001


def _mirrored(item: Any) -> Any:
    return build_mirrored_item(item, QPointF(500.0, 0.0), QPointF(500.0, 400.0))


def _offset(item: Any) -> Any:
    return _compute_offset_item(item, 20.0, inward=False)


def _corner(item: Any) -> Any:
    """What the chamfer and the fillet tool both build of their host
    (``rebuild_with_corner_replaced``), at the item's second corner."""
    if isinstance(item, RectangleItem):
        corners = [item.mapToScene(p) for p in rectangle_corners_local(item)]
    elif isinstance(item, PolygonItem):
        corners = [item.mapToScene(item.polygon().at(k)) for k in range(item.polygon().count())]
    else:
        corners = [item.mapToScene(p) for p in item.points]
    before, corner, after = corners[0], corners[1], corners[2]

    def toward(a: QPointF, b: QPointF) -> QPointF:
        length = ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5
        return QPointF(a.x() + (b.x() - a.x()) * 15.0 / length, a.y() + (b.y() - a.y()) * 15.0 / length)

    target = CornerTarget(item=item, vertex_index=1, p_prev_scene=before, p_corner_scene=corner,
                          p_next_scene=after)
    return rebuild_with_corner_replaced(target, toward(corner, before), toward(corner, after))


def _re_pointed(item: Any) -> Any:
    return item.clone_with_points([QPointF(0.0, 0.0), QPointF(150.0, 40.0), QPointF(260.0, 10.0)])


#: operation → (how, the shapes it accepts, is the result a COPY that keeps the look)
OPERATIONS: dict[str, tuple[Callable[[Any], Any], tuple[str, ...], bool]] = {
    "clipboard / duplicate / arrays": (_serialised, tuple(SOURCES), True),
    "mirror": (_mirrored, tuple(SOURCES), True),
    # a rectangle, circle or ellipse is offset as a new shape of its type's default
    # look — in step, and no copy of its source's look (shipped behaviour, not changed)
    "offset": (_offset, ("polygon", "polyline", "styled path"), True),
    "offset (new shape)": (_offset, ("rectangle", "circle", "ellipse"), False),
    "chamfer / fillet": (_corner, ("rectangle", "polygon", "polyline", "styled path"), True),
    "clone_with_points (trim, corner, mirror of a line)": (_re_pointed, ("polyline", "styled path"), True),
}
CASES = [(name, shape) for name, (_how, shapes, _copy) in OPERATIONS.items() for shape in shapes]


class TestEveryDerivedItemSaysWhatItPaints:
    @pytest.mark.parametrize(("operation", "shape"), CASES, ids=[f"{o} of a {s}" for o, s in CASES])
    def test_the_attributes_describe_the_brush_and_the_pen(
            self, qtbot: Any, operation: str, shape: str) -> None:
        how, _shapes, is_copy = OPERATIONS[operation]
        original = source(shape)
        derived = how(original)
        assert derived is not None
        assert style_gaps(derived) == []
        if is_copy:
            assert looks_like(derived, original) == []

    @pytest.mark.parametrize(("operation", "shape"), CASES, ids=[f"{o} of a {s}" for o, s in CASES])
    def test_the_look_survives_the_project_file(
            self, qtbot: Any, tmp_path: Path, operation: str, shape: str) -> None:
        """The shipped 2D defect behind the finding: the file is written from the
        attributes, so a copy that did not carry them changed colour on save."""
        how, _shapes, _copy = OPERATIONS[operation]
        derived = how(source(shape))
        loaded = through_the_file(derived, tmp_path)
        assert style_gaps(loaded) == []
        assert looks_like(loaded, derived) == []

    @pytest.mark.parametrize("shape", sorted(SOURCES))
    def test_a_loaded_item_says_what_it_paints(self, qtbot: Any, tmp_path: Path, shape: str) -> None:
        """Load → save → load: the same look both times, and attributes that state it
        (a loaded item's stroke attributes were its type's defaults: the properties
        panel showed them, and the undo of a type change painted with them)."""
        original = source(shape)
        once = through_the_file(original, tmp_path)
        assert style_gaps(once) == [] and looks_like(once, original) == []
        twice = through_the_file(once, tmp_path)
        assert style_gaps(twice) == [] and looks_like(twice, original) == []


def _left_click() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


@pytest.fixture()
def canvas(qtbot: Any) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


class TestThroughTheRealTools:
    """The same, through the commands a user reaches — the tools' own entry points."""

    @pytest.mark.parametrize("shape", ["rectangle", "polygon"])
    def test_a_trimmed_shape_becomes_a_line_that_states_its_pen(self, canvas: CanvasView, shape: str) -> None:
        if shape == "rectangle":
            host: Any = RectangleItem(100.0, 100.0, 800.0, 800.0, object_type=ObjectType.TERRACE_PATIO)
        else:
            host = PolygonItem([QPointF(100.0, 100.0), QPointF(900.0, 100.0), QPointF(900.0, 900.0),
                                QPointF(100.0, 900.0)], object_type=ObjectType.LAWN)
        restyle(host)
        canvas.scene().addItem(host)
        for x in (300.0, 700.0):
            canvas.scene().addItem(PolylineItem([QPointF(x, 0.0), QPointF(x, 200.0)], object_type=ObjectType.FENCE))
        before = {id(item) for item in canvas.scene().items()}
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool.mouse_move(_left_click(), QPointF(500.0, 100.0))
        tool.mouse_press(_left_click(), QPointF(500.0, 100.0))
        made = [item for item in canvas.scene().items()
                if isinstance(item, PolylineItem) and id(item) not in before]
        assert len(made) == 1 and host.scene() is None
        (line,) = made
        assert style_gaps(line) == []
        pen = line.pen()
        assert (pen.color(), pen.widthF(), pen.style()) == (STROKE, WIDTH, STYLE.to_qt_pen_style())
        assert (QColor(line.stroke_color), line.stroke_width, line.stroke_style) == (STROKE, WIDTH, STYLE)

    def test_a_trimmed_line_keeps_its_look_in_both_pieces(self, canvas: CanvasView) -> None:
        line = restyle(PolylineItem([QPointF(0.0, 500.0), QPointF(1000.0, 500.0)], object_type=ObjectType.FENCE))
        canvas.scene().addItem(line)
        for x in (300.0, 700.0):
            canvas.scene().addItem(PolylineItem([QPointF(x, 400.0), QPointF(x, 600.0)], object_type=ObjectType.FENCE))
        before = {id(item) for item in canvas.scene().items()}
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool.mouse_move(_left_click(), QPointF(500.0, 500.0))
        tool.mouse_press(_left_click(), QPointF(500.0, 500.0))
        pieces = [item for item in canvas.scene().items()
                  if isinstance(item, PolylineItem) and id(item) not in before]
        assert len(pieces) == 2
        for piece in pieces:
            assert style_gaps(piece) == [] and looks_like(piece, line) == []

    @pytest.mark.parametrize("shape", sorted(SOURCES))
    def test_duplicate_and_paste(self, canvas: CanvasView, shape: str) -> None:
        original = source(shape)
        canvas.scene().addItem(original)
        original.setSelected(True)
        canvas.duplicate_selected()
        canvas.scene().clearSelection()
        original.setSelected(True)
        canvas.copy_selected()
        canvas.paste()
        copies = [item for item in canvas.scene().items()
                  if type(item) is type(original) and item is not original]
        assert len(copies) == 2
        for copy in copies:
            assert style_gaps(copy) == [] and looks_like(copy, original) == []


# ── the writers that restyle an item in place (review 2) ──────────────────────

HEX = QColor.NameFormat.HexArgb
LINE_POINTS = (QPointF(100.0, 100.0), QPointF(400.0, 100.0), QPointF(400.0, 300.0))
LINES: dict[str, tuple[ObjectType, PathFenceStyle]] = {
    "fence": (ObjectType.FENCE, PathFenceStyle.NONE),
    "wall": (ObjectType.WALL, PathFenceStyle.NONE),
    "path": (ObjectType.PATH, PathFenceStyle.NONE),
    "gravel path": (ObjectType.PATH, PathFenceStyle.GRAVEL_PATH),
    "wooden fence": (ObjectType.FENCE, PathFenceStyle.WOODEN_FENCE),
}
#: the type a line is changed to in the type-change tests
OTHER_TYPE = {ObjectType.FENCE: ObjectType.WALL, ObjectType.WALL: ObjectType.PATH,
              ObjectType.PATH: ObjectType.FENCE}


def fresh_line(kind: str) -> PolylineItem:
    object_type, preset = LINES[kind]
    return PolylineItem(list(LINE_POINTS), object_type=object_type, path_fence_style=preset)


def pen_of(item: Any) -> tuple[str, float, Qt.PenStyle]:
    pen = item.pen()
    return pen.color().name(HEX), pen.widthF(), pen.style()


def stated(item: Any) -> tuple[str | None, float | None, StrokeStyle | None]:
    colour = item.stroke_color
    return (None if colour is None else QColor(colour).name(HEX)), item.stroke_width, item.stroke_style


def default_stroke(kind: str) -> tuple[str, float]:
    """The stroke a fresh line of this kind is built with: its preset's, else its type's."""
    object_type, preset = LINES[kind]
    look: Any = get_style(object_type) if preset is PathFenceStyle.NONE else get_path_fence_style_info(preset)
    return QColor(look.stroke_color).name(HEX), look.stroke_width


@pytest.fixture()
def panel(canvas: CanvasView, qtbot: Any) -> PropertiesPanel:
    """The properties panel on the canvas's own undo stack."""
    widget = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(widget)
    return widget


def on_canvas(canvas: CanvasView, panel: PropertiesPanel, item: Any) -> Any:
    canvas.scene().addItem(item)
    panel.set_selected_items([item])
    return item


class TestAFreshLineStatesItsPen:
    """Review 2: a line stated NO stroke until it had been through a project file —
    ``PolylineItem`` built its pen and left its stroke attributes ``None``. One line
    then behaved in two ways: reopened, an undo gave it its stroke back; freshly
    drawn, the same undo raised (``TestUndoOnAFreshLine``)."""

    @pytest.mark.parametrize("kind", sorted(LINES))
    def test_it_states_the_pen_it_is_built_with(self, qtbot: Any, kind: str) -> None:
        colour, width = default_stroke(kind)
        line = fresh_line(kind)
        pen = line.pen()
        # the pen is the one a line always had …
        assert pen_of(line) == (colour, width, Qt.PenStyle.SolidLine)
        assert (pen.capStyle(), pen.joinStyle()) == (Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        # … and the line says so
        assert stated(line) == (colour, width, StrokeStyle.SOLID)
        assert style_gaps(line) == []

    @pytest.mark.parametrize("tool_type", [ToolType.FENCE, ToolType.WALL, ToolType.PATH],
                             ids=lambda tool_type: tool_type.name)
    def test_a_line_drawn_with_the_tool_states_its_pen(self, canvas: CanvasView, tool_type: ToolType) -> None:
        canvas.set_active_tool(tool_type)
        tool = canvas.tool_manager.active_tool
        for point in LINE_POINTS:
            tool.mouse_press(_left_click(), point)
        enter = MagicMock(spec=QKeyEvent)
        enter.key.return_value = Qt.Key.Key_Return
        tool.key_press(enter)
        (line,) = [item for item in canvas.scene().items() if isinstance(item, PolylineItem)]
        colour, width, style = pen_of(line)
        assert stated(line) == (colour, width, StrokeStyle.SOLID) and style is Qt.PenStyle.SolidLine
        assert style_gaps(line) == []

    def test_a_preset_picked_in_the_panel_is_stated_too(self, canvas: CanvasView, panel: PropertiesPanel) -> None:
        line = on_canvas(canvas, panel, fresh_line("path"))
        panel._on_property_changed(line, "path_fence_style", PathFenceStyle.GRAVEL_PATH)  # noqa: SLF001
        assert pen_of(line) == stated_as_pen(line) == ("#ffb4aa96", 8.0, Qt.PenStyle.SolidLine)
        assert style_gaps(line) == []


def stated_as_pen(item: Any) -> tuple[str | None, float | None, Qt.PenStyle | None]:
    colour, width, style = stated(item)
    return colour, width, (None if style is None else style.to_qt_pen_style())


class TestUndoOnAFreshLine:
    """Shipped in v1.30.1, on a line that was DRAWN and not yet reopened: undoing a
    stroke-width edit raised ``TypeError`` (``setWidthF(None)``), undoing a dash edit
    ``AttributeError`` (``None.to_qt_pen_style()``), undoing a type change made in the
    properties panel ``TypeError`` — the panel takes the value to go back to from the
    stroke attributes, and a fresh line had none. Every case: the pen and what the
    line states, before the edit and after its undo, and again after a redo."""

    @pytest.mark.parametrize("kind", sorted(LINES))
    def test_a_width_edit(self, canvas: CanvasView, panel: PropertiesPanel, kind: str) -> None:
        line = on_canvas(canvas, panel, fresh_line(kind))
        before = pen_of(line), stated(line)
        panel._on_property_changed(line, "stroke_width", 7.5)  # noqa: SLF001
        assert pen_of(line)[1] == 7.5 == line.stroke_width
        canvas.command_manager.undo()
        assert (pen_of(line), stated(line)) == before
        canvas.command_manager.redo()
        assert pen_of(line)[1] == 7.5 == line.stroke_width and style_gaps(line) == []

    @pytest.mark.parametrize("kind", sorted(LINES))
    def test_a_dash_edit(self, canvas: CanvasView, panel: PropertiesPanel, kind: str) -> None:
        line = on_canvas(canvas, panel, fresh_line(kind))
        before = pen_of(line), stated(line)
        panel._on_property_changed(line, "stroke_style", StrokeStyle.DASHED)  # noqa: SLF001
        assert pen_of(line)[2] is Qt.PenStyle.DashLine and line.stroke_style is StrokeStyle.DASHED
        canvas.command_manager.undo()
        assert (pen_of(line), stated(line)) == before
        canvas.command_manager.redo()
        assert pen_of(line)[2] is Qt.PenStyle.DashLine and style_gaps(line) == []

    @pytest.mark.parametrize("kind", sorted(LINES))
    def test_a_type_change_in_the_panel(self, canvas: CanvasView, panel: PropertiesPanel, qtbot: Any,
                                        kind: str) -> None:
        """… and what the change itself gives: the NEW TYPE's stroke, also beside a
        preset, which stays (A.14 of the story's report: a gravel path changed to a
        fence is drawn 3.0 wide, where a version that did not read a preset line's
        saved stroke showed the preset's 8.0 after a reopen)."""
        line = on_canvas(canvas, panel, fresh_line(kind))
        was_type, preset = LINES[kind]
        new_type = OTHER_TYPE[was_type]
        style = get_style(new_type)
        before = pen_of(line), stated(line)
        panel._on_property_changed(line, "object_type", new_type)  # noqa: SLF001
        assert line.object_type is new_type and line.path_fence_style is preset
        assert pen_of(line) == (QColor(style.stroke_color).name(HEX), style.stroke_width, Qt.PenStyle.SolidLine)
        assert style_gaps(line) == []
        canvas.command_manager.undo()
        assert line.object_type is was_type and (pen_of(line), stated(line)) == before
        canvas.command_manager.redo()
        assert line.object_type is new_type and style_gaps(line) == []
        qtbot.wait(1)  # the panel refreshes itself on a zero timer: let it, while it lives

    def test_a_type_change_in_the_panel_on_a_restroked_preset_line(
            self, canvas: CanvasView, panel: PropertiesPanel, qtbot: Any) -> None:
        """The undo set the stroke attributes, let ``apply_style_preset`` overwrite them
        with the preset's, and then built the pen from the state: pen 12.0, stated 8.0."""
        line = on_canvas(canvas, panel, fresh_line("gravel path"))
        panel._on_property_changed(line, "stroke_width", 12.0)  # noqa: SLF001
        before = pen_of(line), stated(line)
        assert before[0] == ("#ffb4aa96", 12.0, Qt.PenStyle.SolidLine)
        panel._on_property_changed(line, "object_type", ObjectType.WALL)  # noqa: SLF001
        assert pen_of(line) == ("#ff696969", 4.0, Qt.PenStyle.SolidLine)  # the wall's, beside the gravel
        assert line.path_fence_style is PathFenceStyle.GRAVEL_PATH and style_gaps(line) == []
        canvas.command_manager.undo()
        assert (pen_of(line), stated(line)) == before and style_gaps(line) == []
        qtbot.wait(1)

    def test_a_type_change_in_the_context_menu_gives_a_restroked_line_its_stroke_back(
            self, canvas: CanvasView, panel: PropertiesPanel) -> None:
        """``_setup_styling`` built a line's pen from its TYPE, whatever the line
        stated: the undo of a context-menu type change gave a re-stroked fence the
        fence type's 3.0 solid brown — and attributes that said 7.5 dashed."""
        line = on_canvas(canvas, panel, fresh_line("fence"))
        panel._on_property_changed(line, "stroke_width", 7.5)  # noqa: SLF001
        panel._on_property_changed(line, "stroke_style", StrokeStyle.DASHED)  # noqa: SLF001
        before = pen_of(line), stated(line)
        assert before[0] == ("#ff8b4513", 7.5, Qt.PenStyle.DashLine)
        line.setSelected(True)
        line._dispatch_change_type(ObjectType.WALL)  # noqa: SLF001
        assert pen_of(line) == stated_as_pen(line) == ("#ff696969", 4.0, Qt.PenStyle.SolidLine)
        canvas.command_manager.undo()
        assert line.object_type is ObjectType.FENCE and (pen_of(line), stated(line)) == before
        pen = line.pen()
        assert (pen.capStyle(), pen.joinStyle()) == (Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


# ── a file the app did not write (review 2) ───────────────────────────────────

GRAVEL = ("#ffb4aa96", 8.0)  # the gravel preset's stroke
SAVED = {"stroke_color": "#ff102030", "stroke_width": 12.0}
#: a saved stroke on a preset line → the (colour, width) the line is loaded with
PRESET_STROKES: dict[str, tuple[dict[str, Any], tuple[str, float]]] = {
    "as the app writes it": (SAVED, ("#ff102030", 12.0)),
    "width null": ({**SAVED, "stroke_width": None}, ("#ff102030", 8.0)),
    'width "8"': ({**SAVED, "stroke_width": "8"}, ("#ff102030", 8.0)),
    "width [8.0]": ({**SAVED, "stroke_width": [8.0]}, ("#ff102030", 8.0)),
    "width true": ({**SAVED, "stroke_width": True}, ("#ff102030", 8.0)),
    "width 0.0": ({**SAVED, "stroke_width": 0.0}, ("#ff102030", 8.0)),
    "width -3.0": ({**SAVED, "stroke_width": -3.0}, ("#ff102030", 8.0)),
    "width 0.01": ({**SAVED, "stroke_width": 0.01}, ("#ff102030", 8.0)),
    "width just under the panel's minimum": ({**SAVED, "stroke_width": 0.499}, ("#ff102030", 8.0)),
    "width at the panel's minimum": ({**SAVED, "stroke_width": 0.5}, ("#ff102030", 0.5)),
    "no width": ({"stroke_color": "#ff102030"}, ("#ff102030", 8.0)),
    "colour null": ({**SAVED, "stroke_color": None}, ("#ffb4aa96", 12.0)),
    "colour a number": ({**SAVED, "stroke_color": 7}, ("#ffb4aa96", 12.0)),
    "colour a list": ({**SAVED, "stroke_color": ["#ff102030"]}, ("#ffb4aa96", 12.0)),
    'colour "notacolour"': ({**SAVED, "stroke_color": "notacolour"}, ("#ffb4aa96", 12.0)),
    # a colour the panel's own dialog can make (it offers the alpha channel): as given
    "colour fully transparent": ({**SAVED, "stroke_color": "#00000000"}, ("#00000000", 12.0)),
    "colour by name": ({**SAVED, "stroke_color": "red"}, ("#ffff0000", 12.0)),
    "both unusable": ({"stroke_color": None, "stroke_width": None}, GRAVEL),
}
#: a fill colour and NO fill pattern, on types whose own pattern is a TEXTURE
UNPATTERNED: dict[str, dict[str, Any]] = {
    "rectangle": {"type": "rectangle", "x": 20, "y": 20, "width": 200, "height": 120, "object_type": "LAWN"},
    "circle": {"type": "circle", "center_x": 120, "center_y": 90, "radius": 70, "object_type": "POND_POOL"},
    "ellipse": {"type": "ellipse", "center_x": 120, "center_y": 90, "semi_x": 100, "semi_y": 60,
                "object_type": "POND_POOL"},
    "polygon": {"type": "polygon", "object_type": "LAWN",
                "points": [{"x": 20, "y": 20}, {"x": 220, "y": 20}, {"x": 160, "y": 150}]},
}
SPRITES: dict[str, Callable[[], Any]] = {
    "furniture rectangle": lambda: RectangleItem(100.0, 100.0, 150.0, 100.0, object_type=ObjectType.TABLE_RECTANGULAR),
    "furniture circle": lambda: CircleItem(300.0, 300.0, 50.0, object_type=ObjectType.TABLE_ROUND),
    "plant circle": lambda: CircleItem(300.0, 300.0, 90.0, object_type=ObjectType.TREE),
}
AUDIT_PLAN = REPO / "tests" / "fixtures" / "plans" / "audit-2026-10-plan_500.ogp"


def hand_made(tmp_path: Path, obj: dict[str, Any]) -> Path:
    path = tmp_path / f"hand_made_{len(list(tmp_path.iterdir()))}.ogp"
    path.write_text(json.dumps({"version": "1.4", "canvas": {"width": 400, "height": 300}, "objects": [obj]}),
                    encoding="utf-8")
    return path


def loaded_plan(path: Path) -> CanvasScene:
    scene = CanvasScene()
    _SCENES.append(scene)
    ProjectManager().load(scene, path)
    return scene


def typed_items(scene: CanvasScene) -> list[Any]:
    return [item for item in scene.items() if getattr(item, "object_type", None) is not None
            and item.parentItem() is None]


def picture(scene: CanvasScene) -> bytes:
    image = QImage(240, 180, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(QColor(255, 255, 255))
    painter = QPainter(image)
    scene.render(painter, QRectF(0.0, 0.0, 240.0, 180.0), QRectF(0.0, 0.0, 240.0, 180.0))
    painter.end()
    return bytes(image.constBits().asstring(image.sizeInBytes()))


class TestAFileTheAppDidNotWrite:
    @pytest.mark.parametrize("case", list(PRESET_STROKES))
    def test_a_preset_lines_stroke_the_app_could_not_have_written_keeps_the_presets(
            self, qtbot: Any, tmp_path: Path, case: str) -> None:
        """Review 2: once a preset line's saved stroke was read at all, it was applied
        as found — ``"stroke_width": null``, ``"8"`` or ``[8.0]`` and ``"stroke_color":
        null`` raised and the item was SKIPPED (gone after the next save); 0.0, -3.0
        and 0.01 loaded as given, ``"notacolour"`` as black. Every one of those files
        loaded at the preset's stroke before. Now: a width that is no finite number
        of at least the panel's minimum, and a colour that is none, keep the PRESET's
        value — each on its own — and nothing raises."""
        stroke, (colour, width) = PRESET_STROKES[case]
        obj = {"type": "polyline", "object_type": "PATH", "path_fence_style": "GRAVEL_PATH",
               "points": [{"x": 10, "y": 10}, {"x": 200, "y": 40}], **stroke}
        scene = loaded_plan(hand_made(tmp_path, obj))
        (line,) = typed_items(scene)  # not skipped
        assert pen_of(line)[:2] == (colour, width) == stated(line)[:2]
        assert style_gaps(line) == []
        # … and what the next save writes is a stroke the app can read back
        again = tmp_path / "saved_again.ogp"
        ProjectManager().save(scene, again)
        (saved,) = json.loads(again.read_text(encoding="utf-8"))["objects"]
        assert (saved["stroke_color"], saved["stroke_width"]) == (colour, width)

    @pytest.mark.parametrize("width", [float("inf"), float("nan"), 10 ** 400],
                             ids=["infinite", "not a number", "400 digits"])
    def test_a_width_no_finite_number_can_hold_refuses_the_whole_plan(
            self, qtbot: Any, tmp_path: Path, width: float) -> None:
        """Three of review 2's cases never reach an item since master's strict numeric
        plan I/O (#453, AUD-041, ``core/plan_io.py``): a stroke width that is infinite,
        not a number or an integer no float can hold refuses the DOCUMENT before any
        item is built — the loader raises, the scene stays empty. (On this branch
        before the sync, each kept the preset's width.)"""
        from open_garden_planner.core.plan_io import PlanValidationError

        obj = {"type": "polyline", "object_type": "PATH", "path_fence_style": "GRAVEL_PATH",
               "points": [{"x": 10, "y": 10}, {"x": 200, "y": 40}], **SAVED, "stroke_width": width}
        scene = CanvasScene()
        _SCENES.append(scene)
        with pytest.raises(PlanValidationError):
            ProjectManager().load(scene, hand_made(tmp_path, obj))
        assert typed_items(scene) == []

    def test_what_counts_as_a_saved_stroke(self) -> None:
        """The two readers themselves — a pen cannot tell every case apart (Qt refuses
        an infinite width on its own and keeps the old one)."""
        assert [saved_stroke_width(value) for value in (0.5, 12, 12.0, 20.0, 1e6)] == [0.5, 12.0, 12.0, 20.0, 1e6]
        for unusable in (None, "8", [8.0], {"w": 8}, True, False, 0, 0.0, -3.0, 0.01, 0.499, float("inf"),
                         float("-inf"), float("nan"), 10 ** 400, -(10 ** 400)):
            assert saved_stroke_width(unusable) is None, unusable
        assert MIN_STROKE_WIDTH == 0.5
        for text, rgba in (("#ff102030", (16, 32, 48, 255)), ("#102030", (16, 32, 48, 255)),
                           ("#00000000", (0, 0, 0, 0)), ("red", (255, 0, 0, 255))):
            colour = saved_stroke_colour(text)
            assert colour is not None and colour.getRgb() == rgba
        for unusable in (None, 7, 7.5, True, ["#ff102030"], "notacolour", "", "#ff10203"):
            assert saved_stroke_colour(unusable) is None, unusable

    def test_the_panel_and_the_dialog_start_at_the_same_minimum(self, qtbot: Any) -> None:
        """"The panel's minimum" is one number: both stroke-width spin boxes use it."""
        import inspect

        from open_garden_planner.ui.dialogs import properties_dialog
        from open_garden_planner.ui.panels import properties_panel

        for module in (properties_panel, properties_dialog):
            assert "setRange(MIN_STROKE_WIDTH, 20.0)" in inspect.getsource(module), module.__name__

    @pytest.mark.parametrize("shape", sorted(UNPATTERNED))
    def test_a_fill_colour_without_a_pattern_is_painted_the_same_before_and_after_a_save(
            self, qtbot: Any, tmp_path: Path, shape: str) -> None:
        """Review 2: a file that states a fill colour and no pattern (hand-made, or
        older than the patterns) was painted in two ways — first the type's TEXTURE at
        the type's tint (the loader recoloured the brush the constructor had made,
        which does nothing to a texture) while the item stated the saved colour; and
        after one save and reopen the texture at the saved colour. Measured for all
        four shapes: the middle of a lawn went from (79, 144, 54) to (111, 97, 44)."""
        red = QColor("#ffc81e1e")
        scene = loaded_plan(hand_made(tmp_path, {**UNPATTERNED[shape], "fill_color": "#ffc81e1e"}))
        (item,) = typed_items(scene)
        style = get_style(item.object_type)
        assert item.fill_pattern is style.fill_pattern is not FillPattern.SOLID
        assert _same_brush(item.brush(), create_pattern_brush(style.fill_pattern, red))
        # control: the type's own tint is another picture
        assert not _same_brush(item.brush(), create_pattern_brush(style.fill_pattern, style.fill_color))
        assert style_gaps(item) == []
        first = picture(scene)
        again = tmp_path / "saved_again.ogp"
        ProjectManager().save(scene, again)
        assert picture(loaded_plan(again)) == first

    @pytest.mark.parametrize("kind", sorted(SPRITES))
    def test_a_loaded_sprite_states_what_its_file_holds_and_is_not_held_to_its_pen(
            self, qtbot: Any, tmp_path: Path, kind: str) -> None:
        """A sprite's pen says nothing about its picture — it is ``NoPen`` when the
        item is built, and a solid black 1.0 once it was loaded (the saver writes the
        pen's colour and width, the loader gives the pen the saved ``stroke_style``).

        What the item STATES after a load is master's rule since #502
        (``restore_stored_look``: what the file holds — that black 1.0); review 2's
        "its type's stroke", which this branch had kept by not reading the stroke
        attributes off the pen, gave way to it in the sync of 2026-10-19 (PF-CAN-21).
        What stays this branch's: the guard does not hold a sprite's pen against its
        attributes (``paints_sprite``), and ``adopt_pen`` does not write a sprite's
        attributes from a pen."""
        item = SPRITES[kind]()
        style = get_style(item.object_type)
        assert paints_sprite(item)
        assert stated(item) == (QColor(style.stroke_color).name(HEX), style.stroke_width, style.stroke_style)
        once = through_the_file(item, tmp_path)
        assert pen_of(once) == ("#ff000000", 1.0, Qt.PenStyle.SolidLine)  # the pen it is saved with
        assert stated(once)[:2] == ("#ff000000", 1.0) and style_gaps(once) == []
        twice = through_the_file(once, tmp_path)
        assert stated(twice) == stated(once) and pen_of(twice) == pen_of(once)
        # adopt_pen leaves a sprite's attributes alone, whatever the pen
        before = stated(twice)
        adopt_pen(twice, QPen(QColor("#ff102030"), 7.0))
        assert stated(twice) == before and pen_of(twice)[:2] == ("#ff102030", 7.0)
        assert style_gaps(twice) == []

    def test_the_guard_holds_no_sprite_of_the_reference_plan_to_its_pen(self, qtbot: Any) -> None:
        """200 of the 495 items of the audit's reference plan are sprites: the whole
        plan, loaded, is in step — every item, sprites included."""
        scene = loaded_plan(AUDIT_PLAN)
        items = typed_items(scene)
        sprites = [item for item in items if paints_sprite(item)]
        assert (len(items), len(sprites)) == (495, 200)
        assert style_gaps_in([scene]) == []


# ── the guard itself ──────────────────────────────────────────────────────────


def _forgetful(name: str, item: Any) -> Any:
    """Six ways to build an item from ``item`` and forget its attributes — the ones a
    review planted to see what a scan of the source would catch (one of six)."""
    if name == "the type as a keyword":
        made: Any = PolygonItem(_polygon_points(item), object_type=item.object_type)
    elif name == "the type through a local":
        kind = item.object_type
        made = PolygonItem(_polygon_points(item), kind)
    elif name == "a constant type":
        made = PolygonItem(_polygon_points(item), ObjectType.LAWN)
    elif name == "a factory":
        made = type(item)(_polygon_points(item))
    elif name == "the look through a variable":
        made = PolygonItem(_polygon_points(item), object_type=item.object_type)
        brush = item.brush()
        made.setBrush(brush)
        return made
    else:  # "the pen alone"
        made = PolygonItem(_polygon_points(item), object_type=item.object_type)
        pen = item.pen()
        made.setPen(pen)
        return made
    made.setBrush(QBrush(item.brush()))
    made.setPen(QPen(item.pen()))
    return made


def _polygon_points(item: Any) -> list[QPointF]:
    return [QPointF(point.x() + 40.0, point.y() + 40.0)
            for point in (item.polygon().at(k) for k in range(item.polygon().count()))]


FORGETFUL = ("the type as a keyword", "the type through a local", "a constant type", "a factory",
             "the look through a variable", "the pen alone")


class TestTheGuard:
    """``conftest.py``'s teardown fixture: what it tracks, and that it has teeth."""

    def test_every_test_here_is_watched(self, qtbot: Any, request: pytest.FixtureRequest) -> None:
        assert "_every_item_says_what_it_paints" in request.fixturenames
        with watched_scenes() as mine:  # the same tracking, nested: both see the scene
            scene = CanvasScene()
            assert mine == [scene]
        assert CanvasScene() not in mine  # … and the tracking ends with the block

    @pytest.mark.style_gaps_allowed("plants forgetful copies to show the guard sees each of them")
    @pytest.mark.parametrize("how", FORGETFUL)
    def test_it_sees_a_forgetful_operation_however_it_is_spelled(self, qtbot: Any, how: str) -> None:
        with watched_scenes() as scenes:
            scene = CanvasScene(width_cm=2000.0, height_cm=1500.0)
            original = source("polygon")
            scene.addItem(original)
            assert style_gaps_in(scenes) == []
            scene.addItem(_forgetful(how, original))
        found = style_gaps_in(scenes)
        assert len(found) == 1 and found[0].startswith("PolygonItem ")
        with pytest.raises(pytest.fail.Exception, match="1 item"):
            fail_on_style_gaps(scenes)

    @pytest.mark.style_gaps_allowed("drives the guard by hand around a planted gap")
    def test_the_fixture_fails_a_test_that_leaves_a_gap_and_spares_a_marked_one(
            self, qtbot: Any, request: pytest.FixtureRequest) -> None:
        """The fixture itself, start to end, as pytest drives it — by hand, because a
        fixture's teardown cannot be caught from inside its own test."""
        class Unmarked:
            def get_closest_marker(self, name: str) -> None:
                return None

        class MarkedWithoutAReason:
            def get_closest_marker(self, name: str) -> Any:
                return pytest.mark.style_gaps_allowed().mark

        build = CanvasScene.__init__
        guard = guarded(Unmarked())
        next(guard)  # set-up: scenes are tracked from here on
        assert CanvasScene.__init__ is not build
        scene = CanvasScene(width_cm=2000.0, height_cm=1500.0)
        original = source("polygon")
        scene.addItem(original)
        scene.addItem(_forgetful("a factory", original))
        with pytest.raises(pytest.fail.Exception, match=r"1 item\(s\) whose style attributes"):
            next(guard)  # the judgement
        assert CanvasScene.__init__ is build  # … and the tracking is taken off again
        # a clean test passes it
        clean = guarded(Unmarked())
        next(clean)
        CanvasScene().addItem(source("polygon"))
        with pytest.raises(StopIteration):
            next(clean)
        # a marked test is not tracked and not judged — this one is such a test
        marked = guarded(request.node)
        next(marked)
        assert CanvasScene.__init__ is build
        with pytest.raises(StopIteration):
            next(marked)
        # … and the marker must give its reason
        with pytest.raises(AssertionError, match="needs its reason"):
            next(guarded(MarkedWithoutAReason()))

    def test_two_plain_brushes_that_paint_nothing_are_in_step(self, qtbot: Any) -> None:
        """What the guard found first: a type change gives a LINE its new type's fill
        colour — ``#00808080`` for a wall, fully transparent — beside the transparent
        black brush every line paints with. Neither paints anything; the predicate
        compares what is painted."""
        clear = QBrush(QColor(0, 0, 0, 0))
        assert _same_brush(clear, QBrush(QColor(128, 128, 128, 0)))
        # … and only then: one visible, or two visible colours a step apart, are not
        assert not _same_brush(clear, QBrush(QColor(128, 128, 128, 1)))
        assert not _same_brush(QBrush(QColor(10, 20, 30)), QBrush(QColor(10, 20, 31)))
        line = fresh_line("fence")
        line.fill_color, line.fill_pattern = QColor(128, 128, 128, 0), FillPattern.SOLID
        assert style_gaps(line) == []
        line.fill_color = QColor(128, 128, 128, 1)
        assert len(style_gaps(line)) == 1
        line.fill_color = QColor(128, 128, 128, 0)

    def test_a_scene_that_is_gone_is_skipped(self, qtbot: Any) -> None:
        with watched_scenes() as scenes:
            scene = CanvasScene()
            scene.addItem(source("polygon"))
        sip.delete(scene)
        assert style_gaps_in(scenes) == []
        fail_on_style_gaps(scenes)  # nothing to say: no failure


# ── the map: where items are built from items ─────────────────────────────────

#: The places in the product that build a canvas item out of another one, as far
#: as the scan below can tell: ``module → the functions that do it`` — and,
#: beside each, the operation above that covers it. A function the scan finds
#: and this table does not name fails the test below; a function the scan does
#: NOT find (the type through a local, a ``type(item)(…)`` factory, a brush held
#: in a variable, anything outside ``core/`` and ``ui/canvas/``) is held to the
#: rule by the teardown fixture in ``conftest.py``, not by this table.
DERIVING: dict[str, dict[str, str]] = {
    "core/mirror_geometry.py": {
        "_mirror_polygon": "mirror", "_mirror_circle": "mirror", "_mirror_box": "mirror",
        "_mirror_polyline": "mirror (clone_with_points)",
        # arcs and Béziers: their own stroke model (``ArcItem`` / ``BezierItem`` hold
        # ``stroke_color`` and ``stroke_width`` and build their pen from them); they
        # have no fill and no place on the 3D ground
        "_mirror_arc": "not a GardenItem fill/stroke: own model", "_mirror_bezier": "own model",
    },
    "core/tools/offset_tool.py": {
        "_offset_rectangle": "offset (new shape)", "_offset_circle": "offset (new shape)",
        "_offset_ellipse": "offset (new shape)", "_offset_polygon": "offset", "_offset_polyline": "offset",
    },
    "core/tools/corner_edit_base.py": {"rebuild_with_corner_replaced": "chamfer / fillet"},
    "core/tools/trim_tool.py": {
        "_trim_polyline": "trim (clone_with_points)", "_trim_polygon": "trim", "_trim_rectangle": "trim",
    },
    "ui/canvas/items/polyline_item.py": {"clone_with_points": "clone_with_points"},
    "ui/canvas/canvas_view.py": {
        "paste": "clipboard", "duplicate_selected": "duplicate", "create_linear_array": "arrays",
        "create_grid_array": "arrays", "create_circular_array": "arrays",
        "create_array_along_path": "arrays",
    },
}

_ITEM_CLASSES = {"RectangleItem", "PolygonItem", "PolylineItem", "CircleItem", "EllipseItem", "ArcItem",
                 "BezierItem", "cls"}


def _reads_a_look(node: ast.AST) -> bool:
    """Does the expression read another object's ``brush()`` or ``pen()``?"""
    return any(isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
               and inner.func.attr in ("brush", "pen") for inner in ast.walk(node))


def _derives_an_item(function: ast.AST) -> bool:
    """Does this function build an item from another item? One of four marks:

    - it constructs an item class with a keyword taken off another ITEM
      (``object_type=x.object_type``, ``layer_id=x.layer_id``);
    - it calls ``clone_with_points``, or turns a serialised item back into one
      (``_deserialize_item``);
    - it calls the style helper for a look that is another item's
      (``copy_visual_style``, or ``adopt_pen`` with a pen read off an object —
      an item that gives ITSELF a pen it built, as ``PolylineItem._setup_styling``
      does, derives nothing);
    - it hands one object's ``brush()`` or ``pen()`` to another's ``setBrush`` /
      ``setPen`` — the raw copy the finding was about (a painter's is not an item's).
    """
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
        if name in ("clone_with_points", "_deserialize_item", "copy_visual_style", "_copy_visual_style"):
            return True
        if name == "adopt_pen" and any(_reads_a_look(argument) for argument in node.args):
            return True
        if name in _ITEM_CLASSES and any(
                isinstance(keyword.value, ast.Attribute) and keyword.value.attr == keyword.arg
                and keyword.arg in ("object_type", "layer_id") for keyword in node.keywords):
            return True
        if (name in ("setBrush", "setPen") and isinstance(callee, ast.Attribute)
                and not (isinstance(callee.value, ast.Name) and callee.value.id == "painter")
                and any(_reads_a_look(argument) for argument in node.args)):
            return True
    return False


def test_no_brush_or_pen_is_copied_past_the_helper() -> None:
    """The raw copy — ``a.setBrush(QBrush(b.brush()))`` — exists in ONE place:
    ``core/item_look.py``. Everywhere else it is the defect of the finding."""
    raw = []
    for folder in ("core", "ui/canvas"):
        for path in sorted((SRC / folder).rglob("*.py")):
            relative = path.relative_to(SRC).as_posix()
            if relative == "core/item_look.py":
                continue  # the one place (``copy_visual_style``)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("setBrush", "setPen")
                        and not (isinstance(node.func.value, ast.Name) and node.func.value.id == "painter")
                        and any(_reads_a_look(argument) for argument in node.args)):
                    raw.append(f"{relative}:{node.lineno}")
    assert raw == []
    # control: the scan sees the two lines the offset tool had
    was = ast.parse("\n".join((
        "new_item.setPen(QPen(item.pen()))", "new_item.setBrush(QBrush(item.brush()))",
        "painter.setPen(self.pen())", "pen = item.pen()", "item.setPen(pen)")))
    assert sum(1 for node in ast.walk(was) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr in ("setBrush", "setPen")
               and not (isinstance(node.func.value, ast.Name) and node.func.value.id == "painter")
               and any(_reads_a_look(argument) for argument in node.args)) == 2


def test_the_map_of_item_from_item_operations_is_current() -> None:
    """Every function under ``core/`` and ``ui/canvas/`` that the scan recognises as
    building an item from an item is in ``DERIVING``, with the operation that
    covers it. A map kept current — not a proof that nothing else derives an item:
    the scan knows four spellings (``_derives_an_item``). What holds an operation
    it cannot see to the rule is the teardown fixture in ``conftest.py``."""
    found: dict[str, set[str]] = {}
    for folder in ("core", "ui/canvas"):
        for path in sorted((SRC / folder).rglob("*.py")):
            relative = path.relative_to(SRC).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _derives_an_item(node):
                    found.setdefault(relative, set()).add(node.name)
    # the loader, the wrapper that IS the primitive and the helper itself are not derivations
    found.get("ui/canvas/canvas_view.py", set()).discard("_deserialize_item")
    found.pop("core/project.py", None)
    found.pop("core/item_look.py", None)
    assert {module: set(names) for module, names in DERIVING.items()} == found
