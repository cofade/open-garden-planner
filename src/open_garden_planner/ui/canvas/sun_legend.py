"""The key of the hours-of-sun map: a colour bar with the hours on it (#794).

The map is a continuous cool-to-warm surface with a contour at every hour.
Until #794 the numbers on the even contours were its only key, and they tell
what a line is, not what a colour is. The key is a bar of the map's own tints
from no sun to sun all day, with a mark at every hour the map draws a contour
for and a number at the hours it numbers.

One description, two places:

* ``core.heatmap_render.sun_legend`` says WHAT the key shows, from the tables
  the map is made of (the drift guard is
  ``tests/unit/test_heatmap_render.py``);
* ``paint_sun_legend`` here draws it, every measure taken from the font it is
  given, so it is the same key at any size.

Who draws it:

* the canvas — ``CanvasView`` paints it over the viewport, in the strip the
  scale bar stands in (``CanvasView.set_sun_legend``), in the theme's colours;
* a picture of the plan — ``SunMapLegendItem``, a scene item at the plan's
  south-west corner that only a picture shows (the export seam,
  ``ExportService._hide_overlay_items``, switches it on for the render). It is
  a ``HaloTextItem`` because that is how an export finds constant-size text and
  gives it the size its picture needs (PF-CAN-08): the key grows with it.

Text is painted through ``halo_text.paint_halo_text``; there is no second halo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, QSizeF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from open_garden_planner.core.heatmap_render import SunLegend
from open_garden_planner.ui.canvas.items.halo_text import (
    HaloTextItem,
    halo_colors,
    halo_width,
    paint_halo_text,
)

#: The key's measures, in units of the font's height (ascent + descent).
BAR_LENGTH_EM = 15.0
BAR_HEIGHT_EM = 0.62
TICK_EM = 0.3
GAP_EM = 0.75
#: Clear space between two numbers on the bar, in units of the font's height.
LABEL_GAP_EM = 0.45

#: The ink of the key in a picture of the plan: the dark of the map's own hour
#: labels, on the light halo. (On the canvas the ink is the theme's.)
PICTURE_INK = QColor(18, 22, 42)


@dataclass(frozen=True)
class SunLegendKey:
    """What a key is drawn from: the map's legend and the day it is the map of."""

    legend: SunLegend
    day: date | None


def legend_title(day: date | None) -> str:
    """The key's title in the application's language: what the bar measures
    and, when known, the day."""
    if day is None:
        return QCoreApplication.translate("SunMapLegend", "Hours of sun")
    return QCoreApplication.translate("SunMapLegend", "Hours of sun · {date}").format(
        date=day.isoformat()
    )


def hour_text(hour: int) -> str:
    """``hour`` with its unit, as the map's contours are numbered (the same
    translated text: ``SunHeatmapController``'s)."""
    return QCoreApplication.translate("SunHeatmapController", "{n} h").format(n=hour)


@dataclass(frozen=True)
class _Layout:
    """Where the parts of a key lie, relative to its top-left corner."""

    size: QSizeF
    title_baseline: QPointF | None
    bar: QRectF
    labels: tuple[tuple[QPointF, str], ...]     # baseline, text
    tick_length: float


