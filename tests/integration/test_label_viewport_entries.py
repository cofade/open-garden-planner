"""What the scene keeps for a viewport goes when the viewport goes (review round 2, P2).

The label pass keeps one layout for each viewport that paints the scene, and
the scene keeps what each view stated no label may touch (the sun map's key).
Both were dictionaries keyed by ``id(viewport)``: an entry was never dropped,
and ``id`` is an address — a new widget that Python puts at a dead one's
address was handed the dead one's blockers and layout.

They are keyed by the widget itself now, weakly: the entry goes with the
widget, and no callable hangs on Qt's ``destroyed`` signal for it (a Python
callable there runs while the object is being torn down; PF-E3D-07).
"""

from __future__ import annotations

import gc
from datetime import date

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.heatmap_render import sun_legend
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.sun_legend import SunLegendKey

KEY = SunLegendKey(sun_legend(16.5 * 60), date(2026, 6, 21))  # type: ignore[arg-type]


def _scene() -> CanvasScene:
    scene = CanvasScene(1000, 800)
    bed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.RAISED_BED, name="Bed")
    scene.addItem(bed)
    bed.initialize_label()
    return scene


def _shown(scene: CanvasScene, qtbot) -> CanvasView:
    """A view of ``scene`` that has painted its labels and the sun map's key —
    the key is what a view states no label may touch."""
    view = CanvasView(scene)
    view.resize(900, 600)
    view.show()
    qtbot.waitExposed(view)
    view.fit_in_view()
    view.set_sun_legend(KEY)
    viewport = view.viewport()
    assert viewport is not None
    for _ in range(2):                     # the key is stated in one paint, kept clear of in the next
        QApplication.processEvents()
        viewport.repaint()
    assert not view.sun_legend_rect().isEmpty()
    assert scene.label_blockers(viewport)
    return view


def _destroy(view: CanvasView) -> None:
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def _kept(scene: CanvasScene) -> tuple[int, int]:
    """(viewports a layout is kept for, viewports with stated blockers)."""
    gc.collect()
    return scene.label_viewports_kept, scene.label_blocker_viewports


def test_a_viewports_entries_go_with_the_viewport(qtbot) -> None:
    scene = _scene()
    first, second = _shown(scene, qtbot), _shown(scene, qtbot)
    assert _kept(scene) == (2, 2)

    _destroy(first)
    del first
    assert _kept(scene) == (1, 1), "a dead viewport's layout or blockers are still kept"

    _destroy(second)
    del second
    assert _kept(scene) == (0, 0)


def test_a_new_viewport_starts_with_nothing(qtbot) -> None:
    """Whatever address Python gives it: the keys are the widgets, not their ids."""
    scene = _scene()
    for _ in range(4):
        view = _shown(scene, qtbot)
        _destroy(view)
        del view
        gc.collect()
        fresh = CanvasView(scene)
        viewport = fresh.viewport()
        assert viewport is not None
        assert scene.label_blockers(viewport) == ()
        _destroy(fresh)
        del fresh, viewport
    assert _kept(scene) == (0, 0)
