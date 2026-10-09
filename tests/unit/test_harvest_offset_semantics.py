"""#416 — what the bundled harvest offsets actually mean, and what they don't.

``models/plant_data.py`` documented ``harvest_start`` as "weeks after planting".
Every reader has always counted it from the plan's **last spring frost** —
``services/task_generator.generate_calendar_tasks``, the planting calendar's
Gantt, the agent's ``get_tasks`` / ``get_task_calendar``, and the Phase 17 spike's
fruit window. This file pins the semantics that the code actually implements.

It also records, as data rather than as a silent assumption, how far the bundled
rows diverge from ``days_to_maturity``. The measurement is committed as
``scripts/measure_harvest_offsets.py`` (118 species, 64 with both harvest offsets
and a maturity range):

* reading **A** — frost-relative, ``harvest_start x 7`` inside the maturity range,
  which is what every reader actually implements: **38 fit / 26 miss**;
* reading **B** — planting-relative, ``(harvest_start - planting_offset) x 7``
  inside the range ± 15 %: **45 fit / 19 miss**;
* **11 species fit neither** (basil, bush bean, Brussels sprouts, echinacea,
  oregano, radish, rocket, rosemary, spinach, sweet pea, zucchini).

Two conclusions, and the distinction is the whole point of #416:

* **Both readings fit a majority, so the data is not irreconcilable.** An earlier
  draft of this file claimed "1 fits / 63 miss" and "10 fits / 54 miss" and used
  the absence of a majority to justify deferring the conversion. Those numbers
  matched no harness and the conclusion was wrong — the senior review caught it.
* **Reading B fits more often than the one the code implements.** So the rows were
  probably *authored* as planting-relative while every reader counts them from the
  frost. That is a real, separate finding, and it is what makes the row conversion
  a package rather than a patch.

The shipped half of #416 is therefore to make the documentation true and to name
the divergence. The row conversion is deferred to #418 on the grounds that it
needs a cited horticultural source per row and licence clearance under #311's
provenance rules — **not** because the data cannot be reconciled.
``days_to_maturity`` is reference data that no computation reads (asserted
below), so correcting rows cannot move a computed date.

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

#: Species whose bundled harvest window diverges from ``days_to_maturity``
#: when read as frost-relative offsets. Garlic (Allium sativum) was corrected
#: in #418 to summer harvest (12..16 weeks post-frost) with 240..270d maturity.
#: The remaining rows are multi-year crops or long-season brassicas.
KNOWN_DIVERGENT_SPECIES = frozenset({
    # Multi-year maturity figures against a single-season window.
    "Rheum rhabarbarum",
    "Asparagus officinalis",
    "Allium porrum",
    # Among the 11 measured to fit NEITHER reading.
    "Brassica oleracea var. gemmifera",
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
            harvest_start=12,
            harvest_end=16,
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
        # 12 and 16 weeks after 9 April 2026: 2 July 2026 and 30 July 2026.
        assert harvest[0].start_date == datetime.date(2026, 7, 2)
        assert harvest[0].end_date == datetime.date(2026, 7, 30)

    def test_the_harvest_fields_are_documented_as_frost_relative(self) -> None:
        """Behaviour, not a comment string.

        An earlier version of this test asserted an exact comment literal, which
        breaks on any reformat and cannot notice a semantic change — exactly the
        mistake the class docstring above warns about. What actually matters is
        that the generator is frost-relative, which
        ``test_every_reader_anchors_on_the_frost_date`` already pins by produced
        date. This test only checks the model exposes the offsets as weeks.
        """
        garlic = next(
            sp for sp in _species(_rows())
            if sp.scientific_name == "Allium sativum"
        )
        assert isinstance(garlic.harvest_start, int)
        assert isinstance(garlic.harvest_end, int)

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

    def test_garlic_harvest_lands_after_sowing_and_before_next_sowing(self) -> None:
        """#416 and #418: garlic harvest is in July, strictly between autumn sowings.

        Sown 26..24 weeks before frost (October). Corrected harvest window is
        12..16 weeks after frost (July), well before the next autumn's sowing.
        """
        garlic = next(
            sp for sp in _species(_rows())
            if sp.scientific_name == "Allium sativum"
        )
        assert (garlic.harvest_start, garlic.harvest_end) == (12, 16)
        assert (garlic.direct_sow_start, garlic.direct_sow_end) == (-26, -24)
        assert garlic.days_to_maturity_min == 240
        assert garlic.days_to_maturity_max == 270

        # With an April 9 spring frost:
        last_frost_2026 = datetime.date(2026, 4, 9)
        last_frost_2027 = datetime.date(2027, 4, 9)

        sow_start = last_frost_2026 + datetime.timedelta(weeks=garlic.direct_sow_start)
        sow_end = last_frost_2026 + datetime.timedelta(weeks=garlic.direct_sow_end)
        harvest_start = last_frost_2026 + datetime.timedelta(weeks=garlic.harvest_start)
        harvest_end = last_frost_2026 + datetime.timedelta(weeks=garlic.harvest_end)
        next_sow_start = last_frost_2027 + datetime.timedelta(weeks=garlic.direct_sow_start)

        # Harvest lands strictly after sowing and before next autumn sowing
        assert sow_start < sow_end < harvest_start < harvest_end < next_sow_start
        assert harvest_start == datetime.date(2026, 7, 2)
        assert harvest_end == datetime.date(2026, 7, 30)

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
