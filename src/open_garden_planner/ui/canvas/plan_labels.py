"""The scene's label pass: object labels painted after every item (§8.9.15, #793).

A label item (``items.halo_text.PlanLabelItem``) is a child of its object and
paints nothing in the item pass, where a later-drawn object would cover it.
``CanvasScene.drawForeground`` calls ``LabelPass.paint`` instead, once all
items are painted. The view paints through that hook and so does
``scene.render()``, so an export shows the labels the canvas shows.

Which labels have room is decided by ``core.label_layout`` in device pixels,
over every label of the scene. That is a walk of the scene, so it is not taken
for a paint: ``LabelPass`` keeps each viewport's layout until the scene, the
zoom or the view's blockers change.

A bed's succession badge is painted in the same pass, for the same reason
(the plants of the bed were drawn over it), and under the labels (#836).

Something that is not a label can take room too: the key of the sun map lies
over the plan's corner, and an hour's label half under it reads as part of it.
Such a thing is a *blocker* — a rectangle no label may touch. A scene item
states one with ``plan_label_blocker()`` (the key in a picture of the plan); a
view states the ones it draws over its viewport with
``CanvasScene.set_label_blockers`` (the key on the canvas).
"""

from __future__ import annotations

import math
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainter, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QWidget

from open_garden_planner.core.label_layout import LabelCandidate, badge_has_room, place_labels
from open_garden_planner.ui.canvas.items.garden_item import SuccessionBadgeItem
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
from open_garden_planner.ui.canvas.items.handle_geometry import selection_frame_rect

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene

    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

ShownLabel = tuple[PlanLabelItem, QTransform, QRectF]
ShownBadge = tuple[SuccessionBadgeItem, QTransform, QRectF]
_Item = TypeVar("_Item", PlanLabelItem, SuccessionBadgeItem)


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

    Taken fresh at every call: the canvas paints from ``LabelPass``, which
    keeps the answer.
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


def succession_badges_shown(scene: QGraphicsScene, world: QTransform) -> list[ShownBadge]:
    """The succession badges a paint of ``scene`` with the transform ``world`` shows.

    Each entry is the badge, its device transform and the device rect it is
    painted in. A badge is shown where it has room on its bed
    (``badge_has_room``): the bed's outline and the badge, both in device
    pixels, so the answer is the same on the canvas at any zoom and in an
    export at any resolution.
    """
    no_contents = QGraphicsItem.GraphicsItemFlag.ItemHasNoContents
    shown: list[ShownBadge] = []
    for item in scene.items():
        if not isinstance(item, SuccessionBadgeItem) or not item.isVisible():
            continue
        if item.flags() & no_contents:          # the minimap's way of blanking it
            continue
        device = item.deviceTransform(world)
        box = device.mapRect(item.boundingRect())
        if box.isEmpty():
            continue
        owner = item.parentItem()
        if owner is not None:
            frame = owner.deviceTransform(world).mapRect(selection_frame_rect(owner))
            # With its margin: from the bed's corner to the badge's far corner.
            bounds = item.boundingRect()
            reach = device.mapRect(QRectF(0.0, bounds.top(), bounds.right(), -bounds.top()))
            if not badge_has_room(reach.width(), reach.height(), frame.width(), frame.height()):
                continue
        shown.append((item, device, box))
    return shown


@dataclass(frozen=True)
class _KeptLayout:
    """What one viewport shows of the plan's labels, and what it was taken from."""

    revision: int                               # the scene's paint revision
    scale: tuple[float, float, float, float]    # the paint transform, less its translation
    origin: QPointF                             # ... and its translation
    blocked: tuple[QRectF, ...]                 # what the view stated no label may touch
    labels: list[ShownLabel]
    badges: list[ShownBadge]
    boxes: dict[int, QRectF]                    # the labels by identity (``_repaint_what_changed``)


