"""Issue #210 — free-text property fields commit ONE undo step per edit.

The Name (QLineEdit) and Text Content (QTextEdit) fields used to register a
ChangePropertyCommand on every keystroke, so typing an N-char value pushed N
undo entries and (since #209) fired N heavyweight calendar refreshes. They now
live-update the item on textChanged but commit a single command on
editingFinished / focus-out.

These tests also close the senior-review P2 coverage gap from PR #211: the
properties_panel `register_applied` path had no direct integration coverage.
"""

from PyQt6.QtWidgets import QLineEdit

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.ui.canvas.items import RectangleItem, TextItem
from open_garden_planner.ui.panels import PropertiesPanel
from open_garden_planner.ui.panels.properties_panel import FocusOutTextEdit


def _name_edit(panel: PropertiesPanel) -> QLineEdit:
    """The Name field is the only QLineEdit tagged with _ogp_name_start."""
    edits = [w for w in panel.findChildren(QLineEdit) if hasattr(w, "_ogp_name_start")]
    assert len(edits) == 1, "expected exactly one tagged Name field"
    return edits[0]


def _content_edit(panel: PropertiesPanel) -> FocusOutTextEdit:
    edits = panel.findChildren(FocusOutTextEdit)
    assert len(edits) == 1, "expected exactly one Text Content field"
    return edits[0]


class TestNameFieldUndoGranularity:
    """Name edits: live label update while typing, one undo step on commit."""

    def test_typing_then_commit_is_one_undo_step(self, qtbot) -> None:  # noqa: ARG002
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])
        name_edit = _name_edit(panel)

        # Count command_executed emissions == one calendar refresh each (#210).
        refreshes = []
        manager.command_executed.connect(lambda _desc: refreshes.append(_desc))

        # Type character by character — each keystroke live-updates the item but
        # registers NO command.
        for partial in ("T", "To", "Tom", "Toma", "Tomat", "Tomato"):
            name_edit.setText(partial)
            assert item.name == partial, "label must update live while typing"
        assert not manager.can_undo, "no command may be pushed before commit"
        assert refreshes == [], "no refresh may fire per keystroke"

        # Focus-out / Enter commits exactly one command.
        name_edit.editingFinished.emit()
        assert manager.can_undo
        assert len(refreshes) == 1, "exactly one refresh per completed edit"

        # A single undo restores the original name in one step.
        manager.undo()
        assert item.name == ""
        assert not manager.can_undo

    def test_commit_without_change_is_noop(self, qtbot) -> None:  # noqa: ARG002
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = RectangleItem(0, 0, 100, 50)
        item.name = "Bed A"
        panel.set_selected_items([item])
        name_edit = _name_edit(panel)

        # Focus the field and leave without changing the text.
        name_edit.editingFinished.emit()
        assert not manager.can_undo, "unchanged focus-out must not push a command"

    def test_double_commit_pushes_single_command(self, qtbot) -> None:  # noqa: ARG002
        """Enter fires returnPressed AND editingFinished — must not double-push."""
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])
        name_edit = _name_edit(panel)

        name_edit.setText("Roses")
        name_edit.editingFinished.emit()
        name_edit.editingFinished.emit()  # second fire (focus-out after Enter)

        manager.undo()
        assert item.name == ""
        assert not manager.can_undo, "only one command may have been recorded"


class TestTextContentUndoGranularity:
    """Text Content edits commit one undo step on focus-out."""

    def test_typing_then_focus_out_is_one_undo_step(self, qtbot) -> None:  # noqa: ARG002
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = TextItem(0, 0, "")
        panel.set_selected_items([item])
        content_edit = _content_edit(panel)

        for partial in ("N", "No", "Note"):
            content_edit.setPlainText(partial)
            assert item.content == partial, "content must update live while typing"
        assert not manager.can_undo, "no command before focus-out"

        # Emit the focus-out signal the FocusOutTextEdit subclass adds.
        content_edit.editing_finished.emit()
        assert manager.can_undo

        manager.undo()
        assert item.content == ""
        assert not manager.can_undo

    def test_focus_out_without_change_is_noop(self, qtbot) -> None:  # noqa: ARG002
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = TextItem(0, 0, "hello")
        panel.set_selected_items([item])
        content_edit = _content_edit(panel)

        content_edit.editing_finished.emit()
        assert not manager.can_undo
