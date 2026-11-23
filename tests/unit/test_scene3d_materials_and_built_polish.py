"""Unit tests for 3D materials, lighting, flat-roof facade, raised-bed frames and natural ponds.

Pins the invariants introduced for:
- #883: glossier built surfaces (steel, iron, enamel, glass_pane) sit at roughness >= 0.70
  so Ultra SSR does not shimmer.
- #884: linear albedo scaling on matte mineral/tile/wood surfaces so noon roofs, walls and
  decks do not clip red, while DEFAULT_SURFACE stays unscaled.
- #887: cohesive shed shingle detail, plain ``roof_cap`` surface without detail picture,
  realistic 128 cm masonry scale, and raised ``AO_FLAT_BIAS_CM``.
- #953: cool sky-tinted minimum night ambient fill on moon-away faces.
- #957: raised-bed frame material follows architectural fill patterns (corten, stone,
  concrete, terracotta) while keeping ``soil_surface_cm`` exact.
- #958: water shaders expose ``uSsrRough`` (0.40) for soft Ultra SSR reflections while keeping
  ``uRough`` (0.02) for crisp sun glints and IBL probe reflections.
- #961: organic multi-vertex ground ponds get smoothed outlines, low sloped natural banks
  and darker greener water while formal pools keep stone coping.
- #965: flat-roofed houses get contemporary large-pane dark-framed windows and a neutral
  matte ``flat_roof`` surface with specular off.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.object_height import soil_surface_cm
from open_garden_planner.core.roof_style import FLAT
from open_garden_planner.core.scene3d import SunState, verify_builder
from open_garden_planner.core.scene3d.builders import (
    beds,
    buildings,
    facade,
    palette,
    production_registry,
    surfaces,
)
from open_garden_planner.core.scene3d.look import (
    AO_FLAT_BIAS_CM,
    NIGHT_FILL_SKY_SHARE,
    look_for,
    night_fill_linear,
)
from open_garden_planner.core.scene3d.materials import DEFAULT_SURFACE, SURFACES
from open_garden_planner.core.scene3d.weather import WEATHERS, living_look
from open_garden_planner.ui.view3d.quick3d import materials as engine_materials
from tests.unit.scene3d_builder_cases import circle_record, polygon_record, rectangle

REGISTRY = production_registry()
QML_DIR = Path(engine_materials.__file__).resolve().parent / "qml"


class TestBuiltSurfaceParameters:
    def test_ultra_ssr_surfaces_are_at_or_above_070_roughness(self) -> None:
        """#883: steel, iron, enamel and glass_pane stay >= 0.70 roughness with specular kept."""
        expected = {
            "steel": (0.70, 0.50),
            "iron": (0.70, 0.35),
            "enamel": (0.70, 0.15),
            "glass_pane": (0.70, 0.40),
        }
        for name, (rough, spec) in expected.items():
            surf = SURFACES[name]
            assert surf.roughness == pytest.approx(rough), name
            assert surf.specular == pytest.approx(spec), name

    def test_a_window_pane_gets_its_own_ssr_material(self) -> None:
        """#992: Ultra SSR reflects the garden at 0.38; the IBL keeps the #883 0.70."""
        glass = engine_materials.surface_look("vc", "glass_pane")
        other = engine_materials.surface_look("vc", "stone")
        roof = engine_materials.surface_look("roof", "roof_tile")
        assert glass is not None and other is not None and roof is not None
        assert glass.properties["surfaceGlass"] == 1.0
        assert other.properties["surfaceGlass"] == 0.0
        assert "surfaceGlass" not in roof.properties
        shader = (QML_DIR / "glass.frag").read_text(encoding="utf-8")
        assert "ROUGHNESS = uSsrRough;" in shader
        assert "SPECULAR_AMOUNT = uSpecular;" in shader
        assert "void IBL_PROBE()" in shader
        assert "qt_sampleGlossy(NORMAL, VIEW_VECTOR, uRough)" in shader
        garden = (QML_DIR / "Garden.qml").read_text(encoding="utf-8")
        assert "property real uSsrRough: root.ssrVisible ? 0.38 : surfaceRough" in garden
        assert "surfaceGlass > 0.5 ? [vcGlass]" in garden
        assert garden.count('fragmentShader: "glass.frag"') == 2, "vcGlass + shaderWarmer"

    def test_noon_matte_surfaces_carry_linear_albedo_scale(self) -> None:
        """#884: noon-clipping matte surfaces scale down linearly; default stays 1.0."""
        assert SURFACES[DEFAULT_SURFACE].albedo_scale == 1.0
        for name in ("roof_tile", "roof_cap", "plaster", "masonry", "stone", "concrete", "wood", "wood_cladding"):
            surf = SURFACES[name]
            assert 0.5 < surf.albedo_scale < 1.0, name
            look = engine_materials.surface_look("vc", name)
            assert look is not None
            assert look.properties["surfaceAlbedo"] == pytest.approx(surf.albedo_scale)
            assert 0.5 < look.properties["surfaceAlbedoSrgb"] < 1.0
        default_look = engine_materials.surface_look("vc", DEFAULT_SURFACE)
        assert default_look is not None
        assert default_look.properties["surfaceAlbedo"] == 1.0
        assert default_look.properties["surfaceAlbedoSrgb"] == 1.0

    def test_shed_shingle_ridge_cap_masonry_and_ao_bias(self) -> None:
        """#887: softer shed shingles, plain ridge cap, 128 cm masonry, higher AO flat bias."""
        shingle = SURFACES["shingle"].detail
        assert shingle is not None
        assert shingle.tile_cm == pytest.approx(128.0)
        assert shingle.contrast <= 0.45

        assert SURFACES["roof_cap"].detail is None
        assert palette.ROOF_TILE_CAP.surface == "roof_cap"
        assert palette.SHINGLE_CAP.surface == "roof_cap"

        masonry = SURFACES["masonry"].detail
        assert masonry is not None
        assert masonry.tile_cm == pytest.approx(128.0)

        assert AO_FLAT_BIAS_CM >= 1.4
        qml = (QML_DIR / "Garden.qml").read_text(encoding="utf-8")
        assert f"property real aoBias: {AO_FLAT_BIAS_CM}" in qml

    def test_water_shaders_decouple_ssr_roughness_from_glint_roughness(self) -> None:
        """#958: water uses moderate SSR roughness (0.40) for soft reflections while keeping crisp uRough for sun/IBL."""
        qml = (QML_DIR / "Garden.qml").read_text(encoding="utf-8")
        assert qml.count("property real uSsrRough: 0.40") >= 3
        for shader in ("water.frag", "water_door.frag"):
            src = (QML_DIR / shader).read_text(encoding="utf-8")
            assert "ROUGHNESS = uSsrRough;" in src, shader
            assert "float alpha = uRough * uRough;" in src, shader
            assert "qt_sampleGlossy(NORMAL, VIEW_VECTOR, uRough)" in src, shader


