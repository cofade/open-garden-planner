"""Integration tests: ALL layer operations are undoable via the command stack.

Covers the fix for "layer actions don't react to Ctrl+Z": create, delete,
rename, drag-reorder, visibility, lock and opacity all route through
CommandManager-executed commands now, so undo()/redo() reverse them.

The fixture mirrors the MainWindow wiring in GardenPlannerApp._setup_sidebar /
the layer handlers: the panel emits request signals only; small local handlers
(mirroring application.py) construct and execute the commands; the scene is the
single mutator; the scene -> panel round-trip (layers_changed -> set_layers,
active_layer_changed -> select_layer) keeps the panel in sync.
"""

# ruff: noqa: ARG001, ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.commands import (
    AddLayerCommand,
    DeleteLayerCommand,
    RenameLayerCommand,
    ReorderLayersCommand,
    SetLayerPropertyCommand,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels.layers_panel import LayerListItem, LayersPanel


@pytest.fixture()
def wired(qtbot: object) -> tuple[CanvasView, LayersPanel, CanvasScene]:
    """Canvas + LayersPanel wired together exactly like MainWindow."""
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    panel = LayersPanel()
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    manager = view.command_manager

    panel.set_layers(scene.layers)
    scene.layers_changed.connect(lambda: panel.set_layers(scene.layers))
    scene.active_layer_changed.connect(
        lambda layer: panel.select_layer(layer.id) if layer else None
    )

    # Handlers mirroring GardenPlannerApp's layer command construction.
    def _on_add_requested(name: str) -> None:
        manager.execute(AddLayerCommand(scene, Layer(name=name)))

    def _on_reordered(new_order: list) -> None:
        if [lyr.id for lyr in new_order] == [lyr.id for lyr in scene.layers]:
            return
        manager.execute(ReorderLayersCommand(scene, new_order))

    def _on_renamed(layer_id: object, new_name: str) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer is None or layer.name == new_name:
            return
        manager.execute(RenameLayerCommand(scene, layer, new_name))

    def _on_deleted(layer_id: object) -> None:
        if len(scene.layers) <= 1 or scene.get_layer_by_id(layer_id) is None:  # type: ignore[arg-type]
            return
        manager.execute(DeleteLayerCommand(scene, layer_id))  # type: ignore[arg-type]

    def _on_visibility(layer_id: object, visible: bool) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer is None or layer.visible == visible:
            return
        manager.execute(
            SetLayerPropertyCommand(scene, layer, "visible", layer.visible, visible)
        )

    def _on_lock(layer_id: object, locked: bool) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer is None or layer.locked == locked:
            return
        manager.execute(
            SetLayerPropertyCommand(scene, layer, "locked", layer.locked, locked)
        )

    def _on_opacity_committed(layer_id: object, old: float, new: float) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer is None or abs(old - new) < 1e-9:
            return
        manager.execute(SetLayerPropertyCommand(scene, layer, "opacity", old, new))

    panel.layer_add_requested.connect(_on_add_requested)
    panel.layers_reordered.connect(_on_reordered)
    panel.layer_renamed.connect(_on_renamed)
    panel.layer_deleted.connect(_on_deleted)
    panel.layer_visibility_changed.connect(_on_visibility)
    panel.layer_lock_changed.connect(_on_lock)
    panel.layer_opacity_changed.connect(scene.preview_layer_opacity)
    panel.layer_opacity_committed.connect(_on_opacity_committed)

    def _activate(layer_id: object) -> None:
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[arg-type]
        if layer:
            scene.set_active_layer(layer)

    panel.active_layer_changed.connect(_activate)
    return view, panel, scene


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> RectangleItem:
    """Draw a rectangle on the active layer and return the newly created item."""
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


def _item_widget(panel: LayersPanel, row: int) -> LayerListItem:
    widget = panel.layer_list.itemWidget(panel.layer_list.item(row))
    assert isinstance(widget, LayerListItem)
    return widget


