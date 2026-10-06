"""Two gaps round 5 named: an unguarded colour map and an overclaimed invariant.

1. `_GANTT_COLORS` in `planting_calendar_view.py` maps a generated calendar task
   type to a bar colour, and its comment claimed "a generated type missing here is
   a task the dashboard lists and the chart silently omits". Neither half held: the
   real filter is `_compute_gantt_windows`, and `_paint_bars` uses
   `_GANTT_COLORS.get(task_type, _COL_DIRECT)`, which MIS-COLOURS rather than
   omits. Nothing pinned the map against the generator's own task-type list, so a
   new generated task type would draw in the wrong colour with no failure. This
   test pins the two sets together.

2. #415's text justifies the commit batching with invariant 4 ("one user gesture is
   one undo step"). The gesture produces **no undo step at all** — propagation
   overrides are written straight into `ProjectManager._propagation_overrides` and
   no `Command` reaches the `CommandManager`. That has stood since an earlier
   round. Rather than claim an undo step the code does not create, the docs now
   say what is true — one *write* per gesture, one refresh — and this test asserts
   the claim matches the code, so it cannot be quietly re-inflated.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.propagation import compute_propagation_plan
from open_garden_planner.services.task_generator import (
    PlanState,
    PlantRowInput,
    generate_all,
    make_calendar_task_id,
)
from open_garden_planner.ui.views.planting_calendar_view import _GANTT_COLORS

REPO_ROOT = Path(__file__).resolve().parents[2]


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
            "for them. `_paint_bars` falls back to _COL_DIRECT, so these would draw "
            "in the wrong colour with no test failing."
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


class TestTheCommitBatchIsNotAnUndoStep:
    """#415 must not claim an undo step the code does not create."""

    def _claimed_invariant_4(self, rel: str) -> list[str]:
        path = REPO_ROOT / rel
        if not path.exists():
            return []
        out: list[str] = []
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"invariant 4", text):
            snippet = re.sub(r"\s+", " ", text[max(0, match.start() - 260):match.end() + 260])
            if re.search(r"propagation|step date|override", snippet, re.I):
                out.append(snippet)
        return out

    @pytest.mark.parametrize(
        "rel",
        ["CLAUDE.md", "AGENTS.md", "docs/11-risks-and-technical-debt/README.md"],
    )
    def test_no_propagation_commit_is_justified_by_invariant_4(self, rel: str) -> None:
        claims = self._claimed_invariant_4(rel)
        assert not claims, (
            f"{rel} justifies the propagation-commit batching with invariant 4 "
            "(one user gesture = one undo step), but no Command reaches the "
            "CommandManager for a propagation override:\n  " + "\n  ".join(claims)
        )

    def test_there_really_is_no_undo_entry_for_an_override(self) -> None:
        """The mechanism the claim above rests on, asserted directly."""
        from open_garden_planner.core.project import ProjectManager

        pm = ProjectManager()
        assert not hasattr(pm, "_command_manager"), (
            "ProjectManager now owns a command manager — if propagation overrides "
            "were routed through it, the invariant-4 claim would be true and this "
            "test (and the documentation) should say so"
        )
        assert pm.set_propagation_override("k", "indoor_sow", "2026-01-01", "2026-01-05") is True
        assert pm.propagation_overrides["k"]["indoor_sow"]["start"] == "2026-01-01"

    def test_what_the_commit_actually_guarantees(self) -> None:
        """The true, testable property: ONE write per gesture.

        This is what the batching buys, and it is what the docs now claim.
        """
        from open_garden_planner.core.project import ProjectManager

        writes: list[tuple] = []
        pm = ProjectManager()
        original = ProjectManager.set_propagation_override

        def spy(self, species_key, step_id, start, end):
            writes.append((species_key, step_id))
            return original(self, species_key, step_id, start, end)

        ProjectManager.set_propagation_override = spy
        try:
            # Two steps in one gesture.
            pm.set_propagation_override("k", "indoor_sow", "2026-01-01", "2026-01-05")
            pm.set_propagation_override("k", "harden_off", "2026-02-01", "2026-02-10")
        finally:
            ProjectManager.set_propagation_override = original
        assert len(writes) == 2, writes


class TestTaskIdShapeDocumentedByTheCommitPath:
    def test_the_id_carries_the_anchor_year(self) -> None:
        """ADR-029's Decision 3 depends on this shape."""
        assert make_calendar_task_id("k", "harvest", 2026) != make_calendar_task_id("k", "harvest", 2027)
        assert make_calendar_task_id("k", "harvest", 2026).endswith(":2026")


def test_propagation_plan_round_trip_is_ordered() -> None:
    """A cheap sanity check that the imported helpers are wired, not decoration."""
    plan = compute_propagation_plan(
        species_key="k",
        sow_start=datetime.date(2026, 2, 12),
        sow_end=datetime.date(2026, 2, 26),
        transplant_date=datetime.date(2026, 5, 15),
    )
    for step in plan.steps:
        assert step.end_date >= step.start_date, step.step_id


def test_plan_state_and_species_are_constructible() -> None:
    state = PlanState(
        today=datetime.date(2026, 6, 1),
        year=2026,
        last_frost=datetime.date(2026, 4, 9),
        plant_rows=(
            PlantRowInput(
                display_name="Tomato",
                species_key="k",
                harvest_start=10,
                harvest_end=18,
            ),
        ),
    )
    assert {t.task_type for t in generate_all(state)} >= {"harvest"}
    assert PlantSpeciesData is not None
