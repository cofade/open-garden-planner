"""Callout / leader-line annotation item for the garden canvas."""

import math
import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
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


class CalloutItem(RotationHandleMixin, GardenItemMixin, QGraphicsItem):
    """Callout annotation: leader line with arrowhead pointing at a target + text box.

    The item is positioned at the arrow tip (scene pos = target point).
    _box_offset is the text box top-left relative to the arrow tip.
    """

    _ARROW_SIZE: float = 10.0
    _BOX_PADDING: float = 4.0
    _BOX_RADIUS: float = 3.0
    _FONT_FAMILY: str = "Arial"
    _FONT_SIZE_PT: int = 10

    def __init__(
        self,
        target: QPointF,
        box_offset: QPointF,
        content: str = "",
        layer_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        GardenItemMixin.__init__(
            self,
            object_type=ObjectType.GENERIC_CALLOUT,
            layer_id=layer_id,
            metadata=metadata,
        )
        QGraphicsItem.__init__(self)
        self.init_rotation_handle()

        self._box_offset: QPointF = box_offset
        self._content: str = content
        self._editing: bool = False

        # Child text item with Y-flip (same trick as TextItem for the canvas Y-axis flip)
        self._text_child = QGraphicsTextItem(content, self)
        self._text_child.setTransform(QTransform().scale(1.0, -1.0))
        font = QFont(self._FONT_FAMILY, self._FONT_SIZE_PT)
        self._text_child.setFont(font)
        self._text_child.setDefaultTextColor(QColor(0, 0, 0))
        self._text_child.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._text_child.document().setDocumentMargin(0)
        self._update_text_pos()

        self.setPos(target)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    # ── Properties ───────────────────────────────────────────────

    @property
    def content(self) -> str:
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        self._content = value
        self._text_child.setPlainText(value)

    @property
    def box_offset(self) -> QPointF:
        return QPointF(self._box_offset)

    # ── Geometry ─────────────────────────────────────────────────

    def _text_box_rect(self) -> QRectF:
        """Return the text box QRectF in item-local coords (includes padding)."""
        tr = self._text_child.boundingRect()
        p = self._BOX_PADDING
        return QRectF(
            self._box_offset.x() - p,
            self._box_offset.y() - p,
            tr.width() + 2 * p,
            tr.height() + 2 * p,
        )

    def boundingRect(self) -> QRectF:
        # Union of: arrowhead area + leader line + text box
        arrow_pad = self._ARROW_SIZE
        origin_rect = QRectF(-arrow_pad, -arrow_pad, 2 * arrow_pad, 2 * arrow_pad)
        box = self._text_box_rect()
        # Include leader line
        line_rect = QRectF(
            min(0.0, self._box_offset.x()),
            min(0.0, self._box_offset.y()),
            abs(self._box_offset.x()),
            abs(self._box_offset.y()),
        ).normalized()
        result = origin_rect.united(box).united(line_rect)
        m = self._shadow_margin()
        if m > 0:
            result = result.adjusted(-m, -m, m, m)
        return result

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def _update_text_pos(self) -> None:
        """Place the text child at _box_offset (compensating for Y-flip)."""
        tr = self._text_child.boundingRect()
        # With scale(1,-1) the text child's local (0,0) is its top-left when unflipped,
        # but after the Y-flip it maps to bottom-left. Adjust y so the visible top of
        # the text box aligns with _box_offset.y.
        self._text_child.setPos(
            self._box_offset.x(),
            self._box_offset.y() + tr.height(),
        )

    # ── Painting ──────────────────────────────────────────────────

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,  # noqa: ARG002
    ) -> None:
        from PyQt6.QtWidgets import QStyle

        painter.save()

        # Leader line
        pen = QPen(QColor(30, 30, 30), 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(0, 0), self._box_offset)

        # Arrowhead (filled triangle at origin pointing toward box)
        dx = self._box_offset.x()
        dy = self._box_offset.y()
        length = math.hypot(dx, dy)
        if length > 1e-6:
            ux = dx / length
            uy = dy / length
        else:
            ux, uy = 1.0, 0.0
        size = self._ARROW_SIZE
        # base of arrow = one ARROW_SIZE step along leader from origin
        base_x = ux * size
        base_y = uy * size
        # perpendicular
        perp_x = -uy * size * 0.4
        perp_y = ux * size * 0.4
        arrow = QPolygonF([
            QPointF(0, 0),
            QPointF(base_x + perp_x, base_y + perp_y),
            QPointF(base_x - perp_x, base_y - perp_y),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 30)))
        painter.drawPolygon(arrow)

        # Text box background (rounded rect)
        box = self._text_box_rect()
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        box_pen = QPen(QColor(120, 120, 120), 1.0)
        box_pen.setCosmetic(True)
        painter.setPen(box_pen)
        painter.drawRoundedRect(box, self._BOX_RADIUS, self._BOX_RADIUS)

        # Selection indicator
        if option.state & QStyle.StateFlag.State_Selected and not self._editing:
            sel_pen = QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

        painter.restore()

    # ── Editing ───────────────────────────────────────────────────

    def start_editing(self) -> None:
        """Enter inline text editing mode."""
        self._editing = True
        self._text_child.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._text_child.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self._text_child.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self._text_child.setTextCursor(cursor)

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self._content = self._text_child.toPlainText()
        self._text_child.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        cursor = self._text_child.textCursor()
        cursor.clearSelection()
        self._text_child.setTextCursor(cursor)
        self._text_child.clearFocus()

    # ── Qt events ─────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_editing()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        if self._editing:
            self._commit_edit()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._editing and event.key() in (Qt.Key.Key_Escape,):
            self._commit_edit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        _ = QCoreApplication.translate
        menu = QMenu()
        edit_action = menu.addAction(_("CalloutItem", "Edit Text"))
        move_layer_menu = self._build_move_to_layer_menu(menu)
        menu.addSeparator()
        delete_action = menu.addAction(_("CalloutItem", "Delete"))
        chosen = menu.exec(event.screenPos())
        if chosen == edit_action:
            self.start_editing()
        elif chosen == delete_action:
            scene = self.scene()
            if scene:
                scene.removeItem(self)
        elif move_layer_menu and chosen and chosen.parent() is move_layer_menu:
            self._dispatch_move_to_layer(chosen.data())

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: Any
    ) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.show_rotation_handle()
            else:
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()
        return super().itemChange(change, value)

    # ── Serialization ─────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "callout",
            "target_x": self.pos().x(),
            "target_y": self.pos().y(),
            "box_dx": self._box_offset.x(),
            "box_dy": self._box_offset.y(),
            "content": self._content,
        }
        if self._name:
            data["name"] = self._name
        if self._layer_id is not None:
            data["layer_id"] = str(self._layer_id)
        if self._metadata:
            data["metadata"] = self._metadata
        if hasattr(self, "rotation_angle") and abs(self.rotation_angle) > 0.01:
            data["rotation_angle"] = self.rotation_angle
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalloutItem":
        import contextlib

        layer_id = None
        if "layer_id" in d:
            with contextlib.suppress(ValueError, AttributeError):
                layer_id = uuid.UUID(d["layer_id"])
        item = cls(
            target=QPointF(d.get("target_x", 0.0), d.get("target_y", 0.0)),
            box_offset=QPointF(d.get("box_dx", 80.0), d.get("box_dy", -60.0)),
            content=d.get("content", ""),
            layer_id=layer_id,
            metadata=d.get("metadata"),
        )
        if "name" in d:
            item._name = d["name"]
        if "rotation_angle" in d:
            item._apply_rotation(d["rotation_angle"])
        return item
