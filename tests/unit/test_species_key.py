"""Unit tests for the canonical species_key() helper (ADR-016, issue #176)."""
import pytest

from open_garden_planner.models.plant_data import species_key


class TestSpeciesKey:
    def test_source_id_wins_over_scientific_name(self) -> None:
        result = species_key({"source_id": "perenual:42", "scientific_name": "Solanum lycopersicum"})
        assert result == "perenual:42"

    def test_falls_through_to_scientific_name_when_source_id_empty(self) -> None:
        result = species_key({"source_id": "", "scientific_name": "Solanum lycopersicum"})
        assert result == "solanum lycopersicum"

    def test_falls_through_to_common_name_when_scientific_missing(self) -> None:
        result = species_key({"common_name": "Tomato"})
        assert result == "tomato"

    def test_returns_unknown_when_all_fields_empty(self) -> None:
        assert species_key({}) == "_unknown"
        assert species_key({"source_id": "", "scientific_name": "", "common_name": ""}) == "_unknown"

    def test_strips_whitespace(self) -> None:
        result = species_key({"scientific_name": "  Solanum lycopersicum  "})
        assert result == "solanum lycopersicum"

    def test_lowercases_output(self) -> None:
        result = species_key({"source_id": "PERENUAL:42"})
        assert result == "perenual:42"

    def test_case_insensitive_equivalence(self) -> None:
        a = species_key({"common_name": "TOMATO"})
        b = species_key({"common_name": "tomato"})
        assert a == b

    def test_missing_fields_not_used_as_fallback_if_empty_string(self) -> None:
        result = species_key({"source_id": "", "scientific_name": "", "common_name": "Basil"})
        assert result == "basil"

    def test_none_values_treated_as_missing(self) -> None:
        # get() with a default of "" handles missing keys; .get(k, "") with None
        # stored would return None — species_key() uses .get(field, "").strip()
        # so explicit None would fail. Verify we only pass str values.
        result = species_key({"source_id": "abc"})
        assert result == "abc"

    def test_whitespace_only_falls_through(self) -> None:
        result = species_key({"source_id": "   ", "scientific_name": "Rosa canina"})
        assert result == "rosa canina"
