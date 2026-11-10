"""Export service for exporting garden plans to various formats."""

import csv
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QCoreApplication, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
)


class _PaintedDiagnostics:
    """A scene's painted diagnostic decorations, as one entry of the hidden-overlay list.

    ``ExportService._hide_overlay_items`` hides overlay ITEMS one by one and
    returns them; ``_restore_overlay_items`` shows each entry again. A spacing
    ring or a soil border is painted by its garden item, so there is nothing to
    hide per item: the scene switches them off together. This entry stands for
    that switch, so showing it again switches the decorations back on and no
    caller of the pair has to know about them (#786, §8.9.15).
    """

    def __init__(self, scene: QGraphicsScene) -> None:
        self._scene = scene

    def setVisible(self, visible: bool) -> None:
        self._scene.set_diagnostic_overlays_visible(visible)


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
    def _hide_construction_items(scene: QGraphicsScene) -> list[object]:
        """Hide all construction geometry items before export.

        Returns:
            List of items that were hidden (to restore later).
        """
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        hidden: list[object] = []
        for item in scene.items():
            if isinstance(item, (ConstructionLineItem, ConstructionCircleItem)) and item.isVisible():
                item.setVisible(False)
                hidden.append(item)
        return hidden

    @staticmethod
    def _restore_construction_items(hidden_items: list[object]) -> None:
        """Restore visibility of construction items after export."""
        for item in hidden_items:
            item.setVisible(True)

    @staticmethod
    def _hide_overlay_items(scene: QGraphicsScene) -> tuple[list[object], list[object]]:
        """Hide selection-handle classes + soil reminder badges before export (US-12.10/F7).

        Selection / resize / rotation / vertex handles and the seasonal soil
        badge are scene-attached items, so ``scene.render()`` would paint them
        into PNG / SVG / PDF exports. Hide them temporarily and clear the
        current selection so any selection-rectangle drawn by items themselves
        also disappears.

        Returns:
            (hidden_items, previously_selected_items) — the second list is so
            the selection state can be restored after the render.
        """
        from open_garden_planner.ui.canvas.items.garden_item import (
            GuildBadgeItem,
            LockBadgeItem,
            SunBadgeItem,
        )
        from open_garden_planner.ui.canvas.items.resize_handle import (
            MidpointHandle,
            RectCornerHandle,
            ResizeHandle,
            RotationHandle,
            VertexHandle,
        )
        from open_garden_planner.ui.canvas.items.soil_badge_item import (
            SoilBadgeItem,
        )

        handle_types = (
            ResizeHandle,
            RotationHandle,
            MidpointHandle,
            RectCornerHandle,
            VertexHandle,
            SoilBadgeItem,
            LockBadgeItem,
            SunBadgeItem,
            GuildBadgeItem,
        )
        hidden: list[object] = []
        for item in scene.items():
            if isinstance(item, handle_types) and item.isVisible():
                item.setVisible(False)
                hidden.append(item)

        # The diagnostic decorations a garden item paints itself (spacing ring,
        # companion ring, antagonist / capacity badge, soil and rotation border)
        # are no scene items: the scene switches them off as one (#786).
        if getattr(scene, "diagnostic_overlays_visible", False):
            scene.set_diagnostic_overlays_visible(False)
            hidden.append(_PaintedDiagnostics(scene))

        previously_selected = list(scene.selectedItems())
        scene.clearSelection()
        return hidden, previously_selected

    @staticmethod
    def _restore_overlay_items(
        hidden_items: list[object], previously_selected: list[object]
    ) -> None:
        """Restore visibility of selection handles + soil badges, and the prior selection."""
        for item in hidden_items:
            item.setVisible(True)
        for item in previously_selected:
            item.setSelected(True)
            if hasattr(item, "setCacheMode"):
                item.setCacheMode(QGraphicsItem.CacheMode.NoCache)

    @staticmethod
    def _disable_item_caches(
        scene: QGraphicsScene,
    ) -> list[tuple[QGraphicsItem, QGraphicsItem.CacheMode]]:
        """Temporarily disable item caching before scene export.

        Ensures full vector fidelity and avoids device-coordinate cache
        pixmap scaling artifacts during scene.render().
        """
        cached: list[tuple[QGraphicsItem, QGraphicsItem.CacheMode]] = []
        for item in scene.items():
            mode = item.cacheMode()
            if mode != QGraphicsItem.CacheMode.NoCache:
                cached.append((item, mode))
                item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        return cached

    @staticmethod
    def _restore_item_caches(
        cached_items: list[tuple[QGraphicsItem, QGraphicsItem.CacheMode]],
    ) -> None:
        """Restore item caching modes after scene export.

        Items currently selected remain NoCache to prevent handle ghosting
        and transformation lag.
        """
        for item, mode in cached_items:
            if item.isSelected():
                item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
            else:
                item.setCacheMode(mode)

    @staticmethod
    def _prepare_text_for_export(
        scene: QGraphicsScene, scale: float, dpi: float
    ) -> list[tuple[Any, QFont]]:
        """Give the constant-pixel-size text of *scene* its size for an export.

        A label with ``ItemIgnoresTransformations`` is drawn in device pixels:
        outside a view nothing scales it, so its point size is chosen for the
        output (``compute_export_font_size``). A text note is sized in plan
        centimetres and is not touched (#789).

        Args:
            scene: The QGraphicsScene containing text items
            scale: Scale factor (output_width / canvas_width)
            dpi: Output DPI (the font size is proportional to it)

        Returns:
            The saved fonts, for ``_restore_text_after_export``
        """
        from open_garden_planner.services.scene_rendering import (
            compute_export_font_size,
            retarget_constant_size_text,
        )

        return list(
            retarget_constant_size_text(scene, compute_export_font_size(scale, dpi))
        )

    @staticmethod
    def _restore_text_after_export(saved_state: list[tuple[Any, QFont]]) -> None:
        """Restore text items to their original state after export.

        Args:
            saved_state: List returned from _prepare_text_for_export
        """
        from open_garden_planner.services.scene_rendering import restore_text_fonts

        restore_text_fonts(saved_state)

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

        # Calculate scale for text adjustment
        scale = output_width_cm / canvas_width

        from open_garden_planner.services.scene_rendering import (
            compute_export_font_size,
            render_scene_region,
        )

        text_point_size = compute_export_font_size(scale, dpi)

        # Create image with the calculated dimensions
        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)

        # Fill with background color
        if background_color:
            image.fill(QColor(background_color))
        elif hasattr(scene, 'CANVAS_COLOR'):
            image.fill(scene.CANVAS_COLOR)
        else:
            image.fill(Qt.GlobalColor.white)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        try:
            # Single helper call owns ALL bookkeeping: overlay hide,
            # construction hide, text scaling, Y-flip, and scene render.
            # No legacy `_hide_*` / `_prepare_text_*` calls — this is the
            # deduplication promised by ADR-023.
            render_scene_region(
                scene=scene,
                painter=painter,
                target_rect=QRectF(0, 0, width_px, height_px),
                source_rect=canvas_rect,
                hide_overlays=True,
                hide_construction=True,
                text_point_size=text_point_size,
                y_flip=True,
            )
        finally:
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

        from open_garden_planner.services.svg_export import (
            SVG_UNITS_PER_INCH,
            record_scene,
            write_svg,
        )

        # The drawing is laid out in print-resolution units: what a 300-dpi PNG
        # of the same width paints, as vectors.
        width = output_width_cm / 2.54 * SVG_UNITS_PER_INCH
        height = output_height_cm / 2.54 * SVG_UNITS_PER_INCH

        # Calculate scale for text adjustment
        scale = output_width_cm / canvas_width

        # The scene is painted into a recording engine and replayed into the
        # QSvgGenerator, which on its own drops clips and brush transforms
        # (services/svg_export.py, #787). It is a vector device, so it cannot
        # delegate to render_scene_region (ADR-023).
        saved_text_state = ExportService._prepare_text_for_export(
            scene, scale, SVG_UNITS_PER_INCH
        )
        hidden_construction = ExportService._hide_construction_items(scene)
        hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
        cached_items = ExportService._disable_item_caches(scene)

        try:
            ops = record_scene(scene, canvas_rect, width, height)
        finally:
            # Always restore items to original state
            ExportService._restore_text_after_export(saved_text_state)
            ExportService._restore_construction_items(hidden_construction)
            ExportService._restore_overlay_items(hidden_overlay, prior_selection)
            ExportService._restore_item_caches(cached_items)

        write_svg(ops, file_path, width, height, title=title, description=description)

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
    def export_plant_list_to_csv(
        scene: QGraphicsScene,
        file_path: Path | str,
        include_species_data: bool = True,
    ) -> int:
        """Export all plants in the scene to a CSV file.

        Args:
            scene: The QGraphicsScene containing plant items
            file_path: Path to save the CSV file
            include_species_data: Whether to include species-level botanical data

        Returns:
            Number of plants exported

        Raises:
            ValueError: If export fails
        """
        file_path = Path(file_path)

        # Import here to avoid circular dependency
        from open_garden_planner.core.object_types import ObjectType

        # Collect all plant items from the scene
        plant_items = []
        for item in scene.items():
            if not hasattr(item, "object_type") or not hasattr(item, "metadata"):
                continue

            # Check if this is a plant type
            obj_type = item.object_type
            if obj_type not in (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL):
                continue

            plant_items.append(item)

        if not plant_items:
            # Create empty file with header if no plants
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(ExportService._get_csv_headers(include_species_data))
            return 0

        # Extract data from plant items
        rows = []
        for item in plant_items:
            row_data = ExportService._extract_plant_data(item, include_species_data)
            rows.append(row_data)

        # Write to CSV
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=ExportService._get_csv_headers(include_species_data),
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            raise ValueError(f"Failed to write CSV to {file_path}: {e}") from e

        return len(plant_items)

    @staticmethod
    def _get_csv_headers(include_species_data: bool) -> list[str]:
        """Get CSV column headers.

        Args:
            include_species_data: Whether to include species-level columns

        Returns:
            List of column names
        """
        # Instance-level columns (always included)
        headers = [
            "name",
            "type",
            "variety_cultivar",
            "planting_date",
            "current_spread_cm",
            "current_height_cm",
            "position_x_cm",
            "position_y_cm",
            "notes",
        ]

        # Species-level columns (optional)
        if include_species_data:
            headers.extend([
                "scientific_name",
                "common_name",
                "family",
                "cycle",
                "flower_type",
                "pollination_type",
                "max_height_cm",
                "max_spread_cm",
                "sun_requirement",
                "water_needs",
                "hardiness_zone_min",
                "hardiness_zone_max",
                "edible",
                "edible_parts",
                "data_source",
            ])

        return headers

    @staticmethod
    def _extract_plant_data(item: Any, include_species_data: bool) -> dict[str, Any]:
        """Extract plant data from a graphics item.

        Args:
            item: The QGraphicsItem with plant metadata
            include_species_data: Whether to include species-level data

        Returns:
            Dictionary of plant data for CSV row
        """
        data: dict[str, Any] = {}

        # Get item name and type
        data["name"] = getattr(item, "name", "")
        obj_type = getattr(item, "object_type", None)
        if obj_type:
            from open_garden_planner.core.object_types import get_style
            style = get_style(obj_type)
            data["type"] = style.display_name
        else:
            data["type"] = ""

        # Get position
        pos = item.pos()
        data["position_x_cm"] = round(pos.x(), 2)
        data["position_y_cm"] = round(pos.y(), 2)

        # Extract plant instance data
        metadata = getattr(item, "metadata", {})
        plant_instance = metadata.get("plant_instance", {})

        data["variety_cultivar"] = plant_instance.get("variety_cultivar", "")
        data["planting_date"] = plant_instance.get("planting_date", "")
        data["current_spread_cm"] = plant_instance.get("current_spread_cm") or plant_instance.get("current_diameter_cm", "")
        data["current_height_cm"] = plant_instance.get("current_height_cm", "")
        data["notes"] = plant_instance.get("notes", "")

        # Extract plant species data if requested
        if include_species_data:
            plant_species = metadata.get("plant_species", {})

            data["scientific_name"] = plant_species.get("scientific_name", "")
            data["common_name"] = plant_species.get("common_name", "")
            data["family"] = plant_species.get("family", "")
            data["cycle"] = plant_species.get("cycle", "")
            data["flower_type"] = plant_species.get("flower_type", "")
            data["pollination_type"] = plant_species.get("pollination_type", "")
            data["max_height_cm"] = plant_species.get("max_height_cm", "")
            data["max_spread_cm"] = plant_species.get("max_spread_cm", "")
            data["sun_requirement"] = plant_species.get("sun_requirement", "")
            data["water_needs"] = plant_species.get("water_needs", "")
            data["hardiness_zone_min"] = plant_species.get("hardiness_zone_min", "")
            data["hardiness_zone_max"] = plant_species.get("hardiness_zone_max", "")
            data["edible"] = plant_species.get("edible", "")
            edible_parts = plant_species.get("edible_parts", [])
            data["edible_parts"] = ", ".join(edible_parts) if edible_parts else ""
            data["data_source"] = plant_species.get("data_source", "")

        return data

    @staticmethod
    def export_shopping_list_to_csv(
        items: list[Any],
        file_path: Path | str,
    ) -> int:
        """Export a shopping list (US-12.6) to CSV.

        Args:
            items: List of ``ShoppingListItem`` instances.
            file_path: Path to save the CSV file.

        Returns:
            Number of rows written (excluding header).

        Raises:
            ValueError: If writing fails.
        """
        file_path = Path(file_path)
        headers = [
            "category",
            "name",
            "quantity",
            "unit",
            "size",
            "price_each",
            "total_cost",
            "notes",
        ]
        try:
            # utf-8-sig writes a BOM so Excel on Windows recognises the file as
            # UTF-8 instead of Latin-1; otherwise German Umlauts arrive mojibake'd.
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                for item in items:
                    writer.writerow(item.to_export_row())
        except Exception as e:
            raise ValueError(f"Failed to write shopping list CSV to {file_path}: {e}") from e
        return len(items)

    @staticmethod
    def export_harvest_to_csv(
        harvest_logs: dict[str, Any],
        file_path: Path | str,
    ) -> int:
        """Export garden-wide harvest totals (US-C1) to CSV.

        Aggregates ``harvest_logs`` into per-species, per-year, per-unit totals
        (via :mod:`services.harvest_aggregation`) and writes one row per total.

        Args:
            harvest_logs: ``ProjectManager.harvest_logs``.
            file_path: Path to save the CSV file.

        Returns:
            Number of rows written (excluding header).

        Raises:
            ValueError: If writing fails.
        """
        from open_garden_planner.services.harvest_aggregation import (
            HARVEST_CSV_HEADERS,
            aggregate_by_species_year,
            harvest_csv_rows,
        )

        file_path = Path(file_path)
        rows = harvest_csv_rows(aggregate_by_species_year(harvest_logs))
        # Keep the CSV consistent with the dashboard table + PDF summary: an
        # unnamed, species-less target has a blank name — show the same
        # localized "Unnamed" label rather than an empty cell.
        unnamed = QCoreApplication.translate("HarvestView", "Unnamed")
        for row in rows:
            if not row.get("species"):
                row["species"] = unnamed
        try:
            # utf-8-sig writes a BOM so Excel on Windows recognises the file as
            # UTF-8 instead of Latin-1; otherwise German Umlauts arrive mojibake'd.
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f, fieldnames=HARVEST_CSV_HEADERS, extrasaction="ignore"
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        except Exception as e:
            raise ValueError(f"Failed to write harvest CSV to {file_path}: {e}") from e
        return len(rows)
