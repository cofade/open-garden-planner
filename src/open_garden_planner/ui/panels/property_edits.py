"""PropertyEdits: one responsibility extracted from PropertiesPanel."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPen

from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    MoveToLayerCommand,
)
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.item_look import (
    adopt_pen,
    apply_line_look,
    capture_line_look,
    line_look_for_preset,
    line_look_for_type,
)
from open_garden_planner.core.object_types import (
    StrokeStyle,
    get_style,
)
from open_garden_planner.ui.canvas.items import (
    PolylineItem,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.panels.properties_panel import ColorButton, PropertiesPanel


class PropertyEdits:
    """Uses the original host for state, translation context and command ownership."""

    def __init__(self, host: PropertiesPanel) -> None:
        self._host = host

    def _capture_item_state(self, item: Any) -> dict[str, Any]:
        """Capture the current state of an item for undo purposes.

        Args:
            item: The item to capture state from

        Returns:
            Dictionary with all relevant property values
        """
        state = {}
        if hasattr(item, 'object_type'):
            state['object_type'] = item.object_type
        if hasattr(item, 'name'):
            state['name'] = item.name
        if hasattr(item, 'layer_id'):
            state['layer_id'] = item.layer_id
        if hasattr(item, 'fill_color'):
            state['fill_color'] = QColor(item.fill_color) if item.fill_color else None
        if hasattr(item, 'fill_pattern'):
            state['fill_pattern'] = item.fill_pattern
        if hasattr(item, 'stroke_color'):
            state['stroke_color'] = QColor(item.stroke_color) if item.stroke_color else None
        if hasattr(item, 'stroke_width'):
            state['stroke_width'] = item.stroke_width
        if hasattr(item, 'stroke_style'):
            state['stroke_style'] = item.stroke_style
        if hasattr(item, 'path_fence_style'):
            state['path_fence_style'] = item.path_fence_style
        return state


    def _apply_item_state(self, item: Any, state: dict[str, Any]) -> None:
        """Apply a captured state to an item.

        Args:
            item: The item to apply state to
            state: Dictionary with property values
        """
        if 'object_type' in state and hasattr(item, 'object_type'):
            item.object_type = state['object_type']

        if 'name' in state and hasattr(item, 'name'):
            item.name = state['name']
            if hasattr(item, '_update_label'):
                item._update_label()

        if 'layer_id' in state and hasattr(item, 'layer_id'):
            # z is derived from the scene's normalized stacking order
            # (issue #338), not set directly here -- but switching
            # layer_id moves the item into a different layer's z-band, so
            # both the old and new layer need an explicit refresh; nothing
            # else triggers one for a bare attribute write (issue #338
            # review P2: this write previously left the item's z stale
            # until some unrelated refresh happened to run).
            old_layer_id = item.layer_id
            new_layer_id = state['layer_id']
            item.layer_id = new_layer_id
            if old_layer_id != new_layer_id:
                scene = item.scene()
                refresh_layer = getattr(scene, "_refresh_layer_z", None)
                if callable(refresh_layer):
                    refresh_layer(old_layer_id)
                    refresh_layer(new_layer_id)
                else:
                    refresh_all = getattr(scene, "_update_items_z_order", None)
                    if callable(refresh_all):
                        refresh_all()

        if 'fill_color' in state and hasattr(item, 'fill_color'):
            item.fill_color = state['fill_color']
        if 'fill_pattern' in state and hasattr(item, 'fill_pattern'):
            item.fill_pattern = state['fill_pattern']
        if 'stroke_color' in state and hasattr(item, 'stroke_color'):
            item.stroke_color = state['stroke_color']
        if 'stroke_width' in state and hasattr(item, 'stroke_width'):
            item.stroke_width = state['stroke_width']
        if 'stroke_style' in state and hasattr(item, 'stroke_style'):
            item.stroke_style = state['stroke_style']
        if 'path_fence_style' in state and hasattr(item, 'path_fence_style'):
            item.path_fence_style = state['path_fence_style']
            if hasattr(item, 'apply_style_preset'):
                item.apply_style_preset()

        # Update visual appearance
        if not isinstance(item, PolylineItem):
            pattern = state.get('fill_pattern', FillPattern.SOLID)
            color = state.get('fill_color') or item.brush().color()
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

        stroke_color = state.get('stroke_color') or item.pen().color()
        stroke_width = state.get('stroke_width', item.pen().widthF())
        stroke_style = state.get('stroke_style', StrokeStyle.SOLID)
        pen = QPen(stroke_color)
        pen.setWidthF(cast(float, stroke_width))
        pen.setStyle(stroke_style.to_qt_pen_style())
        # The pen AND the stroke attributes (core.item_look): ``apply_style_preset``
        # above has just set the attributes to the preset's, and the pen built here is
        # the state's — the undo of a type change on a re-stroked preset line left
        # the two apart.
        adopt_pen(item, pen)

        # Update scene
        scene = item.scene()
        if scene:
            scene.update()


    def _on_property_changed(self, item: Any, property_name: str, value: Any) -> None:
        """Handle property change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the property
            value: New value
        """
        host = self._host
        if host._updating:
            return

        # One line-style restore path for both UI surfaces. Snapshot callbacks do
        # not retain this panel, which may be rebuilt before an undo is requested.
        if isinstance(item, PolylineItem) and property_name in ('object_type', 'path_fence_style'):
            old_value = item.object_type if property_name == 'object_type' else item.path_fence_style
            if value == old_value:
                return
            before = capture_line_look(item)
            after = (line_look_for_type(value) if property_name == 'object_type'
                     else line_look_for_preset(item, value))
            apply_line_look(item, after)
            if host._command_manager:
                if property_name == 'object_type':
                    command = ChangePropertyCommand(item, 'type', before, after, apply_line_look)
                else:
                    command = ChangePropertyCommand(item, 'path/fence style', before, after, apply_line_look)
                host._command_manager.register_applied(command)
            if property_name == 'object_type':
                refresh = QTimer(host)
                refresh.setSingleShot(True)
                refresh.timeout.connect(lambda: host.set_selected_items([item]))
                refresh.timeout.connect(host.object_type_changed.emit)
                refresh.timeout.connect(refresh.deleteLater)
                refresh.start(0)
            return

        # Apply the change to the item
        handlers = {
            "object_type": self._change_object_type,
            "label_visible": self._change_label_visible,
            "layer_id": self._change_layer_id,
            "fill_pattern": self._change_fill_pattern,
            "stroke_width": self._change_stroke_width,
            "stroke_style": self._change_stroke_style,
        }
        handler = handlers.get(property_name)
        if handler is not None:
            handler(item, value)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()


    def _change_object_type(self, item: Any, value: Any) -> None:
        host = self._host
        if not (hasattr(item, 'object_type')):
            return
        old_state = host._capture_item_state(item)
        style = get_style(value)
        new_state = {
            'object_type': value,
            'fill_color': style.fill_color,
            'fill_pattern': style.fill_pattern,
            'stroke_color': style.stroke_color,
            'stroke_width': style.stroke_width,
            'stroke_style': style.stroke_style,
        }
        host._apply_item_state(item, new_state)

        # Create undo command if we have a command manager
        if host._command_manager:
            def apply_func(itm: Any, state: dict[str, Any]) -> None:
                host._apply_item_state(itm, state)
            cmd = ChangePropertyCommand(item, "type", old_state, new_state, apply_func)
            # Don't execute - already applied, just add to stack
            host._command_manager.register_applied(cmd)

        # Defer panel refresh to avoid destroying widgets while signal is processing
        QTimer.singleShot(0, lambda: host.set_selected_items([item]))

        # Notify other panels that the object type changed
        QTimer.singleShot(0, host.object_type_changed.emit)


    def _change_label_visible(self, item: Any, value: Any) -> None:
        host = self._host
        if not (hasattr(item, 'label_visible')):
            return
        old_visible = item.label_visible
        item.label_visible = value

        if host._command_manager:
            def apply_label_visible(itm: Any, val: Any) -> None:
                itm.label_visible = val
            cmd = ChangePropertyCommand(item, "label visibility", old_visible, value, apply_label_visible)
            host._command_manager.register_applied(cmd)


    def _change_layer_id(self, item: Any, value: Any) -> None:
        host = self._host
        if not (hasattr(item, 'layer_id')):
            return
        old_layer = item.layer_id
        if old_layer == value:
            return
        scene = item.scene()
        if scene is not None and host._command_manager:
            target_layer = (
                scene.get_layer_by_id(value) if hasattr(scene, 'get_layer_by_id') else None
            )
            layer_name = target_layer.name if target_layer else str(value)
            layer_command = MoveToLayerCommand([item], value, scene, layer_name)
            host._command_manager.execute(layer_command)
        else:
            item.layer_id = value


    def _change_fill_pattern(self, item: Any, value: Any) -> None:
        host = self._host
        old_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
        if hasattr(item, 'fill_pattern'):
            item.fill_pattern = value
        color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
        brush = create_pattern_brush(value, color)
        item.setBrush(brush)

        if host._command_manager:
            def apply_pattern(itm: Any, val: Any) -> None:
                if hasattr(itm, 'fill_pattern'):
                    itm.fill_pattern = val
                c = itm.fill_color if hasattr(itm, 'fill_color') and itm.fill_color else itm.brush().color()
                itm.setBrush(create_pattern_brush(val, c))
            cmd = ChangePropertyCommand(item, "fill pattern", old_pattern, value, apply_pattern)
            host._command_manager.register_applied(cmd)


    def _change_stroke_width(self, item: Any, value: Any) -> None:
        host = self._host
        old_width = item.stroke_width if hasattr(item, 'stroke_width') else item.pen().widthF()
        if hasattr(item, 'stroke_width'):
            item.stroke_width = value
        pen = item.pen()
        pen.setWidthF(value)
        item.setPen(pen)

        if host._command_manager:
            def apply_width(itm: Any, val: Any) -> None:
                if hasattr(itm, 'stroke_width'):
                    itm.stroke_width = val
                p = itm.pen()
                p.setWidthF(val)
                itm.setPen(p)
            cmd = ChangePropertyCommand(item, "stroke width", old_width, value, apply_width)
            host._command_manager.register_applied(cmd)


    def _change_stroke_style(self, item: Any, value: Any) -> None:
        host = self._host
        old_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
        if hasattr(item, 'stroke_style'):
            item.stroke_style = value
        pen = item.pen()
        pen.setStyle(value.to_qt_pen_style())
        item.setPen(pen)

        if host._command_manager:
            def apply_stroke_style(itm: Any, val: Any) -> None:
                if hasattr(itm, 'stroke_style'):
                    itm.stroke_style = val
                p = itm.pen()
                p.setStyle(val.to_qt_pen_style())
                itm.setPen(p)
            cmd = ChangePropertyCommand(item, "stroke style", old_style, value, apply_stroke_style)
            host._command_manager.register_applied(cmd)


    def _on_color_changed(self, item: Any, property_name: str, button: ColorButton) -> None:
        """Handle color button change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the color property ('fill_color' or 'stroke_color')
            button: The color button that was changed
        """
        host = self._host
        if host._updating:
            return

        color = button.color

        if property_name == 'fill_color':
            # Capture old value for undo
            old_color = QColor(item.fill_color) if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()

            # Store the color
            if hasattr(item, 'fill_color'):
                item.fill_color = color
            # Apply to brush
            pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

            # Create undo command
            if host._command_manager:
                def apply_fill_color(itm: Any, val: Any) -> None:
                    if hasattr(itm, 'fill_color'):
                        itm.fill_color = val
                    p = itm.fill_pattern if hasattr(itm, 'fill_pattern') else FillPattern.SOLID
                    itm.setBrush(create_pattern_brush(p, val))
                cmd = ChangePropertyCommand(item, "fill color", old_color, color, apply_fill_color)
                host._command_manager.register_applied(cmd)

        elif property_name == 'stroke_color':
            # Capture old value for undo
            old_color = QColor(item.stroke_color) if hasattr(item, 'stroke_color') and item.stroke_color else item.pen().color()

            # Store the color
            if hasattr(item, 'stroke_color'):
                item.stroke_color = color
            # Apply to pen
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)

            # Create undo command
            if host._command_manager:
                def apply_stroke_color(itm: Any, val: Any) -> None:
                    if hasattr(itm, 'stroke_color'):
                        itm.stroke_color = val
                    p = itm.pen()
                    p.setColor(val)
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke color", old_color, color, apply_stroke_color)
                host._command_manager.register_applied(cmd)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()


