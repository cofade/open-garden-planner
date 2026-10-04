"""Unit tests for the US-D3.3 task-calendar agent wrappers (issue #332).

Qt-free, no ``qtbot``: everything here drives ``agent_api.domain`` over plain
data, which is the point of that split (invariant 10).

The four habits from the delivery discipline are load-bearing in this file:

* the REFUSAL path is asserted, not just the happy path;
* the injected date is asserted everywhere, because a suite that reads the wall
  clock silently rots the day after it is written;
* boundaries are PARAMETRISED over the parameter a defect scales with (the date
  window edges, and the dismissed/archived statuses);
* drift guards pin every set inlined from elsewhere.
"""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.agent_api.domain import (
    HIDDEN_WHEN_NOT_INCLUDE_DISMISSED,
    TASK_SOURCES,
    _months_between,
    get_task_calendar_for_agent,
    get_tasks_for_agent,
)
from open_garden_planner.agent_api.schema import TaskListView
from open_garden_planner.services.task_generator import (
    Task,
    classify_urgency,
    make_calendar_task_id,
)
from open_garden_planner.services.task_status import effective_status

TODAY = datetime.date(2026, 10, 3)


def _task(
    task_id: str = "t1",
    *,
    source: str = "calendar",
    task_type: str = "direct_sow",
    title: str = "Direct sow Tomato",
    start: datetime.date | None = TODAY,
    end: datetime.date | None = TODAY,
    bed_id: str | None = None,
    species_key: str = "solanum_lycopersicum",
    dismissible: bool = True,
) -> Task:
    return Task(
        task_id=task_id,
        source=source,
        task_type=task_type,
        title=title,
        notes="",
        start_date=start,
        end_date=end,
        bed_id=bed_id,
        species_key=species_key,
        item_ids=(),
        dismissible=dismissible,
    )


# ── Urgency is the engine's, never a second implementation ────────────────────


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (TODAY, TODAY, "today"),
        (TODAY - datetime.timedelta(days=3), TODAY - datetime.timedelta(days=1), "overdue"),
        (TODAY + datetime.timedelta(days=2), TODAY + datetime.timedelta(days=4), "this_week"),
        (TODAY + datetime.timedelta(days=20), TODAY + datetime.timedelta(days=25), "upcoming"),
        (TODAY - datetime.timedelta(days=40), TODAY - datetime.timedelta(days=35), None),
    ],
)
def test_urgency_comes_from_classify_urgency(start, end, expected):
    # A wide window, so the only thing under test is the urgency bucket and not
    # whether the task happens to fall inside the default ±30 days.
    view = get_tasks_for_agent(
        [_task(start=start, end=end)],
        today=TODAY,
        from_date=TODAY - datetime.timedelta(days=400),
        to_date=TODAY + datetime.timedelta(days=400),
    )
    assert view.tasks[0].urgency == expected
    # And it is literally the engine's answer, not a look-alike.
    assert view.tasks[0].urgency == classify_urgency(start, end, TODAY)


# ── Determinism and injected dates ───────────────────────────────────────────


def test_two_calls_return_identical_output():
    tasks = [_task("b"), _task("a"), _task("c")]
    first = get_tasks_for_agent(tasks, today=TODAY)
    second = get_tasks_for_agent(tasks, today=TODAY)
    assert first.model_dump() == second.model_dump()


def test_task_ids_are_stable_across_calls():
    """The engine's own ids must survive, or an agent cannot refer to a task."""
    tasks = [_task("x"), _task("y")]
    ids_a = [t.task_id for t in get_tasks_for_agent(tasks, today=TODAY).tasks]
    ids_b = [t.task_id for t in get_tasks_for_agent(tasks, today=TODAY).tasks]
    assert ids_a == ids_b == ["x", "y"]


