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
