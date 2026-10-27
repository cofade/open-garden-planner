"""Every path and fence style exports as it paints (PF-CAN-27; senior review of L4's
owner pass, #388).

``path_style_paint`` serves the canvas, the ground bake, the minimap and every export.
The owner pass made gravel and dirt their textures, first drawn with a texture-brush
PEN: right on screen, in PNG and in PDF, but ``QSvgGenerator`` writes a pen as its
colour, and a texture brush's colour is black — every gravel and dirt path came out
of an SVG export as a solid black bar. Asserted, through ``ExportService``:

- SVG, every style: no opaque black stroke as wide as the line; the textured styles
  are filled with a pattern;
- PNG and PDF, the textured styles: the middle of the line is the line's colour (the
  texture's mean), not black and not the canvas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QMarginsF, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QImage, QPageSize, QPainter, QPdfWriter

from open_garden_planner.core.object_types import PATH_FENCE_STYLES, ObjectType, PathFenceStyle
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

WIDTH_CM, DEPTH_CM = 1000.0, 600.0
LINE = ((100.0, 300.0), (500.0, 350.0), (900.0, 300.0))
#: A point on the line's first leg, far from its ends and its bend.
MIDDLE = (300.0, 325.0)
TEXTURED = (PathFenceStyle.GRAVEL_PATH, PathFenceStyle.DIRT_PATH)

_LEAF_GROUP = re.compile(r"<g ([^>]*)>(.*?)</g>", re.S)
_ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')


def _scene(style: PathFenceStyle) -> tuple[CanvasScene, PolylineItem]:
    kind = ObjectType.FENCE if PATH_FENCE_STYLES[style].category == "fence" else ObjectType.PATH
    scene = CanvasScene(width_cm=WIDTH_CM, height_cm=DEPTH_CM)
    item = PolylineItem([QPointF(x, y) for x, y in LINE], object_type=kind, path_fence_style=style)
    scene.addItem(item)
    return scene, item


def _painted_groups(svg: str) -> list[dict[str, str]]:
    """The attributes of every group that draws something (Qt writes flat groups)."""
    return [dict(_ATTRIBUTE.findall(head)) for head, body in _LEAF_GROUP.findall(svg)
            if "<path" in body or "<polyline" in body or "<rect" in body]


def _mean(image: QImage, x: float, y: float, radius: int = 4) -> tuple[float, float, float]:
    px, py = round(x), round(y)
    colours = [image.pixelColor(px + dx, py + dy)
               for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]
    return tuple(sum(getattr(c, channel)() for c in colours) / len(colours)
                 for channel in ("red", "green", "blue"))  # type: ignore[return-value]


def _is_the_lines_colour(mean: tuple[float, float, float], colour: QColor) -> bool:
    return all(abs(m - c) <= 40.0 for m, c in zip(mean, (colour.red(), colour.green(), colour.blue()),
                                                    strict=True))


@pytest.mark.parametrize("style", list(PathFenceStyle), ids=lambda s: s.name)
def test_no_style_exports_as_a_black_bar_to_svg(qtbot, tmp_path: Path, style: PathFenceStyle) -> None:
    scene, item = _scene(style)
    target = tmp_path / "plan.svg"
    ExportService.export_to_svg(scene, target)
    svg = target.read_text(encoding="utf-8")
    width = item.pen().widthF()
    black_bars = [group for group in _painted_groups(svg)
                  if group.get("stroke") in ("#000000", "black")
                  and float(group.get("stroke-opacity", "1")) > 0.99
                  and float(group.get("stroke-width", "0")) >= 0.5 * width]
    assert black_bars == [], f"{style.name}: an opaque black stroke as wide as the line"
    if style in TEXTURED:
        assert "<pattern" in svg
        assert any(group.get("fill", "").startswith("url(#") for group in _painted_groups(svg)), \
            f"{style.name}: the texture is not a pattern fill"


@pytest.mark.parametrize("style", TEXTURED, ids=lambda s: s.name)
def test_a_textured_line_is_its_colour_in_png_and_pdf(qtbot, tmp_path: Path, style: PathFenceStyle) -> None:
    scene, item = _scene(style)
    colour = item.pen().color()
    png = tmp_path / "plan.png"
    ExportService.export_to_png(scene, png, dpi=72)
    image = QImage(str(png))
    # the export is north-up: scene y grows up the image (the view's flip, ADR-002)
    x, y = MIDDLE
    png_mean = _mean(image, x / WIDTH_CM * image.width(), (1.0 - y / DEPTH_CM) * image.height())
    assert _is_the_lines_colour(png_mean, colour), (style.name, png_mean, colour.name())

    pdf = tmp_path / "plan.pdf"
    writer = QPdfWriter(str(pdf))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0))  # the page IS the paint area
    painter = QPainter(writer)
    page = QRectF(0.0, 0.0, writer.width(), writer.width() * DEPTH_CM / WIDTH_CM)
    scene.render(painter, page, QRectF(0.0, 0.0, WIDTH_CM, DEPTH_CM))  # unflipped: y down
    painter.end()
    from PyQt6.QtPdf import QPdfDocument

    document = QPdfDocument(None)
    assert document.load(str(pdf)) == QPdfDocument.Error.None_
    size = QSize(800, 1131)
    rendered = document.render(0, size)
    document.close()
    pdf_mean = _mean(rendered, x / WIDTH_CM * size.width(), y / DEPTH_CM * size.width() * DEPTH_CM / WIDTH_CM)
    assert _is_the_lines_colour(pdf_mean, colour), (style.name, pdf_mean, colour.name())
