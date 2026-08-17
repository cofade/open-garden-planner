"""Unit pin for issue #305: the companion/spacing scene.changed handlers
must be idempotent.

``_update_spacing_overlaps`` and ``_update_companion_highlights`` run on a
debounce timer wired to ``QGraphicsScene.changed``. If either handler
mutates an item (``prepareGeometryChange()`` / ``update()``) on a tick where
the desired state hasn't actually changed, the scene emits ``changed`` again
and restarts the same debounce timer — a self-sustaining idle loop. These
tests call the handler twice in a row on a static scene and assert the
*second* call touches no item at all (zero ``prepareGeometryChange`` calls),
proving each handler now computes the final per-item state before setting it
exactly once, rather than clearing then re-setting every tick.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred (singleShot) modal Welcome dialog."""
    get_settings().show_welcome_on_startup = False


@pytest.fixture()
def window(qtbot: Any) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _count_prepare_geometry_change_calls(item: object) -> dict[str, int]:
    """Monkeypatch ``item.prepareGeometryChange`` with a call counter."""
    counts = {"n": 0}
    original = item.prepareGeometryChange  # type: ignore[attr-defined]

    def counted() -> None:
        counts["n"] += 1
        original()

    item.prepareGeometryChange = counted  # type: ignore[attr-defined]
    return counts


class TestUpdateSpacingOverlapsIdempotent:
    """A static scene with a plant that has real spacing data must reach a
    fixed point after the first call — the second call mutates nothing."""

    def test_second_call_touches_no_item(self, window: GardenPlannerApp, qtbot: Any) -> None:
        scene = window.canvas_scene
        plant = CircleItem(500.0, 500.0, 50.0, object_type=ObjectType.TREE)
        plant.metadata["plant_species"] = {
            "common_name": "Apple",
            "scientific_name": "Malus domestica",
            "max_spread_cm": 400,
        }
        scene.addItem(plant)
        qtbot.wait(50)

        # First call establishes "ideal" state (may legitimately mutate).
        window._update_spacing_overlaps()

        counts = _count_prepare_geometry_change_calls(plant)
        window._update_spacing_overlaps()

        assert counts["n"] == 0, (
            f"_update_spacing_overlaps mutated the plant {counts['n']} times "
            "on a repeat call with unchanged state — not idempotent (issue #305)"
        )


class TestUpdateCompanionHighlightsIdempotent:
    """A static scene with a permanent antagonist-warning pair must reach a
    fixed point after the first call — the second call mutates nothing."""

    def test_second_call_touches_no_item(self, window: GardenPlannerApp, qtbot: Any) -> None:
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
        qtbot.wait(50)

        # First call establishes the antagonist-warning state (may legitimately mutate).
        window._update_companion_highlights()

        tomato_counts = _count_prepare_geometry_change_calls(tomato)
        fennel_counts = _count_prepare_geometry_change_calls(fennel)
        window._update_companion_highlights()

        assert tomato_counts["n"] == 0 and fennel_counts["n"] == 0, (
            f"_update_companion_highlights mutated items "
            f"(tomato={tomato_counts['n']}, fennel={fennel_counts['n']}) on a "
            "repeat call with unchanged state — not idempotent (issue #305)"
        )
