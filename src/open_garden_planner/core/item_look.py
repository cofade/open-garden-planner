"""An item's *look*, written in one place (issues #438, #441, #469, #470).

A canvas item states its look twice, and both statements must say the same:

* the **live** appearance — the ``QPen`` and ``QBrush`` the item paints with;
* the **serialized** appearance — ``fill_pattern`` / ``fill_color`` /
  ``stroke_color`` / ``stroke_width`` / ``stroke_style`` on
  :class:`~open_garden_planner.ui.canvas.items.garden_item.GardenItemMixin` —
  what the project file, the clipboard, the Properties panel, the undo of a type
  change and the 3D ground bake read.

Every writer that set only one half was a defect nobody saw on the canvas: a
copy that looked right until the next save, a loaded item whose panel showed the
type's defaults, an offset copy baked into the 3D ground in its type's colour.
So the writers go through this module:

* :func:`copy_visual_style` — an "item made from an item" (offset, mirror,
  chamfer / fillet, a re-pointed line) takes its source's look, both halves;
* :func:`restore_stored_look` — the ``.ogp`` loader writes the saved attributes
  before it derives brush and pen from them;
* :func:`adopt_pen` — whoever gives an item a pen states it in the stroke
  attributes too (a freshly drawn line, a trimmed piece, a type change and its
  undo, a preset line's saved stroke);
* :func:`fill_brush` — the brush for a fill colour in the item's OWN pattern.

:func:`style_gaps` says where an item's two statements part. A teardown fixture
holds every item of every scene the integration suites build to it
(``tests/integration/conftest.py``).

ONE KIND OF ITEM IS LEFT OUT: an item whose picture is a sprite
(``GardenItemMixin.paints_sprite`` — a furniture rectangle, a plant or furniture
circle). Its ``paint`` draws the sprite and asks neither the brush nor the pen
for the picture (they are drawn only when the sprite's art is missing); its pen
is ``NoPen`` and its brush empty when it is built, and what the loader gives the
pen and the attributes is what the file holds (the saver writes that pen's colour
and width). Neither half says anything about what is painted, so
``style_gaps`` holds neither against the other and ``adopt_pen`` does not write
a sprite's stroke attributes from a pen.

Qt-touching but layer-neutral: callers live in ``core`` (the tools,
``mirror_geometry``, the loader) and ``ui``, so this module never imports
``ui``. The items are duck-typed (``GardenItemMixin`` items, which mypy cannot
see through a bare ``QGraphicsItem``), hence ``Any``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    StrokeStyle,
    get_path_fence_style_info,
    get_style,
)

__all__ = [
    "MAX_FENCE_WIDTH_CM",
    "MAX_LINE_WIDTH_CM",
    "MAX_STROKE_WIDTH",
    "MIN_STROKE_WIDTH",
    "LineLook",
    "adopt_pen",
    "apply_line_look",
    "capture_line_look",
    "copy_visual_style",
    "fill_brush",
    "line_look_for_preset",
    "line_look_for_type",
    "paints_sprite",
    "restore_stored_look",
    "saved_stroke_colour",
    "saved_stroke_width",
    "stroke_style_of",
    "style_gaps",
]

#: The narrowest stroke the properties panel and the properties dialog can set
#: (both spin boxes start here).
MIN_STROKE_WIDTH = 0.5
#: The widest OUTLINE of a shape the panel and the dialog can set.
MAX_STROKE_WIDTH = 20.0
#: The widest PATH the panel can set, in cm (scene units). A line's stroke is its width
#: on the ground: the 2D path painters, the ground bake and the 3D relief all read it
#: (Phase 17 L4.2, #388: the owner found a garden path capped at 20 cm).
MAX_LINE_WIDTH_CM = 500.0
#: The widest OTHER line — a fence, a wall, a hedge fence — in cm. A fence's posts and
#: rails reach half its stroke past each end, and from 200 cm their 3D build reached a
#: metre past the line (senior review of #388); at 100 cm it holds.
MAX_FENCE_WIDTH_CM = 100.0


@dataclass(frozen=True)
class LineLook:
    """One command's value snapshot; Qt values are copied at capture and restore.

    Presets select decoration geometry. Their defaults are applied when PICKED,
    never when a captured look is restored (#524–#526).
    """

    object_type: ObjectType
    preset: PathFenceStyle
    pen: QPen
    brush: QBrush
    fill_color: QColor | None
    fill_pattern: FillPattern | None


def capture_line_look(item: Any) -> LineLook:
    """Capture the live pen, including caps/joins/dashes, without shared Qt values."""
    color = item.fill_color
    return LineLook(item.object_type, item.path_fence_style, QPen(item.pen()), QBrush(item.brush()),
                    QColor(color) if color is not None else None, item.fill_pattern)


def line_look_for_type(object_type: ObjectType) -> LineLook:
    """A real type change selects its defaults and removes the previous preset."""
    style = get_style(object_type)
    pen = QPen(style.stroke_color)
    pen.setWidthF(style.stroke_width)
    pen.setStyle(style.stroke_style.to_qt_pen_style())
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return LineLook(object_type, PathFenceStyle.NONE, pen, QBrush(QColor(0, 0, 0, 0)),
                    QColor(style.fill_color), style.fill_pattern)


def line_look_for_preset(item: Any, preset: PathFenceStyle) -> LineLook:
    """Selecting NONE retains the stroke; another preset replaces color and width."""
    state = capture_line_look(item)
    pen = QPen(state.pen)
    if preset is not PathFenceStyle.NONE:
        style = get_path_fence_style_info(preset)
        pen.setColor(style.stroke_color)
        pen.setWidthF(style.stroke_width)
    return replace(state, preset=preset, pen=pen)


def apply_line_look(item: Any, state: LineLook) -> None:
    """Restore exactly, without calling a preset or depending on a panel widget."""
    item.object_type = state.object_type
    item.path_fence_style = state.preset
    item.fill_color = QColor(state.fill_color) if state.fill_color is not None else None
    item.fill_pattern = state.fill_pattern
    item.setBrush(QBrush(state.brush))
    adopt_pen(item, QPen(state.pen))
    item.update()

# Serialized appearance attributes carried by GardenItemMixin. Copying these
# keeps a copy's look after the next save; ``area_label_visible`` is copied
# separately as a display flag. A new appearance attribute must be added here.
_LOOK_ATTRIBUTES = (
    "fill_pattern",
    "fill_color",
    "stroke_color",
    "stroke_width",
    "stroke_style",
)


def _copy_value(value: Any) -> Any:
    """Copy a look attribute by value when it is a QColor (avoid a shared instance)."""
    return QColor(value) if isinstance(value, QColor) else value


def copy_visual_style(source: Any, dest: Any) -> None:
    """Copy the complete appearance of ``source`` onto ``dest``.

    ``dest`` is expected to be a freshly-built shape (its own constructor has
    already run); this overwrites whatever type defaults it started with so it
    looks exactly like ``source``.
    """
    for name in _LOOK_ATTRIBUTES:
        if hasattr(source, name) and hasattr(dest, name):
            setattr(dest, name, _copy_value(getattr(source, name)))

    # Live appearance last: the source pen already carries the right colour,
    # width and dash style for the item as it is painted.
    dest.setBrush(QBrush(source.brush()))
    dest.setPen(QPen(source.pen()))

    if getattr(source, "area_label_visible", False):
        dest.area_label_visible = True


def inherit_item_identity(source: Any, dest: Any) -> None:
    """Give a replacement shape the source's identity and garden bookkeeping (#668).

    A corner edit, a trim, or any other "rebuild this shape" operation removes
    the source item and inserts a freshly built one.  A constructor mints a new
    UUID, which silently orphans everything keyed by the old one: a plant's
    ``parent_bed_id`` and the bed's ``child_item_ids``, the bed's
    ``metadata.garden_tracking.zone_id``, the soil / pest / harvest records the
    ``ProjectData`` holds under that UUID, and every constraint anchored to the
    item.  The original leaves the scene in the same command, so the UUID is
    free for the replacement to keep.

    ``object_type`` is deliberately NOT copied — the caller decides the type
    (a trimmed rectangle becomes a fence polyline).  The transform is copied so
    a rotated source is replaced where it stood, not at the origin.
    """
    import copy

    dest._item_id = source.item_id
    dest.name = source.name
    dest._metadata = copy.deepcopy(source.metadata)
    dest._parent_bed_id = source.parent_bed_id
    dest._child_item_ids = list(source.child_item_ids)
    dest.layer_id = source.layer_id
    dest.label_visible = source.label_visible
    dest.area_label_visible = source.area_label_visible
    dest.setPos(source.pos())
    dest.setRotation(source.rotation())
    dest.setTransformOriginPoint(source.transformOriginPoint())


def _converted(convert: Callable[[Any], Any], value: Any) -> Any:
    """``convert(value)``, or None where the value is of a kind it cannot take."""
    try:
        return convert(value)
    except (TypeError, ValueError, OverflowError):
        return None


def restore_stored_look(
    item: Any,
    obj: Mapping[str, Any],
    *,
    fill_pattern: Any = None,
    stroke_style: Any = None,
) -> None:
    """Write a saved object dict's appearance back onto ``item`` (issues #438/#469).

    The `.ogp` loader rebuilt each item's brush and pen from the file but never
    wrote the **stored attributes** those are derived from. The item
    constructors pre-seed those attributes with the object type's style, so
    after a reload ``item.fill_color`` / ``stroke_color`` / ``stroke_width``
    held the *type defaults* while the canvas painted the file's colours: the
    Properties panel — which reads the attributes — disagreed with the canvas,
    and the next save wrote the defaults back over the user's colours.

    Call this **before** the branch's brush/pen derivation (or after, as long as
    the derivation reads the attributes). ``fill_pattern`` and ``stroke_style``
    are passed in already parsed by the caller.

    A saved stroke of a kind no colour or number can be made of (``null``, a
    list) leaves that attribute as it was instead of raising: what the branch
    then does with the value is the branch's decision — a plain shape's pen
    still refuses it (the item is skipped, as before), a preset line keeps its
    preset's stroke and states it (``adopt_pen``).
    """
    if fill_pattern is not None and hasattr(item, "fill_pattern"):
        item.fill_pattern = fill_pattern
    if "fill_color" in obj and hasattr(item, "fill_color"):
        item.fill_color = QColor(obj["fill_color"])
    if "stroke_color" in obj and hasattr(item, "stroke_color"):
        colour = _converted(QColor, obj["stroke_color"])
        if colour is not None:
            item.stroke_color = colour
    if "stroke_width" in obj and hasattr(item, "stroke_width"):
        width = _converted(float, obj["stroke_width"])
        if width is not None:
            item.stroke_width = width
    if stroke_style is not None and hasattr(item, "stroke_style"):
        item.stroke_style = stroke_style


def stroke_style_of(pen: QPen) -> StrokeStyle | None:
    """The ``StrokeStyle`` a pen draws with — None for a pen that draws nothing or
    with a dash pattern no ``StrokeStyle`` names."""
    style = pen.style()
    for candidate in StrokeStyle:
        if candidate.to_qt_pen_style() == style:
            return candidate
    return None


def paints_sprite(item: Any) -> bool:
    """Whether ``item``'s picture is a sprite and not its brush and pen — the item
    says so itself (``GardenItemMixin.paints_sprite``)."""
    return bool(getattr(item, "paints_sprite", False))


def saved_stroke_width(value: object) -> float | None:
    """A stroke width read from a file, if it is one the app could have written: a
    finite number not below ``MIN_STROKE_WIDTH`` — else None. Never raises."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        width = float(value)
    except OverflowError:  # an integer of 400 digits
        return None
    return width if math.isfinite(width) and width >= MIN_STROKE_WIDTH else None


