"""Split every eligible closed shape crossed by a two-point cutting line (#664).

The toolbar's Split tool is scene-wide: it takes two snapped points and cuts
every eligible closed shape that the drawn segment passes through along the
segment's infinite supporting axis. A shape the segment crosses end to end
becomes two (or more) pieces; a shape the segment clips is cut along the same
axis when both resulting pieces are large enough to keep. A segment that only
touches an outline (a corner, an edge, a tangent) is not a crossing. Every cut
of one gesture is one undo step.

The context menu's ``Split Along Line…`` keeps the same gesture scoped to the
clicked shape. ``Shift`` constrains the line to 45-degree steps; ``Esc``
cancels without mutating the scene.
"""

from __future__ import annotations

import contextlib
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsPolygonItem

from open_garden_planner.core.cad_geometry import snap_point_to_axis_step
from open_garden_planner.core.item_look import (
    adopt_rebuilt_type,
    copy_visual_style,
    paints_sprite,
)
from open_garden_planner.core.shape_split import (
    polygon_type_for_split,
    segment_crosses_item,
    split_item_into_local_polygons,
)
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType
from open_garden_planner.core.tools.preview_z import PREVIEW_Z_FILL, PREVIEW_Z_LINE

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


@dataclass
class _ShapeCut:
    """One source shape and its pieces, in the source's local frame."""

    source: QGraphicsItem
    polygons: list[QPolygonF]


@dataclass
class _CutPlan:
    """What one two-point gesture would do, before any item is created."""

    cuts: list[_ShapeCut] = field(default_factory=list)
    crossed: int = 0
    skipped: int = 0
    error: str | None = None


