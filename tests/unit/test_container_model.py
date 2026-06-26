"""Unit tests for the Qt-free container gardening helpers (US-C3)."""

import pytest

from open_garden_planner.core import container_model as cm


class TestAutoSoilVolume:
    def test_rect_footprint_height(self) -> None:
        # 1000 cm² × 30 cm = 30000 cm³ = 30 L
        assert cm.auto_soil_volume_litres(1000.0, 30.0) == pytest.approx(30.0)

    def test_round_footprint(self) -> None:
        # circle r=10cm → area ~314.16 cm²; × 25 cm = ~7.854 L
        import math

        footprint = math.pi * 10.0 * 10.0
        assert cm.auto_soil_volume_litres(footprint, 25.0) == pytest.approx(
            footprint * 25.0 / 1000.0
        )

    def test_non_positive_inputs_are_zero(self) -> None:
        assert cm.auto_soil_volume_litres(0.0, 30.0) == 0.0
        assert cm.auto_soil_volume_litres(1000.0, 0.0) == 0.0
        assert cm.auto_soil_volume_litres(-5.0, 30.0) == 0.0


class TestEffectiveSoilVolume:
    def test_override_wins(self) -> None:
        meta = {"container_soil_volume_l": 12.5}
        assert cm.effective_soil_volume_litres(meta, 1000.0, 30.0) == 12.5

    def test_falls_back_to_auto(self) -> None:
        assert cm.effective_soil_volume_litres({}, 1000.0, 30.0) == pytest.approx(30.0)

    def test_zero_override_is_auto(self) -> None:
        # 0 / None / negative override are not "positive" → auto-compute.
        meta = {"container_soil_volume_l": 0}
        assert cm.effective_soil_volume_litres(meta, 1000.0, 30.0) == pytest.approx(30.0)

    def test_height_from_metadata(self) -> None:
        meta = {"container_height_cm": 20.0}
        assert cm.effective_soil_volume_litres(meta, 1000.0) == pytest.approx(20.0)


class TestMetadataAccessors:
    def test_defaults(self) -> None:
        assert cm.container_height_cm(None) == cm.DEFAULT_HEIGHT_CM
        assert cm.container_material(None) == cm.PLASTIC
        assert cm.container_has_drainage(None) is True

    def test_bad_material_falls_back(self) -> None:
        assert cm.container_material({"container_material": "gold"}) == cm.PLASTIC

    def test_explicit_values(self) -> None:
        meta = {
            "container_height_cm": 45,
            "container_material": cm.WOOD,
            "container_drainage": False,
        }
        assert cm.container_height_cm(meta) == 45.0
        assert cm.container_material(meta) == cm.WOOD
        assert cm.container_has_drainage(meta) is False


class TestWateringHint:
    @pytest.mark.parametrize("material", cm.MATERIALS)
    @pytest.mark.parametrize("drainage", [True, False])
    def test_matrix_non_empty(self, material: str, drainage: bool) -> None:
        hint = cm.watering_hint(material, drainage)
        assert isinstance(hint, str) and hint

    def test_no_drainage_appends_warning(self) -> None:
        with_drain = cm.watering_hint(cm.TERRACOTTA, True)
        without = cm.watering_hint(cm.TERRACOTTA, False)
        assert len(without) > len(with_drain)
        assert "drainage" in without.lower()

    def test_unknown_material_uses_default(self) -> None:
        assert cm.watering_hint("gold", True) == cm.watering_hint(cm.PLASTIC, True)


class TestCapacity:
    def test_footprint_sum_skips_non_positive(self) -> None:
        assert cm.total_child_footprint_cm2([10.0, -3.0, 0.0, 5.0]) == 15.0

    def test_exceeded(self) -> None:
        assert cm.is_capacity_exceeded(100.0, [60.0, 60.0]) is True

    def test_within_capacity(self) -> None:
        assert cm.is_capacity_exceeded(100.0, [30.0, 30.0]) is False

    def test_zero_container_never_exceeds(self) -> None:
        assert cm.is_capacity_exceeded(0.0, [50.0]) is False