class LabelPass:
    """The scene's label pass: paints the labels that have room, above everything.

    Which labels have room is decided over every label of the scene, so it is
    not decided for a paint. Each viewport's layout is KEPT and taken again
    only when what it was taken from has changed:

    - the scene (``CanvasScene.paint_revision``: an edit, a rename, a
      selection, a label hidden or shown — the label items say so themselves,
      ``halo_text.note_label_changed``);
    - the zoom (the paint transform's scale: a label keeps its size on screen
      while the objects under it change theirs);
    - what the view stated no label may touch (``set_label_blockers``).

    A pan is none of these. Which labels have room does not depend on where
    the plan lies in the viewport, so the kept layout is painted moved by the
    pan — unless the view stated a blocker, which stays where it is on the
    viewport while the labels move under it.

    A picture of the plan (an export, the minimap, the Agent API's render) is
    laid out for itself and kept by nobody: it has its own transform and is
    painted once.

    ``layouts`` counts the layouts taken for viewports (§8.10.10).
    """

    def __init__(self) -> None:
        # By the viewport itself, held weakly: a layout goes with its widget
        # (``CanvasScene._label_blockers`` has the reasons).
        self._kept: weakref.WeakKeyDictionary[QWidget, _KeptLayout] = weakref.WeakKeyDictionary()
        self.layouts = 0

    def clear(self) -> None:
        """Forget every kept layout: the items they name are being destroyed."""
        self._kept.clear()

    @property
    def viewports(self) -> int:
        """For how many viewports a layout is kept right now."""
        return len(self._kept)

    def paint(self, scene: CanvasScene, painter: QPainter, rect: QRectF) -> None:
        """Draw the badges and the labels that have room into ``rect`` (scene
        coordinates). The badges first: a name lies over a badge, never under."""
        world = painter.worldTransform()
        exposed = world.mapRect(rect)
        viewport = painter.device()
        if not isinstance(viewport, QWidget):
            _draw(painter, succession_badges_shown(scene, world), exposed, _paint_badge)
            _draw(painter, plan_labels_shown(scene, world), exposed, _paint_label)
            return
        kept = self._layout_for(scene, viewport, world, exposed)
        moved = QPointF(world.dx(), world.dy()) - kept.origin
        _draw(painter, kept.badges, exposed, _paint_badge, moved)
        _draw(painter, kept.labels, exposed, _paint_label, moved)

    def _layout_for(
        self, scene: CanvasScene, viewport: QWidget, world: QTransform, exposed: QRectF
    ) -> _KeptLayout:
        blocked = scene.label_blockers(viewport)
        scale = (world.m11(), world.m12(), world.m21(), world.m22())
        origin = QPointF(world.dx(), world.dy())
        kept = self._kept.get(viewport)
        if (
            kept is not None
            and kept.revision == scene.paint_revision
            and kept.scale == scale
            and kept.blocked == blocked
            and (not blocked or kept.origin == origin)
        ):
            return kept
        labels = plan_labels_shown(scene, world, blocked)
        self.layouts += 1
        new = _KeptLayout(
            scene.paint_revision, scale, origin, blocked, labels,
            succession_badges_shown(scene, world),
            {id(item): box for item, _device, box in labels},
        )
        if kept is not None:
            _repaint_what_changed(viewport, kept, new, exposed)
        self._kept[viewport] = new
        return new


def _repaint_what_changed(
    viewport: QWidget, old: _KeptLayout, new: _KeptLayout, exposed: QRectF
) -> None:
    """Ask for the pixels of the labels that gained or lost their room.

    Such a label may lie outside the region being repainted: an object
    dragged away frees its neighbour's label, and Qt repaints the object, not
    the neighbour. Only those labels are asked for, and none when the paint
    covers the viewport anyway — a zoom step, which changes the choice at
    every step, used to be painted twice for this.
    """
    # The exposed rectangle went to scene coordinates and back: it is the
    # viewport's to within rounding (measured 9e-16 px short of it).
    if exposed.adjusted(-0.5, -0.5, 0.5, 0.5).contains(QRectF(viewport.rect())):
        return
    if old.scale != new.scale:
        if old.boxes.keys() != new.boxes.keys():
            viewport.update()
        return
    moved = new.origin - old.origin
    for label in old.boxes.keys() ^ new.boxes.keys():
        box = new.boxes[label] if label in new.boxes else old.boxes[label].translated(moved)
        if not exposed.contains(box):
            viewport.update(box.toAlignedRect())


def _paint_badge(item: SuccessionBadgeItem, painter: QPainter) -> None:
    item.paint_badge(painter)


def _paint_label(item: PlanLabelItem, painter: QPainter) -> None:
    item.paint_text(painter)


def _draw(
    painter: QPainter,
    shown: Sequence[tuple[_Item, QTransform, QRectF]],
    exposed: QRectF,
    paint: Callable[[_Item, QPainter], None],
    moved: QPointF | None = None,
) -> None:
    """Paint the entries of ``shown`` that reach into ``exposed`` (device
    pixels), each ``moved`` from where it was laid out (a pan since then)."""
    if moved is not None and moved.isNull():
        moved = None
    seen = exposed if moved is None else exposed.translated(-moved)
    for item, device, box in shown:
        # An item destroyed since the layout (and not through the scene, which
        # would have said so) is passed over, not painted from a dead wrapper.
        if not box.intersects(seen) or sip.isdeleted(item):
            continue
        painter.save()
        if moved is not None:
            device = device * QTransform.fromTranslate(moved.x(), moved.y())
        painter.setWorldTransform(device)
        painter.setOpacity(item.effectiveOpacity())
        paint(item, painter)
        painter.restore()
