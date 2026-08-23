"""Per-object stacking order within a layer (issue #338).

Pure, Qt-free core logic for "Bring to Front / Bring Forward / Send Backward
/ Send to Back". Operates on a single layer's bottom-to-top list of
:class:`StackEntry` (never on ``QGraphicsItem`` directly) so it can be
unit-tested without ``qtbot`` or any Qt runtime.

Concepts
--------
- A **rank** (``stack_order`` on the Qt side) is a sparse integer sort key;
  this module never invents ranks, it only reorders a list.
- A **block** is the set of selected items plus the children (in the same
  layer) of any selected plant-parent — bed + its plants move together.
- **Normalization** enforces the derive-only clamp: a child (plant → bed,
  ROOF_RIDGE → owner polygon) always renders immediately above its parent,
  regardless of where the raw arrange step would otherwise have put it. This
  is why "Send to Back" on a lone plant stops just above its bed instead of
  actually reaching the bottom of the layer.

See ``docs/09-architecture-decisions/`` ADR-043 and
``docs/08-crosscutting-concepts/`` section 8.25 for the full design.
"""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

# Spacing between successive ranks. Large enough that inserting a new item
# between two existing ones (rank arithmetic, not used in this module) never
# needs immediate renumbering in practice.
STACK_STEP = 1024


class ArrangeMode(Enum):
    """The four user-facing arrange gestures."""

    BRING_TO_FRONT = "bring_to_front"
    BRING_FORWARD = "bring_forward"
    SEND_BACKWARD = "send_backward"
    SEND_TO_BACK = "send_to_back"


class ArrangeOutcome(Enum):
    """Result of an :func:`arrange` call, for status messages / refusals."""

    CHANGED = "changed"
    ALREADY_AT_FRONT = "already_at_front"
    ALREADY_AT_BACK = "already_at_back"
    NO_OVERLAP_ABOVE = "no_overlap_above"
    NO_OVERLAP_BELOW = "no_overlap_below"
    NOTHING_SELECTED = "nothing_selected"


@dataclass(frozen=True)
class StackEntry:
    """One item's position in a single layer's bottom-to-top stack.

    Attributes:
        item_id: The item's unique identifier.
        parent_id: The id of this item's plant-parent bed (for a plant) or
            owner polygon (for a ROOF_RIDGE), or ``None``. Only meaningful
            when that parent is itself present in the same order list — a
            parent that lives in a different layer (or isn't in the list at
            all) is simply ignored by :func:`normalize_order`.
        rect: Scene bounding box as ``(x, y, width, height)``.
    """

    item_id: UUID
    parent_id: UUID | None
    rect: tuple[float, float, float, float]


def _rects_intersect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    """True when bounding boxes *a* and *b* overlap with positive area.

    Edges that merely touch (zero-area overlap) do NOT count as
    intersecting — two objects placed exactly edge-to-edge are not "in
    front of" each other for FORWARD/BACKWARD stepping purposes. This is a
    deliberate, documented choice (either convention is defensible; this
    one avoids surprising jumps when objects are snapped edge-to-edge).
    """
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def normalize_order(order: list[StackEntry]) -> list[StackEntry]:
    """Move every child to immediately above its parent; otherwise stable.

    ``order`` is bottom-to-top. An entry is a "child" only when its
    ``parent_id`` names another entry that is present in ``order`` (a
    ``parent_id`` pointing outside the list, or ``None``, leaves the entry
    exactly where it is — it sorts as a normal top-level entry). Children of
    the same parent keep their relative order. Idempotent: normalizing an
    already-normalized list returns an equal list.
    """
    ids_present = {entry.item_id for entry in order}

    children_by_parent: dict[UUID, list[StackEntry]] = {}
    non_children: list[StackEntry] = []
    for entry in order:
        parent_id = entry.parent_id
        if parent_id is not None and parent_id != entry.item_id and parent_id in ids_present:
            children_by_parent.setdefault(parent_id, []).append(entry)
        else:
            non_children.append(entry)

    result: list[StackEntry] = []
    for entry in non_children:
        result.append(entry)
        result.extend(children_by_parent.get(entry.item_id, []))
    return result


def expand_block(order: list[StackEntry], selected_ids: set[UUID]) -> set[UUID]:
    """Return *selected_ids* plus the children (present in *order*) of any
    selected parent — the set of ids that must move together as one block.

    Ids in *selected_ids* that aren't present in *order* at all are dropped
    silently (they belong to a different layer, or don't exist).
    """
    ids_present = {entry.item_id for entry in order}
    selected = {item_id for item_id in selected_ids if item_id in ids_present}
    block = set(selected)
    for entry in order:
        if entry.parent_id is not None and entry.parent_id in selected:
            block.add(entry.item_id)
    return block


