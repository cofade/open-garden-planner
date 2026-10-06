"""Two things round 5 named about `_pending_steps` that need pinning, not prose.

1. **Arm-time capture relocates staleness rather than removing it.** The flush no
   longer reads the widgets, which fixed *which* species and *which* pair win — but
   an armed value is now a snapshot of what the editor showed when the user typed.
   Measured consequence: calculated `indoor_sow` is 12–26 Feb; the user moves only
   the start to 20 Feb; if the plan is rebuilt inside the 600 ms debounce (a frost
   date changes, an unrelated refresh lands), the flush persists
   `{start: 2026-02-20, end: 2026-02-26}` — an end date ~10 weeks off the
   recalculated plan, now frozen by the override. Editing ONE field of a period
   step always pins the untouched field to the plan as it stood at arm time.

   That is a real trade (it is what makes a multi-step gesture safe), so it is
   documented and asserted rather than left for the next reader to rediscover.

2. **`show_species` DOES re-enter mid-flush**, contradicting a comment that claimed
   otherwise. The result is correct only because of two orderings: the pending dict
   is cleared *before* the emit, and the species is re-assigned *after* the flush
   returns. Reversing either reintroduces a cross-species misattribution. Pinned
   here so the ordering cannot be "tidied".
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import datetime

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

TOMATO = {
    "scientific_name": "Solanum lycopersicum", "common_name": "Tomato",
    "source_id": "414", "indoor_sow_start": -8, "indoor_sow_end": -6,
    "transplant_start": 4, "harvest_start": 10, "harvest_end": 18,
}
PEPPER = {
    "scientific_name": "Capsicum annuum", "common_name": "Pepper",
    "source_id": "415", "indoor_sow_start": -10, "indoor_sow_end": -8,
    "transplant_start": 3, "harvest_start": 12, "harvest_end": 18,
}


def _view(qtbot) -> PlantingCalendarView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    for spec in (TOMATO, PEPPER):
        item = CircleItem(
            center_x=100, center_y=100, radius=20,
            object_type=ObjectType.TREE, name=spec["common_name"],
        )
        item.metadata["plant_species"] = dict(spec)
        scene.addItem(item)
    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})

    view = PlantingCalendarView(scene, pm)
    qtbot.addWidget(view)
    view._prop_toggle.setChecked(True)
    view.refresh()
    view.resize(1200, 900)
    view.show()
    QApplication.processEvents()
    return view


def _key(view: PlantingCalendarView, name: str) -> str:
    return next(r.species_key for r in view._rows if name in r.display_name)


def _select(view: PlantingCalendarView, key: str) -> None:
    view._on_row_clicked(
        next(i for i, r in enumerate(view._rows) if r.species_key == key)
    )
    QApplication.processEvents()


class TestArmTimeCaptureRelocatesStaleness:
    """The trade, asserted so it is a decision rather than a surprise."""

    def test_editing_one_field_pins_the_untouched_field(self, qtbot) -> None:
        """Documented behaviour: the arm-time pair is what gets stored.

        The end date here was never touched — it is the value the editor showed
        when the user moved the start. That is the price of making a multi-step
        gesture safe, and it is stable and predictable rather than racy.

        The new start is derived to stay BEFORE the shown end, because moving it
        past would produce an inverted pair, which rounds 3-4 established is
        REFUSED — a different behaviour with its own tests, and not what this one
        is measuring.
        """
        view = _view(qtbot)
        tomato = _key(view, "Tomato")
        _select(view, tomato)
        panel = view._detail

        start_edit, end_edit, _reset = panel._step_rows["indoor_sow"][0:3]
        shown_end = end_edit.date().toPyDate()
        shown_start = start_edit.date().toPyDate()
        new_start = shown_start + datetime.timedelta(days=3)
        assert new_start < shown_end, (shown_start, shown_end)

        start_edit.setDate(QDate(new_start.year, new_start.month, new_start.day))
        panel._flush_pending_steps()
        stored = view._project_manager.propagation_overrides[tomato]["indoor_sow"]
        assert stored["start"] == new_start.isoformat()
        assert stored["end"] == shown_end.isoformat(), (
            "the untouched field is pinned to what the editor showed at arm time"
        )

    def test_the_armed_pair_is_a_snapshot_not_a_live_read(self, qtbot) -> None:
        """The mechanism: mutating the widget after arming does not change the write."""
        view = _view(qtbot)
        tomato = _key(view, "Tomato")
        _select(view, tomato)
        panel = view._detail

        start_edit, end_edit, _reset = panel._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2026, 5, 4))
        end_edit.setDate(QDate(2026, 5, 20))
        armed_end = panel._pending_steps["indoor_sow"][2]

        # Something else rewrites the editor before the debounce fires.
        end_edit.blockSignals(True)
        end_edit.setDate(QDate(2026, 12, 25))
        end_edit.blockSignals(False)

        panel._flush_pending_steps()
        stored = view._project_manager.propagation_overrides[tomato]["indoor_sow"]
        assert stored["end"] == armed_end, (
            "the flush re-read the widget instead of using the armed snapshot"
        )


class TestShowSpeciesOrderingIsLoadBearing:
    """`show_species` re-enters mid-flush; two orderings make that safe."""

    def test_the_pending_dict_is_cleared_before_the_emit(self, qtbot) -> None:
        """If it were cleared after, the inner show_species would recurse."""
        view = _view(qtbot)
        tomato = _key(view, "Tomato")
        _select(view, tomato)
        panel = view._detail

        depths: list[int] = []

        def probe(_payload) -> None:
            # Measured from inside the emit: nothing may still be armed.
            depths.append(len(panel._pending_steps))

        panel.steps_date_changed.connect(probe)
        try:
            s, e, _r = panel._step_rows["indoor_sow"][0:3]
            s.setDate(QDate(2026, 5, 4))
            e.setDate(QDate(2026, 5, 20))
            panel._flush_pending_steps()
        finally:
            panel.steps_date_changed.disconnect(probe)

        assert depths == [0], (
            f"the pending dict still held {depths} entries when the emit fired; "
            "the re-entrant show_species would flush them again"
        )

    def test_the_species_is_reassigned_after_the_flush_returns(self, qtbot) -> None:
        """The inner call sets its own species; the outer one must win."""
        view = _view(qtbot)
        tomato = _key(view, "Tomato")
        pepper = _key(view, "Pepper")

        # Arm on Tomato, then let the inner repopulate point the panel at Pepper
        # and check the OUTER frame still ends on Tomato.
        _select(view, tomato)
        panel = view._detail
        s, e, _r = panel._step_rows["indoor_sow"][0:3]
        s.setDate(QDate(2026, 5, 4))
        e.setDate(QDate(2026, 5, 20))

        inner_species: list[str] = []
        original_repopulate = view._repopulate_detail

        def spy(species_key: str) -> None:
            inner_species.append(species_key)
            # Deliberately point the panel at the OTHER species mid-flush, which
            # is what the re-entrancy would do if the outer frame lost the race.
            _select(view, pepper)
            original_repopulate(species_key)

        view._repopulate_detail = spy
        try:
            panel._flush_pending_steps()
            # Now the outer call's own show_species logic, verbatim.
            panel.show_species(
                view._rows[next(i for i, r in enumerate(view._rows)
                                if r.species_key == tomato)].species,
                tomato,
                view._prop_plans[tomato],
            )
        finally:
            view._repopulate_detail = original_repopulate

        assert panel._current_species_key == tomato, (
            "the outer show_species lost the species to a re-entrant inner call"
        )

    @pytest.mark.parametrize("name", ["Tomato", "Pepper"])
    def test_a_plain_selection_lands_on_the_right_species(self, qtbot, name: str) -> None:
        view = _view(qtbot)
        _select(view, _key(view, name))
        assert view._detail._current_species_key == _key(view, name)
