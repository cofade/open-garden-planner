"""Integration tests for issue #213 — apply database species to an existing plant.

When a generic plant already on the canvas has a database species assigned to it
(via the plant database panel), its properties must update to match the database:
  * ``metadata['plant_species']`` is populated, and
  * the on-canvas spacing circle refreshes (``effective_spacing_radius()`` derives
    from the species' ``max_spread_cm`` when no manual override exists).

A manual spacing-radius override that differs from the database value triggers an
"Apply database values / Keep custom values" prompt. The whole assignment is a
single undoable step.
"""

from __future__ import annotations

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.bundled_species_db import (
    lookup_species,
    merge_calendar_data,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel
from open_garden_planner.ui.plant_species_assignment import apply_species_to_item

# Tomato: max_spread_cm == 90 → spacing radius 45 cm.
_SPECIES_NAME = "Solanum lycopersicum"
_DB_SPACING = 45.0


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


@pytest.fixture()
def generic_plant(canvas: CanvasView) -> CircleItem:
    """A generic plant on the canvas with no species metadata."""
    item = CircleItem(100.0, 100.0, 20.0, object_type=ObjectType.SHRUB)
    canvas.scene().addItem(item)
    return item


@pytest.fixture()
def panel(qtbot: object, generic_plant: CircleItem) -> PlantDatabasePanel:
    p = PlantDatabasePanel()
    qtbot.addWidget(p)  # type: ignore[attr-defined]
    p._current_plant_item = generic_plant
    return p


def _species_dict() -> dict:
    return merge_calendar_data(dict(lookup_species(_SPECIES_NAME)))


# ---------------------------------------------------------------------------
# Auto-apply with no manual override


def test_apply_species_populates_metadata_and_spacing(
    panel: PlantDatabasePanel, generic_plant: CircleItem
) -> None:
    assert generic_plant.metadata.get("plant_species") is None

    panel._apply_species_to_item(generic_plant, _species_dict())

    species = generic_plant.metadata.get("plant_species")
    assert species is not None
    assert species["scientific_name"] == _SPECIES_NAME
    # No manual override → spacing cascades from max_spread_cm / 2.
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_SPACING)


def test_apply_species_is_a_single_undo_step(
    canvas: CanvasView, panel: PlantDatabasePanel, generic_plant: CircleItem
) -> None:
    cmd_mgr = canvas.command_manager

    panel._apply_species_to_item(generic_plant, _species_dict())
    assert generic_plant.metadata.get("plant_species") is not None
    assert cmd_mgr.can_undo

    cmd_mgr.undo()
    assert generic_plant.metadata.get("plant_species") is None

    cmd_mgr.redo()
    assert generic_plant.metadata.get("plant_species") is not None
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_SPACING)


# ---------------------------------------------------------------------------
# Manual override reconciliation prompt


def test_override_apply_clears_custom_value(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = 10.0  # custom value, differs from DB (45)
    monkeypatch.setattr(panel, "_confirm_apply_database_values", lambda: True)

    panel._apply_species_to_item(generic_plant, _species_dict())

    # Override cleared → database value wins.
    assert generic_plant.spacing_radius_cm is None
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_SPACING)


def test_override_keep_preserves_custom_value(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = 10.0
    monkeypatch.setattr(panel, "_confirm_apply_database_values", lambda: False)

    panel._apply_species_to_item(generic_plant, _species_dict())

    # Custom override preserved; metadata still updated.
    assert generic_plant.spacing_radius_cm == pytest.approx(10.0)
    assert generic_plant.effective_spacing_radius() == pytest.approx(10.0)
    assert generic_plant.metadata.get("plant_species") is not None


def test_no_prompt_when_override_matches_database(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = _DB_SPACING  # equals DB value → no prompt

    def _fail() -> bool:
        raise AssertionError("prompt should not appear when override matches DB")

    monkeypatch.setattr(panel, "_confirm_apply_database_values", _fail)

    panel._apply_species_to_item(generic_plant, _species_dict())
    assert generic_plant.spacing_radius_cm == pytest.approx(_DB_SPACING)


def test_prompt_suppressed_when_prompt_false(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = 10.0  # differs from DB

    def _fail() -> bool:
        raise AssertionError("prompt must be suppressed when prompt=False")

    monkeypatch.setattr(panel, "_confirm_apply_database_values", _fail)

    panel._apply_species_to_item(generic_plant, _species_dict(), prompt=False)
    # Override untouched, metadata updated.
    assert generic_plant.spacing_radius_cm == pytest.approx(10.0)
    assert generic_plant.metadata.get("plant_species") is not None


# ---------------------------------------------------------------------------
# Shared module function (the Plants-menu search path in application.py)


def test_module_apply_with_confirm_callback(generic_plant: CircleItem) -> None:
    """The standalone helper honours the confirm callback (apply → clears)."""
    generic_plant.spacing_radius_cm = 10.0
    apply_species_to_item(generic_plant, _species_dict(), confirm=lambda: True)
    assert generic_plant.spacing_radius_cm is None
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_SPACING)


def test_module_apply_keeps_override_without_confirm(
    generic_plant: CircleItem,
) -> None:
    """With no confirm callback the differing override is preserved (no prompt)."""
    generic_plant.spacing_radius_cm = 10.0
    apply_species_to_item(generic_plant, _species_dict(), confirm=None)
    assert generic_plant.spacing_radius_cm == pytest.approx(10.0)
    assert generic_plant.metadata.get("plant_species") is not None