class TestNightMinimumFill:
    def test_night_fill_is_zero_by_day_and_positive_cool_at_night(self) -> None:
        """#953: faces turned away from the moon receive a cool minimum ambient floor at night."""
        assert NIGHT_FILL_SKY_SHARE >= 0.75
        day = look_for(SunState(30.0, 180.0))
        sunset = look_for(SunState(5.89, 280.0))
        assert night_fill_linear(day) == (0.0, 0.0, 0.0)
        assert night_fill_linear(sunset) == (0.0, 0.0, 0.0)

        clear_night = look_for(SunState(-15.0, 340.0))
        floor = night_fill_linear(clear_night)
        assert clear_night.twilight_fill_linear == floor
        assert floor[2] > floor[1] > floor[0] > 0.0  # cool blue-tinted night ambient

        overcast_night = living_look(SunState(-15.0, 340.0), "high", "overcast")
        assert min(overcast_night.twilight_fill_linear) > 0.0
        assert sum(overcast_night.twilight_fill_linear) < sum(clear_night.twilight_fill_linear)
        for weather in WEATHERS:
            w_night = living_look(SunState(-15.0, 340.0), "high", weather)
            assert min(w_night.twilight_fill_linear) > 0.0, weather


class TestRaisedBedFillFrames:
    @pytest.mark.parametrize(("pattern", "expected_surface"), [
        ("CORTEN", "corten"),
        ("STONE", "masonry"),
        ("BRICK", "masonry"),
        ("FLAGSTONE", "masonry"),
        ("SLATE", "masonry"),
        ("CONCRETE", "concrete_wall"),
        ("CLAY", "concrete_wall"),
        ("TERRACOTTA", "terracotta"),
    ])
    def test_raised_bed_frame_takes_architectural_fill_material(
        self, pattern: str, expected_surface: str
    ) -> None:
        """#957: architectural fills build a tinted frame in the matching surface + soil."""
        record = polygon_record(
            "RAISED_BED", rectangle(300.0, 120.0), 50.0,
            params={"surface_pattern": pattern},
        )
        parts = verify_builder(REGISTRY.builder_for("RAISED_BED"), record, height_tolerance_cm=0.5)
        assert [part.name for part in parts] == ["walls", "soil"]
        walls_part, soil_part = parts
        assert walls_part.tinted is True
        assert walls_part.surface == expected_surface
        assert soil_part.tinted is False
        assert float(soil_part.mesh.positions[:, 2].max()) == pytest.approx(
            soil_surface_cm("RAISED_BED", 50.0)
        )
        assert sum(p.mesh.triangle_count for p in parts) <= beds.triangle_budget(record, 50.0)

    @pytest.mark.parametrize("pattern", [None, "SOLID", "WOOD", "DECKING", "BARK", "SOIL"])
    def test_raised_bed_default_and_wood_fills_stay_oak_planks(self, pattern: str | None) -> None:
        params = {} if pattern is None else {"surface_pattern": pattern}
        record = polygon_record("RAISED_BED", rectangle(300.0, 120.0), 50.0, params=params)
        parts = verify_builder(REGISTRY.builder_for("RAISED_BED"), record, height_tolerance_cm=0.5)
        assert [part.name for part in parts] == ["bed"]
        assert parts[0].tinted is False


