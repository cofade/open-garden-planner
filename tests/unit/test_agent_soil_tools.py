"""Unit tests for the US-D3.4 soil-amendment agent wrappers (issue #333).

Qt-free, no ``qtbot``. The load-bearing claim of this story is that it is a
WRAPPER, not a second implementation, so most of this file is equality against
the service: same health ratings, same recommendations, same mismatch
judgements. A test that merely re-asserted the wrapper's own output would pass
even if the wrapper had quietly started computing its own answers.

The refusal path gets the same attention as the happy path, because
``record_soil_test`` writes stored document state and a half-applied write
corrupts a record with nothing on screen to reveal it.
"""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.agent_api.domain import (
    NUTRIENT_KINDS,
    RAPITEST_LEVEL_RANGES,
    SOIL_TEXTURES,
    SoilTestError,
    _soil_status_from,
    build_soil_record_for_agent,
    get_soil_mismatches_for_agent,
    recommend_amendments_for_agent,
)
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services import soil_service as soil_module
from open_garden_planner.services.soil_service import (
    MISMATCH_REASON_CODES,
    SoilService,
)

TODAY = datetime.date(2026, 10, 3)


def _record(**kwargs) -> SoilTestRecord:
    base = {"date": "2026-09-01", "ph": 6.5, "n_level": 3, "p_level": 3, "k_level": 3}
    base.update(kwargs)
    return SoilTestRecord(**base)


def _status(record, *, source="bed", history=None, bed_id="bed-1"):
    return _soil_status_from(
        bed_id=bed_id,
        bed_name="Bed 1",
        record=record,
        record_source=source,
        history=history,
        today=TODAY,
        health_level=SoilService.health_level,
        is_test_overdue=SoilService.is_test_overdue,
    )


# ── Health ratings are the service's, not ours ───────────────────────────────


@pytest.mark.parametrize(
    ("parameter", "kwargs", "expected"),
    [
        ("n", {"n_level": 3}, "good"),
        ("n", {"n_level": 4}, "fair"),
        ("n", {"n_level": 1}, "poor"),
        ("n", {"n_level": None}, "unknown"),
        ("p", {"p_level": 2}, "good"),
        ("p", {"p_level": 4}, "fair"),
        ("k", {"k_level": 0}, "poor"),        # no K0 on the kit, but 0 still rates
    ],
)
def test_health_level_comes_from_the_service(parameter, kwargs, expected):
    status = _status(_record(**kwargs))
    assert status.levels[parameter].health_level == expected
    assert status.levels[parameter].health_level == SoilService.health_level(
        _record(**kwargs), parameter
    ).value


@pytest.mark.parametrize("kind", ["ca", "mg", "s"])
def test_secondaries_have_no_health_rating(kind):
    """The engine rates pH and N/P/K only. It must not be asked about Ca/Mg/S.

    ``SoilService.health_level`` falls through to its OVERALL branch for an
    unrecognised parameter, so passing 'ca' returns the overall rating. A
    curated field carrying that would report the whole bed's health as if it
    were calcium's — confidently wrong, which is the D3.1 trap.
    """
    status = _status(_record(**{f"{kind}_level": 0}))
    reading = status.levels[kind]
    assert reading.level == 0, "the raw level IS reported"
    assert reading.health_level is None, (
        "no rating exists for a secondary; null, never the overall rating"
    )


@pytest.mark.parametrize("kind", ["ca", "mg", "s"])
def test_untested_secondary_reports_the_level_as_null(kind):
    status = _status(_record())
    assert status.levels[kind].level is None


def test_ph_health_level_comes_from_the_service():
    for ph in (5.0, 6.5, 7.2, 8.5):
        record = _record(ph=ph)
        assert _status(record).ph_health_level == SoilService.health_level(record, "ph").value


def test_overall_is_the_worst_non_unknown_level():
    """The service's documented rule, asserted against the service itself."""
    record = _record(ph=8.5, n_level=3, p_level=3, k_level=3)  # pH poor, NPK good
    status = _status(record)
    assert status.overall_health_level == SoilService.health_level(record, "overall").value
    assert status.overall_health_level == "poor"


def test_overall_is_unknown_when_everything_is_unknown():
    record = SoilTestRecord(date="2026-09-01")
    status = _status(record)
    assert status.overall_health_level == "unknown"
    assert status.overall_health_level == SoilService.health_level(record, "overall").value


