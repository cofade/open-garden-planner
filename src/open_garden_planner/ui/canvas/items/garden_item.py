"""Base mixin for garden canvas items."""

import uuid
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsSimpleTextItem, QGraphicsTextItem

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMenu

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle


class GardenItemMixin:
    """Mixin providing common functionality for garden items.

    Provides:
        - Unique identifier (UUID)
        - Object type classification
        - Name/label
        - Layer assignment
        - Extensible metadata
        - Painted drop shadows (lightweight, no offscreen buffer)
    """

    # Painted-shadow parameters (scene-coordinate units).
    # Y offset is negative so the shadow appears *below* the item on screen
    # (the view applies a Y-flip).
    SHADOW_OFFSET_X: float = 3.0
    SHADOW_OFFSET_Y: float = -3.0
    SHADOW_COLOR = QColor(0, 0, 0, 40)

    def __init__(
        self,
        object_type: ObjectType | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        fill_color: Any = None,  # QColor, but avoiding import
        stroke_color: Any = None,  # QColor, but avoiding import
        stroke_width: float | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the garden item mixin.

        Args:
            object_type: Type of property object (optional)
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
            fill_pattern: Fill pattern (optional, defaults to pattern from object type)
            fill_color: Base fill color (optional, used with patterns)
            stroke_color: Stroke/outline color (optional)
            stroke_width: Stroke/outline width (optional)
            stroke_style: Stroke/outline style (optional)
            layer_id: Layer ID this item belongs to (optional)
        """
        self._item_id = uuid.uuid4()
        self._object_type = object_type
        self._name = name
        self._metadata = metadata or {}
        self._fill_pattern = fill_pattern
        self._fill_color = fill_color  # Store base color for serialization
        self._stroke_color = stroke_color
        self._stroke_width = stroke_width
        self._stroke_style = stroke_style
        self._layer_id = layer_id
        self._label_visible = True  # Per-object label visibility
        self._global_labels_visible = True  # Global label visibility (set by scene)
        self._shadows_enabled = True  # Painted shadow on/off
        self._companion_highlight: str | None = None  # "beneficial" | "antagonistic" | None
        self._antagonist_warning: bool = False  # Permanent badge: antagonist nearby
        self._rotation_status: str | None = None  # "good" | "suboptimal" | "violation" | None
        self._parent_bed_id: uuid.UUID | None = None  # Parent bed UUID (plant→bed)
        self._child_item_ids: list[uuid.UUID] = []  # Child plant UUIDs (bed→plants)
        self._spacing_radius_cm: float | None = None  # User-override spacing radius (cm)
        self._spacing_overlap: str | None = None  # "overlap" | "ideal" | None
        self._spacing_circles_visible: bool = True  # Global toggle from scene
        self._grid_enabled: bool = self._metadata.get("grid_enabled", False)
        self._grid_spacing: float = self._metadata.get("grid_spacing", 30.0)
        self._grid_visible_in_export: bool = self._metadata.get(
            "grid_visible_in_export", False,
        )
        self._label_item: QGraphicsSimpleTextItem | None = None
        self._edit_label_item: QGraphicsTextItem | None = None
        self._label_edit_start_time: float = 0.0

    @property
    def item_id(self) -> uuid.UUID:
        """Unique identifier for this item."""
        return self._item_id

    @property
    def item_id_str(self) -> str:
        """String representation of item ID."""
        return str(self._item_id)

    @property
    def object_type(self) -> ObjectType | None:
        """Type of property object."""
        return self._object_type

    @object_type.setter
    def object_type(self, value: ObjectType | None) -> None:
        """Set the object type."""
        self._object_type = value

    @property
    def name(self) -> str:
        """Name/label of the object."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the name/label."""
        self._name = value
        self._update_label()

    @property
    def metadata(self) -> dict[str, Any]:
        """Extensible metadata dictionary."""
        return self._metadata

    @property
    def fill_pattern(self) -> FillPattern | None:
        """Fill pattern for this item."""
        return self._fill_pattern

    @fill_pattern.setter
    def fill_pattern(self, value: FillPattern | None) -> None:
        """Set the fill pattern."""
        self._fill_pattern = value

    @property
    def fill_color(self) -> Any | None:  # QColor, but avoiding import
        """Base fill color for this item."""
        return self._fill_color

    @fill_color.setter
    def fill_color(self, value: Any) -> None:  # QColor, but avoiding import
        """Set the base fill color."""
        self._fill_color = value

    @property
    def stroke_color(self) -> Any | None:  # QColor, but avoiding import
        """Stroke/outline color for this item."""
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value: Any) -> None:  # QColor, but avoiding import
        """Set the stroke/outline color."""
        self._stroke_color = value

    @property
    def stroke_width(self) -> float | None:
        """Stroke/outline width for this item."""
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value: float) -> None:
        """Set the stroke/outline width."""
        self._stroke_width = value

    @property
    def stroke_style(self) -> StrokeStyle | None:
        """Stroke/outline style for this item."""
        return self._stroke_style

    @stroke_style.setter
    def stroke_style(self, value: StrokeStyle | None) -> None:
        """Set the stroke/outline style."""
        self._stroke_style = value

    @property
    def layer_id(self) -> uuid.UUID | None:
        """Layer ID this item belongs to."""
        return self._layer_id

    @layer_id.setter
    def layer_id(self, value: uuid.UUID | None) -> None:
        """Set the layer ID."""
        self._layer_id = value

    @property
    def shadows_enabled(self) -> bool:
        """Whether painted shadow is enabled for this item."""
        return self._shadows_enabled

    @shadows_enabled.setter
    def shadows_enabled(self, value: bool) -> None:
        """Toggle painted shadow and trigger geometry/repaint update."""
        if value == self._shadows_enabled:
            return
        self._shadows_enabled = value
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    @property
    def companion_highlight(self) -> str | None:
        """Current companion highlight type: 'beneficial', 'antagonistic', or None."""
        return self._companion_highlight

    @property
    def antagonist_warning(self) -> bool:
        """Whether this plant has an antagonist neighbour within the companion radius."""
        return self._antagonist_warning

    def set_antagonist_warning(self, has_warning: bool) -> None:
        """Show or hide the permanent antagonist warning badge.

        Args:
            has_warning: True to show a warning triangle; False to hide it.
        """
        if self._antagonist_warning == has_warning:
            return
        self._antagonist_warning = has_warning
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    def set_companion_highlight(self, highlight_type: str | None) -> None:
        """Set or clear the companion planting highlight for this item.

        Args:
            highlight_type: "beneficial", "antagonistic", or None to clear.
        """
        if self._companion_highlight == highlight_type:
            return
        self._companion_highlight = highlight_type
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    @property
    def rotation_status(self) -> str | None:
        """Current crop rotation status: 'good', 'suboptimal', 'violation', or None."""
        return self._rotation_status

    def set_rotation_status(self, status: str | None) -> None:
        """Set or clear the crop rotation status indicator for this item.

        Args:
            status: "good", "suboptimal", "violation", or None to clear.
        """
        if self._rotation_status == status:
            return
        self._rotation_status = status
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    @property
    def spacing_radius_cm(self) -> float | None:
        """User-override spacing radius in cm, or None for automatic."""
        return self._spacing_radius_cm

    @spacing_radius_cm.setter
    def spacing_radius_cm(self, value: float | None) -> None:
        """Set the user-override spacing radius."""
        self._spacing_radius_cm = value
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    @property
    def spacing_overlap(self) -> str | None:
        """Current spacing overlap status: 'overlap', 'ideal', or None."""
        return self._spacing_overlap

    def set_spacing_overlap(self, overlap_type: str | None) -> None:
        """Set or clear the spacing overlap indicator.

        Args:
            overlap_type: "overlap", "ideal", or None to clear.
        """
        if self._spacing_overlap == overlap_type:
            return
        self._spacing_overlap = overlap_type
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    @property
    def spacing_circles_visible(self) -> bool:
        """Whether spacing circles are globally visible."""
        return self._spacing_circles_visible

    @spacing_circles_visible.setter
    def spacing_circles_visible(self, value: bool) -> None:
        """Set global spacing circle visibility."""
        if self._spacing_circles_visible == value:
            return
        self._spacing_circles_visible = value
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()  # type: ignore[attr-defined]
        if hasattr(self, 'update'):
            self.update()  # type: ignore[attr-defined]

    def effective_spacing_radius(self) -> float | None:
        """Return the spacing radius in cm, or None if no data available.

        Priority: user override > max_spread_cm/2 from plant database.
        Returns None when no real spacing data exists (no circle drawn).
        """
        if self._spacing_radius_cm is not None:
            return self._spacing_radius_cm
        meta = self._metadata or {}
        species_data = meta.get("plant_species")
        if isinstance(species_data, dict):
            max_spread = species_data.get("max_spread_cm")
            if max_spread is not None and max_spread > 0:
                return float(max_spread) / 2.0
        return None

    # ── Grid overlay properties ──────────────────────────────────

    @property
    def grid_enabled(self) -> bool:
        """Whether the interior grid overlay is shown."""
        return self._grid_enabled

    @grid_enabled.setter
    def grid_enabled(self, value: bool) -> None:
        if self._grid_enabled == value:
            return
        self._grid_enabled = value
        self._metadata["grid_enabled"] = value
        if hasattr(self, "update"):
            self.update()  # type: ignore[attr-defined]

    @property
    def grid_spacing(self) -> float:
        """Grid cell size in cm."""
        return self._grid_spacing

    @grid_spacing.setter
    def grid_spacing(self, value: float) -> None:
        if self._grid_spacing == value:
            return
        self._grid_spacing = max(1.0, value)
        self._metadata["grid_spacing"] = self._grid_spacing
        if hasattr(self, "update"):
            self.update()  # type: ignore[attr-defined]

    @property
    def grid_visible_in_export(self) -> bool:
        """Whether the grid appears in PDF / image exports."""
        return self._grid_visible_in_export

    @grid_visible_in_export.setter
    def grid_visible_in_export(self, value: bool) -> None:
        self._grid_visible_in_export = value
        self._metadata["grid_visible_in_export"] = value

    # ── Parent-bed relationship ────────────────────────────────

    @property
    def parent_bed_id(self) -> uuid.UUID | None:
        """UUID of the parent bed this item belongs to, or None."""
        return self._parent_bed_id

    @parent_bed_id.setter
    def parent_bed_id(self, value: uuid.UUID | None) -> None:
        """Set the parent bed UUID."""
        self._parent_bed_id = value

    @property
    def child_item_ids(self) -> list[uuid.UUID]:
        """List of child item UUIDs (copy)."""
        return list(self._child_item_ids)

    @property
    def has_children(self) -> bool:
        """Whether this item has any child items."""
        return bool(self._child_item_ids)

    def add_child_id(self, child_id: uuid.UUID) -> None:
        """Add a child item UUID if not already present."""
        if child_id not in self._child_item_ids:
            self._child_item_ids.append(child_id)

    def remove_child_id(self, child_id: uuid.UUID) -> None:
        """Remove a child item UUID (no error if absent)."""
        import contextlib
        with contextlib.suppress(ValueError):
            self._child_item_ids.remove(child_id)

    def _shadow_margin(self) -> float:
        """Extra margin to add to bounding rect for painted shadow.

        Returns:
            Margin in scene units (0 when shadows are disabled).
        """
        if not self._shadows_enabled:
            return 0.0
        return max(abs(self.SHADOW_OFFSET_X), abs(self.SHADOW_OFFSET_Y))

    @property
    def label_visible(self) -> bool:
        """Whether the label is visible for this object."""
        return self._label_visible

    @label_visible.setter
    def label_visible(self, value: bool) -> None:
        """Set per-object label visibility."""
        self._label_visible = value
        self._update_label()

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata value.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value.

        Args:
            key: Metadata key
            default: Default value if key not found

        Returns:
            Metadata value or default
        """
        return self._metadata.get(key, default)

    def _get_display_label_text(self) -> str:
        """Get the text that should be displayed in the label.

        Returns:
            The custom name, or empty string if not set
        """
        return self._name

    def _should_show_label(self) -> bool:
        """Determine if the label should be visible.

        Returns:
            True if the label should be shown
        """
        return self._global_labels_visible and self._label_visible

    def _create_label(self) -> None:
        """Create the label text item if it doesn't exist."""
        if self._label_item is None:
            # Create label as a child item
            # TYPE_CHECKING guard to help type checker understand self has QGraphicsItem methods
            if not hasattr(self, 'boundingRect'):
                return

            text = self._get_display_label_text()
            if not text:
                return

            self._label_item = QGraphicsSimpleTextItem(text, self)  # type: ignore[arg-type]

            # Configure label appearance
            font = QFont("Arial", 10)
            font.setBold(True)
            self._label_item.setFont(font)
            self._label_item.setBrush(QColor(0, 0, 0))  # Black text

            # Make the label ignore transformations so it stays readable at any zoom
            self._label_item.setFlag(QGraphicsSimpleTextItem.GraphicsItemFlag.ItemIgnoresTransformations)

            # Position the label
            self._position_label()

    def _remove_label(self) -> None:
        """Remove the label item from the scene."""
        if self._label_item is not None:
            self._label_item.setParentItem(None)
            if hasattr(self, 'scene') and callable(self.scene):  # type: ignore[attr-defined]
                scene = self.scene()  # type: ignore[attr-defined]
                if scene is not None:
                    scene.removeItem(self._label_item)
            self._label_item = None

    def _update_label(self) -> None:
        """Update or create label based on current state."""
        text = self._get_display_label_text()
        should_show = self._should_show_label() and bool(text)

        if should_show:
            if self._label_item is None:
                self._create_label()
            else:
                self._label_item.setText(text)
                self._label_item.show()
                self._position_label()
        else:
            # Hide or remove label
            if self._label_item is not None:
                if not self._should_show_label():
                    # Just hide, don't remove (so it can be shown again)
                    self._label_item.hide()
                else:
                    # No text, remove entirely
                    self._remove_label()

    def set_global_labels_visible(self, visible: bool) -> None:
        """Set global label visibility (called by scene toggle).

        Args:
            visible: Whether labels should be globally visible
        """
        self._global_labels_visible = visible
        self._update_label()

    def _position_label(self) -> None:
        """Position the label at the center of the item's bounding rect.

        Note: With ItemIgnoresTransformations, centering perfectly across all zoom levels
        is challenging due to coordinate system mismatches between device and scene coords.
        We position the text as close to center as possible by offsetting by half the text size.
        """
        if self._label_item is None:
            return

        # TYPE_CHECKING guard to help type checker
        if not hasattr(self, 'boundingRect'):
            return

        # Get the bounding rectangle of the parent item and its center in parent coords
        bounds = self.boundingRect()  # type: ignore[attr-defined]
        center = bounds.center()

        # Get label dimensions
        label_bounds = self._label_item.boundingRect()

        # Offset by half the label size to approximate centering
        # This is not perfect with ItemIgnoresTransformations but is close enough
        offset_x = label_bounds.width() / 2.0
        offset_y = label_bounds.height() / 2.0

        self._label_item.setPos(center.x() - offset_x, center.y() - offset_y)

    def initialize_label(self) -> None:
        """Initialize the label after the item is fully constructed.

        This should be called by subclasses after they complete their initialization.
        """
        if self._should_show_label() and self._get_display_label_text():
            self._create_label()

    def start_label_edit(self) -> None:
        """Start inline editing of the label."""
        # Hide the static label
        if self._label_item is not None:
            self._label_item.hide()

        # Create editable text item if it doesn't exist
        if self._edit_label_item is None:
            # TYPE_CHECKING guard
            if not hasattr(self, 'boundingRect'):
                return

            # Create a custom QGraphicsTextItem subclass for handling events
            class EditableLabel(QGraphicsTextItem):
                def __init__(self, text: str, parent: Any) -> None:
                    super().__init__(text, parent)
                    self.parent_item = parent

                def paint(self, painter: Any, option: Any, widget: Any = None) -> None:
                    """Override paint to remove the dashed focus border."""
                    from PyQt6.QtWidgets import QStyle
                    # Remove the focus state to prevent dashed border
                    option.state &= ~QStyle.StateFlag.State_HasFocus
                    super().paint(painter, option, widget)

                def focusOutEvent(self, event: Any) -> None:
                    """Handle focus loss - commit changes."""
                    import time
                    start_time = getattr(self.parent_item, '_label_edit_start_time', 0)
                    guard_ok = self.isVisible() and time.monotonic() - start_time < 0.2
                    super().focusOutEvent(event)
                    parent = self.parent_item
                    if guard_ok:
                        from PyQt6.QtCore import Qt as _Qt
                        from PyQt6.QtCore import QTimer
                        _self = self
                        _parent_ref = parent
                        def _refocus() -> None:
                            if not _self.isVisible():
                                return
                            import time as _t
                            _parent_ref._label_edit_start_time = _t.monotonic()
                            _self.setFocus(_Qt.FocusReason.OtherFocusReason)
                        QTimer.singleShot(0, _refocus)
                        return
                    if hasattr(parent, '_finish_label_edit'):
                        parent._finish_label_edit()

                def keyPressEvent(self, event: Any) -> None:
                    """Handle key presses - Enter/Escape to finish editing."""
                    from PyQt6.QtCore import Qt
                    if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                        if hasattr(self.parent_item, '_finish_label_edit'):
                            self.parent_item._finish_label_edit()
                        self.clearFocus()
                        event.accept()
                    elif event.key() == Qt.Key.Key_Escape:
                        if hasattr(self.parent_item, '_cancel_label_edit'):
                            self.parent_item._cancel_label_edit()
                        self.clearFocus()
                        event.accept()
                    else:
                        super().keyPressEvent(event)

            self._edit_label_item = EditableLabel(self._name, self)  # type: ignore[arg-type]

            # Configure appearance to match the static label exactly
            font = QFont("Arial", 10)
            font.setBold(True)
            self._edit_label_item.setDefaultTextColor(QColor(0, 0, 0))
            self._edit_label_item.setFont(font)

            # Remove ALL margins and padding to match QGraphicsSimpleTextItem
            from PyQt6.QtGui import QTextFrameFormat
            doc = self._edit_label_item.document()
            doc.setDocumentMargin(0)  # Critical: remove document margins

            frame_format = QTextFrameFormat()
            frame_format.setBorder(0)
            frame_format.setMargin(0)
            frame_format.setPadding(0)
            doc.rootFrame().setFrameFormat(frame_format)

            # Make it editable
            self._edit_label_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)

            # Make it ignore transformations like the static label
            self._edit_label_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)

            # Position it exactly where the static label is
            if self._label_item is not None:
                self._edit_label_item.setPos(self._label_item.pos())
            else:
                bounds = self.boundingRect()  # type: ignore[attr-defined]
                center = bounds.center()
                label_bounds = self._edit_label_item.boundingRect()
                offset_x = label_bounds.width() / 2.0
                offset_y = label_bounds.height() / 2.0
                self._edit_label_item.setPos(center.x() - offset_x, center.y() - offset_y)

            # Connect signal to reposition as text changes
            self._edit_label_item.document().contentsChanged.connect(self._reposition_edit_label)
        else:
            self._edit_label_item.setPlainText(self._name)
            self._edit_label_item.show()

        # Defer focus so Qt finishes processing the triggering mouse event first.
        # Without the timer, the final MouseButtonRelease from the double-click
        # resets the scene's focus item before the editor can accept keystrokes.
        from PyQt6.QtCore import QTimer
        _item = self._edit_label_item
        _parent = self

        def _give_focus() -> None:
            if _item is None:
                return
            import time
            _parent._label_edit_start_time = time.monotonic()
            _item.setFocus(Qt.FocusReason.OtherFocusReason)
            _cursor = _item.textCursor()
            _cursor.select(_cursor.SelectionType.Document)
            _item.setTextCursor(_cursor)

        QTimer.singleShot(0, _give_focus)

    def _reposition_edit_label(self) -> None:
        """Reposition the edit label as text changes size."""
        if self._edit_label_item is None or not hasattr(self, 'boundingRect'):
            return

        bounds = self.boundingRect()  # type: ignore[attr-defined]
        center = bounds.center()
        label_bounds = self._edit_label_item.boundingRect()
        offset_x = label_bounds.width() / 2.0
        offset_y = label_bounds.height() / 2.0
        self._edit_label_item.setPos(center.x() - offset_x, center.y() - offset_y)

    def _finish_label_edit(self) -> None:
        """Finish editing the label and save changes."""
        if self._edit_label_item is None or not self._edit_label_item.isVisible():
            return
        new_text = self._edit_label_item.toPlainText().strip()
        self._edit_label_item.hide()
        self.name = new_text
        if self._label_item is not None:
            self._label_item.show()

    def _cancel_label_edit(self) -> None:
        """Cancel editing the label without saving changes."""
        if self._edit_label_item is None:
            return
        self._edit_label_item.hide()
        if self._label_item is not None:
            self._label_item.show()

    # ------------------------------------------------------------------
    # Layer-assignment helpers (shared by all item context menus)
    # ------------------------------------------------------------------

    def _build_move_to_layer_menu(self, parent_menu: "QMenu") -> "QMenu | None":
        """Append a 'Move to Layer' submenu to *parent_menu* and return it.

        Returns ``None`` when there is only one layer (nothing to move to) or
        when the item has no scene, in which case nothing is added to the menu.
        """
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QMenu

        scene = self.scene()  # type: ignore[attr-defined]
        if not scene or not hasattr(scene, "layers"):
            return None
        layers = scene.layers
        if len(layers) <= 1:
            return None
        label = QCoreApplication.translate("GardenItemMixin", "Move to Layer")
        layer_menu: QMenu = parent_menu.addMenu(label)
        for layer in layers:
            if layer.id != self._layer_id:
                action = layer_menu.addAction(layer.name)
                action.setData(layer.id)
        return layer_menu

    def _dispatch_move_to_layer(self, target_layer_id: "uuid.UUID") -> None:
        """Move all selected items (or just *self*) to *target_layer_id*.

        Wraps the change in a :class:`MoveToLayerCommand` so that it is
        fully undoable via the command manager.
        """
        from open_garden_planner.core.commands import MoveToLayerCommand

        scene = self.scene()  # type: ignore[attr-defined]
        if not scene:
            return
        selected = [i for i in scene.selectedItems() if hasattr(i, "layer_id")]
        items = selected if selected else [self]
        target_layer = scene.get_layer_by_id(target_layer_id)
        layer_name = target_layer.name if target_layer else str(target_layer_id)
        cmd = MoveToLayerCommand(items, target_layer_id, scene, layer_name)
        if scene._command_manager:  # type: ignore[attr-defined]
            scene._command_manager.execute(cmd)  # type: ignore[attr-defined]
        else:
            cmd.execute()  # graceful fallback (e.g. in unit tests without CanvasView)

    # ------------------------------------------------------------------
    # Type-change helpers (shared by all item context menus)
    # ------------------------------------------------------------------

    def _build_change_type_menu(
        self,
        parent_menu: "QMenu",
        valid_types: list,
    ) -> "QMenu | None":
        """Append a 'Change Type' submenu to *parent_menu* and return it.

        Returns ``None`` when the item has no ``object_type`` attribute or
        the valid-types list is empty, in which case nothing is added.
        """
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QMenu

        from open_garden_planner.core.object_types import get_translated_display_name

        if not hasattr(self, "object_type") or not valid_types:
            return None
        label = QCoreApplication.translate("GardenItemMixin", "Change Type")
        type_menu: QMenu = parent_menu.addMenu(label)
        current = self.object_type  # type: ignore[attr-defined]
        for obj_type in valid_types:
            action = type_menu.addAction(get_translated_display_name(obj_type))
            action.setData(obj_type)
            action.setCheckable(True)
            action.setChecked(obj_type == current)
        return type_menu

    def _dispatch_change_type(self, new_type: object) -> None:
        """Apply an object-type change with full undo support.

        Mirrors :meth:`_dispatch_move_to_layer`: applies the change
        immediately, then pushes a :class:`ChangePropertyCommand` onto the
        undo stack so Ctrl+Z restores both type and style.  Only items of
        the same concrete class as *self* are affected (safe for mixed
        multi-selections).
        """
        from open_garden_planner.core.commands import ChangePropertyCommand
        from open_garden_planner.core.object_types import get_style

        scene = self.scene()  # type: ignore[attr-defined]
        if not scene:
            return
        selected = [
            i
            for i in scene.selectedItems()
            if type(i) is type(self) and hasattr(i, "object_type")
        ]
        items = selected if selected else [self]

        def _apply(itm: object, state: dict) -> None:
            for key, val in state.items():
                if hasattr(itm, key):
                    setattr(itm, key, val)
            if hasattr(itm, "_setup_styling"):
                itm._setup_styling()  # type: ignore[union-attr]
            if hasattr(itm, "update"):
                itm.update()  # type: ignore[union-attr]

        for item in items:
            old_state = {
                "object_type": item.object_type,  # type: ignore[union-attr]
                "fill_color": getattr(item, "fill_color", None),
                "fill_pattern": getattr(item, "fill_pattern", None),
                "stroke_color": getattr(item, "stroke_color", None),
                "stroke_width": getattr(item, "stroke_width", None),
                "stroke_style": getattr(item, "stroke_style", None),
            }
            style = get_style(new_type)  # type: ignore[arg-type]
            new_state = {
                "object_type": new_type,
                "fill_color": style.fill_color,
                "fill_pattern": style.fill_pattern,
                "stroke_color": style.stroke_color,
                "stroke_width": style.stroke_width,
                "stroke_style": style.stroke_style,
            }
            _apply(item, new_state)
            cmd = ChangePropertyCommand(item, "type", old_state, new_state, _apply)
            if hasattr(scene, "_command_manager") and scene._command_manager:  # type: ignore[attr-defined]
                scene._command_manager._undo_stack.append(cmd)  # type: ignore[attr-defined]
                scene._command_manager._redo_stack.clear()  # type: ignore[attr-defined]
                scene._command_manager.can_undo_changed.emit(True)  # type: ignore[attr-defined]
                scene._command_manager.can_redo_changed.emit(False)  # type: ignore[attr-defined]

        # Refresh the properties panel by re-emitting the selection signal
        scene.selectionChanged.emit()  # type: ignore[attr-defined]
