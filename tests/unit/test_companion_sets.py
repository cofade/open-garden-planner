"""Unit tests for the compatible-set finder (US-D3.1, issue #319)."""

from __future__ import annotations

from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
)
from open_garden_planner.services.companion_sets import (
    find_compatible_sets,
    suggest_companions,
)


class TestFindCompatibleSets:
    """Tests for find_compatible_sets."""

    def setup_method(self) -> None:
        self.service = CompanionPlantingService()

    def test_three_sisters_found(self) -> None:
        """Three Sisters (corn, bean, squash) should be found as a compatible set."""
        candidates = ["corn", "bean", "squash", "potato", "tomato"]
        sets = find_compatible_sets(self.service, candidates, size=3)
        assert len(sets) > 0
        # Three Sisters should be among the top sets
        members_sets = [s["members"] for s in sets]
        assert any(
            {"corn", "bean", "squash"}.issubset(set(m))
            for m in members_sets
        )

    def test_no_antagonist_pairs(self) -> None:
        """No set should contain an antagonist pair."""
        candidates = ["tomato", "potato", "fennel", "basil"]
        sets = find_compatible_sets(self.service, candidates, size=2)
        for s in sets:
            members = s["members"]
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    rel = self.service.get_relationship(a, b)
                    assert rel is None or rel.type != "antagonistic", (
                        f"Set {members} contains antagonist pair {a}/{b}"
                    )

    def test_size_filter(self) -> None:
        """Sets smaller than the requested size should be excluded."""
        candidates = ["corn", "common bean", "squash"]
        sets = find_compatible_sets(self.service, candidates, size=3)
        for s in sets:
            assert s["size"] >= 3

    def test_must_include(self) -> None:
        """All returned sets must include the must_include species."""
        candidates = ["corn", "common bean", "squash", "tomato"]
        sets = find_compatible_sets(
            self.service, candidates, size=3, must_include=["corn"]
        )
        for s in sets:
            assert "corn" in s["members"]

    def test_empty_candidates(self) -> None:
        """Empty candidates should return empty list."""
        sets = find_compatible_sets(self.service, [], size=3)
        assert sets == []

    def test_invalid_size_raises(self) -> None:
        """Size outside 2–5 should raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="size must be 2"):
            find_compatible_sets(self.service, ["corn"], size=1)
        with pytest.raises(ValueError, match="size must be 2"):
            find_compatible_sets(self.service, ["corn"], size=6)

    def test_deterministic_output(self) -> None:
        """Same input should produce same output."""
        candidates = ["corn", "common bean", "squash", "tomato", "carrot"]
        sets1 = find_compatible_sets(self.service, candidates, size=3)
        sets2 = find_compatible_sets(self.service, candidates, size=3)
        assert sets1 == sets2


class TestSuggestCompanions:
    """Tests for suggest_companions."""

    def setup_method(self) -> None:
        self.service = CompanionPlantingService()

    def test_suggestions_for_tomato(self) -> None:
        """Tomato should have companion suggestions."""
        suggestions = suggest_companions(self.service, "tomato")
        assert len(suggestions) > 0
        # All suggestions should have required fields
        for s in suggestions:
            assert "species_key" in s
            assert "name" in s
            assert "reasons" in s
            assert "source" in s
            assert "score" in s

    def test_exclude_antagonists(self) -> None:
        """Antagonists of excluded species should not appear."""
        # Get tomato's companions
        all_suggestions = suggest_companions(self.service, "tomato")
        all_keys = {s["species_key"] for s in all_suggestions}

        # Exclude antagonists of potato
        filtered = suggest_companions(
            self.service, "tomato", exclude_antagonists_of=["potato"]
        )
        filtered_keys = {s["species_key"] for s in filtered}

        # Filtered should be a subset of all
        assert filtered_keys.issubset(all_keys)

    def test_unknown_species(self) -> None:
        """Unknown species should return empty list."""
        suggestions = suggest_companions(self.service, "nonexistent_species_xyz")
        assert suggestions == []

    def test_ranked_by_score(self) -> None:
        """Suggestions should be sorted by score descending."""
        suggestions = suggest_companions(self.service, "tomato")
        scores = [s["score"] for s in suggestions]
        assert scores == sorted(scores, reverse=True)

    def test_display_name_follows_language_key_does_not(self) -> None:
        """#410: the name is a UI-language display string; the key is stable."""
        english = suggest_companions(self.service, "tomato", language="en")
        german = suggest_companions(self.service, "tomato", language="de")
        assert [s["species_key"] for s in english] == [
            s["species_key"] for s in german
        ]
        en_names = {s["species_key"]: s["name"] for s in english}
        de_names = {s["species_key"]: s["name"] for s in german}
        assert any(
            de_names[key] != en_names[key] for key in en_names
        ), "at least one bundled companion must have a German name"
        for key, name in de_names.items():
            assert name == self.service.get_display_name(key, "de")
