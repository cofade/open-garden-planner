"""Unit choice must reach existing surfaces without recreating the plan."""
import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.config.settings import get_settings
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog


@pytest.fixture
def window(qtbot, monkeypatch):
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    monkeypatch.setattr(win, '_confirm_discard_changes', lambda: True)
    return win


def test_preferences_saves_unit_system(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog._unit_system_combo.setCurrentIndex(dialog._unit_system_combo.findData('imperial'))
    dialog._save_and_accept()
    assert get_settings().unit_system == 'imperial'


def test_status_bar_metric_unchanged(window):
    assert window.coord_label.text() == 'X: 0.00 cm  Y: 0.00 cm'


def test_status_bar_follows_setting(window):
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    assert window.coord_label.text() == 'X: 0"  Y: 0"'
    window.update_coordinates(30.48, -30.48)
    assert window.coord_label.text() == "X: 1' 0\"  Y: -1' 0\""


def test_selection_readout_follows_setting(window):
    item = RectangleItem(0, 0, 30.48, 30.48)
    window.canvas_scene.addItem(item)
    item.setSelected(True)
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    assert '1.00 ft²' in window.selection_label.text()


@pytest.mark.parametrize(("kind", "expected"), [('DISTANCE', ('A – B   1.23 m', 'A to B: 1.23 m')), ('EDGE_LENGTH', ('A   Edge 1.23 m', 'A edge length: 1.23 m')), ('HORIZONTAL', ('A – B   Horizontal', 'A horizontal align B')), ('VERTICAL', ('A – B   Vertical', 'A vertical align B')), ('ANGLE', ('A – B – …   123.5°', 'Angle A–B–…: 123.5°')), ('SYMMETRY_HORIZONTAL', ('A – B   Symmetric', 'A symmetric to B about the horizontal axis')), ('SYMMETRY_VERTICAL', ('A – B   Symmetric', 'A symmetric to B about the vertical axis')), ('COINCIDENT', ('A – B   Coincident', 'A coincident with B')), ('PARALLEL', ('A – B   Parallel', 'A parallel to B')), ('PERPENDICULAR', ('A – B   Perpendicular', 'A perpendicular to B')), ('EQUAL', ('A – B   Equal', 'A equal size to B')), ('FIXED', ('A   Fixed', 'A is fixed in place')), ('HORIZONTAL_DISTANCE', ('A – B   1.23 m', 'A to B: horizontal distance 1.23 m')), ('VERTICAL_DISTANCE', ('A – B   1.23 m', 'A to B: vertical distance 1.23 m')), ('POINT_ON_EDGE', ('A – B   On edge', 'A lies on the edge of B')), ('POINT_ON_CIRCLE', ('A – B   On circle', 'A lies on the circle of B')), ('TANGENT', ('A – B   Tangent', 'A tangent to B (r=1.23 m)'))])
def test_constraint_rows_metric_unchanged(kind, expected):
    from open_garden_planner.ui.constraint_presentation import descriptor_for_name
    assert descriptor_for_name(kind).render("A", "B", 123.456) == expected


def test_canvas_labels_follow_switch(window):
    from PyQt6.QtWidgets import QGraphicsSimpleTextItem

    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType
    a = RectangleItem(0, 0, 30.48, 30.48)
    b = RectangleItem(365.76, 0, 30.48, 30.48)
    window.canvas_scene.addItem(a)
    window.canvas_scene.addItem(b)
    a.area_label_visible = True
    window.canvas_scene.constraint_graph.add_constraint(AnchorRef(a.item_id, AnchorType.CENTER), AnchorRef(b.item_id, AnchorType.CENTER), 365.76)
    window.canvas_scene.dimension_line_manager.update_all()
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    assert a._area_label_item.text() == '1.00 ft²'
    assert any(i.text() == "12' 0\"" for i in window.canvas_scene.items() if isinstance(i, QGraphicsSimpleTextItem))


def test_constraint_rows_imperial(qtbot):
    from open_garden_planner.core.unit_preference import get_unit_preference
    from open_garden_planner.core.units import UnitSystem
    from open_garden_planner.ui.constraint_presentation import descriptor_for_name
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    assert "12' 0\"" in descriptor_for_name('DISTANCE').render('A', 'B', 365.76)[0]


def test_grid_and_scale_bar_follow_units(window):
    from open_garden_planner.core.units import UnitSystem, nice_distances
    assert window.canvas_view.grid_size == 50.0
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    assert window.canvas_view.grid_size == 30.48
    assert window.canvas_view._pick_scale_bar_distance() in nice_distances(UnitSystem.IMPERIAL)


def test_properties_rect_imperial(window, qtbot):
    from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox
    a = RectangleItem(0, 0, 243.84, 121.92)
    window.canvas_scene.addItem(a)
    a.setSelected(True)
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    qtbot.wait(1)
    texts = [box.text() for box in window.properties_panel.findChildren(LengthSpinBox)]
    assert "W: 8' 0\"" in texts
    assert "H: 4' 0\"" in texts


@pytest.mark.parametrize(('system', 'typed', 'expected'), [('imperial', '12', 30.48), ('metric', '31', 31)])
def test_soil_depth_preserves_native_input(window, qtbot, system, typed, expected):
    from PyQt6.QtCore import Qt
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox
    a = RectangleItem(0, 0, 243.84, 121.92, object_type=ObjectType.RAISED_BED)
    window.canvas_scene.addItem(a)
    a.setSelected(True)
    get_settings().unit_system = system
    window._apply_unit_setting()
    qtbot.wait(1)
    box = next(b for b in window.properties_panel.findChildren(LengthSpinBox) if 'Fill depth' in b.toolTip())
    box.lineEdit().selectAll()
    qtbot.keyClicks(box, typed)
    qtbot.keyClick(box, Qt.Key.Key_Return)
    assert a.metadata['soil_depth_cm'] == expected
    if system == 'metric':
        assert isinstance(a.metadata['soil_depth_cm'], int)


def test_no_write_back_on_rebuild(window, qtbot):
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem
    a = CircleItem(200, 200, 30, object_type=ObjectType.TREE)
    a.metadata['spacing_radius_cm'] = 60.0
    window.canvas_scene.addItem(a)
    a.setSelected(True)
    manager = window.canvas_view.command_manager
    before = len(manager._undo_stack)
    get_settings().unit_system = 'imperial'
    window._apply_unit_setting()
    qtbot.wait(1)
    window.properties_panel._rebuild_for_theme()
    window.properties_panel._rebuild_for_theme()
    assert a.metadata['spacing_radius_cm'] == 60
    assert len(manager._undo_stack) == before
