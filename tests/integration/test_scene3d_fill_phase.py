"""A raised solid's fill sits in the SAME phase as the canvas's (#628 follow-up).

The ground bake is the canvas's own painter (``paint_record`` is the 2D painter's
pose and brush), so it is the source of truth for where a fill texture lands. A
record's footprint is CENTRED on its anchor, which the snapshot writes as
``params["paint_origin"]``; the canvas paints the item at ``anchor + position``.
The 3D cap must therefore sample ``(position + paint_origin) / 256``.

This test bakes a real rectangle at a non-degenerate position, samples the tinted
texture at the mesh's phase and correlates it against the bake's pixels — and shows
that the other sign does NOT correlate. A per-``paint_origin`` test matters: the
two signs coincide whenever ``2 * paint_origin`` is a multiple of 256.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core.fill_patterns import (
    FillPattern,
    create_pattern_brush,
    tinted_pattern_pixels,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import Record
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.ground_bake import paint_record
from open_garden_planner.ui.view3d.snapshot import snapshot_records

WIDTH_CM, HEIGHT_CM = 1200, 900


def _bake(record: Record) -> QImage:
    """The record painted as the canvas paints it: 1 px = 1 cm, north up."""
    image = QImage(WIDTH_CM, HEIGHT_CM, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.scale(1.0, -1.0)              # scene north -> up
        painter.translate(0.0, -HEIGHT_CM)
        paint_record(painter, record)
    finally:
        painter.end()
    return image


def _pixels(image: QImage) -> np.ndarray:
    rgb = image.convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = rgb.bits()
    buffer.setsize(rgb.sizeInBytes())
    return np.frombuffer(buffer, dtype=np.uint8).reshape(
        rgb.height(), rgb.width(), 4)[:, :, :3].copy()


def _texture(pattern: FillPattern, colour: QColor) -> np.ndarray:
    pixels = tinted_pattern_pixels(pattern, colour)
    assert pixels is not None
    width, height, data = pixels
    return np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)[:, :, :3]


def _ncc(first: np.ndarray, second: np.ndarray) -> float:
    a = first.reshape(-1).astype(np.float64)
    b = second.reshape(-1).astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denominator) if denominator else 0.0


@pytest.mark.parametrize(("pattern", "colour"), [
    (FillPattern.MULCH, (200, 30, 120, 255)),
    (FillPattern.BRICK, (90, 140, 210, 255)),
])
def test_the_cap_uvs_are_the_bakes_phase(qtbot, pattern: FillPattern,
                                         colour: tuple[int, int, int, int]) -> None:
    scene = CanvasScene(2000.0, 2000.0)
    item = RectangleItem(610.0, 380.0, 300.0, 200.0, object_type=ObjectType.TERRACE_PATIO,
                         layer_id=scene.active_layer.id)
    item.fill_pattern = pattern
    item.fill_color = QColor(*colour)
    item.setBrush(create_pattern_brush(pattern, QColor(*colour)))
    scene.addItem(item)
    record = dataclasses.replace(snapshot_records(scene)[str(item.item_id)], height_cm=40.0)
    origin = record.params["paint_origin"]
    assert origin == (record.transform.east_cm, record.transform.north_cm) == (760.0, 480.0)
    assert record.footprints[0][0] == (-150.0, -100.0), "the footprint is centred on the anchor"

    (part,) = production_registry().build(record)
    assert part.fill_texture and part.name == "platform"
    top = part.mesh.normals[:, 2] > 0.999   # the cap; the part also holds the walls
    cap = [(part.mesh.positions[index], part.mesh.uvs[index])
           for index in range(len(part.mesh.positions)) if top[index]]
    assert len(cap) == 6, "the cap is two triangles"

    baked = _pixels(_bake(record))
    texture = _texture(pattern, QColor(*colour))
    # sample points inside the square, away from the 2.5 px stroke
    xs = range(630, 891, 7)
    ys = range(400, 561, 7)
    seen, truth = [], []
    for x in xs:
        for y in ys:
            r = (x - record.transform.east_cm, y - record.transform.north_cm)
            uv = _uv_at(cap, r)
            if uv is None:                     # outside the cap's triangles (never for a square)
                continue
            seen.append(texture[int(uv[1] * 256.0) % 256, int(uv[0] * 256.0) % 256])
            truth.append(baked[HEIGHT_CM - 1 - y, x])
    assert len(seen) > 500
    score = _ncc(np.asarray(seen), np.asarray(truth))
    print(f"\n{pattern.name}: mesh UVs vs the bake, NCC {score:.4f}")
    assert score >= 0.98, "the raised fill is not in the canvas's phase"


def _uv_at(cap: list[tuple[np.ndarray, np.ndarray]], point: tuple[float, float]) -> tuple[float, float] | None:
    """The cap's interpolated UV at record point *point* (barycentric in its triangle)."""
    for first in range(0, len(cap), 3):
        (a, ua), (b, ub), (c, uc) = cap[first], cap[first + 1], cap[first + 2]
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        cx, cy = float(c[0]), float(c[1])
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            continue
        wb = ((point[0] - ax) * (cy - ay) - (point[1] - ay) * (cx - ax)) / area
        wc = ((bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax)) / area
        wa = 1.0 - wb - wc
        if min(wa, wb, wc) >= -1e-6:
            u = wa * float(ua[0]) + wb * float(ub[0]) + wc * float(uc[0])
            v = wa * float(ua[1]) + wb * float(ub[1]) + wc * float(uc[1])
            return (u, v)
    return None
