"""Child process of ``test_dropped_canvas.py``: build canvases, drop them, collect.

Run as ``python dropped_canvas_child.py <repo root>``. A canvas is built with
everything the 2D branch added to it on show, painted once and then DROPPED: no
``close()``, no ``deleteLater()``. The cyclic collector then takes the view and
the scene together, in an order of its own, and Qt calls back into whichever of
the two it has not destroyed yet. Exit code 0 means the process lived through
that; an abort ends it with no Python traceback (PyQt calls ``qFatal`` when a
virtual it calls raises).
"""

from __future__ import annotations

import faulthandler
import gc
import sys
import weakref
from datetime import date

faulthandler.enable()
sys.path.insert(0, sys.argv[1])

from PyQt6.QtCore import QPointF, QRectF  # noqa: E402
from PyQt6.QtGui import QPainterPath  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

# The suite's own isolation (settings, app data, the offscreen platform):
# before the application is built and before the app's modules are imported.
import tests.conftest  # noqa: E402, F401

app = QApplication.instance() or QApplication([])

from open_garden_planner.core.heatmap_render import sun_legend  # noqa: E402
from open_garden_planner.core.object_types import ObjectType  # noqa: E402
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene  # noqa: E402
from open_garden_planner.ui.canvas.canvas_view import CanvasView  # noqa: E402
from open_garden_planner.ui.canvas.items import (  # noqa: E402
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.canvas.sun_legend import SunLegendKey  # noqa: E402
from open_garden_planner.ui.canvas.sun_shadow_controller import (  # noqa: E402
    SunShadowOverlayItem,
)
from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget  # noqa: E402

KEY = SunLegendKey(sun_legend(16.5 * 60), date(2026, 6, 21))  # type: ignore[arg-type]
VARIANTS = (
    "bare",
    "shown",
    "minimap",
    "selected",
    "zoomed in, with scroll bars and the minimap",
    "scene owned by the view",
)


def build(variant: str) -> weakref.ref[CanvasView]:
    """One canvas with labels, the grid, the sun overlay and the map's key on;
    nothing of it is kept but a weak reference to its view."""
    scene = CanvasScene(2000.0, 1500.0)
    view = CanvasView(scene)
    bed = RectangleItem(200, 200, 400, 250, object_type=ObjectType.RAISED_BED, name="Bed")
    plant = CircleItem(900, 500, 60, object_type=ObjectType.PERENNIAL, name="Sage")
    hedge = PolygonItem(
        [QPointF(1200, 300), QPointF(1500, 300), QPointF(1500, 700), QPointF(1200, 700)],
        object_type=ObjectType.HEDGE_SECTION, name="Hedge",
    )
    fence = PolylineItem(
        [QPointF(100, 1200), QPointF(900, 1300), QPointF(1700, 1200)],
        object_type=ObjectType.FENCE, name="Fence",
    )
    for item in (bed, plant, hedge, fence):
        scene.addItem(item)
        item.initialize_label()
    bed.set_succession_indicator([("Radish", True), ("Kale", False)])
    shade = QPainterPath()
    shade.addRect(QRectF(300, 300, 500, 400))
    overlay = SunShadowOverlayItem()
    scene.addItem(overlay)
    overlay.set_clip_rect(QRectF(0, 0, 2000, 1500))
    overlay.set_shadow_path(shade)
    view.set_grid_visible(True)
    view.set_sun_legend(KEY)
    minimap = MinimapWidget(view, scene) if "minimap" in variant else None
    if variant != "bare":
        view.resize(900, 600)
        view.show()
        app.processEvents()
        view.fit_in_view()
        view.viewport().repaint()
        app.processEvents()
        assert not view.sun_legend_rect().isEmpty(), "the key was not painted"
        assert scene.label_layouts > 0, "no label was laid out"
    if minimap is not None:
        minimap.set_visible(True)
        app.processEvents()
    if variant.startswith("zoomed in"):
        view.set_zoom(view.zoom_factor * 6.0)
        app.processEvents()
        view.viewport().repaint()
        bar = view.horizontalScrollBar()
        assert bar is not None and bar.isVisible(), "the plan was not zoomed in"
    if variant == "selected":
        bed.setSelected(True)
        app.processEvents()
    if variant == "scene owned by the view":
        scene.setParent(view)
    return weakref.ref(view)


for name in VARIANTS:
    for _ in range(2):
        dropped = build(name)
        for _ in range(3):
            gc.collect()
        assert dropped() is None, f"the collector did not take the view ({name})"
    print("dropped:", name, flush=True)
print("done", flush=True)
