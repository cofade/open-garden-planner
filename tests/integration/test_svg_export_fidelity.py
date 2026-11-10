"""The SVG export is the picture the PNG export paints (#787).

``QSvgGenerator`` drops what it cannot write: a painter clip, a brush's own
transform, a pixmap's source rectangle. A parametric roof (two clipped halves,
each with its own brush transform) therefore flooded the drawing with tiles, a
glasshouse's glazing bars ran across the plan, and a sun shadow's feather came
out as heavy outlines. The export now records every draw call below the painter
and replays it with those three things rewritten as plain geometry
(``services/svg_export.py``).

Every test here measures the rendered picture: the SVG is rasterised and
compared with the PNG export of the same scene on the same pixel grid.

The rasteriser is Qt's own ``QSvgRenderer``. It is NOT a browser: it ignores
``clip-path`` (measured on Qt 6.12). That is why the export writes clipped
shapes as geometry — it is right in every renderer, this one included — and why
the one thing that keeps a real ``<clipPath>`` (a clipped picture) is asserted
on the file's structure instead of on pixels.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.fill_patterns import FillPattern, FillTransform
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.text_item import TextItem
from open_garden_planner.ui.canvas.roof_ridge_link import build_linked_ridge
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    SunShadowController,
    SunShadowOverlayItem,
)

EXAMPLES = ["family-garden", "balcony", "food-forest", "raised-bed"]

#: The SVG's user units per inch (``svg_export.SVG_UNITS_PER_INCH``): a PNG at
#: this dpi is painted on the same grid. Stated here, not imported, so the test
#: also pins the number.
UNITS_PER_INCH = 300

# The stated tolerance, on pictures averaged over 4 x 4 pixel blocks (a texture
# tile is resampled differently by the two rasterisers; a block is what the eye
# compares). Measured after the fix, over the four bundled examples and the
# built scene: mean difference 0.2-2.8 of 255, at most 1.0 % of blocks off by
# more than 32. Before it: mean 25-58, 32-71 % of blocks. What is left is
# antialiasing, pattern resampling and the advance widths of live text.
MAX_MEAN_DIFFERENCE = 5.0
MAX_SHARE_OFF = 0.04
OFF_THRESHOLD = 32
BLOCK = 4


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    buffer = image.bits()
    buffer.setsize(image.sizeInBytes())
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16)


def _export_both(scene: CanvasScene, folder: Path, width_cm: float = 10.0) -> tuple[QImage, QImage, str]:
    """(PNG export, the SVG export rasterised on the same grid, the SVG's text)."""
    png = folder / "plan.png"
    svg = folder / "plan.svg"
    ExportService.export_to_png(scene, png, dpi=UNITS_PER_INCH, output_width_cm=width_cm)
    ExportService.export_to_svg(scene, svg, output_width_cm=width_cm)
    reference = QImage(str(png))
    renderer = QSvgRenderer(str(svg))
    assert renderer.isValid()
    raster = QImage(reference.size(), QImage.Format.Format_ARGB32)
    raster.fill(QColor("white"))
    painter = QPainter(raster)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return reference, raster, svg.read_text(encoding="utf-8")


def _blocks(image: QImage) -> np.ndarray:
    pixels = _pixels(image).astype(np.float32)
    rows, columns = pixels.shape[0] // BLOCK * BLOCK, pixels.shape[1] // BLOCK * BLOCK
    pixels = pixels[:rows, :columns]
    return pixels.reshape(rows // BLOCK, BLOCK, columns // BLOCK, BLOCK, 3).mean(axis=(1, 3))


def _difference(first: QImage, second: QImage) -> tuple[float, float]:
    """(mean absolute difference of 255, share of blocks off by more than the threshold)."""
    delta = np.abs(_blocks(first) - _blocks(second))
    return float(delta.mean()), float((delta.max(axis=2) > OFF_THRESHOLD).mean())


def _colour_at(image: QImage, scene: CanvasScene, x_cm: float, y_cm: float) -> QColor:
    """The pixel showing plan point (x, y); the export is north-up (ADR-002)."""
    px = round(x_cm / scene.width_cm * image.width())
    py = round((1.0 - y_cm / scene.height_cm) * image.height())
    return image.pixelColor(min(image.width() - 1, px), min(image.height() - 1, py))


def _near(first: QColor, second: QColor, tolerance: int = 24) -> bool:
    return all(
        abs(a - b) <= tolerance
        for a, b in ((first.red(), second.red()), (first.green(), second.green()),
                     (first.blue(), second.blue()))
    )


def _built_scene() -> CanvasScene:
    """A plan with a parametric roof, a glasshouse, a turned pattern, a shadow and a note."""
    scene = CanvasScene(width_cm=1600, height_cm=1000)
    layer = scene.active_layer.id

    house = RectangleItem(100, 500, 600, 400, object_type=ObjectType.HOUSE, layer_id=layer)
    scene.addItem(house)
    ridge = build_linked_ridge(house, layer)
    assert ridge is not None
    scene.addItem(ridge)

    glasshouse = RectangleItem(900, 550, 400, 300, object_type=ObjectType.GREENHOUSE, layer_id=layer)
    scene.addItem(glasshouse)
    glass_ridge = build_linked_ridge(glasshouse, layer)
    if glass_ridge is not None:
        scene.addItem(glass_ridge)

    turned = RectangleItem(100, 80, 500, 300, object_type=ObjectType.GENERIC_RECTANGLE, layer_id=layer)
    turned.fill_pattern = FillPattern.ROOF_TILES
    turned.fill_color = QColor("#c0603a")
    turned.fill_transform = FillTransform(angle_deg=30.0, scale=2.0, offset_x_cm=17.0)
    turned._setup_styling()
    scene.addItem(turned)

    shadow = SunShadowOverlayItem()
    shadow.set_clip_rect(scene.canvas_rect)
    outline = QPainterPath()
    outline.addEllipse(QRectF(800, 100, 500, 280))
    shadow.set_shadow_path(outline)
    scene.addItem(shadow)

    note = TextItem(700, 470, "Plan note", font_size=1.0, layer_id=layer)
    scene.addItem(note)
    return scene


class _ForeignPainter(QGraphicsItem):
    """An item nobody taught about SVG: clips, a turned pattern, a cut-out picture."""

    def __init__(self) -> None:
        super().__init__()
        tile = QPixmap(40, 40)
        tile.fill(QColor("#2060c0"))
        stripe = QPainter(tile)
        stripe.fillRect(0, 0, 40, 12, QColor("#f0d020"))
        stripe.fillRect(0, 0, 8, 40, QColor("#d02020"))
        stripe.end()
        self._brush = QBrush(tile)
        self._brush.setTransform(QTransform().translate(13, 7).rotate(25).scale(1.5, 0.75))
        sheet = QPixmap(60, 30)
        sheet.fill(QColor("#10a040"))
        mark = QPainter(sheet)
        mark.fillRect(30, 0, 30, 30, QColor("#a01080"))
        mark.end()
        self._sheet = sheet

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 800, 500)

    def paint(self, painter: QPainter, _option: object, _widget: object = None) -> None:
        shape = QPainterPath()
        shape.addEllipse(QRectF(40, 40, 300, 220))
        painter.save()
        painter.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._brush)
        painter.drawRect(QRectF(-500, -500, 2000, 2000))            # a flood, clipped
        painter.setPen(QPen(QColor("#101010"), 14))
        painter.drawLine(QPointF(-200, 150), QPointF(900, 150))     # a stroke, clipped
        painter.restore()

        painter.save()
        painter.translate(420, 60)
        painter.rotate(20)
        painter.setPen(QPen(QColor("#303030"), 3))
        painter.setBrush(self._brush)                               # unclipped, own frame
        painter.drawRect(QRectF(0, 0, 300, 160))
        painter.restore()

        # The right half of a two-coloured sheet: a source rectangle.
        painter.drawPixmap(QRectF(60, 320, 200, 120), self._sheet, QRectF(30, 0, 30, 30))

        inner = QPainterPath()
        inner.addEllipse(QRectF(460, 300, 160, 160))
        painter.save()
        painter.setClipPath(inner, Qt.ClipOperation.IntersectClip)
        painter.drawPixmap(QRectF(420, 280, 260, 200), self._sheet, QRectF(0, 0, 60, 30))
        painter.restore()


