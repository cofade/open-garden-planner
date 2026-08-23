"""Integration tests: the Properties panel's Arrange section (issue #338).

Exercises the panel-specific wiring added in `_add_arrange_section` —
button construction (icon/text fallback, tooltip, accessible name,
`objectName`), the "delegate to the live view selection, else build +
execute the command directly" branch, and the panel's own refresh-after-
command path (`set_selected_items`) — rather than the pure arrange
algorithm (`tests/unit/test_stacking.py`) or the `CanvasView`/context-menu
surfaces (`tests/integration/test_arrange_z_order.py` and friends).

Uses a real `CanvasScene` + `CanvasView` (the `canvas` fixture from
`tests/integration/conftest.py`) because z-order derivation
(`scene._normalized_layer_order`) is a `CanvasScene` responsibility that a
bare `QGraphicsScene` does not provide.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton

from open_garden_planner.core.commands import GroupCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem, TextItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.panels import PropertiesPanel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bottom_to_top_names(scene) -> list[str]:
    """Every named item in the scene, bottom-to-top by z-value."""
    items = [i for i in scene.items() if getattr(i, "name", None)]
    return [i.name for i in sorted(items, key=lambda i: i.zValue())]


def _panel(canvas: CanvasView, qtbot) -> PropertiesPanel:
    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)
    return panel


def _rect(name: str, x: float, y: float, layer_id, width: float = 100.0, height: float = 100.0) -> RectangleItem:
    return RectangleItem(
        x, y, width, height, object_type=ObjectType.GENERIC_RECTANGLE, name=name, layer_id=layer_id
    )


# ---------------------------------------------------------------------------
# Single-item selection
# ---------------------------------------------------------------------------


class TestArrangeSectionSingleSelection:
    def test_bring_to_front_flips_z_and_is_undoable(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        lower = _rect("lower", 0, 0, layer_id)
        upper = _rect("upper", 20, 20, layer_id)
        scene.addItem(lower)
        scene.addItem(upper)
        assert _bottom_to_top_names(scene) == ["lower", "upper"]

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([lower])

        button = panel.findChild(QPushButton, "arrange_front_button")
        assert button is not None
        assert canvas.command_manager.can_undo is False

        button.click()

        assert _bottom_to_top_names(scene) == ["upper", "lower"]
        assert canvas.command_manager.can_undo is True
        undo_count = len(canvas.command_manager._undo_stack)
        assert undo_count == 1

    def test_clicking_again_when_already_at_front_pushes_no_new_undo_step(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        lower = _rect("lower", 0, 0, layer_id)
        upper = _rect("upper", 20, 20, layer_id)
        scene.addItem(lower)
        scene.addItem(upper)

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([lower])
        button = panel.findChild(QPushButton, "arrange_front_button")
        assert button is not None

        button.click()
        undo_count = len(canvas.command_manager._undo_stack)
        assert _bottom_to_top_names(scene) == ["upper", "lower"]

        button.click()  # already at front -> no-op

        assert len(canvas.command_manager._undo_stack) == undo_count
        assert _bottom_to_top_names(scene) == ["upper", "lower"]

    def test_arrange_buttons_have_icon_or_text_tooltip_and_object_name(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        item = _rect("solo", 0, 0, layer_id)
        scene.addItem(item)

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([item])

        expected = {
            "arrange_front_button": "Bring to Front",
            "arrange_forward_button": "Bring Forward",
            "arrange_backward_button": "Send Backward",
            "arrange_back_button": "Send to Back",
        }
        for object_name, label in expected.items():
            button = panel.findChild(QPushButton, object_name)
            assert button is not None, f"missing {object_name}"
            assert button.toolTip() == label
            assert button.accessibleName() == label
            # Either a real icon or a text fallback -- never neither.
            assert not button.icon().isNull() or button.text() == label


# ---------------------------------------------------------------------------
# Multi-selection
# ---------------------------------------------------------------------------


class TestArrangeSectionMultiSelection:
    def test_section_present_and_send_to_back_keeps_relative_order(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        a = _rect("a", 0, 0, layer_id)
        b = _rect("b", 20, 20, layer_id)
        c = _rect("c", 40, 40, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)
        assert _bottom_to_top_names(scene) == ["a", "b", "c"]

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([b, c])

        headers = [
            w.text() for w in panel.findChildren(QLabel) if w.text() == "Arrange"
        ]
        assert headers, "Arrange header missing from multi-selection view"

        button = panel.findChild(QPushButton, "arrange_back_button")
        assert button is not None
        undo_count_before = len(canvas.command_manager._undo_stack)

        button.click()

        # b, c move to the back as a block, keeping their relative order.
        assert _bottom_to_top_names(scene) == ["b", "c", "a"]
        assert len(canvas.command_manager._undo_stack) == undo_count_before + 1


# ---------------------------------------------------------------------------
# Other arrangeable item types (early-return branches in _show_single_item)
# ---------------------------------------------------------------------------


class TestArrangeSectionAppearsForOtherItemTypes:
    def test_text_item_shows_arrange_section(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        text = TextItem(10, 10, content="hello", layer_id=layer_id)
        scene.addItem(text)

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([text])

        assert panel.findChild(QPushButton, "arrange_front_button") is not None

    def test_group_item_shows_arrange_section(self, canvas: CanvasView, qtbot) -> None:
        scene = canvas.scene()
        layer_id = scene.layers[0].id
        a = _rect("a", 0, 0, layer_id, width=50, height=50)
        b = _rect("b", 60, 60, layer_id, width=50, height=50)
        scene.addItem(a)
        scene.addItem(b)
        canvas.command_manager.execute(GroupCommand(scene, [a, b]))
        group = a.parentItem()
        assert isinstance(group, GroupItem)

        panel = _panel(canvas, qtbot)
        panel.set_selected_items([group])

        assert panel.findChild(QPushButton, "arrange_front_button") is not None