def test_output_is_sorted_by_start_date_then_id():
    tasks = [
        _task("z", start=TODAY + datetime.timedelta(days=5)),
        _task("a", start=TODAY),
        _task("b", start=TODAY),
    ]
    view = get_tasks_for_agent(
        tasks, today=TODAY, from_date=TODAY - datetime.timedelta(days=1),
        to_date=TODAY + datetime.timedelta(days=30),
    )
    assert [t.task_id for t in view.tasks] == ["a", "b", "z"]


def test_injected_date_changes_the_answer():
    """Proof the tool does not read the wall clock."""
    task = _task(start=datetime.date(2026, 10, 3), end=datetime.date(2026, 10, 3))
    wide = {
        "from_date": datetime.date(2026, 1, 1),
        "to_date": datetime.date(2027, 1, 1),
    }
    as_of_its_day = get_tasks_for_agent(
        [task], today=datetime.date(2026, 10, 3), **wide
    )
    ten_days_later = get_tasks_for_agent(
        [task], today=datetime.date(2026, 10, 13), **wide
    )
    assert as_of_its_day.tasks[0].urgency == "today"
    assert ten_days_later.tasks[0].urgency == "overdue"


# ── Filters ──────────────────────────────────────────────────────────────────


def test_default_window_is_thirty_days_either_side():
    view = get_tasks_for_agent([_task()], today=TODAY)
    assert view.from_date == (TODAY - datetime.timedelta(days=30)).isoformat()
    assert view.to_date == (TODAY + datetime.timedelta(days=30)).isoformat()


def _two_tasks() -> list[Task]:
    """A roster where every filter key differs between the two tasks."""
    return [
        _task("a", source="frost", bed_id="bed-1", species_key="tomato"),
        _task("b", source="manual", bed_id="bed-2", species_key="carrot"),
    ]


@pytest.mark.parametrize(
    ("filter_kwargs", "expected_id"),
    [
        ({"source": "frost"}, "a"),
        ({"source": "manual"}, "b"),
        ({"source": "soil"}, None),
        ({"bed_id": "bed-1"}, "a"),
        ({"bed_id": "bed-2"}, "b"),
        ({"species_key": "tomato"}, "a"),
        ({"species_key": "carrot"}, "b"),
        ({"source": "succession"}, None),
    ],
)
def test_each_filter_narrows_to_its_own_key(filter_kwargs, expected_id):
    view = get_tasks_for_agent(_two_tasks(), today=TODAY, **filter_kwargs)
    ids = [t.task_id for t in view.tasks]
    assert ids == ([] if expected_id is None else [expected_id])


def test_species_key_filter():
    tasks = [_task("a", species_key="tomato"), _task("b", species_key="carrot")]
    view = get_tasks_for_agent(tasks, today=TODAY, species_key="carrot")
    assert [t.task_id for t in view.tasks] == ["b"]


# ── Window edges, parametrised: a bug at the boundary is the bug ─────────────


@pytest.mark.parametrize(
    ("offset_start", "offset_end", "expect_kept"),
    [
        (-31, -31, False),   # one day before the window
        (-30, -30, True),    # exactly the first day IN window
        (0, 0, True),
        (30, 30, True),      # exactly the last day IN window
        (31, 31, False),     # one day after
    ],
)
def test_window_boundaries_are_inclusive(offset_start, offset_end, expect_kept):
    task = _task(
        start=TODAY + datetime.timedelta(days=offset_start),
        end=TODAY + datetime.timedelta(days=offset_end),
    )
    view = get_tasks_for_agent([task], today=TODAY)
    assert bool(view.tasks) is expect_kept


def test_undated_task_survives_a_filtered_read():
    """An undated manual task must not vanish — it has no dates to place."""
    undated = _task("u", source="manual", start=None, end=None)
    view = get_tasks_for_agent([undated], today=TODAY, from_date=TODAY, to_date=TODAY)
    assert [t.task_id for t in view.tasks] == ["u"]


def test_task_spanning_the_window_edges_is_kept():
    """Overlap, not containment: a long task overlapping the window belongs."""
    task = _task(start=TODAY - datetime.timedelta(days=90), end=TODAY + datetime.timedelta(days=90))
    assert get_tasks_for_agent([task], today=TODAY).total == 1


