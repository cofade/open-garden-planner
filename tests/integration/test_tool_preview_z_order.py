"""Integration tests: an in-progress tool preview draws ABOVE a bed (issue #377).

Symptom: dragging a plant into a bed hides the dashed preview behind the bed, so
the user places blind. Root cause: preview primitives kept Qt's default ``z = 0``
while every real item gets a derived z strictly inside ``(0, 100)``
(``CanvasScene._refresh_layer_z``).

These tests exercise the real tool gesture, not a stub: a bed is put in the scene
first, then the tool's press/move runs, and the live preview item's z is compared
against the bed's.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem


def _press(scene_pos: tuple[float, float]) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _add_bed(view: CanvasView, x: float, y: float, w: float, h: float) -> RectangleItem:
    bed = RectangleItem(x, y, w, h, object_type=ObjectType.RAISED_BED)
    view.scene().addItem(bed)
    return bed


def _preview_items(view: CanvasView, bed: RectangleItem) -> list[QGraphicsItem]:
    """Bare Qt primitives in the scene, excluding real items and the bed."""
    return [
        item
        for item in view.scene().items()
        if item is not bed and not hasattr(item, "object_type")
    ]


# Tool, first-click anchor, second point — all inside the bed rect (100..500).
_GESTURES = [
    (ToolType.CIRCLE, (300, 300), (380, 380)),
    (ToolType.RECTANGLE, (200, 200), (400, 400)),
    (ToolType.ELLIPSE, (200, 200), (400, 400)),
]


class TestPreviewOutranksBed:
    @pytest.mark.parametrize(("tool", "start", "end"), _GESTURES)
    def test_preview_z_is_above_the_bed(
        self,
        canvas: CanvasView,
        qtbot: object,
        tool: ToolType,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> None:
        bed = _add_bed(canvas, 100, 100, 400, 300)
        canvas.set_active_tool(tool)
        active = canvas.tool_manager.active_tool

        active.mouse_press(_press(start), QPointF(*start))
        active.mouse_move(_press(end), QPointF(*end))

        previews = _preview_items(canvas, bed)
        assert previews, f"{tool} produced no preview item"
        for preview in previews:
            assert preview.zValue() >= 1, f"{tool} preview still at default z"
            assert preview.zValue() > bed.zValue(), (
                f"{tool} preview z={preview.zValue()} does not beat bed "
                f"z={bed.zValue()}"
            )

    def test_preview_beats_a_bed_at_every_edge(self, canvas: CanvasView, qtbot: object) -> None:
        """Parameterise the overlap: fully inside vs straddling the bed edge."""
        bed = _add_bed(canvas, 100, 100, 400, 300)
        canvas.set_active_tool(ToolType.RECTANGLE)
        active = canvas.tool_manager.active_tool

        for start, end in [((200, 200), (300, 300)), ((50, 50), (150, 150))]:
            active.cancel()
            active.mouse_press(_press(start), QPointF(*start))
            active.mouse_move(_press(end), QPointF(*end))
            previews = _preview_items(canvas, bed)
            assert previews
            assert all(p.zValue() > bed.zValue() for p in previews)


def test_preview_band_constants_match_the_source() -> None:
    """Drift guard: every preview-building module is either in the band or has
    its own established one.

    Re-derived from source rather than the issue's list, which omitted
    construction_tool.py and wrongly named three modules that build no preview.
    The scan covers BOTH construction styles (direct `QGraphics*Item(...)` and
    `scene.add*()`), because measure_tool/constraint_tool use the latter and the
    original census missed them for exactly that reason.
    """
    from pathlib import Path

    from open_garden_planner.core.tools import preview_z

    tools_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "open_garden_planner"
        / "core"
        / "tools"
    )
    ctor = re.compile(
        r"QGraphics(?:EllipseItem|LineItem|PathItem|RectItem|PolygonItem)\("
        r"|scene\(\)\.add(?:Ellipse|Line|Path|Rect|Polygon|Text)\("
        r"|\.add(?:Ellipse|Line|Path|Rect|Polygon|Text)\("
    )
    # Modules that already govern their preview z with their own established
    # constant and are NOT part of the #377 defect: offset_tool (9999),
    # trim_tool (_HIGHLIGHT_Z), measure_tool / constraint_tool (1000-1003).
    established = {
        "offset_tool.py",
        "trim_tool.py",
        "measure_tool.py",
        "constraint_tool.py",
    }
    offenders = []
    for path in sorted(tools_dir.glob("*_tool.py")):
        if path.name in established:
            continue
        text = path.read_text(encoding="utf-8")
        if not ctor.search(text):
            continue
        if "preview_z import" not in text:
            offenders.append(path.name)
    assert not offenders, f"modules build previews but skip the band: {offenders}"
    assert preview_z.PREVIEW_Z_FILL > 100
