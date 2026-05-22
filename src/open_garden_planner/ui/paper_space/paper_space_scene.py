"""``PaperSpaceScene``: a QGraphicsScene that holds one printable page.

The scene exposes a fixed *page rectangle* (in cm) and the items that
make up the layout: viewports onto the model scene, a title block, and
a scale bar. Items are positioned in paper-cm (1 unit = 1 cm).

The MVP supports exactly one page per layout and one viewport per
layout. The serialisation format leaves room to grow into multi-page
later without breaking compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.ui.paper_space.page_sizes import (
    DEFAULT_ORIENTATION,
    DEFAULT_PAGE_NAME,
    page_size_cm,
)
from open_garden_planner.ui.paper_space.scale_bar_item import ScaleBarItem
from open_garden_planner.ui.paper_space.title_block_item import TitleBlockItem
from open_garden_planner.ui.paper_space.viewport_item import ViewportItem

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


_OFF_PAGE_PADDING_CM = 5.0  # extra scene area around the page


class PaperSpaceScene(QGraphicsScene):
    """One-page paper-space scene with a viewport + title block + scale bar.

    The page is drawn as a white rectangle with a thin border; the area
    *outside* the page is shaded so users see the page edge clearly.
    """

    def __init__(
        self,
        source_scene: CanvasScene,
        page_name: str = DEFAULT_PAGE_NAME,
        orientation: str = DEFAULT_ORIENTATION,
    ) -> None:
        super().__init__()
        self._source_scene = source_scene
        self._page_name = page_name
        self._orientation = orientation
        self._viewport: ViewportItem | None = None
        self._title_block: TitleBlockItem | None = None
        self._scale_bar: ScaleBarItem | None = None
        self._populate_default()

    # ── Page geometry ──────────────────────────────────────────────────

    @property
    def page_name(self) -> str:
        return self._page_name

    @property
    def orientation(self) -> str:
        return self._orientation

    def page_rect_cm(self) -> QRectF:
        w, h = page_size_cm(self._page_name, self._orientation)
        return QRectF(0.0, 0.0, w, h)

    def set_page_size(self, name: str, orientation: str) -> None:
        self._page_name = name
        self._orientation = orientation
        self._refit_layout()
        self._refresh_scene_rect()

    # ── Item accessors ─────────────────────────────────────────────────

    @property
    def viewport(self) -> ViewportItem | None:
        return self._viewport

    @property
    def title_block(self) -> TitleBlockItem | None:
        return self._title_block

    @property
    def scale_bar(self) -> ScaleBarItem | None:
        return self._scale_bar

    # ── Background painting ────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        # Off-page area is light grey; the page itself is white.
        painter.fillRect(rect, QBrush(QColor(220, 220, 220)))
        page = self.page_rect_cm()
        painter.fillRect(page, QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(80, 80, 80), 0.4))
        painter.setBrush(QBrush())
        painter.drawRect(page)

    # ── Persistence ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        if self._viewport is not None:
            items.append(self._viewport.to_dict())
        if self._title_block is not None:
            items.append(self._title_block.to_dict())
        if self._scale_bar is not None:
            items.append(self._scale_bar.to_dict())
        return {
            "page_name": self._page_name,
            "orientation": self._orientation,
            "items": items,
        }

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Replace the scene contents from a serialised dict.

        Unknown item types are skipped so the file format can grow
        forward without breaking older builds.
        """
        self._page_name = str(data.get("page_name", DEFAULT_PAGE_NAME))
        self._orientation = str(data.get("orientation", DEFAULT_ORIENTATION))
        self.clear()
        self._viewport = None
        self._title_block = None
        self._scale_bar = None

        for entry in data.get("items", []):
            kind = entry.get("type")
            if kind == "viewport":
                vp = ViewportItem.from_dict(self._source_scene, entry)
                self.addItem(vp)
                self._viewport = vp
            elif kind == "title_block":
                tb = TitleBlockItem.from_dict(entry)
                self.addItem(tb)
                self._title_block = tb
            elif kind == "scale_bar":
                sb = ScaleBarItem.from_dict(entry)
                self.addItem(sb)
                self._scale_bar = sb

        # Make sure scale bar / title block stay in sync with the
        # current viewport scale (the source viewport rect may have
        # changed in the user's layout).
        self.sync_derived_fields()
        self._refresh_scene_rect()

    # ── Sync helpers ───────────────────────────────────────────────────

    def sync_derived_fields(self, project_name: str | None = None) -> None:
        """Refresh title-block & scale-bar values from the viewport scale.

        Called whenever the project is saved or the viewport scale
        changes. Pass ``project_name`` to update the title block's
        Project field; ``None`` leaves it untouched.
        """
        if self._viewport is None:
            return
        scale = self._viewport.scale_factor
        if self._scale_bar is not None:
            self._scale_bar.scale_factor = scale
        if self._title_block is not None:
            self._title_block.scale_label = _format_scale(scale)
            if project_name is not None:
                self._title_block.project_name = project_name

    # ── Defaults ───────────────────────────────────────────────────────

    def _populate_default(self) -> None:
        """Create the default viewport / title block / scale bar layout."""
        page = self.page_rect_cm()
        margin = 1.5

        # Default viewport: fills most of the page, scaled to fit the
        # full source canvas with a small margin.
        vp_rect = QRectF(
            page.x() + margin,
            page.y() + margin,
            page.width() - 2 * margin,
            page.height() - 2 * margin - 4.0,  # leave room for the title block
        )
        source_rect = self._fit_source_to_viewport(vp_rect)
        viewport = ViewportItem(
            source_scene=self._source_scene,
            source_rect=source_rect,
            paper_rect=QRectF(0, 0, vp_rect.width(), vp_rect.height()),
        )
        viewport.setPos(QPointF(vp_rect.x(), vp_rect.y()))
        self.addItem(viewport)
        self._viewport = viewport

        # Title block in the bottom-right corner.
        tb = TitleBlockItem(
            scale_label=_format_scale(viewport.scale_factor)
        )
        tb_w = 7.0
        tb_h = 3.0
        tb.setRect(0, 0, tb_w, tb_h)
        tb.setPos(QPointF(page.right() - margin - tb_w, page.bottom() - margin - tb_h))
        self.addItem(tb)
        self._title_block = tb

        # Scale bar above the title block.
        sb = ScaleBarItem(scale_factor=viewport.scale_factor)
        sb_w = 6.0
        sb.setRect(0, 0, sb_w, 0.6)
        sb.setPos(
            QPointF(page.right() - margin - sb_w, page.bottom() - margin - tb_h - 1.0)
        )
        self.addItem(sb)
        self._scale_bar = sb

        self._refresh_scene_rect()

    def _fit_source_to_viewport(self, vp_rect: QRectF) -> QRectF:
        """Pick a source_rect whose aspect matches the viewport and covers the canvas."""
        canvas_rect = self._canvas_bounds()
        if vp_rect.width() <= 0 or vp_rect.height() <= 0:
            return canvas_rect
        target_aspect = vp_rect.width() / vp_rect.height()
        canvas_aspect = (
            canvas_rect.width() / canvas_rect.height()
            if canvas_rect.height() > 0
            else 1.0
        )
        if canvas_aspect > target_aspect:
            # Canvas is wider than viewport — keep width, grow height.
            new_w = canvas_rect.width()
            new_h = new_w / target_aspect
        else:
            new_h = canvas_rect.height()
            new_w = new_h * target_aspect
        cx = canvas_rect.x() + canvas_rect.width() / 2.0
        cy = canvas_rect.y() + canvas_rect.height() / 2.0
        return QRectF(cx - new_w / 2.0, cy - new_h / 2.0, new_w, new_h)

    def _canvas_bounds(self) -> QRectF:
        if hasattr(self._source_scene, "canvas_rect"):
            return QRectF(self._source_scene.canvas_rect)
        return QRectF(self._source_scene.sceneRect())

    def _refit_layout(self) -> None:
        """Reposition default items to fit a new page size."""
        # Stay conservative: only nudge the viewport / title block if
        # they still align with the old layout. This is the MVP — full
        # layout re-flow is a job for a later iteration.
        if self._viewport is None:
            return
        page = self.page_rect_cm()
        margin = 1.5
        self._viewport.set_paper_rect(
            QRectF(0, 0, page.width() - 2 * margin, page.height() - 2 * margin - 4.0)
        )
        self._viewport.setPos(QPointF(page.x() + margin, page.y() + margin))
        if self._title_block is not None:
            r = self._title_block.rect()
            self._title_block.setPos(
                QPointF(
                    page.right() - margin - r.width(),
                    page.bottom() - margin - r.height(),
                )
            )
        if self._scale_bar is not None:
            sb_w = self._scale_bar.rect().width()
            tb_h = self._title_block.rect().height() if self._title_block else 3.0
            self._scale_bar.setPos(
                QPointF(
                    page.right() - margin - sb_w,
                    page.bottom() - margin - tb_h - 1.0,
                )
            )

    def _refresh_scene_rect(self) -> None:
        page = self.page_rect_cm()
        self.setSceneRect(
            page.x() - _OFF_PAGE_PADDING_CM,
            page.y() - _OFF_PAGE_PADDING_CM,
            page.width() + 2 * _OFF_PAGE_PADDING_CM,
            page.height() + 2 * _OFF_PAGE_PADDING_CM,
        )


def _format_scale(scale_factor: float) -> str:
    """Render a 1:N label for a paper-cm-per-model-cm factor."""
    if scale_factor <= 0:
        return ""
    denom = 1.0 / scale_factor
    if denom >= 10:
        return f"1:{int(round(denom))}"
    return f"1:{denom:.1f}"
