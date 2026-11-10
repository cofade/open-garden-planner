"""A closed plan's sprites do not stay behind (second review of the 2D branch, P2).

``core.sprite_raster.SPRITE_CACHE`` holds every plant and object sprite the
canvas has painted, up to 256 MB for a large viewport. ``clear_sprite_cache()``
existed and nothing called it: the sprites of a plan that was closed, or
replaced by another, stayed until the next plan's sprites pushed them out.

The scene's teardown is ONE place — ``CanvasScene.clear()``, which New, Open
and "New from example" all go through — and the cache is cleared there.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.sprite_raster import SPRITE_CACHE
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem


def test_clearing_the_scene_clears_the_sprite_cache(qtbot) -> None:
    SPRITE_CACHE.clear()
    scene = CanvasScene(1000, 800)
    for index, kind in enumerate((ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL)):
        scene.addItem(CircleItem(200.0 + 250.0 * index, 400.0, 80.0, object_type=kind))
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)
    view.fit_in_view()
    QApplication.processEvents()
    view.viewport().repaint()
    assert len(SPRITE_CACHE) >= 3 and SPRITE_CACHE.bytes_used > 0, "no sprite was painted"

    scene.clear()                      # what New / Open / New from example do to the plan
    assert len(SPRITE_CACHE) == 0
    assert SPRITE_CACHE.bytes_used == 0

    # ... and the next plan paints its own
    scene.addItem(CircleItem(500.0, 400.0, 80.0, object_type=ObjectType.TREE))
    QApplication.processEvents()
    view.viewport().repaint()
    assert len(SPRITE_CACHE) >= 1
