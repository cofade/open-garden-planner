"""Unit tests for the CoordinateInputBuffer."""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from open_garden_planner.core.coordinate_input.buffer import CoordinateInputBuffer


def test_text_change_emits_signal(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    seen: list[str] = []
    buf.text_changed.connect(seen.append)

    buf.set_text("@1,2")
    assert seen == ["@1,2"]
    # Identical value must not re-emit
    buf.set_text("@1,2")
    assert seen == ["@1,2"]


def test_anchor_change_emits_signal(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    seen: list[object] = []
    buf.anchor_changed.connect(seen.append)

    buf.set_anchor(QPointF(10, 20))
    assert len(seen) == 1
    assert isinstance(seen[0], QPointF)
    # Same anchor must not re-emit
    buf.set_anchor(QPointF(10, 20))
    assert len(seen) == 1
    buf.set_anchor(None)
    assert seen[-1] is None


def test_commit_emits_point_on_success(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    buf.set_anchor(QPointF(0, 0))
    buf.set_text("@500,0")

    committed: list[QPointF] = []
    errors: list[str] = []
    buf.committed.connect(committed.append)
    buf.parse_error.connect(errors.append)

    result = buf.commit()
    assert result is not None
    assert result.kind == "relative"
    assert committed[-1].x() == 500
    assert committed[-1].y() == 0
    assert errors == []


def test_commit_emits_error_on_invalid(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    buf.set_text("xyz")
    errors: list[str] = []
    committed: list[QPointF] = []
    buf.parse_error.connect(errors.append)
    buf.committed.connect(committed.append)

    assert buf.commit() is None
    assert errors and "Expected" in errors[0] or errors and "number" in errors[0].lower()
    assert committed == []


def test_commit_empty_returns_none(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    assert buf.commit() is None


def test_clear(qtbot) -> None:  # noqa: ARG001
    buf = CoordinateInputBuffer()
    buf.set_text("@1,2")
    seen: list[str] = []
    buf.text_changed.connect(seen.append)
    buf.clear()
    assert seen == [""]
    assert buf.text == ""
