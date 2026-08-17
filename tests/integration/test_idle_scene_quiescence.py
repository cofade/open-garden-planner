"""Integration tests pinning issue #305 — "Probable memory leak".

A macOS user reported Open Garden Planner reaching 134 GB of memory after
roughly an hour of the app sitting idle. Two self-sustaining idle loops were
found, both driven by ``QGraphicsScene.changed``:

Loop A (``MinimapWidget._do_update``, ``src/.../ui/widgets/minimap_widget.py``):
hides overlay items, renders a thumbnail, then restores them. For a
*transformable* overlay item ``setVisible()`` makes the scene emit
``changed`` ASYNCHRONOUSLY — queued, delivered only after ``_do_update``
has already returned — and ``changed`` restarted the 100 ms throttle
timer, causing ``_do_update`` to run again, forever. Measured (offscreen
harness): ~1 render/1.5 s with no overlay items, 13-14 renders/1.5 s with
one transformable z>=_OVERLAY_Z_MIN item present, never quiescent. NOTE
(senior review, measured): ``setVisible()`` on an
``ItemIgnoresTransformations`` item emits NO ``changed`` at all — and every
handle, label and badge in this app carries that flag — so selection
handles do not trigger Loop A; in production only the curve-edit connector
lines (transformable, z>=10000) do. The reporter's idle churn came from
Loops B-D.

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
``_on_scene_changed`` self-dirty-rect filter in ``minimap_widget.py``). These tests
pin the end-to-end result on the real application window: once the scene
has settled, an idle window must produce exactly zero further
``scene.changed`` emissions and zero further minimap renders.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
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


def _wrap_scene_changed_counter(scene: Any) -> dict[str, int]:
    """Count ``scene.changed`` emissions from this point forward."""
    counts = {"n": 0}
    scene.changed.connect(lambda _rects: counts.__setitem__("n", counts["n"] + 1))
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
    """A selected bed (handles visible) must settle. Handles are
    ``ItemIgnoresTransformations`` and — measured — do not trigger Loop A;
    this pins the selected state end-to-end regardless (soil badge, spacing,
    companion all run on selection)."""

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


class TestIdleSceneQuiescenceWithTransformableOverlay:
    """End-to-end pin for Loop A specifically: a *transformable* z>=10000
    overlay item (what curve-edit mode's connector lines are) is present on
    the real window and the minimap must still settle."""

    def test_no_minimap_renders_with_transformable_overlay_present(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        from PyQt6.QtWidgets import QGraphicsRectItem

        from open_garden_planner.ui.widgets.minimap_widget import _OVERLAY_Z_MIN

        scene = window.canvas_scene
        overlay = QGraphicsRectItem(-5, -5, 10, 10)
        overlay.setPos(1000, 800)
        overlay.setZValue(_OVERLAY_Z_MIN + 1)  # transformable, no IIT flag
        scene.addItem(overlay)
        qtbot.wait(1500)

        changed_count = {"n": 0}
        scene.changed.connect(
            lambda _rects: changed_count.__setitem__("n", changed_count["n"] + 1)
        )
        render_count = _wrap_minimap_render_counter(window)
        qtbot.wait(2000)

        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle with a "
            "transformable overlay item present — Loop A (issue #305)"
        )
        assert changed_count["n"] == 0


class TestIdleSceneQuiescenceWithSpacingIdealPlant:
    """Pin for ``_update_spacing_overlaps``: a single plant with real spacing
    data settles into "ideal" state and must not keep re-triggering
    ``scene.changed`` forever (issue #305 loop C)."""

    def test_no_changed_or_renders_while_idle_with_spacing_data(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        plant = CircleItem(500.0, 500.0, 50.0, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {
            "common_name": "Apple",
            "scientific_name": "Malus domestica",
            "max_spread_cm": 400,
        }
        scene.addItem(plant)

        qtbot.wait(1500)

        changed_count = _wrap_scene_changed_counter(scene)
        render_count = _wrap_minimap_render_counter(window)

        qtbot.wait(2000)

        assert changed_count["n"] == 0, (
            f"scene.changed fired {changed_count['n']} times while idle with "
            "one spaced-out plant — self-sustaining loop (issue #305)"
        )
        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle with "
            "one spaced-out plant — self-sustaining loop (issue #305)"
        )


class TestIdleSceneQuiescenceWithAntagonistWarning:
    """Pin for ``_update_companion_highlights``: a permanent antagonist
    warning badge (tomato/fennel, no selection needed) must not keep
    re-triggering ``scene.changed`` forever (issue #305 loop C)."""

    def test_no_changed_or_renders_while_idle_with_antagonist_pair(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        tomato = CircleItem(800.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL)
        tomato.plant_species = "tomato"
        tomato.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
        }
        fennel = CircleItem(860.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL)
        fennel.plant_species = "fennel"
        fennel.metadata["plant_species"] = {
            "common_name": "Fennel",
            "scientific_name": "Foeniculum vulgare",
        }
        scene.addItem(tomato)
        scene.addItem(fennel)

        qtbot.wait(1500)

        changed_count = _wrap_scene_changed_counter(scene)
        render_count = _wrap_minimap_render_counter(window)

        qtbot.wait(2000)

        assert changed_count["n"] == 0, (
            f"scene.changed fired {changed_count['n']} times while idle with "
            "an antagonist pair — self-sustaining loop (issue #305)"
        )
        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle with "
            "an antagonist pair — self-sustaining loop (issue #305)"
        )


class TestIdleSceneQuiescenceWithSelectedBeneficialNeighbor:
    """Pin for ``_update_companion_highlights``: a selected plant with a
    beneficial neighbour (coloured ring, not just the permanent badge) must
    not keep re-triggering ``scene.changed`` forever (issue #305 loop C)."""

    def test_no_changed_or_renders_while_idle_with_selection_ring(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        tomato = CircleItem(500.0, 500.0, 30.0, object_type=ObjectType.PERENNIAL)
        tomato.plant_species = "tomato"
        tomato.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
        }
        basil = CircleItem(550.0, 500.0, 20.0, object_type=ObjectType.PERENNIAL)
        basil.plant_species = "basil"
        basil.metadata["plant_species"] = {
            "common_name": "Basil",
            "scientific_name": "Ocimum basilicum",
        }
        scene.addItem(tomato)
        scene.addItem(basil)

        tomato.setSelected(True)  # stays selected through the idle window
        qtbot.wait(300)

        qtbot.wait(1500)

        changed_count = _wrap_scene_changed_counter(scene)
        render_count = _wrap_minimap_render_counter(window)

        qtbot.wait(2000)

        assert changed_count["n"] == 0, (
            f"scene.changed fired {changed_count['n']} times while idle with "
            "a selected plant + beneficial neighbour ring — self-sustaining "
            "loop (issue #305)"
        )
        assert render_count["n"] == 0, (
            f"minimap re-rendered {render_count['n']} times while idle with "
            "a selected plant + beneficial neighbour ring — self-sustaining "
            "loop (issue #305)"
        )


class TestIdleSceneQuiescenceCountersDetectMovement:
    """Positive control: prove the counters used above actually work by
    moving a plant after settle and observing at least one ``changed``."""

    def test_moving_a_plant_after_settle_produces_changed(
        self, window: GardenPlannerApp, qtbot: Any
    ) -> None:
        scene = window.canvas_scene
        plant = CircleItem(500.0, 500.0, 50.0, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {
            "common_name": "Apple",
            "scientific_name": "Malus domestica",
            "max_spread_cm": 400,
        }
        scene.addItem(plant)

        qtbot.wait(1500)

        changed_count = _wrap_scene_changed_counter(scene)

        plant.setPos(plant.pos() + QPointF(10, 0))
        qtbot.wait(200)

        assert changed_count["n"] >= 1, (
            "moving a plant produced no scene.changed at all — the counter "
            "used by the idle-quiescence tests above is not measuring "
            "anything, so a zero result there would be meaningless"
        )
