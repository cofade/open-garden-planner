"""The D3 localisation decision, pinned (issues #332 and #333).

One convention, asserted for BOTH tools, because epic #237 requires the answer to
be consistent across #332 and #333, and #333 states that "two different answers to
the same question across two D3 tools would be worse than either answer".

The convention:

* ``task_type`` / ``source`` / ``task_id`` (D3.3) and ``amendment_id`` /
  ``reason_codes`` (D3.4) are **stable English machine keys**, part of the API
  contract, and never change with the UI language.
* ``title`` / ``notes`` (D3.3) and ``display_name`` / ``reasons`` (D3.4) are
  **display strings in the user's current UI language** and are explicitly NOT
  part of the English contract.

One thing these tests are careful about: the localisation happens UPSTREAM, in
``task_generator`` and ``soil_service``, which call ``QCoreApplication.translate``.
The agent layer only passes those strings through. So each test pins the pass-
through AND the upstream translation separately — asserting only "the title
changed" would pass even if the wrapper had invented a translation of its own,
which is a second localisation path and exactly the failure the decision exists
to prevent.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

TODAY = datetime.date(2026, 10, 3)
MARKER = "DE:"


class _PrefixTranslator(QTranslator):
    """A translator that marks every string it handles with a known prefix."""

    def __init__(self) -> None:
        super().__init__()
        self.handled: list[str] = []

    def translate(self, context, source_text, disambiguation=None, n=-1) -> str:
        self.handled.append(source_text)
        return f"{MARKER}{source_text}"


@pytest.fixture
def german_ui(qtbot: Any):
    """Install a translator, and guarantee it is removed afterwards.

    A leaked translator would make every LATER test in the session see prefixed
    strings — a spectacularly confusing failure to debug from the symptom.
    """
    translator = _PrefixTranslator()
    assert QCoreApplication.installTranslator(translator), (
        "Qt refused the translator; the test would prove nothing"
    )
    try:
        yield translator
    finally:
        QCoreApplication.removeTranslator(translator)


def _soil_mismatch_task():
    """One REAL soil-mismatch task from the engine (its title is translated)."""
    from open_garden_planner.services.task_generator import (
        BedInput,
        PlanState,
        generate_soil_mismatch_tasks,
    )

    tasks = generate_soil_mismatch_tasks(
        PlanState(
            today=TODAY,
            year=TODAY.year,
            beds=(BedInput(bed_id="bed-1", name="Bed 1", mismatch_plants=("Tomato",)),),
        )
    )
    assert tasks, "the fixture must actually produce a soil-mismatch task"
    return tasks[0]


# ── D3.3 ─────────────────────────────────────────────────────────────────────


def test_generator_task_title_is_localised_upstream(german_ui) -> None:
    """The engine's own title follows the UI language."""
    task = _soil_mismatch_task()
    assert MARKER in task.title, (
        "task_generator builds this title through QCoreApplication.translate, so "
        "a German UI must localise it upstream of the agent layer"
    )


def test_get_tasks_passes_the_localised_title_through(german_ui) -> None:
    from open_garden_planner.agent_api.domain import get_tasks_for_agent

    task = _soil_mismatch_task()
    view = get_tasks_for_agent([task], today=TODAY).tasks[0]

    # Pass-through, not a second translation path.
    assert view.title == task.title

    # The machine contract is untouched by the UI language.
    assert view.task_type == task.task_type
    assert view.source == task.source
    assert view.task_id == task.task_id
    assert view.species_key == task.species_key
    assert view.task_type == view.task_type.lower()


def test_the_localised_title_makes_no_difference_to_the_keys(german_ui) -> None:
    """Same task, two UI languages, identical machine fields."""
    from open_garden_planner.agent_api.domain import get_tasks_for_agent
    from open_garden_planner.services.task_generator import Task

    task = Task(
        task_id="calendar:tomato:direct_sow:2026",
        source="calendar",
        task_type="direct_sow",
        title="Direct sow Tomato",
        start_date=TODAY,
        end_date=TODAY,
    )
    keys = ("task_id", "source", "task_type", "urgency", "status", "start_date", "end_date")
    localised = get_tasks_for_agent([task], today=TODAY).tasks[0]

    QCoreApplication.removeTranslator(german_ui)
    plain = get_tasks_for_agent([task], today=TODAY).tasks[0]

    assert {k: getattr(localised, k) for k in keys} == {
        k: getattr(plain, k) for k in keys
    }


# ── D3.4 ─────────────────────────────────────────────────────────────────────


