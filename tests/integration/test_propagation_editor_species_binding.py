"""#415 round 3: the propagation editor must never write to the wrong plant.

Three defects the previous two rounds' tests could not see, because none of them
changed species mid-gesture and the two-file wiring was bypassed:

1. **Cross-species misattribution.** The flush ran from ``_populate_prop_editor``,
   which ``show_species`` calls *after* reassigning ``_current_species_key`` — so
   an armed edit was persisted against the species the user had just clicked ONTO.
   Measured before the fix, with Tomato and Pepper both carrying propagation data:
   arming ``indoor_sow`` on Tomato and clicking Pepper's chart row produced
   ``{'415': {'indoor_sow': {...}}}`` — Pepper's key, Tomato's dates, written to
   the ``.ogp``. It round-trips.
2. **Silent discard.** The armed set was cleared *before* the guards, so an edit
   was destroyed when the newly selected species had no propagation plan.
3. **A value the user never entered.** Clamping an inverted pair to
   ``end = start`` persisted a zero-length period. That is the DEFAULT path for
   moving one field of a period step, so it silently rewrote an untouched end
   date on an ordinary edit.

The species key is now captured when the edit is *armed*, and ``show_species``
flushes before it swaps state.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import pytest
from PyQt6.QtCore import QDate

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

# Two species with different propagation windows, so a mix-up is visible.
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


def _view(qtbot) -> tuple[PlantingCalendarView, str, str]:
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

    rows = {r.species_key: r for r in view._rows}
    tomato = next(k for k in rows if "Tomato" in rows[k].display_name)
    pepper = next(k for k in rows if "Pepper" in rows[k].display_name)
    return view, tomato, pepper


def _select(view: PlantingCalendarView, key: str) -> None:
    idx = next(i for i, r in enumerate(view._rows) if r.species_key == key)
    view._on_row_clicked(idx)


def _arm(view: PlantingCalendarView, step_id: str, start: QDate, end: QDate) -> None:
    start_edit, end_edit, _reset = view._detail._step_rows[step_id][0:3]
    start_edit.setDate(start)
    end_edit.setDate(end)


class TestEditsAreNotMisattributed:
    def test_an_armed_edit_keeps_its_own_species_when_another_row_is_clicked(
        self, qtbot
    ) -> None:
        """The P0: the edit was written under the newly selected species' key."""
        view, tomato, pepper = _view(qtbot)
        _select(view, tomato)
        _arm(view, "indoor_sow", QDate(2026, 5, 4), QDate(2026, 5, 20))

        _select(view, pepper)          # the user clicks Pepper's chart row

        overrides = view._project_manager.propagation_overrides
        assert pepper not in overrides, (
            f"Tomato's edit was persisted against Pepper ({overrides}) — this is "
            "cross-species corruption in the .ogp"
        )
        assert overrides.get(tomato, {}).get("indoor_sow") == {
            "start": "2026-05-04", "end": "2026-05-20",
        }, overrides

    def test_switching_species_never_loses_the_armed_edit(self, qtbot) -> None:
        view, tomato, pepper = _view(qtbot)
        _select(view, tomato)
        _arm(view, "harden_off", QDate(2026, 6, 1), QDate(2026, 6, 20))

        _select(view, pepper)

        stored = view._project_manager.propagation_overrides.get(tomato, {})
        assert stored.get("harden_off") == {"start": "2026-06-01", "end": "2026-06-20"}, stored

    def test_the_armed_key_is_captured_at_arm_time(self, qtbot) -> None:
        """The mechanism, asserted directly rather than through the outcome."""
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        view._detail._step_rows["indoor_sow"][0].setDate(QDate(2026, 5, 4))
        assert view._detail._pending_steps == {"indoor_sow": tomato}

    def test_switching_to_a_species_with_no_plan_keeps_the_edit(self, qtbot) -> None:
        """The silent-discard branch: the armed set was cleared before the guards."""
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        tomato = CircleItem(center_x=100, center_y=100, radius=20,
                            object_type=ObjectType.TREE, name="Tomato")
        tomato.metadata["plant_species"] = dict(TOMATO)
        scene.addItem(tomato)
        plain = CircleItem(center_x=300, center_y=300, radius=15,
                           object_type=ObjectType.TREE, name="Asparagus")
        # Has calendar fields, so it gets a CHART ROW, but no indoor_sow /
        # transplant offsets, so it gets NO propagation plan. That is the shape
        # that used to destroy the armed edit.
        plain.metadata["plant_species"] = {
            "scientific_name": "Asparagus officinalis", "common_name": "Asparagus",
            "source_id": "416", "harvest_start": 104, "harvest_end": 156,
        }
        scene.addItem(plain)

        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        view._prop_toggle.setChecked(True)
        view.refresh()

        key = next(k for k in view._prop_plans)
        _select(view, key)
        # BOTH dates, so the pair is valid: arming only a start past the
        # calculated end is correctly REFUSED (see the refusal tests below), which
        # would mask what this test is actually about.
        _arm(view, "indoor_sow", QDate(2026, 5, 4), QDate(2026, 5, 20))

        plain_idx = next(
            i for i, r in enumerate(view._rows)
            if "Asparagus" in r.display_name
        )
        view._on_row_clicked(plain_idx)

        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "indoor_sow"
        ) is not None, "the armed edit was silently discarded"


