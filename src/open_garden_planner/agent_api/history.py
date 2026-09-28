"""Qt-free mapping from the GUI's command manager to the Agent API history state.

US-D2.7 (#362): exposes the global undo/redo stack so an agent can assert
the D2 undo contract — "one call = one undo step" and "refusals leave the
stack untouched" — without reading the GUI's Edit menu.

This module is deliberately Qt-free: it reads from any object that exposes
the same properties as :class:`~open_garden_planner.core.commands.CommandManager`
(``can_undo``, ``can_redo``, ``undo_description``, ``redo_description``).
The actual manager is injected by the provider callable in ``application.py``,
so this module is unit-testable without a GUI.
"""

from __future__ import annotations

from typing import Protocol

from open_garden_planner.agent_api.schema import HistoryState


class _CommandManagerLike(Protocol):
    """The subset of CommandManager that get_history reads."""

    @property
    def undo_depth(self) -> int: ...
    @property
    def redo_depth(self) -> int: ...
    @property
    def undo_description(self) -> str | None: ...
    @property
    def redo_description(self) -> str | None: ...


def history_from_command_manager(manager: _CommandManagerLike) -> HistoryState:
    """Read the undo/redo stack state without mutating it.

    Args:
        manager: The GUI's global command manager (or any object with the
            same four properties).

    Returns:
        A HistoryState with the current depths and next undo/redo texts.
    """
    return HistoryState(
        undo_depth=manager.undo_depth,
        redo_depth=manager.redo_depth,
        next_undo_text=manager.undo_description,
        next_redo_text=manager.redo_description,
    )
