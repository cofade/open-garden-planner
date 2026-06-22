"""Plant Details panel — missing enum traits must render as a neutral "—", not
the first concrete dropdown option (#231).

Regression: the characteristic combos (cycle / flower type / pollination / sun /
water) were built with the ``UNKNOWN`` member excluded, and the populate code
fell back to ``setCurrentIndex(0)`` when a value was unknown — so a species with
no data for a trait was silently shown as the first option (e.g. a tree's
lifecycle read "Annual"). Worse, saving then wrote that wrong concrete value back.
"""
# ruff: noqa: ARG002

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantCycle, PlantSpeciesData
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel


def _plant(species: PlantSpeciesData) -> CircleItem:
    item = CircleItem(
        center_x=0, center_y=0, radius=20, object_type=ObjectType.TREE, name="Tree"
    )
    item.metadata["plant_species"] = species.to_dict()
    return item


class TestUnknownEnumRendersDash:
    def test_sparse_species_shows_dash_not_first_option(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        # A sparse species (e.g. from online Search) — every trait defaults UNKNOWN.
        panel.set_selected_items([_plant(PlantSpeciesData(scientific_name="Prunus domestica", common_name="Plum"))])

        # Regression guard: cycle was "annual" (index 0 of the UNKNOWN-excluded combo).
        assert panel.cycle_combo.currentData() == PlantCycle.UNKNOWN.value
        assert panel.cycle_combo.currentText() == "—"
        # The sibling characteristic combos were equally bogus index-0 fallbacks.
        for combo in (
            panel.flower_type_combo,
            panel.pollination_combo,
            panel.sun_combo,
            panel.water_combo,
        ):
            assert combo.currentData() == "unknown"
            assert combo.currentText() == "—"

    def test_known_cycle_still_displayed(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        species = PlantSpeciesData(
            scientific_name="Prunus domestica", common_name="Plum", cycle=PlantCycle.PERENNIAL
        )
        panel.set_selected_items([_plant(species)])

        assert panel.cycle_combo.currentData() == PlantCycle.PERENNIAL.value
        assert panel.cycle_combo.currentText() != "—"


class TestMissingDimensionsShowDash:
    """Missing dimension/pH/hardiness traits render as "—", not "0 cm"/"0"/"0.0" (#231).

    Sibling of the enum-combo regression above: the spin-boxes used
    ``setSpecialValueText("")`` — an *empty* string, which Qt treats as *disabling*
    the special-value feature, so a missing (0 = "unset" sentinel) value printed as a
    real "0 cm" instead of blank. A non-empty "—" engages the placeholder.
    """

    # Every dimension/pH/hardiness box (species traits + instance current size).
    _SPINS = (
        "max_height_spin",
        "max_spread_spin",
        "current_height_spin",
        "current_spread_spin",
        "hardiness_min_spin",
        "hardiness_max_spin",
        "ph_min_spin",
        "ph_max_spin",
    )

    def test_special_value_text_is_non_empty_dash(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        for name in self._SPINS:
            assert getattr(panel, name).specialValueText() == "—", name

    def test_sparse_species_shows_dash_not_zero(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        # A sparse online-search result — every dimension field defaults to None.
        panel.set_selected_items(
            [_plant(PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut"))]
        )
        for name in self._SPINS:
            spin = getattr(panel, name)
            assert spin.value() == 0, name  # the "unset" sentinel
            assert spin.text() == "—", name  # regression guard: was "0 cm"/"0"/"0.0"

    def test_known_dimensions_show_numbers(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        species = PlantSpeciesData(
            scientific_name="Juglans regia",
            common_name="Walnut",
            max_height_cm=800,
            max_spread_cm=600,
            ph_min=6.0,
            hardiness_zone_min=4,
        )
        panel.set_selected_items([_plant(species)])
        assert panel.max_height_spin.value() == 800
        assert panel.max_height_spin.text() != "—"
        assert panel.max_spread_spin.value() == 600
        assert panel.ph_min_spin.value() == 6.0
        assert panel.ph_min_spin.text() != "—"
        assert panel.hardiness_min_spin.value() == 4

    def test_sparse_species_saves_back_as_none(self, qtbot) -> None:
        # The dash-at-0 display must not corrupt a missing value into a concrete 0
        # on save (mirrors the enum combos' UNKNOWN→concrete corruption guard).
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.set_selected_items(
            [_plant(PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut"))]
        )
        panel._on_field_changed()
        assert panel._current_plant_data.max_height_cm is None
        assert panel._current_plant_data.max_spread_cm is None
        assert panel._current_plant_data.ph_min is None
        assert panel._current_plant_data.hardiness_zone_min is None