def _layout(key: SunLegendKey, font: QFont, *, with_title: bool) -> _Layout:
    metrics = QFontMetricsF(font)
    em = metrics.ascent() + metrics.descent()
    halo = halo_width(font) / 2.0
    bar_length = BAR_LENGTH_EM * em
    bar_height = BAR_HEIGHT_EM * em
    tick = TICK_EM * em
    title = legend_title(key.day) if with_title else ""
    title_width = metrics.horizontalAdvance(title) if title else 0.0
    bar_left = halo + (title_width + GAP_EM * em if title else 0.0)
    # a number is centred on its mark; the first and the last hang over the
    # bar's ends by half their width, which the key's width allows for
    first = hour_text(key.legend.ticks[0].hour) if key.legend.ticks else ""
    overhang = metrics.horizontalAdvance(first) / 2.0 if not title else 0.0
    bar_left += overhang
    labels_top = halo
    bar_top = labels_top + em + tick
    bar = QRectF(bar_left, bar_top, bar_length, bar_height)
    numbered = [mark for mark in key.legend.ticks if mark.labelled]
    labels: list[tuple[QPointF, str]] = []
    taken_to = bar.left()
    # Every number, or every second, third ... of them: the first step at which
    # no two touch (the rule of the plan's labels, core.label_layout). An even
    # step, so the numbers left are evenly spaced; every mark stays.
    for step in range(1, len(numbered) + 1):
        labels, taken_to, fits = [], -1e9, True
        for mark in numbered[::step]:
            text = hour_text(mark.hour)
            width = metrics.horizontalAdvance(text)
            left = bar.left() + mark.position * bar_length - width / 2.0
            if left < taken_to + LABEL_GAP_EM * em:
                fits = False
                break
            taken_to = left + width
            labels.append((QPointF(left, labels_top + metrics.ascent()), text))
        if fits:
            break
    right = max(bar.right(), taken_to) + halo
    height = bar.bottom() + halo
    title_baseline = None
    if title:
        # the title stands beside the bar, on the bar's own line
        middle = bar.center().y()
        title_baseline = QPointF(halo, middle + (metrics.ascent() - metrics.descent()) / 2.0)
        height = max(height, title_baseline.y() + metrics.descent() + halo)
    return _Layout(QSizeF(right, height), title_baseline, bar, tuple(labels), tick)


def sun_legend_size(key: SunLegendKey, font: QFont, *, with_title: bool = True) -> QSizeF:
    """The room a key takes when it is drawn in ``font``."""
    return _layout(key, font, with_title=with_title).size


def _bar_image(legend: SunLegend, ground: QColor) -> QImage:
    """The map's tints over the bare plan's colour, one pixel a table row.

    The map is translucent and lies on whatever the plan holds; the bar shows
    it on the plan's own ground, where no lawn or soil is under it.
    """
    image = QImage(len(legend.colors), 1, QImage.Format.Format_RGB32)
    base = (ground.red(), ground.green(), ground.blue())
    for column, (red, green, blue, alpha) in enumerate(legend.colors):
        share = alpha / 255.0
        mixed = [round(tint * share + under * (1.0 - share))
                 for tint, under in zip((red, green, blue), base, strict=True)]
        image.setPixelColor(column, 0, QColor(*mixed))
    return image


def paint_sun_legend(
    painter: QPainter,
    top_left: QPointF,
    key: SunLegendKey,
    font: QFont,
    ink: QColor,
    ground: QColor,
    *,
    with_title: bool = True,
) -> QRectF:
    """Draw the key with its top-left corner at ``top_left`` and return the
    rectangle it takes.

    ``ink`` is the colour of text and marks; its halo follows from it
    (``halo_text.halo_colors``), so the key reads on any ground. ``ground`` is
    the bare plan's colour, which the bar's tints are laid on.
    """
    layout = _layout(key, font, with_title=with_title)
    ink_color, halo_color = halo_colors(ink)
    painter.save()
    painter.translate(top_left)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    bar = layout.bar
    edge = max(1.0, halo_width(font) / 4.0)
    # the halo of the bar and its marks: one stroke under everything
    under = QPen(halo_color, 3.0 * edge)
    under.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    under.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(under)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(bar)
    for mark in key.legend.ticks:
        x = bar.left() + mark.position * bar.width()
        painter.drawLine(QPointF(x, bar.top() - layout.tick_length), QPointF(x, bar.top()))
    # the bar: the map's own tints, left (no sun) to right (sun all day)
    painter.drawImage(bar, _bar_image(key.legend, ground))
    line = QPen(ink_color, edge)
    line.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(line)
    painter.drawRect(bar)
    for mark in key.legend.ticks:
        x = bar.left() + mark.position * bar.width()
        top = bar.top() - (layout.tick_length if mark.labelled else layout.tick_length / 2.0)
        painter.drawLine(QPointF(x, top), QPointF(x, bar.top()))
        if 0.0 < mark.position < 1.0:
            # the hour's line across the bar, as its contour crosses the map
            faint = QColor(ink_color)
            faint.setAlphaF(0.45 if mark.labelled else 0.25)
            painter.setPen(QPen(faint, edge))
            painter.drawLine(QPointF(x, bar.top()), QPointF(x, bar.bottom()))
            painter.setPen(line)
    for baseline, text in layout.labels:
        paint_halo_text(painter, baseline, text, font, ink)
    if layout.title_baseline is not None:
        paint_halo_text(painter, layout.title_baseline, legend_title(key.day), font, ink)
    painter.restore()
    return QRectF(top_left, layout.size)


