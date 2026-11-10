"""The scene's label pass: object labels painted after every item (§8.9.15, #793).

A label item (``items.halo_text.PlanLabelItem``) is a child of its object and
paints nothing in the item pass, where a later-drawn object would cover it.
``CanvasScene.drawForeground`` calls ``paint_plan_labels`` instead, once all
items are painted. The view paints through that hook and so does
``scene.render()``, so an export shows the labels the canvas shows.

Which labels have room is decided by ``core.label_layout`` in device pixels.

Something that is not a label can take room too: the key of the sun map lies
over the plan's corner, and an hour's label half under it reads as part of it.
Such a thing is a *blocker* — a rectangle no label may touch. A scene item
states one with ``plan_label_blocker()`` (the key in a picture of the plan); a
view states the ones it draws over its viewport with
``CanvasScene.set_label_blockers`` (the key on the canvas).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QWidget

from open_garden_planner.core.label_layout import LabelCandidate, place_labels
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
from open_garden_planner.ui.canvas.items.handle_geometry import selection_frame_rect

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene

ShownLabel = tuple[PlanLabelItem, QTransform, QRectF]


def plan_labels_shown(
    scene: QGraphicsScene, world: QTransform, blocked: Sequence[QRectF] = ()
) -> list[ShownLabel]:
    """The object labels a paint of ``scene`` with the transform ``world`` shows.

    ``world`` maps scene to device pixels (a view's ``viewportTransform()``, an
    export painter's world transform). Each entry is the label, its device
    transform and the device rect it is painted in. The layout looks at every
    visible label of the scene, never at a repainted region alone: the repaint
    of a small region has to choose the same labels as a full one.

    ``blocked`` are device rectangles no label may touch (module docstring);
    the scene's own blockers — visible items with ``plan_label_blocker()`` —
    are added to them.
    """
    # The minimap suppresses screen-space items with this flag instead of
    # hiding them; what it suppresses must not reappear through this pass.
    no_contents = QGraphicsItem.GraphicsItemFlag.ItemHasNoContents
    labels: list[ShownLabel | None] = []
    candidates: list[LabelCandidate] = []

    def block(rect: QRectF) -> None:
        # placed before every label, and never painted by this pass
        candidates.append(LabelCandidate(
            rect=(rect.left(), rect.top(), rect.right(), rect.bottom()),
            owner_extent_px=math.inf, pinned=True,
        ))
        labels.append(None)

    for rect in blocked:
        block(rect)
    for item in scene.items():
        blocker = getattr(item, "plan_label_blocker", None)
        if blocker is not None and item.isVisible():
            block(item.deviceTransform(world).mapRect(blocker()))
            continue
        if not isinstance(item, PlanLabelItem) or not item.isVisible():
            continue
        if item.flags() & no_contents:
            continue
        device = item.deviceTransform(world)
        box = device.mapRect(item.boundingRect())
        owner = item.parentItem()
        extent, pinned = item.free_extent_px, False
        if owner is not None:
            frame = owner.deviceTransform(world).mapRect(selection_frame_rect(owner))
            extent = max(frame.width(), frame.height())
            pinned = owner.isSelected()
        candidates.append(
            LabelCandidate(
                rect=(box.left(), box.top(), box.right(), box.bottom()),
                owner_extent_px=extent,
                pinned=pinned,
                rank=item.rank,
                tie=item.text() if owner is not None else _free_label_tie(item),
                owner=id(owner) if owner is not None else None,
            )
        )
        labels.append((item, device, box))
    if not candidates:
        return []
    placed = (labels[index] for index in place_labels(candidates))
    return [label for label in placed if label is not None]


def _free_label_tie(item: PlanLabelItem) -> str:
    """What orders two ownerless labels of one weight: text, then place. Their
    order among the scene's items is no property of the plan."""
    place = item.scenePos()
    return f"{item.text()}@{place.x():012.2f},{place.y():012.2f}"


def paint_plan_labels(
    scene: QGraphicsScene,
    painter: QPainter,
    rect: QRectF,
    last_shown: dict[int, frozenset[int]],
) -> None:
    """Draw the object labels that have room, above everything painted so far.

    ``last_shown`` is the caller's memory of which labels each viewport showed
    at its last paint. A label that gained or lost its room may lie outside the
    region just repainted (an object dragged away frees its neighbour's
    label): when the choice changed on a viewport, that viewport is repainted
    once. A render into a picture (an export, the minimap) is never tracked.
    """
    world = painter.worldTransform()
    viewport = painter.device()
    blockers = getattr(scene, "label_blockers", None)
    blocked = blockers(viewport) if callable(blockers) and isinstance(viewport, QWidget) else ()
    shown = plan_labels_shown(scene, world, blocked)
    exposed = world.mapRect(rect)
    for item, device, box in shown:
        if not box.intersects(exposed):
            continue
        painter.save()
        painter.setWorldTransform(device)
        painter.setOpacity(item.effectiveOpacity())
        item.paint_text(painter)
        painter.restore()

    if isinstance(viewport, QWidget):
        chosen = frozenset(id(item) for item, _device, _box in shown)
        key = id(viewport)
        if last_shown.get(key, chosen) != chosen:
            viewport.update()
        last_shown[key] = chosen
