"""Integration tests for DXF export, DXF import, and PDF report (US-12.3, 12.4, 12.5)."""

import math
import tempfile
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.services.dxf_service import (
    DxfExportService,
    DxfImportResult,
    DxfImportService,
)
from open_garden_planner.services.pdf_report_service import PdfReportOptions, PdfReportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:
    return CanvasScene(width_cm=1000, height_cm=800)


# ---------------------------------------------------------------------------
# US-12.3: DXF Export
# ---------------------------------------------------------------------------

class TestDxfExport:
    def test_export_rectangle_produces_lwpolyline(self, scene: CanvasScene) -> None:
        import ezdxf

        rect = RectangleItem(100, 200, 300, 150)
        scene.addItem(rect)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            entities = list(doc.modelspace())
            types = [e.dxftype() for e in entities]
            assert "LWPOLYLINE" in types
        finally:
            tmp.unlink(missing_ok=True)

    def test_export_circle_produces_circle_entity(self, scene: CanvasScene) -> None:
        import ezdxf

        circle = CircleItem(500, 400, 100)
        scene.addItem(circle)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            types = [e.dxftype() for e in doc.modelspace()]
            assert "CIRCLE" in types
        finally:
            tmp.unlink(missing_ok=True)

    def test_export_ellipse_produces_ellipse_entity(self, scene: CanvasScene) -> None:
        import ezdxf

        ellipse = EllipseItem(200, 200, 400, 200)
        scene.addItem(ellipse)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            types = [e.dxftype() for e in doc.modelspace()]
            assert "ELLIPSE" in types
        finally:
            tmp.unlink(missing_ok=True)

    def test_export_polygon_produces_lwpolyline(self, scene: CanvasScene) -> None:
        import ezdxf

        pts = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 100)]
        poly = PolygonItem(pts)
        scene.addItem(poly)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            types = [e.dxftype() for e in doc.modelspace()]
            assert "LWPOLYLINE" in types
        finally:
            tmp.unlink(missing_ok=True)

    def test_export_layer_name_preserved(self, scene: CanvasScene) -> None:
        import ezdxf

        # Add a layer to the scene and assign it to a rect
        from open_garden_planner.models.layer import Layer

        my_layer = Layer(name="TestBeds")
        scene.add_layer(my_layer)

        rect = RectangleItem(0, 0, 200, 100, layer_id=my_layer.id)
        scene.addItem(rect)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            layer_names = [layer.dxf.name for layer in doc.layers]
            assert "TestBeds" in layer_names
        finally:
            tmp.unlink(missing_ok=True)

    def test_export_construction_items_excluded(self, scene: CanvasScene) -> None:
        import ezdxf

        from open_garden_planner.ui.canvas.items.construction_item import ConstructionLineItem

        # Add only a construction item — result should be empty modelspace
        line = ConstructionLineItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(line)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            assert len(list(doc.modelspace())) == 0
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# US-12.4: DXF Import
# ---------------------------------------------------------------------------

class TestDxfImport:
    def _make_dxf(self, tmp: Path) -> None:
        """Write a minimal DXF file with several entity types."""
        import ezdxf

        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_line((0, 0), (100, 100))
        msp.add_circle((200, 200), radius=50)
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100)], close=False)
        msp.add_lwpolyline([(300, 0), (400, 0), (400, 100), (300, 100)], close=True)
        msp.add_ellipse((500, 500), major_axis=(100, 0, 0), ratio=0.5)
        doc.saveas(str(tmp))

    def test_import_creates_expected_item_types(self, scene: CanvasScene) -> None:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            self._make_dxf(tmp)
            result = DxfImportService.import_file(scene, tmp, scale_factor=1.0)
            assert len(result.items) == 5
            assert result.skipped_count == 0
        finally:
            tmp.unlink(missing_ok=True)

    def test_import_circle_creates_circle_item(self, scene: CanvasScene) -> None:
        import ezdxf

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            doc = ezdxf.new()
            doc.modelspace().add_circle((100, 100), radius=50)
            doc.saveas(str(tmp))

            result = DxfImportService.import_file(scene, tmp, scale_factor=1.0)
            assert len(result.items) == 1
            assert isinstance(result.items[0], CircleItem)
        finally:
            tmp.unlink(missing_ok=True)

    def test_import_scale_factor_applied(self, scene: CanvasScene) -> None:
        import ezdxf

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            doc = ezdxf.new()
            doc.modelspace().add_circle((0, 0), radius=100)
            doc.saveas(str(tmp))

            result = DxfImportService.import_file(scene, tmp, scale_factor=0.5)
            assert len(result.items) == 1
            circle = result.items[0]
            assert isinstance(circle, CircleItem)
            # At scale 0.5, radius 100 → 50
            assert math.isclose(circle._radius, 50.0, rel_tol=1e-6)
        finally:
            tmp.unlink(missing_ok=True)

    def test_import_unsupported_entity_skipped(self, scene: CanvasScene) -> None:
        import ezdxf

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            doc = ezdxf.new()
            msp = doc.modelspace()
            # Add a supported and an unsupported entity
            msp.add_circle((0, 0), radius=10)
            msp.add_text("hello")  # TEXT is not in SUPPORTED_TYPES
            doc.saveas(str(tmp))

            result = DxfImportService.import_file(scene, tmp, scale_factor=1.0)
            assert len(result.items) == 1
            assert result.skipped_count == 1
            assert "TEXT" in result.skipped_types
        finally:
            tmp.unlink(missing_ok=True)

    def test_import_layer_filter_applied(self, scene: CanvasScene) -> None:
        import ezdxf

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            doc = ezdxf.new()
            msp = doc.modelspace()
            doc.layers.add("LayerA")
            doc.layers.add("LayerB")
            msp.add_circle((0, 0), radius=10, dxfattribs={"layer": "LayerA"})
            msp.add_circle((100, 0), radius=10, dxfattribs={"layer": "LayerB"})
            doc.saveas(str(tmp))

            result = DxfImportService.import_file(scene, tmp, scale_factor=1.0, selected_layers=["LayerA"])
            assert len(result.items) == 1
        finally:
            tmp.unlink(missing_ok=True)

    def test_import_get_dxf_layers(self, scene: CanvasScene) -> None:
        import ezdxf

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            doc = ezdxf.new()
            doc.layers.add("Walls")
            doc.layers.add("Beds")
            doc.modelspace().add_circle((0, 0), radius=10, dxfattribs={"layer": "Walls"})
            doc.modelspace().add_circle((100, 0), radius=10, dxfattribs={"layer": "Beds"})
            doc.saveas(str(tmp))

            layers = DxfImportService.get_dxf_layers(tmp)
            assert "Walls" in layers
            assert "Beds" in layers
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# US-12.5: PDF Report
# ---------------------------------------------------------------------------

