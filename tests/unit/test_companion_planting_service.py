"""Unit tests for the companion planting service."""

import json
import pytest

from open_garden_planner.services.companion_planting_service import (
    ANTAGONISTIC,
    BENEFICIAL,
    CompanionPlantingService,
    CompanionRelationship,
)


@pytest.fixture()
def svc() -> CompanionPlantingService:
    """Return a freshly loaded CompanionPlantingService."""
    return CompanionPlantingService()


class TestDatabaseLoading:
    def test_loads_without_error(self, svc: CompanionPlantingService) -> None:
        assert len(svc.get_all_plant_names()) > 0

    def test_has_sixty_plus_relationships(self, svc: CompanionPlantingService) -> None:
        """Verify the bundled database covers at least 60 relationships."""
        total = sum(
            1
            for name in svc.get_all_plant_names()
            for _ in svc._adjacency.get(name, [])
        ) // 2  # each relationship is stored twice (bidirectional)
        assert total >= 60

    def test_known_plants_present(self, svc: CompanionPlantingService) -> None:
        names = svc.get_all_plant_names()
        for plant in ("tomato", "basil", "carrot", "marigold", "fennel"):
            assert plant in names


class TestBeneficialLookup:
    def test_tomato_basil_beneficial(self, svc: CompanionPlantingService) -> None:
        good, _ = svc.get_companions("tomato")
        plant_b_names = [r.plant_b for r in good]
        assert "basil" in plant_b_names

    def test_carrot_onion_beneficial(self, svc: CompanionPlantingService) -> None:
        good, _ = svc.get_companions("carrot")
        assert any(r.plant_b == "onion" for r in good)

    def test_corn_bean_beneficial(self, svc: CompanionPlantingService) -> None:
        good, _ = svc.get_companions("corn")
        assert any(r.plant_b == "bean" for r in good)


class TestAntagonisticLookup:
    def test_tomato_fennel_antagonistic(self, svc: CompanionPlantingService) -> None:
        _, bad = svc.get_companions("tomato")
        assert any(r.plant_b == "fennel" for r in bad)

    def test_onion_bean_antagonistic(self, svc: CompanionPlantingService) -> None:
        _, bad = svc.get_companions("onion")
        assert any(r.plant_b == "bean" for r in bad)

    def test_fennel_inhibits_many(self, svc: CompanionPlantingService) -> None:
        _, bad = svc.get_companions("fennel")
        assert len(bad) >= 3


class TestBidirectionality:
    def test_basil_finds_tomato(self, svc: CompanionPlantingService) -> None:
        """If tomato-basil is stored, querying basil must also return tomato."""
        good, _ = svc.get_companions("basil")
        assert any(r.plant_b == "tomato" for r in good)

    def test_bean_finds_onion_antagonism(self, svc: CompanionPlantingService) -> None:
        """onion→bean antagonism must also appear when querying bean."""
        _, bad = svc.get_companions("bean")
        assert any(r.plant_b == "onion" for r in bad)

    def test_fennel_finds_tomato_antagonism(self, svc: CompanionPlantingService) -> None:
        """tomato→fennel antagonism must appear when querying fennel too."""
        _, bad = svc.get_companions("fennel")
        assert any(r.plant_b == "tomato" for r in bad)


class TestGetRelationship:
    def test_known_pair_returns_relationship(self, svc: CompanionPlantingService) -> None:
        rel = svc.get_relationship("tomato", "basil")
        assert rel is not None
        assert rel.type == BENEFICIAL

    def test_reversed_pair_also_works(self, svc: CompanionPlantingService) -> None:
        rel = svc.get_relationship("basil", "tomato")
        assert rel is not None
        assert rel.type == BENEFICIAL

    def test_antagonistic_pair(self, svc: CompanionPlantingService) -> None:
        rel = svc.get_relationship("tomato", "fennel")
        assert rel is not None
        assert rel.type == ANTAGONISTIC

    def test_unknown_pair_returns_none(self, svc: CompanionPlantingService) -> None:
        rel = svc.get_relationship("tomato", "unknown_plant_xyz")
        assert rel is None


