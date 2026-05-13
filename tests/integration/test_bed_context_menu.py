"""Regression test: bed-specific menu actions exist on every bed-capable shape.

History: bed features (soil test, pest log, succession plan) were repeatedly
forgotten on one or more shape items because each shape rolled its own menu
construction by hand. The fix is the centralised ``build_bed_context_menu``
method on ``GardenItemMixin``; this test fails for any future bed-capable
item that doesn't go through the shared builder.

See ADR-017 and ``docs/08-crosscutting-concepts/`` § 8.12.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMenu

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _make_rectangle() -> RectangleItem:
    return RectangleItem(0, 0, 100, 60, object_type=ObjectType.RAISED_BED)


def _make_polygon() -> PolygonItem:
    vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 60), QPointF(0, 60)]
    return PolygonItem(vertices, object_type=ObjectType.GARDEN_BED)


def _make_ellipse() -> EllipseItem:
    return EllipseItem(0, 0, 100, 60, object_type=ObjectType.GARDEN_BED)


def _make_circle() -> CircleItem:
    return CircleItem(0, 0, 30, object_type=ObjectType.GARDEN_BED)


BED_SHAPES = [
    pytest.param(_make_rectangle, True,  id="RectangleItem-raised-bed"),
    pytest.param(_make_polygon,   True,  id="PolygonItem-garden-bed"),
    pytest.param(_make_ellipse,   False, id="EllipseItem-garden-bed"),
    pytest.param(_make_circle,    False, id="CircleItem-garden-bed"),
]


@pytest.mark.parametrize("factory,supports_grid", BED_SHAPES)
def test_bed_context_menu_has_all_features(
    factory, supports_grid: bool, qtbot
) -> None:  # noqa: ARG001 — qtbot needed for Qt init
    """Every bed-capable shape must expose all bed-specific menu actions."""
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(
        menu, grid_enabled=False, supports_grid=supports_grid
    )

    assert actions.add_soil_test is not None, "Add soil test action missing"
    assert actions.log_pest_disease is not None, "Pest/disease log action missing"
    assert actions.plan_succession is not None, "Succession plan action missing"
    if supports_grid:
        assert actions.toggle_grid is not None, "Grid toggle missing on rectangular bed"
    else:
        assert actions.toggle_grid is None, "Round beds should not have grid toggle"


@pytest.mark.parametrize("factory,supports_grid", BED_SHAPES)
def test_bed_menu_actions_have_translated_text(
    factory, supports_grid: bool, qtbot
) -> None:  # noqa: ARG001
    """Each bed action must have non-empty label text (i18n-ready)."""
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(
        menu, grid_enabled=False, supports_grid=supports_grid
    )

    assert actions.add_soil_test.text(), "soil test action has empty text"
    assert actions.log_pest_disease.text(), "pest log action has empty text"
    assert actions.plan_succession.text(), "succession action has empty text"


# ---------------------------------------------------------------------------
# Structural: every bed-capable shape's contextMenuEvent must route through
# the shared builder + dispatcher. Without this, a shape can silently opt
# out and revert to hand-rolled bed actions — the exact recurrence pattern
# (US-12.8) the central pattern is supposed to prevent.
# ---------------------------------------------------------------------------

import inspect


@pytest.mark.parametrize("item_cls", [RectangleItem, PolygonItem, EllipseItem, CircleItem])
def test_context_menu_uses_shared_builder(item_cls) -> None:
    """contextMenuEvent must call build_bed_context_menu AND dispatch_bed_action.

    Source-level enforcement: ``inspect.getsource(item_cls.contextMenuEvent)``
    must reference both helper names. Catches a future shape that bypasses
    the central pattern (or an existing shape regressing to a hand-rolled
    bed-action block).
    """
    src = inspect.getsource(item_cls.contextMenuEvent)
    assert "build_bed_context_menu" in src, (
        f"{item_cls.__name__}.contextMenuEvent must call build_bed_context_menu — "
        "bed-specific actions must go through GardenItemMixin (ADR-017)."
    )
    assert "dispatch_bed_action" in src, (
        f"{item_cls.__name__}.contextMenuEvent must call dispatch_bed_action — "
        "bed-specific action routing must go through GardenItemMixin (ADR-017)."
    )