def saved_stroke_colour(value: object) -> QColor | None:
    """A stroke colour read from a file, if it is a colour: a string Qt can read
    (``#aarrggbb``, ``#rrggbb``, a colour name) — else None. Never raises. A fully
    transparent colour IS one: the panel's colour dialog offers the alpha channel."""
    if not isinstance(value, str):
        return None
    colour = QColor(value)
    return colour if colour.isValid() else None


def fill_brush(item: Any, colour: QColor) -> QBrush:
    """The brush that paints ``colour`` in ``item``'s OWN pattern — the
    ``fill_pattern`` it states (plain for an item that states none). What
    ``style_gaps`` expects of an item whose ``fill_color`` is ``colour``."""
    pattern = getattr(item, "fill_pattern", None) or FillPattern.SOLID
    return create_pattern_brush(pattern, QColor(colour))


def adopt_pen(item: Any, pen: QPen) -> None:
    """Give ``item`` the pen — and say so in its stroke attributes.

    Two cases set the pen and leave the attributes alone: a pen that draws
    nothing (``NoPen`` states no stroke), and an item whose picture is a sprite
    (``paints_sprite`` — see the module docstring).
    """
    item.setPen(QPen(pen))
    if (pen.style() == Qt.PenStyle.NoPen or paints_sprite(item)
            or not hasattr(item, "stroke_color")):
        return
    item.stroke_color = QColor(pen.color())
    item.stroke_width = pen.widthF()
    style = stroke_style_of(pen)
    if style is not None and hasattr(item, "stroke_style"):
        item.stroke_style = style


