import pytest

from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import UnitSystem
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox


@pytest.mark.parametrize(('module', 'cls', 'field'), [
    ('grid_array_dialog', 'GridArrayDialog', '_row_spacing_spin'),
    ('linear_array_dialog', 'LinearArrayDialog', '_spacing_spin'),
    ('circular_array_dialog', 'CircularArrayDialog', '_radius_spin'),
    ('array_along_path_dialog', 'ArrayAlongPathDialog', '_spacing_spin'),
    ('new_project_dialog', 'NewProjectDialog', 'width_spinbox'),
    ('location_dialog', 'LocationDialog', '_elev_spin'),
])
def test_dialog_field_keeps_metric_value_on_switch(qtbot, module, cls, field):
    import importlib
    dialog = getattr(importlib.import_module('open_garden_planner.ui.dialogs.' + module), cls)()
    qtbot.addWidget(dialog)
    box = getattr(dialog, field)
    assert isinstance(box, LengthSpinBox)
    before = box.value()
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    assert box.value() == before


def test_constraint_dialog_returns_centimetres(qtbot):
    from open_garden_planner.core.tools.constraint_tool import DistanceInputDialog
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    dialog = DistanceInputDialog(365.76)
    qtbot.addWidget(dialog)
    assert dialog._spin.text() == "12' 0\""
    assert dialog.distance_cm() == 365.76
