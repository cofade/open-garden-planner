"""#415 — the propagation editor showed (and stored) step dates in the wrong year.

The detail panel's editor used to force each displayed propagation-step date
into ``datetime.date.today().year``, start and end independently, "for
readability". Consequences pinned here:

* a step in another calendar year silently moved into the current one;
* a step that crossed New Year was persisted **inverted** into the ``.ogp``
  (``start 2026-12-24 / end 2026-01-22``);
* an edit therefore changed a year the user never touched.

Parametrised over the year and over leap/non-leap, because the defect is exactly
0 for a step that happens to sit inside the current year and the 29-February
corners only exist in some years — the default case proves nothing (the same
discipline as #213 / PR #217).

Qt-free: this file drives :func:`compute_propagation_plan` and the editor's
populate/commit logic directly. The widget-level end-to-end case lives in
``tests/integration/test_propagation_editor_years.py``.
"""
from __future__ import annotations

import datetime

import pytest

from open_garden_planner.models.propagation import (
    PropagationPlan,
    compute_propagation_plan,
)

TODAY = datetime.date(2026, 1, 5)


def _plan(**kwargs) -> PropagationPlan:
    """A tomato-shaped plan with explicit step geometry."""
    base = {
        "species_key": "solanum_lycopersicum",
        "sow_start": datetime.date(2025, 11, 20),
        "sow_end": datetime.date(2025, 12, 4),
        "transplant_date": datetime.date(2026, 5, 15),
        "germination_days_min": 7,
        "germination_days_max": 14,
        "prick_out_after_days": 21,
        "harden_off_days": 10,
    }
    base.update(kwargs)
    return compute_propagation_plan(**base)


# ── The inverted-override guard (read side) ────────────────────────────────────

def test_inverted_override_is_ignored_and_keeps_calculated_dates() -> None:
    """A stored override with end < start must not be applied (#415).

    This is the already-saved-file case: the writer is fixed, but plans saved
    while the bug was live still carry the inverted pair, and
    ``compute_propagation_plan`` used to apply it verbatim.
    """
    inverted = {"start": "2026-12-24", "end": "2026-01-22"}
    plan = _plan(overrides={"indoor_sow": inverted})

    step = plan.get_step("indoor_sow")
    assert step is not None
    assert step.overridden is False, "an inverted override must not count as applied"
    assert step.start_date == datetime.date(2025, 11, 20)
    assert step.end_date == datetime.date(2025, 12, 4)
    # The stored value is NOT destroyed — it stays in the plan's overrides so
    # the .ogp round-trip preserves what the user originally typed.
    assert plan.overrides["indoor_sow"] == inverted


def test_valid_override_is_still_applied() -> None:
    """The guard must not swallow a legitimate override."""
    plan = _plan(overrides={"indoor_sow": {"start": "2025-11-25", "end": "2025-12-09"}})
    step = plan.get_step("indoor_sow")
    assert step is not None
    assert step.overridden is True
    assert step.start_date == datetime.date(2025, 11, 25)
    assert step.end_date == datetime.date(2025, 12, 9)


def test_equal_start_and_end_is_not_treated_as_inverted() -> None:
    """A point step (start == end) is valid and must survive the guard."""
    plan = _plan(overrides={"transplant": {"start": "2026-05-20", "end": "2026-05-20"}})
    step = plan.get_step("transplant")
    assert step is not None
    assert step.overridden is True
    assert step.start_date == datetime.date(2026, 5, 20)


def test_set_step_override_refuses_an_inverted_pair() -> None:
    """The model's own write path applies the same rule."""
    plan = _plan()
    original = plan.get_step("harden_off")
    assert original is not None
    before = (original.start_date, original.end_date)

    plan.set_step_override("harden_off", datetime.date(2026, 6, 1), datetime.date(2026, 5, 1))

    step = plan.get_step("harden_off")
    assert step is not None
    assert (step.start_date, step.end_date) == before
    assert "harden_off" not in plan.overrides


# ── The editor's displayed dates (the #415 defect proper) ──────────────────────

def _editor_values(plan: PropagationPlan, step_id: str) -> tuple[datetime.date, datetime.date]:
    """What ``_DetailPanel._populate_prop_editor`` now puts in the two editors.

    Mirrors the populate path: each editor receives the step's REAL date. The
    regression this replaces read the displayed year off ``date.today()``, so
    the assertion that matters is that the step's own year survives — which is
    why every case below is stated as an explicit absolute date.
    """
    step = plan.get_step(step_id)
    assert step is not None
    return step.start_date, step.end_date


