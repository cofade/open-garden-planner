"""Shared helper for assigning a database species to an existing plant item.

Used by both the plant database panel (Load Custom / Create Custom) and the
Plants-menu species search so that every "assign species to an existing plant"
path behaves identically (issue #213):

  * writes ``metadata['plant_species']``;
  * resizes the drawn footprint so its diameter equals the species'
    ``max_spread_cm`` (the visible change the issue requires) — silently, unless
    a manual ``spacing_radius_cm`` override conflicts, in which case the user is
    prompted to apply the database values or keep their custom ones;
  * records a single undoable step (``ApplySpeciesCommand``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QGraphicsItem, QMessageBox, QWidget

from open_garden_planner.core.commands import ApplySpeciesCommand
from open_garden_planner.core.plant_sizing import db_spacing_radius_cm

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
    confirm: Callable[[], bool] | None = None,
) -> None:
    """Assign ``species_dict`` to ``plant_item`` (undoable + repaints canvas).

    Args:
        plant_item: The plant item to update (CircleItem).
        species_dict: The species record to assign (already merged via
            ``merge_calendar_data``).
        confirm: Callable returning True to apply database values when a manual
            ``spacing_radius_cm`` override conflicts with the database. Required
            for the prompt to fire; when None a conflicting override is preserved.

    The drawn footprint is resized so its diameter equals the species'
    ``max_spread_cm`` — silently in the common case (no conflicting manual
    spacing override). Only a manual override that disagrees with the database
    triggers the prompt: "apply" clears the override and resizes the footprint;
    "keep" preserves both the override and the placed size. Either way
    ``metadata['plant_species']`` is updated. The neighbour-collision *overlap*
    indicator is recomputed separately by the main window's
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
    # max_spread_cm / 2 (resolved by the single sizing helper, #218).
    db_radius = db_spacing_radius_cm(species_dict)

    # Default: leave the placed footprint and the override untouched.
    new_override = old_override
    new_radius = old_radius

    # A manual spacing override that disagrees with the database is the only
    # "custom value" we ask about (the footprint resize itself is silent).
    override_conflicts = (
        db_radius is not None
        and old_override is not None
        and abs(old_override - db_radius) > _SPACING_EPSILON_CM
    )

    if db_radius is not None:
        if override_conflicts:
            # Ask before discarding the manual override. "Keep" leaves the
            # override and the placed footprint exactly as they are.
            if confirm is not None and confirm():
                new_radius = db_radius  # drawn circle adopts the real plant size
                new_override = None  # let the database spacing cascade win
        else:
            # No conflicting override → silently adopt the database footprint.
            new_radius = db_radius

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
    cmd_mgr = (
        scene.get_command_manager()
        if scene is not None and hasattr(scene, "get_command_manager")
        else None
    )
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
