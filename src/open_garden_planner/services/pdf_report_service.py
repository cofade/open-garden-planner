"""Multi-page PDF report service for garden plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QMarginsF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen


def _tr(text: str) -> str:
    """Translate a service-layer string under the PdfReportService context."""
    return QCoreApplication.translate("PdfReportService", text)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

# Imported lazily inside _scene_to_image to avoid circular imports
_PDF_DPI = 72


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


def _scene_to_image(scene: Any, source: QRectF, dest: QRectF) -> QImage:
    """Render *source* region of *scene* into a QImage sized to *dest*, with Y-flip.

    Using a temporary QImage avoids PDF/SVG coordinate-system interactions that
    make the painter pre-flip approach unreliable on non-QImage devices.
    ItemIgnoresTransformations text items are pre-scaled so they appear
    proportionally correct at the PDF's 72-DPI output size.
    """
    from open_garden_planner.services.export_service import ExportService

    w = max(1, int(round(dest.width())))
    h = max(1, int(round(dest.height())))

    # Scale factor: output physical width (cm at 72 DPI) / scene source width (cm)
    w_cm = w / _PDF_DPI * 2.54
    scale = w_cm / max(1.0, source.width())

    saved_text = ExportService._prepare_text_for_export(scene, scale, _PDF_DPI)
    hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
    try:
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
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

    title_font = QFont("Arial", 7)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("white"))
    painter.drawText(
        QRectF(bar.left() + _pt(2), bar.top(), bar.width() / 2, bar.height()),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        title,
    )
    subtitle_font = QFont("Arial", 6)
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

    font = QFont("Arial", max(4, int(size * 0.4)))
    painter.setFont(font)
    painter.drawText(
        QRectF(-size / 2, -half - _pt(5), size, _pt(5)),
        Qt.AlignmentFlag.AlignCenter,
        _tr("N"),
    )
    painter.restore()


def _draw_scale_bar(
    painter: QPainter,
    left: float,
    bottom: float,
    canvas_width_cm: float,
    page_width_pt: float,
) -> None:
    """Draw a 10 m scale bar below the plan overview."""
    # Pick a round scale bar length: 10 m = 1000 cm
    bar_m = 10
    bar_cm = bar_m * 100
    bar_pt = bar_cm / canvas_width_cm * page_width_pt
    bar_pt = max(20.0, min(bar_pt, page_width_pt * 0.25))  # clamp

    pen = QPen(QColor("#333333"))
    pen.setWidthF(1.0)
    painter.setPen(pen)

    y = bottom + _pt(2)
    painter.drawLine(QPointF(left, y), QPointF(left + bar_pt, y))
    painter.drawLine(QPointF(left, y - _pt(1.5)), QPointF(left, y + _pt(1.5)))
    painter.drawLine(QPointF(left + bar_pt, y - _pt(1.5)), QPointF(left + bar_pt, y + _pt(1.5)))

    font = QFont("Arial", 5)
    painter.setFont(font)
    painter.setPen(QColor("#333333"))
    painter.drawText(
        QRectF(left, y + _pt(1), bar_pt, _pt(6)),
        Qt.AlignmentFlag.AlignCenter,
        f"{bar_m} m",
    )


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------

def _render_cover(painter: QPainter, page_rect: QRectF, opts: PdfReportOptions) -> None:
    painter.fillRect(page_rect, QColor("#f5f5dc"))

    center_x = page_rect.center().x()
    title_y = page_rect.top() + page_rect.height() * 0.3

    # Project name
    font = QFont("Arial", 28)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#2e7d32"))
    painter.drawText(
        QRectF(page_rect.left(), title_y, page_rect.width(), _pt(20)),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        opts.project_name,
    )

    # Subtitle
    font2 = QFont("Arial", 12)
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
    img = _scene_to_image(scene, canvas_rect, content_rect)
    painter.drawImage(content_rect, img)

    # North arrow (top-right of content area)
    _draw_north_arrow(
        painter,
        content_rect.right() - north_size,
        content_rect.top() + north_size,
        north_size,
    )

    # Scale bar
    _draw_scale_bar(
        painter,
        content_rect.left() + _pt(4),
        content_rect.bottom(),
        canvas_rect.width(),
        content_rect.width(),
    )

    _draw_title_block(
        painter,
        page_rect,
        opts.project_name,
        opts.export_date,
    )


def _render_bed_detail(
    painter: QPainter,
    page_rect: QRectF,
    scene: CanvasScene,
    bed_item: Any,
    opts: PdfReportOptions,
) -> None:
    title_bar_h = _pt(8)
    content_rect = QRectF(
        page_rect.left(),
        page_rect.top() + title_bar_h,
        page_rect.width(),
        page_rect.height() - title_bar_h,
    )

    bed_scene_rect = bed_item.mapToScene(bed_item.boundingRect()).boundingRect()
    padding = max(bed_scene_rect.width(), bed_scene_rect.height()) * 0.1
    source = bed_scene_rect.adjusted(-padding, -padding, padding, padding)
    img = _scene_to_image(scene, source, content_rect)
    painter.drawImage(content_rect, img)

    bed_name = getattr(bed_item, "name", "") or _tr("Bed")
    _draw_title_block(painter, page_rect, f"{opts.project_name} – {bed_name}", opts.export_date)


def _render_plant_list(
    painter: QPainter,
    page_rect: QRectF,
    scene: CanvasScene,
    _opts: PdfReportOptions,
) -> None:
    from open_garden_planner.core.object_types import ObjectType

    plant_items = [
        i for i in scene.items()
        if hasattr(i, "object_type") and getattr(i, "object_type", None) in (
            ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL
        )
    ]

    header_font = QFont("Arial", 9)
    header_font.setBold(True)
    row_font = QFont("Arial", 8)
    title_font = QFont("Arial", 14)
    title_font.setBold(True)

    painter.setFont(title_font)
    painter.setPen(QColor("#2e7d32"))

    title_h = _pt(14)
    painter.drawText(
        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        _tr("Plant List"),
    )

    cols = [
        ("Name", 0.35),
        ("Type", 0.20),
        ("Position (cm)", 0.25),
        ("Notes", 0.20),
    ]

    row_h = _pt(7)
    y = page_rect.top() + title_h + _pt(4)

    # Header row
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

    # Data rows
    painter.setFont(row_font)
    for idx, item in enumerate(plant_items):
        if y + row_h > page_rect.bottom() - _pt(8):
            break  # Don't overflow page

        bg = QColor("#f9f9f9") if idx % 2 == 0 else QColor("white")
        painter.fillRect(QRectF(page_rect.left(), y, page_rect.width(), row_h), bg)
        painter.setPen(QColor("#333333"))

        name = getattr(item, "name", "") or ""
        obj_type = getattr(item, "object_type", None)
        type_str = obj_type.name.replace("_", " ").title() if obj_type else ""
        center = item.mapToScene(item.boundingRect().center())
        pos_str = f"({center.x():.0f}, {center.y():.0f})"
        metadata = getattr(item, "metadata", {}) or {}
        notes = (metadata.get("plant_instance") or {}).get("notes", "") or ""

        values = [name, type_str, pos_str, notes]
        x = page_rect.left()
        for val, frac in zip(values, [f for _, f in cols], strict=True):
            col_w = page_rect.width() * frac
            painter.drawText(
                QRectF(x + _pt(2), y, col_w - _pt(4), row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                val[:40],
            )
            x += col_w
        y += row_h

    if not plant_items:
        painter.setFont(row_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), y + _pt(4), page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("No plants found in this project."),
        )


def _render_garden_notes(
    painter: QPainter,
    page_rect: QRectF,
    _scene: CanvasScene,
    opts: PdfReportOptions,
) -> None:
    """Render the Garden Notes page (US-12.9): chronological list of journal entries.

    Paginates automatically — when content runs past ``page_rect.bottom()``, calls
    ``painter.device().newPage()`` and continues on a fresh page with the same
    "Garden Notes" header. No content is silently truncated.
    """
    from pathlib import Path as _Path  # noqa: PLC0415

    from PyQt6.QtGui import QFontMetricsF  # noqa: PLC0415

    from open_garden_planner.models.journal_note import JournalNote  # noqa: PLC0415

    notes_raw = opts.garden_journal_notes or {}
    notes: list[JournalNote] = []
    for raw in notes_raw.values():
        if not isinstance(raw, dict):
            continue
        notes.append(JournalNote.from_dict(raw))
    notes.sort(key=lambda n: n.date or "", reverse=True)

    title_font = QFont("Arial", 14)
    title_font.setBold(True)
    date_font = QFont("Arial", 10)
    date_font.setBold(True)
    body_font = QFont("Arial", 9)
    meta_font = QFont("Arial", 8)
    meta_font.setItalic(True)
    body_metrics = QFontMetricsF(body_font)

    title_h = _pt(14)
    body_line_h = _pt(4.5)
    spacing = _pt(3)
    bottom_limit = page_rect.bottom() - _pt(2)

    def _draw_header() -> float:
        painter.setFont(title_font)
        painter.setPen(QColor("#2e7d32"))
        painter.drawText(
            QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("Garden Notes"),
        )
        return page_rect.top() + title_h + _pt(4)

    def _new_page_if_needed(current_y: float, needed: float) -> float:
        """Open a new page when ``needed`` more vertical space won't fit."""
        if current_y + needed <= bottom_limit:
            return current_y
        device = painter.device()
        if hasattr(device, "newPage"):
            device.newPage()
            painter.fillRect(page_rect, QColor("white"))
        return _draw_header()

    y = _draw_header()

    if not notes:
        painter.setFont(body_font)
        painter.setPen(QColor("#777777"))
        painter.drawText(
            QRectF(page_rect.left(), y, page_rect.width(), _pt(10)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _tr("No journal notes recorded."),
        )
        return

    for note in notes:
        y = _new_page_if_needed(y, _pt(6) + body_line_h)

        painter.setFont(date_font)
        painter.setPen(QColor("#333333"))
        painter.drawText(
            QRectF(page_rect.left(), y, page_rect.width(), _pt(6)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            note.date or _tr("(no date)"),
        )
        y += _pt(6)

        painter.setFont(body_font)
        painter.setPen(QColor("#222222"))
        text_block = note.text.strip() or _tr("(empty)")
        paragraphs = text_block.splitlines() or [text_block]
        for paragraph in paragraphs:
            wrapped = _wrap_to_width(
                paragraph or " ", page_rect.width(), body_metrics
            )
            for line in wrapped:
                y = _new_page_if_needed(y, body_line_h)
                painter.setFont(body_font)
                painter.setPen(QColor("#222222"))
                painter.drawText(
                    QRectF(page_rect.left(), y, page_rect.width(), body_line_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    line,
                )
                y += body_line_h

        if note.photo_path:
            y = _new_page_if_needed(y, body_line_h)
            painter.setFont(meta_font)
            painter.setPen(QColor("#666666"))
            painter.drawText(
                QRectF(page_rect.left(), y, page_rect.width(), body_line_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _tr("(photo: {filename})").format(
                    filename=_Path(note.photo_path).name
                ),
            )
            y += body_line_h

        y += spacing


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


def _render_legend(
    painter: QPainter,
    page_rect: QRectF,
    scene: CanvasScene,
    _opts: PdfReportOptions,
) -> None:
    title_font = QFont("Arial", 14)
    title_font.setBold(True)
    row_font = QFont("Arial", 9)

    painter.setFont(title_font)
    painter.setPen(QColor("#2e7d32"))
    title_h = _pt(14)
    painter.drawText(
        QRectF(page_rect.left(), page_rect.top(), page_rect.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        _tr("Legend"),
    )

    layers = scene.layers if hasattr(scene, "layers") else []
    row_h = _pt(8)
    swatch = _pt(5)
    y = page_rect.top() + title_h + _pt(4)

    painter.setFont(row_font)
    for layer in layers:
        if y + row_h > page_rect.bottom():
            break
        # Color swatch (use a shade based on layer z_order for distinction)
        hue = (layer.z_order * 47) % 360
        color = QColor.fromHsv(hue, 120, 200)
        painter.fillRect(
            QRectF(page_rect.left(), y + (row_h - swatch) / 2, swatch, swatch),
            color,
        )
        pen = QPen(QColor("#555555"))
        pen.setWidthF(0.5)
        painter.setPen(pen)
        painter.drawRect(QRectF(page_rect.left(), y + (row_h - swatch) / 2, swatch, swatch))

        painter.setPen(QColor("#333333"))
        visibility = "" if layer.visible else " [hidden]"
        painter.drawText(
            QRectF(page_rect.left() + swatch + _pt(3), y, page_rect.width() - swatch - _pt(3), row_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"{layer.name}{visibility}",
        )
        y += row_h


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
    title_font = QFont("Arial", 14)
    title_font.setBold(True)
    header_font = QFont("Arial", 9)
    header_font.setBold(True)
    row_font = QFont("Arial", 8)

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

        # Collect pages to render
        pages: list[tuple[str, Any]] = []
        if opts.include_cover:
            pages.append(("cover", None))
        if opts.include_overview:
            pages.append(("overview", None))
        if opts.include_bed_details:
            bed_items = PdfReportService._find_beds(scene)
            for bed in bed_items:
                pages.append(("bed", bed))
        if opts.include_plant_list:
            pages.append(("plant_list", None))
        if opts.include_garden_notes:
            pages.append(("garden_notes", None))
        if opts.include_legend:
            pages.append(("legend", None))

        if not pages:
            return

        total = len(pages)
        painter = QPainter()
        if not painter.begin(writer):
            raise RuntimeError("Failed to start PDF painter")

        try:
            for idx, (page_type, data) in enumerate(pages):
                if idx > 0:
                    writer.newPage()

                if progress_callback:
                    progress_callback(idx, total)

                page_rect = QRectF(painter.viewport())

                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

                painter.fillRect(page_rect, QColor("white"))

                if page_type == "cover":
                    _render_cover(painter, page_rect, opts)
                elif page_type == "overview":
                    _render_overview(painter, page_rect, scene, opts)
                elif page_type == "bed":
                    _render_bed_detail(painter, page_rect, scene, data, opts)
                elif page_type == "plant_list":
                    _render_plant_list(painter, page_rect, scene, opts)
                elif page_type == "garden_notes":
                    _render_garden_notes(painter, page_rect, scene, opts)
                elif page_type == "legend":
                    _render_legend(painter, page_rect, scene, opts)

        finally:
            painter.end()

        if progress_callback:
            progress_callback(total, total)

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

        return [
            item
            for item in scene.items()
            if hasattr(item, "object_type") and is_bed_type(getattr(item, "object_type", None))
        ]
