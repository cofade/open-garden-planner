"""Between the canvas's selection and the 3D view's (Phase 17 L1.8, ADR-060). Engine-free.

There is ONE selection in the app: the canvas scene's (``QGraphicsScene``'s own —
``setSelected`` / ``clearSelection`` / ``selectionChanged``, which the property
panels, the status bar and every tool already follow). The 3D view has none of its
own. This module is the two translations between them:

- **3D → 2D** (``apply_click``): a click in the 3D view named a record's item id —
  and what lies behind it along the ray. It becomes exactly what a click on the
  canvas at that item would have become, by the canvas's own means. The rules were
  MEASURED on the canvas (``tests/integration/test_view3d_selection_bridge.py``
  clicks it with real mouse events and holds this module to the answer):

  ==============================  ==============================================
  a plain click on an item        that item alone is selected
  Ctrl+click / Shift+click        the item is toggled; the rest stays
  a click on nothing              the selection is cleared — also with Ctrl or
                                  Shift held (the canvas does the same)
  an item on a LOCKED layer       is not selectable: the click falls THROUGH it to
                                  the first selectable item behind it — and when
                                  there is none: a plain or Shift click clears, a
                                  Ctrl click changes NOTHING (Qt's own Ctrl rule:
                                  an unselectable item under a Ctrl click keeps
                                  the selection — measured, fix round 1)
  an item on a hidden layer       has no record, so the 3D view cannot name it
  an item inside a group          the group is selected (the outermost one)
  ==============================  ==============================================

  ONE measured difference is kept on purpose: on the canvas Shift+click THROUGH a
  locked item is a plain click on what is behind it (the select tool's Shift looks
  only at the item right under the cursor, and Qt's own toggle key is Ctrl). That
  contradicts the canvas's own rule; here Shift toggles what the click reaches,
  as Ctrl does. The test pins both answers.

- **2D → 3D** (``selected_record_ids``): the ids whose records get a ring — the
  selected items themselves, and for a selected group every item inside it (a
  group has no record of its own; its members have).

Which item an id names, what selecting it selects and whether it can be selected
are not this module's: they are the app's ONE select-by-id path,
``ui/canvas/select_by_id.py`` (the Diagnostics, Canopy and Guilds panels and the 3D
view's problems list select through it too). This module adds the ray's rule.

No Qt Quick import, no engine call, no state: functions on the scene.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.ui.canvas.select_by_id import (
    click_target,
    is_selectable,
    item_with_id,
    replace_selection,
)

__all__ = [
    "apply_click",
    "click_target",
    "hit_ids",
    "is_selectable",
    "item_with_id",
    "selectable_target",
    "selected_record_ids",
    "sole_selected",
]


def hit_ids(hit: Any) -> tuple[str, ...]:
    """The item ids along a pick's ray, nearest first, each once: the hit's own and
    those of what lies ``behind`` it (``Quick3DHost.pick``). ``()`` for no hit."""
    if hit is None:
        return ()
    ordered = [str(getattr(hit, "item_id", "") or "")]
    ordered += [str(getattr(further, "item_id", "") or "") for further in getattr(hit, "behind", ())]
    return tuple(dict.fromkeys(item_id for item_id in ordered if item_id))


def selectable_target(scene: QGraphicsScene, item_ids: Iterable[str]) -> QGraphicsItem | None:
    """The canvas item a click along ``item_ids`` (nearest first) selects: the click
    target of the first id whose target is selectable. None: the click meets nothing
    it can select."""
    seen: set[int] = set()
    for item_id in item_ids:
        item = item_with_id(scene, item_id)
        if item is None:
            continue
        target = click_target(item)
        if id(target) in seen:
            continue
        seen.add(id(target))
        if is_selectable(target):
            return target
    return None


_CTRL: Final = Qt.KeyboardModifier.ControlModifier
_TOGGLE: Final = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def apply_click(scene: QGraphicsScene, item_ids: Iterable[str],
                modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
                ) -> QGraphicsItem | None:
    """Do to the canvas selection what a canvas click along ``item_ids`` with
    ``modifiers`` held does (module docstring's table): Ctrl or Shift toggles; a click
    that names only items it cannot select changes nothing with Ctrl held and clears
    otherwise. Returns the item the click landed on, or None for nothing."""
    ids = tuple(item_ids)
    toggle = bool(modifiers & _TOGGLE)
    target = selectable_target(scene, ids)
    if target is None:
        if modifiers & _CTRL and any(item_with_id(scene, item_id) is not None for item_id in ids):
            return None  # Qt's Ctrl click on an unselectable item keeps the selection
        replace_selection(scene, ())
        return None
    if toggle:
        target.setSelected(not target.isSelected())
        return target
    replace_selection(scene, (target,))
    return target


def _members(item: QGraphicsItem) -> Iterator[QGraphicsItem]:
    children = item.childItems()
    if not children:
        return
    for child in children:
        yield child
        yield from _members(child)


def selected_record_ids(scene: QGraphicsScene) -> frozenset[str]:
    """The ids the 3D view shows as selected: every selected item's, and — for a
    selected group — its members' (a group covers no ground itself). Ids only: which
    of them have a record is the pipeline's to say."""
    ids: set[str] = set()
    for item in scene.selectedItems():
        for candidate in (item, *_members(item)):
            item_id = getattr(candidate, "item_id", None)
            if item_id is not None and getattr(candidate, "object_type", None) is not None:
                ids.add(str(item_id))
    return frozenset(ids)


def sole_selected(scene: QGraphicsScene) -> QGraphicsItem | None:
    """The one selected item when exactly one is selected, else None."""
    selected = scene.selectedItems()
    return selected[0] if len(selected) == 1 else None