class SplitShapeTool(BaseTool):
    """Two snapped picks define a cutting line; every crossed shape is split."""

    tool_type = ToolType.SPLIT
    display_name = QCoreApplication.translate("SplitShapeTool", "Split along line")
    # Shift+S, not S: S is the main window's Snap to Grid action, and a second
    # window shortcut on the same key makes Qt fire neither (measured).
    shortcut = "Shift+S"
    cursor = Qt.CursorShape.CrossCursor
    accepts_typed_coordinates = False
    # Keep BaseTool's shared anchor snap: both picks and the preview use it.

    def _translated_name(self) -> str:
        return QCoreApplication.translate("SplitShapeTool", "Split along line")

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        #: When set, the gesture is scoped to this one source (context menu).
        #: ``None`` is the toolbar's scene-wide mode.
        self.source_id: UUID | None = None
        self._start: QPointF | None = None
        self._candidates: list[QGraphicsItem] = []
        self._refusal_cache: dict[QGraphicsItem, str | None] = {}
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_axis: QGraphicsLineItem | None = None
        self._preview_pieces: list[QGraphicsPolygonItem] = []
        self._scene = view._canvas_scene
        self._scene.document_replaced.connect(self.cancel)

    # ------------------------------------------------------------------
    # Starting and finishing the gesture
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Start a fresh gesture whenever the tool becomes active."""
        super().activate()
        self.cancel()
        self._view.set_status_message(
            QCoreApplication.translate(
                "SplitShapeTool", "Click the first point of the cutting line. Esc cancels."
            )
        )

    def prepare(self, source_id: UUID | None) -> None:
        """Scope the next cut to one shape, or clear the scope (``None``).

        The context menu passes the clicked shape; the toolbar and shortcut pass
        ``None`` so the line splits every eligible closed shape it crosses.
        """
        self.cancel()
        self.source_id = source_id

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Take the first or second cutting point."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        if self.source_id is not None and self._source() is None:
            self._view.set_status_message(
                QCoreApplication.translate(
                    "SplitShapeTool", "The shape to split is no longer available."
                )
            )
            self.cancel()
            self._view.set_active_tool(ToolType.SELECT)
            return True

        if self._start is None:
            self._start = QPointF(scene_pos)
            self._candidates = self._collect_candidates()
            self._refusal_cache.clear()
            self._show_line_preview(QPointF(scene_pos))
            self._view.set_status_message(
                QCoreApplication.translate(
                    "SplitShapeTool",
                    "Click the second point of the cutting line; "
                    "Shift constrains the angle. Esc cancels.",
                )
            )
            return True

        end = self._end(scene_pos, event)
        plan = self._plan_cut(self._start, end)
        if not plan.cuts:
            self._view.set_status_message(
                plan.error
                or QCoreApplication.translate(
                    "SplitShapeTool",
                    "The cutting line must cross a closed shape. "
                    "Choose another second point.",
                )
            )
            return True

        self._apply(plan)
        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Follow the cursor with the line and the live pieces."""
        if self._start is None:
            return True
        end = self._end(scene_pos, event)
        self._show_line_preview(end)
        self._show_piece_preview(end)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            self._view.set_status_message(
                QCoreApplication.translate("SplitShapeTool", "Split cancelled")
            )
            self._view.set_active_tool(ToolType.SELECT)
            return True
        return False

    def cancel(self) -> None:
        """Remove every preview and forget the armed source and gesture."""
        self._clear_previews()
        self._start = None
        self.source_id = None
        self._candidates = []
        self._refusal_cache.clear()

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _collect_candidates(self) -> list[QGraphicsItem]:
        """Every closed shape this gesture may cut, snapshotted at the first click.

        In scene-wide mode that is every visible polygon/rectangle/circle/ellipse
        including grouped children: a grouped child is still reported by the
        refusal check (with "ungroup first") instead of vanishing silently.
        """
        if self.source_id is not None:
            source = self._source()
            return [source] if source is not None else []

        from open_garden_planner.ui.canvas.items import (
            CircleItem,
            EllipseItem,
            PolygonItem,
            RectangleItem,
        )

        shape_types = (PolygonItem, RectangleItem, CircleItem, EllipseItem)
        return [
            item
            for item in self._scene.items()
            if isinstance(item, shape_types)
            and getattr(item, "item_id", None) is not None
            and item.isVisible()
        ]

    def _refusal_for(self, item: QGraphicsItem) -> str | None:
        """Cache the view's refusal reason for the life of one gesture."""
        if item not in self._refusal_cache:
            self._refusal_cache[item] = self._view.split_refusal_reason(item)
        return self._refusal_cache[item]

    def _plan_cut(self, start: QPointF, end: QPointF) -> _CutPlan:
        """Collect every crossed shape and its pieces without mutating anything."""
        from open_garden_planner.ui.canvas.items.polygon_item import (
            MAX_POLYGON_VERTICES,
        )

        plan = _CutPlan()
        first_reason: str | None = None
        vertex_error: str | None = None
        segment_bounds = QRectF(start, end).normalized().adjusted(-1, -1, 1, 1)

        for item in self._candidates:
            if item.scene() is not self._scene:
                continue
            if not item.sceneBoundingRect().intersects(segment_bounds):
                continue
            if not segment_crosses_item(item, start, end):
                continue
            plan.crossed += 1

            reason = self._refusal_for(item)
            if reason is not None:
                plan.skipped += 1
                first_reason = first_reason or reason
                continue

            local_polygons = split_item_into_local_polygons(item, start, end)
            if not local_polygons:
                plan.skipped += 1
                first_reason = first_reason or QCoreApplication.translate(
                    "SplitShapeTool",
                    "The cut would leave a piece too small to keep",
                )
                continue
            if any(
                polygon.count() > MAX_POLYGON_VERTICES for polygon in local_polygons
            ):
                vertex_error = QCoreApplication.translate(
                    "SplitShapeTool",
                    "A piece would have {count} vertices; the plan supports at "
                    "most {limit}. Choose a simpler cut.",
                ).format(
                    count=max(polygon.count() for polygon in local_polygons),
                    limit=MAX_POLYGON_VERTICES,
                )
                plan.skipped += 1
                continue

            plan.cuts.append(_ShapeCut(item, local_polygons))

        if not plan.cuts:
            if vertex_error is not None:
                plan.error = vertex_error
            elif plan.crossed and plan.skipped and first_reason is not None:
                plan.error = QCoreApplication.translate(
                    "SplitShapeTool", "Nothing was split: {reason}"
                ).format(reason=first_reason)
        return plan

    # ------------------------------------------------------------------
    # Applying
    # ------------------------------------------------------------------

    def _apply(self, plan: _CutPlan) -> None:
        """Create all pieces and replace every source in one undo step."""
        from open_garden_planner.core.commands import (
            Command,
            CompoundCommand,
            ReconcileBedMembershipCommand,
            SplitShapeCommand,
        )

        splits = [
            (
                cut.source,
                [
                    self._make_piece(cut.source, polygon)
                    for polygon in cut.polygons
                ],
            )
            for cut in plan.cuts
        ]
        commands: list[Command] = [
            SplitShapeCommand(self._scene, source, pieces)
            for source, pieces in splits
        ]
        # A bed with plants is splittable: re-home every linked plant to the
        # piece its standing point falls in, inside the SAME undo step (#664).
        # The command captures the links BEFORE the sources disappear.
        parent_ids: set[UUID] = set()
        for cut in plan.cuts:
            parent_id = getattr(cut.source, "item_id", None)
            if getattr(cut.source, "has_children", False) and parent_id is not None:
                parent_ids.add(parent_id)
        if parent_ids:
            commands.append(
                ReconcileBedMembershipCommand(
                    self._scene, focus_parents=parent_ids
                )
            )
        command = (
            commands[0]
            if len(commands) == 1
            else CompoundCommand(
                commands,
                (
                    commands[0].description
                    if len(plan.cuts) == 1
                    else QCoreApplication.translate(
                        "SplitShapeTool", "Split {count} shapes"
                    ).format(count=len(plan.cuts))
                ),
            )
        )

        scoped = self.source_id is not None
        pieces = [piece for _source, split_pieces in splits for piece in split_pieces]
        self._clear_previews()
        self._start = None
        self.source_id = None
        self._view.command_manager.execute(command)
        self._scene.clearSelection()
        for piece in pieces:
            piece.setSelected(True)

        if len(plan.cuts) == 1:
            message = QCoreApplication.translate(
                "SplitShapeTool", "Split the shape into {count} pieces"
            ).format(count=len(pieces))
        else:
            message = QCoreApplication.translate(
                "SplitShapeTool", "Split {shapes} shapes into {pieces} pieces"
            ).format(shapes=len(plan.cuts), pieces=len(pieces))
        if plan.skipped == 1:
            message = QCoreApplication.translate(
                "SplitShapeTool", "{message}; 1 crossed object could not be split"
            ).format(message=message)
        elif plan.skipped:
            message = QCoreApplication.translate(
                "SplitShapeTool", "{message}; {count} crossed objects could not be split"
            ).format(message=message, count=plan.skipped)
        self._view.set_status_message(message)

        if scoped:
            # The context-menu action is a one-shot edit; return to Select.
            self._view.set_active_tool(ToolType.SELECT)

    def _make_piece(self, source: QGraphicsItem, polygon: QPolygonF) -> QGraphicsItem:
        """Build one unsaved piece that keeps the source's frame and look."""
        from open_garden_planner.ui.canvas.items import PolygonItem

        item = PolygonItem.from_polygon(QPolygonF(polygon))
        # Work in the source's local frame so the material keeps its
        # orientation and the source's rotation is reproduced exactly.
        item._apply_rotation(source.rotation())
        centre = item.transformOriginPoint()
        item.setPos(source.mapToScene(centre) - centre)
        source_type = getattr(source, "object_type", None)
        polygon_type = polygon_type_for_split(source_type)
        if polygon_type is not None:
            item.object_type = polygon_type
        item.name = getattr(source, "name", "")
        item.label_visible = getattr(source, "label_visible", True)
        item.area_label_visible = getattr(source, "area_label_visible", False)
        item.layer_id = getattr(source, "layer_id", None)
        item.stack_order = getattr(source, "stack_order", None)
        metadata = getattr(source, "metadata", None)
        if metadata:
            item.metadata.update(deepcopy(metadata))
        # The source's roof ridge leaves with the source; ``SplitShapeCommand``
        # builds every piece its own, so no piece may name the old one.
        item.metadata.pop("ridge_item_id", None)
        copy_visual_style(source, item)
        # A piece whose type had to change stands as tall as its source (the
        # 40 cm of a raised bed is a type default a garden bed lacks). A sprite
        # (the raised bed's wooden frame) cannot be drawn on a free-form
        # outline and its stored fill was never on screen, so such a piece
        # takes its new type's pattern (soil) instead of going flat brown; a
        # shape painted by its own brush keeps the pattern the user gave it.
        adopt_rebuilt_type(
            item, source_type, polygon_type, keep_fill=not paints_sprite(source)
        )
        item._setup_styling()
        return item

    # ------------------------------------------------------------------
    # Geometry and preview
    # ------------------------------------------------------------------

    def _source(self) -> QGraphicsItem | None:
        if self.source_id is None:
            return None
        return self._scene.find_item_by_id(self.source_id)

    def _end(self, point: QPointF, event: QMouseEvent) -> QPointF:
        if self._start is not None and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return snap_point_to_axis_step(self._start, point, 45)
        return QPointF(point)

    def _show_line_preview(self, end: QPointF) -> None:
        """Draw the segment, plus the supporting axis the cut actually uses.

        Only the drawn segment decides WHICH shapes are cut; the cut itself
        runs along the segment's infinite supporting axis, so the faint axis
        line shows how far the blades reach (#664 review).
        """
        if self._start is None:
            return
        if self._preview_line is None:
            self._preview_line = QGraphicsLineItem()
            pen = QPen(QColor(25, 120, 220), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._preview_line.setPen(pen)
            self._preview_line.setZValue(PREVIEW_Z_LINE)
            self._scene.addItem(self._preview_line)
        if self._preview_axis is None:
            self._preview_axis = QGraphicsLineItem()
            pen = QPen(QColor(25, 120, 220, 90), 1.0, Qt.PenStyle.DotLine)
            pen.setCosmetic(True)
            self._preview_axis.setPen(pen)
            self._preview_axis.setZValue(PREVIEW_Z_LINE)
            self._scene.addItem(self._preview_axis)
        self._preview_line.setLine(
            self._start.x(), self._start.y(), end.x(), end.y()
        )
        direction = end - self._start
        length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if length <= 1e-6:
            self._preview_axis.setLine(
                self._start.x(),
                self._start.y(),
                self._start.x(),
                self._start.y(),
            )
            return
        extent = self._scene.sceneRect().width() + self._scene.sceneRect().height()
        direction *= extent / length
        first = self._start - direction
        second = self._start + direction
        self._preview_axis.setLine(
            first.x(), first.y(), second.x(), second.y()
        )

    def _show_piece_preview(self, end: QPointF) -> None:
        if self.source_id is not None and self._source() is None:
            self._clear_previews()
            return
        if self._start is None:
            return
        plan = self._plan_cut(self._start, end)
        self._clear_piece_preview()
        for cut in plan.cuts:
            for polygon in cut.polygons:
                scene_polygon = cut.source.mapToScene(QPolygonF(polygon))
                preview = QGraphicsPolygonItem(scene_polygon)
                preview.setPen(
                    QPen(QColor(60, 130, 200), 1.2, Qt.PenStyle.DashLine)
                )
                preview.setBrush(QColor(60, 130, 200, 40))
                preview.setZValue(PREVIEW_Z_FILL)
                self._scene.addItem(preview)
                self._preview_pieces.append(preview)

    def _clear_piece_preview(self) -> None:
        for preview in self._preview_pieces:
            with contextlib.suppress(RuntimeError):
                if preview.scene() is not None:
                    self._scene.removeItem(preview)
        self._preview_pieces.clear()

    def _clear_previews(self) -> None:
        self._clear_piece_preview()
        for preview in (self._preview_line, self._preview_axis):
            if preview is not None:
                with contextlib.suppress(RuntimeError):
                    if preview.scene() is not None:
                        self._scene.removeItem(preview)
        self._preview_line = None
        self._preview_axis = None
