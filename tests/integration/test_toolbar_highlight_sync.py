"""Integration tests for toolbar highlight synchronization (issue #304).

Symptom: the main toolbar's SELECT button and a constraint toolbar button
(e.g. Equal Size) could both show as checked at once, even though only one
tool is ever active. Root cause: `MainToolbar` and `ConstraintToolbar` each
own their own exclusive `QButtonGroup`, and the old `_sync_toolbar_state`
mapped the tool's *translated display name* to a `ToolType` through a
hard-coded dict that only knew a handful of tools — every other tool change
(most constraint tools, all gallery draw tools) silently failed to sync
either toolbar, leaving a stale button checked.

The fix threads the raw `ToolType` through a new `tool_type_changed` signal
(`ToolManager` -> `CanvasView` -> `GardenPlannerApp._sync_toolbar_state_by_type`)
and has both toolbars unconditionally reconcile on every tool change: the
toolbar that owns the new tool checks its button, the other toolbar unchecks
whatever it had checked. These tests build the real `GardenPlannerApp` (per
the project's mandatory integration-test policy, §8.10) and drive it exactly
as a user would via `canvas_view.set_active_tool`.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.tools import ToolType


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred (singleShot) modal Welcome dialog.

    Depends on the conftest reset so this write survives the per-test store
    clear. Without it, a pumped event loop can block the run on a modal dialog.
    """
    get_settings().show_welcome_on_startup = False


@pytest.fixture()
def window(qtbot: Any) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _all_checked_buttons(window: GardenPlannerApp) -> list[Any]:
    """Every currently-checked button across both exclusive-group toolbars."""
    checked = []
    main_checked = window.main_toolbar._button_group.checkedButton()
    if main_checked is not None:
        checked.append(main_checked)
    constraint_checked = window.constraint_toolbar._button_group.checkedButton()
    if constraint_checked is not None:
        checked.append(constraint_checked)
    return checked


class TestToolbarHighlightSync:
    """Exactly one button, on exactly one toolbar, is checked at a time."""

    @pytest.fixture()
    def constraint_tool_types(self, window: GardenPlannerApp) -> list[ToolType]:
        return list(window.constraint_toolbar._buttons.keys())

    def test_every_tool_type_leaves_exactly_one_button_checked(
        self, window: GardenPlannerApp, constraint_tool_types: list[ToolType]
    ) -> None:
        tool_types = [
            *constraint_tool_types,
            ToolType.MEASURE,
            ToolType.TEXT,
            ToolType.SELECT,
        ]
        for tool_type in tool_types:
            window.canvas_view.set_active_tool(tool_type)

            checked = _all_checked_buttons(window)
            assert len(checked) == 1, (
                f"expected exactly one checked button after activating "
                f"{tool_type}, found {len(checked)}"
            )

            expected_button = window.main_toolbar._buttons.get(
                tool_type
            ) or window.constraint_toolbar._buttons.get(tool_type)
            assert expected_button is not None, (
                f"no button registered anywhere for {tool_type} — fixture bug"
            )
            assert checked[0] is expected_button, (
                f"wrong button checked for {tool_type}: {checked[0]!r} is not "
                f"the button for this tool"
            )

    def test_304_constraint_equal_does_not_leave_select_checked(
        self, window: GardenPlannerApp
    ) -> None:
        """Reproduces the exact #304 screenshot: SELECT + Equal Size both lit."""
        window.canvas_view.set_active_tool(ToolType.CONSTRAINT_EQUAL)

        assert not window.main_toolbar._buttons[ToolType.SELECT].isChecked()
        assert window.constraint_toolbar._buttons[ToolType.CONSTRAINT_EQUAL].isChecked()

    def test_304_switching_back_to_select_unchecks_the_constraint_button(
        self, window: GardenPlannerApp
    ) -> None:
        window.canvas_view.set_active_tool(ToolType.CONSTRAINT_EQUAL)
        window.canvas_view.set_active_tool(ToolType.SELECT)

        assert window.main_toolbar._buttons[ToolType.SELECT].isChecked()
        assert not window.constraint_toolbar._buttons[ToolType.CONSTRAINT_EQUAL].isChecked()

    def test_gallery_draw_tool_leaves_no_button_checked_on_either_toolbar(
        self, window: GardenPlannerApp
    ) -> None:
        """A drawing tool reached via the category gallery (e.g. RECTANGLE)
        has no button on either exclusive-group toolbar, so activating it
        must leave both toolbars fully unchecked rather than stranding
        SELECT (or a stale constraint button) highlighted."""
        assert ToolType.RECTANGLE not in window.main_toolbar._buttons
        assert ToolType.RECTANGLE not in window.constraint_toolbar._buttons

        window.canvas_view.set_active_tool(ToolType.RECTANGLE)

        assert _all_checked_buttons(window) == []
