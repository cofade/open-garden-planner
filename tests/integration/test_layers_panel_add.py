"""Integration tests: new layers default to the top of the layer order (issue #201).

Verifies the full LayersPanel <-> CanvasScene workflow when the user clicks
"Add Layer":
  - the new layer is inserted at the TOP of the order (list index 0),
  - the scene recomputes z_order so the new layer has the highest z_order,
  - the new layer becomes the scene's active layer,
  - stacking is reflected on the QGraphicsItems (new-layer items render above
    items on pre-existing layers),
  - repeated adds keep stacking newest-on-top.

The panel/scene wiring here mirrors MainWindow (application.py:1205-1212):
  panel.layers_reordered    -> scene.reorder_layers
  panel.active_layer_changed -> scene.set_active_layer (via get_layer_by_id)
"""

# ruff: noqa: ARG001, ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.commands import AddLayerCommand
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels.layers_panel import LayersPanel


@pytest.fixture()
def wired(qtbot: object) -> tuple[CanvasView, LayersPanel, CanvasScene]:
    """Canvas + LayersPanel wired together exactly like MainWindow."""
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    panel = LayersPanel()
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)

    panel.set_layers(scene.layers)
    panel.layers_reordered.connect(scene.reorder_layers)
    # Mirror the scene -> panel round-trip wired in GardenPlannerApp
    # (application.py:1217): reorder_layers emits layers_changed, which rebuilds
    # the panel list. _on_add_layer relies on this path for its refresh.
    scene.layers_changed.connect(lambda: panel.set_layers(scene.layers))
    # Mirror GardenPlannerApp._on_layer_add_requested: the panel only requests
    # the add; an undoable AddLayerCommand performs the top-insert + activation.
    panel.layer_add_requested.connect(
        lambda name: view.command_manager.execute(
            AddLayerCommand(scene, Layer(name=name))
        )
    )
    # Mirror the scene -> panel active-layer sync (select the new top layer).
    scene.active_layer_changed.connect(
        lambda layer: panel.select_layer(layer.id) if layer else None
    )

    def _activate(layer_id: object) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer:
            scene.set_active_layer(layer)

    panel.active_layer_changed.connect(_activate)
    return view, panel, scene


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> RectangleItem:
    """Draw a rectangle on the active layer and return the newly created item.

    Note: QGraphicsScene.items() returns items in stacking order (not insertion
    order), so the new rectangle is identified by diffing the item set rather
    than indexing.
    """
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

    before = {i for i in view.scene().items() if isinstance(i, RectangleItem)}
    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))

    after = {i for i in view.scene().items() if isinstance(i, RectangleItem)}
    (new_item,) = after - before
    return new_item


class TestNewLayerGoesOnTop:
    def test_new_layer_inserted_at_index_zero(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """A newly added layer occupies the top slot (index 0) of the order."""
        _, panel, scene = wired
        original_top = scene.layers[0]

        panel._on_add_layer()

        assert scene.layers[0] is not original_top
        assert scene.layers[0].name == "Layer 2"
        assert original_top in scene.layers[1:]

    def test_new_layer_has_highest_z_order(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """The new top layer gets the highest z_order after the scene recomputes it."""
        _, panel, scene = wired

        panel._on_add_layer()

        new_layer = scene.layers[0]
        assert new_layer.z_order == max(layer.z_order for layer in scene.layers)
        # With 2 layers, top index -> z_order 1, bottom index -> z_order 0.
        assert new_layer.z_order == len(scene.layers) - 1

    def test_new_layer_becomes_active(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Adding a layer activates it so new elements land on top."""
        _, panel, scene = wired

        panel._on_add_layer()

        assert scene.active_layer is scene.layers[0]
        assert scene.active_layer.name == "Layer 2"

    def test_repeated_adds_stack_newest_on_top(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Each new layer stacks above the previously added one."""
        _, panel, scene = wired

        panel._on_add_layer()  # Layer 2 -> top
        first_added = scene.layers[0]
        panel._on_add_layer()  # Layer 3 -> top
        second_added = scene.layers[0]

        assert second_added.name == "Layer 3"
        assert scene.layers[1] is first_added
        assert second_added.z_order > first_added.z_order

    def test_item_on_new_layer_renders_above_existing(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """An item drawn on the new top layer has a higher zValue than one below."""
        view, panel, scene = wired

        bottom_item = _draw_rect(view, 100, 100, 300, 200)

        panel._on_add_layer()  # new active top layer
        top_item = _draw_rect(view, 150, 150, 350, 250)

        assert top_item.layer_id == scene.layers[0].id
        assert top_item.zValue() > bottom_item.zValue()

    def test_refresh_preserves_selection_by_identity_not_index(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """A non-top selection survives a top-insert refresh by identity, not row.

        Guards the _refresh_list selection-restore fix: inserting a layer at the
        top shifts every existing row down by one, so restoring by row index would
        select the wrong layer. We select the original bottom layer, then rebuild
        the list (as the scene round-trip does) and assert the same layer is still
        the current row.
        """
        _, panel, scene = wired

        panel._on_add_layer()  # now [Layer 2 (top), Layer 1]
        original = scene.layers[1]  # the pre-existing "Layer 1"

        # Select the original layer (row 1), then force a full list rebuild.
        panel.layer_list.setCurrentRow(1)
        panel._refresh_list()

        current = panel.layer_list.currentItem()
        widget = panel.layer_list.itemWidget(current)
        assert widget.layer.id == original.id