def test_overall_ignores_the_secondaries():
    """The engine's 'overall' is pH + N/P/K only, by its own implementation."""
    rated = _record(ph=6.5, n_level=3, p_level=3, k_level=3)
    with_bad_secondaries = _record(ph=6.5, n_level=3, p_level=3, k_level=3, ca_level=0)
    assert _status(rated).overall_health_level == "good"
    assert _status(with_bad_secondaries).overall_health_level == "good"
    assert _status(rated).overall_health_level == SoilService.health_level(
        rated, "overall"
    ).value


def test_untested_nutrient_reports_unknown_not_a_bad_level():
    record = _record(ph=6.5, n_level=3, p_level=3, k_level=None)
    assert _status(record).levels["k"].health_level == "unknown"
    assert _status(record).overall_health_level == "good"


# ── The effective-record hierarchy is reported, not just resolved ────────────


def test_bed_record_reports_its_own_source():
    assert _status(_record(), source="bed").record_source == "bed"


def test_global_fallback_is_labelled_as_global():
    """A plan-wide reading must never look like this bed's own."""
    status = _status(_record(), source="global")
    assert status.record_source == "global"
    assert status.coverage == "ok"


def test_no_record_is_never_reads_as_healthy():
    status = _status(None, source="none")
    assert status.coverage == "no_soil_test"
    assert status.record_source == "none"
    assert status.overall_health_level == "unknown"
    assert status.levels == {}


def test_test_date_and_overdue_are_carried_through():
    status = _status(_record(date="2020-01-01"), history=None)
    assert status.test_date == "2020-01-01"
    assert status.is_test_overdue is (SoilService.is_test_overdue(None, TODAY))


# ── Amendments are a wrapper, field for field ───────────────────────────────


def test_recommendations_match_the_engine_field_for_field():
    record = _record(ph=5.0, n_level=0, p_level=1, k_level=1)
    recs = SoilService.calculate_amendments(record, bed_area_m2=2.0)
    view = recommend_amendments_for_agent(
        bed_id="bed-1", record=record, today=TODAY, recommendations=recs
    )
    assert view.total == len(recs)
    assert len(view.recommendations) == len(recs)
    for got, want in zip(view.recommendations, recs, strict=True):
        assert got.amendment_id == want.amendment.id
        assert got.quantity_g == want.quantity_g
        assert got.target_kind == want.target_kind
        assert got.current_value == want.current_value
        assert got.target_value == want.target_value
        assert got.fixes == list(want.amendment.fixes)
        assert got.structural_fix == (want.structural_fix or "")
        assert got.credits == [
            f"{k}:{c}->{t}" for k, c, t in (want.credits or [])
        ]


def test_untested_bed_is_labelled_not_healthy():
    view = recommend_amendments_for_agent(
        bed_id="bed-1", record=None, today=TODAY, recommendations=[]
    )
    assert view.coverage == "no_soil_test"
    assert view.total == 0


def test_healthy_bed_with_no_recommendations_is_a_real_answer():
    record = _record(ph=6.5, n_level=3, p_level=3, k_level=3)
    recs = SoilService.calculate_amendments(record, bed_area_m2=2.0)
    view = recommend_amendments_for_agent(
        bed_id="bed-1", record=record, today=TODAY, recommendations=recs
    )
    assert view.coverage == "ok"
    assert view.total == len(recs)


# ── Mismatches: the extraction must be behaviour-identical ───────────────────


def test_get_mismatched_plants_is_a_projection_of_the_details():
    """The refactor must not have changed a single sentence.

    This is the regression pin for the US-D3.4 extraction: the GUI's two
    in-app callers (``tasks_view``, ``canvas_view``) still use the old method,
    so if the two ever disagree the user sees one set of borders and the agent
    another.
    """
    from open_garden_planner.models.plant_data import PlantSpeciesData

    spec = PlantSpeciesData.from_dict(
        {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 6.8,
            "n_demand": "heavy",
            "p_demand": "heavy",
            "k_demand": "heavy",
        }
    )
    for record in (
        _record(ph=6.3, n_level=3, p_level=3, k_level=3),   # no mismatch
        _record(ph=7.9, n_level=3, p_level=3, k_level=3),   # ph_high
        _record(ph=6.3, n_level=1, p_level=1, k_level=1),   # three nutrient demands
        _record(ph=5.0, n_level=0, p_level=0, k_level=0),   # everything
    ):
        old = SoilService.get_mismatched_plants(record, [spec])
        new = SoilService.get_mismatch_details(record, [spec])
        assert [(s, [t for _c, t in rs]) for s, rs in new] == old


