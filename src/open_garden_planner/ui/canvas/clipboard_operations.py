"""ClipboardOperations: one responsibility extracted from CanvasView."""
from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.object_types import (
    is_plant_parent_type,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

_log = logging.getLogger(__name__)


def _strip_item_ids(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip item_id from a serialized item dict so deserialization mints new UUIDs."""
    copy_d = data.copy()
    copy_d.pop("item_id", None)
    if "children" in copy_d:
        copy_d["children"] = [_strip_item_ids(child) for child in copy_d["children"]]
    return copy_d


def _offset_item_dict(data: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
    """Apply an offset (dx, dy) to all supported geometry coordinates in an item dict."""
    copy_d = data.copy()
    if "position" in copy_d and isinstance(copy_d["position"], dict):
        pos_copy = dict(copy_d["position"])
        if "x" in pos_copy:
            pos_copy["x"] += dx
        if "y" in pos_copy:
            pos_copy["y"] += dy
        copy_d["position"] = pos_copy
    if "x" in copy_d:
        copy_d["x"] += dx
    if "y" in copy_d:
        copy_d["y"] += dy
    if "center_x" in copy_d:
        copy_d["center_x"] += dx
    if "center_y" in copy_d:
        copy_d["center_y"] += dy
    if "target_x" in copy_d:
        copy_d["target_x"] += dx
    if "target_y" in copy_d:
        copy_d["target_y"] += dy
    if "through_x" in copy_d:
        copy_d["through_x"] += dx
    if "through_y" in copy_d:
        copy_d["through_y"] += dy
    if "x1" in copy_d:
        copy_d["x1"] += dx
    if "y1" in copy_d:
        copy_d["y1"] += dy
    if "x2" in copy_d:
        copy_d["x2"] += dx
    if "y2" in copy_d:
        copy_d["y2"] += dy
    if "points" in copy_d:
        copy_d["points"] = [
            {"x": p["x"] + dx, "y": p["y"] + dy}
            for p in copy_d["points"]
        ]
    for key in ("anchors", "handles_in", "handles_out"):
        if key in copy_d:
            copy_d[key] = [
                {"x": p["x"] + dx, "y": p["y"] + dy}
                for p in copy_d[key]
            ]
    return copy_d


class ClipboardOperations:
    """Uses the original host for state, translation context and command ownership."""

    def __init__(self, host: CanvasView) -> None:
        self._host = host

    def copy_selected(self) -> None:
        """Copy selected items to clipboard (auto-includes plant-parent children)."""
        host = self._host
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        selected = list(cast("CanvasScene", host.scene()).selectedItems())
        if not selected:
            return

        # Auto-include children of selected plant-parents (beds/containers/trellises)
        selected_ids = {
            item.item_id for item in selected if isinstance(item, GardenItemMixin)
        }
        for item in list(selected):
            if isinstance(item, GardenItemMixin) and is_plant_parent_type(
                item.object_type
            ):
                for child_id in item.child_item_ids:
                    if child_id not in selected_ids:
                        child = host._canvas_scene.find_item_by_id(child_id)
                        if child is not None:
                            selected.append(child)
                            selected_ids.add(child_id)

        # Sort bottom-to-top by current z before serializing so paste
        # recreates the same relative stacking order (issue #338) --
        # CreateItemsCommand adds items in list order, and each addItem
        # ranks a new item above whatever's already been added.
        selected.sort(key=lambda item: item.zValue())

        from open_garden_planner.ui.guild_copy import scene_guild_member_ids

        host._clipboard_guild_members = scene_guild_member_ids(cast("CanvasScene", host.scene()))
        # Serialize selected items
        host._clipboard = []
        for item in selected:
            obj_data = host._serialize_item(item)
            if obj_data:
                host._clipboard.append(obj_data)

        # Show status message
        if len(host._clipboard) > 0:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Copied {count} item(s)").format(count=len(host._clipboard))
            )


    def cut_selected(self) -> None:
        """Cut selected items (copy then delete)."""
        host = self._host
        selected = cast("CanvasScene", host.scene()).selectedItems()
        if not selected:
            return

        # Copy first
        host.copy_selected()

        # Then delete
        if host._clipboard:
            host._delete_selected_items()
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Cut {count} item(s)").format(count=len(host._clipboard))
            )


    def paste(self) -> None:
        """Paste items from clipboard."""
        item: QGraphicsItem | None
        host = self._host
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not host._clipboard:
            host.set_status_message(QCoreApplication.translate("CanvasView", "Nothing to paste"))
            return

        # Deselect all items
        for item in cast("CanvasScene", host.scene()).selectedItems():
            item.setSelected(False)

        # Create new items from clipboard
        pasted_items: list[QGraphicsItem] = []
        clipboard_data: list[dict[str, Any]] = []
        from open_garden_planner.ui.guild_copy import copy_guild_records

        records = copy_guild_records(cast("CanvasScene", host.scene()), host._clipboard, getattr(host, "_clipboard_guild_members", None))
        for obj_data in records:
            # Apply offset to position and strip item_ids so new UUIDs are minted (AUD-002)
            obj_copy = _strip_item_ids(
                _offset_item_dict(obj_data, host._paste_offset, host._paste_offset)
            )

            # Deserialize the item (gets a new UUID)
            item = host._deserialize_item(obj_copy)
            if item:
                host._restore_layer_id(item, obj_copy)
                pasted_items.append(item)
                clipboard_data.append(obj_data)

        # Rebuild parent-child relationships with new UUIDs
        if pasted_items:
            old_id_to_new: dict[str, QGraphicsItem] = {}
            for obj_data, item in zip(clipboard_data, pasted_items, strict=True):
                old_id = obj_data.get("item_id")
                if old_id:
                    old_id_to_new[old_id] = item

            for obj_data, item in zip(clipboard_data, pasted_items, strict=True):
                if not isinstance(item, GardenItemMixin):
                    continue
                # Clear auto-detect fields so CreateItemsCommand doesn't double-parent
                item._parent_bed_id = None
                item._child_item_ids = []

                # Remap parent — the scene derives z from the normalized
                # stacking order (issue #338), so a plant renders above its
                # bed automatically once CreateItemsCommand adds both items.
                old_parent = obj_data.get("parent_bed_id")
                if old_parent and old_parent in old_id_to_new:
                    parent = old_id_to_new[old_parent]
                    if isinstance(parent, GardenItemMixin):
                        item.parent_bed_id = parent.item_id
                        parent.add_child_id(item.item_id)

            # Use command for undo support
            from open_garden_planner.core import CreateItemsCommand

            command = CreateItemsCommand(cast("CanvasScene", host.scene()), pasted_items, "pasted objects")
            host._command_manager.execute(command)

            # Select the pasted items
            for item in pasted_items:
                item.setSelected(True)

            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Pasted {count} item(s)").format(count=len(pasted_items))
            )


    def duplicate_selected(self) -> None:
        """Duplicate selected items (copy and paste in one action)."""
        item: QGraphicsItem | None
        host = self._host
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        selected = list(cast("CanvasScene", host.scene()).selectedItems())
        if not selected:
            host.set_status_message(QCoreApplication.translate("CanvasView", "Nothing to duplicate"))
            return

        # Auto-include children of selected plant-parents (beds/containers/trellises)
        selected_ids = {
            item.item_id for item in selected if isinstance(item, GardenItemMixin)
        }
        for item in list(selected):
            if isinstance(item, GardenItemMixin) and is_plant_parent_type(
                item.object_type
            ):
                for child_id in item.child_item_ids:
                    if child_id not in selected_ids:
                        child = host._canvas_scene.find_item_by_id(child_id)
                        if child is not None:
                            selected.append(child)
                            selected_ids.add(child_id)

        # Sort bottom-to-top by current z before serializing so the
        # duplicates keep the same relative stacking order (issue #338) --
        # CreateItemsCommand adds items in list order, and each addItem
        # ranks a new item above whatever's already been added.
        selected.sort(key=lambda item: item.zValue())

        # Serialize selected items directly (don't modify clipboard)
        source_data: list[dict[str, Any]] = []
        for item in selected:
            obj_data = host._serialize_item(item)
            if obj_data:
                source_data.append(obj_data)

        if not source_data:
            return

        # Deselect all items
        for item in cast("CanvasScene", host.scene()).selectedItems():
            item.setSelected(False)

        # Create new items with offset
        duplicated_items: list[QGraphicsItem] = []
        dup_source: list[dict[str, Any]] = []
        from open_garden_planner.ui.guild_copy import copy_guild_records

        source_data = copy_guild_records(cast("CanvasScene", host.scene()), source_data)
        for obj_data in source_data:
            obj_copy = _strip_item_ids(
                _offset_item_dict(obj_data, host._paste_offset, host._paste_offset)
            )

            # Deserialize the item
            item = host._deserialize_item(obj_copy)
            if item:
                host._restore_layer_id(item, obj_copy)
                duplicated_items.append(item)
                dup_source.append(obj_data)

        # Rebuild parent-child relationships with new UUIDs
        if duplicated_items:
            old_id_to_new: dict[str, QGraphicsItem] = {}
            for obj_data, item in zip(dup_source, duplicated_items, strict=True):
                old_id = obj_data.get("item_id")
                if old_id:
                    old_id_to_new[old_id] = item

            for obj_data, item in zip(dup_source, duplicated_items, strict=True):
                if not isinstance(item, GardenItemMixin):
                    continue
                item._parent_bed_id = None
                item._child_item_ids = []

                old_parent = obj_data.get("parent_bed_id")
                if old_parent and old_parent in old_id_to_new:
                    parent = old_id_to_new[old_parent]
                    if isinstance(parent, GardenItemMixin):
                        item.parent_bed_id = parent.item_id
                        parent.add_child_id(item.item_id)

            from open_garden_planner.core import CreateItemsCommand

            command = CreateItemsCommand(
                cast("CanvasScene", host.scene()), duplicated_items, "duplicated objects"
            )
            host._command_manager.execute(command)

            # Select the duplicated items
            for item in duplicated_items:
                item.setSelected(True)

            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Duplicated {count} item(s)").format(
                    count=len(duplicated_items)
                )
            )


    def create_linear_array(self) -> None:
        """Create a linear array from the single selected item."""
        host = self._host
        import math

        selected = cast("CanvasScene", host.scene()).selectedItems()
        if len(selected) != 1:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Select exactly one item to create a linear array")
            )
            return

        from PyQt6.QtWidgets import QDialog

        from open_garden_planner.ui.dialogs.linear_array_dialog import LinearArrayDialog

        dlg = LinearArrayDialog(host)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        count = dlg.count
        spacing = dlg.spacing_cm
        angle_rad = math.radians(dlg.angle_deg)
        # Negate dy: canvas has a Y-flip (origin bottom-left, Y-up in view),
        # so +scene_y is visually upward. Negate to match screen-space intuition
        # where 90° = downward and 270° = upward.
        dx = spacing * math.cos(angle_rad)
        dy = -spacing * math.sin(angle_rad)

        source_item = selected[0]
        obj_data = host._serialize_item(source_item)
        if not obj_data:
            return

        canvas_w = host._canvas_scene.width_cm
        canvas_h = host._canvas_scene.height_cm

        new_items = []
        for i in range(1, count):
            obj_copy = obj_data.copy()
            offset_x = dx * i
            offset_y = dy * i

            if "points" in obj_copy:
                pts = [
                    {"x": p["x"] + offset_x, "y": p["y"] + offset_y}
                    for p in obj_data["points"]
                ]
                # Clamp: shift all points so bbox stays within canvas
                min_x = min(p["x"] for p in pts)
                max_x = max(p["x"] for p in pts)
                min_y = min(p["y"] for p in pts)
                max_y = max(p["y"] for p in pts)
                cx = max(0.0, -min_x) - max(0.0, max_x - canvas_w)
                cy = max(0.0, -min_y) - max(0.0, max_y - canvas_h)
                obj_copy["points"] = [{"x": p["x"] + cx, "y": p["y"] + cy} for p in pts]
            elif "center_x" in obj_copy:
                r = obj_data.get("radius", 0.0)
                cx = obj_data["center_x"] + offset_x
                cy = obj_data["center_y"] + offset_y
                obj_copy["center_x"] = max(r, min(cx, canvas_w - r))
                obj_copy["center_y"] = max(r, min(cy, canvas_h - r))
            else:
                item_w = obj_data.get("width", 0.0)
                item_h = obj_data.get("height", 0.0)
                nx = obj_data["x"] + offset_x
                ny = obj_data["y"] + offset_y
                obj_copy["x"] = max(0.0, min(nx, canvas_w - item_w))
                obj_copy["y"] = max(0.0, min(ny, canvas_h - item_h))

            item = host._deserialize_item(_strip_item_ids(host._remap_guild_copy([obj_copy])[0]))
            if item:
                new_items.append(item)

        if not new_items:
            return

        # Build optional constraint pairs (center-to-center between consecutive items)
        constraint_pairs = None
        if dlg.create_constraints:
            from open_garden_planner.core.constraints import AnchorRef
            from open_garden_planner.core.measure_snapper import AnchorType
            from open_garden_planner.ui.canvas.items import GardenItemMixin

            if isinstance(source_item, GardenItemMixin):
                all_items = [source_item, *new_items]
                constraint_pairs = []
                for j in range(len(all_items) - 1):
                    a = all_items[j]
                    b = all_items[j + 1]
                    if isinstance(a, GardenItemMixin) and isinstance(
                        b, GardenItemMixin
                    ):
                        ref_a = AnchorRef(
                            item_id=a.item_id,
                            anchor_type=AnchorType.CENTER,
                        )
                        ref_b = AnchorRef(
                            item_id=b.item_id,
                            anchor_type=AnchorType.CENTER,
                        )
                        constraint_pairs.append((ref_a, ref_b, spacing))

        from open_garden_planner.core import LinearArrayCommand

        command = LinearArrayCommand(
            cast("CanvasScene", host.scene()),
            new_items,
            constraint_pairs=constraint_pairs,
            graph=host._canvas_scene.constraint_graph if constraint_pairs else None,
        )
        host._command_manager.execute(command)

        # Select original + all copies
        cast("CanvasScene", host.scene()).clearSelection()
        source_item.setSelected(True)
        for item in new_items:
            item.setSelected(True)

        host.set_status_message(
            QCoreApplication.translate("CanvasView", "Created linear array of {count} items").format(count=count)
        )


    def create_grid_array(self) -> None:
        """Create a rectangular grid array from the single selected item."""
        host = self._host
        selected = cast("CanvasScene", host.scene()).selectedItems()
        if len(selected) != 1:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Select exactly one item to create a grid array")
            )
            return

        from PyQt6.QtWidgets import QDialog

        from open_garden_planner.ui.dialogs.grid_array_dialog import GridArrayDialog

        dlg = GridArrayDialog(host)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        rows = dlg.rows
        cols = dlg.cols
        row_spacing = dlg.row_spacing_cm
        col_spacing = dlg.col_spacing_cm

        # Canvas Y-axis is flipped: scale(zoom, -zoom) makes positive scene Y visually upward.
        # Rows go downward on screen → -row_spacing per row in scene coords.
        # Columns go rightward → +col_spacing per column in scene coords (X not flipped).

        source_item = selected[0]
        obj_data = host._serialize_item(source_item)
        if not obj_data:
            return

        canvas_w = host._canvas_scene.width_cm
        canvas_h = host._canvas_scene.height_cm

        # Build a flat list of (row, col) positions skipping (0, 0) = original
        new_items: list[Any] = []
        grid: list[Any] = []  # list of (row, col, item) — includes original at (0,0)

        # Add original at grid position (0,0)
        grid.append((0, 0, source_item))

        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue  # original
                obj_copy = obj_data.copy()
                # col → rightward = +x; row → downward on screen = -y (scene Y-flip)
                offset_x = col_spacing * c
                offset_y = -row_spacing * r

                if "points" in obj_copy:
                    pts = [
                        {"x": p["x"] + offset_x, "y": p["y"] + offset_y}
                        for p in obj_data["points"]
                    ]
                    min_x = min(p["x"] for p in pts)
                    max_x = max(p["x"] for p in pts)
                    min_y = min(p["y"] for p in pts)
                    max_y = max(p["y"] for p in pts)
                    cx = max(0.0, -min_x) - max(0.0, max_x - canvas_w)
                    cy = max(0.0, -min_y) - max(0.0, max_y - canvas_h)
                    obj_copy["points"] = [
                        {"x": p["x"] + cx, "y": p["y"] + cy} for p in pts
                    ]
                elif "center_x" in obj_copy:
                    rad = obj_data.get("radius", 0.0)
                    cx = obj_data["center_x"] + offset_x
                    cy = obj_data["center_y"] + offset_y
                    obj_copy["center_x"] = max(rad, min(cx, canvas_w - rad))
                    obj_copy["center_y"] = max(rad, min(cy, canvas_h - rad))
                else:
                    item_w = obj_data.get("width", 0.0)
                    item_h = obj_data.get("height", 0.0)
                    nx = obj_data["x"] + offset_x
                    ny = obj_data["y"] + offset_y
                    obj_copy["x"] = max(0.0, min(nx, canvas_w - item_w))
                    obj_copy["y"] = max(0.0, min(ny, canvas_h - item_h))

                item = host._deserialize_item(_strip_item_ids(host._remap_guild_copy([obj_copy])[0]))
                if item:
                    new_items.append(item)
                    grid.append((r, c, item))

        if not new_items:
            return

        # Build optional constraint pairs between adjacent items (same row/col)
        constraint_pairs = None
        if dlg.create_constraints:
            from open_garden_planner.core.constraints import AnchorRef
            from open_garden_planner.core.measure_snapper import AnchorType
            from open_garden_planner.ui.canvas.items import GardenItemMixin

            if isinstance(source_item, GardenItemMixin):
                # Index the grid by (row, col)
                grid_map: dict[tuple[int, int], QGraphicsItem] = {(r, c): itm for r, c, itm in grid}
                constraint_pairs = []
                for r in range(rows):
                    for c in range(cols):
                        itm = grid_map.get((r, c))
                        if itm is None or not isinstance(itm, GardenItemMixin):
                            continue
                        # Horizontal neighbour (same row, next col)
                        right = grid_map.get((r, c + 1))
                        if right is not None and isinstance(right, GardenItemMixin):
                            constraint_pairs.append(
                                (
                                    AnchorRef(
                                        item_id=itm.item_id,
                                        anchor_type=AnchorType.CENTER,
                                    ),
                                    AnchorRef(
                                        item_id=right.item_id,
                                        anchor_type=AnchorType.CENTER,
                                    ),
                                    col_spacing,
                                )
                            )
                        # Vertical neighbour (next row, same col)
                        below = grid_map.get((r + 1, c))
                        if below is not None and isinstance(below, GardenItemMixin):
                            constraint_pairs.append(
                                (
                                    AnchorRef(
                                        item_id=itm.item_id,
                                        anchor_type=AnchorType.CENTER,
                                    ),
                                    AnchorRef(
                                        item_id=below.item_id,
                                        anchor_type=AnchorType.CENTER,
                                    ),
                                    row_spacing,
                                )
                            )

        from open_garden_planner.core import GridArrayCommand

        command = GridArrayCommand(
            cast("CanvasScene", host.scene()),
            new_items,
            constraint_pairs=constraint_pairs,
            graph=host._canvas_scene.constraint_graph if constraint_pairs else None,
        )
        host._command_manager.execute(command)

        # Select original + all copies
        cast("CanvasScene", host.scene()).clearSelection()
        source_item.setSelected(True)
        for item in new_items:
            item.setSelected(True)

        total = rows * cols
        host.set_status_message(
            QCoreApplication.translate("CanvasView", "Created grid array of {count} items ({rows}×{cols})").format(
                count=total, rows=rows, cols=cols
            )
        )


    def create_circular_array(self) -> None:
        """Create a circular array from the single selected item."""
        host = self._host
        import math

        selected = cast("CanvasScene", host.scene()).selectedItems()
        if len(selected) != 1:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Select exactly one item to create a circular array")
            )
            return

        from PyQt6.QtWidgets import QDialog

        from open_garden_planner.ui.dialogs.circular_array_dialog import (
            CircularArrayDialog,
        )

        dlg = CircularArrayDialog(host)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        count = dlg.count
        radius = dlg.radius_cm
        start_rad = math.radians(dlg.start_angle_deg)
        sweep_rad = math.radians(dlg.sweep_angle_deg)

        # Angular step between copies. When sweep == 360° divide evenly by count
        # (no duplicated endpoint). When sweep < 360° include both endpoints by
        # dividing by (count - 1).
        if abs(sweep_rad - 2 * math.pi) < 1e-6:
            step_rad = sweep_rad / count
        else:
            step_rad = sweep_rad / max(count - 1, 1)

        source_item = selected[0]
        obj_data = host._serialize_item(source_item)
        if not obj_data:
            return

        # Determine the center of the source item to use as circle origin.
        if "center_x" in obj_data:
            origin_x = obj_data["center_x"]
            origin_y = obj_data["center_y"]
        elif "points" in obj_data:
            xs = [p["x"] for p in obj_data["points"]]
            ys = [p["y"] for p in obj_data["points"]]
            origin_x = (min(xs) + max(xs)) / 2.0
            origin_y = (min(ys) + max(ys)) / 2.0
        else:
            origin_x = obj_data["x"] + obj_data.get("width", 0.0) / 2.0
            origin_y = obj_data["y"] + obj_data.get("height", 0.0) / 2.0

        canvas_w = host._canvas_scene.width_cm
        canvas_h = host._canvas_scene.height_cm

        # The original sits at start_angle on the circle; each copy is offset
        # relative to the original's position (not from an implicit center).
        # Canvas Y-axis is flipped (scale(zoom, -zoom)), so negate sin for dy.
        # offset_i = radius * (direction_i - direction_0), so at i=0 offset=(0,0).
        base_cos = math.cos(start_rad)
        base_sin = math.sin(start_rad)

        new_items = []
        for i in range(1, count):
            angle = start_rad + i * step_rad
            offset_x = radius * (math.cos(angle) - base_cos)
            offset_y = -radius * (math.sin(angle) - base_sin)

            obj_copy = obj_data.copy()

            if "points" in obj_copy:
                pts = [
                    {"x": p["x"] + offset_x, "y": p["y"] + offset_y}
                    for p in obj_data["points"]
                ]
                min_x = min(p["x"] for p in pts)
                max_x = max(p["x"] for p in pts)
                min_y = min(p["y"] for p in pts)
                max_y = max(p["y"] for p in pts)
                cx = max(0.0, -min_x) - max(0.0, max_x - canvas_w)
                cy = max(0.0, -min_y) - max(0.0, max_y - canvas_h)
                obj_copy["points"] = [{"x": p["x"] + cx, "y": p["y"] + cy} for p in pts]
            elif "center_x" in obj_copy:
                r = obj_data.get("radius", 0.0)
                cx = origin_x + offset_x
                cy = origin_y + offset_y
                obj_copy["center_x"] = max(r, min(cx, canvas_w - r))
                obj_copy["center_y"] = max(r, min(cy, canvas_h - r))
            else:
                item_w = obj_data.get("width", 0.0)
                item_h = obj_data.get("height", 0.0)
                nx = origin_x - item_w / 2.0 + offset_x
                ny = origin_y - item_h / 2.0 + offset_y
                obj_copy["x"] = max(0.0, min(nx, canvas_w - item_w))
                obj_copy["y"] = max(0.0, min(ny, canvas_h - item_h))

            item = host._deserialize_item(_strip_item_ids(host._remap_guild_copy([obj_copy])[0]))
            if item:
                new_items.append(item)

        if not new_items:
            return

        from open_garden_planner.core import CircularArrayCommand

        command = CircularArrayCommand(cast("CanvasScene", host.scene()), new_items)
        host._command_manager.execute(command)

        # Select original + all copies
        cast("CanvasScene", host.scene()).clearSelection()
        source_item.setSelected(True)
        for item in new_items:
            item.setSelected(True)

        host.set_status_message(
            QCoreApplication.translate("CanvasView", "Created circular array of {count} items").format(count=count)
        )


    def create_array_along_path(self) -> None:
        """Create copies of an item distributed along a polyline path."""
        item: QGraphicsItem | None
        host = self._host
        from PyQt6.QtWidgets import QDialog

        from open_garden_planner.core.path_sampling import sample_points_along_path
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
        from open_garden_planner.ui.dialogs.array_along_path_dialog import (
            ArrayAlongPathDialog,
        )

        selected = cast("CanvasScene", host.scene()).selectedItems()
        if len(selected) != 2:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Select one item and one polyline path for array along path")
            )
            return

        # Identify the path and the source item
        path_item = None
        source_item = None
        for item in selected:
            if isinstance(item, PolylineItem):
                path_item = item
            else:
                source_item = item

        if path_item is None or source_item is None:
            host.set_status_message(
                QCoreApplication.translate("CanvasView", "Select one item and one polyline path for array along path")
            )
            return

        # Get the path in scene coordinates
        from PyQt6.QtGui import QPainterPath

        local_path = path_item.path()
        # Map path to scene coordinates by sampling and rebuilding
        scene_path = QPainterPath()
        n_segments = 200
        for i in range(n_segments + 1):
            t = i / n_segments
            local_pt = local_path.pointAtPercent(t)
            scene_pt = path_item.mapToScene(local_pt)
            if i == 0:
                scene_path.moveTo(scene_pt)
            else:
                scene_path.lineTo(scene_pt)

        dlg = ArrayAlongPathDialog(host)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Determine count
        total_length = scene_path.length()
        start_pct = dlg.start_offset_pct / 100.0
        end_pct = 1.0 - dlg.end_offset_pct / 100.0
        usable_length = total_length * (end_pct - start_pct)

        if dlg.use_spacing_mode:
            count = max(2, int(usable_length / dlg.spacing_cm) + 1)
        else:
            count = dlg.count

        points = sample_points_along_path(
            scene_path, count, start_pct, end_pct, dlg.follow_tangent
        )

        obj_data = host._serialize_item(source_item)
        if not obj_data:
            return

        # Determine the center of the source item
        if "center_x" in obj_data:
            src_cx = obj_data["center_x"]
            src_cy = obj_data["center_y"]
        elif "points" in obj_data:
            xs = [p["x"] for p in obj_data["points"]]
            ys = [p["y"] for p in obj_data["points"]]
            src_cx = (min(xs) + max(xs)) / 2.0
            src_cy = (min(ys) + max(ys)) / 2.0
        else:
            src_cx = obj_data["x"] + obj_data.get("width", 0.0) / 2.0
            src_cy = obj_data["y"] + obj_data.get("height", 0.0) / 2.0

        new_items = []
        for pt, angle in points:
            offset_x = pt.x() - src_cx
            offset_y = pt.y() - src_cy

            obj_copy = obj_data.copy()

            if "points" in obj_copy:
                pts = [
                    {"x": p["x"] + offset_x, "y": p["y"] + offset_y}
                    for p in obj_data["points"]
                ]
                obj_copy["points"] = pts
            elif "center_x" in obj_copy:
                obj_copy["center_x"] = pt.x()
                obj_copy["center_y"] = pt.y()
            else:
                item_w = obj_data.get("width", 0.0)
                item_h = obj_data.get("height", 0.0)
                obj_copy["x"] = pt.x() - item_w / 2.0
                obj_copy["y"] = pt.y() - item_h / 2.0

            item = host._deserialize_item(_strip_item_ids(host._remap_guild_copy([obj_copy])[0]))
            if item:
                if dlg.follow_tangent:
                    # Rotate around the item's visual center, not its local origin,
                    # so the item stays centred on the path point after rotation.
                    item.setTransformOriginPoint(item.boundingRect().center())
                    item.setRotation(-angle)
                new_items.append(item)

        if not new_items:
            return

        from open_garden_planner.core import ArrayAlongPathCommand

        command = ArrayAlongPathCommand(cast("CanvasScene", host.scene()), new_items)
        host._command_manager.execute(command)

        # Select original + all copies
        cast("CanvasScene", host.scene()).clearSelection()
        source_item.setSelected(True)
        for item in new_items:
            item.setSelected(True)

        host.set_status_message(
            QCoreApplication.translate("CanvasView", "Created array of {count} items along path").format(
                count=len(new_items) + 1
            )
        )


    def _serialize_item(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Serialize a single graphics item.

        Delegates to ProjectManager._serialize_item (AUD-002, TD-018).
        """
        from open_garden_planner.core.project import ProjectManager

        return ProjectManager._serialize_item(item)


    def _restore_layer_id(self, item: QGraphicsItem, obj: dict[str, Any]) -> None:
        """Apply a clipboard dict's ``layer_id`` (if any) onto *item*.

        The clipboard's ``layer_id`` can outlive its source: paste after a
        File -> New Plan (fresh layer UUIDs), or paste into a different
        scene, means the copied id no longer resolves. Applying it blindly
        would give the pasted item a dangling ``layer_id`` -- invisible to
        the layer's visibility/lock, filtered out of stacking/arrange, and
        written to disk as an orphan reference. Only apply it when it still
        resolves in the *target* scene; otherwise fall back to the active
        layer (if any), else leave the item layer-less.
        """
        host = self._host
        from uuid import UUID

        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin):
            return
        scene = cast("CanvasScene", host.scene())
        layer_id_str = obj.get("layer_id")
        resolved: UUID | None = None
        if layer_id_str:
            with contextlib.suppress(ValueError, TypeError):
                candidate = UUID(layer_id_str)
                if scene is not None and scene.get_layer_by_id(candidate) is not None:
                    resolved = candidate
        if resolved is None and scene is not None and scene.active_layer is not None:
            resolved = scene.active_layer.id
        item.layer_id = resolved


    def _serialize_item_core(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Core serialization delegating to ProjectManager._serialize_item_core."""
        from open_garden_planner.core.project import ProjectManager

        return ProjectManager._serialize_item_core(item)


    def _remap_guild_copy(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        host = self._host
        from open_garden_planner.ui.guild_copy import copy_guild_records

        return copy_guild_records(cast("CanvasScene", host.scene()), records)


    def _deserialize_item(self, obj: dict[str, Any]) -> QGraphicsItem | None:
        """Deserialize a single object to a graphics item.

        Delegates to ProjectManager._deserialize_item (AUD-002, TD-018).
        """
        from open_garden_planner.core.project import ProjectManager

        return ProjectManager._deserialize_item(obj)


