"""Unit tests for the pure harvest aggregation engine (US-C1, #188)."""
from __future__ import annotations

from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.services.harvest_aggregation import (
    HARVEST_CSV_HEADERS,
    aggregate_by_species_year,
    harvest_csv_rows,
)


def _history(
    target_id: str, species_key: str, species_name: str, records: list[HarvestRecord]
) -> dict:
    return HarvestHistory(
        target_id=target_id,
        species_key=species_key,
        species_name=species_name,
        records=records,
    ).to_dict()


class TestAggregateBySpeciesYear:
    def test_sums_same_species_year_unit(self) -> None:
        logs = {
            "t1": _history(
                "t1", "tomato", "Tomato",
                [
                    HarvestRecord(date="2026-06-15", quantity=2.5, unit="kg"),
                    HarvestRecord(date="2026-06-20", quantity=1.0, unit="kg"),
                ],
            ),
        }
        rows = aggregate_by_species_year(logs)
        assert len(rows) == 1
        assert rows[0].total_quantity == 3.5
        assert rows[0].entry_count == 2
        assert rows[0].unit == "kg"
        assert rows[0].year == 2026
        assert rows[0].species_name == "Tomato"

    def test_different_units_do_not_merge(self) -> None:
        logs = {
            "t1": _history(
                "t1", "tomato", "Tomato",
                [
                    HarvestRecord(date="2026-06-15", quantity=2.5, unit="kg"),
                    HarvestRecord(date="2026-06-20", quantity=4, unit="pcs"),
                ],
            ),
        }
        rows = aggregate_by_species_year(logs)
        assert len(rows) == 2
        units = {r.unit: r.total_quantity for r in rows}
        assert units == {"kg": 2.5, "pcs": 4.0}

    def test_sort_year_desc_then_name(self) -> None:
        logs = {
            "t1": _history("t1", "tomato", "Tomato",
                           [HarvestRecord(date="2025-06-15", quantity=1, unit="kg")]),
            "t2": _history("t2", "lettuce", "Lettuce",
                           [HarvestRecord(date="2026-06-15", quantity=2, unit="kg")]),
            "t3": _history("t3", "apple", "Apple",
                           [HarvestRecord(date="2026-08-15", quantity=3, unit="kg")]),
        }
        rows = aggregate_by_species_year(logs)
        assert [(r.year, r.species_name) for r in rows] == [
            (2026, "Apple"),
            (2026, "Lettuce"),
            (2025, "Tomato"),
        ]

    def test_unkeyed_targets_do_not_merge(self) -> None:
        # Two beds without a species key must stay separate (keyed by target id).
        logs = {
            "bedA": _history("bedA", "", "Bed A",
                             [HarvestRecord(date="2026-06-15", quantity=1, unit="kg")]),
            "bedB": _history("bedB", "", "Bed B",
                             [HarvestRecord(date="2026-06-15", quantity=2, unit="kg")]),
        }
        rows = aggregate_by_species_year(logs)
        assert len(rows) == 2
        assert {r.species_key for r in rows} == {"target:bedA", "target:bedB"}

    def test_skips_unparseable_dates(self) -> None:
        logs = {
            "t1": _history("t1", "tomato", "Tomato",
                           [
                               HarvestRecord(date="", quantity=1, unit="kg"),
                               HarvestRecord(date="bad", quantity=2, unit="kg"),
                               HarvestRecord(date="2026-06-15", quantity=3, unit="kg"),
                           ]),
        }
        rows = aggregate_by_species_year(logs)
        assert len(rows) == 1
        assert rows[0].total_quantity == 3

    def test_empty(self) -> None:
        assert aggregate_by_species_year({}) == []


class TestCsvRows:
    def test_headers_and_values(self) -> None:
        logs = {
            "t1": _history("t1", "tomato", "Tomato",
                           [HarvestRecord(date="2026-06-15", quantity=2.5, unit="kg")]),
        }
        rows = harvest_csv_rows(aggregate_by_species_year(logs))
        assert set(rows[0].keys()) == set(HARVEST_CSV_HEADERS)
        assert rows[0]["species"] == "Tomato"
        assert rows[0]["total_quantity"] == "2.5"
        assert rows[0]["year"] == 2026