def _find_overlap(
    candidates: list[StackEntry], block: list[StackEntry]
) -> StackEntry | None:
    """First entry in *candidates* whose rect intersects any block member's."""
    for entry in candidates:
        if any(_rects_intersect(entry.rect, member.rect) for member in block):
            return entry
    return None


def _move_block(
    order: list[StackEntry],
    block_ids: set[UUID],
    target_id: UUID,
    *,
    above_target: bool,
) -> list[StackEntry]:
    """Return *order* with the block (contiguous, relative order kept)
    reinserted immediately above (or below) *target_id*."""
    block = [entry for entry in order if entry.item_id in block_ids]
    others = [entry for entry in order if entry.item_id not in block_ids]
    target_pos = next(i for i, entry in enumerate(others) if entry.item_id == target_id)
    insert_pos = target_pos + 1 if above_target else target_pos
    return others[:insert_pos] + block + others[insert_pos:]


def _finish(
    candidate: list[StackEntry],
    normalized_input: list[StackEntry],
    no_op_outcome: ArrangeOutcome,
) -> tuple[list[StackEntry] | None, ArrangeOutcome]:
    """Normalize *candidate* and compare against the (already-normalized)
    input to decide whether anything actually changed.

    Comparing AFTER normalization (rather than before) is what makes the
    plant/ROOF_RIDGE clamp visible as a proper no-op: e.g. sending a lone
    plant to the back of its layer produces a raw candidate with the plant
    below its bed, but normalizing snaps it right back above the bed — so if
    that's the only difference, the net result equals the input and this
    correctly reports "already at back" instead of a phantom change.
    """
    final = normalize_order(candidate)
    if final == normalized_input:
        return None, no_op_outcome
    return final, ArrangeOutcome.CHANGED


def arrange(
    order: list[StackEntry],
    selected_ids: set[UUID],
    mode: ArrangeMode,
) -> tuple[list[StackEntry] | None, ArrangeOutcome]:
    """Arrange the block of *selected_ids* within one layer's *order*.

    Args:
        order: The layer's full bottom-to-top list (need not already be
            normalized — this function normalizes it first).
        selected_ids: The user's selection (only ids present in *order*
            matter; the block also includes their plant-parent children).
        mode: Which of the four gestures to perform.

    Returns:
        ``(new_order, ArrangeOutcome.CHANGED)`` with the new, normalized,
        bottom-to-top order, or ``(None, reason)`` when nothing changes —
        empty/foreign selection, already at the front/back (including the
        derive-only clamp collapsing the move to a no-op), or no overlapping
        object to step past.
    """
    normalized_input = normalize_order(order)

    block_ids = expand_block(normalized_input, selected_ids)
    if not block_ids:
        return None, ArrangeOutcome.NOTHING_SELECTED

    block = [entry for entry in normalized_input if entry.item_id in block_ids]
    others = [entry for entry in normalized_input if entry.item_id not in block_ids]

    if mode is ArrangeMode.BRING_TO_FRONT:
        candidate = others + block
        return _finish(candidate, normalized_input, ArrangeOutcome.ALREADY_AT_FRONT)

    if mode is ArrangeMode.SEND_TO_BACK:
        candidate = block + others
        return _finish(candidate, normalized_input, ArrangeOutcome.ALREADY_AT_BACK)

    block_indices = [
        i for i, entry in enumerate(normalized_input) if entry.item_id in block_ids
    ]
    topmost = max(block_indices)
    bottommost = min(block_indices)

    if mode is ArrangeMode.BRING_FORWARD:
        if topmost == len(normalized_input) - 1:
            return None, ArrangeOutcome.ALREADY_AT_FRONT
        target = _find_overlap(normalized_input[topmost + 1 :], block)
        if target is None:
            return None, ArrangeOutcome.NO_OVERLAP_ABOVE
        candidate = _move_block(normalized_input, block_ids, target.item_id, above_target=True)
        return _finish(candidate, normalized_input, ArrangeOutcome.ALREADY_AT_FRONT)

    if mode is ArrangeMode.SEND_BACKWARD:
        if bottommost == 0:
            return None, ArrangeOutcome.ALREADY_AT_BACK
        candidates = list(reversed(normalized_input[:bottommost]))
        target = _find_overlap(candidates, block)
        if target is None:
            return None, ArrangeOutcome.NO_OVERLAP_BELOW
        candidate = _move_block(normalized_input, block_ids, target.item_id, above_target=False)
        return _finish(candidate, normalized_input, ArrangeOutcome.ALREADY_AT_BACK)

    raise AssertionError(f"Unhandled ArrangeMode: {mode!r}")
