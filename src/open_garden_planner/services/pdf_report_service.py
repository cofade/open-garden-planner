"""Multi-page PDF report service for garden plans."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QMarginsF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from open_garden_planner.core.measurements import (
    SCALE_BAR_NICE_DISTANCES_CM,
    format_scale_distance,
)


def _tr(text: str) -> str:
    """Translate a service-layer string under the PdfReportService context."""
    return QCoreApplication.translate("PdfReportService", text)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

#: Resolution of a plan picture in the report (#788). The page itself is laid
#: out in points; the plan is painted into a picture of this resolution and
#: placed on the page (the scene cannot be painted on the PDF painter directly:
#: see ``_scene_to_image``). Measured on the four bundled examples, A4
#: landscape, every page type on (9-16 pages) — file size and generation time:
#:
#:     150 dpi   1.2-2.7 MB   0.3-0.8 s
#:     200 dpi   1.8-4.0 MB   0.4-1.3 s
#:     300 dpi   3.2-7.0 MB   0.8-2.4 s
#:
#: (72 dpi, the old value, was 1.0 MB and 0.4 s for the largest plan, and soft
#: even on screen.) 300 dpi is what a print shop asks for and what the PNG
#: export calls high resolution; its cost is a few megabytes and two seconds.
PLAN_RENDER_DPI = 300


# ---------------------------------------------------------------------------
# Options dataclass
# ---------------------------------------------------------------------------

@dataclass
class PdfReportOptions:
    """Configuration for a PDF report."""

    paper_size: str = "A4"           # "A4" | "A3" | "Letter" | "Legal"
    orientation: str = "landscape"   # "landscape" | "portrait"
    include_cover: bool = True
    include_overview: bool = True
    include_bed_details: bool = False
    include_plant_list: bool = True
    include_legend: bool = True
    # US-12.9: optional Garden Notes page. ``garden_journal_notes`` must be
    # populated when ``include_garden_notes`` is True — pass the raw dict from
    # ``ProjectManager.garden_journal_notes``. ``None`` is treated as empty.
    include_garden_notes: bool = False
    garden_journal_notes: dict[str, Any] | None = None
    # US-C1: optional Harvest Summary page. ``harvest_logs`` must be populated
    # when ``include_harvest_summary`` is True — pass the raw dict from
    # ``ProjectManager.harvest_logs``. ``None`` is treated as empty.
    include_harvest_summary: bool = False
    harvest_logs: dict[str, Any] | None = None
    project_name: str = "Garden Plan"
    author: str = ""
    export_date: str = field(default_factory=lambda: date.today().isoformat())


# ---------------------------------------------------------------------------
# Paper size helpers
# ---------------------------------------------------------------------------

_PAGE_SIZE_MAP: dict[str, QPageSize.PageSizeId] = {
    "A4": QPageSize.PageSizeId.A4,
    "A3": QPageSize.PageSizeId.A3,
    "Letter": QPageSize.PageSizeId.Letter,
    "Legal": QPageSize.PageSizeId.Legal,
}

_MARGIN_MM = 12.0


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _pt(mm: float) -> float:
    """Convert millimetres to printer points (1 pt = 1/72 inch ≈ 0.353 mm)."""
    return mm / 25.4 * 72.0


def _font(point_size: int) -> QFont:
    """The report's typeface at *point_size*, laid out by its design metrics.

    The page is laid out at 72 units per inch, and a hinted font rounds every
    glyph's advance to a whole unit there: measured, ``Thyme`` was written as
    ``Thy me`` and ``Driveway`` as ``Driv eway``. Without hinting the advances
    are the typeface's own and the words close up.
    """
    font = QFont("Arial", point_size)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _scene_to_image(
    scene: Any, source: QRectF, dest: QRectF, dpi: float | None = None
) -> QImage:
    """Render *source* of *scene*, Y-up, into a picture for the page rectangle *dest*.

    *dest* is in points; the picture has ``dpi`` pixels per inch of it. Using a
    temporary QImage avoids PDF/SVG coordinate-system interactions that make
    the painter pre-flip approach unreliable on non-QImage devices, and gives
    the scene a painter whose world transform carries the real output scale —
    which is what a sprite or a texture rasterises itself for. The picture is
    the frame: nothing of the scene can be painted outside *dest*.
    Constant-pixel-size labels are sized for the output; a text note keeps the
    size it has on the plan (#789).
    """
    from open_garden_planner.services.export_service import ExportService

    dpi = PLAN_RENDER_DPI if dpi is None else dpi
    w = max(1, int(round(dest.width() * dpi / 72.0)))
    h = max(1, int(round(dest.height() * dpi / 72.0)))

    # Scale factor: output physical width (cm) / scene source width (cm)
    w_cm = dest.width() / 72.0 * 2.54
    scale = w_cm / max(1.0, source.width())

    saved_text = ExportService._prepare_text_for_export(scene, scale, dpi)
    hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
    cached_items = ExportService._disable_item_caches(scene)
    try:
        # Opaque: a picture with an alpha channel is written with a mask of its own.
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.save()
        p.translate(0, h)
        p.scale(1.0, -1.0)
        scene.render(p, QRectF(0, 0, w, h), source)
        p.restore()
        p.end()
    finally:
        ExportService._restore_text_after_export(saved_text)
        ExportService._restore_overlay_items(hidden_overlay, prior_selection)
        ExportService._restore_item_caches(cached_items)
    return img


def _draw_title_block(
    painter: QPainter,
    page_rect: QRectF,
    title: str,
    subtitle: str,
) -> None:
    """Draw a thin title block at the bottom of *page_rect*."""
    bar_h = _pt(8.0)
    bar = QRectF(page_rect.left(), page_rect.bottom() - bar_h, page_rect.width(), bar_h)
    painter.fillRect(bar, QColor("#2e7d32"))

    title_font = _font(7)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("white"))
    painter.drawText(
        QRectF(bar.left() + _pt(2), bar.top(), bar.width() / 2, bar.height()),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        title,
    )
    subtitle_font = _font(6)
    painter.setFont(subtitle_font)
    painter.drawText(
        QRectF(bar.left() + bar.width() / 2, bar.top(), bar.width() / 2 - _pt(2), bar.height()),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
        subtitle,
    )


def _draw_north_arrow(painter: QPainter, cx: float, cy: float, size: float) -> None:
    """Draw a simple north arrow centred at (cx, cy)."""
    painter.save()
    painter.translate(cx, cy)

    pen = QPen(QColor("#333333"))
    pen.setWidthF(1.0)
    painter.setPen(pen)

    half = size / 2.0
    # Arrow body
    painter.drawLine(QPointF(0, half), QPointF(0, -half))
    # Arrowhead
    painter.drawLine(QPointF(0, -half), QPointF(-size * 0.2, -half + size * 0.35))
    painter.drawLine(QPointF(0, -half), QPointF(size * 0.2, -half + size * 0.35))

    font = _font(max(4, int(size * 0.4)))
    painter.setFont(font)
    painter.drawText(
        QRectF(-size / 2, -half - _pt(5), size, _pt(5)),
        Qt.AlignmentFlag.AlignCenter,
        _tr("N"),
    )
    painter.restore()


_SCALE_BAR_PREFERRED_CM = 1000.0   # 10 m, where it fits
_SCALE_BAR_MIN_PT = 20.0           # shorter is a stub nobody can lay a ruler on
_SCALE_BAR_MAX_PAGE_SHARE = 0.25   # longer is a banner


def _fit_rect(source: QRectF, bounds: QRectF) -> QRectF:
    """The largest rectangle of *source*'s aspect ratio inside *bounds*, centred.

    ``QGraphicsScene.render`` keeps the source's aspect ratio and anchors the
    picture at the target's corner. Rendering into this rectangle instead puts
    the plan in the middle of its page, and makes ``width / source.width()``
    the one true scale of the picture (#782).
    """
    if source.width() <= 0 or source.height() <= 0:
        return QRectF(bounds)
    scale = min(bounds.width() / source.width(), bounds.height() / source.height())
    width = source.width() * scale
    height = source.height() * scale
    return QRectF(
        bounds.left() + (bounds.width() - width) / 2.0,
        bounds.top() + (bounds.height() - height) / 2.0,
        width,
        height,
    )


def _pick_pdf_scale_distance(pt_per_cm: float, page_width_pt: float) -> float:
    """The round distance, in cm, that the overview's scale bar shows.

    10 m where a bar of 10 m is between 20 pt and a quarter of the page;
    otherwise the round distance nearest to 10 m that is. The bar is drawn at
    exactly this distance, so its label is always its length.
    """
    longest = page_width_pt * _SCALE_BAR_MAX_PAGE_SHARE
    fitting = [
        float(d) for d in SCALE_BAR_NICE_DISTANCES_CM
        if _SCALE_BAR_MIN_PT <= d * pt_per_cm <= longest
    ]
    if _SCALE_BAR_PREFERRED_CM in fitting:
        return _SCALE_BAR_PREFERRED_CM
    if fitting:
        return min(fitting, key=lambda d: abs(math.log(d / _SCALE_BAR_PREFERRED_CM)))
    # No round distance fits (a plan of many kilometres, or one of centimetres):
    # the one whose bar is nearest the allowed range. Still drawn to scale.
    target = math.sqrt(_SCALE_BAR_MIN_PT * longest)
    return float(min(
        SCALE_BAR_NICE_DISTANCES_CM,
        key=lambda d: abs(math.log(max(d * pt_per_cm, 1e-9) / target)),
    ))


def _draw_scale_bar(
    painter: QPainter,
    left: float,
    bottom: float,
    pt_per_cm: float,
    page_width_pt: float,
) -> None:
    """Draw a scale bar of a round distance below the plan overview.

    *pt_per_cm* is the scale the plan was drawn at. The bar is never clamped:
    its length is its label's distance at that scale.
    """
    bar_cm = _pick_pdf_scale_distance(pt_per_cm, page_width_pt)
    bar_pt = bar_cm * pt_per_cm

    pen = QPen(QColor("#333333"))
    pen.setWidthF(1.0)
    painter.setPen(pen)

    y = bottom + _pt(2)
    painter.drawLine(QPointF(left, y), QPointF(left + bar_pt, y))
    painter.drawLine(QPointF(left, y - _pt(1.5)), QPointF(left, y + _pt(1.5)))
    painter.drawLine(QPointF(left + bar_pt, y - _pt(1.5)), QPointF(left + bar_pt, y + _pt(1.5)))

    font = _font(5)
    painter.setFont(font)
    painter.setPen(QColor("#333333"))
    # The label is centred on the bar but not squeezed into it: a short bar
    # would clip its own text.
    label_w = max(bar_pt, _pt(20))
    painter.drawText(
        QRectF(left + (bar_pt - label_w) / 2.0, y + _pt(1), label_w, _pt(6)),
        Qt.AlignmentFlag.AlignCenter,
        format_scale_distance(bar_cm),
    )


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------

def _render_cover(painter: QPainter, page_rect: QRectF, opts: PdfReportOptions) -> None:
    painter.fillRect(page_rect, QColor("#f5f5dc"))

    center_x = page_rect.center().x()
    title_y = page_rect.top() + page_rect.height() * 0.3

    # Project name
    font = _font(28)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#2e7d32"))
    painter.drawText(
        QRectF(page_rect.left(), title_y, page_rect.width(), _pt(20)),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        opts.project_name,
    )

    # Subtitle
    font2 = _font(12)
    painter.setFont(font2)
    painter.setPen(QColor("#555555"))
    meta_lines = []
    if opts.author:
        meta_lines.append(opts.author)
    meta_lines.append(opts.export_date)
    meta_lines.append(_tr("Created with Open Garden Planner"))

    for i, line in enumerate(meta_lines):
        painter.drawText(
            QRectF(
                page_rect.left(),
                title_y + _pt(22) + i * _pt(10),
                page_rect.width(),
                _pt(10),
            ),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            line,
        )

    # Decorative line under title
    pen = QPen(QColor("#2e7d32"))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    line_w = page_rect.width() * 0.4
    line_y = title_y + _pt(19)
    painter.drawLine(
        QPointF(center_x - line_w / 2, line_y),
        QPointF(center_x + line_w / 2, line_y),
    )


def _render_overview(
    painter: QPainter,
    page_rect: QRectF,
    scene: CanvasScene,
    opts: PdfReportOptions,
) -> None:
    title_bar_h = _pt(8)
    scale_bar_h = _pt(10)
    north_size = _pt(12)

    content_rect = QRectF(
        page_rect.left(),
        page_rect.top() + title_bar_h,
        page_rect.width(),
        page_rect.height() - title_bar_h - scale_bar_h - _pt(8),
    )

    canvas_rect = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()
    plan_rect = _fit_rect(canvas_rect, content_rect)
    img = _scene_to_image(scene, canvas_rect, plan_rect)
    painter.drawImage(plan_rect, img)

    # North arrow (top-right of content area)
    _draw_north_arrow(
        painter,
        content_rect.right() - north_size,
        content_rect.top() + north_size,
        north_size,
    )

    # Scale bar, at the scale the plan was drawn at
    _draw_scale_bar(
        painter,
        content_rect.left() + _pt(4),
        content_rect.bottom(),
        plan_rect.width() / max(1.0, canvas_rect.width()),
        content_rect.width(),
    )

    _draw_title_block(
        painter,
        page_rect,
        opts.project_name,
        opts.export_date,
    )


# A bed-detail page shows the bed with some of the plan around it, at a scale a
# person can read (#788). Padding gives context; the minimum extent keeps a
# 40 cm pot from being blown up to a page of blur; the minimum aspect keeps a
# long strip from becoming a sliver. Beds smaller than ``_SMALL_BED_CM`` whose
# frames touch share one page — a row of pots is one picture, not three.
_BED_PADDING_SHARE = 0.10
_BED_PADDING_MIN_CM = 20.0
_BED_MIN_EXTENT_CM = 150.0
_BED_MIN_ASPECT = 0.4
_SMALL_BED_CM = 100.0
_BED_TITLE_NAMES = 3


def _bed_rect(bed_item: Any) -> QRectF:
    """The bed's own outline in the scene (its bounding rect also holds a shadow margin)."""
    return QRectF(bed_item.mapToScene(bed_item.shape()).boundingRect())


def _bed_frame(beds: QRectF, canvas: QRectF) -> QRectF:
    """The part of the plan a detail page of *beds* shows, inside *canvas*."""
    padding = max(_BED_PADDING_MIN_CM, _BED_PADDING_SHARE * max(beds.width(), beds.height()))
    width = max(beds.width() + 2.0 * padding, _BED_MIN_EXTENT_CM)
    height = max(beds.height() + 2.0 * padding, _BED_MIN_EXTENT_CM)
    width = max(width, height * _BED_MIN_ASPECT)
    height = max(height, width * _BED_MIN_ASPECT)
    if canvas.width() > 0 and canvas.height() > 0:
        width = min(width, canvas.width())
        height = min(height, canvas.height())
    centre = beds.center()
    left = centre.x() - width / 2.0
    top = centre.y() - height / 2.0
    if canvas.width() > 0 and canvas.height() > 0:
        # Moved into the plan, never shrunk: the scale stays the frame's.
        left = min(max(left, canvas.left()), canvas.right() - width)
        top = min(max(top, canvas.top()), canvas.bottom() - height)
    return QRectF(left, top, width, height)


def _natural_key(text: str) -> list[Any]:
    """Sort key that puts ``Bed 2`` before ``Bed 10``."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def _bed_groups(scene: Any) -> list[list[Any]]:
    """The beds of *scene* as detail pages: one bed, or a cluster of small ones."""
    canvas = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()
    beds = sorted(
        PdfReportService._find_beds(scene),
        key=lambda bed: _natural_key(getattr(bed, "name", "") or ""),
    )
    groups: list[list[Any]] = []
    clusters: list[list[Any]] = []
    for bed in beds:
        rect = _bed_rect(bed)
        if max(rect.width(), rect.height()) >= _SMALL_BED_CM:
            groups.append([bed])
        else:
            clusters.append([bed])

    def frame_of(members: list[Any]) -> QRectF:
        united = QRectF()
        for member in members:
            united = united.united(_bed_rect(member))
        return _bed_frame(united, canvas)

    merged = True
    while merged:
        merged = False
        for first in range(len(clusters)):
            for second in range(first + 1, len(clusters)):
                if frame_of(clusters[first]).intersects(frame_of(clusters[second])):
                    clusters[first] = clusters[first] + clusters.pop(second)
                    merged = True
                    break
            if merged:
                break
    groups.extend(clusters)
    groups.sort(key=lambda members: _natural_key(getattr(members[0], "name", "") or ""))
    return groups


def _render_bed_detail(
    painter: QPainter,
    page_rect: QRectF,
    scene: CanvasScene,
    beds: Any,
    opts: PdfReportOptions,
) -> None:
    members = list(beds) if isinstance(beds, (list, tuple)) else [beds]
    title_bar_h = _pt(8)
    content_rect = QRectF(
        page_rect.left(),
        page_rect.top() + title_bar_h,
        page_rect.width(),
        page_rect.height() - title_bar_h,
    )

    canvas_rect = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()
    united = QRectF()
    for member in members:
        united = united.united(_bed_rect(member))
    source = _bed_frame(united, canvas_rect)
    bed_rect = _fit_rect(source, content_rect)
    img = _scene_to_image(scene, source, bed_rect)
    painter.drawImage(bed_rect, img)

    names = [getattr(member, "name", "") or _tr("Bed") for member in members]
    shown = ", ".join(names[:_BED_TITLE_NAMES])
    if len(names) > _BED_TITLE_NAMES:
        shown += ", …"
    _draw_title_block(painter, page_rect, f"{opts.project_name} – {shown}", opts.export_date)


# ---------------------------------------------------------------------------
# Sections that run over several pages
# ---------------------------------------------------------------------------
#
# One rule for every list of the report (#788, #836): ``plan_pages`` cuts the
# section into the pages it needs and ``render_page`` paints one of them. No
# renderer opens a page of its own and none stops at the foot of the first: a
# row the report was asked for is on some page, and every page is counted.

_TABLE_TITLE_H_MM = 14.0
_TABLE_ROW_H_MM = 7.0
_TABLE_FOOT_MM = 8.0

#: One page of a section: its rows, its number, the section's page count and
#: the index of its first row in the whole section.
SectionPage = tuple[list[Any], int, int, int]


def _table_rows_per_page(page_rect: QRectF) -> int:
    """How many data rows of a titled table fit on one page."""
    first_row = page_rect.top() + _pt(_TABLE_TITLE_H_MM) + _pt(4) + _pt(_TABLE_ROW_H_MM)
    room = page_rect.bottom() - _pt(_TABLE_FOOT_MM) - first_row
    return max(1, int(room // _pt(_TABLE_ROW_H_MM)))


def _section_pages(rows: list[Any], per_page: int) -> list[SectionPage]:
    """*rows* cut into pages of *per_page*; an empty section still has one page."""
    per_page = max(1, per_page)
    count = max(1, math.ceil(len(rows) / per_page))
    return [
        (rows[number * per_page:(number + 1) * per_page], number + 1, count, number * per_page)
        for number in range(count)
    ]


def _paged_title(title: str, page: int, pages: int) -> str:
    """*title*, with the page of the section when it runs over more than one."""
    if pages <= 1:
        return title
    return _tr("{title} – page {page} of {pages}").format(title=title, page=page, pages=pages)


def _draw_section_title(painter: QPainter, page_rect: QRectF, title: str) -> float:
    """Draw a section's title at the top of *page_rect*; return where its body starts."""
    title_font = _font(14)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#2e7d32"))
    title_h = _pt(_TABLE_TITLE_H_MM)
    painter.drawText(
        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        title,
    )
    return page_rect.top() + title_h + _pt(4)


def _render_table_page(
    painter: QPainter,
    page_rect: QRectF,
    title: str,
    columns: list[tuple[str, float]],
    rows: list[tuple[str, ...]],
    first_index: int = 0,
    empty_text: str = "",
) -> None:
    """One page of a titled table: header, then *rows*, striped by their index.

    *columns* is ``(heading, share of the page width)``. A cell too long for
    its column is elided, never cut at a character count. *empty_text* is what
    the page says when the table has no row at all.
    """
    header_font = _font(9)
    header_font.setBold(True)
    row_font = _font(8)

    row_h = _pt(_TABLE_ROW_H_MM)
    y = _draw_section_title(painter, page_rect, title)

    # Header row
    painter.fillRect(QRectF(page_rect.left(), y, page_rect.width(), row_h), QColor("#2e7d32"))
    painter.setFont(header_font)
    painter.setPen(QColor("white"))
    x = page_rect.left()
    for label, frac in columns:
        col_w = page_rect.width() * frac
        painter.drawText(
            QRectF(x + _pt(2), y, col_w - _pt(4), row_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )
        x += col_w
    y += row_h

    # Data rows
    painter.setFont(row_font)
    metrics = painter.fontMetrics()
    for offset, values in enumerate(rows):
        bg = QColor("#f9f9f9") if (first_index + offset) % 2 == 0 else QColor("white")
        painter.fillRect(QRectF(page_rect.left(), y, page_rect.width(), row_h), bg)
        painter.setPen(QColor("#333333"))
        x = page_rect.left()
        for val, frac in zip(values, [f for _, f in columns], strict=True):
            col_w = page_rect.width() * frac
            painter.drawText(
                QRectF(x + _pt(2), y, col_w - _pt(4), row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(val, Qt.TextElideMode.ElideRight, int(col_w - _pt(4))),
            )
            x += col_w
        y += row_h

    if not rows and empty_text:
        painter.setFont(row_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), y + _pt(4), page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            empty_text,
        )


def _plant_display_name(item: Any) -> str:
    """A plant's name as the plant panels show it: its own name, else its species'."""
    from open_garden_planner.ui.plant_traits import species_display_name

    name = getattr(item, "name", "") or ""
    if name:
        return str(name)
    metadata = getattr(item, "metadata", {}) or {}
    species = metadata.get("plant_species") if isinstance(metadata, dict) else None
    if species is not None and not isinstance(species, dict):
        species = {
            "common_name": getattr(species, "common_name", "") or "",
            "scientific_name": getattr(species, "scientific_name", "") or "",
        }
    if isinstance(species, dict):
        return species_display_name(species) or ""
    return ""


def _plant_items(scene: Any) -> list[Any]:
    from open_garden_planner.core.object_types import is_plant_type

    present = getattr(scene, "is_present", None)
    return [
        item for item in scene.items()
        if is_plant_type(getattr(item, "object_type", None))
        and (present is None or present(item))
    ]


def _plant_rows(scene: Any) -> list[tuple[str, str, str, str]]:
    """Every plant of *scene* as (name, type, position, notes), ordered by name."""
    from open_garden_planner.core.object_types import get_translated_display_name
    from open_garden_planner.ui.canvas.items.handle_geometry import selection_frame_rect

    found: list[tuple[list[Any], float, float, tuple[str, str, str, str]]] = []
    for item in _plant_items(scene):
        # Where the plant stands: the centre of its outline. Its bounding
        # rectangle also holds a badge in one corner, which moved the listed
        # position off the plant (PF-CAN-51).
        center = item.mapToScene(selection_frame_rect(item).center())
        metadata = getattr(item, "metadata", {}) or {}
        notes = (metadata.get("plant_instance") or {}).get("notes", "") or ""
        name = _plant_display_name(item) or _tr("Unnamed")
        found.append((_natural_key(name), center.x(), center.y(), (
            name,
            get_translated_display_name(item.object_type),
            f"({center.x():.0f}, {center.y():.0f})",
            str(notes),
        )))
    # By name, and plants of one name from left to right.
    found.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    return [row for _key, _x, _y, row in found]


def _render_plant_list(
    painter: QPainter,
    page_rect: QRectF,
    rows: list[tuple[str, str, str, str]],
    page: int = 1,
    pages: int = 1,
    first_index: int = 0,
) -> None:
    """One page of the plant list: *rows* is this page's share of the plants."""
    _render_table_page(
        painter,
        page_rect,
        _paged_title(_tr("Plant List"), page, pages),
        [
            (_tr("Name"), 0.35),
            (_tr("Type"), 0.20),
            (_tr("Position (cm)"), 0.25),
            (_tr("Notes"), 0.20),
        ],
        list(rows),
        first_index,
        _tr("No plants found in this project.") if pages <= 1 else "",
    )


def _harvest_rows(opts: PdfReportOptions) -> list[tuple[str, str, str, str, str]]:
    """The harvest totals as (species, year, total, unit, entries), newest year first."""
    from open_garden_planner.services.harvest_aggregation import (
        aggregate_by_species_year,
    )

    return [
        (
            agg.species_name or _tr("Unnamed"),
            str(agg.year),
            f"{agg.total_quantity:g}",
            agg.unit,
            str(agg.entry_count),
        )
        for agg in aggregate_by_species_year(opts.harvest_logs or {})
    ]


def _render_harvest_summary(
    painter: QPainter,
    page_rect: QRectF,
    rows: list[tuple[str, str, str, str, str]],
    page: int = 1,
    pages: int = 1,
    first_index: int = 0,
) -> None:
    """One page of the Harvest Summary (US-C1): per-species, per-year totals.

    Until #836 this painted the first page's worth and stopped: a garden with
    more totals than one page holds lost the rest without a word.
    """
    _render_table_page(
        painter,
        page_rect,
        _paged_title(_tr("Harvest Summary"), page, pages),
        [
            (_tr("Species"), 0.40),
            (_tr("Year"), 0.15),
            (_tr("Total"), 0.20),
            (_tr("Unit"), 0.13),
            (_tr("Entries"), 0.12),
        ],
        list(rows),
        first_index,
        _tr("No harvests logged in this project.") if pages <= 1 else "",
    )


# Garden Notes (US-12.9): a date line, the wrapped body and an optional photo
# line per note, newest first. The lines are laid out before a page is painted,
# so the section's pages are known to ``plan_pages`` like any other's.
_NOTE_DATE_H_MM = 6.0
_NOTE_LINE_H_MM = 4.5
_NOTE_GAP_MM = 3.0
_NOTE_FOOT_MM = 2.0
_NOTE_BODY_PT = 9

#: One laid-out line of the Garden Notes: its kind and its text.
NoteLine = tuple[str, str]
_NOTE_LINE_HEIGHTS_MM = {
    "date": _NOTE_DATE_H_MM,
    "body": _NOTE_LINE_H_MM,
    "photo": _NOTE_LINE_H_MM,
    "gap": _NOTE_GAP_MM,
}


def _page_metrics(point_size: int) -> Any:
    """Metrics of the report's typeface in points — the page's own unit.

    ``QFontMetricsF(font)`` measures for the screen (96 units per inch), a
    third wider than the same text on the page, which is laid out at 72: the
    Garden Notes wrapped at three quarters of the page's width (#836). A font
    sized in pixels is measured as it is given, on every device.
    """
    from PyQt6.QtGui import QFontMetricsF

    font = _font(point_size)
    font.setPixelSize(point_size)
    return QFontMetricsF(font)


def _note_lines(opts: PdfReportOptions, width_pt: float) -> list[list[NoteLine]]:
    """Every note of *opts* as its lines, wrapped to *width_pt*, newest first."""
    from open_garden_planner.models.journal_note import JournalNote

    notes = [
        JournalNote.from_dict(raw)
        for raw in (opts.garden_journal_notes or {}).values()
        if isinstance(raw, dict)
    ]
    notes.sort(key=lambda note: note.date or "", reverse=True)

    metrics = _page_metrics(_NOTE_BODY_PT)
    laid_out: list[list[NoteLine]] = []
    for note in notes:
        lines: list[NoteLine] = [("date", note.date or _tr("(no date)"))]
        text_block = note.text.strip() or _tr("(empty)")
        for paragraph in text_block.splitlines() or [text_block]:
            lines.extend(
                ("body", line) for line in _wrap_to_width(paragraph or " ", width_pt, metrics)
            )
        if note.photo_path:
            lines.append(
                ("photo", _tr("(photo: {filename})").format(filename=Path(note.photo_path).name))
            )
        laid_out.append(lines)
    return laid_out


def _notes_pages(opts: PdfReportOptions, page_rect: QRectF) -> list[SectionPage]:
    """The Garden Notes cut into pages: every line of every note is on one."""
    top = page_rect.top() + _pt(_TABLE_TITLE_H_MM) + _pt(4)
    bottom = page_rect.bottom() - _pt(_NOTE_FOOT_MM)

    pages: list[list[NoteLine]] = [[]]
    y = top
    for lines in _note_lines(opts, page_rect.width()):
        for index, (kind, text) in enumerate(lines):
            height = _pt(_NOTE_LINE_HEIGHTS_MM[kind])
            # A date is never the last line of a page: it takes its first body
            # line with it.
            needed = height + (_pt(_NOTE_LINE_H_MM) if index == 0 else 0.0)
            if y + needed > bottom and pages[-1]:
                pages.append([])
                y = top
            pages[-1].append((kind, text))
            y += height
        # The space under a note; a page never starts with it.
        if y + _pt(_NOTE_GAP_MM) <= bottom:
            pages[-1].append(("gap", ""))
            y += _pt(_NOTE_GAP_MM)
    count = len(pages)
    first = 0
    numbered: list[SectionPage] = []
    for number, lines_of_page in enumerate(pages, start=1):
        numbered.append((lines_of_page, number, count, first))
        first += len(lines_of_page)
    return numbered


def _render_garden_notes(
    painter: QPainter,
    page_rect: QRectF,
    lines: list[NoteLine],
    page: int = 1,
    pages: int = 1,
) -> None:
    """One page of the Garden Notes (US-12.9): *lines* is this page's share.

    Until #836 this opened further pages on the paint device by itself, so a
    report with many notes had more pages than its progress counted, and only
    the last of them carried what ``generate`` adds to a page.
    """
    date_font = _font(10)
    date_font.setBold(True)
    body_font = _font(_NOTE_BODY_PT)
    meta_font = _font(8)
    meta_font.setItalic(True)
    looks = {
        "date": (date_font, QColor("#333333")),
        "body": (body_font, QColor("#222222")),
        "photo": (meta_font, QColor("#666666")),
    }

    y = _draw_section_title(painter, page_rect, _paged_title(_tr("Garden Notes"), page, pages))

    if not lines and pages <= 1:
        painter.setFont(body_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), y, page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("No journal notes recorded."),
        )
        return

    for kind, text in lines:
        height = _pt(_NOTE_LINE_HEIGHTS_MM[kind])
        if kind != "gap":
            font, colour = looks[kind]
            painter.setFont(font)
            painter.setPen(colour)
            painter.drawText(
                QRectF(page_rect.left(), y, page_rect.width(), height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
        y += height


def _wrap_to_width(
    text: str, width_pt: float, metrics: Any
) -> list[str]:
    """Greedy word-wrap helper for the Garden Notes renderer."""
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if metrics.horizontalAdvance(candidate) <= width_pt - _pt(2):
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# The legend lists what is on the plan: every kind of object in use and every
# plant, each with a swatch painted by the item itself, so the legend shows the
# fill, the texture or the sprite the reader sees on the plan pages (#788).
_LEGEND_ROW_H_MM = 9.0
_LEGEND_SWATCH_MM = 7.0
_LEGEND_PATCH_CM = 150.0
_LEGEND_LINE_PATCH_MIN_CM = 30.0
_LEGEND_LINE_WIDTHS = 8.0
_LEGEND_ANNOTATIONS = ("GENERIC_TEXT", "GENERIC_CALLOUT", "ROOF_RIDGE", "GARDEN_JOURNAL_PIN")


@dataclass
class LegendEntry:
    """One legend line: a heading (no item) or a sample of *item* with a label."""

    label: str
    item: Any = None


def _legend_entries(scene: Any) -> list[LegendEntry]:
    """What the legend of *scene* lists, in reading order."""
    from open_garden_planner.core.object_types import (
        ObjectType,
        get_translated_display_name,
        is_plant_type,
    )

    skipped = {getattr(ObjectType, name, None) for name in _LEGEND_ANNOTATIONS}
    present = getattr(scene, "is_present", None)
    objects: dict[Any, list[Any]] = {}
    plants: dict[str, list[Any]] = {}
    for item in scene.items():
        kind = getattr(item, "object_type", None)
        if kind is None or kind in skipped or not item.isVisible():
            continue
        if present is not None and not present(item):
            continue
        if is_plant_type(kind):
            plants.setdefault(_plant_display_name(item) or _tr("Unnamed"), []).append(item)
        else:
            objects.setdefault(kind, []).append(item)

    def line(name: str, members: list[Any]) -> LegendEntry:
        label = name if len(members) == 1 else f"{name} ({len(members)})"
        # The largest of its kind is the clearest sample.
        sample = max(members, key=lambda member: member.boundingRect().width())
        return LegendEntry(label, sample)

    entries: list[LegendEntry] = []
    if objects:
        entries.append(LegendEntry(_tr("Objects")))
        named = sorted(
            ((get_translated_display_name(kind), members) for kind, members in objects.items()),
            key=lambda pair: _natural_key(pair[0]),
        )
        entries.extend(line(name, members) for name, members in named)
    if plants:
        entries.append(LegendEntry(_tr("Plants")))
        entries.extend(
            line(name, plants[name]) for name in sorted(plants, key=_natural_key)
        )
    return entries


def _legend_swatch(item: Any, side_pt: float, dpi: float | None = None) -> QImage:
    """A square sample of *item*, painted by the item itself, as on the plan."""
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem

    from open_garden_planner.core.object_types import is_plant_type

    dpi = PLAN_RENDER_DPI if dpi is None else dpi
    pixels = max(8, int(round(side_pt * dpi / 72.0)))
    image = QImage(pixels, pixels, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    bounds = QRectF(item.boundingRect())
    if bounds.width() <= 0 or bounds.height() <= 0:
        return image
    side = max(bounds.width(), bounds.height())
    centre = bounds.center()
    if is_plant_type(getattr(item, "object_type", None)):
        # The plant itself: its bounding rect also holds its spacing circle.
        own = item.rect() if hasattr(item, "rect") else bounds
        if own.width() > 0 and own.height() > 0:
            side = max(own.width(), own.height())
            centre = own.center()
    else:
        # A patch of an area, not the whole lawn squeezed into a stamp; on a
        # line (a fence, a path), a few widths of it around its first leg.
        side = min(side, _LEGEND_PATCH_CM)
        points = getattr(item, "points", None)
        if points is not None and len(points) >= 2:
            centre = QPointF(
                (points[0].x() + points[1].x()) / 2.0, (points[0].y() + points[1].y()) / 2.0
            )
            side = min(side, max(_LEGEND_LINE_PATCH_MIN_CM, _LEGEND_LINE_WIDTHS * item.pen().widthF()))
    patch = QRectF(centre.x() - side / 2.0, centre.y() - side / 2.0, side, side)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    # Y-up, as every plan picture is.
    painter.translate(0, pixels)
    painter.scale(pixels / side, -pixels / side)
    painter.translate(-patch.left(), -patch.top())
    option = QStyleOptionGraphicsItem()
    option.exposedRect = bounds
    item.paint(painter, option, None)
    painter.end()
    return image


def _legend_columns(page_rect: QRectF) -> int:
    return 3 if page_rect.width() >= page_rect.height() else 2


def _legend_rows_per_page(page_rect: QRectF) -> int:
    """How many legend lines fit on one page, over all its columns."""
    room = page_rect.bottom() - (page_rect.top() + _pt(_TABLE_TITLE_H_MM) + _pt(4))
    return max(1, int(room // _pt(_LEGEND_ROW_H_MM))) * _legend_columns(page_rect)


def _render_legend(
    painter: QPainter,
    page_rect: QRectF,
    entries: list[LegendEntry],
    page: int = 1,
    pages: int = 1,
) -> None:
    """One page of the legend: *entries* is this page's share of the lines."""
    title_font = _font(14)
    title_font.setBold(True)
    row_font = _font(9)
    heading_font = _font(10)
    heading_font.setBold(True)

    painter.setFont(title_font)
    painter.setPen(QColor("#2e7d32"))
    title_h = _pt(_TABLE_TITLE_H_MM)
    painter.drawText(
        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        _paged_title(_tr("Legend"), page, pages),
    )

    row_h = _pt(_LEGEND_ROW_H_MM)
    swatch = _pt(_LEGEND_SWATCH_MM)
    top = page_rect.top() + title_h + _pt(4)
    columns = _legend_columns(page_rect)
    column_w = page_rect.width() / columns
    rows = max(1, _legend_rows_per_page(page_rect) // columns)

    if not entries and pages <= 1:
        painter.setFont(row_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), top, page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("Nothing is drawn on this plan yet."),
        )
        return

    # The samples are painted as an export paints the plan: selection handles
    # and badges hidden, whatever else ``_hide_overlay_items`` takes off.
    from open_garden_planner.services.export_service import ExportService

    scene = next((entry.item.scene() for entry in entries if entry.item is not None), None)
    samples: dict[int, QImage] = {}
    if scene is not None:
        hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
        try:
            samples = {
                index: _legend_swatch(entry.item, swatch)
                for index, entry in enumerate(entries) if entry.item is not None
            }
        finally:
            ExportService._restore_overlay_items(hidden_overlay, prior_selection)

    for index, entry in enumerate(entries):
        left = page_rect.left() + (index // rows) * column_w
        y = top + (index % rows) * row_h
        if entry.item is None:
            painter.setFont(heading_font)
            painter.setPen(QColor("#2e7d32"))
            painter.drawText(
                QRectF(left, y, column_w - _pt(4), row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                entry.label,
            )
            continue
        box = QRectF(left, y + (row_h - swatch) / 2, swatch, swatch)
        painter.drawImage(box, samples[index])
        pen = QPen(QColor("#555555"))
        pen.setWidthF(0.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)

        painter.setFont(row_font)
        painter.setPen(QColor("#333333"))
        text_w = column_w - swatch - _pt(7)
        painter.drawText(
            QRectF(left + swatch + _pt(3), y, text_w, row_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            painter.fontMetrics().elidedText(entry.label, Qt.TextElideMode.ElideRight, int(text_w)),
        )


def _shopping_list_fits(items: list[Any], page_rect: QRectF) -> bool:
    """Return True when ``items`` (plus title + header + footer slack) all fit
    on a single page of size ``page_rect``."""
    title_h = _pt(14)
    row_h = _pt(7)
    footer_slack = _pt(20)
    available = page_rect.bottom() - page_rect.top() - title_h - _pt(4) - row_h - footer_slack
    return len(items) * row_h <= available


def _render_shopping_list(
    painter: QPainter,
    page_rect: QRectF,
    items: list[Any],
    grand_total: float | None = None,
) -> int:
    """Render shopping list rows into ``page_rect``.

    Returns the index of the first item that did not fit so the caller can
    paginate; returns ``len(items)`` when everything fit.

    ``grand_total`` is the whole-list total to print as a footer; pass it only
    on the final page to avoid showing per-page subtotals labelled "Grand total".
    """
    title_font = _font(14)
    title_font.setBold(True)
    header_font = _font(9)
    header_font.setBold(True)
    row_font = _font(8)

    painter.setFont(title_font)
    painter.setPen(QColor("#2e7d32"))

    title_h = _pt(14)
    painter.drawText(
        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        _tr("Shopping List"),
    )

    cols = [
        (_tr("Category"), 0.13),
        (_tr("Item"), 0.32),
        (_tr("Quantity"), 0.12),
        (_tr("Unit"), 0.10),
        (_tr("Price"), 0.10),
        (_tr("Total"), 0.10),
        (_tr("Notes"), 0.13),
    ]

    row_h = _pt(7)
    y = page_rect.top() + title_h + _pt(4)

    painter.fillRect(QRectF(page_rect.left(), y, page_rect.width(), row_h), QColor("#2e7d32"))
    painter.setFont(header_font)
    painter.setPen(QColor("white"))
    x = page_rect.left()
    for label, frac in cols:
        col_w = page_rect.width() * frac
        painter.drawText(
            QRectF(x + _pt(2), y, col_w - _pt(4), row_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )
        x += col_w
    y += row_h

    painter.setFont(row_font)
    rendered = 0
    for idx, item in enumerate(items):
        if y + row_h > page_rect.bottom() - _pt(20):
            return idx
        bg = QColor("#f9f9f9") if idx % 2 == 0 else QColor("white")
        painter.fillRect(QRectF(page_rect.left(), y, page_rect.width(), row_h), bg)
        painter.setPen(QColor("#333333"))
        price_str = "" if item.price_each is None else f"{item.price_each:.2f}"
        total_str = "" if item.total_cost is None else f"{item.total_cost:.2f}"
        values = [
            item.category.value,
            item.name,
            f"{item.quantity:g}",
            item.unit,
            price_str,
            total_str,
            item.notes,
        ]
        x = page_rect.left()
        for val, frac in zip(values, [f for _, f in cols], strict=True):
            col_w = page_rect.width() * frac
            painter.drawText(
                QRectF(x + _pt(2), y, col_w - _pt(4), row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(val)[:60],
            )
            x += col_w
        y += row_h
        rendered = idx + 1

    if grand_total is not None:
        y += _pt(4)
        painter.setFont(header_font)
        painter.setPen(QColor("#2e7d32"))
        painter.drawText(
            QRectF(page_rect.left(), y, page_rect.width(), row_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            f"{_tr('Grand total')}: {grand_total:.2f}",
        )

    if not items:
        painter.setFont(row_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), y + _pt(4), page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("Shopping list is empty."),
        )

    return rendered


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class PdfReportService:
    """Generates a multi-page PDF report from a CanvasScene."""

    @staticmethod
    def generate(
        scene: CanvasScene,
        opts: PdfReportOptions,
        file_path: Path | str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Generate a PDF report and write it to *file_path*.

        Args:
            scene: The canvas scene to render.
            opts: Report configuration options.
            file_path: Destination path for the PDF file.
            progress_callback: Optional callable(current, total) for progress.
        """
        writer = QPdfWriter(str(file_path))
        # Set 72 DPI so painter.viewport() dimensions are in PDF points and match
        # the _pt(mm) helper. Default QPdfWriter resolution is much higher, which
        # causes all _pt() values to land in the top-left corner of the page.
        writer.setResolution(72)

        page_size_id = _PAGE_SIZE_MAP.get(opts.paper_size, QPageSize.PageSizeId.A4)
        orientation = (
            QPageLayout.Orientation.Landscape
            if opts.orientation == "landscape"
            else QPageLayout.Orientation.Portrait
        )
        page_layout = QPageLayout(
            QPageSize(page_size_id),
            orientation,
            QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
            QPageLayout.Unit.Millimeter,
        )
        writer.setPageLayout(page_layout)

        bed_groups = _bed_groups(scene) if opts.include_bed_details else []
        if not (
            opts.include_cover or opts.include_overview or bed_groups
            or opts.include_plant_list or opts.include_garden_notes
            or opts.include_harvest_summary or opts.include_legend
        ):
            return

        painter = QPainter()
        if not painter.begin(writer):
            raise RuntimeError("Failed to start PDF painter")

        try:
            page_rect = QRectF(painter.viewport())
            pages = PdfReportService.plan_pages(scene, opts, page_rect, bed_groups)
            total = len(pages)
            for idx, (page_type, data) in enumerate(pages):
                if idx > 0:
                    writer.newPage()

                if progress_callback:
                    progress_callback(idx, total)

                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

                painter.fillRect(page_rect, QColor("white"))
                PdfReportService.render_page(painter, page_rect, scene, opts, page_type, data)

                day = getattr(scene, "plan_date", None)
                if day is not None and day != date.today():
                    painter.setFont(_font(8))
                    painter.setPen(QColor("#333333"))
                    painter.drawText(
                        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), _pt(6)),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        _tr("Plan as of {date}").format(date=day.isoformat()),
                    )

        finally:
            painter.end()

        if progress_callback:
            progress_callback(total, total)

    @staticmethod
    def plan_pages(
        scene: CanvasScene,
        opts: PdfReportOptions,
        page_rect: QRectF,
        bed_groups: list[list[Any]] | None = None,
    ) -> list[tuple[str, Any]]:
        """Every page of the report, in order, as ``(page type, its data)``.

        A section that needs more than one page — the plant list, the Garden
        Notes, the Harvest Summary, the legend — is one entry per page, so the
        page count is the length of this list and a progress callback counts
        real pages. Every such section is cut here, by ``_section_pages`` or
        ``_notes_pages``; no renderer opens a page of its own (#836).
        """
        pages: list[tuple[str, Any]] = []
        if opts.include_cover:
            pages.append(("cover", None))
        if opts.include_overview:
            pages.append(("overview", None))
        if opts.include_bed_details:
            groups = _bed_groups(scene) if bed_groups is None else bed_groups
            pages.extend(("bed", group) for group in groups)
        table_rows = _table_rows_per_page(page_rect)
        if opts.include_plant_list:
            pages.extend(
                ("plant_list", page) for page in _section_pages(_plant_rows(scene), table_rows)
            )
        if opts.include_garden_notes:
            pages.extend(
                ("garden_notes", (lines, number, count))
                for lines, number, count, _first in _notes_pages(opts, page_rect)
            )
        if opts.include_harvest_summary:
            pages.extend(
                ("harvest_summary", page)
                for page in _section_pages(_harvest_rows(opts), table_rows)
            )
        if opts.include_legend:
            pages.extend(
                ("legend", (entries, number, count))
                for entries, number, count, _first in _section_pages(
                    _legend_entries(scene), _legend_rows_per_page(page_rect)
                )
            )
        return pages

    @staticmethod
    def render_page(
        painter: QPainter,
        page_rect: QRectF,
        scene: CanvasScene,
        opts: PdfReportOptions,
        page_type: str,
        data: Any,
    ) -> None:
        """Paint one page of ``plan_pages`` into *page_rect*."""
        if page_type == "cover":
            _render_cover(painter, page_rect, opts)
        elif page_type == "overview":
            _render_overview(painter, page_rect, scene, opts)
        elif page_type == "bed":
            _render_bed_detail(painter, page_rect, scene, data, opts)
        elif page_type == "plant_list":
            rows, page, pages, first_index = data
            _render_plant_list(painter, page_rect, rows, page, pages, first_index)
        elif page_type == "garden_notes":
            lines, page, pages = data
            _render_garden_notes(painter, page_rect, lines, page, pages)
        elif page_type == "harvest_summary":
            rows, page, pages, first_index = data
            _render_harvest_summary(painter, page_rect, rows, page, pages, first_index)
        elif page_type == "legend":
            entries, page, pages = data
            _render_legend(painter, page_rect, entries, page, pages)

    @staticmethod
    def export_shopping_list_to_pdf(
        items: list[Any],
        file_path: Path | str,
        paper_size: str = "A4",
    ) -> None:
        """Render a shopping list (US-12.6) to a single-or-multi-page PDF."""
        writer = QPdfWriter(str(file_path))
        writer.setResolution(72)
        page_size_id = _PAGE_SIZE_MAP.get(paper_size, QPageSize.PageSizeId.A4)
        writer.setPageLayout(QPageLayout(
            QPageSize(page_size_id),
            QPageLayout.Orientation.Portrait,
            QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
            QPageLayout.Unit.Millimeter,
        ))

        priced = [i.total_cost for i in items if i.total_cost is not None]
        grand_total = sum(priced) if priced else None

        painter = QPainter()
        if not painter.begin(writer):
            raise RuntimeError("Failed to start PDF painter")
        try:
            remaining = list(items)
            first = True
            while True:
                if not first:
                    writer.newPage()
                first = False
                page_rect = QRectF(painter.viewport())
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                painter.fillRect(page_rect, QColor("white"))
                # Probe whether the whole remaining slice fits on this page;
                # if so, this is the final page → emit the grand total here.
                fits_on_page = _shopping_list_fits(remaining, page_rect)
                rendered = _render_shopping_list(
                    painter, page_rect, remaining,
                    grand_total=grand_total if fits_on_page else None,
                )
                if rendered >= len(remaining):
                    break
                if rendered == 0:
                    raise RuntimeError(
                        "Shopping list row too large to fit on a page"
                    )
                remaining = remaining[rendered:]
        finally:
            painter.end()

    @staticmethod
    def _find_beds(scene: CanvasScene) -> list[Any]:
        from open_garden_planner.core.object_types import is_bed_type

        present = getattr(scene, "is_present", None)
        return [
            item
            for item in scene.items()
            if is_bed_type(getattr(item, "object_type", None))
            and (present is None or present(item))
        ]