def test_a_parametric_roof_and_a_glasshouse_stay_inside_their_outlines(qtbot, tmp_path: Path) -> None:
    scene = _built_scene()
    reference, raster, svg = _export_both(scene, tmp_path)

    mean, share = _difference(reference, raster)
    assert mean < MAX_MEAN_DIFFERENCE and share < MAX_SHARE_OFF, (mean, share)

    canvas = QColor(scene.CANVAS_COLOR)
    # Beside the roof and inside its oversized fill rectangle: bare canvas.
    for x, y in ((60, 700), (740, 700), (400, 950), (400, 460)):
        assert _near(_colour_at(raster, scene, x, y), canvas), ("roof flooded", x, y)
        assert _near(_colour_at(reference, scene, x, y), canvas)
    # On the lines the glazing bars run along, just outside the glasshouse.
    for x, y in ((860, 700), (1340, 700), (1100, 520), (1100, 880), (900 + 400 / 4, 890)):
        assert _near(_colour_at(raster, scene, x, y), canvas), ("glazing bar escaped", x, y)
    # The roof itself is tiled, and both halves are the PNG's halves.
    for x, y in ((400, 800), (400, 600), (250, 620), (600, 870)):
        assert _near(_colour_at(raster, scene, x, y), _colour_at(reference, scene, x, y), 60), (x, y)
        assert not _near(_colour_at(raster, scene, x, y), canvas)
    # No clip is left to a renderer: every clipped shape here is geometry.
    assert "<clipPath" not in svg


