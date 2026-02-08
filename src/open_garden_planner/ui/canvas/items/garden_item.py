"""Base mixin for garden canvas items."""

import uuid
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsSimpleTextItem, QGraphicsTextItem

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
    """

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
        self._label_item: QGraphicsSimpleTextItem | None = None
        self._edit_label_item: QGraphicsTextItem | None = None

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
                    super().focusOutEvent(event)
                    if hasattr(self.parent_item, '_finish_label_edit'):
                        self.parent_item._finish_label_edit()

                def keyPressEvent(self, event: Any) -> None:
                    """Handle key presses - Enter/Escape to finish editing."""
                    from PyQt6.QtCore import Qt
                    if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                        # Commit on Enter
                        if hasattr(self.parent_item, '_finish_label_edit'):
                            self.parent_item._finish_label_edit()
                        self.clearFocus()
                        event.accept()
                    elif event.key() == Qt.Key.Key_Escape:
                        # Cancel on Escape - restore original text
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
                # Copy the exact position from the static label
                self._edit_label_item.setPos(self._label_item.pos())
            else:
                # Fallback positioning if no static label exists
                bounds = self.boundingRect()  # type: ignore[attr-defined]
                center = bounds.center()
                label_bounds = self._edit_label_item.boundingRect()
                offset_x = label_bounds.width() / 2.0
                offset_y = label_bounds.height() / 2.0
                self._edit_label_item.setPos(center.x() - offset_x, center.y() - offset_y)

            # Connect signal to reposition as text changes
            self._edit_label_item.document().contentsChanged.connect(self._reposition_edit_label)
        else:
            # Update text and show
            self._edit_label_item.setPlainText(self._name)
            self._edit_label_item.show()

        # Give it focus and select all text
        self._edit_label_item.setFocus()
        cursor = self._edit_label_item.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self._edit_label_item.setTextCursor(cursor)

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

        # Get the edited text
        new_text = self._edit_label_item.toPlainText().strip()

        # Hide the edit item
        self._edit_label_item.hide()

        # Update the name (this will update or remove the static label)
        self.name = new_text

        # Show the static label again if there's text
        if self._label_item is not None:
            self._label_item.show()

    def _cancel_label_edit(self) -> None:
        """Cancel editing the label without saving changes."""
        if self._edit_label_item is None:
            return

        # Hide the edit item
        self._edit_label_item.hide()

        # Show the static label again
        if self._label_item is not None:
            self._label_item.show()
