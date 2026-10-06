"""#395/#415 drift guards that pin behaviour rather than prose.

Three things this covers, all of which a green suite had failed to catch:

1. **`_GANTT_COLORS` against the generator's own task-type list.** The map's
   source comment states the failure it exists to prevent: a generated type
   missing from the map is a task the dashboard lists and the chart silently
   omits. That is accurate — `_compute_gantt_windows` skips any type not in the
   map — but nothing pinned the map against the generator, so adding a generated
   type without a colour would be caught only by someone noticing a missing bar.
   Pinned here in both directions.

2. **The propagation commit is ONE write per gesture, and is not an undo step.**
   #415's text justified the commit batching with invariant 4 ("one user gesture is
   one undo step"), but a propagation override is written straight into
   `ProjectManager._propagation_overrides` and no `Command` reaches the
   `CommandManager`, so there is no undo entry at all. Rather than claim an undo
   step the code does not create, the documentation says what is true — one write
   and one refresh per gesture — and this fails if the claim is re-inflated.

   The batching is asserted through the PANEL (arming two steps and flushing
   yields one batch containing both), not by calling the writer twice, which would
   pass whether or not the UI batched anything.

3. **The anchor-year task-id shape** that ADR-029's Decision 3 depends on.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDate

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.task_generator import make_calendar_task_id
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import (
    _GANTT_COLORS,
    PlantingCalendarView,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

TOMATO = {
    "scientific_name": "Solanum lycopersicum", "common_name": "Tomato",
    "source_id": "414", "indoor_sow_start": -8, "indoor_sow_end": -6,
    "transplant_start": 4, "harvest_start": 10, "harvest_end": 18,
}


def _generated_task_types() -> set[str]:
    """Every task type the shared generator can emit for a calendar window."""
    from open_garden_planner.services import task_generator as tg

    defs = getattr(tg, "_CALENDAR_TASK_DEFS", None)
    assert defs is not None, (
        "task_generator no longer exposes _CALENDAR_TASK_DEFS, so this drift "
        "guard can no longer be derived — update it rather than deleting it"
    )
    return {task_type for task_type, *_rest in defs}


class TestGanttColoursTrackTheGenerator:
    def test_every_generated_task_type_has_a_colour(self) -> None:
        missing = _generated_task_types() - set(_GANTT_COLORS)
        assert not missing, (
            f"the generator produces {sorted(missing)} but the Gantt has no colour "
            "for them. `_compute_gantt_windows` skips types not in the map, so "
            "these would be listed on the dashboard and drawn NOWHERE on the "
            "chart — the silent omission the map's own comment warns about."
        )

    def test_the_colour_map_has_no_entries_for_types_that_cannot_occur(self) -> None:
        """The other direction: a stale entry hides a removed generator."""
        extra = set(_GANTT_COLORS) - _generated_task_types()
        assert not extra, (
            f"_GANTT_COLORS names {sorted(extra)}, which the generator no longer "
            "emits — a removed task type would leave its colour behind"
        )

    def test_colours_are_distinct(self) -> None:
        """Two task types sharing a colour is as invisible as a missing one."""
        seen: dict[str, str] = {}
        for task_type, colour in _GANTT_COLORS.items():
            key = colour.name() if hasattr(colour, "name") else str(colour)
            assert key not in seen, (
                f"{task_type!r} and {seen[key]!r} share the colour {key}"
            )
            seen[key] = task_type


def _view(qtbot) -> PlantingCalendarView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    item = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    item.metadata["plant_species"] = dict(TOMATO)
    scene.addItem(item)
    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
    view = PlantingCalendarView(scene, pm)
    qtbot.addWidget(view)
    view._prop_toggle.setChecked(True)
    view.refresh()
    view.resize(1200, 900)
    return view


def _select(view: PlantingCalendarView) -> str:
    key = next(iter(view._prop_plans))
    view._on_row_clicked(
        next(i for i, r in enumerate(view._rows) if r.species_key == key)
    )
    return key


class TestOneGestureIsOneWrite:
    """The batching, asserted through the panel rather than the writer."""

    def test_a_multi_step_gesture_writes_each_step_once(self, qtbot) -> None:
        view = _view(qtbot)
        key = _select(view)
        panel = view._detail

        writes: list[tuple] = []
        panel.steps_date_changed.connect(lambda payload: writes.extend(payload[1]))
        for step in ("indoor_sow", "harden_off"):
            s, e, _r = panel._step_rows[step][0:3]
            s.setDate(QDate(2026, 5, 4))
            e.setDate(QDate(2026, 5, 20))
        panel._flush_pending_steps()

        assert sorted(w[0] for w in writes) == ["harden_off", "indoor_sow"], writes
        stored = view._project_manager.propagation_overrides[key]
        assert set(stored) == {"indoor_sow", "harden_off"}, stored

    def test_one_gesture_emits_one_batch(self, qtbot) -> None:
        view = _view(qtbot)
        _select(view)
        panel = view._detail
        batches: list[tuple] = []
        panel.steps_date_changed.connect(batches.append)

        for step in ("indoor_sow", "harden_off"):
            s, e, _r = panel._step_rows[step][0:3]
            s.setDate(QDate(2026, 5, 4))
            e.setDate(QDate(2026, 5, 20))
        panel._flush_pending_steps()

        assert len(batches) == 1, (
            f"one gesture produced {len(batches)} batches, so the refresh runs "
            f"{len(batches)} times for a single user action"
        )


class TestTheCommitIsNotAnUndoStep:
    """The MECHANISM, not the prose.

    #415's write-up used to justify the commit batching with invariant 4 ("one user
    gesture is one undo step"). That was never true: a propagation override is
    written straight into ``ProjectManager._propagation_overrides`` and no
    ``Command`` reaches the ``CommandManager``, so there is no undo entry at all.
    The documentation now says what ships — one write and one refresh per gesture.

    An earlier version of this class also grepped CLAUDE.md, AGENTS.md and §11.4
    for the string "invariant 4" near the word "propagation" and failed if a
    sentence it disliked was present. Round 7's objection was correct and it is
    gone: a guard written in prose, over prose, fires the next time someone writes
    an accurate sentence in the wrong order, and cannot catch a *new* false claim
    either. The claim is no longer machine-checked — which is the honest state.

    What remains checks the mechanism, which is what actually determines the
    answer.
    """

    def test_there_really_is_no_undo_entry_for_an_override(self) -> None:
        """The mechanism the claim above rests on, asserted directly."""
        pm = ProjectManager()
        assert not hasattr(pm, "_command_manager"), (
            "ProjectManager now owns a command manager — if propagation overrides "
            "were routed through it, the invariant-4 claim would be true and both "
            "the documentation and this test should say so"
        )
        assert pm.set_propagation_override(
            "k", "indoor_sow", "2026-01-01", "2026-01-05"
        ) is True
        assert pm.propagation_overrides["k"]["indoor_sow"]["start"] == "2026-01-01"


class TestTaskIdCarriesTheAnchorYear:
    def test_adjacent_anchor_years_are_distinct_ids(self) -> None:
        """ADR-029's Decision 3: two anchors are two physical harvests."""
        assert make_calendar_task_id("k", "harvest", 2026) != make_calendar_task_id(
            "k", "harvest", 2027
        )

    def test_the_id_ends_with_the_anchor_year(self) -> None:
        assert make_calendar_task_id("k", "harvest", 2026).endswith(":2026")


def test_species_data_is_importable() -> None:
    """Keeps the PlantSpeciesData import honest rather than decorative."""
    parsed = PlantSpeciesData.from_dict(TOMATO)
    assert parsed.scientific_name == TOMATO["scientific_name"]
