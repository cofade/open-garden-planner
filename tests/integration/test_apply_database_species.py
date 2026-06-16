"""Integration tests for issue #213 — apply database species to an existing plant.

When a database species is assigned to a generic plant already on the canvas, the
plant's properties must update to match the database and the canvas must reflect
it:
  * ``metadata['plant_species']`` is populated, and
  * on "apply database values" the drawn footprint is resized so its diameter
    equals the species' ``max_spread_cm`` (the visible change the issue asks for).

A drawn footprint (or manual spacing override) that differs from the database
triggers an "Apply database values / Keep custom values" prompt; "Apply" resizes
the footprint and clears any override, "Keep" preserves the placed size. The
whole assignment is a single undoable step.
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

# Tomato: max_spread_cm == 90 → footprint radius 45 cm (diameter == max_spread).
_SPECIES_NAME = "Solanum lycopersicum"
_DB_RADIUS = 45.0
# A placed plant whose footprint differs from the database size.
_PLACED_RADIUS = 20.0


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
    item = CircleItem(100.0, 100.0, _PLACED_RADIUS, object_type=ObjectType.SHRUB)
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


def _stub(panel: PlantDatabasePanel, monkeypatch, *, apply: bool) -> None:
    monkeypatch.setattr(panel, "_confirm_apply_database_values", lambda: apply)


# ---------------------------------------------------------------------------
# No conflicting override → footprint resizes silently (no prompt)


def _fail_prompt(panel: PlantDatabasePanel, monkeypatch) -> None:
    def _fail() -> bool:
        raise AssertionError("prompt must not appear without a conflicting override")

    monkeypatch.setattr(panel, "_confirm_apply_database_values", _fail)


def test_apply_resizes_footprint_silently(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    assert generic_plant.metadata.get("plant_species") is None
    assert generic_plant.radius == pytest.approx(_PLACED_RADIUS)
    _fail_prompt(panel, monkeypatch)  # no override → must not prompt

    panel._apply_species_to_item(generic_plant, _species_dict())

    species = generic_plant.metadata.get("plant_species")
    assert species is not None
    assert species["scientific_name"] == _SPECIES_NAME
    # The drawn circle silently adopts the real plant size (#213's visible change).
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_RADIUS)


def test_apply_is_a_single_undo_step(
    canvas: CanvasView, panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    cmd_mgr = canvas.command_manager
    _fail_prompt(panel, monkeypatch)

    panel._apply_species_to_item(generic_plant, _species_dict())
    assert generic_plant.metadata.get("plant_species") is not None
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    assert cmd_mgr.can_undo

    cmd_mgr.undo()
    # Both metadata and the footprint revert in one step.
    assert generic_plant.metadata.get("plant_species") is None
    assert generic_plant.radius == pytest.approx(_PLACED_RADIUS)

    cmd_mgr.redo()
    assert generic_plant.metadata.get("plant_species") is not None
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)


def test_no_prompt_when_override_matches_database(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    # An override equal to the DB value does not conflict → silent resize.
    generic_plant.spacing_radius_cm = _DB_RADIUS
    _fail_prompt(panel, monkeypatch)

    panel._apply_species_to_item(generic_plant, _species_dict())
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    assert generic_plant.metadata.get("plant_species") is not None


# ---------------------------------------------------------------------------
# A conflicting manual spacing override is the only thing that prompts


def test_override_apply_clears_custom_and_resizes(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = 10.0  # custom override, differs from DB
    _stub(panel, monkeypatch, apply=True)

    panel._apply_species_to_item(generic_plant, _species_dict())

    # Override cleared + footprint resized → database value wins.
    assert generic_plant.spacing_radius_cm is None
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_RADIUS)


def test_override_keep_preserves_custom_value(
    panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant.spacing_radius_cm = 10.0
    _stub(panel, monkeypatch, apply=False)

    panel._apply_species_to_item(generic_plant, _species_dict())

    # Keep custom values → both the override and the placed footprint untouched;
    # metadata still updated.
    assert generic_plant.spacing_radius_cm == pytest.approx(10.0)
    assert generic_plant.radius == pytest.approx(_PLACED_RADIUS)
    assert generic_plant.effective_spacing_radius() == pytest.approx(10.0)
    assert generic_plant.metadata.get("plant_species") is not None


# ---------------------------------------------------------------------------
# Shared module function (the Plants-menu search path in application.py)


def test_module_apply_resizes_silently_without_override(
    generic_plant: CircleItem,
) -> None:
    """No override → silent resize even though a confirm callback is supplied."""
    def _fail() -> bool:
        raise AssertionError("confirm must not be called without a conflicting override")

    apply_species_to_item(generic_plant, _species_dict(), confirm=_fail)
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    assert generic_plant.effective_spacing_radius() == pytest.approx(_DB_RADIUS)


def test_module_override_apply_with_confirm_callback(
    generic_plant: CircleItem,
) -> None:
    """A conflicting override is reconciled via the confirm callback (apply)."""
    generic_plant.spacing_radius_cm = 10.0
    apply_species_to_item(generic_plant, _species_dict(), confirm=lambda: True)
    assert generic_plant.spacing_radius_cm is None
    assert generic_plant.radius == pytest.approx(_DB_RADIUS)


def test_module_override_kept_without_confirm(
    generic_plant: CircleItem,
) -> None:
    """A conflicting override with no confirm callback is preserved (no prompt)."""
    generic_plant.spacing_radius_cm = 10.0
    apply_species_to_item(generic_plant, _species_dict(), confirm=None)
    assert generic_plant.spacing_radius_cm == pytest.approx(10.0)
    assert generic_plant.radius == pytest.approx(_PLACED_RADIUS)
    assert generic_plant.metadata.get("plant_species") is not None


# ---------------------------------------------------------------------------
# Footprint resize must not displace a ROTATED plant (regression: the serializer
# stores a circle's centre as pos + center, so the resize must keep that centre
# fixed and the rotation pivot on it — otherwise save/reload drifts the plant).


def _serialized_center(item: CircleItem) -> tuple[float, float]:
    # Mirrors core.project serialization: center_x/center_y = pos + center.
    return (item.pos().x() + item.center.x(), item.pos().y() + item.center.y())


def test_apply_keeps_rotated_plant_centered(
    canvas: CanvasView, panel: PlantDatabasePanel, generic_plant: CircleItem, monkeypatch
) -> None:
    generic_plant._apply_rotation(37.0)
    before_serialized = _serialized_center(generic_plant)
    before_visual = generic_plant.mapToScene(generic_plant.rect().center())
    _stub(panel, monkeypatch, apply=True)

    panel._apply_species_to_item(generic_plant, _species_dict())

    assert generic_plant.radius == pytest.approx(_DB_RADIUS)
    # Both the on-screen centre and the value the .ogp file would store are
    # preserved (no drift on save/reload, no jump on the next rotation).
    after_serialized = _serialized_center(generic_plant)
    after_visual = generic_plant.mapToScene(generic_plant.rect().center())
    assert after_serialized[0] == pytest.approx(before_serialized[0])
    assert after_serialized[1] == pytest.approx(before_serialized[1])
    assert after_visual.x() == pytest.approx(before_visual.x())
    assert after_visual.y() == pytest.approx(before_visual.y())
    # The rotation pivot tracks the new centre (invariant the serializer relies on).
    assert generic_plant.transformOriginPoint() == generic_plant.rect().center()

    # Undo restores size and centre in one step.
    canvas.command_manager.undo()
    assert generic_plant.radius == pytest.approx(_PLACED_RADIUS)
    undone_serialized = _serialized_center(generic_plant)
    assert undone_serialized[0] == pytest.approx(before_serialized[0])
    assert undone_serialized[1] == pytest.approx(before_serialized[1])


# ---------------------------------------------------------------------------
# Rotation pivot must be the geometric rect centre, not the badge-expanded
# boundingRect centre (#219). The antagonist badge is runtime-only (not
# serialized), so a pivot that depends on it makes the save-time pivot
# (badge on) disagree with the load-time pivot (badge off) → drift.


def test_rotation_pivots_about_rect_center_with_badge(
    generic_plant: CircleItem,
) -> None:
    center_before = generic_plant.mapToScene(generic_plant.rect().center())

    # Badge ON expands boundingRect asymmetrically (+x/+y); rect() is unchanged.
    generic_plant.set_antagonist_warning(True)
    assert generic_plant.boundingRect().center() != generic_plant.rect().center()

    generic_plant._apply_rotation(37.0)

    # Pivot is the geometric centre regardless of the badge.
    assert generic_plant.transformOriginPoint() == generic_plant.rect().center()
    # Rotating about the centre leaves the visual centre put.
    after_visual = generic_plant.mapToScene(generic_plant.rect().center())
    assert after_visual.x() == pytest.approx(center_before.x())
    assert after_visual.y() == pytest.approx(center_before.y())
    # What the .ogp file stores (pos + center) matches the on-screen centre, so
    # reopening (badge off) reproduces the same position — no save/reload drift.
    sx, sy = _serialized_center(generic_plant)
    assert sx == pytest.approx(after_visual.x())
    assert sy == pytest.approx(after_visual.y())
