"""Unit tests for GlobalSearchField lifecycle and signals (#482)."""

import ast
from pathlib import Path

from PyQt6.QtWidgets import QWidget

from open_garden_planner.ui.widgets.gallery_data import GalleryCategory
from open_garden_planner.ui.widgets.global_search import GlobalSearchField

_SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"


def _destroyed_connects(source: str) -> list[int]:
    """Lines of ``<…>.destroyed.connect(…)`` — a Python callable on an object's
    ``destroyed`` signal."""
    return [
        node.lineno for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect" and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "destroyed"
    ]


def test_global_search_field_has_no_destroyed_signal_closure(qtbot) -> None:
    """Issue #482: GlobalSearchField has no closure connected to destroyed, and teardown is clean."""
    search_file = _SRC / "ui" / "widgets" / "global_search.py"
    assert _destroyed_connects(search_file.read_text(encoding="utf-8")) == []

    # Also verify widget instantiation and deletion without error
    categories: list[GalleryCategory] = []
    field = GlobalSearchField(categories)
    qtbot.addWidget(field)

    dummy = QWidget()
    qtbot.addWidget(dummy)

    # Focus change callback runs safely while alive
    field._on_focus_changed(None, dummy)

    # Deleting field works cleanly
    field.deleteLater()
    qtbot.wait(50)

    # Subsequent focus changes after deletion do not raise
    dummy.setFocus()

