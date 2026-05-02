"""Validation script — load .ogp file, export PNG/SVG/PDF, render PDF pages to images."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src))

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.pdf_report_service import PdfReportOptions, PdfReportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

OGP_FILE = Path(r"C:\Users\wienh\Downloads\Unser Garten_2026.ogp")
OUT = Path(r"C:\Users\wienh\Downloads\validate_exports")
OUT.mkdir(exist_ok=True)

# Load
scene = CanvasScene()
pm = ProjectManager()
pm.load(scene, OGP_FILE)
canvas_rect = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()
print(f"[LOAD] canvas_rect: {canvas_rect}")
print(f"[LOAD] total items: {len(scene.items())}")

# --- Debug plant items ---
plant_types = (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL)
plant_items = [
    i for i in scene.items()
    if hasattr(i, "object_type") and getattr(i, "object_type", None) in plant_types
]
print(f"[PLANTS] count: {len(plant_items)}")
for it in plant_items[:5]:
    center = it.mapToScene(it.boundingRect().center())
    print(f"  type={type(it).__name__}  center=({center.x():.0f}, {center.y():.0f})  name={getattr(it,'name','?')}")

# --- PNG export ---
png_path = OUT / "overview.png"
ExportService.export_to_png(scene, png_path, dpi=150, output_width_cm=30.0)
print(f"[PNG] written: {png_path}  ({png_path.stat().st_size} bytes)")

# --- SVG export ---
svg_path = OUT / "overview.svg"
ExportService.export_to_svg(scene, svg_path)
print(f"[SVG] written: {svg_path}  ({svg_path.stat().st_size} bytes)")

# --- PDF export ---
pdf_path = OUT / "report.pdf"
opts = PdfReportOptions(
    paper_size="A4",
    orientation="landscape",
    include_cover=True,
    include_overview=True,
    include_bed_details=False,
    include_plant_list=True,
    include_legend=True,
    project_name="Unser Garten 2026",
    author="Test",
)
PdfReportService.generate(scene, opts, pdf_path)
print(f"[PDF] written: {pdf_path}  ({pdf_path.stat().st_size} bytes)")

# --- Render PDF pages to PNG ---
try:
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtCore import QSize

    doc = QPdfDocument(None)
    doc.load(str(pdf_path))
    print(f"[PDF] pages: {doc.pageCount()}")
    for pg in range(doc.pageCount()):
        size = doc.pagePointSize(pg).toSize()
        render_size = QSize(size.width() * 2, size.height() * 2)
        img = doc.render(pg, render_size)
        img_path = OUT / f"pdf_page_{pg+1}.png"
        img.save(str(img_path))
        print(f"[PDF] page {pg+1} -> {img_path}  ({img_path.stat().st_size} bytes)")
except Exception as e:
    print(f"[PDF] page render failed: {e}")

print(f"\n=== Done. Outputs in {OUT} ===")