_picture: tuple[tuple[object, ...], QPixmap] | None = None


def sun_legend_picture(
    key: SunLegendKey,
    font: QFont,
    ink: QColor,
    ground: QColor,
    *,
    with_title: bool,
    pixel_ratio: float,
) -> QPixmap:
    """The key as a picture for a viewport of ``pixel_ratio``, kept until what
    it shows changes.

    A view paints its key on every repaint. Stroking the outlines of its seven
    strings costs a millisecond or two each time; the picture is a blit. One
    picture is kept: a window has one key. The texts are part of what is
    compared, so a change of language makes a new picture.
    """
    global _picture
    texts = (legend_title(key.day) if with_title else "", hour_text(0))
    wanted = (key, font.key(), ink.rgba(), ground.rgba(), with_title, pixel_ratio, texts)
    if _picture is not None and _picture[0] == wanted:
        return _picture[1]
    size = sun_legend_size(key, font, with_title=with_title)
    picture = QPixmap(
        math.ceil(size.width() * pixel_ratio), math.ceil(size.height() * pixel_ratio)
    )
    picture.setDevicePixelRatio(pixel_ratio)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    try:
        paint_sun_legend(painter, QPointF(0.0, 0.0), key, font, ink, ground, with_title=with_title)
    finally:
        painter.end()
    _picture = (wanted, picture)
    return picture


def legend_font(point_size: float = 8.0) -> QFont:
    """The key's font: the scale bar's (bold, 8 pt on the canvas)."""
    font = QFont()
    font.setPointSizeF(point_size)
    font.setBold(True)
    return font


class SunMapLegendItem(HaloTextItem):
    """The key of the map in a picture of the plan (module docstring).

    Stands at the plan's south-west corner, inside the plan: a picture of the
    plan is exactly the plan, so there is no margin to put it in. Hidden
    except while a picture is rendered — on the canvas the view draws the key
    over the viewport, where it stays in sight at any zoom and pan.
    """

    def __init__(self, key: SunLegendKey, ground: QColor) -> None:
        super().__init__(legend_title(key.day))
        self._key = key
        self._ground = QColor(ground)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFont(legend_font())
        self.setBrush(PICTURE_INK)
        self.setVisible(False)

    def legend_key(self) -> SunLegendKey:
        """What this key shows."""
        return self._key

    def set_legend_key(self, key: SunLegendKey) -> None:
        """Show another map's key."""
        if key != self._key:
            self.prepareGeometryChange()
            self._key = key
            self.setText(legend_title(key.day))

    def _margin(self) -> float:
        metrics = QFontMetricsF(self.font())
        return 0.8 * (metrics.ascent() + metrics.descent())

    def _key_rect(self) -> QRectF:
        """Where the key is painted. The item ignores every transformation:
        these are device pixels, y down, from the plan's south-west corner — the
        key lies up and right of it."""
        size = sun_legend_size(self._key, self.font())
        margin = self._margin()
        return QRectF(margin, -margin - size.height(), size.width(), size.height())

    def plan_label_blocker(self) -> QRectF:
        """The room the key takes, which no label of the plan may touch
        (``ui.canvas.plan_labels``): an hour's label half under the key reads
        as one of the key's own numbers."""
        return self._key_rect()

    def boundingRect(self) -> QRectF:
        # The key's rectangle AND its mirror image below the corner. A picture
        # is rendered through a painter that flips y, and the scene finds the
        # items of a picture by their rectangles taken WITHOUT that flip: there
        # the key's own rectangle lies south of the plan, outside the picture,
        # and the key was not painted at all.
        rect = self._key_rect()
        return rect.united(QRectF(rect.left(), -rect.bottom(), rect.width(), rect.height()))

    def paint(
        self,
        painter: QPainter | None,
        _option: QStyleOptionGraphicsItem | None,
        _widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        paint_sun_legend(
            painter, self._key_rect().topLeft(), self._key, self.font(),
            self.brush().color(), self._ground,
        )


__all__ = [
    "PICTURE_INK",
    "SunLegendKey",
    "SunMapLegendItem",
    "hour_text",
    "legend_font",
    "legend_title",
    "paint_sun_legend",
    "sun_legend_picture",
    "sun_legend_size",
]
