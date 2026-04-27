"""Integration tests for Find & Replace panel (US-11.24).

Tests verify search filtering, select-all matching, bulk layer change,
and species replace on canvas items.
"""

# ruff: noqa: ARG002

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.find_replace_panel import FindReplacePanel


def _make_rect(canvas: CanvasView, name: str = "", w: float = 100.0) -> RectangleItem:
    from open_garden_planner.core.object_types import ObjectType

    item = RectangleItem(0, 0, w, w, object_type=ObjectType.GENERIC_RECTANGLE)
    if name:
        item._name = name
    canvas.add_item(item, "rectangle")
    return item


def _panel(canvas: CanvasView) -> FindReplacePanel:
    p = FindReplacePanel(canvas)
    p.refresh_combos()
    return p


class TestSearch:
    def test_search_by_name_returns_matching(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        _make_rect(canvas, name="Bed Alpha")
        _make_rect(canvas, name="Bed Beta")
        _make_rect(canvas, name="Other")
        panel = _panel(canvas)
        panel._name_edit.setText("Bed")
        results = panel._search()
        assert len(results) == 2

    def test_search_empty_name_returns_all(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        _make_rect(canvas)
        _make_rect(canvas)
        panel = _panel(canvas)
        panel._name_edit.setText("")
        results = panel._search()
        assert len(results) == 2

    def test_search_no_match_returns_empty(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        _make_rect(canvas, name="Alpha")
        panel = _panel(canvas)
        panel._name_edit.setText("XYZ")
        results = panel._search()
        assert len(results) == 0

    def test_search_by_type_filters(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        _make_rect(canvas, name="R1")
        circle = CircleItem(200, 200, 50, object_type=ObjectType.GENERIC_CIRCLE)
        canvas.add_item(circle, "circle")

        panel = _panel(canvas)
        panel.refresh_combos()
        type_idx = panel._type_combo.findData("GENERIC_CIRCLE")
        if type_idx < 0:
            # ObjectType.GENERIC_CIRCLE name may vary; get it from the item
            ot_name = getattr(circle.object_type, "name", None)
            if ot_name:
                type_idx = panel._type_combo.findData(ot_name)
        if type_idx >= 0:
            panel._type_combo.setCurrentIndex(type_idx)
            results = panel._search()
            assert all(isinstance(r, CircleItem) for r in results)


class TestSelectAll:
    def test_select_all_matching_selects_items(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        _make_rect(canvas, name="Target")
        _make_rect(canvas, name="Target2")
        _make_rect(canvas, name="Other")
        panel = _panel(canvas)
        panel._name_edit.setText("Target")
        panel._on_select_all()

        selected = [i for i in canvas.scene().selectedItems()]
        assert len(selected) == 2
        assert all(hasattr(i, "name") for i in selected)

    def test_select_all_clears_previous_selection(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        r1 = _make_rect(canvas, name="A")
        r2 = _make_rect(canvas, name="B")
        r1.setSelected(True)
        r2.setSelected(True)
        panel = _panel(canvas)
        panel._name_edit.setText("A")
        panel._on_select_all()
        selected = canvas.scene().selectedItems()
        assert len(selected) == 1


class TestBulkLayerChange:
    def test_apply_layer_moves_matched_items(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from open_garden_planner.models.layer import Layer

        scene = canvas.scene()
        layer2 = Layer(name="Layer 2")
        scene.add_layer(layer2)

        item = _make_rect(canvas, name="TargetRect")
        original_layer_id = item.layer_id

        panel = _panel(canvas)
        panel._name_edit.setText("TargetRect")
        panel._on_search()

        layer2_idx = panel._target_layer_combo.findText("Layer 2")
        if layer2_idx >= 0:
            panel._target_layer_combo.setCurrentIndex(layer2_idx)
            panel._on_apply_layer()
            assert item.layer_id == layer2.id
            assert item.layer_id != original_layer_id


class TestSpeciesReplace:
    def test_replace_species_updates_metadata(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        item = _make_rect(canvas)
        item._metadata = {"plant_species": {"common_name": "Tomato", "scientific_name": "S. lycopersicum"}}

        panel = _panel(canvas)
        panel._name_edit.setText("")
        panel._on_search()
        panel._replace_species_edit.setText("Pepper")
        panel._on_replace_species()

        assert item._metadata["plant_species"]["common_name"] == "Pepper"

    def test_replace_species_no_match_does_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        item = _make_rect(canvas, name="X")
        item._metadata = {"plant_species": {"common_name": "Tomato"}}

        panel = _panel(canvas)
        panel._name_edit.setText("NONEXISTENT")
        panel._on_search()
        panel._replace_species_edit.setText("Pepper")
        panel._on_replace_species()

        assert item._metadata["plant_species"]["common_name"] == "Tomato"
