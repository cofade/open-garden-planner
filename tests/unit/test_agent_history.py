"""Unit tests for the Agent API history module (US-D2.7, issue #362)."""

from __future__ import annotations

from open_garden_planner.agent_api.history import history_from_command_manager
from open_garden_planner.agent_api.schema import HistoryState


class _FakeManager:
    """Minimal stand-in for CommandManager with the four properties we read."""

    def __init__(
        self,
        undo_depth: int = 0,
        redo_depth: int = 0,
        undo_description: str | None = None,
        redo_description: str | None = None,
    ) -> None:
        self._undo_depth = undo_depth
        self._redo_depth = redo_depth
        self._undo_description = undo_description
        self._redo_description = redo_description

    @property
    def undo_depth(self) -> int:
        return self._undo_depth

    @property
    def redo_depth(self) -> int:
        return self._redo_depth

    @property
    def undo_description(self) -> str | None:
        return self._undo_description

    @property
    def redo_description(self) -> str | None:
        return self._redo_description


class TestHistoryFromCommandManager:
    """Tests for history_from_command_manager."""

    def test_empty_stack(self) -> None:
        manager = _FakeManager()
        result = history_from_command_manager(manager)
        assert result.undo_depth == 0
        assert result.redo_depth == 0
        assert result.next_undo_text is None
        assert result.next_redo_text is None

    def test_with_undo_only(self) -> None:
        manager = _FakeManager(
            undo_depth=3,
            undo_description="Move object",
        )
        result = history_from_command_manager(manager)
        assert result.undo_depth == 3
        assert result.redo_depth == 0
        assert result.next_undo_text == "Move object"
        assert result.next_redo_text is None

    def test_with_redo_only(self) -> None:
        manager = _FakeManager(
            redo_depth=2,
            redo_description="Delete object",
        )
        result = history_from_command_manager(manager)
        assert result.undo_depth == 0
        assert result.redo_depth == 2
        assert result.next_undo_text is None
        assert result.next_redo_text == "Delete object"

    def test_with_both_stacks(self) -> None:
        manager = _FakeManager(
            undo_depth=5,
            redo_depth=1,
            undo_description="Resize bed",
            redo_description="Create plant",
        )
        result = history_from_command_manager(manager)
        assert result.undo_depth == 5
        assert result.redo_depth == 1
        assert result.next_undo_text == "Resize bed"
        assert result.next_redo_text == "Create plant"

    def test_returns_history_state_model(self) -> None:
        manager = _FakeManager(undo_depth=1, undo_description="Test")
        result = history_from_command_manager(manager)
        assert isinstance(result, HistoryState)

    def test_does_not_mutate_manager(self) -> None:
        """get_history must not change the stack (read-only contract)."""
        manager = _FakeManager(
            undo_depth=2,
            redo_depth=1,
            undo_description="Move",
            redo_description="Delete",
        )
        history_from_command_manager(manager)
        # Verify the manager is unchanged
        assert manager.undo_depth == 2
        assert manager.redo_depth == 1
        assert manager.undo_description == "Move"
        assert manager.redo_description == "Delete"