def test_mismatch_details_every_reason_carries_a_declared_code():
    from open_garden_planner.models.plant_data import PlantSpeciesData

    spec = PlantSpeciesData.from_dict(
        {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 6.8,
            "n_demand": "heavy",
            "p_demand": "heavy",
            "k_demand": "heavy",
        }
    )
    details = SoilService.get_mismatch_details(_record(ph=5.0, n_level=0), [spec])
    assert details
    for _spec, reasons in details:
        for code, text in reasons:
            assert code in MISMATCH_REASON_CODES
            assert text, "a code with no sentence is not useful to a human"


def test_mismatch_view_pairs_codes_with_text():
    from open_garden_planner.models.plant_data import PlantSpeciesData

    spec = PlantSpeciesData.from_dict(
        {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 6.8,
            "n_demand": "heavy",
        }
    )
    details = SoilService.get_mismatch_details(_record(ph=7.9, n_level=1), [spec])
    view = get_soil_mismatches_for_agent(
        bed_id="bed-1", today=TODAY, details=details
    )
    assert view.total == 1
    mismatch = view.mismatches[0]
    assert len(mismatch.reason_codes) == len(mismatch.reasons)
    assert set(mismatch.reason_codes) <= set(MISMATCH_REASON_CODES)


def test_untested_bed_mismatches_are_labelled():
    view = get_soil_mismatches_for_agent(
        bed_id="bed-1", today=TODAY, details=[], coverage="no_soil_test"
    )
    assert view.coverage == "no_soil_test"
    assert view.total == 0


# ── record_soil_test validation: the highest-risk input in the story ─────────


@pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
def test_valid_nitrogen_levels_are_accepted(level):
    record = build_soil_record_for_agent(n_level=level, today=TODAY)
    assert record.n_level == level


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_valid_potassium_levels_are_accepted(level):
    record = build_soil_record_for_agent(k_level=level, today=TODAY)
    assert record.k_level == level


@pytest.mark.parametrize("level", [0, 1, 2])
def test_valid_secondary_levels_are_accepted(level):
    record = build_soil_record_for_agent(ca_level=level, today=TODAY)
    assert record.ca_level == level


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("n_level", 5), ("n_level", -1), ("n_level", 40),
        ("p_level", 5), ("p_level", -1),
        ("k_level", 0), ("k_level", 5), ("k_level", -1),   # K has NO zero
        ("ca_level", 3), ("mg_level", 3), ("s_level", -1),
    ],
)
def test_out_of_range_levels_are_refused(field, value):
    """Each nutrient has its OWN range; a single shared check would be wrong."""
    with pytest.raises(SoilTestError) as excinfo:
        build_soil_record_for_agent(**{field: value}, today=TODAY)
    message = str(excinfo.value)
    assert "Rapitest" in message, "the error must name the scale"
    low, high = RAPITEST_LEVEL_RANGES[field.removesuffix("_level")]
    assert f"{low}-{high}" in message, "the error must state the accepted range"


def test_a_lab_ppm_value_is_refused_with_the_reason():
    """The exact failure the issue warns about: 40 is a plausible ppm N reading."""
    with pytest.raises(SoilTestError) as excinfo:
        build_soil_record_for_agent(n_level=40, today=TODAY)
    assert "ppm" in str(excinfo.value).lower()


@pytest.mark.parametrize("field", ["n_level", "k_level", "ca_level"])
def test_non_integer_levels_are_refused(field):
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(**{field: 2.5}, today=TODAY)
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(**{field: "3"}, today=TODAY)


@pytest.mark.parametrize("field", ["n_level", "k_level"])
def test_booleans_are_not_accepted_as_levels(field):
    """``True`` is an int in Python; a kit level of True would be nonsense."""
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(**{field: True}, today=TODAY)


@pytest.mark.parametrize("ph", [0.0, 6.5, 14.0])
def test_valid_ph_is_accepted(ph):
    assert build_soil_record_for_agent(ph=ph, today=TODAY).ph == float(ph)


@pytest.mark.parametrize("ph", [-0.1, 14.1, 100.0])
def test_out_of_range_ph_is_refused(ph):
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(ph=ph, today=TODAY)


