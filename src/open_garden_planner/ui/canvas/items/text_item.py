"""Text annotation item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPen,
    QTextCursor,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType

from .garden_item import GardenItemMixin
from .resize_handle import RotationHandleMixin


class TextItem(RotationHandleMixin, GardenItemMixin, QGraphicsTextItem):
    """A text annotation on the garden canvas.

    Supports free placement, inline editing on double-click,
    configurable font properties, rotation, and serialization.
    """

    # Conversion: 1 cm = 72/2.54 ≈ 28.35 pt (screen points at 72 dpi)
    _CM_TO_PT: float = 72.0 / 2.54

    def __init__(
        self,
        x: float,
        y: float,
        content: str = "",
        font_family: str = "Arial",
        font_size: float = 1.0,
        bold: bool = False,
        italic: bool = False,
        text_color: QColor | None = None,
        layer_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the text item.

        Args:
            x: X position in scene coordinates
            y: Y position in scene coordinates
            content: Text content
            font_family: Font family name
            font_size: Font size in cm (scene units), default 1 cm
            bold: Whether text is bold
            italic: Whether text is italic
            text_color: Text color (defaults to black)
            layer_id: Layer ID this item belongs to
            metadata: Optional metadata dictionary
        """
        GardenItemMixin.__init__(
            self,
            object_type=ObjectType.GENERIC_TEXT,
            layer_id=layer_id,
            metadata=metadata,
        )
        QGraphicsTextItem.__init__(self)

        self.init_rotation_handle()

        if text_color is None:
            text_color = QColor(0, 0, 0)

        self._content = content
        self._font_family = font_family
        self._font_size = font_size  # stored in cm
        self._bold = bold
        self._italic = italic
        self._text_color = text_color
        self._editing = False

        # Counter-transform for the canvas Y-flip (view applies scale(zoom, -zoom)).
        # Flipping Y locally makes the text appear right-side-up on screen.
        self.setTransform(QTransform().scale(1.0, -1.0))

        self.setPos(x, y)
        self._apply_font()
        self.setPlainText(content)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Disable text editing until double-clicked
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    # ── Font / content properties ────────────────────────────────

    @property
    def content(self) -> str:
        """Text content."""
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        self._content = value
        self.setPlainText(value)

    @property
    def font_family(self) -> str:
        return self._font_family

    @font_family.setter
    def font_family(self, value: str) -> None:
        self._font_family = value
        self._apply_font()

    @property
    def font_size(self) -> float:
        return self._font_size

    @font_size.setter
    def font_size(self, value: float) -> None:
        self._font_size = max(0.1, value)  # minimum 0.1 cm
        self._apply_font()

    @property
    def bold(self) -> bool:
        return self._bold

    @bold.setter
    def bold(self, value: bool) -> None:
        self._bold = value
        self._apply_font()

    @property
    def italic(self) -> bool:
        return self._italic

    @italic.setter
    def italic(self, value: bool) -> None:
        self._italic = value
        self._apply_font()

    @property
    def text_color(self) -> QColor:
        return self._text_color

    @text_color.setter
    def text_color(self, value: QColor) -> None:
        self._text_color = value
        self.setDefaultTextColor(value)

    def _apply_font(self) -> None:
        """Apply current font settings (font_size stored in cm, converted to pt)."""
        pt = max(1, round(self._font_size * self._CM_TO_PT))
        font = QFont(self._font_family, pt)
        font.setBold(self._bold)
        font.setItalic(self._italic)
        self.setFont(font)
        self.setDefaultTextColor(self._text_color)

    # ── Editing ──────────────────────────────────────────────────

    def start_editing(self) -> None:
        """Enter inline text editing mode."""
        self._editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)

    def _commit_edit(self) -> None:
        """Commit the current text and exit editing mode."""
        if not self._editing:
            return
        self._editing = False
        self._content = self.toPlainText()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Clear selection
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.clearFocus()

    # ── Qt event overrides ───────────────────────────────────────

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Double-click enters edit mode."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_editing()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """In edit mode pass to text item; otherwise handle as movable item."""
        if self._editing:
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        """Commit text when focus is lost."""
        if self._editing:
            self._commit_edit()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Escape exits edit mode; Enter/Tab pass through while editing."""
        if self._editing and event.key() == Qt.Key.Key_Escape:
            self._commit_edit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show right-click context menu."""
        menu = QMenu()

        edit_action = menu.addAction(self.tr("Edit Text"))

        menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Delete"))

        chosen = menu.exec(event.screenPos())
        if chosen == edit_action:
            self.start_editing()
        elif chosen == delete_action:
            scene = self.scene()
            if scene:
                scene.removeItem(self)
        elif move_layer_menu and chosen and chosen.parent() is move_layer_menu:
            self._dispatch_move_to_layer(chosen.data())

    # ── Visual / bounding ────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        """Return bounding rect expanded slightly for visual affordance."""
        base = super().boundingRect()
        m = self._shadow_margin()
        if m > 0:
            base = base.adjusted(-m, -m, m, m)
        return base

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint with selection indicator when selected."""
        from PyQt6.QtWidgets import QStyle
        # Remove focus box drawn by Qt (we draw our own selection box)
        option.state &= ~QStyle.StateFlag.State_HasFocus

        # Draw a thin dashed selection border when selected and not editing
        if (option.state & QStyle.StateFlag.State_Selected) and not self._editing:
            painter.save()
            pen = QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(super().boundingRect())
            painter.restore()

        super().paint(painter, option, widget)

    # ── Selection handle lifecycle ───────────────────────────────

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: Any
    ) -> Any:
        """Show/hide rotation handle on selection change."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.show_rotation_handle()
            else:
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()
        return super().itemChange(change, value)