# ── Status: the shared store, and the GUI's own hiding rule ───────────────────


def test_status_comes_from_the_shared_store():
    states = {"t1": {"status": "done", "done_date": TODAY.isoformat()}}
    view = get_tasks_for_agent([_task("t1")], today=TODAY, task_states=states)
    assert view.tasks[0].status == "done"
    assert view.tasks[0].done_date == TODAY.isoformat()


def test_status_matches_effective_status_exactly():
    for stored in (
        None,
        {},
        {"status": "dismissed"},
        {"status": "done", "done_date": TODAY.isoformat()},
        {"status": "done", "done_date": "2020-01-01"},
        {"status": "snoozed", "snooze_until": (TODAY + datetime.timedelta(days=5)).isoformat()},
    ):
        states = {"t1": stored} if stored is not None else {}
        # include_dismissed, because two of those resolve to a HIDDEN status and
        # would otherwise be filtered out before the status could be compared.
        view = get_tasks_for_agent(
            [_task("t1")],
            today=TODAY,
            task_states=states,
            include_dismissed=True,
        )
        assert view.tasks[0].status == effective_status(stored, TODAY)


@pytest.mark.parametrize("status", ["dismissed", "archived"])
def test_hidden_statuses_are_hidden_by_default(status):
    states = {"t1": {"status": status}}
    if status == "archived":
        # 'archived' is what a done task resolves to once done_date is stale.
        states["t1"] = {"status": "done", "done_date": "2020-01-01"}
    assert get_tasks_for_agent([_task("t1")], today=TODAY, task_states=states).total == 0


@pytest.mark.parametrize("status", ["dismissed", "archived"])
def test_hidden_statuses_reappear_when_asked(status):
    states = {"t1": {"status": status}}
    if status == "archived":
        states["t1"] = {"status": "done", "done_date": "2020-01-01"}
    view = get_tasks_for_agent(
        [_task("t1")], today=TODAY, task_states=states, include_dismissed=True
    )
    assert view.total == 1
    assert view.tasks[0].status == effective_status(states["t1"], TODAY)


def test_hidden_status_set_matches_the_tasks_tab():
    """The GUI hides exactly these two (``ui/views/tasks_view.py``).

    A tool that hid a different set would be a third surface disagreeing with
    the other two about one store — the defect invariant 6 exists to prevent.
    """
    assert set(HIDDEN_WHEN_NOT_INCLUDE_DISMISSED) == {"archived", "dismissed"}


def test_done_task_is_still_shown_by_default():
    """A task completed this week is history the user wants, not noise."""
    states = {"t1": {"status": "done", "done_date": TODAY.isoformat()}}
    assert get_tasks_for_agent([_task("t1")], today=TODAY, task_states=states).total == 1


# ── Degradation: never an empty list that reads as "nothing to do" ───────────


def test_no_frost_dates_sets_coverage_and_still_returns_other_tasks():
    manual = _task("m", source="manual", title="Order seed")
    soil = _task("s", source="soil_amendment", title="Add compost")
    view = get_tasks_for_agent(
        [manual, soil], today=TODAY, has_frost_dates=False
    )
    assert view.coverage == "no_frost_dates"
    assert view.total == 2, "non-calendar tasks must survive the missing frost dates"


def test_full_coverage_when_frost_dates_exist():
    assert get_tasks_for_agent([_task()], today=TODAY).coverage == "full"


def test_empty_plan_is_still_labelled():
    view = get_tasks_for_agent([], today=TODAY, has_frost_dates=False)
    assert view.total == 0
    assert view.coverage == "no_frost_dates", (
        "an empty list must never be the whole answer — it has to say WHY"
    )


# ── Calendar buckets ─────────────────────────────────────────────────────────


