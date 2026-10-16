"""One rule for copying a shape's *look* from a source item to its copy (issue #470).

An "item made from an item" (the offset tool and the mirror builder today) must
look like its source, and must *stay* that way across a save → reload round
trip. Two representations carry a shape's look and both must be copied together,
or the copy silently reverts to its object type's defaults:

* the **live** appearance — the ``QPen`` and ``QBrush`` the item paints with;
* the **serialized** appearance — ``fill_pattern`` / ``fill_color`` /
  ``stroke_color`` / ``stroke_width`` / ``stroke_style`` on
  :class:`~open_garden_planner.ui.canvas.items.garden_item.GardenItemMixin`.

Copying only the pen/brush (as the offset tool did for polygons) looked right
until the next save; copying only the attributes left the item painting its
type's defaults. :func:`copy_visual_style` copies both, once, so its callers
share one rule instead of re-deriving it (issues #441, #470).

Qt-touching but layer-neutral: callers live in ``core`` (the offset tool and
``mirror_geometry``), so this helper does too — it never imports ``ui``. Both
arguments are duck-typed shape items (``GardenItemMixin`` items), which mypy
cannot see through a bare ``QGraphicsItem``, hence ``Any``.

Chamfer, fillet and trim copies have the same defect and are deliberately NOT
routed here: they are owned by the in-flight L1 branch (#441). The mirror
polyline, circle, box and polygon builders all call this helper; the stroke-only
arc/bezier mirror builders set ``stroke_color``/``stroke_width`` by hand instead.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtGui import QBrush, QColor, QPen

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

