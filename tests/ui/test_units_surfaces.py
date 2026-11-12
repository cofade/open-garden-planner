"""Unit choice must reach existing surfaces without recreating the plan."""
import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.config.settings import get_settings
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog


@pytest.fixture
def window(qtbot):
    win = GardenPlannerApp()
    qtbot.addWidget(win)
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
