"""Cached sun evaluations, badges and canopy grouping; never launches work."""

import contextlib
import weakref
from dataclasses import asdict
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsPixmapItem

from open_garden_planner.core.guild_commands import guild_plant_bounds
from open_garden_planner.core.object_types import ObjectType, is_plant_type
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.sun_mismatch_service import (
    MEASUREMENT_METHOD,
    CanopyPlant,
    SunEvaluation,
    canopy_members,
    classify_mismatch,
    evaluate_sun,
)
from open_garden_planner.ui.canvas.sun_badge_placement import badge_rectangle, plant_footprint
from open_garden_planner.ui.canvas.sun_exposure_snapshot import collect_exposure_snapshot
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.icons import get_pixmap
from open_garden_planner.ui.plant_traits import species_display_name
from open_garden_planner.ui.sun_exposure_text import mismatch_message, unavailable_message
from open_garden_planner.ui.theme import register_theme_listener, unregister_theme_listener


class SunExposureCoordinator(QObject):
    def __init__(self, scene: Any, heatmap: SunHeatmapController, clock: SimClock,
                 project_manager: Any, toolbar: Any, canopy_panel: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene, self.heatmap, self.clock = scene, heatmap, clock
        self.project_manager, self.toolbar, self.canopy_panel = project_manager, toolbar, canopy_panel
        self.evaluations: dict[str, SunEvaluation] = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        scene.changed.connect(self.schedule)
        scene.selectionChanged.connect(self.schedule)
        scene.document_replaced.connect(self.reset)
        heatmap.exposure_changed.connect(self.schedule)
        project_manager.location_changed.connect(self.schedule)
        clock.date_changed.connect(self.schedule)
        # Non-Qt registries outlive the QObject. A weak callback plus an
        # external destruction closure cannot retain a deleted coordinator.
        reference = weakref.ref(self)
        def theme_listener(*_args: Any) -> None:
            coordinator = reference()
            if coordinator is not None:
                coordinator.schedule()
        register_theme_listener(theme_listener)
        subscriber = self.schedule
        def disconnect() -> None:
            # Cyclic Python collection can prune Channel's weak receiver
            # before Qt emits destroyed. Teardown is idempotent in that case.
            with contextlib.suppress(ValueError):
                clock.date_changed.disconnect(subscriber)
            unregister_theme_listener(theme_listener)
        self.destroyed.connect(disconnect)
        self.schedule()

    def reset(self) -> None:
        self.timer.stop()
        self.evaluations = {}
        self.canopy_panel.set_members(None, [], {})
        self.toolbar.set_exposure_hint(unavailable_message("absent"))

    def schedule(self, *_args: Any) -> None:
        with contextlib.suppress(RuntimeError):
            if not self.timer.isActive():
                self.timer.start(60)

    def refresh(self) -> None:
        with contextlib.suppress(RuntimeError):
            self._refresh()

    def _refresh(self) -> None:
        location = self.project_manager.location
        snapshot = collect_exposure_snapshot(self.scene, location, self.clock.plan_date)
        if self.heatmap.snapshot is not None and snapshot != self.heatmap.snapshot:
            self.heatmap.invalidate_exposure()
        reason = self.heatmap.exposure_reason
        if snapshot.latitude is None or snapshot.longitude is None:
            reason = "no_location"
        hint = "" if reason == "ready" else unavailable_message(reason)
        self.toolbar.set_exposure_hint(hint)
        self.heatmap.set_exposure_hint(hint)
        plants = [item for item in self.scene.items() if hasattr(item, "item_id") and hasattr(item, "object_type")
                  and is_plant_type(item.object_type)]
        diagnostics = []
        evaluations = {}
        canopy_plants = []
        species_snapshots = {}
        for plant in plants:
            if not plant.isVisible():
                self._badge(plant, None, "")
                continue
            identity = str(plant.item_id)
            species = plant.metadata.get("plant_species")
            species = species if isinstance(species, dict) else {}
            species_snapshots[identity] = species
            name = plant.name or species_display_name(species)
            geometry = guild_plant_bounds(plant)
            centre = plant.mapToScene(geometry.center())
            canopy_plants.append(CanopyPlant(identity, name, centre.x(), centre.y(), species.get("permaculture_layer", "unknown")))
            minutes = self.heatmap.receiver_minutes.get(identity) if reason == "ready" else None
            unavailable = ("hidden" if not plant.isVisible() else "out_of_grid") if reason == "ready" else reason
            evaluation = evaluate_sun(identity, species.get("sun_requirement"), minutes, self.clock.plan_date, reason=unavailable)
            evaluations[identity] = evaluation
            mismatch = classify_mismatch(evaluation)
            root = plant
            while root.parentItem() is not None and hasattr(root.parentItem(), "item_id"):
                root = root.parentItem()
            details = {"receiver_id": identity, "required": evaluation.required.value,
                       "reference_date": evaluation.reference_date.isoformat(), "hours": evaluation.hours,
                       "measurement_method": MEASUREMENT_METHOD,
                       "label": plant.name or species.get("common_name") or species.get("scientific_name") or identity,
                       "label_is_species": not bool(plant.name)}
            if mismatch is not None:
                details["direction"] = mismatch.direction
                diagnostics.append({"kind": "sun_mismatch", "severity": "warning", "item_ids": [str(root.item_id)],
                                    "message": f"{details['label']} receives {mismatch.hours:.1f} h direct sun on {evaluation.reference_date.isoformat()} "
                                               f"({mismatch.direction}; requires {evaluation.required.value}).", "details": details})
            elif evaluation.hours is None and evaluation.required != SunRequirement.UNKNOWN:
                details["status"] = "not_evaluated"
                details["reason"] = evaluation.reason
                diagnostics.append({"kind": "sun_evaluation", "severity": "info", "item_ids": [str(root.item_id)],
                                    "message": f"Sun exposure has not been evaluated ({evaluation.reason}).", "details": details})
            self._badge(plant, mismatch, name)
        self.evaluations = evaluations
        if getattr(self.scene, "_sun_diagnostics", []) != diagnostics:
            self.scene._sun_diagnostics = diagnostics
            self.scene.diagnostics_changed.emit()
        selected = self.scene.selectedItems()
        tree = selected[0] if len(selected) == 1 and getattr(selected[0], "object_type", None) == ObjectType.TREE else None
        if tree is None:
            self.canopy_panel.set_members(None, [], {})
        else:
            centre = tree.mapToScene(guild_plant_bounds(tree).center())
            species = species_snapshots[str(tree.item_id)]
            members = canopy_members(str(tree.item_id), (centre.x(), centre.y()), species.get("max_spread_cm"), canopy_plants)
            self.canopy_panel.set_members(str(tree.item_id), members, evaluations)

    @staticmethod
    def _badge(plant: Any, mismatch: Any, name: str) -> None:
        badge = getattr(plant, "_sun_badge", None)
        if mismatch is None:
            if badge is not None and badge.isVisible():
                badge.setVisible(False)
            return
        pixmap = get_pixmap("sun_warning", 24)
        if pixmap is None:
            return
        tooltip = mismatch_message(name, mismatch.required, mismatch.hours, mismatch.reference_date, mismatch.direction)
        footprint = plant_footprint(plant)
        signature = (asdict(mismatch), tooltip, footprint, pixmap.cacheKey())
        if getattr(plant, "_sun_badge_signature", None) == signature and badge is not None and badge.isVisible():
            return
        plant._sun_badge_signature = signature
        rectangle = badge_rectangle(footprint)
        if rectangle is None:
            if badge is not None:
                badge.setVisible(False)
            return
        if badge is None:
            badge = QGraphicsPixmapItem(plant)
            badge.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            badge.setZValue(100)
            # The canvas is Y-up. Flip the icon's pixel frame once.
            badge.setTransform(QTransform().scale(1, -1))
            plant._sun_badge = badge
        badge.setPixmap(pixmap)
        size = rectangle.width()
        badge.setScale(size / 24)
        badge.setPos(rectangle.left(), rectangle.bottom())
        badge.setToolTip(tooltip)
        badge.setVisible(True)
