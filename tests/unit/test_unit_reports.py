from unittest.mock import MagicMock

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import UnitSystem
from open_garden_planner.services.shopping_list_service import ShoppingListService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem


def test_soil_prices_never_cross_unit_systems(qtbot):
    scene = CanvasScene()
    scene.addItem(RectangleItem(0, 0, 100, 100, object_type=ObjectType.RAISED_BED))
    service = ShoppingListService(
        scene, MagicMock(get_effective_record=MagicMock(return_value=None)), ProjectManager()
    )
    assert any(i.id == "soil_fill:m3" for i in service.build())
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    items = service.build()
    assert any(i.id == "soil_fill:ft3" and i.unit == "ft³" for i in items)
    assert any(i.id == "mulch:ft2" and i.unit == "ft²" for i in items)


def test_seed_depth_refreshes_without_reselection(qtbot):
    from open_garden_planner.models.plant_data import PlantSpeciesData
    from open_garden_planner.ui.views.planting_calendar_view import _DetailPanel

    panel = _DetailPanel()
    qtbot.addWidget(panel)
    panel.show_species(
        PlantSpeciesData(scientific_name="Plant", common_name="Plant", seed_depth_cm=0.635),
        "plant",
        None,
    )
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    assert 'Seed depth: 1/4"' in panel._info_lbl.text()
