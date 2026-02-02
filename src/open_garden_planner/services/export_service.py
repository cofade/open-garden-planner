"""Export service for exporting garden plans to various formats."""

from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtWidgets import QGraphicsScene


class ExportService:
    """Service for exporting garden plans to PNG and SVG formats."""

    # Standard DPI options
    DPI_SCREEN = 72
    DPI_PRINT = 150
    DPI_HIGH = 300

    # Common paper widths in cm (landscape orientation)
    PAPER_A4_LANDSCAPE_WIDTH_CM = 29.7
    PAPER_A3_LANDSCAPE_WIDTH_CM = 42.0
    PAPER_LETTER_LANDSCAPE_WIDTH_CM = 27.94

    @staticmethod
    def export_to_png(
        scene: QGraphicsScene,
        file_path: Path | str,
        dpi: int = 150,
        output_width_cm: float = 30.0,
        background_color: str | None = None,
    ) -> None:
        """Export the scene to a PNG image.

        Args:
            scene: The QGraphicsScene to export
            file_path: Path to save the PNG file
            dpi: Dots per inch for the output image (72, 150, or 300)
            output_width_cm: Width of the output image in centimeters (default 30cm ~ A4 landscape)
            background_color: Optional background color hex string (e.g., "#ffffff")
                            If None, uses the scene's canvas background

        Raises:
            ValueError: If export fails
        """
        file_path = Path(file_path)

        # Get canvas dimensions from scene
        canvas_rect = scene.canvas_rect if hasattr(scene, 'canvas_rect') else scene.sceneRect()
        canvas_width = canvas_rect.width()
        canvas_height = canvas_rect.height()

        # Calculate output dimensions maintaining aspect ratio
        aspect_ratio = canvas_height / canvas_width
        output_height_cm = output_width_cm * aspect_ratio

        # Convert output cm to pixels based on DPI
        # 1 inch = 2.54 cm, so pixels = (cm / 2.54) * dpi
        width_px = int((output_width_cm / 2.54) * dpi)
        height_px = int((output_height_cm / 2.54) * dpi)

        # Create image with the calculated dimensions
        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)

        # Fill with background color
        if background_color:
            image.fill(QColor(background_color))
        else:
            # Use scene's canvas color if available
            if hasattr(scene, 'CANVAS_COLOR'):
                image.fill(scene.CANVAS_COLOR)
            else:
                image.fill(Qt.GlobalColor.white)

        # Create painter and render scene
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Render the canvas area scaled to fit the output
        target_rect = QRectF(0, 0, width_px, height_px)
        scene.render(painter, target_rect, canvas_rect)

        painter.end()

        # Save the image
        if not image.save(str(file_path), "PNG"):
            raise ValueError(f"Failed to save PNG to {file_path}")

    @staticmethod
    def export_to_svg(
        scene: QGraphicsScene,
        file_path: Path | str,
        output_width_cm: float = 30.0,
        title: str = "Garden Plan",
        description: str = "",
    ) -> None:
        """Export the scene to an SVG vector file.

        Args:
            scene: The QGraphicsScene to export
            file_path: Path to save the SVG file
            output_width_cm: Width of the output SVG in centimeters (default 30cm ~ A4 landscape)
            title: Title metadata for the SVG
            description: Description metadata for the SVG

        Raises:
            ValueError: If export fails
        """
        file_path = Path(file_path)

        # Get canvas dimensions from scene
        canvas_rect = scene.canvas_rect if hasattr(scene, 'canvas_rect') else scene.sceneRect()
        canvas_width = canvas_rect.width()
        canvas_height = canvas_rect.height()

        # Calculate output dimensions maintaining aspect ratio
        aspect_ratio = canvas_height / canvas_width
        output_height_cm = output_width_cm * aspect_ratio

        # For SVG, use 96 DPI as standard (common screen DPI)
        svg_dpi = 96
        width_px = int((output_width_cm / 2.54) * svg_dpi)
        height_px = int((output_height_cm / 2.54) * svg_dpi)

        # Create SVG generator
        generator = QSvgGenerator()
        generator.setFileName(str(file_path))
        generator.setSize(QSize(width_px, height_px))
        generator.setViewBox(QRectF(0, 0, width_px, height_px))
        generator.setTitle(title)
        generator.setDescription(description)

        # Create painter and render scene
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Render the canvas area scaled to fit the output
        target_rect = QRectF(0, 0, width_px, height_px)
        scene.render(painter, target_rect, canvas_rect)

        painter.end()

    @staticmethod
    def calculate_image_size(
        canvas_width_cm: float,
        canvas_height_cm: float,
        output_width_cm: float,
        dpi: int,
    ) -> tuple[int, int]:
        """Calculate the output image size in pixels.

        Args:
            canvas_width_cm: Canvas width in centimeters (real-world scale)
            canvas_height_cm: Canvas height in centimeters (real-world scale)
            output_width_cm: Desired output width in centimeters
            dpi: Dots per inch

        Returns:
            Tuple of (width_pixels, height_pixels)
        """
        aspect_ratio = canvas_height_cm / canvas_width_cm
        output_height_cm = output_width_cm * aspect_ratio

        width_px = int((output_width_cm / 2.54) * dpi)
        height_px = int((output_height_cm / 2.54) * dpi)
        return width_px, height_px

    @staticmethod
    def calculate_scale(canvas_width_cm: float, output_width_cm: float) -> float:
        """Calculate the export scale ratio.

        Args:
            canvas_width_cm: Canvas width in centimeters (real-world scale)
            output_width_cm: Desired output width in centimeters

        Returns:
            Scale ratio (e.g., 0.01 means 1:100 scale)
        """
        return output_width_cm / canvas_width_cm

    @staticmethod
    def estimate_file_size_mb(width_px: int, height_px: int) -> float:
        """Estimate the PNG file size in megabytes.

        This is a rough estimate based on ARGB32 format with typical
        PNG compression.

        Args:
            width_px: Image width in pixels
            height_px: Image height in pixels

        Returns:
            Estimated file size in megabytes
        """
        # ARGB32 = 4 bytes per pixel, typical PNG compression ~30-50%
        raw_size_bytes = width_px * height_px * 4
        # Assume ~40% compression for garden plans (lots of solid colors)
        compressed_size = raw_size_bytes * 0.4
        return compressed_size / (1024 * 1024)
