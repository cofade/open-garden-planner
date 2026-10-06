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


class _pinned_today:
    """Pin ``date.today()`` for the duration of the block.

    The 29-February case is defined by which year *today* is in: the old populate
    code rewrote the displayed dates to today's year, so the bug only appeared
    when today was not the step's own (leap) year.
    """

    def __init__(self, day: datetime.date) -> None:
        self._day = day
        self._real: object = None
        self._tg: object = None

    def __enter__(self) -> _pinned_today:
        import open_garden_planner.ui.views.planting_calendar_view as mod

        self._tg = mod
        self._real = mod.datetime.date

        class _Frozen(datetime.date):
            @classmethod
            def today(cls):  # type: ignore[override]
                return self._day

        mod.datetime.date = _Frozen
        return self

    def __exit__(self, *_exc) -> bool:
        self._tg.datetime.date = self._real  # type: ignore[attr-defined]
        return False


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

    @pytest.mark.parametrize("leap", [True, False], ids=["leap_today", "non_leap_today"])
    def test_29_february_edge_shows_real_dates(self, qtbot, leap: bool) -> None:
        """Master's ``except ValueError`` kept the real year for the 29-Feb date
        while the other date moved into today's year, stretching the step.

        The step's real 29-Feb date can only come from a leap ANCHOR year (2028);
        what varies is which year "today" is, because that is what the old code
        rewrote the displayed dates to. A 2024 anchor is NOT a non-leap case —
        2024 is a leap year.
        """
        panel = _panel(qtbot)
        today_year = 2028 if leap else 2027
        plan = _plan(
            datetime.date(2028, 2, 20), datetime.date(2028, 2, 29)
        )
        with _pinned_today(datetime.date(today_year, 3, 1)):
            panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        start, end = _step_editor_dates(panel, "indoor_sow")
        assert start == datetime.date(2028, 2, 20)
        assert end == datetime.date(2028, 2, 29)
        assert end >= start


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
        panel._flush_pending_steps()

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
        assert panel._pending_steps == {"indoor_sow"}
        reset_btn.click()                              # reset wins

        assert resets == [("solanum_lycopersicum", "indoor_sow")]
        panel._flush_pending_steps()
        assert stored == [], "the superseded edit must not be written after a reset"

    def test_two_steps_edited_in_quick_succession_are_both_written(self, qtbot) -> None:
        """A SET of pending steps, not one slot (#415 review).

        Correcting a step's start and then its end arms two steps; with a single
        pending slot the first edit was silently dropped.
        """
        panel = _panel(qtbot)
        plan = _plan(datetime.date(2025, 12, 24), datetime.date(2026, 1, 21))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        stored: list[tuple] = []
        panel.step_date_changed.connect(
            lambda _key, sid, start, end: stored.append((sid, start, end))
        )

        indoor_sow_start, indoor_sow_end, _ = panel._step_rows["indoor_sow"]
        germ_start, germ_end, _ = panel._step_rows["germination"]
        indoor_sow_start.setDate(QDate(2025, 12, 26))
        germ_end.setDate(QDate(2026, 1, 24))

        assert panel._pending_steps == {"indoor_sow", "germination"}
        panel._flush_pending_steps()

        assert sorted(sid for sid, _s, _e in stored) == ["germination", "indoor_sow"], stored

    def test_switching_species_flushes_an_armed_edit_instead_of_dropping_it(
        self, qtbot
    ) -> None:
        """Selecting another row must not silently discard the pending date.

        The Gantt has Qt::NoFocus, so clicking a chart row fires no
        ``editingFinished`` — the populate path is the only implicit commit.
        """
        panel = _panel(qtbot)
        plan = _plan(datetime.date(2025, 12, 24), datetime.date(2026, 1, 21))
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        stored: list[tuple] = []
        panel.step_date_changed.connect(
            lambda _key, sid, start, end: stored.append((sid, start, end))
        )

        start_edit, _end, _reset = panel._step_rows["indoor_sow"]
        start_edit.setDate(QDate(2025, 12, 27))
        assert panel._pending_steps == {"indoor_sow"}

        # Show a different species — exactly what _on_row_clicked does.
        panel.show_species(_SPECIES, "solanum_lycopersicum", plan)

        assert [s for s, _a, _b in stored] == ["indoor_sow"], (
            "the armed edit must be written before the editors are re-populated"
        )
        assert panel._pending_steps == set()


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
    def test_a_new_inverted_override_is_never_written(self) -> None:
        """The WRITE path refuses it, so a fresh save cannot contain one.

        The owner decision covers values that are ALREADY in a file: ignore them
        on read, keep the bytes. For a new write the stronger guarantee is
        simply not to store it, so the file never grows the problem.
        """
        pm = ProjectManager()
        pm.set_propagation_override(
            "solanum_lycopersicum", "indoor_sow", "2026-12-24", "2026-01-22"
        )
        assert pm.propagation_overrides == {}, (
            "an inverted pair must be refused at the write path"
        )

    def test_an_already_saved_inversion_is_ignored_but_left_on_disk(self) -> None:
        """Simulates a plan written by the buggy build, then read back.

        The stored value is PRESERVED — destroying the user's file content would
        be worse than ignoring it — while the computed plan refuses to use it.
        The value is injected directly rather than through
        ``set_propagation_override`` precisely because that writer now refuses it.
        """
        pm = ProjectManager()
        stored = {"start": "2026-12-24", "end": "2026-01-22"}
        pm._propagation_overrides = {  # noqa: SLF001 - simulating a legacy .ogp
            "solanum_lycopersicum": {"indoor_sow": dict(stored)}
        }

        assert pm.propagation_overrides["solanum_lycopersicum"]["indoor_sow"] == stored, (
            "the stored value must survive untouched"
        )

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
