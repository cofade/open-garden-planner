"""#415 end-to-end: the propagation editor's persisted step dates.

The widget-level counterpart to ``tests/unit/test_propagation_editor_years.py``.
That file pins the model-side rules Qt-free; this one drives the real
``_DetailPanel`` through real ``QDateEdit``s and asserts what lands in the
project's ``propagation_overrides`` — the dict that is serialized into the
``.ogp`` — because that is where master wrote the inverted pair.

Observed failing on master before the fix:
  * a step crossing New Year was stored ``start 2026-12-24 / end 2026-01-22``;
  * a step in another calendar year moved into the current one;
  * the ``29 Feb`` edge stretched or inverted depending on leap-ness.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import datetime

import pytest
from PyQt6.QtCore import QDate

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.propagation import PropagationStep, compute_propagation_plan
from open_garden_planner.ui.views.planting_calendar_view import _DetailPanel

_SPECIES = PlantSpeciesData(
    scientific_name="Solanum lycopersicum",
    common_name="Tomato",
    source_id="12345",
    indoor_sow_start=-8,
    indoor_sow_end=-6,
    transplant_start=4,
)

TODAY = datetime.date(2026, 1, 5)


def _plan(sow_start: datetime.date, sow_end: datetime.date):
    return compute_propagation_plan(
        species_key="solanum_lycopersicum",
        sow_start=sow_start,
        sow_end=sow_end,
        transplant_date=datetime.date(2026, 6, 1),
    )


def _panel(qtbot) -> _DetailPanel:
    panel = _DetailPanel()
    qtbot.addWidget(panel)
    panel.set_show_propagation(True)
    return panel


def _editors(panel: _DetailPanel, step_id: str) -> tuple[QDate, QDate]:
    start_edit, end_edit, _reset = panel._step_rows[step_id]
    assert end_edit is not None
    return start_edit.date(), end_edit.date()


def _step_editor_dates(panel: _DetailPanel, step_id: str) -> tuple[datetime.date, datetime.date]:
    s, e = _editors(panel, step_id)
    return datetime.date(s.year(), s.month(), s.day()), datetime.date(e.year(), e.month(), e.day())


class TestEditorShowsRealDates:
    def test_step_in_another_year_shows_its_own_year(self, qtbot) -> None:
        """Master moved a Nov/Dec 2025 step into 2026 when today was 2026-01-05."""
        panel = _panel(qtbot)
        plan = _plan(datetime.date(2025, 12, 24), datetime.date(2026, 1, 21))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        start, end = _step_editor_dates(panel, "indoor_sow")
        assert start == datetime.date(2025, 12, 24)
        assert end == datetime.date(2026, 1, 21)

    def test_crossing_new_year_stays_ordered(self, qtbot) -> None:
        """The exact inversion master stored: start 2026-12-24, end 2026-01-22."""
        panel = _panel(qtbot)
        plan = _plan(datetime.date(2026, 12, 24), datetime.date(2027, 1, 22))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        start, end = _step_editor_dates(panel, "indoor_sow")
        assert start == datetime.date(2026, 12, 24)
        assert end == datetime.date(2027, 1, 22)
        assert end >= start

    @pytest.mark.parametrize("leap", [True, False], ids=["leap", "non_leap"])
    def test_29_february_edge_shows_real_dates(self, qtbot, leap: bool) -> None:
        """Master's ``except ValueError`` kept the real year for the 29-Feb date
        while the other date moved into today's year, stretching the step."""
        panel = _panel(qtbot)
        year = 2028 if leap else 2024
        plan = _plan(datetime.date(year, 2, 20), datetime.date(year, 2, 29))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        start, end = _step_editor_dates(panel, "indoor_sow")
        assert start == datetime.date(year, 2, 20)
        assert end == datetime.date(year, 2, 29)


