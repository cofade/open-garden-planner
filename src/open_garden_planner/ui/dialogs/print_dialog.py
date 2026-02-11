"""Print dialog for printing garden plans with scaling and page layout options."""

import math
from datetime import date

from PyQt6.QtCore import QMarginsF, QRectF
from PyQt6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPen
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

# Scale presets: display name -> scale denominator (0 = fit to page)
SCALE_PRESETS = [
    ("Fit to Page", 0),
    ("1:20", 20),
    ("1:50", 50),
    ("1:100", 100),
    ("1:200", 200),
    ("1:500", 500),
]


class PrintOptionsDialog(QDialog):
    """Dialog for configuring print options before showing print preview.

    Allows user to select scale, and toggle grid/labels/legend inclusion.
    """

    def __init__(
        self,
        canvas_width_cm: float,
        canvas_height_cm: float,
        grid_visible: bool,
        labels_visible: bool,
        parent: object = None,
    ) -> None:
        """Initialize the Print Options dialog.

        Args:
            canvas_width_cm: Canvas width in centimeters
            canvas_height_cm: Canvas height in centimeters
            grid_visible: Whether grid is currently visible
            labels_visible: Whether labels are currently visible
            parent: Parent widget
        """
        super().__init__(parent)

        self._canvas_width_cm = canvas_width_cm
        self._canvas_height_cm = canvas_height_cm

        self.setWindowTitle(self.tr("Print Options"))
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui(grid_visible, labels_visible)
        self._update_page_info()

    def _setup_ui(self, grid_visible: bool, labels_visible: bool) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Scale group
        scale_group = QGroupBox(self.tr("Scale"))
        scale_layout = QVBoxLayout(scale_group)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel(self.tr("Print scale:")))
        self._scale_combo = QComboBox()
        for display_name, _denom in SCALE_PRESETS:
            self._scale_combo.addItem(display_name)
        self._scale_combo.setCurrentIndex(0)  # Default: Fit to Page
        self._scale_combo.currentIndexChanged.connect(self._update_page_info)
        scale_row.addWidget(self._scale_combo)
        scale_layout.addLayout(scale_row)

        # Page count info
        self._page_info_label = QLabel()
        self._page_info_label.setStyleSheet("color: palette(mid);")
        scale_layout.addWidget(self._page_info_label)

        layout.addWidget(scale_group)

        # Include options group
        include_group = QGroupBox(self.tr("Include"))
        include_layout = QVBoxLayout(include_group)

        self._grid_check = QCheckBox(self.tr("Grid"))
        self._grid_check.setChecked(grid_visible)
        include_layout.addWidget(self._grid_check)

        self._labels_check = QCheckBox(self.tr("Object labels"))
        self._labels_check.setChecked(labels_visible)
        include_layout.addWidget(self._labels_check)

        self._legend_check = QCheckBox(self.tr("Legend (project name, scale, date)"))
        self._legend_check.setChecked(True)
        include_layout.addWidget(self._legend_check)

        layout.addWidget(include_group)

        # Canvas info
        info_label = QLabel(
            self.tr("Canvas: {w} m × {h} m").format(
                w=f"{self._canvas_width_cm / 100:.1f}",
                h=f"{self._canvas_height_cm / 100:.1f}",
            )
        )
        info_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_page_info(self) -> None:
        """Update the page count estimation label."""
        idx = self._scale_combo.currentIndex()
        _name, denom = SCALE_PRESETS[idx]

        if denom == 0:
            self._page_info_label.setText(self.tr("Single page (scaled to fit)"))
        else:
            # Estimate pages for A4 landscape at this scale
            # A4 landscape printable area ~27.7 x 19.0 cm (with margins)
            printable_w = 27.7
            printable_h = 19.0

            # At scale 1:denom, 1 cm on paper = denom cm in real world
            real_w = printable_w * denom
            real_h = printable_h * denom

            cols = max(1, math.ceil(self._canvas_width_cm / real_w))
            rows = max(1, math.ceil(self._canvas_height_cm / real_h))
            total = cols * rows

            if total == 1:
                self._page_info_label.setText(
                    self.tr("1 page at {scale}").format(scale=f"1:{denom}")
                )
            else:
                self._page_info_label.setText(
                    self.tr("{total} pages ({cols} × {rows}) at {scale}").format(
                        total=total, cols=cols, rows=rows, scale=f"1:{denom}"
                    )
                )

    @property
    def scale_denominator(self) -> int:
        """Get the selected scale denominator (0 = fit to page)."""
        idx = self._scale_combo.currentIndex()
        return SCALE_PRESETS[idx][1]

    @property
    def include_grid(self) -> bool:
        """Whether to include the grid in the printout."""
        return self._grid_check.isChecked()

    @property
    def include_labels(self) -> bool:
        """Whether to include object labels in the printout."""
        return self._labels_check.isChecked()

    @property
    def include_legend(self) -> bool:
        """Whether to include a legend in the printout."""
        return self._legend_check.isChecked()