def test_a_shadow_feather_is_a_soft_edge_not_an_outline(qtbot, tmp_path: Path) -> None:
    scene = _built_scene()
    reference, raster, _svg = _export_both(scene, tmp_path)
    # Just inside the shadow's edge the feather must not darken the flat tone:
    # unclipped, the feather's strokes lay over the shadow as a dark ring.
    inside_edge = _colour_at(raster, scene, 800 + 6, 240)
    deep_inside = _colour_at(raster, scene, 1050, 240)
    assert _near(inside_edge, deep_inside, 10), (inside_edge.name(), deep_inside.name())
    assert _near(inside_edge, _colour_at(reference, scene, 800 + 6, 240), 10)


def test_a_painter_nobody_taught_about_svg_exports_as_it_paints(qtbot, tmp_path: Path) -> None:
    """The guard against drift: the recorder sits below QPainter, so an item's
    paint() needs no SVG knowledge — its clip, brush transform and source
    rectangle arrive in the file whatever it does."""
    scene = CanvasScene(width_cm=800, height_cm=500)
    scene.addItem(_ForeignPainter())
    reference, raster, svg = _export_both(scene, tmp_path)

    # The clipped picture keeps a real clip, which QSvgRenderer ignores: leave
    # its frame out of the comparison and assert the clip on the file instead.
    assert svg.count("<clipPath") == 1
    assert re.search(r'<g clip-path="url\(#[^)]+\)">\s*<g[^>]*>\s*<image', svg)
    left, top = round(410 / 800 * reference.width()), round((1 - 490 / 500) * reference.height())
    right, bottom = round(690 / 800 * reference.width()), round((1 - 270 / 500) * reference.height())
    for image in (reference, raster):
        blank = QPainter(image)
        blank.fillRect(left, top, right - left, bottom - top, QColor("white"))
        blank.end()

    mean, share = _difference(reference, raster)
    assert mean < MAX_MEAN_DIFFERENCE and share < MAX_SHARE_OFF, (mean, share)
    canvas = QColor(scene.CANVAS_COLOR)
    assert _near(_colour_at(raster, scene, 20, 20), canvas)        # the flood is cut
    assert _near(_colour_at(raster, scene, 380, 150), canvas)      # so is the stroke
    assert _near(_colour_at(raster, scene, 90, 380), QColor("#a01080"))   # the cut-out half
    assert _near(_colour_at(raster, scene, 230, 380), QColor("#a01080"))


@pytest.mark.parametrize("example", EXAMPLES)
def test_a_bundled_example_exports_to_svg_as_it_exports_to_png(qtbot, tmp_path: Path, example: str) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    reference, raster, _svg = _export_both(scene, tmp_path)
    mean, share = _difference(reference, raster)
    assert mean < MAX_MEAN_DIFFERENCE and share < MAX_SHARE_OFF, (example, mean, share)


