"""Canvas text that stays readable on any background: glyphs over a stroked halo.

A label on the plan lies on a red roof, dark soil, a bright lawn or the grey
around the plan, and its colour cannot suit them all. So no label relies on what
is under it: the glyph outlines are stroked first in a colour the ink contrasts
with (``core.legibility``), then the text is drawn over that. Stroking the
*outline path* is the point: ``QPainter.drawText`` with a wide pen does not
outline anything, which is how the scale bar's "halo" never showed (#793).

Three users share this module:

* ``paint_halo_text`` — immediate painting (the view's scale bar);
* ``HaloTextItem`` — a ``QGraphicsSimpleTextItem`` with a halo (dimension
  and constraint labels). It stays that class on purpose: the export paths find
  text by ``isinstance(item, QGraphicsSimpleTextItem)`` to resize it;
* ``PlanLabelItem`` — an object's name or area label. It is centred on its
  anchor at every zoom and is painted by the scene AFTER all items
  (``CanvasScene.drawForeground``), so a later-drawn object cannot cover it.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextLayout,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.legibility import halo_for, legible_ink

#: Width of the stroke under the glyphs as a share of the font's ascent; half of
#: it shows around each glyph. A share, not a pixel count: an export gives the
#: labels another font size, and the halo has to grow and shrink with the text.
#: At the canvas's 10 pt label this is 5 px, 2.5 px around each glyph.
HALO_WIDTH_RATIO = 0.4
#: ...but never thinner than this: under 1.5 px a halo no longer separates.
HALO_MIN_WIDTH_PX = 3.0
#: The halo is opaque: a see-through halo takes on the background's tone and
#: the contrast it is there for is gone.
HALO_ALPHA = 255


def note_label_changed(item: QGraphicsItem) -> None:
    """Tell ``item``'s scene that a label of the plan changed what it shows:
    its text, its size, whether it is visible, whether it is in the scene.

    The scene keeps each viewport's label layout until its paint revision
    moves (``plan_labels.LabelPass``), and Qt's ``changed`` does not carry
    these: hiding or showing an item that ignores transformations emits
    nothing (measured, PF-CAN-60). A scene without a label pass has no
    ``note_paint_changed`` and nothing is told.
    """
    note = getattr(item.scene(), "note_paint_changed", None)
    if note is not None:
        note()


#: The changes of a label item that change the layout of the plan's labels.
#: ``ItemSceneChange`` is sent while the item is still in the scene it leaves.
LABEL_LAYOUT_CHANGES = frozenset({
    QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged,
    QGraphicsItem.GraphicsItemChange.ItemSceneChange,
    QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged,
    QGraphicsItem.GraphicsItemChange.ItemParentHasChanged,
})


def halo_colors(requested: QColor) -> tuple[QColor, QColor]:
    """The ink to paint and the halo under it, for a requested text colour.

    A dark ink gets the light halo and a light ink the dark one; an ink that
    does not reach ``core.legibility.INK_CONTRAST_TARGET`` against its halo is
    moved away from it, hue kept, until it does.
    """
    rgb = (requested.red(), requested.green(), requested.blue())
    halo = halo_for(rgb)
    ink = QColor(*legible_ink(rgb, halo), requested.alpha())
    return ink, QColor(*halo, HALO_ALPHA)


def halo_width(font: QFont) -> float:
    """Width of the halo stroke for text in ``font``, in the font's own pixels."""
    return max(HALO_MIN_WIDTH_PX, HALO_WIDTH_RATIO * QFontMetricsF(font).ascent())


def halo_pen(halo: QColor, font: QFont) -> QPen:
    """The pen that strokes a glyph outline in ``font`` into a halo."""
    pen = QPen(halo, halo_width(font))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def text_outline(text: str, font: QFont, origin: QPointF | None = None) -> QPainterPath:
    """The outline of ``text`` with its top-left corner at ``origin``.

    The glyphs are put where ``QGraphicsSimpleTextItem`` draws them: the text
    is laid out the way that class lays it out, and each glyph's outline is
    taken at the place the layout gives it. ``QPainterPath.addText`` lays the
    text out a second time, by its own rules, and the two do not agree: a
    hinted layout rounds every advance to a whole pixel, and the outline of a
    bold face came out at the regular width. Measured on Windows, a bold 10 pt
    "Perennial border" ended 3.9 px past such an outline, where the halo
    reaches 2.5 px: the last letters stood outside their halo.
    """
    top_left = origin if origin is not None else QPointF(0.0, 0.0)
    layout = QTextLayout(text.replace("\n", "\u2028"), font)
    layout.beginLayout()
    while layout.createLine().isValid():
        pass
    layout.endLayout()
    # A line has its height only once the next one is begun (or the layout is
    # ended), so the lines are stacked afterwards, as Qt's own item does.
    height = 0.0
    for index in range(layout.lineCount()):
        line = layout.lineAt(index)
        line.setPosition(QPointF(0.0, height))
        height += line.height()
    path = QPainterPath()
    for run in layout.glyphRuns():
        raw_font = run.rawFont()
        for glyph, position in zip(run.glyphIndexes(), run.positions(), strict=True):
            path.addPath(raw_font.pathForGlyph(glyph).translated(top_left + position))
    return path


