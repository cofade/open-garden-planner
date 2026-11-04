"""A6: every generic property dispatcher branch is driven through its editor."""

import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel


@pytest.mark.parametrize("label,attribute,requested", [
    ("Type:", "object_type", ObjectType.CONTAINER),
    ("Label:", "label_visible", False),
    ("Layer:", "layer_id", "layer"),
    ("Fill Pattern:", "fill_pattern", FillPattern.GRAVEL),
    ("Stroke Width:", "stroke_width", 4.5),
    ("Stroke Style:", "stroke_style", StrokeStyle.DASHED),
])
def test_editor_change_is_one_step_and_restores_exact_value(qtbot, label, attribute, requested):
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)
    layer = Layer(name="Second")
    scene.add_layer(layer)
    item = RectangleItem(100, 100, 80, 60, object_type=ObjectType.RAISED_BED)
    item.label_visible = True
    scene.addItem(item)
    panel = PropertiesPanel(command_manager=view.command_manager)
    qtbot.addWidget(panel)
    panel.set_selected_items([item])
    field = None
    form = panel._form_layout
    for row in range(form.rowCount()):
        name = form.itemAt(row, form.ItemRole.LabelRole)
        if name and isinstance(name.widget(), QLabel) and name.widget().text() == label:
            field = form.itemAt(row, form.ItemRole.FieldRole).widget()
    assert field is not None
    before = getattr(item, attribute)
    value = layer.id if requested == "layer" else requested
    depth = view.command_manager.undo_depth
    if isinstance(field, QComboBox):
        index = field.findData(value)
        assert index >= 0
        field.setCurrentIndex(index)
    elif isinstance(field, QCheckBox):
        field.setChecked(value)
    else:
        assert isinstance(field, QDoubleSpinBox)
        field.setValue(value)
    assert getattr(item, attribute) == value
    assert view.command_manager.undo_depth == depth + 1
    view.command_manager.undo()
    assert getattr(item, attribute) == before
    view.command_manager.redo()
    assert getattr(item, attribute) == value