def style_gaps(item: Any) -> list[str]:
    """Where ``item``'s style attributes do NOT describe its live brush and pen —
    [] when they are in step. An attribute that is None states nothing and is
    not held against anything; a pen that draws nothing is not held against the
    stroke attributes; and an item that paints a sprite (``paints_sprite``) is
    not judged at all: neither its brush nor its pen is its picture."""
    gaps: list[str] = []
    if paints_sprite(item):
        return gaps
    pen = item.pen()
    if pen.style() != Qt.PenStyle.NoPen:
        colour = getattr(item, "stroke_color", None)
        if colour is not None and QColor(colour) != pen.color():
            gaps.append(f"stroke_color {QColor(colour).name(QColor.NameFormat.HexArgb)} "
                        f"!= pen {pen.color().name(QColor.NameFormat.HexArgb)}")
        width = getattr(item, "stroke_width", None)
        if width is not None and abs(float(width) - pen.widthF()) > 1e-9:
            gaps.append(f"stroke_width {width} != pen {pen.widthF()}")
        style = getattr(item, "stroke_style", None)
        if style is not None and style.to_qt_pen_style() != pen.style():
            gaps.append(f"stroke_style {style.name} != pen {pen.style().name}")
    colour = getattr(item, "fill_color", None)
    pattern = getattr(item, "fill_pattern", None)
    brush = item.brush()
    if colour is not None and pattern is not None and brush.style() != Qt.BrushStyle.NoBrush:
        expected = create_pattern_brush(pattern, QColor(colour))
        if not _same_brush(brush, expected):
            gaps.append(f"fill {pattern.name} {QColor(colour).name(QColor.NameFormat.HexArgb)} "
                        f"is not the brush ({brush.style().name}, "
                        f"{brush.color().name(QColor.NameFormat.HexArgb)})")
    return gaps


def _same_brush(first: QBrush, second: QBrush) -> bool:
    """Two brushes paint the same: style and transform, and the colour of a plain
    one or the PIXELS of a textured one (``QBrush.__eq__`` compares cache keys —
    the same texture made twice is two keys). Two plain brushes that are both
    fully transparent paint the same — nothing — whatever their colours: a line
    states its type's fill, ``#00808080`` for a wall, and paints with
    ``#00000000``."""
    if first.style() != second.style() or first.transform() != second.transform():
        return False
    if first.style() == Qt.BrushStyle.TexturePattern:
        return bool(first.textureImage() == second.textureImage())
    mine, theirs = first.color(), second.color()
    return bool(mine == theirs or (mine.alpha() == 0 and theirs.alpha() == 0))