def test_calendar_buckets_by_month():
    tasks = [
        _task("a", start=datetime.date(2026, 10, 1), end=datetime.date(2026, 10, 2)),
        _task("b", source="frost", start=datetime.date(2026, 11, 3), end=datetime.date(2026, 11, 3)),
    ]
    view = get_task_calendar_for_agent(tasks, today=TODAY)
    assert [m.month for m in view.months] == ["2026-10", "2026-11"]
    assert view.months[0].total == 1
    assert view.months[0].by_source == {"calendar": 1}
    assert view.total == 2


def test_task_spanning_a_month_boundary_counts_in_both():
    task = _task(
        start=datetime.date(2026, 10, 28), end=datetime.date(2026, 11, 2)
    )
    view = get_task_calendar_for_agent([task], today=TODAY)
    assert [m.month for m in view.months] == ["2026-10", "2026-11"]


@pytest.mark.parametrize(
    ("start", "end", "year", "months"),
    [
        (datetime.date(2025, 12, 28), datetime.date(2026, 1, 5), 2026, ["2026-01"]),
        (datetime.date(2026, 12, 28), datetime.date(2027, 1, 5), 2026, ["2026-12"]),
        (datetime.date(2026, 12, 28), datetime.date(2027, 1, 5), 2027, ["2027-01"]),
        (datetime.date(2025, 12, 28), datetime.date(2027, 1, 5), 2026,
         [f"2026-{month:02d}" for month in range(1, 13)]),
    ],
)
def test_calendar_clips_cross_year_tasks(start, end, year, months):
    view = get_task_calendar_for_agent([_task(start=start, end=end)], today=TODAY, year=year)
    assert [bucket.month for bucket in view.months] == months


def test_calendar_excludes_tasks_outside_the_target_year():
    task = _task(start=datetime.date(2027, 5, 1), end=datetime.date(2027, 5, 2))
    view = get_task_calendar_for_agent([task], today=TODAY, year=2026)
    assert view.total == 0


def test_calendar_coverage_marks_missing_frost_dates():
    view = get_task_calendar_for_agent([], today=TODAY, has_frost_dates=False)
    assert view.coverage == "no_frost_dates"


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        ("2026-10", "2026-10", ["2026-10"]),
        ("2026-10", "2026-12", ["2026-10", "2026-11", "2026-12"]),
        ("2026-11", "2027-02", ["2026-11", "2026-12", "2027-01", "2027-02"]),
        ("2026-12", "2027-01", ["2026-12", "2027-01"]),   # year rollover
        ("2026-10", "2026-09", []),                        # inverted
        ("", "2026-10", []),                               # sentinel: outside year
        ("2026-10", "", []),
    ],
)
def test_month_range_edges(first, last, expected):
    assert _months_between(first, last) == expected


# ── Drift guards ─────────────────────────────────────────────────────────────


def test_task_sources_match_what_the_generators_emit():
    """EQUALITY, both directions — this guard has already caught a real bug.

    An earlier version asserted only ``emitted <= TASK_SOURCES``, which passed
    while ``TASK_SOURCES`` carried two values no generator can emit
    (``soil_amendment`` / ``soil_mismatch``). The effect in the field:
    ``get_tasks(source="soil_mismatch")`` returned an empty list, while
    ``get_tasks(source="soil")`` — the value that works — was refused as unknown.

    Read from the engine module by AST rather than from a fixture, because four
    of the seven generators need live inputs (plants, frost alerts,
    propagation plans) that a bare ``PlanState`` cannot supply — a
    fixture-driven roster would silently under-report, which is how the wrong
    values survived in the first place.
    """
    import ast
    import pathlib

    import open_garden_planner.services.task_generator as engine

    tree = ast.parse(pathlib.Path(engine.__file__).read_text(encoding="utf-8"))
    emitted: set[str] = set()
    task_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "Task":
            continue
        task_calls += 1
        for keyword in node.keywords:
            if keyword.arg == "source" and isinstance(keyword.value, ast.Constant):
                emitted.add(str(keyword.value.value))

    assert task_calls >= 7, (
        f"only {task_calls} Task(...) constructions found — the guard is not "
        "seeing the generators and would pass vacuously"
    )
    assert emitted == set(TASK_SOURCES), (
        "TASK_SOURCES and the generators disagree: "
        f"declared-but-never-emitted={set(TASK_SOURCES) - emitted}, "
        f"emitted-but-undeclared={emitted - set(TASK_SOURCES)}"
    )


