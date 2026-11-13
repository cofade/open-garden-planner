"""A large labelled plan for tests of what a repaint costs (review of #784, #793).

The bundled examples hold about a hundred objects; a cost that grows with the
number of objects does not show on them. This plan is the one the review of the
2D visual-polish branch measured: 853 named objects on a 50 m x 30 m canvas,
every eighth a raised bed, the others perennials, placed by a seeded generator
so that every run and every machine builds the same plan.

Tests COUNT with it (builds, layouts, paints: §8.10.10); the timings taken on
it are in §8.37.
"""

from __future__ import annotations

import random

from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

#: Objects on the review's plan.
LARGE_PLAN_ITEMS = 853
LARGE_PLAN_SIZE_CM = (5000.0, 3000.0)
#: The viewport the review measured it in.
REVIEW_VIEWPORT = (1469, 901)


def build_large_plan(
    count: int = LARGE_PLAN_ITEMS, *, seed: int = 1
) -> tuple[CanvasScene, list[RectangleItem | CircleItem]]:
    """A scene of ``count`` named objects, each with its label, and the objects."""
    generator = random.Random(seed)
    scene = CanvasScene(*LARGE_PLAN_SIZE_CM)
    items: list[RectangleItem | CircleItem] = []
    for index in range(count):
        x, y = generator.uniform(100.0, 4900.0), generator.uniform(100.0, 2900.0)
        item: RectangleItem | CircleItem
        if index % 8 == 0:
            item = RectangleItem(
                x, y, 200.0, 120.0, object_type=ObjectType.RAISED_BED, name=f"Bed {index}"
            )
        else:
            item = CircleItem(
                x, y, generator.uniform(15.0, 60.0),
                object_type=ObjectType.PERENNIAL, name=f"Plant {index}",
            )
        scene.addItem(item)
        item.initialize_label()
        items.append(item)
    return scene, items


def show_large_plan(
    qtbot, count: int = LARGE_PLAN_ITEMS, *, size: tuple[int, int] = REVIEW_VIEWPORT,
    seed: int = 1,
) -> tuple[CanvasView, CanvasScene, list[RectangleItem | CircleItem]]:
    """The plan in a shown view, fitted and painted once."""
    scene, items = build_large_plan(count, seed=seed)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(*size)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    view.fit_in_view()
    QApplication.processEvents()
    view.viewport().repaint()
    QApplication.processEvents()
    return view, scene, items
