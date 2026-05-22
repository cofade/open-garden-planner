"""Simple title-block item for the Paper Space layout (MVP).

A title block sits in a corner of the page and shows three fields:
    - project name (auto-pulled from the active project filename)
    - date (auto = today, format YYYY-MM-DD)
    - scale (auto-derived from the layout's primary viewport)

This MVP intentionally has no field customisation; later iterations
will add user-defined fields and templates.
"""

from __future__ import annotations

from datetime import date as _date_cls

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

_DEFAULT_WIDTH_CM = 7.0
_DEFAULT_HEIGHT_CM = 3.0
_PADDING_CM = 0.25


class TitleBlockItem(QGraphicsRectItem):
    """Three-line title block: project / date / scale."""

    def __init__(
        self,
        project_name: str = "",
        date_iso: str | None = None,
        scale_label: str = "",
    ) -> None:
        super().__init__(QRectF(0, 0, _DEFAULT_WIDTH_CM, _DEFAULT_HEIGHT_CM))
        self._project_name = project_name
        self._date_iso = date_iso or _date_cls.today().isoformat()
        self._scale_label = scale_label

        # The title block is a layout decoration, not a user-positionable
        # drawing object. Making it movable/selectable led to users
        # accidentally dragging it (PR #191 manual-test feedback —
        # leaves smear trails on move because the selection-rendered
        # bounding rect doesn't cover the dashed indicator).
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        pen = QPen(QColor(20, 20, 20), 0.4)
        pen.setCosmetic(False)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 255, 255)))

    # ── Field accessors ────────────────────────────────────────────────

    @property
    def project_name(self) -> str:
        return self._project_name

    @project_name.setter
    def project_name(self, value: str) -> None:
        self._project_name = value
        self.update()

    @property
    def date_iso(self) -> str:
        return self._date_iso

    @date_iso.setter
    def date_iso(self, value: str) -> None:
        self._date_iso = value
        self.update()

    @property
    def scale_label(self) -> str:
        return self._scale_label

    @scale_label.setter
    def scale_label(self, value: str) -> None:
        self._scale_label = value
        self.update()

    # ── Painting ───────────────────────────────────────────────────────

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        super().paint(painter, option, widget)
        rect = self.rect()

        # MVP: only the box + horizontal dividers are drawn. The
        # Project / Date / Scale fields are tracked in the item's data
        # (and persist through save/reload) but the actual text
        # rendering is deferred to issue #194 — both `setPointSizeF`
        # and `setPixelSize` in a Y-flipped, transformed paint()
        # produced visual artefacts (invisible glyphs and white-bar
        # placeholders respectively) on the PR #191 manual-test
        # baseline. That UX pass will replace the manual painter.drawText
        # with QGraphicsSimpleTextItem children, which Qt renders
        # predictably in transformed scenes.
        painter.save()
        line_h = rect.height() / 3.0
        for i in (1, 2):
            y = rect.y() + i * line_h
            painter.drawLine(
                int(rect.x()),
                int(y),
                int(rect.x() + rect.width()),
                int(y),
            )
        painter.restore()

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float | str]:
        r = self.rect()
        pos = self.pos()
        return {
            "type": "title_block",
            "x": pos.x(),
            "y": pos.y(),
            "width": r.width(),
            "height": r.height(),
            "project_name": self._project_name,
            "date_iso": self._date_iso,
            "scale_label": self._scale_label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | str]) -> TitleBlockItem:
        item = cls(
            project_name=str(data.get("project_name", "")),
            date_iso=str(data.get("date_iso", "")) or None,
            scale_label=str(data.get("scale_label", "")),
        )
        from PyQt6.QtCore import QPointF

        item.setRect(
            0.0,
            0.0,
            float(data.get("width", _DEFAULT_WIDTH_CM)),
            float(data.get("height", _DEFAULT_HEIGHT_CM)),
        )
        item.setPos(QPointF(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        return item