class TestAddLayerUndo:
    def test_add_undo_redo_round_trip(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Add via the panel button → one undo step removes it, redo restores it."""
        view, panel, scene = wired
        manager = view.command_manager
        prev_active = scene.active_layer
        assert not manager.can_undo

        panel._on_add_layer()

        assert manager.can_undo
        assert len(scene.layers) == 2
        new_layer = scene.layers[0]
        assert scene.active_layer is new_layer
        assert panel.layer_list.count() == 2

        manager.undo()

        assert len(scene.layers) == 1
        assert new_layer not in scene.layers
        assert scene.active_layer is prev_active
        assert panel.layer_list.count() == 1

        manager.redo()

        assert scene.layers[0] is new_layer
        assert scene.active_layer is new_layer
        assert panel.layer_list.count() == 2


class TestDeleteLayerUndo:
    def test_delete_with_items_undo_restores_assignment(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Deleting a layer with a drawn item reassigns it; undo restores it."""
        view, panel, scene = wired
        manager = view.command_manager
        panel._on_add_layer()  # new top layer, active
        target = scene.layers[0]
        item = _draw_rect(view, 100, 100, 300, 200)
        assert item.layer_id == target.id
        original_index = scene.layers.index(target)
        replacement = scene.layers[1]

        panel._on_delete_layer(target.id)

        assert target not in scene.layers
        assert item.layer_id == replacement.id

        manager.undo()

        assert scene.layers[original_index] is target
        assert item.layer_id == target.id
        assert panel.layer_list.count() == 2

    def test_delete_last_layer_is_blocked(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """The single remaining layer cannot be deleted and pushes no command."""
        view, panel, scene = wired
        manager = view.command_manager

        panel._on_delete_layer(scene.layers[0].id)

        assert len(scene.layers) == 1
        assert not manager.can_undo


class TestRenameLayerUndo:
    def test_rename_via_editor_undo_restores_name(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Renaming through the inline editor is one undoable step."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]
        old_name = layer.name
        widget = _item_widget(panel, 0)

        widget.name_edit.setText("Vegetables")
        widget._finish_editing()

        assert layer.name == "Vegetables"
        assert manager.can_undo
        assert _item_widget(panel, 0).name_label.text() == "Vegetables"

        manager.undo()

        assert layer.name == old_name
        assert _item_widget(panel, 0).name_label.text() == old_name

    def test_rename_to_same_name_pushes_nothing(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Confirming the editor without changing the name is a no-op."""
        view, panel, scene = wired
        widget = _item_widget(panel, 0)

        widget.name_edit.setText(scene.layers[0].name)
        widget._finish_editing()

        assert not view.command_manager.can_undo


class TestReorderLayersUndo:
    def test_reorder_undo_restores_order_and_z(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """A drag-reorder is one undoable step restoring order and z_orders."""
        view, panel, scene = wired
        manager = view.command_manager
        panel._on_add_layer()
        panel._on_add_layer()
        original = list(scene.layers)
        original_z = [lyr.z_order for lyr in scene.layers]
        manager.clear()  # isolate the reorder

        # Simulate a drag: panel rebuilds its order from the widget rows; here
        # we emit the reordered list directly (same signal path as the drag).
        new_order = [original[2], original[0], original[1]]
        panel.layers_reordered.emit(new_order)

        assert scene.layers == new_order
        assert manager.can_undo

        manager.undo()

        assert scene.layers == original
        assert [lyr.z_order for lyr in scene.layers] == original_z

    def test_identical_order_pushes_nothing(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Emitting the unchanged order is a no-op."""
        view, panel, scene = wired

        panel.layers_reordered.emit(list(scene.layers))

        assert not view.command_manager.can_undo


class TestLayerPropertyUndo:
    def test_visibility_click_undo(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene], qtbot
    ) -> None:
        """Clicking the eye button hides the layer + items; undo restores both."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]
        item = _draw_rect(view, 100, 100, 300, 200)
        widget = _item_widget(panel, 0)

        qtbot.mouseClick(widget.visibility_btn, Qt.MouseButton.LeftButton)

        assert layer.visible is False
        assert item.isVisible() is False
        assert manager.can_undo
        # Panel was rebuilt with the new state.
        assert _item_widget(panel, 0).visibility_btn.isChecked() is False

        manager.undo()

        assert layer.visible is True
        assert item.isVisible() is True
        assert _item_widget(panel, 0).visibility_btn.isChecked() is True

    def test_lock_click_undo(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene], qtbot
    ) -> None:
        """Clicking the lock button locks the layer; undo unlocks it."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]
        widget = _item_widget(panel, 0)

        qtbot.mouseClick(widget.lock_btn, Qt.MouseButton.LeftButton)

        assert layer.locked is True
        assert manager.can_undo

        manager.undo()

        assert layer.locked is False
        assert _item_widget(panel, 0).lock_btn.isChecked() is False


class TestOpacityCoalescing:
    def test_slider_drag_is_one_undo_step(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """A whole slider drag coalesces into exactly one undoable command."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]
        assert layer.opacity == 1.0

        panel.opacity_slider.setSliderDown(True)
        panel._on_opacity_drag_started()
        for value in (80, 60, 40):
            panel.opacity_slider.setValue(value)
        panel.opacity_slider.setSliderDown(False)
        panel._on_opacity_drag_finished()

        assert layer.opacity == pytest.approx(0.4)
        assert len(manager._undo_stack) == 1

        manager.undo()

        assert layer.opacity == pytest.approx(1.0)

    def test_keyboard_change_commits_immediately(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """A non-drag value change (keyboard/groove click) is one command."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]

        panel.opacity_slider.setValue(70)  # no sliderDown → immediate commit

        assert layer.opacity == pytest.approx(0.7)
        assert len(manager._undo_stack) == 1

        manager.undo()

        assert layer.opacity == pytest.approx(1.0)

    def test_drag_back_to_origin_pushes_nothing(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene]
    ) -> None:
        """Dragging away and back to the start value pushes no command."""
        view, panel, scene = wired
        manager = view.command_manager
        layer = scene.layers[0]

        panel.opacity_slider.setSliderDown(True)
        panel._on_opacity_drag_started()
        panel.opacity_slider.setValue(50)
        panel.opacity_slider.setValue(100)
        panel.opacity_slider.setSliderDown(False)
        panel._on_opacity_drag_finished()

        assert layer.opacity == pytest.approx(1.0)
        assert not manager.can_undo


class TestFullRoundTrip:
    def test_undo_all_redo_all(
        self, wired: tuple[CanvasView, LayersPanel, CanvasScene], qtbot
    ) -> None:
        """add → rename → hide → reorder → delete, then undo and redo it all."""
        view, panel, scene = wired
        manager = view.command_manager
        base = scene.layers[0]

        panel._on_add_layer()  # 1: add
        added = scene.layers[0]
        widget = _item_widget(panel, 0)
        widget.name_edit.setText("Plants")
        widget._finish_editing()  # 2: rename
        qtbot.mouseClick(_item_widget(panel, 1).visibility_btn, Qt.MouseButton.LeftButton)  # 3: hide base
        panel.layers_reordered.emit([base, added])  # 4: reorder
        panel._on_delete_layer(added.id)  # 5: delete

        assert len(manager._undo_stack) == 5
        assert scene.layers == [base]

        for _ in range(4):  # undo delete, reorder, hide, rename
            manager.undo()

        assert scene.layers == [added, base]
        assert added.name != "Plants"
        assert base.visible is True

        manager.undo()  # undo the add → back to the initial state

        assert scene.layers == [base]
        assert scene.active_layer is base
        assert not manager.can_undo

        for _ in range(5):
            manager.redo()

        assert scene.layers == [base]
        assert base.visible is False
        assert not manager.can_redo
