"""Tests for properties panel."""

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


class TestNumericDimensionInput:
    """Tests for US-7.8: editable width/height/diameter in properties panel."""

    def _find_double_spinboxes(self, panel: PropertiesPanel) -> list:
        """Collect all QDoubleSpinBox widgets from the form layout."""
        from PyQt6.QtWidgets import QDoubleSpinBox, QWidget

        spinboxes = []
        for i in range(panel._form_layout.rowCount()):
            field = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.FieldRole)
            if field is None:
                continue
            widget = field.widget()
            if isinstance(widget, QDoubleSpinBox):
                spinboxes.append(widget)
            elif isinstance(widget, QWidget):
                # Look inside compound widgets (e.g. size row)
                for child in widget.findChildren(QDoubleSpinBox):
                    spinboxes.append(child)
        return spinboxes

    def test_circle_diameter_spin_present(self, qtbot):  # noqa: ARG002
        """Diameter spin box is shown for circles with correct initial value."""
        item = CircleItem(50.0, 50.0, 25.0)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        spinboxes = self._find_double_spinboxes(panel)
        diameter_values = [s.value() for s in spinboxes if s.suffix() == " cm"]
        assert any(abs(v - 50.0) < 0.01 for v in diameter_values), (
            f"Expected 50.0 cm diameter spin box, found values: {diameter_values}"
        )

    def test_circle_diameter_change_updates_radius(self, qtbot):  # noqa: ARG002
        """Changing diameter spin updates circle radius and keeps center fixed."""
        from PyQt6.QtWidgets import QDoubleSpinBox

        item = CircleItem(50.0, 50.0, 25.0)
        # Initial center in item coords (since pos is at 0,0): (25, 25) in item local space
        # Scene center = pos + rect.center = (0,0) + (25,25) = (25,25)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        # Find the diameter spin box
        spinboxes = self._find_double_spinboxes(panel)
        diameter_spin = next((s for s in spinboxes if s.suffix() == " cm"), None)
        assert diameter_spin is not None, "Diameter spin box not found"

        # Change diameter from 50 to 100 cm
        diameter_spin.setValue(100.0)

        # Radius should now be 50 cm
        assert abs(item.radius - 50.0) < 0.01, f"Expected radius 50, got {item.radius}"

    def test_circle_diameter_change_preserves_center(self, qtbot):  # noqa: ARG002
        """Changing diameter keeps scene center position fixed."""
        from PyQt6.QtWidgets import QDoubleSpinBox

        item = CircleItem(0.0, 0.0, 30.0)
        # pos = (0,0), rect = (0,0,60,60), scene center = (30, 30)
        item.setPos(0.0, 0.0)

        panel = PropertiesPanel()
        panel.set_selected_items([item])

        spinboxes = self._find_double_spinboxes(panel)
        diameter_spin = next((s for s in spinboxes if s.suffix() == " cm"), None)
        assert diameter_spin is not None

        # Compute old scene center
        old_rect = item.rect()
        old_center_x = item.pos().x() + old_rect.x() + old_rect.width() / 2
        old_center_y = item.pos().y() + old_rect.y() + old_rect.height() / 2

        # Change diameter
        diameter_spin.setValue(40.0)

        # Check new scene center is same
        new_rect = item.rect()
        new_center_x = item.pos().x() + new_rect.x() + new_rect.width() / 2
        new_center_y = item.pos().y() + new_rect.y() + new_rect.height() / 2

        assert abs(new_center_x - old_center_x) < 0.01, (
            f"Center X shifted: was {old_center_x}, now {new_center_x}"
        )
        assert abs(new_center_y - old_center_y) < 0.01, (
            f"Center Y shifted: was {old_center_y}, now {new_center_y}"
        )

    def test_rectangle_size_spinboxes_present(self, qtbot):  # noqa: ARG002
        """Width and height spin boxes are shown for rectangles."""
        item = RectangleItem(0.0, 0.0, 120.0, 80.0)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        spinboxes = self._find_double_spinboxes(panel)
        # Filter out position spinboxes (they have no suffix); size spinboxes also have no suffix
        # We expect at least 4 spinboxes: X, Y (position) + W, H (size)
        # Identify by value: position are scene coords, size are rect dims
        values = [s.value() for s in spinboxes]
        assert 120.0 in values or any(abs(v - 120.0) < 0.01 for v in values), (
            f"Expected width 120 in spinboxes, got {values}"
        )
        assert any(abs(v - 80.0) < 0.01 for v in values), (
            f"Expected height 80 in spinboxes, got {values}"
        )

    def _find_rect_size_spins(self, panel: PropertiesPanel):
        """Find the W and H spin boxes in the Size row of the form layout."""
        from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QWidget

        for i in range(panel._form_layout.rowCount()):
            label_item = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.LabelRole)
            field_item = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.FieldRole)
            if label_item is None or field_item is None:
                continue
            label_widget = label_item.widget()
            if not isinstance(label_widget, QLabel):
                continue
            # Look for "Size:" row (text may include trailing colon)
            if "Size" not in label_widget.text():
                continue
            field_widget = field_item.widget()
            if isinstance(field_widget, QWidget):
                children = field_widget.findChildren(QDoubleSpinBox)
                if len(children) == 2:  # noqa: PLR2004
                    return children[0], children[1]
        return None, None

    def test_rectangle_width_change_updates_rect(self, qtbot):  # noqa: ARG002
        """Changing width spin updates rectangle width."""
        item = RectangleItem(0.0, 0.0, 100.0, 50.0)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        w_spin, h_spin = self._find_rect_size_spins(panel)
        assert w_spin is not None, "Width spin box not found in Size row"
        assert h_spin is not None, "Height spin box not found in Size row"

        # Change width from 100 to 200
        w_spin.setValue(200.0)

        assert abs(item.rect().width() - 200.0) < 0.01, (
            f"Expected width 200, got {item.rect().width()}"
        )

    def test_rectangle_height_change_updates_rect(self, qtbot):  # noqa: ARG002
        """Changing height spin updates rectangle height."""
        item = RectangleItem(0.0, 0.0, 100.0, 50.0)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        _w_spin, h_spin = self._find_rect_size_spins(panel)
        assert h_spin is not None, "Height spin box not found in Size row"

        h_spin.setValue(90.0)

        assert abs(item.rect().height() - 90.0) < 0.01, (
            f"Expected height 90, got {item.rect().height()}"
        )

    def test_circle_resize_creates_undo_command(self, qtbot):  # noqa: ARG002
        """Resizing a circle via the panel creates a ResizeItemCommand."""
        from PyQt6.QtWidgets import QDoubleSpinBox

        from open_garden_planner.core.commands import CommandManager

        item = CircleItem(0.0, 0.0, 25.0)
        cmd_manager = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_manager)
        panel.set_selected_items([item])

        spinboxes = self._find_double_spinboxes(panel)
        diameter_spin = next((s for s in spinboxes if s.suffix() == " cm"), None)
        assert diameter_spin is not None

        initial_undo_count = len(cmd_manager._undo_stack)
        diameter_spin.setValue(80.0)

        assert len(cmd_manager._undo_stack) > initial_undo_count, (
            "Expected undo command to be created after diameter change"
        )

    def test_rectangle_resize_creates_undo_command(self, qtbot):  # noqa: ARG002
        """Resizing a rectangle via the panel creates a ResizeItemCommand."""
        from open_garden_planner.core.commands import CommandManager

        item = RectangleItem(0.0, 0.0, 100.0, 50.0)
        cmd_manager = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_manager)
        panel.set_selected_items([item])

        w_spin, _h_spin = self._find_rect_size_spins(panel)
        assert w_spin is not None, "Width spin box not found"

        initial_undo_count = len(cmd_manager._undo_stack)
        w_spin.setValue(150.0)

        assert len(cmd_manager._undo_stack) > initial_undo_count, (
            "Expected undo command to be created after width change"
        )