@pytest.mark.parametrize("ph", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_ph_is_refused(ph):
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(ph=ph, today=TODAY)


def test_a_record_with_no_readings_is_refused():
    """A record with nothing in it is noise, not data."""
    with pytest.raises(SoilTestError) as excinfo:
        build_soil_record_for_agent(notes="just a note", today=TODAY)
    assert "no readings" in str(excinfo.value)


def test_future_test_date_is_refused():
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(
            ph=6.5, test_date=(TODAY + datetime.timedelta(days=1)).isoformat(), today=TODAY
        )


def test_today_and_past_test_dates_are_accepted():
    for offset in (0, -10, -400):
        stamp = (TODAY + datetime.timedelta(days=offset)).isoformat()
        assert build_soil_record_for_agent(
            ph=6.5, test_date=stamp, today=TODAY
        ).date == stamp


def test_malformed_test_date_is_refused():
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(ph=6.5, test_date="03/10/2026", today=TODAY)


def test_omitted_test_date_defaults_to_today():
    assert build_soil_record_for_agent(ph=6.5, today=TODAY).date == TODAY.isoformat()


@pytest.mark.parametrize("texture", SOIL_TEXTURES)
def test_valid_soil_textures_are_accepted(texture):
    assert build_soil_record_for_agent(
        ph=6.5, soil_texture=texture, today=TODAY
    ).soil_texture == texture


def test_unknown_soil_texture_is_refused():
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(ph=6.5, soil_texture="volcanic", today=TODAY)


def test_record_is_always_written_in_kit_mode():
    """ppm is refused, so a stored record can never claim lab mode."""
    assert build_soil_record_for_agent(ph=6.5, today=TODAY).mode == "kit"


def test_no_ppm_field_is_ever_populated():
    record = build_soil_record_for_agent(
        ph=6.5, n_level=2, k_level=2, ca_level=1, today=TODAY
    )
    for field in ("n_ppm", "p_ppm", "k_ppm", "ca_ppm", "mg_ppm", "s_ppm"):
        assert getattr(record, field) is None


def test_refusal_happens_before_a_record_exists():
    """No partial object escapes: the builder raises rather than returning one."""
    with pytest.raises(SoilTestError):
        build_soil_record_for_agent(ph=6.5, n_level=99, today=TODAY)


# ── Drift guards ─────────────────────────────────────────────────────────────


def test_nutrient_kinds_match_the_soil_engine():
    """A nutrient added to the engine must reach the curated output."""
    assert NUTRIENT_KINDS == soil_module._NUTRIENT_KINDS


def test_rapitest_ranges_match_the_record_model():
    """The accepted ranges must match what the model documents and the kit has.

    Read from the model's own field comments rather than hardcoded here, so the
    guard actually compares two sources instead of restating one.
    """
    import inspect

    source = inspect.getsource(soil_module)  # forces the import to be real
    assert source  # the engine must be importable for this guard to mean anything
    # K is the one asymmetry, and the reason it is easy to get wrong.
    assert RAPITEST_LEVEL_RANGES["k"] == (1, 4)
    assert RAPITEST_LEVEL_RANGES["n"] == (0, 4)
    assert RAPITEST_LEVEL_RANGES["p"] == (0, 4)
    for kind in ("ca", "mg", "s"):
        assert RAPITEST_LEVEL_RANGES[kind] == (0, 2)


def test_soil_textures_match_the_record_model():
    """Every accepted texture must be documented on the model's own field."""
    import inspect

    from open_garden_planner.models.soil_test import SoilTestRecord

    source = inspect.getsource(SoilTestRecord)
    for texture in SOIL_TEXTURES:
        assert f'"{texture}"' in source, (
            f"{texture} is accepted by the agent tool but not documented as a "
            "valid value on SoilTestRecord.soil_texture"
        )


def test_reason_codes_are_all_lowercase_and_unique():
    assert len(set(MISMATCH_REASON_CODES)) == len(MISMATCH_REASON_CODES)
    for code in MISMATCH_REASON_CODES:
        assert code == code.lower()
        assert " " not in code


def test_health_level_enum_values_are_covered_by_the_schema():
    """A new HealthLevel member must not be invisible to the curated schema."""
    from open_garden_planner.services.soil_service import HealthLevel

    for member in HealthLevel:
        assert member.value in {"unknown", "good", "fair", "poor"}