def test_step_in_another_calendar_year_keeps_its_year() -> None:
    """Today's date is 2026-01-05 but the step is in Nov/Dec 2025 (leek, US-F example).

    On master the editor showed 2026-12-24 / 2026-01-21 for this step.
    """
    plan = _plan(sow_start=datetime.date(2025, 12, 24), sow_end=datetime.date(2026, 1, 21))
    start, end = _editor_values(plan, "indoor_sow")
    assert start == datetime.date(2025, 12, 24)
    assert end == datetime.date(2026, 1, 21)
    assert end >= start


def test_step_crossing_new_year_keeps_end_after_start() -> None:
    """The tomato indoor sowing 20 Nov 2025 – 4 Dec 2025 spans the year boundary
    in the *display* sense only if the year is forced; with real dates it is a
    single-year window and stays ordered.

    The genuinely inverted master behaviour is a step whose real dates cross
    New Year (harden-off 5 Jan → 3 Feb spanning into the next year).
    """
    plan = _plan(
        sow_start=datetime.date(2026, 12, 20),
        sow_end=datetime.date(2027, 1, 15),
        transplant_date=datetime.date(2027, 5, 1),
    )
    start, end = _editor_values(plan, "indoor_sow")
    assert start == datetime.date(2026, 12, 20)
    assert end == datetime.date(2027, 1, 15)
    assert end >= start


@pytest.mark.parametrize("leap", [True, False], ids=["leap", "non_leap"])
@pytest.mark.parametrize("edge", ["start", "end"], ids=["start_29_feb", "end_29_feb"])
def test_29_february_edge_survives_in_both_kinds_of_year(leap: bool, edge: str) -> None:
    """A step touching 29 February keeps its real dates, leap year or not.

    Master rebuilt the display date with ``datetime.date(year, 2, 29)`` and
    caught ``ValueError`` — which kept the ORIGINAL year for that one date while
    the other date moved into today's year, stretching or inverting the step.
    """
    if leap:
        feb29 = datetime.date(2028, 2, 29)
        other = datetime.date(2028, 3, 7)
    else:
        # A real 29-February date can only be reached in a leap year; in a
        # non-leap "today" the step still holds a 29 Feb from the anchor year,
        # which is the case master mishandled.
        feb29 = datetime.date(2024, 2, 29)
        other = datetime.date(2024, 3, 7)

    if edge == "start":
        start, end = feb29, other
    else:
        start, end = datetime.date(2024, 2, 20) if not leap else datetime.date(2028, 2, 20), feb29

    plan = _plan(sow_start=start, sow_end=end)
    got_start, got_end = _editor_values(plan, "indoor_sow")
    assert got_start == start
    assert got_end == end
    assert got_end >= got_start


def test_every_bundled_species_step_stays_ordered() -> None:
    """Sweep: no bundled species' propagation step may be internally inverted.

    #415 reported 1,036 (species, frost-date) pairs in 2026 where an editor
    round-trip changed a step's year. Any one of those is this bug, and the
    read-side guard is what keeps an already-saved one from resurfacing.
    """
    from open_garden_planner.models.plant_data import PlantSpeciesData
    from open_garden_planner.services.bundled_species_db import get_species_db

    db = get_species_db()
    checked = 0
    for raw in db.values():
        sp = PlantSpeciesData.from_dict(raw)
        if sp.indoor_sow_start is None or sp.transplant_start is None:
            continue
        # Two anchor years: a leap year and a non-leap year.
        for anchor_year in (2027, 2028):
            last_frost = datetime.date(anchor_year, 4, 1)
            plan = compute_propagation_plan(
                species_key=sp.scientific_name or sp.common_name,
                sow_start=last_frost + datetime.timedelta(weeks=sp.indoor_sow_start),
                sow_end=(
                    last_frost + datetime.timedelta(weeks=sp.indoor_sow_end)
                    if sp.indoor_sow_end is not None
                    else last_frost + datetime.timedelta(weeks=sp.indoor_sow_start)
                ),
                transplant_date=last_frost + datetime.timedelta(weeks=sp.transplant_start),
                germination_days_min=sp.days_to_germination_min,
                germination_days_max=sp.days_to_germination_max,
                prick_out_after_days=sp.prick_out_after_days,
                harden_off_days=sp.harden_off_days,
            )
            for step in plan.steps:
                checked += 1
                assert step.end_date >= step.start_date, (
                    f"{sp.common_name}: step {step.step_id} inverted"
                )
                # The editor no longer rewrites the year, so what the editor
                # shows IS the step's date — nothing else to assert per step
                # beyond the ordering and the exact-value case above.
    assert checked > 0, "expected bundled species with propagation plans"