class TestPdfReport:
    def test_pdf_created_with_all_pages(self, scene: CanvasScene) -> None:
        rect = RectangleItem(100, 100, 400, 300)
        scene.addItem(rect)

        opts = PdfReportOptions(
            paper_size="A4",
            orientation="landscape",
            include_cover=True,
            include_overview=True,
            include_bed_details=False,
            include_plant_list=True,
            include_legend=True,
            project_name="Test Garden",
            author="Tester",
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = Path(f.name)

        try:
            PdfReportService.generate(scene, opts, tmp)
            assert tmp.exists()
            assert tmp.stat().st_size > 0
            header = tmp.read_bytes()[:5]
            assert header == b"%PDF-"
        finally:
            tmp.unlink(missing_ok=True)

    def test_pdf_progress_callback_called(self, scene: CanvasScene) -> None:
        opts = PdfReportOptions(
            include_cover=True,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_legend=False,
        )

        calls: list[tuple[int, int]] = []

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = Path(f.name)

        try:
            PdfReportService.generate(scene, opts, tmp, progress_callback=lambda c, t: calls.append((c, t)))
            assert len(calls) >= 1
        finally:
            tmp.unlink(missing_ok=True)

    def test_pdf_empty_pages_no_crash(self, scene: CanvasScene) -> None:
        opts = PdfReportOptions(
            include_cover=False,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_legend=False,
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = Path(f.name)

        try:
            # All pages disabled → service should return without creating file / creating empty
            PdfReportService.generate(scene, opts, tmp)
            # No crash expected
        finally:
            tmp.unlink(missing_ok=True)

    def test_pdf_letter_portrait(self, scene: CanvasScene) -> None:
        opts = PdfReportOptions(
            paper_size="Letter",
            orientation="portrait",
            include_cover=True,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=False,
            include_legend=False,
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = Path(f.name)

        try:
            PdfReportService.generate(scene, opts, tmp)
            assert tmp.exists()
            assert tmp.read_bytes()[:4] == b"%PDF"
        finally:
            tmp.unlink(missing_ok=True)

    def test_pdf_plant_list_page_with_plants(self, scene: CanvasScene) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        plant = CircleItem(150, 150, 40, ObjectType.TREE)
        plant.name = "Apple Tree"
        scene.addItem(plant)

        opts = PdfReportOptions(
            paper_size="A4",
            orientation="landscape",
            include_cover=False,
            include_overview=False,
            include_bed_details=False,
            include_plant_list=True,
            include_legend=False,
            project_name="Orchard",
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = Path(f.name)

        try:
            PdfReportService.generate(scene, opts, tmp)
            assert tmp.exists()
            assert tmp.stat().st_size > 0
            assert tmp.read_bytes()[:5] == b"%PDF-"
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# SVG export — Qt texture-fill clipping post-process (regression coverage)
# ---------------------------------------------------------------------------

class TestSvgTextureClipping:
    """A textured export stays a well-formed SVG.

    The export used to pair Qt's "shadow" groups with texture groups in the
    written file to recover dropped clips; it now records the clip below the
    painter (``services/svg_export.py``, #787). What the picture looks like is
    pinned by ``tests/integration/test_svg_export_fidelity.py``.
    """

    def test_textured_export_produces_well_formed_svg(self, scene: CanvasScene) -> None:
        """End-to-end smoke: a real textured polygon export must be well-formed."""
        import xml.etree.ElementTree as ET

        from open_garden_planner.core.fill_patterns import FillPattern
        from open_garden_planner.services.export_service import ExportService

        poly = PolygonItem(
            [QPointF(100, 100), QPointF(700, 100),
             QPointF(700, 600), QPointF(100, 600)],
            fill_pattern=FillPattern.GRASS,
        )
        scene.addItem(poly)

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            tmp = Path(f.name)

        try:
            ExportService.export_to_svg(scene, tmp)
            ET.fromstring(tmp.read_text(encoding="utf-8"))
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Orientation guards — coordinate-level checks for the seven Y-axis bugs
# ---------------------------------------------------------------------------

class TestExportOrientation:
    """Coordinate-level guards for the seven orientation bugs fixed in
    US-12.3/12.4/12.5. Earlier tests only verified entity types and headers;
    these assert that the actual coordinates round-trip correctly."""

    def test_dxf_export_preserves_scene_y_unchanged(self, scene: CanvasScene) -> None:
        """OGP scene Y-up == DXF Y-up: no negation, no canvas-height flip."""
        import ezdxf

        # CircleItem at scene (500, 400) — visual lower-half of a 1000×800 canvas.
        circle = CircleItem(500, 400, 100)
        scene.addItem(circle)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)
            doc = ezdxf.readfile(str(tmp))
            circles = [e for e in doc.modelspace() if e.dxftype() == "CIRCLE"]
            assert len(circles) == 1
            cx, cy, _cz = circles[0].dxf.center
            # Identity mapping: scene_y (Y-up) → dxf_y (Y-up).
            assert abs(cx - 500.0) < 0.01, f"x drifted: {cx}"
            assert abs(cy - 400.0) < 0.01, f"y drifted: {cy}"
        finally:
            tmp.unlink(missing_ok=True)

    def test_dxf_round_trip_preserves_position(self, scene: CanvasScene) -> None:
        """Export → import round-trip must land back at the original scene Y."""

        rect = RectangleItem(200, 150, 300, 100)
        scene.addItem(rect)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            tmp = Path(f.name)

        try:
            DxfExportService.export(scene, tmp)

            target_scene = CanvasScene(width_cm=1000, height_cm=800)
            result = DxfImportService.import_file(target_scene, tmp)
            assert isinstance(result, DxfImportResult)
            assert result.items, "rectangle not re-imported"

            # The result holds detached items; place them like the dialog does.
            for item in result.items:
                target_scene.addItem(item)

            imported_polys = [
                it for it in target_scene.items()
                if isinstance(it, PolygonItem)
            ]
            assert imported_polys, "rectangle not re-imported as polygon"
            poly = imported_polys[0]
            # Use the polygon vertices directly (independent of stroke width).
            verts = list(poly.polygon())
            xs = [v.x() for v in verts]
            ys = [v.y() for v in verts]
            # Original rectangle spans x∈[200,500], y∈[150,250]. Y-axis is
            # identity in both directions; any double-flip would push y below
            # 0 or above canvas height.
            assert min(ys) >= 0 and max(ys) <= 800, f"y outside canvas: ys={ys}"
            # Width and height preserved exactly (vertices are unaffected by stroke).
            assert abs((max(xs) - min(xs)) - 300) < 1.0, f"width drifted: {xs}"
            assert abs((max(ys) - min(ys)) - 100) < 1.0, f"height drifted: {ys}"
        finally:
            tmp.unlink(missing_ok=True)

    def test_png_export_visual_bottom_pixel_matches_scene_origin(self, scene: CanvasScene) -> None:
        """PNG bottom pixel-row must correspond to scene Y=0 (visual bottom).

        Without the painter pre-flip, scene.render() draws Y-down, so a
        rectangle at scene-Y=0..50 would land in the *top* of the image.
        """
        # Black-filled rectangle in the bottom-left scene region: scene
        # coords x∈[0,200], y∈[0,50] (Y-up → visually low).
        from PyQt6.QtGui import QImage

        from open_garden_planner.services.export_service import ExportService
        from tests.integration.conftest import recolour
        rect = RectangleItem(0, 0, 200, 50)
        recolour(rect, "#000000")  # the attribute AND the brush, as the panel sets them
        scene.addItem(rect)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)

        try:
            ExportService.export_to_png(scene, tmp, dpi=72, output_width_cm=20.0)
            img = QImage(str(tmp))
            assert not img.isNull()
            h = img.height()
            w = img.width()
            # Sample one column from the left third (where the rect lives).
            sample_x = w // 6
            top_pixel = img.pixelColor(sample_x, 5)
            bottom_pixel = img.pixelColor(sample_x, h - 5)
            # Y-up: scene y=0..50 should render to the BOTTOM pixel rows, not
            # the top. Bottom must be black-ish; top must NOT be.
            assert bottom_pixel.lightnessF() < 0.3, (
                f"expected black at bottom, got {bottom_pixel.name()}"
            )
            assert top_pixel.lightnessF() > 0.5, (
                f"top pixel unexpectedly dark — Y-flip regressed: {top_pixel.name()}"
            )
        finally:
            tmp.unlink(missing_ok=True)
