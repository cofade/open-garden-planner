"""The plant's own calendar snapshot drives its rendered fruit season (#387)."""

import datetime as dt

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.phenology import evaluate_phenology_for_records
from open_garden_planner.services.task_generator import (
    PlanState,
    PlantRowInput,
    generate_for_date_window,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.view3d.snapshot import snapshot_records


@pytest.mark.parametrize("frost,day", [("09-20", dt.date(2027, 1, 1)),
                                      ("02-29", dt.date(2027, 6, 7))])
def test_instance_harvest_and_task_calendar_agree_across_years(qtbot, frost, day):
    scene = CanvasScene(1000, 1000)
    item = CircleItem(200, 200, 30, object_type=ObjectType.PERENNIAL, metadata={
        "height_cm": 150,
        "plant_species": {"common_name": "Tomato", "harvest_start": 10, "harvest_end": 20},
    })
    item.plant_species = "Tomato"
    scene.addItem(item)
    row = PlantRowInput("Tomato", "tomato", harvest_start=10, harvest_end=20)
    from open_garden_planner.core.frost_dates import parse_frost
    for date in (day - dt.timedelta(days=80), day, day + dt.timedelta(days=80)):
        records = snapshot_records(scene, date)
        record = records[str(item.item_id)]
        assert record.params["harvest_start"] == 10
        assert record.params["harvest_end"] == 20
        state = evaluate_phenology_for_records(
            tuple(records.values()), date, frost_dates={"last_spring_frost": frost},
        )[str(item.item_id)]
        plan = PlanState(date, date.year, last_frost=parse_frost(frost, date.year),
                         last_frost_mmdd=frost, plant_rows=(row,), actionable_only=False)
        tasks = generate_for_date_window(plan, date, date)
        assert (state.ripeness > 0) == any(task.task_type == "harvest" for task in tasks)
