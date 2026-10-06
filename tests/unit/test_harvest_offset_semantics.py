"""#416 — what the bundled harvest offsets actually mean, and what they don't.

``models/plant_data.py`` documented ``harvest_start`` as "weeks after planting".
Every reader has always counted it from the plan's **last spring frost** —
``services/task_generator.generate_calendar_tasks``, the planting calendar's
Gantt, the agent's ``get_tasks`` / ``get_task_calendar``, and the Phase 17 spike's
fruit window. This file pins the semantics that the code actually implements.

It also records, as data rather than as a silent assumption, how far the bundled
rows diverge from ``days_to_maturity``. The measurement behind the issue (118
species, 64 with both harvest offsets and a maturity range):

* "``harvest_offset x 7`` lies inside ``days_to_maturity``" — **1 fits, 63 miss**;
* "(``harvest_offset - planting_offset``) x 7 lies inside the maturity range,
  +/-15%" — **10 fit, 54 miss**;
* on the harvest *start* under the second reading, most species land 1.0-1.5x
  their stated maturity, and garlic lands at 364 days against a stated
  180-210.

So the rows cannot be reconciled against ``days_to_maturity`` under either
reading, and there is no majority to convert towards. The shipped half of #416 is
therefore to make the documentation true and to name the divergence; converting
the rows to planting-relative is deferred to its own package with a cited
horticultural source (``days_to_maturity`` is reference data that no computation
reads — it is displayed, never scheduled from).

The named exceptions below are a drift guard: adding or reordering a bundled
species that changes this set must be a deliberate act, not a silent diff.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData

DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "open_garden_planner"
    / "resources"
    / "data"
    / "plant_species.json"
)

#: Species whose bundled harvest window diverges most from ``days_to_maturity``
#: when read as frost-relative offsets. Named deliberately: these are the rows a
#: future planting-relative conversion must revisit first, and garlic is the
#: worked example in #414/#416.
KNOWN_DIVERGENT_SPECIES = frozenset({
    "Allium sativum",       # garlic: 364 d from sowing vs 180-210 stated maturity
    "Rheum rhabarbarum",     # rhubarb: multi-year maturity, one-season window
    "Asparagus officinalis",  # asparagus: 730-1095 d maturity
    "Allium porrum",         # leek
    "Brassica oleracea var. gemmifera",  # Brussels sprouts
})


def _rows() -> list[dict]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))["plants"]


def _species(rows: list[dict]) -> list[PlantSpeciesData]:
    return [PlantSpeciesData.from_dict(r) for r in rows]


class TestHarvestOffsetsAreFrostRelative:
    """The invariant the generators rely on."""

    def test_every_reader_anchors_on_the_frost_date(self) -> None:
        """The shared generator computes harvest as frost + weeks.

        Pinned by asserting the produced dates rather than the source text, so a
        refactor that changes the anchor breaks here instead of silently moving
        every user's harvest dates.
        """
        from open_garden_planner.services.task_generator import (
            PlanState,
            PlantRowInput,
            generate_calendar_tasks,
        )

        last_frost = datetime.date(2026, 4, 9)   # garlic's example frost date
        row = PlantRowInput(
            display_name="Garlic",
            species_key="allium_sativum",
            harvest_start=26,
            harvest_end=32,
        )
        state = PlanState(
            today=last_frost,
            year=2026,
            last_frost=last_frost,
            plant_rows=(row,),
            actionable_only=False,   # keep the window regardless of urgency
        )
        harvest = [
            t for t in generate_calendar_tasks(state) if t.task_type == "harvest"
        ]
        assert len(harvest) == 1
        # 26 and 32 weeks after 9 April 2026 — NOT 26 weeks after the sowing.
        assert harvest[0].start_date == datetime.date(2026, 10, 8)
        assert harvest[0].end_date == datetime.date(2026, 11, 19)

    def test_model_docstring_no_longer_promises_weeks_after_planting(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "open_garden_planner"
            / "models"
            / "plant_data.py"
        ).read_text(encoding="utf-8")
        # The two inline field comments, which is where the wrong claim lived.
        assert "harvest_start: int | None = None      # weeks after planting" not in source
        assert "harvest_start: int | None = None      # weeks relative to last frost" in source, (
            "the harvest fields must be documented as frost-relative while every "
            "reader anchors them on the last spring frost (#416)"
        )

    @pytest.mark.parametrize("field", ["harvest_start", "harvest_end"])
    def test_no_bundled_row_uses_a_non_integer_offset(self, field: str) -> None:
        for row in _rows():
            value = row.get(field)
            assert value is None or isinstance(value, int), (row.get("common_name"), field, value)


class TestHarvestFollowsItsOwnPlantingWindow:
    """The invariant that DOES hold, and which the generator depends on."""

    @pytest.mark.parametrize("anchor_year", [2025, 2026, 2027])
    def test_harvest_window_never_precedes_the_planting_window(self, anchor_year: int) -> None:
        """Harvest must not land before the sowing/transplant it follows.

        Parametrised over anchor years because the offsets are large enough
        (asparagus harvests 104 weeks after the frost) that a single year cannot
        express the ordering.
        """
        last_frost = datetime.date(anchor_year, 4, 15)
        for sp in _species(_rows()):
            if sp.harvest_start is None or sp.harvest_end is None:
                continue
            harvest_start = last_frost + datetime.timedelta(weeks=sp.harvest_start)
            harvest_end = last_frost + datetime.timedelta(weeks=sp.harvest_end)
            assert harvest_end >= harvest_start, sp.common_name

            # The plant goes in somewhere inside its sowing window, so the
            # invariant is against the window's START, not its end — Bean (Bush)
            # legitimately harvests while its own sowing window is still open.
            planting_offsets = [
                o for o in (
                    sp.direct_sow_start,
                    sp.transplant_start,
                    sp.indoor_sow_start,
                ) if o is not None
            ]
            if not planting_offsets:
                continue
            earliest_planting = last_frost + datetime.timedelta(weeks=min(planting_offsets))
            assert harvest_start >= earliest_planting, (
                f"{sp.common_name}: harvest starts {harvest_start} but its planting "
                f"window opens {earliest_planting}"
            )


class TestKnownDivergenceFromMaturityIsNamed:
    """The rows a planting-relative conversion must revisit, pinned as data."""

    def test_divergent_species_set_is_stable(self) -> None:
        present = {sp.scientific_name for sp in _species(_rows())}
        missing = KNOWN_DIVERGENT_SPECIES - present
        assert not missing, (
            f"these named exceptions no longer exist in the bundled data: {sorted(missing)} — "
            "re-measure and update KNOWN_DIVERGENT_SPECIES deliberately"
        )

    def test_garlic_is_still_the_worked_counterexample(self) -> None:
        """#414 and #416 both use garlic; the numbers must not drift unnoticed."""
        garlic = next(
            sp for sp in _species(_rows())
            if sp.scientific_name == "Allium sativum"
        )
        # Frost-relative, so the harvest window is 26..32 weeks after the frost.
        assert (garlic.harvest_start, garlic.harvest_end) == (26, 32)
        # Sown 26..24 weeks BEFORE the frost, so the frost-relative harvest
        # lands ~52 weeks after the sowing — the overlap #416 documents.
        assert (garlic.direct_sow_start, garlic.direct_sow_end) == (-26, -24)
        # And its stated maturity does not reconcile with either reading.
        assert garlic.days_to_maturity_min == 180
        assert garlic.days_to_maturity_max == 210

    def test_maturity_fields_are_reference_data_not_used_for_scheduling(self) -> None:
        """No generator reads days_to_maturity; it is displayed only.

        This is why #416's deferred half can be a data correction rather than a
        behavioural change: correcting the rows cannot move a computed date
        unless a reader starts using these fields.
        """
        generator = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "open_garden_planner"
            / "services"
            / "task_generator.py"
        ).read_text(encoding="utf-8")
        assert "days_to_maturity" not in generator, (
            "task_generator must not schedule from days_to_maturity; if it now "
            "does, the #416 deferral is no longer safe and needs re-scoping"
        )
