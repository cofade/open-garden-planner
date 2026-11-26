"""One place that rebuilds a `QGraphicsScene`'s item index from live items.

Qt's BSP index updates lazily. A batch that reparents or removes many items at
once (a document replacement, a group or an ungroup) is exactly when a stale
search-tree entry can outlive its item; the next paint or hit test then walks a
freed pointer (PF-CAN-76, #1031). The linear index is built from Qt's live
top-level inventory and discards the outgoing BSP tree, so wrapping the batch
and restoring the previous method afterwards leaves the scene with an index
that names live items only.

Callers must keep this scope to the reparent/remove work itself. A z-order
renumber or an arrange query reads the scene's stacking order, which the
linear index does not report; restoring the index before those reads preserves
their result (the #1031 review finding).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from PyQt6.QtWidgets import QGraphicsScene


@contextlib.contextmanager
def rebuilt_scene_index(scene: QGraphicsScene) -> Iterator[None]:
    """Use the linear index for the block, then restore the scene's own index.

    A scene already on ``NoIndex`` is left alone: its caller owns that choice
    and restoring it would override it. The ``finally`` restores the previous
    method even when the block raises, so a failed command cannot leave the
    scene without its spatial index.
    """
    previous = scene.itemIndexMethod()
    if previous == QGraphicsScene.ItemIndexMethod.NoIndex:
        yield
        return
    scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
    try:
        yield
    finally:
        scene.setItemIndexMethod(previous)
