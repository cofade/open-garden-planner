"""Unit tests for models/propagation.py — US-9.5."""
import datetime

import pytest

from open_garden_planner.models.propagation import (
    STEP_IDS,
    PropagationPlan,
    PropagationStep,
    compute_propagation_plan,
)


# ── compute_propagation_plan ──────────────────────────────────────────────────


def _make_plan(**kwargs):
    """Helper: build a plan for tomato-like species with sensible defaults."""
    defaults = dict(
        species_key="tomato",
        sow_start=datetime.date(2025, 3, 1),
        sow_end=datetime.date(2025, 3, 15),
        transplant_date=datetime.date(2025, 5, 15),
        germination_days_min=7,
        germination_days_max=14,
        prick_out_after_days=21,
        harden_off_days=10,
    )
    defaults.update(kwargs)
    return compute_propagation_plan(**defaults)


class TestComputePropagationPlan:
    def test_returns_all_five_steps(self):
        plan = _make_plan()
        step_ids = {s.step_id for s in plan.steps}
        assert step_ids == set(STEP_IDS)

    def test_indoor_sow_dates(self):
        plan = _make_plan(
            sow_start=datetime.date(2025, 3, 1),
            sow_end=datetime.date(2025, 3, 15),
        )
        step = plan.get_step("indoor_sow")
        assert step is not None
        assert step.start_date == datetime.date(2025, 3, 1)
        assert step.end_date == datetime.date(2025, 3, 15)

    def test_germination_window(self):
        plan = _make_plan(
            sow_start=datetime.date(2025, 3, 1),
            germination_days_min=7,
            germination_days_max=14,
        )
        step = plan.get_step("germination")
        assert step is not None
        assert step.start_date == datetime.date(2025, 3, 8)
        assert step.end_date == datetime.date(2025, 3, 15)

    def test_prick_out_is_point_event(self):
        plan = _make_plan(
            sow_start=datetime.date(2025, 3, 1),
            prick_out_after_days=21,
        )
        step = plan.get_step("prick_out")
        assert step is not None
        assert step.start_date == step.end_date
        assert step.start_date == datetime.date(2025, 3, 22)

    def test_harden_off_dates(self):
        plan = _make_plan(
            transplant_date=datetime.date(2025, 5, 15),
            harden_off_days=10,
        )
        step = plan.get_step("harden_off")
        assert step is not None
        assert step.end_date == datetime.date(2025, 5, 15)
        assert step.start_date == datetime.date(2025, 5, 5)

    def test_transplant_is_point_event(self):
        plan = _make_plan(transplant_date=datetime.date(2025, 5, 15))
        step = plan.get_step("transplant")
        assert step is not None
        assert step.start_date == step.end_date == datetime.date(2025, 5, 15)

    def test_defaults_used_when_none(self):
        plan = compute_propagation_plan(
            species_key="x",
            sow_start=datetime.date(2025, 3, 1),
            sow_end=datetime.date(2025, 3, 14),
            transplant_date=datetime.date(2025, 5, 1),
        )
        germ = plan.get_step("germination")
        assert germ is not None
        assert germ.start_date == datetime.date(2025, 3, 8)   # default 7 days
        assert germ.end_date == datetime.date(2025, 3, 15)     # default 14 days

        prick = plan.get_step("prick_out")
        assert prick is not None
        assert prick.start_date == datetime.date(2025, 3, 22)  # default 21 days

    def test_no_overrides_flag(self):
        plan = _make_plan()
        for step in plan.steps:
            assert not step.overridden

    def test_overrides_applied(self):
        overrides = {
            "prick_out": {"start": "2025-03-25", "end": "2025-03-25"},
        }
        plan = _make_plan(overrides=overrides)
        step = plan.get_step("prick_out")
        assert step is not None
        assert step.start_date == datetime.date(2025, 3, 25)
        assert step.overridden

    def test_malformed_override_ignored(self):
        overrides = {
            "prick_out": {"start": "not-a-date", "end": "also-not"},
        }
        plan = _make_plan(
            sow_start=datetime.date(2025, 3, 1),
            prick_out_after_days=21,
            overrides=overrides,
        )
        step = plan.get_step("prick_out")
        assert step is not None
        # Should use calculated date, not raise
        assert step.start_date == datetime.date(2025, 3, 22)
        assert not step.overridden


# ── PropagationPlan ──────────────────────────────────────────────────────────


class TestPropagationPlan:
    def test_get_step_returns_none_for_unknown(self):
        plan = _make_plan()
        assert plan.get_step("nonexistent") is None

    def test_set_step_override(self):
        plan = _make_plan()
        new_date = datetime.date(2025, 4, 1)
        plan.set_step_override("prick_out", new_date, new_date)

        step = plan.get_step("prick_out")
        assert step is not None
        assert step.start_date == new_date
        assert step.overridden
        assert plan.overrides["prick_out"]["start"] == "2025-04-01"

    def test_clear_override(self):
        plan = _make_plan()
        new_date = datetime.date(2025, 4, 1)
        plan.set_step_override("prick_out", new_date, new_date)
        plan.clear_override("prick_out")

        step = plan.get_step("prick_out")
        assert step is not None
        assert not step.overridden
        assert "prick_out" not in plan.overrides

    def test_to_dict_no_overrides(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert d["species_key"] == "tomato"
        assert "overrides" not in d  # omitted when empty

    def test_to_dict_with_overrides(self):
        plan = _make_plan()
        plan.set_step_override(
            "prick_out",
            datetime.date(2025, 4, 1),
            datetime.date(2025, 4, 1),
        )
        d = plan.to_dict()
        assert "overrides" in d
        assert "prick_out" in d["overrides"]

    def test_from_dict_roundtrip(self):
        plan = _make_plan()
        plan.set_step_override(
            "harden_off",
            datetime.date(2025, 5, 1),
            datetime.date(2025, 5, 10),
        )
        d = plan.to_dict()
        restored = PropagationPlan.from_dict(d)
        assert restored.species_key == "tomato"
        assert restored.overrides["harden_off"]["start"] == "2025-05-01"
