"""Integration tests: Edit ▸ Arrange menu actions, shortcuts, shortcuts
dialog rows (issue #338, plan implementation step 6).

`tests/integration/test_arrange_z_order.py` already exercises the Qt-aware
`CanvasView.arrange_selected` seam directly on a bare `CanvasView`. This file
is the layer above it: the main window's four `QAction`s (menu wiring, both
shortcut sequences per action) on a REAL `GardenPlannerApp`, plus the
`ShortcutsDialog` rows that document them.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QLabel, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.dialogs.shortcuts_dialog import ShortcutsDialog


def _discard_on_close(monkeypatch: Any) -> None:
    """Mutating a plan dirties it; qtbot's teardown close would then block on
    the unsaved-changes modal. Auto-answer Discard (mirrors
    test_agent_api_default_on.py's `_discard_on_close`)."""
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Discard,
    )


def _rect(x: float, y: float, layer_id: Any, name: str) -> RectangleItem:
    return RectangleItem(
        x, y, 100.0, 100.0,
        object_type=ObjectType.GENERIC_RECTANGLE,
        name=name,
        layer_id=layer_id,
    )


class TestArrangeMenuActionsTriggerRealApp:
    def test_bring_to_front_then_send_to_back_via_actions(
        self, qtbot: Any, monkeypatch: Any
    ) -> None:
        _discard_on_close(monkeypatch)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        try:
            scene = win.canvas_scene
            layer_id = scene.active_layer.id
            lower = _rect(0, 0, layer_id, "lower")
            upper = _rect(20, 20, layer_id, "upper")
            scene.addItem(lower)
            scene.addItem(upper)
            assert lower.zValue() < upper.zValue()

            lower.setSelected(True)
            win._arrange_front_action.trigger()

            assert lower.zValue() > upper.zValue()
            assert win.canvas_view.command_manager.can_undo

            win._arrange_back_action.trigger()

            assert lower.zValue() < upper.zValue()
        finally:
            win.close()

    def test_trigger_with_nothing_selected_pushes_no_undo_step(
        self, qtbot: Any, monkeypatch: Any
    ) -> None:
        _discard_on_close(monkeypatch)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        try:
            scene = win.canvas_scene
            layer_id = scene.active_layer.id
            scene.addItem(_rect(0, 0, layer_id, "solo"))
            assert not win.canvas_view.command_manager.can_undo

            win._arrange_front_action.trigger()

            assert not win.canvas_view.command_manager.can_undo
        finally:
            win.close()

    @pytest.mark.parametrize(
        ("action_name", "primary", "secondary"),
        [
            ("_arrange_front_action", "Ctrl+Shift+]", "Ctrl+Shift+Up"),
            ("_arrange_forward_action", "Ctrl+]", "Ctrl+Up"),
            ("_arrange_backward_action", "Ctrl+[", "Ctrl+Down"),
            ("_arrange_back_action", "Ctrl+Shift+[", "Ctrl+Shift+Down"),
        ],
    )
    def test_action_has_both_shortcut_sequences(
        self, qtbot: Any, monkeypatch: Any, action_name: str, primary: str, secondary: str
    ) -> None:
        _discard_on_close(monkeypatch)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        try:
            action = getattr(win, action_name)
            assert action.shortcuts() == [QKeySequence(primary), QKeySequence(secondary)]
        finally:
            win.close()


class TestShortcutsDialogArrangeRows:
    def test_arrange_labels_present(self, qtbot: Any) -> None:
        dialog = ShortcutsDialog()
        qtbot.addWidget(dialog)

        labels = {label.text() for label in dialog.findChildren(QLabel)}
        for expected in (
            "Bring to Front",
            "Bring Forward",
            "Send Backward",
            "Send to Back",
        ):
            assert expected in labels, (expected, labels)
