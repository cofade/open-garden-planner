"""Export service for exporting garden plans to various formats."""

import csv
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsTextItem


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
            item.setVisible(True)  # type: ignore[union-attr]

    @staticmethod
    def _prepare_text_for_export(scene: QGraphicsScene, scale: float, dpi: int) -> list[tuple[object, bool, QFont | None]]:
        """Prepare text items for export by adjusting fonts.

        Args:
            scene: The QGraphicsScene containing text items
            scale: Scale factor (output_width / canvas_width)
            dpi: Output DPI (used to scale font size proportionally)

        Returns:
            List of (item, had_ignore_transform_flag, original_font) for restoration
        """
        saved_state = []

        # Calculate appropriate font size for export
        # We want text to be readable but not dominant
        # For a 1:100 scale, 10pt looks good. Scale accordingly.
        reference_scale = 0.01  # 1:100
        reference_font_size = 10

        # Adjust font size based on scale - smaller scale (more zoomed out) needs slightly larger fonts
        # Use square root to moderate the scaling effect
        import math
        scale_ratio = scale / reference_scale
        base_font_size = reference_font_size * math.sqrt(scale_ratio)
        base_font_size = max(6, min(14, base_font_size))  # Clamp between 6pt and 14pt

        # Scale font size proportionally with DPI to maintain same physical size
        # At 150 DPI (reference), use base size. At 300 DPI, double it. At 72 DPI, scale down.
        reference_dpi = 150
        target_font_size = int(base_font_size * (dpi / reference_dpi))
        target_font_size = max(4, target_font_size)  # Minimum 4pt

        # Keep the ItemIgnoresTransformations flag ON - this makes text render
        # at a fixed point size in the output image, not scaled with scene

        for item in scene.items():
            if isinstance(item, (QGraphicsSimpleTextItem, QGraphicsTextItem)):
                # Save original state
                had_flag = bool(item.flags() & item.GraphicsItemFlag.ItemIgnoresTransformations)
                original_font = item.font()
                saved_state.append((item, had_flag, QFont(original_font)))

                # Set font to calculated size for output
                new_font = QFont(original_font)
                new_font.setPointSize(target_font_size)
                item.setFont(new_font)

        return saved_state

    @staticmethod
    def _restore_text_after_export(saved_state: list[tuple[object, bool, QFont | None]]) -> None:
        """Restore text items to their original state after export.

        Args:
            saved_state: List returned from _prepare_text_for_export
        """
        for item, had_flag, original_font in saved_state:
            # Restore original font
            if original_font is not None:
                item.setFont(original_font)

            # Restore ignore transformations flag
            if had_flag:
                item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations, True)

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

        # Prepare text items for export
        saved_text_state = ExportService._prepare_text_for_export(scene, scale, dpi)
        hidden_construction = ExportService._hide_construction_items(scene)

        try:
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
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            # Pre-flip Y so scene Y=0 (visual bottom in OGP's Y-up view) maps to
            # image bottom. translate(0, H) then scale(1,-1) maps scene y → H - y·scale.
            painter.save()
            painter.translate(0, height_px)
            painter.scale(1.0, -1.0)
            scene.render(painter, QRectF(0, 0, width_px, height_px), canvas_rect)
            painter.restore()

            painter.end()

            # Save the image
            if not image.save(str(file_path), "PNG"):
                raise ValueError(f"Failed to save PNG to {file_path}")
        finally:
            # Always restore items to original state
            ExportService._restore_text_after_export(saved_text_state)
            ExportService._restore_construction_items(hidden_construction)

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

        # Calculate scale for text adjustment
        scale = output_width_cm / canvas_width

        # Prepare text items for export
        saved_text_state = ExportService._prepare_text_for_export(scene, scale, svg_dpi)
        hidden_construction = ExportService._hide_construction_items(scene)

        try:
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
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            # Pre-flip Y so scene Y=0 (visual bottom in OGP's Y-up view) maps to
            # output bottom. translate(0, H) then scale(1,-1) maps scene y → H - y·scale.
            painter.save()
            painter.translate(0, height_px)
            painter.scale(1.0, -1.0)
            scene.render(painter, QRectF(0, 0, width_px, height_px), canvas_rect)
            painter.restore()

            painter.end()
        finally:
            # Always restore items to original state
            ExportService._restore_text_after_export(saved_text_state)
            ExportService._restore_construction_items(hidden_construction)

        # Post-process SVG: the Y-flip painter transform causes pattern tile images to
        # appear vertically inverted. Add patternTransform to each <pattern> element to
        # compensate (flip the tile back so it renders correctly in browsers).
        ExportService._fix_svg_pattern_yflip(file_path)
        # Qt's QSvgGenerator does not serialize the painter clip region. Texture-filled
        # shapes are emitted as a large unconstrained <rect> that bleeds across the
        # canvas. Wrap each such group in a <clipPath> derived from the preceding
        # "shadow" group's actual polygon path.
        ExportService._fix_svg_qt_texture_clipping(file_path)

    @staticmethod
    def _fix_svg_pattern_yflip(file_path: Path) -> None:
        """Post-process a Qt-generated SVG to fix pattern tile orientation.

        Qt's Y-flip painter transform causes texture tile images inside <pattern>
        elements to render upside-down in SVG viewers. Adding patternTransform
        with a matching Y-flip compensates so tiles render correctly.
        """
        import re
        text = file_path.read_text(encoding="utf-8")

        def add_pattern_transform(m: re.Match) -> str:
            tag = m.group(0)
            # Extract height attribute to build the flip matrix (flip around y=height/2)
            h_match = re.search(r'height="([^"]+)"', tag)
            h = float(h_match.group(1)) if h_match else 256.0
            # Avoid adding a duplicate patternTransform
            if "patternTransform" in tag:
                return tag
            # Insert patternTransform before the closing >
            return tag.rstrip(">") + f' patternTransform="matrix(1,0,0,-1,0,{h})">'

        text = re.sub(r'<pattern\b[^>]+>', add_pattern_transform, text)
        file_path.write_text(text, encoding="utf-8")

    @staticmethod
    def _fix_svg_qt_texture_clipping(file_path: Path) -> None:
        """Wrap Qt-emitted texture groups in SVG clipPath elements.

        Qt's QSvgGenerator emits each textured QGraphicsItem as a "shadow" group
        (`fill="#000000"` + `<path d="..."/>`) carrying the real polygon outline,
        followed (after Qt's empty bookkeeping groups) by a texture group
        (`fill="url(#...)"` + a large `<rect>`). The painter's clip region — which
        constrains the rect to the polygon shape during native rendering — is *not*
        serialized. The result in SVG viewers is a large rect that bleeds across
        the canvas.

        The fix: pair non-empty shadow groups with the next non-empty texture
        group in document order, build a `<clipPath>` from the shadow's path
        (with its transform) and wrap the texture group with `clip-path=...`.
        """
        import re

        text = file_path.read_text(encoding="utf-8")

        # Items smaller than this are not worth clipping (e.g. text glyphs).
        LARGE_THRESHOLD = 400.0  # cm

        shadow_re = re.compile(
            r'<g\b(?P<attrs>[^>]*)\bfill="#000000"[^>]*>\s*'
            r'(?P<path><path\b[^/]*/?>)\s*</g>',
            re.DOTALL,
        )
        texture_re = re.compile(
            r'<g\b(?P<tattrs>[^>]*)\bfill="url\(#[^)]+\)"[^>]*>\s*'
            r'(?P<rect><rect\b[^/]*/>)\s*</g>',
            re.DOTALL,
        )

        # Collect ALL shadow groups (sorted by position) and all texture groups
        # (sorted by position). Walk both in lockstep so each texture is matched
        # to exactly one shadow.
        shadows = list(shadow_re.finditer(text))
        textures = list(texture_re.finditer(text))

        clip_defs: list[str] = []
        replacements: list[tuple[int, int, str]] = []
        cp_id = 0

        used_textures: set[int] = set()

        for shadow_m in shadows:
            d_m = re.search(r'\bd="([^"]+)"', shadow_m.group("path"))
            if not d_m:
                continue
            path_d = d_m.group(1)
            tr_m = re.search(r'\btransform="([^"]+)"', shadow_m.group("attrs"))
            transform = tr_m.group(1) if tr_m else None

            # First unused texture starting after this shadow ends.
            tex_m = None
            for idx, t in enumerate(textures):
                if idx in used_textures:
                    continue
                if t.start() < shadow_m.end():
                    continue
                tex_m = t
                tex_idx = idx
                break
            if tex_m is None:
                continue

            rect_attrs = tex_m.group("rect")
            w_m = re.search(r'\bwidth="([0-9.+\-eE]+)"', rect_attrs)
            x_m = re.search(r'\bx="([0-9.+\-eE]+)"', rect_attrs)
            y_m = re.search(r'\by="([0-9.+\-eE]+)"', rect_attrs)
            if not (w_m and x_m and y_m):
                continue

            rect_w = float(w_m.group(1))
            rect_x = float(x_m.group(1))
            rect_y = float(y_m.group(1))

            # Skip without consuming: small rects (already shape-bounded) and
            # the canvas background rect (origin at 0,0 — that rect IS the
            # canvas, no clipping wanted). Leaving the index unconsumed means
            # the next shadow re-evaluates it; the position check
            # (t.start() < shadow.end()) filters it out naturally and any
            # genuinely later texture group remains available.
            if rect_w < LARGE_THRESHOLD:
                continue
            if abs(rect_x) < 1.0 and abs(rect_y) < 1.0:
                continue

            used_textures.add(tex_idx)
            cp_id += 1
            cp_name = f"ogp_clip_{cp_id}"

            if transform:
                clip_defs.append(
                    f'<clipPath id="{cp_name}" clipPathUnits="userSpaceOnUse">'
                    f'<g transform="{transform}">'
                    f'<path fill-rule="evenodd" d="{path_d}"/>'
                    f'</g></clipPath>'
                )
            else:
                clip_defs.append(
                    f'<clipPath id="{cp_name}" clipPathUnits="userSpaceOnUse">'
                    f'<path fill-rule="evenodd" d="{path_d}"/>'
                    f'</clipPath>'
                )

            abs_start = tex_m.start()
            abs_end = tex_m.end()
            full_texture_group = text[abs_start:abs_end]
            replacements.append(
                (abs_start, abs_end,
                 f'<g clip-path="url(#{cp_name})">{full_texture_group}</g>')
            )

        # Apply replacements back-to-front so earlier offsets stay valid.
        for start, end, rep in sorted(replacements, key=lambda r: -r[0]):
            text = text[:start] + rep + text[end:]

        if clip_defs:
            defs_close = text.find("</defs>")
            if defs_close >= 0:
                text = text[:defs_close] + "\n" + "\n".join(clip_defs) + "\n" + text[defs_close:]
            else:
                svg_open = re.search(r'<svg\b[^>]*>', text)
                if svg_open is not None:
                    insert_at = svg_open.end()
                    defs_block = "\n<defs>\n" + "\n".join(clip_defs) + "\n</defs>\n"
                    text = text[:insert_at] + defs_block + text[insert_at:]

        file_path.write_text(text, encoding="utf-8")

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
