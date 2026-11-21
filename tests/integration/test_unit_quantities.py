"""#907: temperature, precipitation and harvest mass follow their own units."""

from __future__ import annotations

from PyQt6.QtCore import Qt

from open_garden_planner.core.unit_preference import (
    Quantity,
    UnitPreset,
    UnitProfile,
    get_unit_preference,
)
from open_garden_planner.core.units import UnitSystem
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.weather_service import DayForecast, WeatherForecast
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog
from open_garden_planner.ui.views.planting_calendar_view import _DetailPanel
from open_garden_planner.ui.widgets.unit_spin_box import TemperatureSpinBox
from open_garden_planner.ui.widgets.weather_widget import WeatherWidget


def _forecast() -> WeatherForecast:
    return WeatherForecast(
        days=[
            DayForecast(
                date="2026-06-21",
                max_c=21.0,
                min_c=10.0,
                precipitation_mm=25.4,
                weathercode=0,
            )
        ],
        fetched_at="2026-06-21T00:00:00+00:00",
    )


def test_canada_preset_reaches_weather_and_germination_in_one_switch(qtbot) -> None:
    """One save in the dialog changes length, weather and the species card."""
    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog._unit_preset_combo.setCurrentIndex(
        dialog._unit_preset_combo.findData(UnitPreset.CANADA_MIXED.value)
    )
    dialog._save_and_accept()

    assert get_unit_preference().profile.preset == UnitPreset.CANADA_MIXED
    assert get_unit_preference().profile.system_for(Quantity.LENGTH) == UnitSystem.IMPERIAL
    assert get_unit_preference().profile.system_for(Quantity.TEMPERATURE) == UnitSystem.METRIC

    widget = WeatherWidget()
    qtbot.addWidget(widget)
    widget._on_fetch_success(_forecast())
    headers = [
        widget._table.horizontalHeaderItem(column).text()
        for column in (2, 3, 4)
    ]
    assert headers == ["Max °C", "Min °C", "Rain mm"]
    assert widget._table.item(0, 2).text() == "21.0 °C"

    # ... and switching only the weather quantities leaves lengths alone.
    get_unit_preference().set_quantity_system(Quantity.TEMPERATURE, UnitSystem.IMPERIAL)
    get_unit_preference().set_quantity_system(Quantity.PRECIPITATION, UnitSystem.IMPERIAL)
    qtbot.wait(1)
    headers = [
        widget._table.horizontalHeaderItem(column).text()
        for column in (2, 3, 4)
    ]
    assert headers == ["Max °F", "Min °F", "Rain in"]
    assert widget._table.item(0, 2).text() == "69.8 °F"
    assert widget._table.item(0, 4).text() == "1.00 in"
    assert get_unit_preference().profile.system_for(Quantity.LENGTH) == UnitSystem.IMPERIAL

    panel = _DetailPanel()
    qtbot.addWidget(panel)
    panel.show_species(
        PlantSpeciesData(
            scientific_name="Plant",
            common_name="Plant",
            min_germination_temp_c=10.0,
        ),
        "plant",
        None,
    )
    assert "50 °F" in panel._info_lbl.text()


def test_temperature_field_keeps_celsius_on_a_switch(qtbot) -> None:
    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
    field = TemperatureSpinBox()
    qtbot.addWidget(field)
    field.setRange(-30.0, 30.0)
    field.setDecimals(1)
    field.setSuffix(" °C")
    field.setValue(10.0)
    assert field.text() == "10.0 °C"
    get_unit_preference().set_quantity_system(Quantity.TEMPERATURE, UnitSystem.IMPERIAL)
    assert field.value() == 10.0
    assert field.text() == "50.0 °F"
    field.lineEdit().selectAll()
    qtbot.keyClicks(field, "68 °F")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert field.value() == 20.0


def test_the_harvest_entry_offers_the_mass_profiles_unit(qtbot) -> None:
    """#907: the mass row is not inert — it chooses the harvest default.

    A saved record keeps whatever unit was entered, so this is a default and
    not a conversion of history.
    """
    from open_garden_planner.ui.dialogs.harvest_log_dialog import HarvestLogDialog

    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
    metric = HarvestLogDialog(target_id="plant-1", target_name="Tomato")
    qtbot.addWidget(metric)
    assert metric._unit_combo.currentData() == "kg"

    get_unit_preference().set_quantity_system(Quantity.MASS, UnitSystem.IMPERIAL)
    imperial = HarvestLogDialog(target_id="plant-1", target_name="Tomato")
    qtbot.addWidget(imperial)
    assert imperial._unit_combo.currentData() == "lb"


def test_harvest_mass_units_stay_explicit_and_do_not_mix_totals(qtbot) -> None:
    from open_garden_planner.services.harvest_aggregation import aggregate_by_species_year

    history = HarvestHistory(
        target_id="plant-1",
        species_key="tomato",
        species_name="Tomato",
        records=[
            HarvestRecord(date="2026-07-01", quantity=1.0, unit="kg"),
            HarvestRecord(date="2026-07-02", quantity=2.0, unit="lb"),
        ],
    )
    totals = aggregate_by_species_year({"plant-1": history.to_dict()})
    assert {(row.unit, row.total_quantity) for row in totals} == {
        ("kg", 1.0),
        ("lb", 2.0),
    }
