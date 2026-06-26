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


def _make_container_rect() -> RectangleItem:
    return RectangleItem(0, 0, 100, 60, object_type=ObjectType.CONTAINER)


def _make_wall_planter() -> RectangleItem:
    return RectangleItem(0, 0, 120, 40, object_type=ObjectType.WALL_PLANTER)


def _make_container_round() -> CircleItem:
    return CircleItem(0, 0, 30, object_type=ObjectType.CONTAINER_ROUND)


def _make_trellis() -> RectangleItem:
    return RectangleItem(0, 0, 150, 20, object_type=ObjectType.TRELLIS)


# (factory, supports_grid, supports_soil) — supports_soil is False only for the
# trellis (a plant-parent that holds no soil, US-C3b).
BED_SHAPES = [
    pytest.param(_make_rectangle, True,  True,  id="RectangleItem-raised-bed"),
    pytest.param(_make_polygon,   True,  True,  id="PolygonItem-garden-bed"),
    pytest.param(_make_ellipse,   False, True,  id="EllipseItem-garden-bed"),
    pytest.param(_make_circle,    False, True,  id="CircleItem-garden-bed"),
    # US-C3a: containers are soil-capable (is_bed_type) → same bed menu.
    pytest.param(_make_container_rect,  True,  True,  id="RectangleItem-container"),
    pytest.param(_make_wall_planter,    True,  True,  id="RectangleItem-wall-planter"),
    pytest.param(_make_container_round, False, True,  id="CircleItem-round-container"),
    # US-C3b: trellis is a plant-parent but NOT soil — no grid, no soil test.
    pytest.param(_make_trellis,         False, False, id="RectangleItem-trellis"),
]


@pytest.mark.parametrize("factory,supports_grid,supports_soil", BED_SHAPES)
def test_bed_context_menu_has_all_features(
    factory, supports_grid: bool, supports_soil: bool, qtbot
) -> None:  # noqa: ARG001 — qtbot needed for Qt init
    """Every plant-parent shape exposes the non-soil bed actions; soil-test +
    grid are gated by supports_soil / supports_grid (trellis omits both)."""
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(
        menu,
        grid_enabled=False,
        supports_grid=supports_grid,
        supports_soil=supports_soil,
    )

    # Pest / harvest / succession are present on every plant-parent (climbers
    # get pests, get harvested, can be succession-planted).
    assert actions.log_pest_disease is not None, "Pest/disease log action missing"
    assert actions.log_harvest is not None, "Harvest log action missing"
    assert actions.plan_succession is not None, "Succession plan action missing"
    if supports_soil:
        assert actions.add_soil_test is not None, "Add soil test action missing"
    else:
        assert actions.add_soil_test is None, "Trellis must not offer a soil test"
    if supports_grid:
        assert actions.toggle_grid is not None, "Grid toggle missing on rectangular bed"
    else:
        assert actions.toggle_grid is None, "Round/vertical shapes have no grid toggle"


@pytest.mark.parametrize("factory,supports_grid,supports_soil", BED_SHAPES)
def test_bed_menu_actions_have_translated_text(
    factory, supports_grid: bool, supports_soil: bool, qtbot
) -> None:  # noqa: ARG001
    """Each present bed action must have non-empty label text (i18n-ready)."""
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(
        menu,
        grid_enabled=False,
        supports_grid=supports_grid,
        supports_soil=supports_soil,
    )

    assert actions.log_pest_disease.text(), "pest log action has empty text"
    assert actions.plan_succession.text(), "succession action has empty text"
    if supports_soil:
        assert actions.add_soil_test.text(), "soil test action has empty text"


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
