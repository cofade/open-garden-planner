"""Tests for the duplicate-record guard helper (F2.6c / F12).

The helper backs the no-op guard in ``_open_soil_test_dialog`` so clicking
OK without changing anything (common after Edit-via-History) does not
append a stale duplicate of the latest record.
"""
from __future__ import annotations

from open_garden_planner.app.application import _records_equivalent
from open_garden_planner.models.soil_test import SoilTestRecord


def _record(**kwargs) -> SoilTestRecord:
    defaults = {"date": "2026-04-01"}
    defaults.update(kwargs)
    return SoilTestRecord(**defaults)


class TestRecordsEquivalent:
    def test_identical_records_are_equivalent(self) -> None:
        a = _record(ph=6.5, n_level=2, p_level=3, notes="ok")
        b = _record(ph=6.5, n_level=2, p_level=3, notes="ok")
        assert _records_equivalent(a, b) is True

    def test_different_id_still_equivalent(self) -> None:
        # id and date are intentionally ignored.
        a = _record(ph=6.5, n_level=2)
        b = _record(ph=6.5, n_level=2, date="2099-12-31")
        assert _records_equivalent(a, b) is True

    def test_different_ph_not_equivalent(self) -> None:
        a = _record(ph=6.5)
        b = _record(ph=5.5)
        assert _records_equivalent(a, b) is False

    def test_different_n_level_not_equivalent(self) -> None:
        a = _record(n_level=2)
        b = _record(n_level=3)
        assert _records_equivalent(a, b) is False

    def test_different_notes_not_equivalent(self) -> None:
        a = _record(notes="initial")
        b = _record(notes="revised")
        assert _records_equivalent(a, b) is False

    def test_none_inputs_never_equivalent(self) -> None:
        a = _record()
        assert _records_equivalent(None, a) is False
        assert _records_equivalent(a, None) is False
        assert _records_equivalent(None, None) is False

    def test_ppm_fields_compared(self) -> None:
        a = _record(n_ppm=12.5)
        b = _record(n_ppm=15.0)
        assert _records_equivalent(a, b) is False

    def test_secondary_levels_compared(self) -> None:
        a = _record(ca_level=1, mg_level=1, s_level=2)
        b = _record(ca_level=1, mg_level=2, s_level=2)
        assert _records_equivalent(a, b) is False