def test_amendment_id_is_english_and_independent_of_the_ui(german_ui) -> None:
    """``amendment_id`` is the key; ``display_name`` is display text.

    Amendment names are NOT ``tr()`` output — they are bilingual DATA
    (``Amendment.name`` / ``name_de``) — so the invariant under test is the same
    one either way: the id never changes with the UI language.
    """
    from open_garden_planner.agent_api.domain import recommend_amendments_for_agent
    from open_garden_planner.models.soil_test import SoilTestRecord
    from open_garden_planner.services.soil_service import SoilService

    record = SoilTestRecord(date="2026-09-01", ph=5.0, n_level=0, p_level=0, k_level=1)
    recs = SoilService.calculate_amendments(record, bed_area_m2=2.0)
    assert recs, "acidic, depleted soil must produce recommendations"

    view = recommend_amendments_for_agent(
        bed_id="bed-1", record=record, today=TODAY, recommendations=recs, language="de"
    )
    for got, want in zip(view.recommendations, recs, strict=True):
        assert got.amendment_id == want.amendment.id
        assert got.display_name == want.amendment.display_name("de")
        assert got.target_kind == want.target_kind


def test_reason_codes_stay_english_while_the_reason_follows_the_ui(german_ui) -> None:
    from open_garden_planner.agent_api.domain import get_soil_mismatches_for_agent
    from open_garden_planner.models.plant_data import PlantSpeciesData
    from open_garden_planner.models.soil_test import SoilTestRecord
    from open_garden_planner.services.soil_service import SoilService

    spec = PlantSpeciesData.from_dict(
        {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 6.8,
            "n_demand": "heavy",
        }
    )
    record = SoilTestRecord(date="2026-09-01", ph=7.9, n_level=1)
    details = SoilService.get_mismatch_details(record, [spec])
    assert details, "the fixture must actually produce a mismatch"

    view = get_soil_mismatches_for_agent(bed_id="bed-1", today=TODAY, details=details)
    assert view.total == 1
    mismatch = view.mismatches[0]

    # Codes: the declared stable set, whatever the UI language.
    assert set(mismatch.reason_codes) <= {
        "ph_low", "ph_high",
        "n_high_demand", "p_high_demand", "k_high_demand",
    }
    for code in mismatch.reason_codes:
        assert code == code.lower() and MARKER not in code

    # Reasons: localised upstream, paired with the codes positionally.
    assert len(mismatch.reasons) == len(mismatch.reason_codes)
    assert any(MARKER in reason for reason in mismatch.reasons), (
        "soil_service builds these sentences through QCoreApplication.translate"
    )


# ── D3.1 ─────────────────────────────────────────────────────────────────────


def test_companion_name_follows_the_ui_while_the_key_stays_english() -> None:
    """D3.1's display name obeys the same rule as D3.3/D3.4 (issue #410)."""
    from open_garden_planner.agent_api.domain import suggest_companions_for_agent
    from open_garden_planner.services.companion_planting_service import (
        CompanionPlantingService,
    )

    service = CompanionPlantingService()
    english = suggest_companions_for_agent(service, "tomato", language="en")
    german = suggest_companions_for_agent(service, "tomato", language="de")
    assert english and german
    # The machine key is untouched by the UI language.
    assert [s.species_key for s in english] == [s.species_key for s in german]
    # The display name is the only part that moves.
    assert any(
        de.name != en.name for de, en in zip(german, english, strict=True)
    ), "at least one bundled companion has a German name"


# ── The convention must be DOCUMENTED where an agent reads it ─────────────────


def test_the_schema_documents_the_display_string_rule() -> None:
    """A convention nothing states is a convention that erodes.

    Asserted against the field descriptions an agent actually reads, not a doc
    file that can drift away from the schema.
    """
    from open_garden_planner.agent_api.schema import (
        AmendmentRecommendationView,
        CompanionSuggestion,
        SoilMismatchView,
        TaskView,
    )

    for model, keys, display_fields in (
        (TaskView, ("task_type", "source"), ("title", "notes")),
        (AmendmentRecommendationView, ("amendment_id", "target_kind"), ("display_name",)),
        (SoilMismatchView, ("reason_codes",), ("reasons",)),
        (CompanionSuggestion, ("species_key",), ("name",)),
    ):
        for name in display_fields:
            description = model.model_fields[name].description or ""
            assert "display string" in description.lower(), (
                f"{model.__name__}.{name} must document itself as a display "
                "string, not part of the English API contract"
            )
        for name in keys:
            description = (model.model_fields[name].description or "").lower()
            assert "english" in description or "stable" in description, (
                f"{model.__name__}.{name} must document itself as a stable key"
            )


def test_the_tool_docstrings_state_the_split() -> None:
    """The docstring is the contract an agent reads before its first call."""
    import inspect

    from open_garden_planner.agent_api import prompts

    week = inspect.getdoc(prompts.render_plan_my_week_prompt) or ""
    soil = inspect.getdoc(prompts.render_plan_soil_amendments_prompt) or ""
    assert "display" in week.lower()
    assert "display" in soil.lower()
