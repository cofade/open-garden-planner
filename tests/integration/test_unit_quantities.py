"""#907: temperature, precipitation and harvest mass follow their own units."""

from __future__ import annotations

import datetime

import pytest
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
    assert widget._table.item(0, 2).text() == "21.0"

    # ... and switching only the weather quantities leaves lengths alone.
    get_unit_preference().set_quantity_system(Quantity.TEMPERATURE, UnitSystem.IMPERIAL)
    get_unit_preference().set_quantity_system(Quantity.PRECIPITATION, UnitSystem.IMPERIAL)
    qtbot.wait(1)
    headers = [
        widget._table.horizontalHeaderItem(column).text()
        for column in (2, 3, 4)
    ]
    assert headers == ["Max °F", "Min °F", "Rain in"]
    assert widget._table.item(0, 2).text() == "69.8"
    assert widget._table.item(0, 4).text() == "1.00"
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

    # Negative Fahrenheit must stay negative in Celsius (#907 review P0).
    field.lineEdit().selectAll()
    qtbot.keyClicks(field, "-4 °F")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert field.value() == pytest.approx(-20.0)

    field.lineEdit().selectAll()
    qtbot.keyClicks(field, "-20 °F")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert field.value() == pytest.approx((-20.0 - 32.0) / 1.8)

    # Explicit °F entry also works while the field is displaying Metric (°C).
    get_unit_preference().set_quantity_system(Quantity.TEMPERATURE, UnitSystem.METRIC)
    field.lineEdit().selectAll()
    qtbot.keyClicks(field, "68 °F")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert field.value() == pytest.approx(20.0)
    assert field.text() == "20.0 °C"


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


def test_calendar_dashboard_frost_row_updates_on_live_temperature_switch(qtbot) -> None:
    """#907: PlantingCalendarView subscribes to profile_changed so Today's Tasks
    frost-alert titles switch between °C and °F without reopening the plan."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.weather_service import FrostAlert
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
    scene = CanvasScene(1000.0, 1000.0)
    plant = CircleItem(200.0, 200.0, 30.0, object_type=ObjectType.PERENNIAL)
    plant.name = "Tomato"
    scene.addItem(plant)
    pm = ProjectManager()
    view = PlantingCalendarView(scene, pm)
    qtbot.addWidget(view)

    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    view._current_frost_alerts = [
        FrostAlert(
            date=tomorrow,
            min_temp=-1.0,
            severity="red",
            affected_plant_ids=[str(plant.item_id)],
        )
    ]
    view._rebuild_dashboard()
    assert any("-1.0 °C" in t.display_name for t in view._current_dashboard_tasks)

    get_unit_preference().set_quantity_system(Quantity.TEMPERATURE, UnitSystem.IMPERIAL)
    qtbot.wait(1)
    assert any("30.2 °F" in t.display_name for t in view._current_dashboard_tasks)
    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))


def test_area_only_custom_switch_refreshes_scene_info_card_and_status_bar(qtbot) -> None:
    """#907: switching ONLY Quantity.AREA (leaving length metric) must refresh
    CanvasScene, View3DInfoCard and GardenPlannerApp's selection status bar."""
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.scene3d import Material, Params, Record, Transform
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
    from open_garden_planner.ui.view3d.info_card import CardSubject, View3DInfoCard

    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
    win = GardenPlannerApp()
    qtbot.addWidget(win)

    bed = RectangleItem(100.0, 100.0, 200.0, 100.0, object_type=ObjectType.GARDEN_BED)
    bed.name = "Bed 1"
    win.canvas_scene.addItem(bed)
    bed.setSelected(True)
    win.update_selection(1, [bed])
    assert "m²" in win.selection_label.text()

    card = View3DInfoCard()
    qtbot.addWidget(card)
    ring = ((0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0))
    rec = Record(
        item_id=str(bed.item_id),
        kind="GARDEN_BED",
        shape="polygon",
        footprints=(ring,),
        transform=Transform(100.0, 100.0, 0.0, 0.0),
        material=Material("GARDEN_BED"),
        height_cm=25.0,
        params=Params({"seed": str(bed.item_id)}),
    )
    card.show_subject(CardSubject(item=bed, record=rec, has_model=True))
    assert "m²" in card._body.text()

    rev_before = win.canvas_scene._paint_revision
    get_unit_preference().set_quantity_system(Quantity.AREA, UnitSystem.IMPERIAL)
    qtbot.wait(1)
    assert win.canvas_scene._paint_revision > rev_before
    assert "ft²" in win.selection_label.text()
    assert "ft²" in card._body.text()
    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))


def test_preferences_save_commits_uncommitted_frost_edit_before_unit_switch(qtbot) -> None:
    """#907: saving Preferences with an uncommitted Imperial frost edit AND a unit
    switch in the same dialog must commit the typed frost threshold first."""
    from open_garden_planner.app.settings import get_settings

    settings = get_settings()
    prev_orange = settings.frost_warning_orange_c
    prev_profile = settings.unit_profile
    try:
        get_unit_preference().set_profile(UnitProfile.all(UnitSystem.IMPERIAL))
        settings.unit_profile = UnitProfile.all(UnitSystem.IMPERIAL)
        settings.frost_warning_orange_c = 5.0

        dialog = PreferencesDialog()
        qtbot.addWidget(dialog)
        dialog._frost_orange_spin.lineEdit().selectAll()
        qtbot.keyClicks(dialog._frost_orange_spin, "35.0 °F")
        # Change temperature unit back to Metric WITHOUT blurring or hitting Return first.
        dialog._unit_temperature_combo.setCurrentIndex(
            dialog._unit_temperature_combo.findData(UnitSystem.METRIC.value)
        )
        dialog._save_and_accept()

        assert settings.frost_warning_orange_c == pytest.approx((35.0 - 32.0) / 1.8)
    finally:
        settings.frost_warning_orange_c = prev_orange
        settings.unit_profile = prev_profile
        get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))


def test_seed_packet_temp_spinboxes_fit_imperial_range_and_accept_input(qtbot) -> None:
    """#907: SeedPacketEditDialog temperature fields must not clip Imperial readouts
    (e.g. 140.0 °F) and must accept native °F input while storing Celsius."""
    from open_garden_planner.ui.dialogs.seed_inventory_dialog import SeedPacketEditDialog

    get_unit_preference().set_profile(UnitProfile.all(UnitSystem.IMPERIAL))
    try:
        dialog = SeedPacketEditDialog()
        qtbot.addWidget(dialog)
        dialog._temp_max.setValue(60.0)
        dialog.show()
        qtbot.wait(1)
        le = dialog._temp_max.lineEdit()
        assert le is not None
        advance = le.fontMetrics().horizontalAdvance(dialog._temp_max.text())
        assert le.width() >= advance, (
            f"SeedPacketEditDialog temp field clips {dialog._temp_max.text()!r}: "
            f"lineEdit width {le.width()} < text advance {advance}"
        )

        dialog._temp_opt.lineEdit().selectAll()
        qtbot.keyClicks(dialog._temp_opt, "68 °F")
        dialog._temp_opt.interpretText()
        assert dialog._temp_opt.value() == pytest.approx(20.0)
    finally:
        get_unit_preference().set_profile(UnitProfile.all(UnitSystem.METRIC))