class TestEditorPersistsWhatTheUserSaw:
    def _commit_via_signal(self, panel: _DetailPanel, stored: list[tuple]) -> None:
        """Drive the panel's commit path the way the view wires it.

        ``_DetailPanel`` emits ``step_date_changed``; the view slot persists it.
        Capturing the emission is enough to assert the ISO pair that WOULD be
        written, which is the value master got wrong.
        """
        panel.step_date_changed.connect(
            lambda key, sid, start, end: stored.append((key, sid, start, end))
        )

    def test_editing_end_does_not_move_the_start_year(self, qtbot) -> None:
        panel = _panel(qtbot)
        plan = _plan(datetime.date(2025, 12, 24), datetime.date(2026, 1, 21))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        stored: list[tuple] = []
        self._commit_via_signal(panel, stored)

        # Move the END forward by one day, exactly as the issue reports.
        start_edit, end_edit, _reset = panel._step_rows["indoor_sow"]
        end_edit.setDate(QDate(2026, 1, 22))
        panel._flush_pending_step()

        assert stored == [("solanum_lycopersicum", "indoor_sow", "2025-12-24", "2026-01-22")]
        start_iso, end_iso = stored[0][2], stored[0][3]
        assert datetime.date.fromisoformat(end_iso) >= datetime.date.fromisoformat(start_iso)

    def test_a_reset_does_not_leave_a_pending_write_behind(self, qtbot) -> None:
        """A pending debounce must not fire after the step is reset (#415)."""
        panel = _panel(qtbot)
        # The step carries a real override, so the reset button is enabled (it
        # is disabled for a calculated-only step and would swallow the click).
        plan = compute_propagation_plan(
            species_key="solanum_lycopersicum",
            sow_start=datetime.date(2025, 12, 24),
            sow_end=datetime.date(2026, 1, 21),
            transplant_date=datetime.date(2026, 6, 1),
            overrides={"indoor_sow": {"start": "2025-12-24", "end": "2026-01-21"}},
        )
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        stored: list[tuple] = []
        panel.step_date_changed.connect(
            lambda key, sid, start, end: stored.append((key, sid, start, end))
        )
        resets: list[tuple] = []
        panel.step_date_reset.connect(lambda key, sid: resets.append((key, sid)))

        start_edit, _end, reset_btn = panel._step_rows["indoor_sow"]
        assert reset_btn.isEnabled() is True
        start_edit.setDate(QDate(2025, 12, 25))       # arms the debounce
        assert panel._pending_step_id == "indoor_sow"
        reset_btn.click()                              # reset wins

        assert resets == [("solanum_lycopersicum", "indoor_sow")]
        panel._flush_pending_step()
        assert stored == [], "the superseded edit must not be written after a reset"


class TestAlreadySavedInvertedOverride:
    def test_plan_with_a_stored_inversion_shows_calculated_dates(self, qtbot) -> None:
        """A plan saved by the buggy build must display sane dates, not the inversion."""
        panel = _panel(qtbot)
        inverted = {"start": "2026-12-24", "end": "2026-01-22"}
        plan = compute_propagation_plan(
            species_key="solanum_lycopersicum",
            sow_start=datetime.date(2025, 11, 20),
            sow_end=datetime.date(2025, 12, 4),
            transplant_date=datetime.date(2026, 6, 1),
            overrides={"indoor_sow": inverted},
        )
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        start, end = _step_editor_dates(panel, "indoor_sow")
        assert start == datetime.date(2025, 11, 20)
        assert end == datetime.date(2025, 12, 4)
        # The reset button reflects "not overridden", so the user can tell the
        # stored custom date is being ignored rather than applied.
        _s, _e, reset_btn = panel._step_rows["indoor_sow"]
        assert reset_btn.isEnabled() is False

    def test_point_step_start_equals_end_is_not_rejected(self) -> None:
        plan = compute_propagation_plan(
            species_key="x",
            sow_start=datetime.date(2026, 3, 1),
            sow_end=datetime.date(2026, 3, 10),
            transplant_date=datetime.date(2026, 5, 1),
            overrides={"transplant": {"start": "2026-05-02", "end": "2026-05-02"}},
        )
        step = plan.get_step("transplant")
        assert isinstance(step, PropagationStep)
        assert step.overridden is True


class TestPersistedProjectRoundTrip:
    def test_inverted_override_survives_save_and_load_without_being_applied(self, qtbot) -> None:
        """The stored value is preserved in the .ogp; only its use is refused.

        Destroying the user's file content on load would be worse than ignoring
        it, so this asserts both halves: the value round-trips verbatim AND the
        computed plan ignores it.
        """
        pm = ProjectManager()
        pm.set_propagation_override("solanum_lycopersicum", "indoor_sow", "2026-12-24", "2026-01-22")

        assert pm.propagation_overrides["solanum_lycopersicum"]["indoor_sow"] == {
            "start": "2026-12-24",
            "end": "2026-01-22",
        }

        plan = compute_propagation_plan(
            species_key="solanum_lycopersicum",
            sow_start=datetime.date(2025, 11, 20),
            sow_end=datetime.date(2025, 12, 4),
            transplant_date=datetime.date(2026, 6, 1),
            overrides=pm.propagation_overrides.get("solanum_lycopersicum", {}),
        )
        step = plan.get_step("indoor_sow")
        assert step is not None
        assert step.overridden is False
        assert step.start_date == datetime.date(2025, 11, 20)