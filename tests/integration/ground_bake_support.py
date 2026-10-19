"""Shared by the ground-bake tests (Phase 17 L1.5, #385) — not a test module.

THE PARITY PATTERN (docs §8.10.28). The ground bake claims to paint a flat item
"as the 2D canvas paints it". The judge is therefore the canvas itself:

- the REFERENCE is the app's own full-detail render of a real ``CanvasScene`` —
  ``services.scene_rendering.render_scene_region``, the path the exports use,
  with labels and drop shadows switched off — on the bake's pixel grid;
- the bake under test is given the canvas's background colour as its bare-ground
  colour (``GroundBaker(bare_rgb=…)``), so the two images are comparable pixel for
  pixel, antialiased edges and translucent fills included. That the PRODUCT's
  bare ground is the meadow is a separate, one-line assertion.

The reference clears the scene's selection and toggles item visibility — it is
the very thing the bake must not do — so it is only ever taken of a scene the
test owns.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    GroundGrid,
    GroundSpec,
    GroundTile,
    RecordingSink,
    SceneSync,
)
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.view3d.ground_bake import GroundBaker
from open_garden_planner.ui.view3d.snapshot import SkippedItem, snapshot_records

FORMAT = QImage.Format.Format_RGBA8888_Premultiplied


def canvas_rgb() -> tuple[int, int, int]:
    """The canvas's own background colour — the bare ground of a parity bake."""
    color = QColor(CanvasScene.CANVAS_COLOR)
    return (color.red(), color.green(), color.blue())


def rgba(image: QImage) -> np.ndarray:
    """A ``QImage`` as an (height, width, 4) int16 array (room for differences)."""
    converted = image.convertToFormat(FORMAT)
    bits = converted.constBits()
    assert bits is not None
    rows = np.frombuffer(bits.asstring(converted.sizeInBytes()), np.uint8).reshape(
        converted.height(), converted.bytesPerLine() // 4, 4)
    return rows[:, :converted.width(), :].astype(np.int16)


def tiles_rgba(tiles: Iterable[GroundTile], grid: GroundGrid) -> np.ndarray:
    """The tiles assembled into the whole ground, north up — by plain array
    slicing, independent of ``GroundBaker.image()``."""
    whole = np.zeros((grid.height_px, grid.width_px, 4), dtype=np.int16)
    seen = 0
    for tile in tiles:
        x0, y0, width, height = grid.tile_px_rect(tile.key)
        assert (tile.width_px, tile.height_px) == (width, height)
        part = np.frombuffer(tile.pixels, np.uint8).reshape(height, width, 4)
        top = grid.height_px - y0 - height
        whole[top:top + height, x0:x0 + width, :] = part
        seen += 1
    assert seen == grid.tile_count
    return whole


def canvas_render(scene: CanvasScene, grid: GroundGrid) -> np.ndarray:
    """The 2D canvas's own full-detail render of ``scene`` on the bake's pixel
    grid, north up (labels and drop shadows off, as the gate says). TEST-OWNED
    scenes only: it clears the selection (module docstring)."""
    scene.set_labels_visible(False)
    scene.set_shadows_enabled(False)
    image = QImage(grid.width_px, grid.height_px, FORMAT)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scale = grid.px_per_cm
    try:
        render_scene_region(scene, painter, QRectF(0, 0, grid.width_px, grid.height_px),
                            QRectF(0, 0, grid.width_px / scale, grid.height_px / scale),
                            y_flip=True)
    finally:
        painter.end()
    return rgba(image)


def difference(first: np.ndarray, second: np.ndarray) -> tuple[float, int]:
    """``(mean, max)`` absolute difference over the three colour channels."""
    delta = np.abs(first[..., :3] - second[..., :3])
    return float(delta.mean()), int(delta.max())


def luma(image: np.ndarray) -> np.ndarray:
    return 0.2126 * image[..., 0] + 0.7152 * image[..., 1] + 0.0722 * image[..., 2]


def ncc(first: np.ndarray, second: np.ndarray) -> float:
    """Normalised cross-correlation of two images' luma (1.0: the same picture)."""
    a, b = luma(first).astype(np.float64), luma(second).astype(np.float64)
    a, b = a - a.mean(), b - b.mean()
    scale = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / scale) if scale else 0.0


class Bake:
    """A real scene → ``snapshot_records`` → ``SceneSync`` (a recording sink and a
    ground baker): the product's pipeline, as the workspace will drive it."""

    def __init__(self, scene: CanvasScene, *, registry: BuilderRegistry | None = None,
                 bare_rgb: tuple[int, int, int] | None = None, baker: GroundBaker | None = None,
                 at_date: Any = None) -> None:
        self.scene = scene
        self.at_date = at_date
        self.sink = RecordingSink()
        if baker is None:
            baker = (GroundBaker(budget_s=None) if bare_rgb is None
                     else GroundBaker(bare_rgb=bare_rgb, budget_s=None))
        self.baker = baker
        self.sync = SceneSync(self.sink, registry, ground_baker=self.baker)
        self.plan = GroundSpec(float(scene.width_cm), float(scene.height_cm))
        self.skipped: list[SkippedItem] = []
        self.records: dict[str, Any] = {}
        self.last_diff: Any = None

    def step(self) -> Any:
        """One tick: one snapshot, one ``apply``. Returns the records' diff."""
        self.skipped = []
        self.records = snapshot_records(self.scene, self.at_date, skipped=self.skipped)
        self.last_diff = self.sync.apply(self.records, ground=self.plan)
        return self.last_diff

    def finish(self) -> int:
        """Run passes until no ground work is pending (a baker with a time budget):
        how many it took."""
        passes = 0
        while self.sync.ground_pending:
            self.sync.continue_ground()
            passes += 1
        return passes

    @property
    def grid(self) -> GroundGrid:
        grid = self.baker.grid
        assert grid is not None
        return grid

    @property
    def tiles(self) -> tuple[GroundTile, ...]:
        ground = self.sink.ground
        assert ground is not None
        return ground.tiles

    def image(self) -> np.ndarray:
        """What the SINK was told, assembled."""
        return tiles_rgba(self.tiles, self.grid)
