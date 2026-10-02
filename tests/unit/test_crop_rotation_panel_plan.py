"""Unit tests for the crop-rotation panel's succession-plan section (issue #378).

The panel must show a bed's succession plan as **planned this season**, kept
separate from the rotation history, and must not change `CropRotationService`'s
advice. These tests use a stub project manager so they need no real document.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtWidgets import QWidget

from open_garden_planner.services.crop_rotation_service import CropRotationService
from open_garden_planner.ui.panels.crop_rotation_panel import CropRotationPanel


class _Emitter:
    """Minimal stand-in for a pyqtSignal: records connect() calls."""

    def __init__(self) -> None:
        self._slots: list[Any] = []

    def connect(self, slot: Any) -> None:
        self._slots.append(slot)

    def emit(self, *args: object) -> None:
        for slot in list(self._slots):
            slot(*args)


class _StubProjectManager:
    """Project-manager stand-in exposing only ``succession_plans``."""

    def __init__(self, plans: dict[str, Any] | None = None) -> None:
        self.succession_plans: dict[str, Any] = plans or {}
        self.succession_plans_changed = _Emitter()


def _plan_dict(bed_id: str, *, species: str, common: str, scientific: str) -> dict[str, Any]:
    return {
        "bed_id": bed_id,
        "year": 2026,
        "entries": [
            {
                "id": "e1",
                "species_key": species,
                "common_name": common,
                "scientific_name": scientific,
                "start_date": "2026-04-01",
                "end_date": "2026-06-01",
            }
        ],
    }


class _Bed:
    def __init__(self, name: str = "Bed A") -> None:
        self.name = name


def _make_panel(pm: _StubProjectManager | None) -> CropRotationPanel:
    panel = CropRotationPanel(CropRotationService())
    if pm is not None:
        panel.set_project_manager(pm)
    return panel


class TestSuccessionPlanSection:
    def test_plan_and_no_history_shows_section(self, qtbot: object) -> None:
        bed_id = "bed-1"
        pm = _StubProjectManager(
            {
                bed_id: _plan_dict(
                    bed_id,
                    species="solanum lycopersicum",
                    common="Tomato",
                    scientific="Solanum lycopersicum",
                )
            }
        )
        panel = _make_panel(pm)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]

        panel.update_for_bed(_Bed(), bed_id)

        assert panel._plan_header.isVisibleTo(panel)
        assert panel._plan_list.count() == 1
        # The explicit message replaces the bare "every crop is suitable".
        assert "planned crops" in panel._recommendation_label.text().lower()
        assert "suitable" not in panel._recommendation_label.text().lower()

    def test_plan_and_history_shows_both_sections(self, qtbot: object) -> None:
        from open_garden_planner.models.crop_rotation import PlantingRecord

        bed_id = "bed-2"
        pm = _StubProjectManager(
            {
                bed_id: _plan_dict(
                    bed_id,
                    species="solanum lycopersicum",
                    common="Tomato",
                    scientific="Solanum lycopersicum",
                )
            }
        )
        panel = _make_panel(pm)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel._service.history.add_record(
            PlantingRecord(
                year=2024,
                season="spring",
                species_name="Solanum lycopersicum",
                common_name="Tomato",
                family="Solanaceae",
                nutrient_demand="heavy",
                area_id=bed_id,
            )
        )

        panel.update_for_bed(_Bed(), bed_id)

        assert panel._plan_header.isVisibleTo(panel)
        assert panel._history_list.count() >= 1
        # With history the standard recommendation wording is used, not the gap note.
        assert "cannot see" not in panel._recommendation_label.text().lower()

    def test_no_plan_hides_section(self, qtbot: object) -> None:
        panel = _make_panel(_StubProjectManager({}))
        qtbot.addWidget(panel)  # type: ignore[attr-defined]

        panel.update_for_bed(_Bed(), "bed-3")

        assert not panel._plan_header.isVisibleTo(panel)
        assert panel._plan_list.count() == 0

    def test_unresolvable_species_still_lists_row(self, qtbot: object) -> None:
        bed_id = "bed-4"
        pm = _StubProjectManager(
            {
                bed_id: _plan_dict(
                    bed_id,
                    species="some api plant",
                    common="API Plant",
                    scientific="Nonexistentum apii",
                )
            }
        )
        panel = _make_panel(pm)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]

        panel.update_for_bed(_Bed(), bed_id)

        assert panel._plan_list.count() == 1
        assert "family unknown" in panel._plan_list.item(0).text().lower()

    def test_no_project_manager_is_safe(self, qtbot: object) -> None:
        panel = _make_panel(None)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.update_for_bed(_Bed(), "bed-5")
        assert not panel._plan_header.isVisibleTo(panel)

    def test_clearing_bed_hides_section(self, qtbot: object) -> None:
        bed_id = "bed-6"
        pm = _StubProjectManager(
            {
                bed_id: _plan_dict(
                    bed_id,
                    species="solanum lycopersicum",
                    common="Tomato",
                    scientific="Solanum lycopersicum",
                )
            }
        )
        panel = _make_panel(pm)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.update_for_bed(_Bed(), bed_id)
        assert panel._plan_header.isVisibleTo(panel)

        panel.update_for_bed(None, None)
        assert not panel._plan_header.isVisibleTo(panel)


class TestRotationAdviceUnchanged:
    def test_service_advice_is_identical_with_a_plan(self, qtbot: object) -> None:
        """The plan must NOT feed into get_recommendation (option 2 rejected)."""
        bed_id = "bed-7"
        service = CropRotationService()
        before = service.get_recommendation(bed_id)

        pm = _StubProjectManager(
            {
                bed_id: _plan_dict(
                    bed_id,
                    species="solanum lycopersicum",
                    common="Tomato",
                    scientific="Solanum lycopersicum",
                )
            }
        )
        panel = CropRotationPanel(service)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_project_manager(pm)
        panel.update_for_bed(_Bed(), bed_id)

        after = service.get_recommendation(bed_id)
        assert before.status == after.status
        assert before.suggested_demand == after.suggested_demand
        assert before.avoid_families == after.avoid_families

    def test_signal_rerenders_the_panel(self, qtbot: object) -> None:
        bed_id = "bed-8"
        pm = _StubProjectManager({})
        panel = _make_panel(pm)
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.update_for_bed(_Bed(), bed_id)
        assert not panel._plan_header.isVisibleTo(panel)

        pm.succession_plans[bed_id] = _plan_dict(
            bed_id,
            species="solanum lycopersicum",
            common="Tomato",
            scientific="Solanum lycopersicum",
        )
        pm.succession_plans_changed.emit(pm.succession_plans)

        assert panel._plan_header.isVisibleTo(panel)
