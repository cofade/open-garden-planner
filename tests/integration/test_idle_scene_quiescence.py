"""Integration tests pinning issue #305 — "Probable memory leak".

A macOS user reported Open Garden Planner reaching 134 GB of memory after
roughly an hour of the app sitting idle. Two self-sustaining idle loops were
found, both driven by ``QGraphicsScene.changed``:

Loop A (``MinimapWidget._do_update``, ``src/.../ui/widgets/minimap_widget.py``):
hides overlay/handle items, renders a thumbnail, then restores them. Each
``setVisible()`` makes the scene emit ``changed`` ASYNCHRONOUSLY — queued,
delivered only after ``_do_update`` has already returned — and ``changed``
is connected to ``_schedule_update``, which restarted the 100 ms throttle
timer, causing ``_do_update`` to run again, forever, whenever any overlay
item (selection/resize/rotation handles, dimension labels, ...) was present.
Measured (offscreen harness): ~1 render/1.5 s with no overlay items, 13-14
renders/1.5 s with one overlay item present, never quiescent.

Loop B (``CanvasView._update_soil_mismatches`` / ``_update_soil_badges``,
``src/.../ui/canvas/canvas_view.py``): the 500 ms soil debounce handler
called ``item.setToolTip()`` / ``item.update()`` / (via
``SoilBadgeItem.update_position``) ``setPos()`` unconditionally on every
tick for every bed, which itself makes the scene emit ``changed`` and
restarts the same debounce timer. Measured in the real ``GardenPlannerApp``:
a single ``GARDEN_BED`` on the plan, never selected, produced 16
``scene.changed`` emissions + 8 minimap renders per 4 s, forever (0 for a
non-bed rectangle, which the soil code ignores entirely).

Both loops feed EVERY ``scene.changed`` subscriber (companion checker,
spacing checker, plant-search debounce, the snap dirty flag, the sun-shadow
debounce, the minimap) — a full-scene render plus pixmap allocations plus
O(n^2) scans every cycle, while the user is doing nothing at all.

The fix makes both handlers idempotent (soil) and makes the minimap ignore
the ``changed`` emissions its own hide/restore provokes (see the
``_suppress_self_changed`` mechanism in ``minimap_widget.py``). These tests
pin the end-to-end result on the real application window: once the scene
has settled, an idle window must produce exactly zero further
``scene.changed`` emissions and zero further minimap renders.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred (singleShot) modal Welcome dialog.

    Depends on the conftest reset so this write survives the per-test store
    clear. Without it, a pumped event loop can block the run on a modal dialog.
    """
    get_settings().show_welcome_on_startup = False


@pytest.fixture()
def window(qtbot: Any) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _wrap_minimap_render_counter(window: GardenPlannerApp) -> dict[str, int]:
    """Reroute the minimap's throttle-timer timeout through a counter.

    Assigning ``window._minimap._do_update = wrapper`` as a plain instance
    attribute would NOT be observed: the timer's ``timeout`` signal was
    already connected to the original bound method inside
    ``MinimapWidget.__init__``. The timer's connection has to be replaced.
    """
    minimap = window._minimap
    counts = {"n": 0}
    original = minimap._do_update

    def counted() -> None:
        counts["n"] += 1
        original()

    minimap._update_timer.timeout.disconnect()
    minimap._update_timer.timeout.connect(counted)
    return counts


class TestIdleSceneQuiescenceAfterDeselect:
    """End-to-end pin: a bed that WAS selected (handles existed, then were
    removed) must not leave either loop running."""

    def test_no_scene_changed_or_minimap_renders_while_idle(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        item = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(item)

        # Select (creates resize/rotation handles — Loop A's overlay items),
        # then deselect (removes them again) — the common real-world path.
        item.setSelected(True)
        qtbot.wait(300)
        item.setSelected(False)

        # Let everything triggered by add/select/deselect (and the soil
        # debounce it may have kicked off) settle before we start counting.
        qtbot.wait(1500)

        changed_count = {"n": 0}
        scene.changed.connect(
            lambda _rects: changed_count.__setitem__("n", changed_count["n"] + 1)
        )
        render_count = _wrap_minimap_render_counter(window)

        qtbot.wait(2000)

        assert changed_count["n"] == 0, (
            f"scene.changed fired {changed_count['n']} times while idle after "
            "deselect — self-sustaining loop (issue #305)"
        )
        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle after "
            "deselect — self-sustaining loop (issue #305)"
        )


class TestIdleSceneQuiescenceWhileSelected:
    """End-to-end pin for Loop A specifically: overlay/handle items are
    ACTIVELY present (bed stays selected) and the minimap must still settle."""

    def test_no_minimap_renders_while_selected_and_idle(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        item = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(item)

        item.setSelected(True)  # handles stay visible for the rest of the test

        # Let add/select (and the soil debounce it may have kicked off) settle.
        qtbot.wait(1500)

        render_count = _wrap_minimap_render_counter(window)

        qtbot.wait(2000)

        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle with "
            "the bed still selected (handles visible) — self-sustaining "
            "loop (issue #305)"
        )