@pytest.mark.parametrize("example", ["family-garden", "food-forest"])
def test_a_bundled_example_with_the_sun_study_on_exports_to_svg_as_to_png(
    qtbot, tmp_path: Path, example: str
) -> None:
    """The examples above are loaded with no sun study, so their pictures hold
    no shadow. With a live ``SunShadowController`` the overlay of a real plan
    is in the picture: a shade of many outlines and its soft edge, which is a
    field laid down as a picture (#793) — in the SVG as in the PNG."""
    bare_folder, sun_folder = tmp_path / "bare", tmp_path / "sun"
    bare_folder.mkdir()
    sun_folder.mkdir()
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    without, without_raster, _svg = _export_both(scene, bare_folder)

    controller = SunShadowController(scene, lambda: {"latitude": 52.52, "longitude": 13.405})
    controller.set_sim_datetime(datetime(2026, 6, 21, 15, 30, tzinfo=UTC))
    controller.set_enabled(True)
    assert controller.state == STATE_ACTIVE
    (overlay,) = [item for item in scene.items() if isinstance(item, SunShadowOverlayItem)]
    assert overlay.isVisible() and not overlay.path().isEmpty()

    reference, raster, _svg = _export_both(scene, sun_folder)
    mean, share = _difference(reference, raster)
    assert mean < MAX_MEAN_DIFFERENCE and share < MAX_SHARE_OFF, (example, mean, share)
    # What the study adds to each picture: the darkening against the same
    # format without it, so a texture the two rasterisers resample differently
    # cancels out. A tenth of the PNG is shade ...
    shade = _blocks(without) - _blocks(reference)
    shaded = shade.sum(axis=2) > 30
    assert shaded.mean() > 0.10, shaded.mean()
    # ... and the SVG is darker by the same amount in the same places.
    in_svg = _blocks(without_raster) - _blocks(raster)
    assert np.abs(in_svg - shade)[shaded].mean() < MAX_MEAN_DIFFERENCE
    assert np.abs(in_svg - shade)[~shaded].mean() < MAX_MEAN_DIFFERENCE


@pytest.mark.parametrize("example", EXAMPLES)
@pytest.mark.parametrize("width_cm", [29.7, 42.0])
def test_the_svg_states_the_requested_physical_size(
    qtbot, tmp_path: Path, example: str, width_cm: float
) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    target = tmp_path / "plan.svg"
    ExportService.export_to_svg(scene, target, output_width_cm=width_cm)
    root = re.search(r"<svg\b[^>]*>", target.read_text(encoding="utf-8"))
    assert root is not None
    width = re.search(r'\bwidth="([0-9.]+)mm"', root.group(0))
    height = re.search(r'\bheight="([0-9.]+)mm"', root.group(0))
    box = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', root.group(0))
    assert width and height and box, root.group(0)
    expected_height = width_cm * 10.0 * scene.height_cm / scene.width_cm
    assert float(width.group(1)) == pytest.approx(width_cm * 10.0, abs=0.05)
    assert float(height.group(1)) == pytest.approx(expected_height, abs=0.05)
    # One user unit is 1/300 inch across and down.
    assert float(box.group(1)) / float(width.group(1)) == pytest.approx(UNITS_PER_INCH / 25.4, rel=1e-3)
    assert float(box.group(2)) / float(height.group(1)) == pytest.approx(UNITS_PER_INCH / 25.4, rel=1e-3)


def test_text_stays_text_and_names_a_generic_fallback_family(qtbot, tmp_path: Path) -> None:
    scene = _built_scene()
    scene.addItem(TextItem(100, 440, "Courier note", font_family="Courier New", font_size=0.8))
    _reference, _raster, svg = _export_both(scene, tmp_path)
    notes = re.findall(r"<text\b([^>]*)>([^<]*)</text>", svg)
    assert {"Plan note", "Courier note"} <= {text.strip() for _attributes, text in notes}
    for attributes, text in notes:
        family = re.search(r'font-family="([^"]*)"', attributes)
        assert family, (text, attributes)
        assert family.group(1).split(",")[-1].strip() in ("sans-serif", "serif", "monospace"), family.group(1)
    by_text = {text.strip(): attributes for attributes, text in notes}
    assert "'Arial', sans-serif" in by_text["Plan note"]
    assert "'Courier New', monospace" in by_text["Courier note"]