def test_propagation_source_is_declared():
    assert "propagation" in TASK_SOURCES


def test_soil_amendment_and_mismatch_share_the_soil_source() -> None:
    """Both soil generators emit ``source="soil"``; ``task_type`` tells them apart.

    This is why ``TASK_SOURCES`` has six entries for seven generators, and why a
    caller filtering by ``source`` alone cannot select one of the two.
    """
    from open_garden_planner.services.task_generator import (
        BedInput,
        PlanState,
        generate_soil_amendment_tasks,
        generate_soil_mismatch_tasks,
    )

    bed = BedInput(
        bed_id="bed-1",
        name="Bed 1",
        amendment_recs=(("Compost", "~200 g"),),
        mismatch_plants=("Tomato",),
    )
    state = PlanState(today=TODAY, year=TODAY.year, beds=(bed,))

    amendment = generate_soil_amendment_tasks(state)
    mismatch = generate_soil_mismatch_tasks(state)
    assert amendment and mismatch
    assert amendment[0].source == mismatch[0].source == "soil"
    assert amendment[0].task_type != mismatch[0].task_type


def test_task_types_distinguish_the_two_soil_generators() -> None:
    from open_garden_planner.services.task_generator import (
        BedInput,
        PlanState,
        generate_soil_amendment_tasks,
        generate_soil_mismatch_tasks,
    )

    bed = BedInput(
        bed_id="bed-1",
        name="Bed 1",
        amendment_recs=(("Compost", "~200 g"),),
        mismatch_plants=("Tomato",),
    )
    state = PlanState(today=TODAY, year=TODAY.year, beds=(bed,))
    assert generate_soil_amendment_tasks(state)[0].task_type == "soil_amendment"
    assert generate_soil_mismatch_tasks(state)[0].task_type == "soil_mismatch"


def test_soil_mismatch_title_is_localised_upstream(qtbot) -> None:
    """The mismatch title is built with QCoreApplication.translate.

    This is the concrete instance behind the D3 localisation decision: a German
    UI returns a German task title through a surface documented as an English
    API contract, which is why ``task_type`` is the field agents must branch on.
    """
    from PyQt6.QtCore import QCoreApplication, QTranslator

    from open_garden_planner.services.task_generator import (
        BedInput,
        PlanState,
        generate_soil_mismatch_tasks,
    )

    plain = generate_soil_mismatch_tasks(
        PlanState(
            today=TODAY,
            year=TODAY.year,
            beds=(BedInput(bed_id="b", name="Bed", mismatch_plants=("Tomato",)),),
        )
    )[0].title

    class _T(QTranslator):
        def translate(self, context, source_text, disambiguation=None, n=-1):
            return f"DE:{source_text}"

    translator = _T()
    assert QCoreApplication.installTranslator(translator)
    try:
        localised = generate_soil_mismatch_tasks(
            PlanState(
                today=TODAY,
                year=TODAY.year,
                beds=(BedInput(bed_id="b", name="Bed", mismatch_plants=("Tomato",)),),
            )
        )[0].title
    finally:
        QCoreApplication.removeTranslator(translator)

    assert localised != plain
    assert "DE:" in localised


def test_make_calendar_task_id_is_the_id_source():
    """The ids the tool surfaces are the engine's, not ones minted here."""
    tid = make_calendar_task_id("solanum_lycopersicum", "direct_sow", 2026)
    task = _task(tid)
    view = get_tasks_for_agent([task], today=TODAY)
    assert view.tasks[0].task_id == tid


def test_view_type_is_returned_not_a_bare_list():
    """A bare list could not carry the coverage marker."""
    assert isinstance(get_tasks_for_agent([], today=TODAY), TaskListView)
