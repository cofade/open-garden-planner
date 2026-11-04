"""Tests for building interior floor (#589) and shader warmer (#582)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from open_garden_planner.core.scene3d.builders import palette, production_registry
from tests.unit.scene3d_builder_cases import polygon_record, rectangle

QML_SCENE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "open_garden_planner"
    / "ui"
    / "view3d"
    / "quick3d"
    / "qml"
    / "Garden.qml"
)


def test_building_has_neutral_interior_wood_floor() -> None:
    """Issue #589: buildings in 3D have a neutral interior wood floor (palette.PLANK)."""
    registry = production_registry()
    rec = polygon_record("HOUSE", rectangle(600.0, 400.0), 300.0, shape="rectangle")
    parts = registry.build(rec)
    floor_parts = [p for p in parts if p.name == "floor"]
    assert len(floor_parts) == 1, "Expected one floor part"
    floor = floor_parts[0]
    assert floor.material_kind == "vc"
    assert not floor.tinted
    # z should be 0.5 cm
    assert np.allclose(floor.mesh.positions[:, 2], 0.5, atol=1e-3)
    # colors should be palette.PLANK.linear
    expected_color = np.asarray(palette.PLANK.linear, dtype=np.float32)
    assert np.allclose(floor.mesh.colors, expected_color, atol=1e-4)


def test_shader_warmer_in_scene() -> None:
    """Issue #582: Garden.qml declares a shaderWarmer node to pre-warm screen door materials."""
    qml_text = QML_SCENE.read_text(encoding="utf-8")
    assert "id: shaderWarmer" in qml_text
    assert '"screen.vert"' in qml_text
    assert '"screen.frag"' in qml_text
    assert '"foliage_door.vert"' in qml_text
    assert '"foliage_door.frag"' in qml_text
    assert '"grass_door.vert"' in qml_text
    assert '"water_door.frag"' in qml_text
