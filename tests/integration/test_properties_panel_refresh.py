"""Issue #206 — Properties panel refreshes in place instead of rebuilding.

`set_selected_items` used to tear down and rebuild the entire form on every
`command_executed` / `can_undo_changed` / `can_redo_changed` signal. It now:

  * caches a structural selection signature and, when the selection is
    unchanged, pushes fresh values into the existing widgets (no teardown);
  * is driven by a single `stack_changed` wiring (which — unlike
    `command_executed` — also fires on undo/redo).

These tests cover the value-refresh on undo/redo and the application-level
signal wiring (multiplicity + undo/redo coverage), which is the core
regression risk of dropping the `can_undo/redo_changed` wirings.
"""

# ruff: noqa: ARG002

from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QLabel

from open_garden_planner.core.commands import CommandManager, MoveItemsCommand
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel


def _field(panel: PropertiesPanel, label_text: str):
    form = panel._form_layout
    for i in range(form.rowCount()):
        label_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if label_item is None or field_item is None:
            continue
        lw = label_item.widget()
        if isinstance(lw, QLabel) and label_text in lw.text():
            return field_item.widget()
    return None


class TestUndoRedoValueRefresh:
    """Undo/redo of a property on a still-selected item refreshes the panel."""

    def test_undo_resize_refreshes_size_in_place(self, qtbot, monkeypatch) -> None:
        monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
        manager = CommandManager()
        item = RectangleItem(0, 0, 100, 50)
        panel = PropertiesPanel(command_manager=manager)
        panel.set_selected_items([item])

        size_widget = _field(panel, "Size")
        w_spin, h_spin = size_widget.findChildren(QDoubleSpinBox)

        # Resize via the panel spin box -> registers a command.
        w_spin.setValue(400.0)
        assert manager.can_undo
        # Mimic the app's stack_changed -> _update_properties_panel.
        panel.set_selected_items([item])
        assert w_spin.value() == 400.0

        # Undo: the same selection is re-set; the spin box must revert in place.
        manager.undo()
        panel.set_selected_items([item])
        again = _field(panel, "Size")
        assert again is size_widget, "undo refresh tore the form down"
        w_spin2, _ = again.findChildren(QDoubleSpinBox)
        assert w_spin2.value() == 100.0, "spin box must show the reverted width"


def _silence_close_prompt(monkeypatch) -> None:
    """Executing a command marks the project dirty; the close prompt would then
    block headless teardown. Auto-discard so qtbot can tear the window down."""
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Discard,
    )


class TestApplicationSignalWiring:
    """End-to-end: stack_changed drives the panel exactly once, incl. undo/redo."""

    def test_execute_and_undo_each_trigger_one_panel_update(
        self, qtbot, monkeypatch
    ) -> None:
        from PyQt6.QtCore import QPointF

        from open_garden_planner.app.application import GardenPlannerApp

        _silence_close_prompt(monkeypatch)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        monkeypatch.setattr(QApplication, "focusWidget", lambda: None)

        item = RectangleItem(0, 0, 100, 50)
        win.canvas_scene.addItem(item)
        item.setSelected(True)

        calls: list[int] = []
        orig = win.properties_panel.set_selected_items

        def _spy(items):
            calls.append(len(items))
            return orig(items)

        monkeypatch.setattr(win.properties_panel, "set_selected_items", _spy)

        mgr = win.canvas_view.command_manager

        calls.clear()
        mgr.execute(MoveItemsCommand([item], QPointF(10, 0)))
        qtbot.waitUntil(lambda: len(calls) >= 1)
        assert len(calls) == 1, "execute should refresh the panel exactly once"

        calls.clear()
        mgr.undo()
        qtbot.waitUntil(lambda: len(calls) >= 1)
        assert len(calls) == 1, "undo must refresh the panel (command_executed misses it)"

        calls.clear()
        mgr.redo()
        qtbot.waitUntil(lambda: len(calls) >= 1)
        assert len(calls) == 1, "redo must refresh the panel"

    def test_undo_action_enablement_still_tracks_manager(self, qtbot, monkeypatch) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        _silence_close_prompt(monkeypatch)
        win = GardenPlannerApp()
        qtbot.addWidget(win)

        item = RectangleItem(0, 0, 100, 50)
        win.canvas_scene.addItem(item)
        mgr = win.canvas_view.command_manager

        from PyQt6.QtCore import QPointF

        mgr.execute(MoveItemsCommand([item], QPointF(10, 0)))
        assert win._undo_action.isEnabled(), "can_undo_changed still drives the toolbar"
        mgr.undo()
        assert not win._undo_action.isEnabled()
        assert win._redo_action.isEnabled()