class TestFlatRoofHouseAndFacade:
    def test_flat_roofed_house_uses_modern_large_windows_and_neutral_matte_roof(self) -> None:
        """#965: flat-roofed house gets contemporary dark-framed large windows and neutral flat_roof."""
        flat_rec = polygon_record(
            "HOUSE", rectangle(900.0, 500.0), 340.0,
            params={"roof_style": FLAT},
        )
        gable_rec = polygon_record(
            "HOUSE", rectangle(900.0, 500.0), 450.0,
            params={"roof_style": "gable", "ridge": ((-450.0, 0.0), (450.0, 0.0))},
        )
        flat_parts = verify_builder(REGISTRY.builder_for("HOUSE"), flat_rec, height_tolerance_cm=0.5)
        gable_parts = verify_builder(REGISTRY.builder_for("HOUSE"), gable_rec, height_tolerance_cm=0.5)

        flat_roof_part = next(p for p in flat_parts if p.name == "roof")
        assert flat_roof_part.surface == "flat_roof"
        assert SURFACES["flat_roof"].specular == 0.0
        assert SURFACES["flat_roof"].albedo_scale < 0.6

        flat_facade = next(p for p in flat_parts if p.name == "facade").mesh
        gable_facade = next(p for p in gable_parts if p.name == "facade").mesh
        iron = np.asarray(palette.IRON.linear, dtype=np.float32)
        white = np.asarray(palette.STEEL_LIGHT.linear, dtype=np.float32)
        # Modern flat-roof facade uses dark IRON frames and no cottage white frames
        assert np.isclose(flat_facade.colors, iron, atol=1e-5).all(axis=1).any()
        assert not np.isclose(flat_facade.colors, white, atol=1e-5).all(axis=1).any()
        # Pitched gable facade keeps classic white frames
        assert np.isclose(gable_facade.colors, white, atol=1e-5).all(axis=1).any()
        assert facade.MODERN_HOUSE_SPEC.modern is True
        assert facade.MODERN_HOUSE_SPEC.window_w > facade.SPECS["HOUSE"].window_w
        assert sum(p.mesh.triangle_count for p in flat_parts) <= buildings.triangle_budget(flat_rec)

    def test_automatic_ridgeless_flat_house_and_custom_green_flat_roof_surfaces(self) -> None:
        """#965: automatic ridge-less flat houses get modern facade + specular-free concrete
        slab (FR-3D-BUILT-02), while explicit flat roofs resolve ``flat_roof`` vs matte
        ``concrete`` on the material path (``fill_surface_name``) so changing a flat roof's
        fill pattern keeps its mesh and custom green roofs stay bright."""
        auto_flat = polygon_record("HOUSE", rectangle(900.0, 500.0), 340.0)
        auto_parts = verify_builder(REGISTRY.builder_for("HOUSE"), auto_flat, height_tolerance_cm=0.5)
        auto_roof = next(p for p in auto_parts if p.name == "roof")
        assert any(name == "concrete" for name, _count in auto_roof.surface_runs)
        assert SURFACES["concrete"].specular == 0.0
        auto_facade = next(p for p in auto_parts if p.name == "facade").mesh
        iron = np.asarray(palette.IRON.linear, dtype=np.float32)
        assert np.isclose(auto_facade.colors, iron, atol=1e-5).all(axis=1).any()

        for pattern in (None, "", "SOLID", "CONCRETE"):
            assert engine_materials.fill_surface_name("flat_roof", pattern) == "flat_roof"
        for pattern in ("GRASS", "ROOF_TILES", "GRAVEL"):
            assert engine_materials.fill_surface_name("flat_roof", pattern) == "concrete"
        assert engine_materials.fill_surface_name("concrete", "GRASS") == "concrete"
        assert SURFACES["concrete"].specular == 0.0
        assert SURFACES["concrete"].albedo_scale >= 0.80


