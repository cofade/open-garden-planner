"""Validation script — load .ogp file, export PNG/SVG/PDF, render PDF pages to images.

Diagnostic harness (not a required CI merge gate): accepts explicit CLI arguments
for the plan file and output directory, defaulting to a temporary sample plan
and output folder when run without arguments.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OGP_ALLOW_PRODUCTION_SETTINGS", "1")

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def create_sample_plan(target_path: Path) -> Path:
    """Create a minimal valid .ogp plan with basic items for validation."""
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance()
    if _app is None:
        _app = QApplication([sys.argv[0]] if sys.argv else ["validate_exports"])

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

    scene = CanvasScene(width_cm=1000, height_cm=800)

    rect = RectangleItem(100.0, 100.0, 300.0, 150.0)
    rect.object_type = ObjectType.RAISED_BED
    rect.name = "Raised Bed 1"
    scene.addItem(rect)

    circle = CircleItem(200.0, 150.0, 25.0)
    circle.object_type = ObjectType.PERENNIAL
    circle.name = "Lavender"
    scene.addItem(circle)

    pm = ProjectManager()
    pm.save(scene, target_path)
    return target_path


def validate_exports(
    ogp_file: Path,
    out_dir: Path,
    verbose: bool = True,
) -> dict[str, Any]:
    """Load *ogp_file*, export PNG/SVG/PDF into *out_dir*, and optionally render PDF pages.

    Returns a dict with paths and file sizes of the generated outputs.
    """
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance()
    if _app is None:
        _app = QApplication([sys.argv[0]] if sys.argv else ["validate_exports"])

    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.export_service import ExportService
    from open_garden_planner.services.pdf_report_service import (
        PdfReportOptions,
        PdfReportService,
    )
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    out_dir.mkdir(parents=True, exist_ok=True)

    scene = CanvasScene()
    pm = ProjectManager()
    pm.load(scene, ogp_file)

    canvas_rect = getattr(scene, "canvas_rect", scene.sceneRect())
    total_items = len(scene.items())
    if verbose:
        print(f"[LOAD] ogp_file: {ogp_file}")
        print(f"[LOAD] canvas_rect: {canvas_rect}")
        print(f"[LOAD] total QGraphicsItems in scene: {total_items}")

    results: dict[str, Any] = {
        "ogp_file": ogp_file,
        "out_dir": out_dir,
        "canvas_rect": (canvas_rect.x(), canvas_rect.y(), canvas_rect.width(), canvas_rect.height()),
        "total_items": total_items,
        "outputs": {},
    }

    # 1. Export PNG
    png_path = out_dir / "overview.png"
    ExportService.export_to_png(
        scene,
        png_path,
        dpi=150,
    )
    png_size = png_path.stat().st_size if png_path.is_file() else 0
    results["outputs"]["png"] = {"path": png_path, "bytes": png_size}
    if verbose:
        print(f"[PNG] written: {png_path} ({png_size} bytes)")

    # 2. Export SVG
    svg_path = out_dir / "overview.svg"
    ExportService.export_to_svg(
        scene,
        svg_path,
    )
    svg_size = svg_path.stat().st_size if svg_path.is_file() else 0
    results["outputs"]["svg"] = {"path": svg_path, "bytes": svg_size}
    if verbose:
        print(f"[SVG] written: {svg_path} ({svg_size} bytes)")

    # 3. Export PDF Report
    pdf_path = out_dir / "report.pdf"
    pdf_opts = PdfReportOptions(
        include_overview=True,
        include_plant_list=True,
        include_bed_details=True,
    )
    PdfReportService.generate(
        scene,
        pdf_opts,
        pdf_path,
    )
    pdf_size = pdf_path.stat().st_size if pdf_path.is_file() else 0
    results["outputs"]["pdf"] = {"path": pdf_path, "bytes": pdf_size}
    if verbose:
        print(f"[PDF] written: {pdf_path} ({pdf_size} bytes)")

    # 4. Render PDF pages to PNG (if QtPdf available)
    pdf_pages: list[Path] = []
    try:
        from PyQt6.QtCore import QSize
        from PyQt6.QtPdf import QPdfDocument

        doc = QPdfDocument(None)
        doc.load(str(pdf_path))
        page_count = doc.pageCount()
        if verbose:
            print(f"[PDF] pages: {page_count}")
        for pg in range(page_count):
            size = doc.pagePointSize(pg).toSize()
            render_size = QSize(size.width() * 2, size.height() * 2)
            img = doc.render(pg, render_size)
            img_path = out_dir / f"pdf_page_{pg + 1}.png"
            img.save(str(img_path))
            pdf_pages.append(img_path)
            if verbose:
                print(f"[PDF] page {pg + 1} -> {img_path} ({img_path.stat().st_size} bytes)")
    except Exception as exc:
        if verbose:
            print(f"[PDF] page render skipped or failed: {exc}")

    results["outputs"]["pdf_pages"] = pdf_pages
    return results


def main(argv: list[str] | None = None) -> int:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance()
    if _app is None:
        _app = QApplication([sys.argv[0]] if sys.argv else ["validate_exports"])

    parser = argparse.ArgumentParser(
        description="Validate plan exports (PNG, SVG, PDF) from an .ogp file."
    )
    parser.add_argument(
        "--ogp",
        type=Path,
        default=None,
        help="Path to .ogp plan file (generates a temporary sample plan if omitted).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to a temporary directory).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output.",
    )

    args = parser.parse_args(argv)

    if args.out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="ogp_validate_exports_"))
    else:
        out_dir = args.out_dir

    sample_ogp_path = None
    if args.ogp is None:
        with tempfile.NamedTemporaryFile(suffix=".ogp", delete=False) as f:
            sample_ogp_path = Path(f.name)
        ogp_file = create_sample_plan(sample_ogp_path)
    else:
        ogp_file = args.ogp

    try:
        results = validate_exports(ogp_file, out_dir, verbose=not args.quiet)
        if not args.quiet:
            print(f"\n=== Done. Outputs written to {out_dir} ===")
        return 0 if results["outputs"]["pdf"]["bytes"] > 0 else 1
    finally:
        if sample_ogp_path is not None:
            sample_ogp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
