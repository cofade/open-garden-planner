"""Exercise Qt's C++ editing path, not just Python setValue."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDoubleSpinBox, QInputDialog

from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import LengthStyle as S
from open_garden_planner.core.units import UnitSystem as U
from open_garden_planner.core.units import inches_to_cm
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox, VolumeSpinBox, get_length


def switch(system=U.IMPERIAL):
    get_unit_preference().set_system(system)


def make(qtbot, cls=LengthSpinBox, **kwargs):
    box = cls(**kwargs)
    box.setRange(-1000, 1000)
    qtbot.addWidget(box)
    return box


def enter(qtbot, box, text):
    box.lineEdit().selectAll()
    qtbot.keyClicks(box, text)
    qtbot.keyClick(box, Qt.Key.Key_Return)


def test_metric_text_matches_plain_spin_box(qtbot):
    plain, box = make(qtbot, QDoubleSpinBox), make(qtbot)
    for spin in (plain, box):
        spin.setDecimals(1)
        spin.setSuffix(" cm")
        spin.setValue(45.25)
    assert box.text() == plain.text()
    assert box.value() == plain.value()


def test_typed_inches_round_trip(qtbot):
    box = make(qtbot)
    box.setDecimals(1)
    switch()
    box.setValue(30.48)
    assert box.value() == 30.48
    assert box.text() == "1' 0\""
    for _ in range(10):
        enter(qtbot, box, '12"')
        assert box.value() == 30.48
        assert box.text() == "1' 0\""


def test_switch_emits_no_value_changed(qtbot):
    box = make(qtbot)
    box.setDecimals(1)
    box.setSuffix(" cm")
    box.setValue(60)
    with qtbot.assertNotEmitted(box.valueChanged):
        switch()
        assert box.text() == "1' 11 5/8\""
        switch(U.METRIC)
    assert box.value() == 60


def test_no_write_back(qtbot):
    switch()
    box = make(qtbot, style=S.PLANT_SIZE)
    box.setValue(60)
    assert box.text() == "2' 0\""
    box.show()
    box.setFocus()
    box.clearFocus()
    box.editingFinished.emit()
    assert box.value() == 60


def test_step_snaps_to_native_unit(qtbot):
    box = make(qtbot)
    box.setSingleStep(10)
    switch()
    box.setValue(60)
    box.stepBy(1)
    assert box.value() == pytest.approx(inches_to_cm(28))
    box.stepBy(-1)
    assert box.value() == pytest.approx(inches_to_cm(24))


@pytest.mark.parametrize("special", ["—", "Not set", "Auto"])
def test_special_value_survives_switch(qtbot, special):
    box = make(qtbot)
    box.setRange(0, 100)
    box.setSpecialValueText(special)
    box.setValue(0)
    with qtbot.assertNotEmitted(box.valueChanged):
        switch()
        assert box.text() == special
        switch(U.METRIC)
        assert box.text() == special


def test_metres_value_unit(qtbot):
    box = make(qtbot, style=S.METRES, value_unit_cm=100)
    box.setDecimals(2)
    box.setSuffix(" m")
    box.setValue(1.5)
    assert box.text() == "1.50 m"
    switch()
    assert box.text() == "4' 11\""
    enter(qtbot, box, "5")
    assert box.value() == pytest.approx(1.524)


def test_garbage_rejected(qtbot):
    switch()
    box = make(qtbot)
    box.setValue(30.48)
    enter(qtbot, box, "abc")
    assert box.value() == 30.48


@pytest.mark.parametrize(
    ("text", "expected"),
    [("30 cm", 30), ("2,5 ft", 76.2), ("1.5m", 150), ('2 1/2"', 6.35), ("-2' 6\"", -76.2)],
)
def test_other_units_accepted(qtbot, text, expected):
    switch()
    box = make(qtbot)
    enter(qtbot, box, text)
    assert box.value() == pytest.approx(expected)


def test_volume_spin_box(qtbot):
    switch()
    box = make(qtbot, VolumeSpinBox)
    box.setValue(3.785411784)
    assert box.text() == "1.0 gal"
    assert box.value() == 3.785411784
    enter(qtbot, box, "2 qt")
    assert box.value() == pytest.approx(1.892705892)


def test_get_length_metric_delegates(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QInputDialog, "getDouble", lambda *args: calls.append(args) or (30.48, True)
    )
    assert get_length(None, "Title", "Distance", 30.48, 0, 100) == (30.48, True)
    assert calls == [(None, "Title", "Distance", 30.48, 0, 100, 2)]
