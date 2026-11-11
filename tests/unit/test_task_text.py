"""#856: the Tasks tab and the calendar dashboard share one task row text."""

from __future__ import annotations

from open_garden_planner.ui.views.task_text import task_row_text


def test_a_plant_task_gets_its_verb(qtbot) -> None:
    assert task_row_text("harvest", "Rosemary") == "Harvest Rosemary"
    assert task_row_text("direct_sow", "Carrot") == "Direct sow Carrot"
    assert task_row_text("transplant", "Tomato") == "Transplant Tomato outdoors"
    assert task_row_text("harden_off", "Leek") == "Start hardening off Leek"


def test_a_complete_label_is_not_decorated(qtbot) -> None:
    assert task_row_text("manual", "Order compost") == "Order compost"
    assert task_row_text("soil_mismatch", "Basil — acid soil") == "Basil — acid soil"
    assert task_row_text("succession_sow", "Lettuce") == "Lettuce"