def paint_halo_text(
    painter: QPainter, baseline: QPointF, text: str, font: QFont, color: QColor
) -> None:
    """Paint one line of ``text`` at ``baseline`` over its halo."""
    ink, halo = halo_colors(color)
    path = QPainterPath()
    path.addText(baseline, font, text)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.strokePath(path, halo_pen(halo, font))
    painter.fillPath(path, QBrush(ink))
    painter.restore()


class HaloTextItem(QGraphicsSimpleTextItem):
    """A simple text item whose glyphs lie on a halo.

    ``setBrush`` keeps its meaning (the text colour); the colour actually used
    is the legible one of ``halo_colors``. With ``centered=True`` the text is
    centred on the item's position instead of hanging below-right of it. For an
    ``ItemIgnoresTransformations`` label that is the only way to centre it at
    every zoom: its position is in plan units and its size in pixels, so an
    offset computed from one cannot cancel the other.
    """

    def __init__(
        self,
        text: str = "",
        parent: QGraphicsItem | None = None,
        *,
        centered: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self._centered = centered
        self._screen_offset = QPointF(0.0, 0.0)
        self._stacked_under: HaloTextItem | None = None
        self._halo_color = QColor(255, 255, 255, HALO_ALPHA)
        self._outline_key: tuple[str, str] | None = None
        self._outline = QPainterPath()
        self._measured: tuple[QRectF, float] | None = None
        self._picture_key: tuple[str, str, int, int, float] | None = None
        self._picture_cache = QPixmap()
        self.setBrush(QColor(0, 0, 0))

    def setFont(self, font: QFont) -> None:
        """Set the font; the text's measured size is taken again."""
        super().setFont(font)
        self._measured = None

    def setText(self, text: str | None) -> None:
        """Set the text; its measured size is taken again."""
        super().setText(text)
        self._measured = None

    def _measure(self) -> tuple[QRectF, float]:
        """The text's own rect at the origin and the margin its halo needs.

        Kept between paints: the label pass asks every label for its rect on
        every repaint, and measuring a font is the costly part of the answer.
        """
        if self._measured is None:
            self._measured = (
                super().boundingRect(), halo_width(self.font()) / 2.0 + 1.0
            )
        return self._measured

    def setBrush(self, brush: QBrush | QColor | Qt.GlobalColor | int | QGradient) -> None:
        """Set the text colour; the halo and the legible ink follow from it."""
        ink, self._halo_color = halo_colors(QBrush(brush).color())
        super().setBrush(QBrush(ink))

    def halo_color(self) -> QColor:
        """The colour of the halo under the glyphs."""
        return QColor(self._halo_color)

    def set_screen_offset(self, dx: float, dy: float) -> None:
        """Shift the text ``(dx, dy)`` screen pixels from its anchor (x right, y down)."""
        offset = QPointF(dx, dy)
        if offset == self._screen_offset:
            return
        self.prepareGeometryChange()
        self._screen_offset = offset
        self.update()

    def stack_under(self, other: HaloTextItem | None) -> None:
        """Hang this text one line below ``other`` while ``other`` is shown.

        Both hang on the same anchor (an object's centre). The step is taken
        from the two texts' sizes when it is needed, not stored: an export
        gives both another font size, and a stored step would be the canvas's.
        """
        if other is self._stacked_under:
            return
        self.prepareGeometryChange()
        self._stacked_under = other
        self.update()

    def text_rect(self) -> QRectF:
        """The text's own rect (no halo) in item coordinates, where it is painted."""
        rect = self._measure()[0]
        return rect.translated(self._origin(rect))

    def _origin(self, text_rect: QRectF) -> QPointF:
        """Where the text's top-left corner is painted."""
        dx, dy = self._screen_offset.x(), self._screen_offset.y()
        above = self._stacked_under
        if above is not None and above.isVisible():
            above_height = above._measure()[0].height()
            dy += (above_height + text_rect.height()) / 2.0 + self._measure()[1] - 1.0
        if self._centered:
            return QPointF(dx - text_rect.width() / 2.0, dy - text_rect.height() / 2.0)
        return QPointF(dx, dy)

    def boundingRect(self) -> QRectF:
        margin = self._measure()[1]
        return self.text_rect().adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def _text_outline(self) -> QPainterPath:
        key = (self.text(), self.font().key())
        if key != self._outline_key:
            self._outline = text_outline(self.text(), self.font())
            self._outline_key = key
        return self._outline

    def _paint_vector(
        self,
        painter: QPainter,
        origin: QPointF,
        option: QStyleOptionGraphicsItem | None = None,
        widget: QWidget | None = None,
    ) -> None:
        """Stroke the halo and draw the text with its top-left corner at ``origin``."""
        painter.save()
        painter.translate(origin)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.strokePath(self._text_outline(), halo_pen(self._halo_color, self.font()))
        super().paint(painter, option or QStyleOptionGraphicsItem(), widget)
        painter.restore()

    def _picture(self, pixel_ratio: float) -> QPixmap:
        """The label as a picture, kept until its text, font or colours change.

        Stroking a glyph outline costs about half a millisecond a label; a
        plan with fifty named objects paid 40 ms on every repaint for it. On
        screen the label never changes with the zoom (it ignores the view's
        transformations), so one picture serves every paint.
        """
        key = (
            self.text(), self.font().key(), self.brush().color().rgba(),
            self._halo_color.rgba(), pixel_ratio,
        )
        if key != self._picture_key:
            text_rect, margin = self._measure()
            picture = QPixmap(
                math.ceil((text_rect.width() + 2.0 * margin) * pixel_ratio),
                math.ceil((text_rect.height() + 2.0 * margin) * pixel_ratio),
            )
            picture.setDevicePixelRatio(pixel_ratio)
            picture.fill(Qt.GlobalColor.transparent)
            painter = QPainter(picture)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self._paint_vector(painter, QPointF(margin, margin))
            painter.end()
            self._picture_cache, self._picture_key = picture, key
        return self._picture_cache

    def paint_text(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem | None = None,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the halo, then the text over it.

        On a viewport, where the painter only moves the label (a label that
        ignores the view's transformations), the kept picture is drawn on
        whole pixels. Anything else gets vectors: an export, a print, an SVG,
        a painter that scales or turns.
        """
        world = painter.worldTransform()
        device = painter.device()
        on_screen = isinstance(device, QWidget) and world.type() in (
            QTransform.TransformationType.TxNone,
            QTransform.TransformationType.TxTranslate,
        )
        if device is None or not on_screen:
            self._paint_vector(painter, self._origin(self._measure()[0]), option, widget)
            return
        corner = world.map(self.boundingRect().topLeft())
        painter.save()
        painter.resetTransform()
        painter.drawPixmap(
            QPointF(round(corner.x()), round(corner.y())),
            self._picture(device.devicePixelRatioF()),
        )
        painter.restore()

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is not None:
            self.paint_text(painter, option, widget)


class PlanLabelItem(HaloTextItem):
    """An object's name label or area label.

    Centred on its anchor, and painted in the scene's foreground pass rather
    than in the item pass: a child item is drawn with its parent, so the lawn's
    label used to lie under every object drawn after the lawn. The item itself
    stays a child of its object. That keeps everything that follows the object
    for free: its place, visibility, opacity and lifetime, and the export
    paths' text resizing. In a scene that does not run the label pass (a plain
    ``QGraphicsScene`` in a test) it paints itself like any item.

    ``rank`` orders the labels of one object when room is short: the name (0)
    before the area (1).

    A label of no object (the hours on a contour of the sun map) has no owner
    whose size could earn it room. It states ``free_extent_px`` instead: what
    it counts as among the objects' sizes on screen. Zero, the default, shows
    no ownerless label, as before.

    **It takes no click** (``shape()`` is empty). Whether it is painted is the
    label pass's decision, per paint and per view, and the item knows nothing
    of it: with its rectangle as its shape, a label that was left out still
    covered the plan, and a press there selected nothing and started no box
    selection (a third of an 853-plant plan at fit). A label is writing on the
    plan, not a body; what lies under it takes the click, the double click, the
    context menu and the tooltip.
    """

    #: The size on screen an ownerless label is placed as (pixels); see the class.
    free_extent_px: float = 0.0

    def __init__(self, text: str = "", parent: QGraphicsItem | None = None, *, rank: int = 0) -> None:
        super().__init__(text, parent, centered=True)
        self.rank = rank
        note_label_changed(self)

    def shape(self) -> QPainterPath:
        """Nothing: no point of the plan is a hit on a label (class docstring)."""
        return QPainterPath()

    # The scene keeps the layout of its labels between paints; a label says
    # when it changed what that layout was taken from (``note_label_changed``).

    def setText(self, text: str | None) -> None:
        super().setText(text)
        note_label_changed(self)

    def setFont(self, font: QFont) -> None:
        super().setFont(font)
        note_label_changed(self)

    def set_screen_offset(self, dx: float, dy: float) -> None:
        super().set_screen_offset(dx, dy)
        note_label_changed(self)

    def stack_under(self, other: HaloTextItem | None) -> None:
        super().stack_under(other)
        note_label_changed(self)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change in LABEL_LAYOUT_CHANGES:
            note_label_changed(self)
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None or getattr(self.scene(), "paints_plan_labels", False):
            return
        self.paint_text(painter, option, widget)
