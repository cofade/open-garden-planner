"""Issue #530 - the seven Properties-panel edits are undoable and mark the plan.

Seven handlers of the Properties panel wrote into the item DIRECTLY: a bed's
grid on/off and grid spacing, a bed's soil depth, and a container's material,
drainage, height and soil volume. A direct write is no command, so it was
neither undoable nor a mark of a modified plan: the edit was lost when the app
closed and asked nothing, and Ctrl+Z undid the container's creation instead of
its height.

Each of them is now ONE undoable step - a ``ChangePropertyCommand``, like the
panel's name, height, fill and stroke edits - and each still announces itself
to the 3D view (the plan revision moves; the sun's shadow sees the repaint).

The tests drive the REAL panel widgets of a REAL canvas, and they assert the
three things the defect was about: the edit takes effect, it is ONE undo step,
and undo puts the old value back.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSpinBox,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel


@pytest.fixture()
def canvas(qtbot) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


@pytest.fixture()
def panel(qtbot, canvas: CanvasView) -> PropertiesPanel:
    p = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(p)
    return p


def _field(panel: PropertiesPanel, label_text: str):
    """The widget of the form row whose label contains ``label_text``."""
    form = panel._form_layout
    for i in range(form.rowCount()):
        label_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if label_item is None or field_item is None:
            continue
        widget = label_item.widget()
        if isinstance(widget, QLabel) and label_text in widget.text():
            return field_item.widget()
    return None


def _bed(canvas: CanvasView) -> RectangleItem:
    item = RectangleItem(100.0, 100.0, 400.0, 300.0, object_type=ObjectType.RAISED_BED)
    canvas.scene().addItem(item)
    return item


def _container(canvas: CanvasView) -> CircleItem:
    item = CircleItem(800.0, 800.0, 60.0, object_type=ObjectType.CONTAINER_ROUND)
    canvas.scene().addItem(item)
    return item


def test_the_grid_edits_of_a_bed_are_one_undo_step_each(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    bed = _bed(canvas)
    panel.set_selected_items([bed])
    manager = canvas.command_manager

    grid = _field(panel, "Grid:")
    spacing = _field(panel, "Spacing:")
    assert isinstance(grid, QCheckBox) and isinstance(spacing, QDoubleSpinBox)

    steps = manager.undo_depth
    grid.setChecked(True)
    assert bed.grid_enabled is True
    assert manager.undo_depth == steps + 1, "the grid edit is one undo step"

    manager.undo()
    assert bed.grid_enabled is False, "and undo puts it back"

    steps = manager.undo_depth
    spacing.setValue(spacing.value() + 10.0)
    assert bed.grid_spacing == pytest.approx(spacing.value())
    assert manager.undo_depth == steps + 1, "the grid spacing edit is one undo step"

    manager.undo()
    assert bed.grid_spacing == pytest.approx(30.0), "and undo puts it back"


def test_the_soil_depth_of_a_bed_is_one_undo_step(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    bed = _bed(canvas)
    panel.set_selected_items([bed])
    manager = canvas.command_manager

    depth = _field(panel, "Soil depth:")
    assert isinstance(depth, QSpinBox)
    steps = manager.undo_depth

    depth.setValue(45)

    assert bed.metadata["soil_depth_cm"] == 45
    assert manager.undo_depth == steps + 1, "the soil depth edit is one undo step"

    manager.undo()
    assert "soil_depth_cm" not in bed.metadata, "and undo takes the value back out"


def test_the_container_edits_are_one_undo_step_each(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    container = _container(canvas)
    panel.set_selected_items([container])
    manager = canvas.command_manager

    material = _field(panel, "Material:")
    drainage = _field(panel, "Drainage:")
    height = _field(panel, "Height:")
    volume = _field(panel, "Soil volume:")
    assert isinstance(material, QComboBox) and isinstance(drainage, QCheckBox)
    assert isinstance(height, QSpinBox) and isinstance(volume, QDoubleSpinBox)

    steps = manager.undo_depth
    material.setCurrentIndex(material.findData("metal"))
    assert container.metadata["container_material"] == "metal"
    assert manager.undo_depth == steps + 1, "the material edit is one undo step"
    manager.undo()
    assert "container_material" not in container.metadata, "and undo takes it back out"

    steps = manager.undo_depth
    drainage.setChecked(not drainage.isChecked())
    assert container.metadata["container_drainage"] is drainage.isChecked()
    assert manager.undo_depth == steps + 1, "the drainage edit is one undo step"
    manager.undo()
    assert "container_drainage" not in container.metadata

    steps = manager.undo_depth
    height.setValue(70)
    assert container.metadata["container_height_cm"] == 70.0
    assert manager.undo_depth == steps + 1, "the height edit is one undo step"
    manager.undo()
    assert "container_height_cm" not in container.metadata

    steps = manager.undo_depth
    volume.setValue(12.5)
    assert container.metadata["container_soil_volume_l"] == 12.5
    assert manager.undo_depth == steps + 1, "the soil volume edit is one undo step"
    manager.undo()
    assert "container_soil_volume_l" not in container.metadata


def test_an_edit_announces_the_plan_change_the_3d_view_follows(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    """The edit is a command now, and it still moves the plan revision - that is
    what tells the 3D view (and the sun's shadow) that the container changed."""
    container = _container(canvas)
    panel.set_selected_items([container])
    height = _field(panel, "Height:")
    assert isinstance(height, QSpinBox)

    before = canvas.scene().plan_revision
    height.setValue(70)
    assert canvas.scene().plan_revision > before, "the plan revision moved"


def test_an_edit_marks_the_plan_modified(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    """The other half of the defect: a direct write marked nothing, so the app
    asked nothing when it closed and the edit was lost.

    The plan's dirty flag hangs off the command stack's ``stack_changed`` signal
    (``app/application.py`` wires it to ``ProjectManager.mark_dirty``), so that
    signal firing once per edit is what marks the plan."""
    container = _container(canvas)
    panel.set_selected_items([container])
    height = _field(panel, "Height:")
    assert isinstance(height, QSpinBox)

    announced: list[int] = []
    canvas.command_manager.stack_changed.connect(
        lambda: announced.append(len(announced)))

    height.setValue(70)

    assert announced, "the edit did not announce itself to the plan"


def test_an_unchanged_value_commits_nothing(
    canvas: CanvasView, panel: PropertiesPanel
) -> None:
    """A value that did not change is not an edit: no undo step, no noise."""
    container = _container(canvas)
    panel.set_selected_items([container])
    height = _field(panel, "Height:")
    assert isinstance(height, QSpinBox)

    steps = canvas.command_manager.undo_depth
    height.setValue(height.value())
    assert canvas.command_manager.undo_depth == steps


def test_the_panel_without_a_command_manager_still_edits(
    qtbot,
) -> None:
    """A panel with no command manager (a detached item, a test) still applies
    the edit - it just cannot undo it."""
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    container = CircleItem(0.0, 0.0, 60.0, object_type=ObjectType.CONTAINER_ROUND)
    panel.set_selected_items([container])

    height = _field(panel, "Height:")
    assert isinstance(height, QSpinBox)
    height.setValue(70)
    assert container.metadata["container_height_cm"] == 70.0
