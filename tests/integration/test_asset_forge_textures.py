"""End-to-end `.ogp` round-trip test for every asset-forge fill pattern.

Started as the US-E9 pilot gate (DECKING/CORTEN); since Package 3b (#309)
every texture comes out of the forge, so every non-solid pattern round-trips
here. Patterns are persisted by ``FillPattern.name`` and reloaded via
``FillPattern[...]`` with a ``KeyError -> None`` guard. The unit tests in
``tests/unit/test_fill_patterns.py`` cover texture load + brush creation; this
pins the full save -> reload path so a rename/removal of an enum member can't
silently break a saved plan — the §8.10 integration gate for the patterns.
"""
from __future__ import annotations

import json

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture
def manager(qtbot) -> ProjectManager:  # noqa: ARG001 — qtbot for Qt init
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:  # noqa: ARG001
    return QGraphicsScene()


@pytest.mark.parametrize(
    "pattern",
    sorted((p for p in FillPattern if p is not FillPattern.SOLID), key=lambda p: p.name),
    ids=lambda p: p.name,
)
def test_pattern_round_trips(manager, scene, tmp_path, pattern) -> None:
    """A rectangle filled with a forge pattern survives save -> reload."""
    rect = RectangleItem(
        0, 0, 120, 80,
        object_type=ObjectType.TERRACE_PATIO,
        fill_pattern=pattern,
    )
    rect.fill_color = QColor(160, 120, 90)
    scene.addItem(rect)

    file_path = tmp_path / f"{pattern.name.lower()}.ogp"
    manager.save(scene, file_path)

    # Serialized by enum name — file-forward-safe (old apps degrade to None).
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    assert pattern.name in json.dumps(raw)

    scene.clear()
    manager.load(scene, file_path)

    rects = [i for i in scene.items() if isinstance(i, RectangleItem)]
    assert len(rects) == 1
    loaded = rects[0]
    assert loaded.fill_pattern is pattern
    # Reloaded item paints with a real texture brush, not a blank fill.
    assert not loaded.brush().texture().isNull()
