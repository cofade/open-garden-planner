"""UI tests for US-8.5: Planting Calendar View."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from open_garden_planner.ui.views.planting_calendar_view import (
    PlantingCalendarView,
    _GanttWidget,
    _date_to_x,
    _days_in_year,
    _NAME_W,
    _MONTH_W,
    _parse_frost,
)


# ─── Unit helpers ─────────────────────────────────────────────────────────────


class TestHelpers:
    def test_days_in_year_leap(self) -> None:
        assert _days_in_year(2024) == 366

    def test_days_in_year_non_leap(self) -> None:
        assert _days_in_year(2025) == 365

    def test_days_in_year_century_non_leap(self) -> None:
        assert _days_in_year(1900) == 365

    def test_days_in_year_400_year_leap(self) -> None:
        assert _days_in_year(2000) == 366

    def test_date_to_x_jan1(self) -> None:
        x = _date_to_x(1, 1, 2025)
        assert x == pytest.approx(_NAME_W, abs=1)

    def test_date_to_x_dec31(self) -> None:
        x = _date_to_x(12, 31, 2025)
        assert x < _NAME_W + 12 * _MONTH_W
        assert x > _NAME_W + 11 * _MONTH_W  # somewhere in December

    def test_parse_frost_valid(self) -> None:
        d = _parse_frost("05-15", 2025)
        assert d == datetime.date(2025, 5, 15)

    def test_parse_frost_invalid(self) -> None:
        assert _parse_frost("bad", 2025) is None
        assert _parse_frost("13-01", 2025) is None

    def test_parse_frost_none(self) -> None:
        assert _parse_frost(None, 2025) is None  # type: ignore[arg-type]


# ─── PlantingCalendarView widget ──────────────────────────────────────────────


def _make_mock_project(location: dict | None = None):
    pm = MagicMock()
    pm.location = location
    return pm


def _make_mock_scene(items: list | None = None):
    scene = MagicMock()
    scene.items.return_value = items or []
    return scene


class TestPlantingCalendarViewEmptyState:
    """Calendar shows empty state messages when no data is available."""

    def test_no_location_shows_empty_label(self, qtbot) -> None:
        view = PlantingCalendarView(_make_mock_scene(), _make_mock_project(None))
        qtbot.addWidget(view)
        assert not view._empty_lbl.isHidden()
        assert view._scroll.isHidden()
        assert "location" in view._empty_lbl.text().lower()

    def test_no_plants_shows_empty_label(self, qtbot) -> None:
        location = {"frost_dates": {"last_spring_frost": "05-15"}}
        view = PlantingCalendarView(_make_mock_scene([]), _make_mock_project(location))
        qtbot.addWidget(view)
        assert not view._empty_lbl.isHidden()
        assert "plants" in view._empty_lbl.text().lower()

    def test_location_but_no_frost_date_shows_empty(self, qtbot) -> None:
        location = {"latitude": 51.0, "longitude": 10.0}  # no frost_dates key
        view = PlantingCalendarView(_make_mock_scene([]), _make_mock_project(location))
        qtbot.addWidget(view)
        assert not view._empty_lbl.isHidden()

    def test_detail_panel_hidden_initially(self, qtbot) -> None:
        view = PlantingCalendarView(_make_mock_scene(), _make_mock_project(None))
        qtbot.addWidget(view)
        assert view._detail.isHidden()


class TestPlantingCalendarViewWithData:
    """Calendar shows chart rows when plants with calendar data are present."""

    def _make_plant_item(self) -> MagicMock:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        species = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            indoor_sow_start=-8,
            indoor_sow_end=-6,
            transplant_start=2,
            transplant_end=4,
            harvest_start=10,
            harvest_end=20,
        )
        item = MagicMock()
        item.metadata = {"plant_species": species.to_dict()}
        return item

    def _location(self) -> dict:
        return {"frost_dates": {"last_spring_frost": "05-15", "first_fall_frost": "10-01"}}

    def test_chart_visible_with_plant_data(self, qtbot) -> None:
        view = PlantingCalendarView(
            _make_mock_scene([self._make_plant_item()]),
            _make_mock_project(self._location()),
        )
        qtbot.addWidget(view)
        assert not view._scroll.isHidden()
        assert view._empty_lbl.isHidden()

    def test_one_row_per_unique_species(self, qtbot) -> None:
        # Two items with same species → only 1 row
        items = [self._make_plant_item(), self._make_plant_item()]
        view = PlantingCalendarView(
            _make_mock_scene(items),
            _make_mock_project(self._location()),
        )
        qtbot.addWidget(view)
        assert len(view._rows) == 1

    def test_detail_panel_shows_on_row_click(self, qtbot) -> None:
        view = PlantingCalendarView(
            _make_mock_scene([self._make_plant_item()]),
            _make_mock_project(self._location()),
        )
        qtbot.addWidget(view)
        view._on_row_clicked(0)
        assert not view._detail.isHidden()

    def test_detail_panel_hides_on_deselect(self, qtbot) -> None:
        view = PlantingCalendarView(
            _make_mock_scene([self._make_plant_item()]),
            _make_mock_project(self._location()),
        )
        qtbot.addWidget(view)
        view._on_row_clicked(0)
        assert not view._detail.isHidden()
        view._on_row_clicked(-1)
        assert view._detail.isHidden()

    def test_items_without_calendar_data_excluded(self, qtbot) -> None:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        species_no_cal = PlantSpeciesData(scientific_name="Foo bar", common_name="Foo")
        item = MagicMock()
        item.metadata = {"plant_species": species_no_cal.to_dict()}

        view = PlantingCalendarView(
            _make_mock_scene([item]),
            _make_mock_project(self._location()),
        )
        qtbot.addWidget(view)
        assert not view._empty_lbl.isHidden()
        assert len(view._rows) == 0


class TestPlantingCalendarRefresh:
    """refresh() rebuilds the chart from updated state."""

    def _plant_item(self) -> MagicMock:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        sp = PlantSpeciesData(
            scientific_name="Lactuca sativa",
            common_name="Lettuce",
            direct_sow_start=-2,
            direct_sow_end=4,
            harvest_start=6,
            harvest_end=10,
        )
        item = MagicMock()
        item.metadata = {"plant_species": sp.to_dict()}
        return item

    def test_refresh_updates_rows(self, qtbot) -> None:
        scene = _make_mock_scene([])
        pm = _make_mock_project({"frost_dates": {"last_spring_frost": "04-15"}})
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        assert len(view._rows) == 0

        scene.items.return_value = [self._plant_item()]
        view.refresh()
        assert len(view._rows) == 1

    def test_refresh_after_location_cleared(self, qtbot) -> None:
        scene = _make_mock_scene([self._plant_item()])
        pm = _make_mock_project({"frost_dates": {"last_spring_frost": "04-15"}})
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        assert not view._scroll.isHidden()

        pm.location = None
        view.refresh()
        assert not view._empty_lbl.isHidden()


# ─── GanttWidget ──────────────────────────────────────────────────────────────


class TestGanttWidget:
    """Unit tests for the _GanttWidget painter-level logic."""

    def test_set_data_updates_size(self, qtbot) -> None:
        from open_garden_planner.ui.views.planting_calendar_view import (
            _PlantRow,
            _HEADER_H,
            _ROW_H,
            _TOTAL_W,
        )
        from open_garden_planner.models.plant_data import PlantSpeciesData

        w = _GanttWidget()
        qtbot.addWidget(w)
        sp = PlantSpeciesData(scientific_name="A b", common_name="A")
        rows = [_PlantRow(display_name="A", species=sp)]
        w.set_data(rows, 2025, None, None)
        assert w.width() == _TOTAL_W
        assert w.height() == _HEADER_H + _ROW_H

    def test_row_at_returns_minus_one_in_header(self, qtbot) -> None:
        from open_garden_planner.ui.views.planting_calendar_view import _HEADER_H

        w = _GanttWidget()
        qtbot.addWidget(w)
        assert w._row_at(_HEADER_H - 1) == -1

    def test_row_at_returns_zero_first_row(self, qtbot) -> None:
        from open_garden_planner.ui.views.planting_calendar_view import (
            _PlantRow,
            _HEADER_H,
        )
        from open_garden_planner.models.plant_data import PlantSpeciesData

        w = _GanttWidget()
        qtbot.addWidget(w)
        sp = PlantSpeciesData(scientific_name="A b", common_name="A")
        w.set_data([_PlantRow("A", sp)], 2025, None, None)
        assert w._row_at(_HEADER_H + 1) == 0

    def test_row_at_out_of_bounds(self, qtbot) -> None:
        from open_garden_planner.ui.views.planting_calendar_view import _HEADER_H, _ROW_H

        w = _GanttWidget()
        qtbot.addWidget(w)
        assert w._row_at(_HEADER_H + 9999) == -1
