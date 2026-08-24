"""The one apply path for per-object stacking-order changes (issue #338).

Every surface that performs "Bring to Front / Bring Forward / Send Backward
/ Send to Back" — the Edit menu, each item's context menu, the Properties
panel's Arrange buttons, and the Agent API's ``arrange_object`` tool — funnels
through :func:`build_arrange_command`. Before this module existed each of
those surfaces would have needed its own copy of "group the selection by
layer, ask ``core.stacking.arrange`` what changed, build the command" — and
copies drift (see ``ui/canvas/geometry_apply.py`` for the shape of that
lesson on the resize/rotate side). There is exactly one seam here; if you
find yourself reaching for a second one, use this one instead.

:func:`build_arrange_command` is Qt-aware (it reads live ``QGraphicsItem``
state — layer membership, scene bounding rects, the scene's derived stacking
order) but pushes all the actual reordering logic down into the Qt-free
:mod:`open_garden_planner.core.stacking` module, so the algorithm itself
stays unit-testable without ``qtbot``.
"""

from collections.abc import Iterable
from uuid import UUID

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.core import stacking
from open_garden_planner.core.commands import ArrangeItemsCommand
from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome

# Source strings only -- NOT translated here. A module-level dict is built
# once at import time, so calling QCoreApplication.translate() here would
# freeze every description at whatever translator state exists at import
# (typically none), permanently in English regardless of the active UI
# language (CLAUDE.md i18n rule: module-level dicts use QT_TR_NOOP, translate
# at the point of use). See build_arrange_command() below for the translate
# call.
_DESCRIPTIONS: dict[ArrangeMode, str] = {
    ArrangeMode.BRING_TO_FRONT: QT_TR_NOOP("Bring {count} item(s) to front"),
    ArrangeMode.BRING_FORWARD: QT_TR_NOOP("Bring {count} item(s) forward"),
    ArrangeMode.SEND_BACKWARD: QT_TR_NOOP("Send {count} item(s) backward"),
    ArrangeMode.SEND_TO_BACK: QT_TR_NOOP("Send {count} item(s) to back"),
}


def build_arrange_command(
    scene: QGraphicsScene,
    items: Iterable[QGraphicsItem],
    mode: ArrangeMode,
) -> tuple[ArrangeItemsCommand | None, ArrangeOutcome]:
    """Build the undoable command for arranging *items* within their layer(s).

    Journal pins and items without a resolvable layer are dropped first (they
    never take part in stacking). The remaining items are grouped by layer;
    each layer's current stacking order is fetched from the scene
    (:meth:`CanvasScene._stack_entries`, the ONE place that builds
    ``StackEntry`` objects from live items) and handed to
    :func:`core.stacking.arrange`, which decides what changes for that layer
    alone. A selection spanning several layers therefore still becomes one
    undo step — each layer's block is arranged within its own layer only.

    Args:
        scene: The canvas scene.
        items: Candidate items (typically the current selection).
        mode: Which of the four arrange gestures to perform.

    Returns:
        ``(command, ArrangeOutcome.CHANGED)`` when at least one layer's order
        actually changed — the caller still needs to
        ``command_manager.execute(command)``. Otherwise ``(None, outcome)``,
        where *outcome* is ``NOTHING_SELECTED`` when no eligible item remains
        after filtering, or the first affected layer's non-CHANGED outcome
        (already at front/back, or no overlapping object to step past).
    """
    from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

    eligible = []
    for item in items:
        if isinstance(item, JournalPinItem):
            continue
        layer_id = getattr(item, "layer_id", None)
        if layer_id is None:
            continue
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[attr-defined]
        # A locked layer is dropped here too (not just refused by name in the
        # agent's arrange_object tool) so every GUI arrange surface -- Edit
        # menu, context menu, Properties panel -- agrees with the agent: none
        # of them can reorder an item the user locked against editing (issue
        # #338 review round 3, P2).
        if layer is None or layer.locked:
            continue
        eligible.append(item)
    if not eligible:
        return None, ArrangeOutcome.NOTHING_SELECTED

    by_layer: dict[UUID, list[QGraphicsItem]] = {}
    for item in eligible:
        by_layer.setdefault(item.layer_id, []).append(item)  # type: ignore[attr-defined]

    new_orders: dict[UUID, list[QGraphicsItem]] = {}
    outcome = ArrangeOutcome.NOTHING_SELECTED  # sentinel: "not set yet"
    for layer_id, layer_items in by_layer.items():
        entries = scene._stack_entries(layer_id)  # type: ignore[attr-defined]
        items_by_id = {
            scene._stack_identity(item): item  # type: ignore[attr-defined]
            for item in scene._normalized_layer_order(layer_id)  # type: ignore[attr-defined]
        }
        selected_ids = {scene._stack_identity(item) for item in layer_items}  # type: ignore[attr-defined]

        new_order, layer_outcome = stacking.arrange(entries, selected_ids, mode)
        if new_order is None:
            # Every eligible item is present in `entries` (they came from
            # this same layer), so `layer_outcome` here is never
            # NOTHING_SELECTED — the sentinel check below only ever fires
            # once, for the first affected layer.
            if outcome is ArrangeOutcome.NOTHING_SELECTED:
                outcome = layer_outcome
            continue
        new_orders[layer_id] = [items_by_id[entry.item_id] for entry in new_order]

    if not new_orders:
        return None, outcome

    description = QCoreApplication.translate("Commands", _DESCRIPTIONS[mode]).format(
        count=len(eligible)
    )
    command = ArrangeItemsCommand(scene, new_orders, description)
    return command, ArrangeOutcome.CHANGED
