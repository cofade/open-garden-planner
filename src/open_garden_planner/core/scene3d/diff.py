"""What changed between two snapshots (Phase 17 L1.1, ADR-054).

``diff(old, new)`` compares two ``{item_id: Record}`` mappings, both ordered
bottom-to-top (paint order), and names the minimal work for the engine.

Semantics — exact, and pinned for all eight combinations by
``tests/unit/test_scene3d_contract.py``:

- ``added``: ids in ``new`` only, in ``new``'s order. ``removed``: ids in
  ``old`` only, in ``old``'s order. Neither is ever also listed below.
- For an id in both, three INDEPENDENT comparisons: it is listed under
  ``geometry`` when its geometry part differs, under ``transform`` when its
  transform differs, under ``material`` when its material differs — under each
  aspect that changed and under no other. A resize that moves the item's centre
  is therefore ``geometry`` + ``transform``; a height change is ``geometry``
  alone; a recolour is ``material`` alone.
- Each list is in ``new``'s order.
- ``reordered`` is True when the ids present in both snapshots come in another
  relative order. It is not an engine call (the depth buffer sorts solids) and
  never a geometry change; the ground bake paints flat surfaces in this order.
- A rename, a re-parent, a selection or a hover changes none of the above.

Comparisons use the signatures as a fast path and the values as the proof
(``Record.same_geometry`` — a hash collision must not hide an edit).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .record import Record


@dataclass(frozen=True, slots=True)
class SceneDiff:
    """The difference of two snapshots, as item ids (module docstring)."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    transform: tuple[str, ...] = ()
    material: tuple[str, ...] = ()
    geometry: tuple[str, ...] = ()
    reordered: bool = False

    @property
    def touches_sink(self) -> bool:
        """True when an engine sink has work to do (any of the five lists)."""
        return bool(self.added or self.removed or self.transform or self.material
                    or self.geometry)

    @property
    def is_empty(self) -> bool:
        """True when the two snapshots describe the same scene in the same order."""
        return not (self.touches_sink or self.reordered)

    @property
    def changed(self) -> tuple[str, ...]:
        """Every surviving id with any change, once each (geometry first, then
        transform, then material — each group in ``new``'s order)."""
        return tuple(dict.fromkeys((*self.geometry, *self.transform, *self.material)))


_EMPTY = SceneDiff()


def diff(old: Mapping[str, Record], new: Mapping[str, Record]) -> SceneDiff:
    """Compare two snapshots; see the module docstring for the exact semantics."""
    if old is new:
        return _EMPTY
    added: list[str] = []
    geometry: list[str] = []
    transform: list[str] = []
    material: list[str] = []
    survivors: list[str] = []
    for item_id, record in new.items():
        previous = old.get(item_id)
        if previous is None:
            added.append(item_id)
            continue
        survivors.append(item_id)
        if previous is record:
            continue
        if not previous.same_geometry(record):
            geometry.append(item_id)
        if not previous.same_transform(record):
            transform.append(item_id)
        if not previous.same_material(record):
            material.append(item_id)
    removed = [item_id for item_id in old if item_id not in new]
    if len(survivors) == len(old):  # nothing removed: old's survivor order is old itself
        reordered = survivors != list(old)
    else:
        reordered = survivors != [item_id for item_id in old if item_id in new]
    if not (added or removed or geometry or transform or material or reordered):
        return _EMPTY
    return SceneDiff(
        added=tuple(added),
        removed=tuple(removed),
        transform=tuple(transform),
        material=tuple(material),
        geometry=tuple(geometry),
        reordered=reordered,
    )
