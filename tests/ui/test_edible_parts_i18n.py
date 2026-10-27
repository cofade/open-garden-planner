"""Localized plant-detail values preserve the stored species vocabulary on edits."""

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.i18n import load_translator
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.ui.canvas.items import CircleItem
from open_garden_planner.ui.edible_parts import display_edible_parts, parse_edible_parts
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel


def test_german_edible_parts_are_visible_but_an_unrelated_edit_keeps_raw_values(qtbot):
    app = QApplication.instance()
    load_translator(app, "de")
    try:
        item = CircleItem(200, 200, 50, object_type=ObjectType.TREE)
        item.metadata["plant_species"] = PlantSpeciesData(
            scientific_name="Prunus persica", common_name="Pfirsich",
            edible=True, edible_parts=["fruit"], max_height_cm=600,
        ).to_dict()
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.set_selected_items([item])
        assert panel.edible_parts_edit.text() == "Früchte"
        panel.max_height_spin.setValue(550)
        panel._on_field_changed()
        assert item.metadata["plant_species"]["edible_parts"] == ["fruit"]
    finally:
        load_translator(app, "en")


@pytest.mark.parametrize("language,display", [("en", "Fruit, Roots"), ("de", "Früchte, Wurzeln"),
                                             ("es", "Frutos, Raíces")])
def test_localized_edible_part_editing_preserves_unknown_data(qtbot, language, display):
    app = QApplication.instance()
    load_translator(app, language)
    try:
        assert display_edible_parts(["fruit", "roots"]) == display
        assert parse_edible_parts(display + ", custom part", []) == ["fruit", "roots", "custom part"]
        assert parse_edible_parts(display_edible_parts(["Fruit", "unknown"]), ["Fruit", "unknown"]) == ["Fruit", "unknown"]
    finally:
        load_translator(app, "en")
