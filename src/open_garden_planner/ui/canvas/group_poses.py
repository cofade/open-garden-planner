"""Represent a detached group member using the geometry its serializer writes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.angles import is_zero_angle

from .items.arc_item import ArcItem
from .items.bezier_item import BezierItem
from .items.construction_item import ConstructionCircleItem, ConstructionLineItem
from .items.group_item import GroupItem
from .items.handle_geometry import selection_frame_rect
from .items.journal_pin_item import JournalPinItem
from .items.reference_point_item import ReferencePointItem
from .items.resize_handle import RotationHandleMixin
from .items.text_item import TextItem


def document_members(group: QGraphicsItem) -> list[QGraphicsItem]:
    return [child for child in group.childItems() if hasattr(child, "item_id")]


def _is_rigid(matrix: QTransform, handedness: int = 1) -> bool:
    x, y = matrix.m11(), matrix.m12()
    return (
        matrix.isAffine()
        and all(math.isfinite(v) for v in (x, y, matrix.dx(), matrix.dy()))
        and math.isclose(math.hypot(x, y), 1.0, abs_tol=1e-9)
        and math.isclose(matrix.m21(), -handedness * y, abs_tol=1e-9)
        and math.isclose(matrix.m22(), handedness * x, abs_tol=1e-9)
    )


def can_ungroup(group: QGraphicsItem) -> bool:
    """Each direct member must be representable in the scene frame."""
    return (
        group.parentItem() is None
        and not group.transformations()
        and _is_rigid(group.transform())
        and _is_rigid(group.sceneTransform())
        and all(
            isinstance(item, (
                RotationHandleMixin, ArcItem, BezierItem, ConstructionCircleItem,
                ConstructionLineItem, JournalPinItem,
            ))
            and _has_rigid_member_pose(item)
            for item in document_members(group)
        )
    )


def _has_rigid_member_pose(item: QGraphicsItem) -> bool:
    handedness = -1 if isinstance(item, TextItem) else 1
    return (
        not item.transformations()
        and _is_rigid(item.transform(), handedness)
        and _is_rigid(item.sceneTransform(), handedness)
    )


@dataclass(frozen=True, slots=True)
class MemberPose:
    pos: QPointF
    base: QTransform
    pivot: QPointF
    rotation: float
    recorded_angle: float
    geometry: tuple[Any, ...] | QLineF | None = None
    group_pivot_initialized: bool | None = None

    @classmethod
    def capture(cls, item: QGraphicsItem) -> MemberPose:
        geometry: tuple[Any, ...] | QLineF | None = None
        if isinstance(item, (ArcItem, BezierItem)):
            geometry = item._capture_geometry()
        elif isinstance(item, ConstructionLineItem):
            geometry = item.line()
        recorded = item.rotation_angle if isinstance(item, RotationHandleMixin) else 0.0
        group_pivot = item._pivot_initialized if isinstance(item, GroupItem) else None
        return cls(item.pos(), item.transform(), item.transformOriginPoint(), item.rotation(),
                   recorded, geometry, group_pivot)

    def detached(self, item: QGraphicsItem) -> MemberPose:
        world = item.sceneTransform()
        scene_angle = math.degrees(math.atan2(world.m12(), world.m11()))
        pos = world.map(QPointF())
        if isinstance(item, ArcItem):
            assert isinstance(self.geometry, tuple)
            _, cx, cy, radius, start, span, tx, ty = self.geometry
            centre = world.map(QPointF(cx, cy))
            through = world.map(QPointF(tx, ty))
            arc = ("arc", centre.x(), centre.y(), radius, start + scene_angle,
                   span, through.x(), through.y())
            return MemberPose(QPointF(), QTransform(), QPointF(), 0.0, 0.0, arc)
        if isinstance(item, BezierItem):
            assert isinstance(self.geometry, tuple)
            _, *point_sets = self.geometry
            bezier = ("bezier", *(
                tuple((p.x(), p.y()) for p in (world.map(QPointF(x, y)) for x, y in points))
                for points in point_sets
            ))
            return MemberPose(QPointF(), QTransform(), QPointF(), 0.0, 0.0, bezier)
        if isinstance(item, ConstructionLineItem):
            line = item.line()
            mapped = QLineF(world.map(line.p1()), world.map(line.p2()))
            return MemberPose(QPointF(), QTransform(), QPointF(), 0.0, 0.0, mapped)
        if isinstance(item, ConstructionCircleItem):
            centre = item.rect().center()
            return MemberPose(world.map(centre) - centre, QTransform(), QPointF(), 0.0, 0.0)
        if isinstance(item, JournalPinItem) or (
            isinstance(item, ReferencePointItem)
            and bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        ):
            return MemberPose(pos, QTransform(), QPointF(), 0.0, 0.0)

        text = isinstance(item, TextItem)
        base = QTransform.fromScale(1.0, -1.0) if text else QTransform()
        angle = -scene_angle if text else scene_angle
        if is_zero_angle(angle):
            angle = 0.0
        pivot = self.pivot
        group_pivot = self.group_pivot_initialized
        if group_pivot is False and angle != 0.0:
            pivot = selection_frame_rect(item).center()
            group_pivot = True
        elif group_pivot is None and is_zero_angle(self.rotation) and angle != 0.0:
            rect = getattr(item, "rect", item.boundingRect)
            pivot = rect().center()
        # Qt rotates about the local pivot first, then applies the base matrix.
        # Solve the translation from the mapped local origin.
        offset = base.map(pivot - QTransform().rotate(angle).map(pivot))
        return MemberPose(pos - offset, base, pivot, angle, angle,
                          group_pivot_initialized=group_pivot)

    def apply(self, item: QGraphicsItem) -> None:
        item.setTransform(self.base)
        item.setTransformOriginPoint(self.pivot)
        if isinstance(item, RotationHandleMixin):
            item.rotation_angle = self.recorded_angle
        if isinstance(item, GroupItem) and self.group_pivot_initialized is not None:
            item._pivot_initialized = self.group_pivot_initialized
        item.setRotation(self.rotation)
        if isinstance(item, ReferencePointItem):
            item.set_pos_exact(self.pos)
        else:
            item.setPos(self.pos)
        if isinstance(item, (ArcItem, BezierItem)):
            item._restore_geometry(self.geometry)
        elif isinstance(item, ConstructionLineItem):
            assert isinstance(self.geometry, QLineF)
            item.setLine(self.geometry)
