"""Tests for unified living buffer assembly and 3D materials culling (#689, #720)."""

import math
from datetime import date

from open_garden_planner.core.phenology import PhenologyState
from open_garden_planner.core.scene3d import (
    TWO_SIDED_KINDS,
    LivingAssembly,
    Material,
    Params,
    Record,
    Transform,
    living_buffers,
    two_sided_kinds,
)


def test_two_sided_kinds_culling_modes() -> None:
    """TWO_SIDED_KINDS covers foliage, grass, glass; cutaway additionally treats vc as two-sided."""
    assert two_sided_kinds(cutaway=False) == TWO_SIDED_KINDS
    assert frozenset({"foliage", "grass", "glass"}) == TWO_SIDED_KINDS
    assert two_sided_kinds(cutaway=True) == TWO_SIDED_KINDS | {"vc"}
    assert "vc" not in TWO_SIDED_KINDS


def test_living_buffers_empty_records() -> None:
    """Empty records return empty buffers and empty lamp sets."""
    assembly = living_buffers({}, {}, date(2026, 6, 21), 52.0, (0.0, 0.0, 0.0))
    assert isinstance(assembly, LivingAssembly)
    assert assembly.buffers.is_empty
    assert assembly.lamps == ()
    assert assembly.emitters == ()
    assert assembly.sources == ()

    # Unpackable as tuple
    buf, lamps = assembly
    assert buf is assembly.buffers
    assert lamps is assembly.lamps


def test_living_buffers_with_flowering_plants_and_lamps() -> None:
    """Unified living buffers assembly combines plant emitters and lamp sources (#689)."""
    ring = tuple((50.0 * math.cos(a), 50.0 * math.sin(a)) for a in (2.0 * math.pi * k / 16 for k in range(16)))
    lamp_ring = tuple((20.0 * math.cos(a), 20.0 * math.sin(a)) for a in (2.0 * math.pi * k / 16 for k in range(16)))
    plant_rec = Record(
        item_id="plant_1",
        kind="SHRUB",
        shape="circle",
        footprints=(ring,),
        transform=Transform(100.0, 100.0, 0.0, 0.0),
        material=Material("foliage", fill_rgba=(60, 120, 50, 255)),
        height_cm=80.0,
        params=Params({"radius_cm": 50.0}),
    )
    lamp_rec = Record(
        item_id="lamp_1",
        kind="GARDEN_LIGHT",
        shape="circle",
        footprints=(lamp_ring,),
        transform=Transform(200.0, 200.0, 0.0, 0.0),
        material=Material("steel", fill_rgba=(49, 53, 56, 255)),
        height_cm=100.0,
        params=Params({"radius_cm": 20.0}),
    )
    seasons = {
        "plant_1": PhenologyState(
            leaf_density=1.0,
            autumn_color=0.0,
            autumn_tint_linear=(1.0, 1.0, 1.0),
            bloom=1.0,
            ripeness=0.0,
            snow=0.0,
            foliage_tint_linear=(1.0, 1.0, 1.0),
            foliage_tint_rgba=(255, 255, 255, 255),
            accent_opacity=1.0,
            accent_tint_linear=(1.0, 1.0, 1.0),
            accent_tint_rgba=(255, 255, 255, 255),
        ),
    }
    assembly = living_buffers(
        [plant_rec, lamp_rec],
        seasons,
        date(2026, 6, 21),
        52.0,
        target=(200.0, 200.0, 0.0),
    )
    assert len(assembly.emitters) >= 1
    assert any(e.kind == "butterfly" for e in assembly.emitters)
    assert len(assembly.sources) == 1
    assert len(assembly.lamps) == 1
    assert len(assembly.bulbs) >= 1
    assert assembly.lamps[0].item_id == "lamp_1"
    assert not assembly.buffers.is_empty


def test_living_buffers_fallback_with_empty_seasons() -> None:
    """When seasons mapping is empty, emitters are empty but lamp bulbs assemble (#689)."""
    lamp_ring = tuple((20.0 * math.cos(a), 20.0 * math.sin(a)) for a in (2.0 * math.pi * k / 16 for k in range(16)))
    lamp_rec = Record(
        item_id="lamp_1",
        kind="GARDEN_LIGHT",
        shape="circle",
        footprints=(lamp_ring,),
        transform=Transform(200.0, 200.0, 0.0, 0.0),
        material=Material("steel", fill_rgba=(49, 53, 56, 255)),
        height_cm=100.0,
        params=Params({"radius_cm": 20.0}),
    )
    assembly = living_buffers([lamp_rec], {}, date(2026, 6, 21), 52.0)
    assert assembly.emitters == ()
    assert len(assembly.sources) == 1
    assert len(assembly.lamps) == 1
    assert len(assembly.bulbs) == 1
    assert not assembly.buffers.is_empty


def test_living_buffers_accepts_mapping_and_sorts_lamps_by_target() -> None:
    """living_buffers accepts dict input and selects nearest lamps to target (#689)."""
    lamp_ring = tuple((20.0 * math.cos(a), 20.0 * math.sin(a)) for a in (2.0 * math.pi * k / 16 for k in range(16)))
    lamp_near = Record(
        item_id="lamp_near",
        kind="GARDEN_LIGHT",
        shape="circle",
        footprints=(lamp_ring,),
        transform=Transform(10.0, 10.0, 0.0, 0.0),
        material=Material("steel", fill_rgba=(49, 53, 56, 255)),
        height_cm=100.0,
        params=Params({"radius_cm": 20.0}),
    )
    lamp_far = Record(
        item_id="lamp_far",
        kind="GARDEN_LIGHT",
        shape="circle",
        footprints=(lamp_ring,),
        transform=Transform(1000.0, 1000.0, 0.0, 0.0),
        material=Material("steel", fill_rgba=(49, 53, 56, 255)),
        height_cm=100.0,
        params=Params({"radius_cm": 20.0}),
    )
    records = {"near": lamp_near, "far": lamp_far}
    assembly = living_buffers(records, {}, date(2026, 6, 21), 52.0, target=(0.0, 0.0, 0.0))
    assert len(assembly.sources) == 2
    assert len(assembly.lamps) == 2
    assert assembly.lamps[0].item_id == "lamp_near"
    assert assembly.lamps[1].item_id == "lamp_far"
    assert len(assembly.bulbs) == 2
