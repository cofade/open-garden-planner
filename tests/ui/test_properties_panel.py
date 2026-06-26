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


class TestFocusPreservation:
    """Regression tests for issue #200: live-edit fields must not lose focus.

    Typing in the Name (``QLineEdit``) or Text Content (``QTextEdit``) field
    emits ``can_undo_changed`` / ``can_redo_changed``, which (wired up in
    ``application.py``) deferred-calls ``set_selected_items``. If the panel's
    focus-preservation guard does not cover the focused widget, the whole form
    is rebuilt and the field being typed into is destroyed — dropping focus and
    the caret after every keystroke.
    """

    @staticmethod
    def _find_field_by_label(panel: PropertiesPanel, label_text: str):
        """Return the field widget whose form-row label contains label_text."""
        from PyQt6.QtWidgets import QLabel

        form = panel._form_layout
        for i in range(form.rowCount()):
            label_item = form.itemAt(i, form.ItemRole.LabelRole)
            field_item = form.itemAt(i, form.ItemRole.FieldRole)
            if label_item is None or field_item is None:
                continue
            label_widget = label_item.widget()
            if isinstance(label_widget, QLabel) and label_text in label_widget.text():
                return field_item.widget()
        return None

    def test_name_field_survives_rebuild_while_focused(self, qtbot, monkeypatch):  # noqa: ARG002
        """Issue #200: the Name field keeps its widget (and focus) across a rebuild."""
        from PyQt6.QtWidgets import QApplication, QLineEdit

        from open_garden_planner.core.commands import CommandManager

        item = RectangleItem(0, 0, 100, 50)
        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])

        name_edit = self._find_field_by_label(panel, "Name")
        assert isinstance(name_edit, QLineEdit), "Name field not found in panel"

        # Simulate the field holding keyboard focus (deterministic, no window).
        monkeypatch.setattr(QApplication, "focusWidget", lambda: name_edit)  # type: ignore[attr-defined]

        # Mimic the per-keystroke rebuild trigger (can_undo/redo_changed).
        panel.set_selected_items([item])

        after = self._find_field_by_label(panel, "Name")
        assert after is name_edit, (
            "Name field was rebuilt while focused — focus/caret would be lost (#200)"
        )

    def test_name_field_rebuilds_when_unfocused(self, qtbot, monkeypatch):  # noqa: ARG002
        """Guard is not over-broad: an unfocused panel still rebuilds normally."""
        from PyQt6.QtWidgets import QApplication, QLineEdit

        item = RectangleItem(0, 0, 100, 50)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        # Nothing in the panel holds focus → the rebuild must proceed.
        monkeypatch.setattr(QApplication, "focusWidget", lambda: None)  # type: ignore[attr-defined]
        panel.set_selected_items([item])

        name_edit = self._find_field_by_label(panel, "Name")
        assert isinstance(name_edit, QLineEdit), (
            "Name field should still render after an unfocused rebuild"
        )

    def test_panel_updates_when_focus_outside_panel(self, qtbot, monkeypatch):  # noqa: ARG002
        """Guard fires only for the panel's own widgets: external focus still updates.

        Locks the ``and self.isAncestorOf(fw)`` clause — a focused editable widget
        that is *not* a descendant of the panel must not suppress the update. Since
        #206 a same-selection call refreshes the live widgets in place (the widget
        is reused, not recreated), so this asserts the refreshed *value* lands
        rather than a teardown.
        """
        from PyQt6.QtWidgets import QApplication, QLineEdit

        item = RectangleItem(0, 0, 100, 50)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        before = self._find_field_by_label(panel, "Name")
        assert isinstance(before, QLineEdit), "Name field not found in panel"

        # Mutate the model, then re-trigger with focus on a QLineEdit that is NOT
        # parented to the panel → isAncestorOf is False → the update must proceed
        # and the refreshed value must reach the (reused) field.
        item.name = "Birch"
        stray = QLineEdit()
        monkeypatch.setattr(QApplication, "focusWidget", lambda: stray)  # type: ignore[attr-defined]
        panel.set_selected_items([item])

        after = self._find_field_by_label(panel, "Name")
        assert after is before, "same selection should reuse the live widget (#206)"
        assert after.text() == "Birch", (
            "external focus must not suppress the in-place value refresh"
        )

    def test_text_content_field_survives_rebuild_while_focused(self, qtbot, monkeypatch):  # noqa: ARG002
        """Latent #200 sibling: the Text annotation Content box must also survive."""
        from PyQt6.QtWidgets import QApplication, QTextEdit

        from open_garden_planner.core.commands import CommandManager
        from open_garden_planner.ui.canvas.items import TextItem

        item = TextItem(10, 10, content="Hello")
        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])

        content_edit = self._find_field_by_label(panel, "Content")
        assert isinstance(content_edit, QTextEdit), "Content field not found in panel"

        monkeypatch.setattr(QApplication, "focusWidget", lambda: content_edit)  # type: ignore[attr-defined]
        panel.set_selected_items([item])

        after = self._find_field_by_label(panel, "Content")
        assert after is content_edit, (
            "Text Content field was rebuilt while focused — focus would be lost (#200)"
        )


