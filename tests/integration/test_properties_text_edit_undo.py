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

from open_garden_planner.core.commands import ChangePropertyCommand, CommandManager
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

        # The post-commit panel rebuild (command_executed -> set_selected_items
        # in the real app) must not lose the committed value or crash.
        panel.set_selected_items([item])
        assert item.name == "Tomato"

        # A single undo restores the original name in one step; redo re-applies
        # the whole value (not one character).
        manager.undo()
        assert item.name == ""
        assert not manager.can_undo
        manager.redo()
        assert item.name == "Tomato"

    def test_debounce_commits_without_focus_out(self, qtbot) -> None:
        """Bug-1 fix: a typing pause commits one command WITHOUT a focus-out, so
        the Undo action is enabled and Ctrl+Z works while the field still has
        focus. Previously the command only landed on focus-out -> nothing to undo
        mid-edit -> 'name stays'."""
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])
        name_edit = _name_edit(panel)

        name_edit.setText("Tomato")
        assert not manager.can_undo, "command must not commit on the keystroke itself"
        # No editingFinished — just wait for the debounce timer to fire.
        qtbot.waitUntil(lambda: manager.can_undo, timeout=2000)
        manager.undo()
        assert item.name == ""

    def test_pending_edit_flushed_when_selection_changes(self, qtbot) -> None:  # noqa: ARG002
        """P1 (round-2 review): a pending debounced edit must not be lost when
        the panel rebuilds for a different item. Selecting another item while a
        debounce is still armed must flush the edit to a real undo command, not
        silently apply it to the model with an empty undo stack."""
        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item_a = RectangleItem(0, 0, 100, 50)
        item_b = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item_a])
        name_edit = _name_edit(panel)

        # Type into A but do NOT fire editingFinished and do NOT wait for the
        # debounce — simulate a selection change landing first.
        name_edit.setText("Apple")
        assert not manager.can_undo
        assert item_a.name == "Apple", "live edit applied to the model"

        # Selection changes to B -> rebuild. The pending edit on A must commit.
        panel.set_selected_items([item_b])
        # Pin the mechanism: A's field was actually destroyed by the rebuild
        # (so its debounce timer can never fire) — the flush is what saved it.
        from PyQt6 import sip
        assert sip.isdeleted(name_edit), "A's field must be destroyed by the rebuild"
        assert manager.can_undo, "A's pending edit must be flushed to a command"
        manager.undo()
        assert item_a.name == "", "the flushed command undoes A's edit in one step"

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
        """editingFinished can fire twice (Enter, then focus-out) — the
        start-value reset must keep that to a single recorded command."""
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

    def test_real_focus_out_event_commits(self, qtbot) -> None:  # noqa: ARG002
        """A genuine QFocusEvent through FocusOutTextEdit.focusOutEvent commits
        one command — exercises the new subclass code, not just the signal."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QFocusEvent
        from PyQt6.QtWidgets import QApplication

        manager = CommandManager()
        panel = PropertiesPanel()
        panel.set_command_manager(manager)
        item = TextItem(0, 0, "")
        panel.set_selected_items([item])
        content_edit = _content_edit(panel)

        content_edit.setPlainText("Note")
        assert not manager.can_undo
        QApplication.sendEvent(content_edit, QFocusEvent(QEvent.Type.FocusOut))
        assert manager.can_undo
        manager.undo()
        assert item.content == ""


class TestCommandDescriptionLocalized:
    """The {property} fragment localizes end-to-end via the compiled .qm (#210)."""

    def test_german_description_is_fully_localized(self, qtbot) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

        from open_garden_planner.core.i18n import load_translator

        app = QApplication.instance()
        item = QGraphicsRectItem(0, 0, 10, 10)
        cmd = ChangePropertyCommand(item, "text content", "a", "b", lambda *_: None)

        load_translator(app, "de")
        try:
            # Guards code<->registration drift: a typo'd fragment would silently
            # fall back to English here and the i18n gate would not catch it.
            assert cmd.description == "Textinhalt ändern"
        finally:
            load_translator(app, "en")  # restore source language for other tests