class TestAnImpossiblePairIsRefusedNotRewritten:
    def test_moving_one_field_past_the_other_stores_nothing(self, qtbot) -> None:
        """Moving only the START past the untouched end must not rewrite the end."""
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)

        start_edit, _end_edit, _reset = view._detail._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2027, 6, 1))     # far past the unchanged end
        view._detail._flush_pending_steps()

        overrides = view._project_manager.propagation_overrides.get(tomato, {})
        assert "indoor_sow" not in overrides, (
            f"an impossible pair was stored: {overrides}"
        )

    def test_the_editor_shows_the_real_dates_after_a_refusal(self, qtbot) -> None:
        """A refused date must not keep displaying as though it were saved."""
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        start_edit, _end, _reset = view._detail._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2027, 6, 1))
        view._detail._flush_pending_steps()

        shown = start_edit.date()
        assert (shown.year(), shown.month(), shown.day()) != (2027, 6, 1), (
            "the panel still shows the refused date as if it had been saved"
        )

    def test_a_refusal_is_reported(self, qtbot) -> None:
        """A silent refusal looks exactly like a lost edit."""
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        refused: list[tuple] = []
        view._detail.step_date_rejected.connect(
            lambda key, step_id: refused.append((key, step_id))
        )
        view._detail._step_rows["indoor_sow"][0].setDate(QDate(2027, 6, 1))
        view._detail._flush_pending_steps()
        assert refused == [(tomato, "indoor_sow")], refused

    def test_a_valid_pair_is_still_stored(self, qtbot) -> None:
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        _arm(view, "indoor_sow", QDate(2026, 5, 4), QDate(2026, 5, 20))
        view._detail._flush_pending_steps()
        assert view._project_manager.propagation_overrides[tomato]["indoor_sow"] == {
            "start": "2026-05-04", "end": "2026-05-20",
        }


class TestOneGestureIsOneRefresh:
    def test_a_multi_step_gesture_costs_a_single_refresh(self, qtbot, monkeypatch) -> None:
        """Invariant 4: one user gesture, not N heavyweight refreshes.

        The slot runs a full calendar refresh — scene walk, dashboard rebuild and
        a weather fetch — so emitting once per step made a single gesture cost one
        of those per step.
        """
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)

        calls: list[int] = []
        monkeypatch.setattr(
            type(view), "refresh", lambda _self: calls.append(1), raising=False
        )

        _arm(view, "indoor_sow", QDate(2026, 5, 4), QDate(2026, 5, 20))
        _arm(view, "harden_off", QDate(2026, 6, 1), QDate(2026, 6, 20))
        view._detail._flush_pending_steps()

        assert len(calls) == 1, f"one gesture triggered {len(calls)} refreshes"


class TestBatchedSignalShape:
    @pytest.mark.parametrize("step_id", ["indoor_sow", "germination", "harden_off"])
    def test_the_batch_carries_the_species_key_and_every_step(self, qtbot, step_id: str) -> None:
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        _arm(view, step_id, QDate(2026, 5, 4), QDate(2026, 5, 20))

        payloads: list[tuple] = []
        view._detail.steps_date_changed.connect(payloads.append)
        view._detail._flush_pending_steps()

        assert len(payloads) == 1
        species_key, writes = payloads[0]
        assert species_key == tomato
        assert [w[0] for w in writes] == [step_id]
        assert writes[0][1] == "2026-05-04" and writes[0][2] == "2026-05-20"

    def test_point_steps_commit_as_start_equals_end(self, qtbot) -> None:
        """``prick_out``/``transplant`` have no end editor; they must still commit."""
        view, tomato, _pepper = _view(qtbot)
        _select(view, tomato)
        payloads: list[tuple] = []
        view._detail.steps_date_changed.connect(payloads.append)

        edit = view._detail._step_rows["transplant"][0]
        assert view._detail._step_rows["transplant"][1] is None
        edit.setDate(QDate(2026, 6, 1))
        view._detail._flush_pending_steps()

        _species, writes = payloads[0]
        assert writes == [("transplant", "2026-06-01", "2026-06-01")], writes
