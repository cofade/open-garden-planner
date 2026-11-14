"""Every bed shape paints the crop-rotation status border (#842).

Rectangle and polygon beds drew the coloured inner border that says "what grew
here last season is a good / suboptimal / violating predecessor"; ellipse and
circle beds drew nothing at all, so a rotation warning was invisible on exactly
the shapes a round bed uses. The four shapes now share one painter
(``GardenItemMixin._draw_rotation_status_border``) and this test renders each
through the real scene painter, compares the picture with and without a status,
and checks that the ink follows the status (green for good, red for violation)
and stays out of an export.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    RectangleItem,
)

_GOOD = "good"
_VIOLATION = "violation"


def _scene_with(kind: str) -> tuple[CanvasScene, object]:
    scene = CanvasScene(width_cm=500, height_cm=400)
    scene.set_shadows_enabled(False)
    if kind == "rectangle":
        item = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
    elif kind == "rectangle-raised":
        item = RectangleItem(100, 100, 200, 150, object_type=ObjectType.RAISED_BED)
    elif kind == "polygon":
        item = PolygonItem(
            [
                QPointF(100, 100),
                QPointF(300, 100),
                QPointF(300, 250),
                QPointF(100, 250),
            ],
            object_type=ObjectType.GARDEN_BED,
        )
    elif kind == "ellipse":
        item = EllipseItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
    else:  # circle
        item = CircleItem(200.0, 175.0, 100.0, object_type=ObjectType.GARDEN_BED)
    scene.addItem(item)
    return scene, item


def _render(scene: CanvasScene) -> QImage:
    rect = scene.canvas_rect
    image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    render_scene_region(
        scene,
        painter,
        QRectF(0, 0, image.width(), image.height()),
        rect,
        hide_overlays=False,
        hide_construction=True,
    )
    painter.end()
    return image


def _changed_pixels(first: QImage, second: QImage, threshold: int = 24) -> list[tuple[int, int]]:
    changed: list[tuple[int, int]] = []
    for y in range(first.height()):
        for x in range(first.width()):
            a, b = QColor(first.pixel(x, y)), QColor(second.pixel(x, y))
            if (
                abs(a.red() - b.red())
                + abs(a.green() - b.green())
                + abs(a.blue() - b.blue())
                > threshold
            ):
                changed.append((x, y))
    return changed


@pytest.mark.parametrize("kind", ["rectangle", "rectangle-raised", "polygon", "ellipse", "circle"])
def test_every_bed_shape_paints_the_rotation_status_border(
    kind: str, qtbot: object
) -> None:
    """#842: the inner border exists on all four bed outlines."""
    scene, bed = _scene_with(kind)

    plain = _render(scene)
    bed.set_rotation_status(_VIOLATION)  # type: ignore[attr-defined]
    violation = _render(scene)

    changed = _changed_pixels(plain, violation)
    assert len(changed) > 100, f"the {kind} bed painted no rotation border"

    # The same outline, greener ink for a good predecessor.
    bed.set_rotation_status(_GOOD)  # type: ignore[attr-defined]
    good = _render(scene)
    good_green = sum(QColor(good.pixel(x, y)).green() for x, y in changed)
    violation_green = sum(QColor(violation.pixel(x, y)).green() for x, y in changed)
    assert good_green > violation_green, f"the {kind} border did not follow the status"


@pytest.mark.parametrize("kind", ["rectangle", "rectangle-raised", "polygon", "ellipse", "circle"])
def test_the_rotation_border_stays_out_of_an_export(kind: str, qtbot: object) -> None:
    """A picture of the plan carries no diagnostic decoration (#786, #842)."""
    scene, bed = _scene_with(kind)
    bed.set_rotation_status(_VIOLATION)  # type: ignore[attr-defined]

    on_canvas = _render(scene)
    scene.set_diagnostic_overlays_visible(False)
    exported = _render(scene)

    assert _changed_pixels(on_canvas, exported) != []
