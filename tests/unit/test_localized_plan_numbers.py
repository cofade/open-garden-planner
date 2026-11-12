"""#860: plan-level numbers use the UI language's decimal mark."""

from __future__ import annotations

import pytest

from open_garden_planner.core.i18n import set_current_language
from open_garden_planner.core.measurement_display import area_text
from open_garden_planner.core.measurements import format_scale_distance
from open_garden_planner.services.pdf_report_service import (
    _shopping_list_rows,
)


@pytest.fixture
def german(qtbot):
    set_current_language("de")
    try:
        yield
    finally:
        set_current_language("en")


def test_the_scale_bar_and_ruler_use_the_german_decimal_comma(german) -> None:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    assert format_scale_distance(150) == "1,5 m"
    assert format_scale_distance(250) == "2,5 m"
    assert CanvasView._ruler_label(150) == "1,5m"


def test_area_and_edge_labels_use_the_german_decimal_comma(german) -> None:
    from open_garden_planner.ui.canvas.items.vertex_handles import _format_edge_length

    assert area_text(15_000) == "1,50 m²"
    assert area_text(150) == "150,0 cm²"
    assert _format_edge_length(250) == "2,50 m"


def test_pdf_shopping_list_money_uses_the_german_decimal_comma(german) -> None:
    from open_garden_planner.models.shopping_list import (
        ShoppingListCategory as Cat,
    )
    from open_garden_planner.models.shopping_list import ShoppingListItem

    rows = _shopping_list_rows([
        ShoppingListItem(
            id="x:1", category=Cat.PLANTS, name="Basil",
            quantity=1.5, unit="x", price_each=1.25,
        )
    ])
    assert rows[0][2] == "1,5"
    assert rows[0][4] == "1,25"


def test_the_harvest_journal_writes_a_localized_quantity(german) -> None:
    from open_garden_planner.core.commands import _harvest_note_text
    from open_garden_planner.models.harvest_log import HarvestRecord

    text = _harvest_note_text(
        HarvestRecord(date="2026-06-21", quantity=2.5, unit="kg"), "Basil"
    )
    assert "2,5" in text
    assert "2.5" not in text


def test_measure_and_constraint_previews_use_the_german_decimal_comma(german, qtbot) -> None:
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.tools.constraint_tool import (
        _angle_preview_text,
        _distance_preview_text,
    )
    from open_garden_planner.core.tools.measure_tool import MeasureTool
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    assert _distance_preview_text(250.0) == "2,50 m"
    assert _angle_preview_text(45.0) == "45,0°"

    scene = CanvasScene(1000, 1000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    tool = MeasureTool(view)
    tool._draw_measurement(QPointF(0, 0), QPointF(250, 0))
    texts = [
        item.toPlainText()
        for item in tool._graphics_items
        if hasattr(item, "toPlainText")
    ]
    assert texts and texts[-1] == "2,50 m"
