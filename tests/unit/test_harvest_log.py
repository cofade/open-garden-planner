"""Unit tests for the harvest log model + yield aggregation (US-C1, #188)."""

from open_garden_planner.models.harvest_log import HarvestEntry, HarvestLogHistory
from open_garden_planner.services.harvest_aggregation import (
    aggregate_yields,
    all_years,
)


class TestHarvestEntry:
    def test_round_trip_full(self) -> None:
        entry = HarvestEntry(
            date="2026-06-15",
            quantity=1.5,
            unit="kg",
            quality="excellent",
            notes="first pick",
            photo_path="harvest_photos/a.jpg",
            journal_note_id="note-1",
            id="e1",
        )
        restored = HarvestEntry.from_dict(entry.to_dict())
        assert restored == entry

    def test_to_dict_omits_empty_optionals(self) -> None:
        d = HarvestEntry(date="2026-06-15", quantity=200, unit="g", id="e1").to_dict()
        assert "quality" not in d
        assert "notes" not in d
        assert "photo_path" not in d
        assert "journal_note_id" not in d

    def test_from_dict_forgiving(self) -> None:
        entry = HarvestEntry.from_dict({"date": "2026-07-01"})
        assert entry.quantity == 0.0
        assert entry.unit == "g"
        assert entry.id  # generated

    def test_from_dict_bad_quantity_defaults_zero(self) -> None:
        assert HarvestEntry.from_dict({"quantity": "not-a-number"}).quantity == 0.0

    def test_year_property(self) -> None:
        assert HarvestEntry(date="2026-06-15").year == 2026
        assert HarvestEntry(date="").year is None
        assert HarvestEntry(date="bad").year is None


class TestHarvestLogHistory:
    def test_round_trip(self) -> None:
        hist = HarvestLogHistory(
            target_id="plant-1",
            entries=[
                HarvestEntry(date="2026-06-15", quantity=1.0, unit="kg", id="a"),
                HarvestEntry(date="2026-07-20", quantity=2.0, unit="kg", id="b"),
            ],
        )
        restored = HarvestLogHistory.from_dict(hist.to_dict())
        assert restored == hist


class TestAggregateYields:
    def test_per_species_per_year_totals(self) -> None:
        logs = {
            "p1": HarvestLogHistory(
                "p1",
                [
                    HarvestEntry(date="2025-06-01", quantity=1.0, unit="kg", id="a"),
                    HarvestEntry(date="2026-06-01", quantity=2.0, unit="kg", id="b"),
                    HarvestEntry(date="2026-07-01", quantity=0.5, unit="kg", id="c"),
                ],
            ).to_dict(),
        }
        rows = aggregate_yields(logs, {"p1": "Tomato"})
        assert len(rows) == 1
        row = rows[0]
        assert row.species == "Tomato"
        assert row.unit == "kg"
        assert row.totals_by_year == {2025: 1.0, 2026: 2.5}
        assert row.total == 3.5
        assert all_years(rows) == [2025, 2026]

    def test_mixed_units_split_into_rows(self) -> None:
        logs = {
            "p1": HarvestLogHistory(
                "p1",
                [
                    HarvestEntry(date="2026-06-01", quantity=500, unit="g", id="a"),
                    HarvestEntry(date="2026-06-02", quantity=3, unit="pcs", id="b"),
                ],
            ).to_dict(),
        }
        rows = aggregate_yields(logs, {"p1": "Zucchini"})
        units = {r.unit: r.total for r in rows}
        assert units == {"g": 500, "pcs": 3}

    def test_unknown_target_falls_back_to_id(self) -> None:
        logs = {
            "p9": HarvestLogHistory(
                "p9", [HarvestEntry(date="2026-06-01", quantity=1, unit="kg", id="a")]
            ).to_dict(),
        }
        rows = aggregate_yields(logs, {})
        assert rows[0].species == "p9"

    def test_entry_without_year_counts_in_total_only(self) -> None:
        logs = {
            "p1": HarvestLogHistory(
                "p1",
                [
                    HarvestEntry(date="", quantity=1.0, unit="kg", id="a"),
                    HarvestEntry(date="2026-06-01", quantity=2.0, unit="kg", id="b"),
                ],
            ).to_dict(),
        }
        rows = aggregate_yields(logs, {"p1": "Bean"})
        assert rows[0].total == 3.0
        assert rows[0].totals_by_year == {2026: 2.0}
