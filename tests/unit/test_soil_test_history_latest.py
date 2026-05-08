"""Regression tests for SoilTestHistory.latest tie-breaking (US-12.10/F2.10a).

When two records share the same ISO date, ``.latest`` must return the
*most-recently-appended* one. Python's ``max(records, key=date)`` returns
the first-encountered tie, which would silently hide a freshly-saved
Lab-mode record behind an existing Kit-mode record on the same day.
"""
from __future__ import annotations

from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord


class TestLatestTieBreak:
    def test_same_date_returns_last_appended(self) -> None:
        history = SoilTestHistory(
            target_id="bed-1",
            records=[
                SoilTestRecord(date="2026-05-02", mode="kit", n_level=0),
                SoilTestRecord(date="2026-05-02", mode="lab", n_ppm=12.5),
            ],
        )
        latest = history.latest
        assert latest is not None
        assert latest.mode == "lab"
        assert latest.n_ppm == 12.5

    def test_different_dates_returns_max_date(self) -> None:
        history = SoilTestHistory(
            target_id="bed-1",
            records=[
                SoilTestRecord(date="2026-05-02", mode="lab"),
                SoilTestRecord(date="2026-05-01", mode="kit"),
            ],
        )
        latest = history.latest
        assert latest is not None
        assert latest.date == "2026-05-02"
        assert latest.mode == "lab"

    def test_empty_history_returns_none(self) -> None:
        history = SoilTestHistory(target_id="bed-1", records=[])
        assert history.latest is None

    def test_three_same_date_picks_last(self) -> None:
        history = SoilTestHistory(
            target_id="bed-1",
            records=[
                SoilTestRecord(date="2026-05-02", mode="kit", notes="first"),
                SoilTestRecord(date="2026-05-02", mode="lab", notes="middle"),
                SoilTestRecord(date="2026-05-02", mode="kit", notes="last"),
            ],
        )
        latest = history.latest
        assert latest is not None
        assert latest.notes == "last"


class TestSoilTextureRoundTrip:
    """US-12.11: ``soil_texture`` survives ``to_dict`` / ``from_dict``."""

    def test_none_is_omitted_from_dict(self) -> None:
        record = SoilTestRecord(date="2026-05-02")
        d = record.to_dict()
        assert "soil_texture" not in d
        assert SoilTestRecord.from_dict(d).soil_texture is None

    def test_each_texture_value_round_trips(self) -> None:
        for texture in ("sandy", "loamy", "clayey", "compacted"):
            record = SoilTestRecord(date="2026-05-02", soil_texture=texture)
            restored = SoilTestRecord.from_dict(record.to_dict())
            assert restored.soil_texture == texture
