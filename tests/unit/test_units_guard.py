"""Prevent new UI measurement formats bypassing the units layer (#673)."""

import ast
import re
from pathlib import Path

ROOT = Path("src/open_garden_planner")
ALLOWLIST = {
    "ui/widgets/weather_widget.py": "Precipitation stays in mm; separate quantity follow-up.",
    "services/svg_export.py": "SVG XML width/height physical-unit syntax, independent of display preference (FR-EXP-02).",
}
UNIT = r"(?:cm²|m²|cm|mm|km|m|L)\b"
INLINE = re.compile(r"\{[^}]*\}\s?" + UNIT)
AFTER_VALUE = re.compile(r"^\s?" + UNIT)


class MeasurementGuard(ast.NodeVisitor):
    def __init__(self):
        self.hits = []
        self.unit_box_function = False

    def visit_FunctionDef(self, node):
        old = self.unit_box_function
        self.unit_box_function = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("LengthSpinBox", "VolumeSpinBox")
            for n in ast.walk(node)
        )
        self.generic_visit(node)
        self.unit_box_function = old

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return  # docstring
        self.generic_visit(node)

    def visit_Raise(self, node):
        pass

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            receiver = ast.unparse(node.func.value)
            if receiver in ("logging", "logger", "_logger", "_log", "log"):
                return
            if node.func.attr == "setSuffix" and node.args and not self.unit_box_function:
                value = node.args[0]
                if isinstance(value, ast.Call) and value.args:
                    value = value.args[0]
                if isinstance(value, ast.Constant) and value.value in (" cm", " m", " mm", " L"):
                    self.hits.append((node.lineno, ast.unparse(node)))
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        for a, b in zip(node.values, node.values[1:], strict=False):
            if (
                isinstance(a, ast.FormattedValue)
                and isinstance(b, ast.Constant)
                and AFTER_VALUE.search(b.value)
            ):
                self.hits.append((node.lineno, ast.unparse(node)))
        # Visit expressions, not literal fragments or format specs.
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                self.visit(value.value)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and INLINE.search(node.value):
            self.hits.append((node.lineno, node.value))


def test_no_inline_measurement_formats():
    hits = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if (
            relative in ALLOWLIST
            or relative == "core/units.py"
            or relative.startswith(("agent_api/", "core/scene3d/"))
        ):
            continue
        visitor = MeasurementGuard()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        hits.extend(f"{relative}:{line}: {text}" for line, text in visitor.hits)
    assert not hits, "\n".join(hits)


def test_one_definition_per_formatter():
    for name in ("format_length", "format_area"):
        locations = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert locations == ["core/units.py"]
