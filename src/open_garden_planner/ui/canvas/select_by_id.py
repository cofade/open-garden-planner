"""THE path from item ids to the canvas selection (Phase 17 L1.8, ADR-060).

There is ONE selection in the app — the canvas scene's — and ONE way to select an
object on the plan BY ITS ID, ``select_by_ids``. It is what every list that names
objects uses to show one: the Diagnostics, Canopy and Guilds panels
(``ui/panels/diagnostics_panel.ObjectNavigator``) and the 3D view's list of what it
cannot show (``Workspace.select_item``). A click in the 3D view adds only the ray's
rule — the first selectable item along it (``ui/view3d/selection_bridge.apply_click``)
— and is built from the same three pieces:

- ``item_with_id``: which canvas item carries an id (None: none any more — a stale
  row of a list, a pick from before the plan changed);
- ``click_target``: what selecting an item selects — the item, or the outermost
  group it is in (Qt hands a group member's selection to its group as well);
- ``is_selectable``: whether it can be selected at all — shown, enabled and carrying
  Qt's selectable flag, which the scene takes from every item of a LOCKED layer.

So a row of a panel, a row of the 3D list and a click in 3D cannot disagree about
which object an id means, what selecting it selects or whether a locked layer
lets it be selected.

No engine, no state, no strings: functions on the scene.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

_SELECTABLE = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def item_with_id(scene: QGraphicsScene, item_id: str) -> QGraphicsItem | None:
    """The canvas item carrying ``item_id`` (None: there is none any more)."""
    if not item_id:
        return None
    for item in scene.items():
        if str(getattr(item, "item_id", "")) == item_id:
            return item
    return None


def click_target(item: QGraphicsItem) -> QGraphicsItem:
    """What selecting ``item`` selects: the item — or the group it is in, the
    outermost one (a group handles its members' clicks, however deeply nested)."""
    target = item
    while True:
        group = target.group()
        if group is None:
            return target
        target = group


def is_selectable(item: QGraphicsItem) -> bool:
    """True when ``item`` can be selected: shown, enabled and carrying Qt's selectable
    flag — which the scene takes from every item of a locked layer."""
    return bool(item.isVisible() and item.isEnabled() and item.flags() & _SELECTABLE)


def replace_selection(scene: QGraphicsScene, items: Sequence[QGraphicsItem]) -> None:
    """Make ``items`` the canvas selection. When they already are, nothing happens:
    no ``selectionChanged`` — so no panel refresh and no pass of the 3D view."""
    wanted = {id(item): item for item in items}
    if {id(item) for item in scene.selectedItems()} == set(wanted):
        return
    scene.clearSelection()
    for item in wanted.values():
        item.setSelected(True)


def select_by_ids(scene: QGraphicsScene, item_ids: Iterable[str]) -> list[QGraphicsItem]:
    """Select the objects ``item_ids`` name — THE select-by-id path (module docstring).

    Each id's click target, once; the selection becomes the selectable ones (an
    object on a locked layer is named but not selected). Ids that name nothing are
    skipped; when NONE names anything the selection is left as it is (a stale row
    of a list). Returns the click targets the ids name, selectable or not, in the
    ids' order — a caller scrolls the plan to the first."""
    targets: dict[int, QGraphicsItem] = {}
    for item_id in item_ids:
        item = item_with_id(scene, str(item_id))
        if item is not None:
            target = click_target(item)
            targets.setdefault(id(target), target)
    found = list(targets.values())
    if found:
        replace_selection(scene, [target for target in found if is_selectable(target)])
    return found
