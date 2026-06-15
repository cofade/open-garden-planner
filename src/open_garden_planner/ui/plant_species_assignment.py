"""Shared helper for assigning a database species to an existing plant item.

Used by both the plant database panel (Load Custom / Create Custom / Save to
library) and the Plants-menu species search so that every "assign species to an
existing plant" path behaves identically (issue #213):

  * writes ``metadata['plant_species']``;
  * refreshes the on-canvas spacing circle (derived from the species'
    ``max_spread_cm`` via ``effective_spacing_radius()``);
  * reconciles a manual ``spacing_radius_cm`` override via an optional prompt;
  * records a single undoable step (``ApplySpeciesCommand``).

The drawn circle diameter is intentionally left unchanged — consistent with the
drag-and-drop populate path (FR-PLANT-15); only the spacing circle and metadata
update.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QGraphicsItem, QMessageBox, QWidget

from open_garden_planner.core.commands import ApplySpeciesCommand

# Spacing radii within this many cm are treated as equal (avoids prompting on
# float round-trip noise).
_SPACING_EPSILON_CM = 1e-6


def _tr(text: str) -> str:
    # Keep the same context the strings are registered under in
    # scripts/fill_translations.py so translations resolve.
    return QCoreApplication.translate("PlantDatabasePanel", text)


def confirm_apply_database_values(parent: QWidget | None) -> bool:
    """Prompt whether to overwrite a differing manual override with the DB value.

    Returns True to apply database values (clear the override), False to keep the
    user's custom value.
    """
    msg = QMessageBox(parent)
    msg.setWindowTitle(_tr("Apply Database Values"))
    msg.setText(
        _tr(
            "This plant has custom values that differ from the database. "
            "Apply the database values?"
        )
    )
    apply_btn = msg.addButton(
        _tr("Apply database values"), QMessageBox.ButtonRole.AcceptRole
    )
    msg.addButton(_tr("Keep custom values"), QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(apply_btn)
    msg.exec()
    return msg.clickedButton() is apply_btn


def apply_species_to_item(
    plant_item: QGraphicsItem,
    species_dict: dict[str, Any],
    *,
    prompt: bool = True,
    confirm: Callable[[], bool] | None = None,
) -> None:
    """Assign ``species_dict`` to ``plant_item`` (undoable + repaints canvas).

    Args:
        plant_item: The plant item to update (CircleItem).
        species_dict: The species record to assign (already merged via
            ``merge_calendar_data``).
        prompt: When False, never reconcile differing custom values (used by
            live field edits / library saves where the drawn size and override
            must not change).
        confirm: Callable returning True to apply database values when the drawn
            footprint or a manual override differs from the database. Required
            for the prompt to fire; when None the custom values are preserved.

    On "apply database values" the drawn footprint is resized so its diameter
    equals the species' ``max_spread_cm`` (and any manual spacing override is
    cleared so the database value cascades); otherwise the placed size is kept.
    Either way ``metadata['plant_species']`` is updated. The neighbour-collision
    *overlap* indicator is recomputed separately by the main window's
    ``_update_spacing_overlaps`` on the resulting ``scene.changed`` — it is not
    re-flagged here.
    """
    old_species = None
    existing = plant_item.metadata.get("plant_species")  # type: ignore[attr-defined]
    if isinstance(existing, dict):
        old_species = existing

    old_override = getattr(plant_item, "spacing_radius_cm", None)
    old_radius = getattr(plant_item, "radius", None)

    # Footprint radius / spacing radius the database would yield. The drawn
    # circle's diameter should equal max_spread_cm, so both derive from
    # max_spread_cm / 2.
    max_spread = species_dict.get("max_spread_cm")
    db_radius = (
        float(max_spread) / 2.0
        if isinstance(max_spread, (int, float)) and max_spread > 0
        else None
    )

    # Default: leave the placed footprint and the override untouched.
    new_override = old_override
    new_radius = old_radius

    # Would applying the database values actually change anything visible?
    footprint_differs = (
        db_radius is not None
        and old_radius is not None
        and abs(old_radius - db_radius) > _SPACING_EPSILON_CM
    )
    override_differs = (
        db_radius is not None
        and old_override is not None
        and abs(old_override - db_radius) > _SPACING_EPSILON_CM
    )

    # Reconcile custom values that disagree with the database (footprint size or
    # a manual spacing override). Default is to apply the database values.
    if (
        prompt
        and db_radius is not None
        and (footprint_differs or override_differs)
        and confirm is not None
        and confirm()
    ):
        new_radius = db_radius  # drawn circle adopts the real plant size
        new_override = None  # let the database spacing cascade win

    command = ApplySpeciesCommand(
        plant_item,
        old_species,
        species_dict,
        old_override,
        new_override,
        old_radius,
        new_radius,
    )

    scene = plant_item.scene()
    cmd_mgr = getattr(scene, "_command_manager", None) if scene else None
    if cmd_mgr is not None:
        # Dirties the document via the stack_changed → mark_dirty wiring (#209).
        cmd_mgr.execute(command)
    else:
        # No command manager (e.g. a detached item in a test) — apply directly.
        command.execute()

    # Refresh soil-mismatch borders (US-12.10d) now that species data changed.
    if scene is not None and hasattr(scene, "views"):
        for view in scene.views():
            if hasattr(view, "refresh_soil_mismatches"):
                view.refresh_soil_mismatches()
