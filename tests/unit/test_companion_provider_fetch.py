"""Unit tests for Permapeople companion provider fetch (US-G3, issue #318)."""

from __future__ import annotations

from open_garden_planner.services.companion_cache import (
    clear_cache,
    get_cached_companions,
    set_cached_companions,
)
from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
)


class TestCompanionCache:
    def test_cache_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_cache.get_cache_dir",
            lambda: tmp_path,
        )
        companions = [
            {"plant_a": "Malus domestica", "plant_b": "Allium schoenoprasum", "type": "beneficial", "reason": "", "source": "permapeople"},
            {"plant_a": "Malus domestica", "plant_b": "Solanum tuberosum", "type": "antagonistic", "reason": "", "source": "permapeople"},
        ]
        set_cached_companions("Malus domestica", companions)
        cached = get_cached_companions("Malus domestica")
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["plant_b"] == "Allium schoenoprasum"

    def test_cache_miss_returns_none(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_cache.get_cache_dir",
            lambda: tmp_path,
        )
        assert get_cached_companions("Nonexistent plant") is None

    def test_clear_cache(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_cache.get_cache_dir",
            lambda: tmp_path,
        )
        set_cached_companions("Malus domestica", [])
        assert clear_cache() == 1
        assert get_cached_companions("Malus domestica") is None


class TestProviderCompanions:
    def test_add_provider_companions(self) -> None:
        svc = CompanionPlantingService()
        companions = [
            {"plant_a": "Malus domestica", "plant_b": "Allium schoenoprasum", "type": "beneficial", "reason": "", "source": "permapeople"},
            {"plant_a": "Malus domestica", "plant_b": "Solanum tuberosum", "type": "antagonistic", "reason": "", "source": "permapeople"},
        ]
        svc.add_provider_companions("Malus domestica", companions)

        # Check that the companions are now available
        beneficial, antagonistic = svc.get_companions("Malus domestica")
        # Note: the service resolves names, so we need to check by the raw names
        all_rels = beneficial + antagonistic
        plant_b_names = [r.plant_b for r in all_rels]
        assert "allium schoenoprasum" in plant_b_names
        assert "solanum tuberosum" in plant_b_names

    def test_provider_companions_count(self) -> None:
        svc = CompanionPlantingService()
        initial_count = svc.get_provider_companions_count()
        companions = [
            {"plant_a": "Malus domestica", "plant_b": "Allium schoenoprasum", "type": "beneficial", "reason": "", "source": "permapeople"},
        ]
        svc.add_provider_companions("Malus domestica", companions)
        assert svc.get_provider_companions_count() == initial_count + 1

    def test_bundled_wins_on_conflict(self) -> None:
        """When bundled says beneficial but provider says antagonistic, bundled wins."""
        svc = CompanionPlantingService()
        # Add a provider rule that conflicts with bundled data
        # Tomato and Basil are beneficial in bundled data
        companions = [
            {"plant_a": "Solanum lycopersicum", "plant_b": "Ocimum basilicum", "type": "antagonistic", "reason": "", "source": "permapeople"},
        ]
        svc.add_provider_companions("Solanum lycopersicum", companions)

        # The bundled relationship should still be beneficial
        rel = svc.get_relationship("tomato", "basil")
        assert rel is not None
        assert rel.type == "beneficial"  # Bundled wins