class TestContainerProperties:
    """US-C3: container material/drainage/height/soil-volume controls."""

    def _labels(self, panel: PropertiesPanel) -> list:
        from PyQt6.QtWidgets import QLabel

        out = []
        for i in range(panel._form_layout.rowCount()):
            field = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.LabelRole)
            if field and isinstance(field.widget(), QLabel):
                out.append(field.widget().text())
        return out

    def test_container_section_shown_for_container(self, qtbot):  # noqa: ARG002
        item = RectangleItem(0, 0, 80, 50, object_type=ObjectType.CONTAINER)
        panel = PropertiesPanel()
        panel.set_selected_items([item])
        labels = self._labels(panel)
        assert "Material:" in labels
        assert "Height:" in labels
        assert "Soil volume:" in labels

    def test_container_section_absent_for_plain_bed(self, qtbot):  # noqa: ARG002
        item = RectangleItem(0, 0, 80, 50, object_type=ObjectType.GARDEN_BED)
        panel = PropertiesPanel()
        panel.set_selected_items([item])
        assert "Material:" not in self._labels(panel)

    def test_editing_material_updates_metadata(self, qtbot):  # noqa: ARG002
        from PyQt6.QtWidgets import QComboBox

        from open_garden_planner.core import container_model as cm

        item = RectangleItem(0, 0, 80, 50, object_type=ObjectType.CONTAINER)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        combo = None
        for i in range(panel._form_layout.rowCount()):
            field = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.FieldRole)
            widget = field.widget() if field else None
            if isinstance(widget, QComboBox) and widget.currentData() in cm.MATERIALS:
                combo = widget
                break
        assert combo is not None, "material combo not found"
        idx = cm.MATERIALS.index(cm.WOOD)
        combo.setCurrentIndex(idx)
        assert item.metadata["container_material"] == cm.WOOD

    def test_effective_volume_refreshes_on_footprint_change(self, qtbot):  # noqa: ARG002
        """The derived 'Effective' volume must re-compute on incremental refresh
        (e.g. after a canvas resize changes the footprint), not go stale."""
        from PyQt6.QtWidgets import QLabel

        item = RectangleItem(0, 0, 100, 100, object_type=ObjectType.CONTAINER)
        panel = PropertiesPanel()
        panel.set_selected_items([item])

        def effective_text() -> str:
            for i in range(panel._form_layout.rowCount()):
                lbl = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.LabelRole)
                fld = panel._form_layout.itemAt(i, panel._form_layout.ItemRole.FieldRole)
                if (
                    lbl and isinstance(lbl.widget(), QLabel)
                    and lbl.widget().text() == "Effective:"
                    and fld and isinstance(fld.widget(), QLabel)
                ):
                    return fld.widget().text()
            return ""

        before = effective_text()
        # Shrink the footprint, then trigger an incremental refresh (no rebuild).
        item.setRect(0, 0, 50, 50)
        panel._refresh_field_values()
        after = effective_text()
        assert before and after and before != after, (
            f"Effective volume did not refresh on footprint change: {before!r} -> {after!r}"
        )
