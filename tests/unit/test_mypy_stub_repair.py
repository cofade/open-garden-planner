"""The Types gate's repair of PyQt6 6.12's invalid stubs (Phase 17 L7, #391).

PyQt6 6.12.0's generated stubs put the positional-only marker after ``*args`` — not
valid Python, so mypy rejected ``QtGui.pyi`` / ``QtDBus.pyi`` whole and the gate could
not run. ``scripts/check_mypy_baseline.py`` reads a copy with that marker dropped.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from scripts.check_mypy_baseline import _MARKER_AFTER_STAR_ARGS, sanitized_pyqt6_stubs


@pytest.mark.parametrize(("line", "expected"), [
    ("    def drawPolygon(self, point: QtCore.QPointF|None, *args: QtCore.QPointF, /) -> None: ...",
     "    def drawPolygon(self, point: QtCore.QPointF|None, *args: QtCore.QPointF) -> None: ..."),
    ("    def call(self, method: str|None, *args: typing.Any, /) -> 'QDBusMessage': ...",
     "    def call(self, method: str|None, *args: typing.Any) -> 'QDBusMessage': ..."),
])
def test_the_marker_after_star_args_is_dropped(line: str, expected: str) -> None:
    repaired, count = _MARKER_AFTER_STAR_ARGS.subn(r"\1)", line)
    assert (repaired, count) == (expected, 1)
    compile(f"class C:\n{repaired}", "<stub>", "exec")   # valid Python now
    with pytest.raises(SyntaxError):
        compile(f"class C:\n{line}", "<stub>", "exec")   # it was not


@pytest.mark.parametrize("line", [
    "    def drawPolygon(self, points: 'QPolygonF', /, fillRule: QtCore.Qt.FillRule = ...) -> None: ...",
    "    def drawConvexPolygon(self, poly: 'QPolygon', /) -> None: ...",
    "    def setValue(self, *args: typing.Any) -> None: ...",
    "    def f(self, a: int, /, *args: int) -> None: ...",
])
def test_a_valid_stub_line_is_left_alone(line: str) -> None:
    assert _MARKER_AFTER_STAR_ARGS.subn(r"\1)", line) == (line, 0)


def test_the_copy_is_valid_python_and_changes_nothing_else(tmp_path: Path) -> None:
    """Every repaired stub parses; apart from the repaired lines, each is byte-identical."""
    spec = importlib.util.find_spec("PyQt6")
    assert spec is not None and spec.submodule_search_locations
    source = Path(next(iter(spec.submodule_search_locations)))
    repairs = sanitized_pyqt6_stubs(tmp_path)
    copy = tmp_path / "PyQt6"
    assert (copy / "__init__.pyi").is_file()
    for stub in sorted(source.glob("*.pyi")):
        original = stub.read_text(encoding="utf-8").splitlines()
        repaired = (copy / stub.name).read_text(encoding="utf-8").splitlines()
        assert len(original) == len(repaired), stub.name
        changed = [(a, b) for a, b in zip(original, repaired, strict=True) if a != b]
        assert all(re.search(r"\*\w+: [^()]*?, /\)", a) and ", /)" not in b for a, b in changed)
        compile("\n".join(repaired), str(stub.name), "exec", flags=0, dont_inherit=True,
                _feature_version=11)
    # the tripwire: the day a PyQt6 release ships valid stubs this reads 0 — then remove
    # the repair (and the PyQt6 ignore_errors override in pyproject.toml)
    assert repairs == 19, ("PyQt6's stubs changed: re-check whether the Types gate still "
                           f"needs its repair ({repairs} lines repaired)")