class GardenPrintManager:
    """Manages printing of the garden scene with scaling and multi-page support."""

    # Legend bar height in mm
    LEGEND_HEIGHT_MM = 12

    def __init__(
        self,
        scene: QGraphicsScene,
        project_name: str = "Garden Plan",
    ) -> None:
        """Initialize the print manager.

        Args:
            scene: The canvas scene to print
            project_name: Name of the project for the legend
        """
        self._scene = scene
        self._project_name = project_name
        self._scale_denom = 0
        self._include_grid = False
        self._include_labels = True
        self._include_legend = True

        # State saved/restored during printing
        self._saved_labels_visible: bool | None = None
        self._saved_bg_clips: list[tuple] = []

    def configure(
        self,
        scale_denominator: int,
        include_grid: bool,
        include_labels: bool,
        include_legend: bool,
    ) -> None:
        """Configure print options.

        Args:
            scale_denominator: Scale denominator (0 = fit to page)
            include_grid: Whether to include grid
            include_labels: Whether to include object labels
            include_legend: Whether to include legend bar
        """
        self._scale_denom = scale_denominator
        self._include_grid = include_grid
        self._include_labels = include_labels
        self._include_legend = include_legend

    def print_preview(self, parent=None) -> None:
        """Show the print preview dialog.

        Args:
            parent: Parent widget for the dialog
        """
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)

        # Default to A4 landscape for garden plans
        page_layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QMarginsF(10, 10, 10, 10),
        )
        printer.setPageLayout(page_layout)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle("Print Preview - " + self._project_name)
        preview.paintRequested.connect(self._render_to_printer)
        preview.exec()

    def _render_to_printer(self, printer: QPrinter) -> None:
        """Render the scene to the printer.

        Args:
            printer: The QPrinter to render to
        """
        scene = self._scene
        canvas_rect = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()

        # Get printable area in mm from the printer
        page_layout = printer.pageLayout()
        page_rect_mm = page_layout.paintRect(QPageLayout.Unit.Millimeter)
        printable_w_mm = page_rect_mm.width()
        printable_h_mm = page_rect_mm.height()

        # Reserve space for legend if enabled
        legend_h_mm = self.LEGEND_HEIGHT_MM if self._include_legend else 0
        content_h_mm = printable_h_mm - legend_h_mm

        # Prepare scene state for printing (text scaling, labels, selection)
        self._prepare_scene_for_print()

        try:
            painter = QPainter()
            if not painter.begin(printer):
                return

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            if self._scale_denom == 0:
                # Fit to single page
                self._render_fit_to_page(
                    painter, printer, canvas_rect,
                    printable_w_mm, content_h_mm, legend_h_mm,
                )
            else:
                # Specific scale - may require multiple pages
                self._render_scaled(
                    painter, printer, canvas_rect,
                    printable_w_mm, content_h_mm, legend_h_mm,
                )

            painter.end()
        finally:
            self._restore_scene_after_print()

    def _prepare_scene_for_print(self) -> None:
        """Prepare the scene for printing by adjusting labels and clearing selection.

        Also temporarily crops background images to canvas bounds because
        QGraphicsScene.render() does not apply ItemClipsToShape.
        """
        from open_garden_planner.ui.canvas.items.background_image_item import (
            BackgroundImageItem,
        )

        scene = self._scene

        # Save and set labels
        if hasattr(scene, "labels_enabled"):
            self._saved_labels_visible = scene.labels_enabled
            scene.set_labels_visible(self._include_labels)

        # Hide background images during printing.
        # scene.render() ignores ItemClipsToShape, so background images
        # that extend beyond the canvas would overflow into the print.
        # We hide them and instead render them manually with clipping.
        self._saved_bg_clips = []
        for item in scene.items():
            if isinstance(item, BackgroundImageItem) and item.isVisible():
                self._saved_bg_clips.append(item)
                item.setVisible(False)

        # Clear selection to avoid printing selection handles
        scene.clearSelection()

    def _restore_scene_after_print(self) -> None:
        """Restore the scene state after printing."""
        scene = self._scene

        if self._saved_labels_visible is not None and hasattr(scene, "set_labels_visible"):
            scene.set_labels_visible(self._saved_labels_visible)
            self._saved_labels_visible = None

        # Restore background image visibility
        for item in self._saved_bg_clips:
            item.setVisible(True)
        self._saved_bg_clips = []

    def _render_fit_to_page(
        self,
        painter: QPainter,
        printer: QPrinter,
        canvas_rect: QRectF,
        printable_w_mm: float,
        content_h_mm: float,
        legend_h_mm: float,
    ) -> None:
        """Render the entire garden fitted to a single page.

        Args:
            painter: Active QPainter on the printer
            printer: The QPrinter device
            canvas_rect: Scene canvas rectangle (in cm)
            printable_w_mm: Printable width in mm
            content_h_mm: Printable height for content (excluding legend) in mm
            legend_h_mm: Height reserved for legend in mm
        """
        resolution = printer.resolution()  # DPI
        canvas_w = canvas_rect.width()

        # Convert printable area to pixels
        content_w_px = printable_w_mm / 25.4 * resolution
        content_h_px = content_h_mm / 25.4 * resolution

        # Calculate scale to fit, preserving aspect ratio
        scale_x = content_w_px / canvas_w
        scale_y = content_h_px / canvas_rect.height()
        scale = min(scale_x, scale_y)

        # Calculate the target rect centered in the content area
        target_w = canvas_w * scale
        target_h = canvas_rect.height() * scale
        offset_x = (content_w_px - target_w) / 2
        offset_y = (content_h_px - target_h) / 2

        target_rect = QRectF(offset_x, offset_y, target_w, target_h)

        # Render the scene with Y-flip.
        # The CanvasView displays with a Y-flip (CAD convention: Y-up).
        # scene.render() uses native Qt coords (Y-down), so we flip the
        # painter to match what the user sees on screen.
        painter.save()
        painter.translate(0, 2 * offset_y + target_h)
        painter.scale(1, -1)
        self._scene.render(painter, target_rect, canvas_rect)
        painter.restore()

        # Draw legend (outside the flip)
        if legend_h_mm > 0:
            # Calculate effective scale for legend text
            effective_scale_denom = int(canvas_w * 10 / printable_w_mm) if printable_w_mm > 0 else 100
            self._draw_legend(
                painter, printer, printable_w_mm, content_h_mm,
                legend_h_mm, effective_scale_denom,
            )

    def _render_scaled(
        self,
        painter: QPainter,
        printer: QPrinter,
        canvas_rect: QRectF,
        printable_w_mm: float,
        content_h_mm: float,
        legend_h_mm: float,
    ) -> None:
        """Render the garden at a specific scale, potentially across multiple pages.

        Args:
            painter: Active QPainter on the printer
            printer: The QPrinter device
            canvas_rect: Scene canvas rectangle (in cm)
            printable_w_mm: Printable width in mm
            content_h_mm: Printable height for content (excluding legend) in mm
            legend_h_mm: Height reserved for legend in mm
        """
        resolution = printer.resolution()  # DPI
        canvas_w = canvas_rect.width()  # cm
        canvas_h = canvas_rect.height()  # cm

        # At scale 1:denom, 1 mm on paper = denom/10 cm in real world
        # So canvas_w cm requires canvas_w * 10 / denom mm on paper
        paper_w_mm = canvas_w * 10.0 / self._scale_denom
        paper_h_mm = canvas_h * 10.0 / self._scale_denom

        # Calculate how many pages we need
        cols = max(1, math.ceil(paper_w_mm / printable_w_mm))
        rows = max(1, math.ceil(paper_h_mm / content_h_mm))

        # Real-world cm covered per page tile
        tile_w_cm = printable_w_mm * self._scale_denom / 10.0
        tile_h_cm = content_h_mm * self._scale_denom / 10.0

        # Convert printable area to pixels
        content_w_px = printable_w_mm / 25.4 * resolution
        content_h_px = content_h_mm / 25.4 * resolution

        first_page = True
        # Iterate rows bottom-to-top in scene coords so that the output
        # matches the Y-flipped view the user sees (CAD convention: Y-up).
        for row in range(rows):
            # Map to scene row: the user's top row corresponds to the
            # bottom of the scene (highest Y values).
            scene_row = rows - 1 - row
            for col in range(cols):
                if not first_page:
                    printer.newPage()
                first_page = False

                # Source rect in scene coordinates (cm)
                src_x = canvas_rect.x() + col * tile_w_cm
                src_y = canvas_rect.y() + scene_row * tile_h_cm
                src_w = min(tile_w_cm, canvas_w - col * tile_w_cm)
                src_h = min(tile_h_cm, canvas_h - scene_row * tile_h_cm)
                source_rect = QRectF(src_x, src_y, src_w, src_h)

                # Target rect in printer pixels (proportional to source)
                tgt_w = src_w / tile_w_cm * content_w_px
                tgt_h = src_h / tile_h_cm * content_h_px
                target_rect = QRectF(0, 0, tgt_w, tgt_h)

                # Render this tile with Y-flip to match screen view
                painter.save()
                painter.translate(0, tgt_h)
                painter.scale(1, -1)
                self._scene.render(painter, target_rect, source_rect)
                painter.restore()

                # Draw legend on each page (outside the flip)
                if legend_h_mm > 0:
                    page_label = ""
                    if cols * rows > 1:
                        page_label = f" (Page {row * cols + col + 1}/{cols * rows})"
                    self._draw_legend(
                        painter, printer, printable_w_mm, content_h_mm,
                        legend_h_mm, self._scale_denom, page_label,
                    )

    def _draw_legend(
        self,
        painter: QPainter,
        printer: QPrinter,
        printable_w_mm: float,
        content_h_mm: float,
        legend_h_mm: float,
        scale_denom: int,
        extra_text: str = "",
    ) -> None:
        """Draw a legend bar at the bottom of the page.

        Args:
            painter: Active QPainter on the printer
            printer: The QPrinter device
            printable_w_mm: Printable width in mm
            content_h_mm: Content height in mm (legend is drawn below this)
            legend_h_mm: Legend height in mm
            scale_denom: Scale denominator for display
            extra_text: Additional text to append (e.g., page number)
        """
        resolution = printer.resolution()

        # Convert mm to pixels
        legend_y_px = content_h_mm / 25.4 * resolution
        legend_h_px = legend_h_mm / 25.4 * resolution
        legend_w_px = printable_w_mm / 25.4 * resolution

        # Draw separator line
        painter.save()
        pen = QPen(QColor(100, 100, 100))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawLine(
            0, int(legend_y_px),
            int(legend_w_px), int(legend_y_px),
        )

        # Draw legend text - use setPixelSize since legend_h_px is in device pixels
        font = QFont("Segoe UI")
        font.setStyleHint(QFont.StyleHint.SansSerif)
        font.setPixelSize(max(8, int(legend_h_px * 0.55)))
        painter.setFont(font)
        painter.setPen(QColor(60, 60, 60))

        text_y = legend_y_px + legend_h_px * 0.7

        # Left: project name
        painter.drawText(
            4, int(text_y),
            self._project_name,
        )

        # Center: scale
        scale_text = f"1:{scale_denom}" if scale_denom > 0 else "Fit to Page"
        scale_text += extra_text
        fm = painter.fontMetrics()
        scale_w = fm.horizontalAdvance(scale_text)
        painter.drawText(
            int((legend_w_px - scale_w) / 2), int(text_y),
            scale_text,
        )

        # Right: date
        date_text = date.today().strftime("%Y-%m-%d")
        date_w = fm.horizontalAdvance(date_text)
        painter.drawText(
            int(legend_w_px - date_w - 4), int(text_y),
            date_text,
        )

        painter.restore()
