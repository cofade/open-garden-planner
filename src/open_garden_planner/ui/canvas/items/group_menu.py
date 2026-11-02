"""Group / Ungroup context-menu entries, shared by every groupable item (#674).

Grouping used to be reachable only by ``Ctrl+G``. The inverse direction was
already discoverable (a group's own "Ungroup" entry), which left the feature
one-sided and undiscoverable. Both entries now come from this one seam so that
every item's menu asks the *same* question of the *same* selection:

===============  ============================================
Selection        Entries offered
===============  ============================================
0 or 1 object    —
2+, no groups    **Group**
exactly 1 group  **Ungroup**
groups + other   **Group** + **Ungroup**
2+ groups        **Group** + **Ungroup**
===============  ============================================

Dispatch goes through the canvas view's own Ctrl+G / Ctrl+Shift+G methods, so
the menu cannot be stricter than the shortcut and there is exactly one
implementation of each action. A ``SmartSymbolItem`` is a group by class but
never an Ungroup target (its generated members are not user geometry).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QMenu

from .group_item import groupable_selection, ungroupable_groups


@dataclass(frozen=True)
class GroupMenuActions:
    """The actions a menu actually offered; ``None`` means the row is absent."""

    group_action: QAction | None = None
    ungroup_action: QAction | None = None

    @property
    def offered(self) -> bool:
        """Whether this menu row has anything in it (callers add separators)."""
        return self.group_action is not None or self.ungroup_action is not None

    def dispatch(self, action: QAction | None, scene: QGraphicsScene | None) -> bool:
        """Run the chosen entry on the whole selection through the view.

        Returns False for an action this builder did not create (Qt's
        ``exec`` returns None on dismissal), so callers can fall through to
        their remaining entries.
        """
        if action is None:
            return False
        if action is self.group_action:
            method = "group_selected"
        elif action is self.ungroup_action:
            method = "ungroup_selected"
        else:
            return False
        views = scene.views() if scene is not None else []
        view = views[0] if views else None
        handler = getattr(view, method, None)
        if not callable(handler):
            return False
        handler()
        return True


def normalize_context_menu_selection(item: QGraphicsItem) -> None:
    """Make an unselected right-clicked item the selection.

    Shared by the item types that use ``GardenItemMixin`` and the two curve
    items that do not; see ``GardenItemMixin.normalize_context_menu_selection``.
    """
    scene = item.scene()
    if scene is None or item.isSelected():
        return
    scene.clearSelection()
    item.setSelected(True)


def build_group_context_menu(
    menu: QMenu,
    item: QGraphicsItem,
    *,
    allow_ungroup: bool = True,
) -> GroupMenuActions:
    """Append Group / Ungroup according to the scene's current selection.

    ``allow_ungroup=False`` is for a smart symbol's own menu: it may still be
    grouped with other objects, but never dissolved.
    """
    scene = item.scene()
    selected = groupable_selection(list(scene.selectedItems())) if scene else []

    group_action = None
    ungroup_action = None
    if len(selected) >= 2:
        group_action = menu.addAction(
            QCoreApplication.translate("GardenItem", "Group")
        )
    if allow_ungroup and ungroupable_groups(selected):
        ungroup_action = menu.addAction(
            QCoreApplication.translate("GardenItem", "Ungroup")
        )
    return GroupMenuActions(group_action, ungroup_action)
