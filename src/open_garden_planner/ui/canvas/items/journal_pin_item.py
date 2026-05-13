"""Garden journal pin item (US-12.9).

A small map-pin glyph anchored to a scene point. Carries only a
``note_id`` reference back to ``ProjectData.garden_journal_notes`` — the
note body lives there so the sidebar panel and PDF page can iterate
notes without scanning the scene.

Rendered with :attr:`QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations`
so the pin stays at a constant screen-pixel size regardless of zoom (and so
the canvas Y-flip does not mirror the drop shape).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QMenu,
)

from open_garden_planner.core.object_types import ObjectType

from .garden_item import GardenItemMixin

if TYPE_CHECKING:
    from PyQt6.QtWidgets import (
        QGraphicsSceneContextMenuEvent,
        QGraphicsSceneMouseEvent,
        QStyleOptionGraphicsItem,
        QWidget,
    )


# Screen-pixel sizes (ItemIgnoresTransformations means local units = screen px).
_PIN_BODY_RADIUS: float = 7.0
_PIN_HEIGHT: float = 22.0       # tip-to-top distance
_PIN_DOT_RADIUS: float = 2.0

_FILL_COLOR = QColor(255, 200, 0)
_OUTLINE_COLOR = QColor(120, 80, 0)
_DOT_COLOR = QColor(60, 40, 0)
_SELECTION_COLOR = QColor(0, 100, 255)


class JournalPinItem(GardenItemMixin, QGraphicsObject):
    """Standalone canvas pin linking a scene location to a journal note."""

    def __init__(
        self,
        x: float,
        y: float,
        note_id: str,
        layer_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        GardenItemMixin.__init__(
            self,
            object_type=ObjectType.GARDEN_JOURNAL_PIN,
            layer_id=layer_id,
            metadata=metadata,
        )
        QGraphicsObject.__init__(self)

        self._note_id: str = note_id

        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Pins sit above structural items so they remain clickable when overlapping.
        self.setZValue(9_500)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self.setToolTip(
            QCoreApplication.translate(
                "JournalPinItem", "Garden journal note (double-click to edit)"
            )
        )

    # ── Properties ───────────────────────────────────────────────

    @property
    def note_id(self) -> str:
        return self._note_id

    # ── Geometry / painting ──────────────────────────────────────

    def _pin_path(self) -> QPainterPath:
        """Drop-shaped pin: rounded body on top, tip at (0,0) pointing down.

        Because the parent flag is ``ItemIgnoresTransformations``, ``y`` axis
        in local coords matches screen y (positive = down), so the body sits
        at negative-y above the tip.
        """
        path = QPainterPath()
        r = _PIN_BODY_RADIUS
        h = _PIN_HEIGHT
        body_cy = -(h - r)
        # Tip
        path.moveTo(0.0, 0.0)
        # Right edge curving up into the body circle
        path.cubicTo(
            QPointF(r * 0.55, -r * 0.7),
            QPointF(r, body_cy + r * 0.4),
            QPointF(r, body_cy),
        )
        # Top half of the body (arc the long way around)
        path.arcTo(QRectF(-r, body_cy - r, 2 * r, 2 * r), 0.0, 180.0)
        # Left edge back down to the tip
        path.cubicTo(
            QPointF(-r, body_cy + r * 0.4),
            QPointF(-r * 0.55, -r * 0.7),
            QPointF(0.0, 0.0),
        )
        path.closeSubpath()
        return path

    def boundingRect(self) -> QRectF:  # noqa: N802
        r = _PIN_BODY_RADIUS
        h = _PIN_HEIGHT
        # Include a small selection-border margin.
        margin = 2.0
        return QRectF(-r - margin, -h - margin, 2 * (r + margin), h + 2 * margin)

    def shape(self) -> QPainterPath:
        return self._pin_path()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        from PyQt6.QtWidgets import QStyle  # noqa: PLC0415

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = self._pin_path()
        painter.setBrush(QBrush(_FILL_COLOR))
        painter.setPen(QPen(_OUTLINE_COLOR, 1.2))
        painter.drawPath(path)

        # Inner dot in the body so the pin reads as a "pin head".
        body_cy = -(_PIN_HEIGHT - _PIN_BODY_RADIUS)
        painter.setBrush(QBrush(_DOT_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(0.0, body_cy), _PIN_DOT_RADIUS, _PIN_DOT_RADIUS
        )

        if option.state & QStyle.StateFlag.State_Selected:
            sel_pen = QPen(_SELECTION_COLOR, 1.5, Qt.PenStyle.DashLine)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

    # ── Interaction ──────────────────────────────────────────────

    def _emit_to_view(self, action: str) -> None:
        """Forward an action to the canvas view via duck-typed callbacks.

        We avoid signals on the item itself so the pin can be loaded from
        ``.ogp`` without per-item wiring. The view exposes
        ``request_journal_note_edit`` and ``request_journal_note_delete``
        for this.
        """
        scene = self.scene()
        if scene is None:
            return
        views = scene.views()
        if not views:
            return
        view = views[0]
        handler = getattr(view, f"request_journal_note_{action}", None)
        if callable(handler):
            handler(self._note_id)

    def mouseDoubleClickEvent(  # noqa: N802 (Qt API)
        self, event: QGraphicsSceneMouseEvent
    ) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_to_view("edit")
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(  # noqa: N802 (Qt API)
        self, event: QGraphicsSceneContextMenuEvent
    ) -> None:
        _ = QCoreApplication.translate
        menu = QMenu()
        edit_action = menu.addAction(_("JournalPinItem", "Edit Note…"))
        delete_action = menu.addAction(_("JournalPinItem", "Delete"))
        chosen = menu.exec(event.screenPos())
        if chosen is edit_action:
            self._emit_to_view("edit")
        elif chosen is delete_action:
            self._emit_to_view("delete")

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "journal_pin",
            "item_id": str(self.item_id),
            "note_id": self._note_id,
            "x": self.pos().x(),
            "y": self.pos().y(),
        }
        if self._layer_id is not None:
            data["layer_id"] = str(self._layer_id)
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> JournalPinItem:
        import contextlib  # noqa: PLC0415

        layer_id: uuid.UUID | None = None
        if "layer_id" in d:
            with contextlib.suppress(ValueError, AttributeError):
                layer_id = uuid.UUID(d["layer_id"])
        item = cls(
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            note_id=str(d.get("note_id", "")),
            layer_id=layer_id,
        )
        if "item_id" in d:
            with contextlib.suppress(ValueError, TypeError):
                item._item_id = uuid.UUID(d["item_id"])
        return item


__all__ = ["JournalPinItem"]
