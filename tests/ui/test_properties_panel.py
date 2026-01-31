"""Tests for properties panel."""

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel


class TestPropertiesPanel:
    """Tests for the PropertiesPanel class."""

    def test_creation(self, qtbot):  # noqa: ARG002
        """Test that a properties panel can be created."""
        panel = PropertiesPanel()
        assert panel is not None

    def test_no_selection(self, qtbot):  # noqa: ARG002
        """Test panel shows 'no selection' when nothing is selected."""
        panel = PropertiesPanel()
        panel.set_selected_items([])
        # Panel should show no selection message
        assert panel._form_layout.rowCount() > 0

    def test_single_item_selection(self, qtbot):  # noqa: ARG002
        """Test panel shows properties for single selected item."""
        panel = PropertiesPanel()
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])
        # Panel should show properties
        assert panel._form_layout.rowCount() > 0


class TestObjectTypeChange:
    """Tests for changing object types in the properties panel."""

    def test_change_rectangle_to_house(self, qtbot):  # noqa: ARG002
        """Test changing a rectangle to a house."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.object_type == ObjectType.GENERIC_RECTANGLE

        # Change the object type
        item.object_type = ObjectType.HOUSE
        assert item.object_type == ObjectType.HOUSE

    def test_change_polygon_to_garden_bed(self, qtbot):  # noqa: ARG002
        """Test changing a polygon to a garden bed."""
        vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)]
        item = PolygonItem(vertices)
        assert item.object_type == ObjectType.GENERIC_POLYGON

        # Change the object type
        item.object_type = ObjectType.GARDEN_BED
        assert item.object_type == ObjectType.GARDEN_BED

    def test_change_circle_to_tree(self, qtbot):  # noqa: ARG002
        """Test changing a circle to a tree."""
        item = CircleItem(50, 50, 25)
        assert item.object_type == ObjectType.GENERIC_CIRCLE

        # Change the object type
        item.object_type = ObjectType.TREE
        assert item.object_type == ObjectType.TREE

    def test_change_house_to_pool(self, qtbot):  # noqa: ARG002
        """Test changing a house to a pool."""
        vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)]
        item = PolygonItem(vertices, object_type=ObjectType.HOUSE)
        assert item.object_type == ObjectType.HOUSE

        # Change the object type
        item.object_type = ObjectType.POND_POOL
        assert item.object_type == ObjectType.POND_POOL

    def test_change_garden_bed_to_terrace(self, qtbot):  # noqa: ARG002
        """Test changing a garden bed to a terrace."""
        vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)]
        item = PolygonItem(vertices, object_type=ObjectType.GARDEN_BED)
        assert item.object_type == ObjectType.GARDEN_BED

        # Change the object type
        item.object_type = ObjectType.TERRACE_PATIO
        assert item.object_type == ObjectType.TERRACE_PATIO

    def test_properties_panel_type_combo_includes_garden_bed(self, qtbot):  # noqa: ARG002
        """Test that the properties panel type combo includes Garden Bed."""
        from PyQt6.QtWidgets import QComboBox

        panel = PropertiesPanel()
        vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)]
        item = PolygonItem(vertices)
        panel.set_selected_items([item])

        # Find the type combo in the form layout
        type_combo = None
        for i in range(panel._form_layout.rowCount()):
            widget = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.FieldRole)
            if widget and isinstance(widget.widget(), QComboBox):
                combo = widget.widget()
                # Check if this is the type combo by looking for object types
                for j in range(combo.count()):
                    if combo.itemData(j) == ObjectType.HOUSE:
                        type_combo = combo
                        break
                if type_combo:
                    break

        assert type_combo is not None, "Type combo not found in properties panel"

        # Check that Garden Bed is in the combo
        garden_bed_found = False
        for i in range(type_combo.count()):
            if type_combo.itemData(i) == ObjectType.GARDEN_BED:
                garden_bed_found = True
                break

        assert garden_bed_found, "Garden Bed not found in type combo"