class TestNameResolution:
    def test_lookup_by_scientific_name(self, svc: CompanionPlantingService) -> None:
        """Scientific name 'Solanum lycopersicum' resolves to 'tomato'."""
        good, _ = svc.get_companions("Solanum lycopersicum")
        assert len(good) > 0

    def test_lookup_by_alias(self, svc: CompanionPlantingService) -> None:
        """Alias 'cherry tomato' resolves to 'tomato'."""
        good, _ = svc.get_companions("cherry tomato")
        assert len(good) > 0

    def test_case_insensitive(self, svc: CompanionPlantingService) -> None:
        """Lookups are case-insensitive."""
        good1, _ = svc.get_companions("TOMATO")
        good2, _ = svc.get_companions("tomato")
        assert len(good1) == len(good2)

    def test_get_scientific_name(self, svc: CompanionPlantingService) -> None:
        sci = svc.get_plant_scientific_name("tomato")
        assert sci == "Solanum lycopersicum"

    def test_get_family(self, svc: CompanionPlantingService) -> None:
        family = svc.get_plant_family("tomato")
        assert family == "Solanaceae"


class TestFamilyLookup:
    def test_solanaceae_plants(self, svc: CompanionPlantingService) -> None:
        solanaceae = svc.get_plants_by_family("Solanaceae")
        assert "tomato" in solanaceae
        assert "potato" in solanaceae
        assert "pepper" in solanaceae

    def test_family_case_insensitive(self, svc: CompanionPlantingService) -> None:
        lower = svc.get_plants_by_family("solanaceae")
        upper = svc.get_plants_by_family("SOLANACEAE")
        assert set(lower) == set(upper)

    def test_unknown_family_returns_empty(self, svc: CompanionPlantingService) -> None:
        assert svc.get_plants_by_family("NonExistentFamily") == []


class TestCustomRules:
    def test_add_custom_rule(self, svc: CompanionPlantingService, tmp_path, monkeypatch) -> None:  # noqa: ARG002
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        # Re-create service with monkeypatched path
        fresh_svc = CompanionPlantingService()
        rule = CompanionRelationship(
            plant_a="apple",
            plant_b="chive",
            type=BENEFICIAL,
            reason="Chives prevent apple scab",
        )
        fresh_svc.add_custom_rule(rule)

        good, _ = fresh_svc.get_companions("apple")
        assert any(r.plant_b == "chive" for r in good)
        # Bidirectional
        good2, _ = fresh_svc.get_companions("chive")
        assert any(r.plant_b == "apple" for r in good2)

    def test_custom_rule_is_persisted(self, svc: CompanionPlantingService, tmp_path, monkeypatch) -> None:  # noqa: ARG002
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        fresh_svc = CompanionPlantingService()
        rule = CompanionRelationship(
            plant_a="apple",
            plant_b="chive",
            type=BENEFICIAL,
            reason="Chives prevent apple scab",
        )
        fresh_svc.add_custom_rule(rule)

        rules_file = tmp_path / "custom_companion_rules.json"
        assert rules_file.exists()
        data = json.loads(rules_file.read_text(encoding="utf-8"))
        assert any(r["plant_a"] == "apple" for r in data["rules"])

    def test_remove_custom_rule(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        fresh_svc = CompanionPlantingService()
        rule = CompanionRelationship(
            plant_a="apple",
            plant_b="chive",
            type=BENEFICIAL,
            reason="Test",
        )
        fresh_svc.add_custom_rule(rule)
        removed = fresh_svc.remove_custom_rule("apple", "chive")
        assert removed is True
        good, _ = fresh_svc.get_companions("apple")
        assert not any(r.plant_b == "chive" for r in good)

    def test_remove_nonexistent_custom_rule_returns_false(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        fresh_svc = CompanionPlantingService()
        assert fresh_svc.remove_custom_rule("apple", "chive") is False

    def test_custom_rule_marked_as_custom(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        fresh_svc = CompanionPlantingService()
        rule = CompanionRelationship(
            plant_a="apple",
            plant_b="lavender",
            type=BENEFICIAL,
            reason="Lavender attracts pollinators",
        )
        fresh_svc.add_custom_rule(rule)
        rules = fresh_svc.get_custom_rules()
        assert all(r.is_custom for r in rules)

    def test_replace_existing_custom_rule(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.companion_planting_service.get_app_data_dir",
            lambda: tmp_path,
        )
        fresh_svc = CompanionPlantingService()
        rule1 = CompanionRelationship(
            plant_a="apple", plant_b="chive", type=BENEFICIAL, reason="First reason"
        )
        rule2 = CompanionRelationship(
            plant_a="apple", plant_b="chive", type=ANTAGONISTIC, reason="Changed to antagonistic"
        )
        fresh_svc.add_custom_rule(rule1)
        fresh_svc.add_custom_rule(rule2)

        rel = fresh_svc.get_relationship("apple", "chive")
        assert rel is not None
        assert rel.type == ANTAGONISTIC
        assert len(fresh_svc.get_custom_rules()) == 1