class TestNaturalPond:
    @staticmethod
    def _organic_ring(n: int = 10, rx: float = 240.0, ry: float = 170.0) -> tuple[tuple[float, float], ...]:
        return tuple(
            (rx * math.cos(2.0 * math.pi * k / n), ry * math.sin(2.0 * math.pi * k / n))
            for k in range(n)
        )

    def test_organic_polygon_pond_gets_smoothed_bank_and_natural_water(self) -> None:
        """#961: multi-vertex ground pond gets smoothed outline, low sloped bank, greener water."""
        ring = self._organic_ring(10)
        record = polygon_record("POND_POOL", ring, None)
        assert surfaces.is_natural_pond(record) is True
        water, bank = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=10.0)
        assert water.material_kind == "water" and water.tinted is True
        # Natural pond water is darker and greener than a formal pool's 0.9
        wcol = water.mesh.colors[0]
        assert wcol[1] > wcol[2] and wcol[1] > wcol[0] and wcol[2] < 0.5
        # Flush low earth shore stays strictly below DECK_TOP_CM so overhanging decks clear it
        assert float(bank.mesh.positions[:, 2].max()) == pytest.approx(surfaces.BANK_UP_CM)
        assert surfaces.WATER_CM < surfaces.BANK_UP_CM < surfaces.DECK_TOP_CM < surfaces.COPING_UP_CM
        assert surfaces.GRAVEL_RIM_CM < surfaces.DECK_TOP_CM
        # Outline is smoothed (more vertices than the raw 10-gon)
        assert water.mesh.triangle_count > len(ring) - 2

    def test_formal_pools_keep_stone_coping_and_pool_water(self) -> None:
        """4-vertex rectangular, circular and raised pools stay formal pools."""
        for rec in (
            polygon_record("POND_POOL", rectangle(400.0, 240.0), None),
            circle_record("POND_POOL", 150.0, None),
            polygon_record("POND_POOL", self._organic_ring(10), 60.0),
        ):
            assert surfaces.is_natural_pond(rec) is False
            parts = verify_builder(REGISTRY.builder_for("POND_POOL"), rec, plan_margin_cm=10.0)
            if rec.height_cm is None:
                water, coping = parts
                assert np.allclose(water.mesh.colors[0, :3], 0.9, atol=1e-5)
                assert float(coping.mesh.positions[:, 2].max()) == pytest.approx(surfaces.COPING_UP_CM)

    def test_pinched_concave_natural_pond_falls_back_cleanly_and_never_disappears(self) -> None:
        """#961: a valid 5-vertex pinched concave pond whose fillet would self-intersect falls
        back to its original unsmoothed ring instead of silently dropping out of 3D."""
        pinched = ((0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (197.0, 3.0), (0.0, 200.0))
        record = polygon_record("POND_POOL", pinched, None)
        assert surfaces.is_natural_pond(record) is True
        water, bank = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=10.0)
        assert water.material_kind == "water"
        assert water.mesh.triangle_count >= 3
        assert bank.mesh.triangle_count > 0
