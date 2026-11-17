"""Mutation notices for screen-sized editing decorations.

These items change without changing plan geometry (vertex modes, resampling,
hover tools). Their retained spacing-ring exclusions need their own notices.
"""

from typing import Any, cast

from PyQt6.QtWidgets import QGraphicsItem


def note_edit_decoration_changed(item: QGraphicsItem) -> None:
    invalidate = getattr(item.scene(), "invalidate_edit_decoration_covers", None)
    if invalidate is not None:
        invalidate()


class EditDecorationMixin:
    """Cooperative mixin before a concrete Qt graphics-item base."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast(QGraphicsItem, self).setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change in {
            QGraphicsItem.GraphicsItemChange.ItemSceneChange,
            QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemParentHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemScaleHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemTransformOriginPointHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemFlagsHaveChanged,
        }:
            note_edit_decoration_changed(cast(QGraphicsItem, self))
        # The next MRO entry is the concrete Qt item; the standalone mixin
        # deliberately does not inherit a second SIP/C++ graphics-item base.
        return super().itemChange(change, value)  # type: ignore[misc]
