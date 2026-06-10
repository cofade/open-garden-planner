"""Mirror tool — reflect the selection across a user-defined axis (US-B4).

Workflow:
    1. Select one or more shapes, then activate the tool (``Shift+M``).
    2. Click the axis start point, then the axis end point. Hold **Shift**
       while picking the end to constrain the axis to 0/45/90°.
    3. A small modal asks **Copy** (default) or **Move**.
        - *Copy* adds reflected duplicates and keeps the originals.
        - *Move* replaces the originals with their reflections, preserving each
          item's identity so existing constraints stay bound.

Supported types are the drawing shapes (polyline, polygon, rectangle, ellipse,
circle, arc, bezier — plus rectangle/circle-based SVG furniture & plants).
Unsupported items in the selection are skipped with a status note. See
``core.mirror_geometry`` for the per-type reflection and ADR-026 for rationale.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsLineItem, QMessageBox

from open_garden_planner.core.cad_geometry import snap_point_to_axis_step
from open_garden_planner.core.mirror_geometry import build_mirrored_item

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from open_garden_planner.ui.canvas.canvas_view import CanvasView


_PREVIEW_COLOR = QColor(0, 100, 255)
_PREVIEW_WIDTH = 1.0
_MIN_AXIS_LENGTH = 1e-6  # cm — reject a zero-length axis (two identical clicks)


class MirrorTool(BaseTool):
    """Two-click axis mirror of the current selection (copy or move)."""

    tool_type = ToolType.MIRROR
    display_name = QCoreApplication.translate("MirrorTool", "Mirror")
    shortcut = "Shift+M"
    cursor = Qt.CursorShape.CrossCursor
    # The second click is a geometric axis endpoint; the Dist/Angle overlay
    # would imply it sets a polar offset, which it does not.
    accepts_typed_coordinates = False

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._axis_start: QPointF | None = None
        self._axis_end: QPointF | None = None
        self._sources: list[QGraphicsItem] = []
        self._preview_line: QGraphicsLineItem | None = None
        # Default chosen when the modal Copy/Move dialog is skipped (offscreen
        # / tests). Tests set this to drive Copy vs Move deterministically.
        self._copy_mode = True

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        super().activate()
        if not self._eligible_selection():
            self._status(
                QCoreApplication.translate(
                    "MirrorTool", "Select shapes to mirror first, then pick the axis"
                )
            )
        else:
            self._status(
                QCoreApplication.translate("MirrorTool", "Mirror: click axis start")
            )

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = self._view.snap_point(scene_pos)

        if self._axis_start is None:
            # Snapshot the selection now (the suppressed click can't deselect it).
            self._sources = self._collect_sources()
            if not self._sources:
                self._status(
                    QCoreApplication.translate(
                        "MirrorTool", "Select shapes to mirror first"
                    )
                )
                return True
            self._axis_start = QPointF(snapped)
            self._ensure_preview_line()
            self._status(
                QCoreApplication.translate(
                    "MirrorTool", "Click axis end (hold Shift for 45°)"
                )
            )
            return True

        end = self._constrained_end(snapped, event)
        if _distance(self._axis_start, end) < _MIN_AXIS_LENGTH:
            self._status(
                QCoreApplication.translate("MirrorTool", "Axis must have a length")
            )
            return True
        self._axis_end = end
        self._cleanup_preview()
        self._choose_mode_and_apply()
        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._axis_start is None:
            return False
        end = self._constrained_end(self._view.snap_point(scene_pos), event)
        self._update_preview_line(end)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._axis_start is not None:
            self.cancel()
            return True
        return False

    @property
    def last_point(self) -> QPointF | None:
        return QPointF(self._axis_start) if self._axis_start is not None else None

    def _constrained_end(self, point: QPointF, event: QMouseEvent) -> QPointF:
        if self._axis_start is not None and (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            return snap_point_to_axis_step(self._axis_start, point, 45.0)
        return QPointF(point)

    # ------------------------------------------------------------------
    # Copy / Move + apply
    # ------------------------------------------------------------------

    def _choose_mode_and_apply(self) -> None:
        if not _is_interactive_platform():
            self._perform_mirror(self._copy_mode)
            return
        copy = self._ask_copy_or_move()
        if copy is None:  # cancelled
            self._reset_axis()
            return
        self._perform_mirror(copy)

    def _ask_copy_or_move(self) -> bool | None:
        """Modal chooser. Returns True=copy, False=move, None=cancel."""
        box = QMessageBox(self._view)
        box.setWindowTitle(QCoreApplication.translate("MirrorTool", "Mirror"))
        box.setText(
            QCoreApplication.translate(
                "MirrorTool", "Mirror the selection across the axis?"
            )
        )
        copy_btn = box.addButton(
            QCoreApplication.translate("MirrorTool", "Copy"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        move_btn = box.addButton(
            QCoreApplication.translate("MirrorTool", "Move"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(copy_btn)
        box.exec()
        # Hand focus back so the next mouse_move reaches the view (see FilletTool).
        if hasattr(self._view, "setFocus"):
            self._view.setFocus()
        clicked = box.clickedButton()
        if clicked is copy_btn:
            return True
        if clicked is move_btn:
            return False
        return None

    def _perform_mirror(self, copy: bool) -> None:
        """Build + commit the reflected items (the testable core)."""
        if self._axis_start is None or self._axis_end is None or not self._sources:
            self._reset_axis()
            return
        a, b = self._axis_start, self._axis_end

        mirrored: list[QGraphicsItem] = []
        kept_sources: list[QGraphicsItem] = []
        skipped = 0
        had_constraints = False
        for src in self._sources:
            new_item = build_mirrored_item(src, a, b)
            if new_item is None:
                skipped += 1
                continue
            if not copy:
                _stamp_identity(new_item, src)
            mirrored.append(new_item)
            kept_sources.append(src)
            if self._source_has_constraints(src):
                had_constraints = True

        if not mirrored:
            self._status(
                QCoreApplication.translate(
                    "MirrorTool", "Nothing mirrored ({skipped} unsupported)"
                ).format(skipped=skipped)
            )
            self._reset_axis()
            return

        if copy:
            self._remap_parent_links(kept_sources, mirrored)

        # Keep the reflected geometry on the canvas — the axis can place a
        # reflection partly/fully outside. Shifts the whole mirrored set back
        # together (preserving its arrangement), like array/drag clamping.
        if hasattr(self._view, "_clamp_items_to_canvas"):
            self._view._clamp_items_to_canvas(mirrored)

        from open_garden_planner.core.commands import MirrorItemsCommand

        cmd = MirrorItemsCommand(self._view.scene(), kept_sources, mirrored, copy)
        self._view.command_manager.execute(cmd)

        scene = self._view.scene()
        for item in scene.selectedItems():
            item.setSelected(False)
        for item in mirrored:
            item.setSelected(True)

        self._announce(len(mirrored), skipped, copy, had_constraints)
        self._reset_axis()

    def _announce(
        self, count: int, skipped: int, copy: bool, had_constraints: bool
    ) -> None:
        msg = QCoreApplication.translate(
            "MirrorTool", "Mirrored {count} item(s)"
        ).format(count=count)
        if skipped:
            msg += " " + QCoreApplication.translate(
                "MirrorTool", "({skipped} unsupported skipped)"
            ).format(skipped=skipped)
        if copy and had_constraints:
            msg += " " + QCoreApplication.translate(
                "MirrorTool", "— copies are unconstrained"
            )
        self._status(msg)

    # ------------------------------------------------------------------
    # Identity / relationships
    # ------------------------------------------------------------------

    def _source_has_constraints(self, src: QGraphicsItem) -> bool:
        graph = getattr(self._view.scene(), "constraint_graph", None)
        if graph is None or not hasattr(src, "item_id"):
            return False
        return bool(graph.get_item_constraints(src.item_id))

    def _remap_parent_links(
        self, sources: list[QGraphicsItem], mirrored: list[QGraphicsItem]
    ) -> None:
        """Re-point bed→plant links onto the mirrored copies (paste-style)."""
        from open_garden_planner.core.commands import ensure_z_above_parent
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        old_to_new: dict[object, QGraphicsItem] = {}
        for src, new_item in zip(sources, mirrored, strict=True):
            if hasattr(src, "item_id"):
                old_to_new[src.item_id] = new_item

        for src, new_item in zip(sources, mirrored, strict=True):
            if not (
                isinstance(src, GardenItemMixin)
                and isinstance(new_item, GardenItemMixin)
            ):
                continue
            parent_id = src.parent_bed_id
            if parent_id is not None and parent_id in old_to_new:
                parent = old_to_new[parent_id]
                if isinstance(parent, GardenItemMixin):
                    new_item.parent_bed_id = parent.item_id
                    parent.add_child_id(new_item.item_id)
                    ensure_z_above_parent(new_item, parent)

    # ------------------------------------------------------------------
    # Selection snapshot
    # ------------------------------------------------------------------

    def _eligible_selection(self) -> list[QGraphicsItem]:
        return [i for i in self._view.scene().selectedItems() if _is_mirrorable(i)]

    def _collect_sources(self) -> list[QGraphicsItem]:
        """Eligible selection plus the children of any selected bed.

        Beds are mirrored together with their plants so the children move/copy
        with the bed rather than being left behind (matching copy/duplicate).
        """
        from open_garden_planner.core.object_types import is_bed_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        sources = self._eligible_selection()
        scene = self._view.scene()
        if not hasattr(scene, "find_item_by_id"):
            return sources
        seen = {i.item_id for i in sources if hasattr(i, "item_id")}
        for item in list(sources):
            if not (isinstance(item, GardenItemMixin) and is_bed_type(item.object_type)):
                continue
            for child_id in item.child_item_ids:
                if child_id in seen:
                    continue
                child = scene.find_item_by_id(child_id)
                if child is not None and _is_mirrorable(child):
                    sources.append(child)
                    seen.add(child_id)
        return sources

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------

    def _ensure_preview_line(self) -> None:
        if self._preview_line is not None:
            return
        self._preview_line = QGraphicsLineItem()
        pen = QPen(_PREVIEW_COLOR, _PREVIEW_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self._preview_line.setPen(pen)
        self._view.scene().addItem(self._preview_line)

    def _update_preview_line(self, cursor: QPointF) -> None:
        if self._preview_line is None or self._axis_start is None:
            return
        self._preview_line.setLine(
            self._axis_start.x(), self._axis_start.y(), cursor.x(), cursor.y()
        )

    def _cleanup_preview(self) -> None:
        if self._preview_line is not None:
            scene = self._view.scene()
            if self._preview_line.scene() is scene:
                scene.removeItem(self._preview_line)
            self._preview_line = None

    # ------------------------------------------------------------------
    # State + lifecycle
    # ------------------------------------------------------------------

    def _reset_axis(self) -> None:
        self._cleanup_preview()
        self._axis_start = None
        self._axis_end = None
        self._sources = []

    def cancel(self) -> None:
        self._reset_axis()

    def deactivate(self) -> None:
        self._reset_axis()
        super().deactivate()

    def _status(self, message: str) -> None:
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(message)


def _is_mirrorable(item: QGraphicsItem) -> bool:
    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        BezierItem,
        CircleItem,
        EllipseItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )

    return isinstance(
        item,
        (
            PolylineItem,
            PolygonItem,
            CircleItem,
            RectangleItem,
            EllipseItem,
            ArcItem,
            BezierItem,
        ),
    )


def _stamp_identity(new_item: QGraphicsItem, source: QGraphicsItem) -> None:
    """Carry the source's identity onto its replacement (Move mode).

    Preserving ``item_id`` keeps constraints (keyed by item id) and bed
    parent/child links bound to the reflected geometry.
    """
    if hasattr(source, "_item_id"):
        new_item._item_id = source._item_id
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    if isinstance(source, GardenItemMixin) and isinstance(new_item, GardenItemMixin):
        new_item.parent_bed_id = source.parent_bed_id
        for cid in source.child_item_ids:
            new_item.add_child_id(cid)


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(b.x() - a.x(), b.y() - a.y())


def _is_interactive_platform() -> bool:
    """False under the offscreen Qt platform used by CI/tests (skip modals)."""
    app = QApplication.instance()
    return app is not None and app.platformName() != "offscreen"
