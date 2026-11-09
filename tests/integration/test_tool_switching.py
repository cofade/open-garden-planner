"""Integration tests: tool activation and switching.

Verifies that:
  - The default active tool is SELECT.
  - Switching tools works correctly.
  - Switching while a draw is in progress cleanly cancels the draw.
  - Completing a draw auto-switches back to SELECT (add_item behaviour).
  - Escape key cancels an active drawing gesture.
  - Escape always returns to SELECT, from the canvas and from any other widget
    of the main window (manual test of PR #783).
"""


from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _escape_key_event() -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = Qt.Key.Key_Escape
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _rect_count(view: CanvasView) -> int:
    return sum(1 for i in view.scene().items() if isinstance(i, RectangleItem))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolSwitching:
    """Tool activation and switching integration tests."""

    def test_default_tool_is_select(self, canvas: CanvasView, qtbot: object) -> None:
        """After CanvasView initialisation the SELECT tool is active."""
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_switch_to_rectangle(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(RECTANGLE) makes RECTANGLE the active tool."""
        canvas.set_active_tool(ToolType.RECTANGLE)
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE

    def test_switch_to_circle(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(CIRCLE) makes CIRCLE the active tool."""
        canvas.set_active_tool(ToolType.CIRCLE)
        assert canvas.tool_manager.active_tool_type == ToolType.CIRCLE

    def test_switch_to_polygon(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(POLYGON) makes POLYGON the active tool."""
        canvas.set_active_tool(ToolType.POLYGON)
        assert canvas.tool_manager.active_tool_type == ToolType.POLYGON

    def test_switch_from_select_to_rectangle_and_back(self, canvas: CanvasView, qtbot: object) -> None:
        """Switching between tools updates active_tool_type each time."""
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        canvas.set_active_tool(ToolType.RECTANGLE)
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE
        canvas.set_active_tool(ToolType.SELECT)
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_tool_changed_signal_emitted(self, canvas: CanvasView, qtbot: object) -> None:
        """tool_manager.tool_changed is emitted when switching tools."""
        with qtbot.waitSignal(canvas.tool_manager.tool_changed, timeout=500):
            canvas.set_active_tool(ToolType.RECTANGLE)

    def test_switch_while_drawing_cancels_draw(self, canvas: CanvasView, qtbot: object) -> None:
        """Switching away from a tool mid-draw cancels the ongoing gesture.

        BaseTool.deactivate() calls self.cancel() — so no partial item should remain
        and the old tool's drawing state should be reset.
        """
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        # Start a draw gesture but don't release
        tool.mouse_press(event, QPointF(100, 100))
        assert tool._is_drawing is True

        # Switch tool — deactivate() calls cancel()
        canvas.set_active_tool(ToolType.SELECT)

        # Previous tool state should be reset
        assert tool._is_drawing is False
        assert tool._preview_item is None
        # No item should have been created
        assert _rect_count(canvas) == 0

    def test_draw_tool_stays_active_after_completing_draw(self, canvas: CanvasView, qtbot: object) -> None:
        """After completing a draw gesture the tool remains active (not auto-switched).

        CanvasView.add_item() does NOT switch to SELECT for tool-based draws.
        (SELECT auto-switch only happens for gallery drag-drop, not tool gestures.)
        The user must press Escape or select SELECT explicitly.
        """
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(400, 300))
        tool.mouse_release(event, QPointF(400, 300))

        # Tool stays as RECTANGLE — draw again immediately is possible
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE

    def test_escape_cancels_active_draw_gesture(self, canvas: CanvasView, qtbot: object) -> None:
        """Escape key during a draw cancels the gesture (no item created)."""
        click = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(click, QPointF(100, 100))
        assert tool._is_drawing is True

        # Simulate Escape via the tool's key_press handler
        esc = _escape_key_event()
        tool.key_press(esc)

        assert tool._is_drawing is False
        assert _rect_count(canvas) == 0


class TestEscapeReturnsToSelect:
    """Esc ends every tool; V was the only key that did (manual test, PR #783)."""

    def test_escape_on_the_canvas_returns_every_tool_to_select(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from PyQt6.QtTest import QTest

        stuck = []
        for tool_type in list(canvas.tool_manager._tools):
            canvas.set_active_tool(tool_type)
            assert canvas.tool_manager.active_tool_type == tool_type
            QTest.keyClick(canvas, Qt.Key.Key_Escape)
            if canvas.tool_manager.active_tool_type != ToolType.SELECT:
                stuck.append(tool_type.name)
        assert stuck == []

    def test_escape_mid_gesture_cancels_the_draw_and_returns_to_select(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from PyQt6.QtTest import QTest

        from open_garden_planner.ui.canvas.items import PolygonItem

        canvas.set_active_tool(ToolType.POLYGON)
        tool = canvas.tool_manager.active_tool
        items_before = len(canvas.scene().items())
        for point in (QPointF(100, 100), QPointF(300, 100), QPointF(300, 300)):
            tool.mouse_press(_left_click_event(), point)
        assert len(canvas.scene().items()) > items_before, "no preview was drawn"

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        assert len(canvas.scene().items()) == items_before, "a preview survived Esc"
        assert not any(isinstance(i, PolygonItem) for i in canvas.scene().items())

    def test_escape_takes_the_distance_angle_prompt_away(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The prompt follows the mouse; Esc with the mouse at rest must hide it."""
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest

        canvas.resize(800, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        canvas.set_dynamic_input_enabled(True)
        canvas.set_active_tool(ToolType.POLYGON)
        viewport = canvas.viewport()
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
        QTest.mouseMove(viewport, QPoint(380, 340))
        QTest.qWait(20)
        overlay = canvas._dynamic_overlay
        assert overlay is not None and overlay.isVisible(), "no prompt to hide"

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        assert not overlay.isVisible()

    def test_one_escape_finishes_a_text_annotation_and_returns_to_select(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The focused inline editor gets Esc first, then the tool ends.

        The view sees keys before the scene: without the forwarding the tool
        switch swallowed the key and the edit needed a second Esc.
        """
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest

        from open_garden_planner.ui.canvas.items.text_item import TextItem

        canvas.resize(800, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        canvas.set_active_tool(ToolType.TEXT)
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
        item = next(i for i in canvas.scene().items() if isinstance(i, TextItem))
        assert item._editing and canvas.scene().focusItem() is item
        item.setPlainText("abc")

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        assert item._editing is False, "the edit needed a second Esc"
        assert item.scene() is canvas.scene()
        assert item.content == "abc"

    def test_escape_on_an_empty_text_annotation_removes_it(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest

        from open_garden_planner.ui.canvas.items.text_item import TextItem

        canvas.resize(800, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        canvas.set_active_tool(ToolType.TEXT)
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
        assert any(isinstance(i, TextItem) for i in canvas.scene().items())

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        assert not any(isinstance(i, TextItem) for i in canvas.scene().items())

    def test_a_label_editor_under_a_drawing_tool_closes_on_the_first_escape(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from PyQt6.QtTest import QTest

        canvas.resize(800, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        bed = RectangleItem(100, 100, 300, 200)
        bed.name = "Bed"
        canvas.scene().addItem(bed)
        canvas.set_active_tool(ToolType.RECTANGLE)
        bed.start_label_edit()
        editor = bed._edit_label_item
        assert editor is not None and editor.isVisible()
        # The editor takes the focus on the next event-loop turn.
        qtbot.waitUntil(  # type: ignore[attr-defined]
            lambda: canvas.scene().focusItem() is editor, timeout=2000
        )

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert not editor.isVisible(), "the label editor needed a second Esc"
        assert bed.name == "Bed"
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_one_escape_finishes_a_callout_and_returns_to_select(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The Callout tool stays active while its text is edited."""
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest

        from open_garden_planner.ui.canvas.items.callout_item import CalloutItem

        canvas.resize(800, 600)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        canvas.set_active_tool(ToolType.CALLOUT)
        viewport = canvas.viewport()
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(420, 240))
        callout = next(i for i in canvas.scene().items() if isinstance(i, CalloutItem))
        editor = canvas.scene().focusItem()
        assert editor is not None and hasattr(editor, "toPlainText")
        assert canvas.tool_manager.active_tool_type == ToolType.CALLOUT
        editor.setPlainText("note")

        QTest.keyClick(canvas, Qt.Key.Key_Escape)

        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        assert canvas.scene().focusItem() is not editor, "the edit needed a second Esc"
        assert callout.scene() is canvas.scene()
        assert callout.to_dict()["content"] == "note"

    def test_the_shortcuts_dialog_lists_escape(self, qtbot: object) -> None:
        from PyQt6.QtWidgets import QLabel

        from open_garden_planner.ui.dialogs.shortcuts_dialog import ShortcutsDialog

        dialog = ShortcutsDialog()
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]
        labels = {label.text() for label in dialog.findChildren(QLabel)}
        assert "Cancel and return to the Select tool" in labels

    def test_escape_with_select_active_changes_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        assert canvas.return_to_select_tool() is False
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_escape_anywhere_in_the_running_window_returns_to_select(
        self, qtbot: object, monkeypatch: object
    ) -> None:
        """Right after a tool was picked, the focus is rarely on the canvas."""
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QMessageBox

        from open_garden_planner.app.application import GardenPlannerApp

        monkeypatch.setattr(  # type: ignore[attr-defined]
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
        )
        window = GardenPlannerApp()
        qtbot.addWidget(window)  # type: ignore[attr-defined]
        window.show()
        QTest.qWaitForWindowExposed(window)
        view = window.canvas_view
        focus_holders = {
            "the canvas": view,
            "the properties panel": window.properties_panel,
            "the object search field": window.category_toolbar._search_field,
            "the window's own focus widget": window.focusWidget() or window,
            "the main window": window,
        }
        stuck = []
        for tool_type in (
            ToolType.RAISED_BED,
            ToolType.HOUSE,
            ToolType.TREE,
            ToolType.POLYGON,
            ToolType.MEASURE,
            ToolType.CONSTRAINT,
            ToolType.SPLIT,
            ToolType.TEXT,
        ):
            for name, widget in focus_holders.items():
                window._on_tool_selected(tool_type)
                assert view.tool_manager.active_tool_type == tool_type
                QTest.keyClick(widget, Qt.Key.Key_Escape)
                if view.tool_manager.active_tool_type != ToolType.SELECT:
                    stuck.append(f"{tool_type.name} with Esc in {name}")
        assert stuck == []
        assert window.main_toolbar._buttons[ToolType.SELECT].isChecked()

        # The Select button itself always worked; keep it that way.
        window._on_tool_selected(ToolType.RAISED_BED)
        QTest.mouseClick(
            window.main_toolbar._buttons[ToolType.SELECT], Qt.MouseButton.LeftButton
        )
        assert view.tool_manager.active_tool_type == ToolType.SELECT
